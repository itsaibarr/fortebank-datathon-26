"""Frozen local detection, ByteTrack fragments and appearance reconciliation.

This runtime registry is a model proposal, separate from the immutable human
tracking-review contract. No identity, geometry, role or training approval is
created here. Embeddings and registry files are private inference state.
"""

import errno
import json
import math
import socket
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from importlib.resources import files
from pathlib import Path
from typing import Literal

from PIL import Image

from forte.person_proposals import LocalByteTrack, YoloxONNX, detection_schedule, sha256
from forte.video import FrameRef, VideoRegistry, decode_video, open_video, oriented, probe_video


def require_outbound_blocked():
    """Fail closed unless the OS denies a route/socket before any packet is sent.

    UDP connect selects a route without sending a datagram or disclosing case
    facts. This is a conservative prerequisite check, not a sandbox installer.
    Use sandbox-exec deny-network or a Linux container with --network none.
    An environment variable is deliberately insufficient.
    """
    denied = []
    for family, destination in (
        (socket.AF_INET, ("192.0.2.1", 9)),
        (socket.AF_INET6, ("2001:db8::1", 9)),
    ):
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as probe:
                probe.connect(destination)
        except OSError as exc:
            accepted = {errno.EPERM, errno.EACCES, errno.ENETUNREACH, errno.EHOSTUNREACH}
            if family == socket.AF_INET6:
                accepted |= {errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT}
            if exc.errno in accepted:
                denied.append({"family": int(family), "errno": exc.errno})
                continue
            raise RuntimeError("Cannot verify offline inference isolation") from exc
        raise RuntimeError("Private inference requires OS-enforced outbound network denial")
    return {"outbound_probe": "os_denied", "errno": denied[0]["errno"], "families": denied}


def private_directory(path: Path):
    path = Path(path).resolve()
    if any((p / ".git").exists() for p in (path, *path.parents)):
        raise ValueError("Participant artifacts must remain outside Git")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def detector_configuration():
    asset = files("forte").joinpath("data/person-tracking.json")
    if asset.is_file():
        return json.loads(asset.read_text())
    return json.loads(
        (Path(__file__).resolve().parents[2] / "configs/person-tracking.json").read_text()
    )


@dataclass
class TrackingConfig:
    detector_weights: Path | None = None
    detector_config: dict | Path | None = None
    mode: Literal["byte_track", "reid"] = "reid"
    reid_manifest: Path | None = None
    cadence_sec: float = 0.2
    max_gap_sec: float = 8.0
    continuous_gap_sec: float = 0.6
    min_similarity: float = 0.82
    ambiguity_margin: float = 0.08
    switch_similarity: float = 0.35
    max_center_speed: float = 0.8
    max_area_ratio: float = 3.0
    min_crop_pixels: int = 1024
    min_quality: float = 0.5
    gallery_size: int = 8
    # Camera facts only. No zone implies an operational role or legal rule.
    camera_zones: list[dict] = field(default_factory=list)
    # Required for explicitly decoded-frame input; a digest, never a filename cue.
    source_sha256: str | None = None

    def __post_init__(self):
        numeric = (
            self.cadence_sec,
            self.max_gap_sec,
            self.continuous_gap_sec,
            self.min_similarity,
            self.ambiguity_margin,
            self.switch_similarity,
            self.max_center_speed,
            self.max_area_ratio,
            self.min_quality,
        )
        if not all(math.isfinite(x) for x in numeric):
            raise ValueError("Non-finite tracking configuration")
        if self.mode not in {"byte_track", "reid"}:
            raise ValueError("Unknown tracking mode")
        if not (0 < self.cadence_sec <= self.continuous_gap_sec <= self.max_gap_sec):
            raise ValueError("Invalid tracking time bounds")
        if not (0 < self.min_similarity <= 1 and 0 <= self.ambiguity_margin <= 1):
            raise ValueError("Invalid appearance gate")
        if not (0 <= self.switch_similarity < self.min_similarity and 0 < self.min_quality <= 1):
            raise ValueError("Invalid appearance quality/switch gate")
        if not (self.max_center_speed > 0 and self.max_area_ratio >= 1):
            raise ValueError("Invalid motion/geometry gate")
        if not (1 <= self.gallery_size <= 32 and self.min_crop_pixels >= 16):
            raise ValueError("Invalid gallery/crop bounds")
        for zone in self.camera_zones:
            if zone.get("kind") not in {"reflection", "workstation", "public", "staff"}:
                raise ValueError("Unknown camera zone kind")
            polygon = zone.get("polygon", [])
            if not zone.get("zone_id") or len(polygon) < 3:
                raise ValueError("Camera zones require an ID and normalized polygon")
            if any(len(p) != 2 or any(not 0 <= v <= 1 for v in p) for p in polygon):
                raise ValueError("Invalid normalized camera polygon")


class LocalReIDONNX:
    """Hash-bound, frozen OSNet feature extraction; no model download or training.

    The caller must prepare a genuine pretrained feature-extractor ONNX export
    and its provenance manifest. Supplying an architecture name alone is never
    recorded as proof of pretrained weights.
    """

    def __init__(self, manifest_path: Path):
        import onnxruntime as ort

        manifest_path = Path(manifest_path).resolve(strict=True)
        cfg = json.loads(manifest_path.read_bytes())
        required = {"weights", "weights_sha256", "architecture", "pretrained", "input_size"}
        if not required <= cfg.keys() or not cfg["architecture"].startswith("osnet_"):
            raise ValueError("Expected a documented pretrained OSNet ONNX export")
        pretrained = cfg["pretrained"]
        if not all(pretrained.get(k) for k in ("source", "revision", "checkpoint_sha256")):
            raise ValueError("Pretrained checkpoint provenance is required")
        if any(
            len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
            for digest in (cfg["weights_sha256"], pretrained["checkpoint_sha256"])
        ):
            raise ValueError("Expected SHA256 weight fingerprints")
        weights = (manifest_path.parent / cfg["weights"]).resolve(strict=True)
        if (
            not weights.is_relative_to(manifest_path.parent)
            or sha256(weights) != cfg["weights_sha256"]
        ):
            raise ValueError("ReID weight hash/path mismatch")
        self.height, self.width = cfg["input_size"]
        if not (32 <= self.height <= 512 and 16 <= self.width <= 256):
            raise ValueError("Unsupported ReID input dimensions")
        self.mean = cfg.get("mean", [0.485, 0.456, 0.406])
        self.std = cfg.get("std", [0.229, 0.224, 0.225])
        if len(self.mean) != 3 or len(self.std) != 3 or any(x <= 0 for x in self.std):
            raise ValueError("Invalid ReID RGB preprocessing")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.enable_profiling = False
        self.session = ort.InferenceSession(
            str(weights), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 3, self.height, self.width]:
            raise ValueError("Unexpected ReID input shape; export a fixed RGB NCHW feature model")
        if len(outputs) != 1 or len(outputs[0].shape) != 2 or outputs[0].shape[0] != 1:
            raise ValueError("Expected a single embedding output, not classifier logits")
        if (
            cfg.get("output_kind") != "embedding"
            or cfg.get("feature_dimension") != outputs[0].shape[1]
        ):
            raise ValueError("Explicit feature output and dimension are required")
        self.input_name = inputs[0].name
        self.feature_dimension = cfg["feature_dimension"]
        self.provenance = {
            **cfg,
            "manifest_sha256": sha256(manifest_path),
            "frozen": True,
            "provider": "CPUExecutionProvider",
        }

    def embed(self, image: Image.Image):
        import numpy as np

        pixels = (
            np.asarray(
                image.convert("RGB").resize((self.width, self.height), Image.Resampling.BILINEAR),
                dtype=np.float32,
            )
            / 255.0
        )
        pixels = (pixels - np.asarray(self.mean, dtype=np.float32)) / np.asarray(
            self.std, dtype=np.float32
        )
        tensor = np.ascontiguousarray(pixels.transpose(2, 0, 1))[None]
        output = self.session.run(None, {self.input_name: tensor})[0]
        if output.shape != (1, self.feature_dimension):
            raise ValueError("Unexpected ReID output shape")
        return normalized_embedding(output[0].tolist())


def normalized_embedding(values):
    values = [float(x) for x in values]
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("Invalid appearance embedding")
    norm = math.sqrt(sum(x * x for x in values))
    if norm <= 1e-12:
        raise ValueError("Degenerate appearance embedding")
    return [x / norm for x in values]


def cosine(a, b):
    if len(a) != len(b):
        raise ValueError("Inconsistent appearance feature dimensions")
    return sum(x * y for x, y in zip(a, b, strict=True))


def similarity(a, b):
    return max(
        (cosine(x["embedding"], y["embedding"]) for x in a for y in b),
        default=None,
    )


def bounded_gallery(entries, size):
    # Keep high-quality exemplars with distinct source frames, bounded per person.
    unique = {e["frame_id"]: e for e in entries}
    return sorted(unique.values(), key=lambda e: (-e["quality"], e["frame_id"]))[:size]


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def in_polygon(point, polygon):
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def view_zone(box, zones):
    return next(
        (
            z["zone_id"]
            for z in zones
            if z["kind"] == "reflection" and in_polygon(center(box), z["polygon"])
        ),
        None,
    )


@dataclass
class DecodedFrame:
    ref: FrameRef
    image: Image.Image
    time_base: str
    source_width: int
    source_height: int
    rotation: float = 0


def source_transform(width, height, rotation):
    # PIL.rotate uses counterclockwise display rotation, with continuous edge coordinates.
    angle = rotation % 360
    transforms = {
        0: [1, 0, 0, 0, 1, 0],
        90: [0, 1, 0, -1, 0, width],
        180: [-1, 0, width, 0, -1, height],
        270: [0, -1, height, 1, 0, 0],
    }
    if angle not in transforms:
        raise ValueError("Only source right-angle rotations are supported")
    return transforms[angle]


def source_frames(registry, selected, deadline):
    metadata = probe_video(registry.path)
    count = 0
    with open_video(registry.path) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        for ordinal, frame in enumerate(container.decode(stream)):
            if time.monotonic() >= deadline:
                raise TimeoutError("Participant tracking deadline exhausted")
            if (
                ordinal >= len(registry.frames)
                or frame.pts != registry.frames[ordinal].source_pts
                or frame.is_corrupt
            ):
                raise ValueError("Tracking source PTS association changed")
            count += 1
            if ordinal in selected:
                yield DecodedFrame(
                    registry.frames[ordinal],
                    oriented(frame, stream, registry.rotation),
                    str(frame.time_base),
                    metadata["width"],
                    metadata["height"],
                    registry.rotation,
                )
    if count != len(registry.frames) or sha256(registry.path) != registry.source_sha256:
        raise ValueError("Incomplete or changed tracking source")


def _box_embedding(image, box, score, ref, config, embedder):
    width, height = image.size
    edges = (
        math.floor(box[0] * width),
        math.floor(box[1] * height),
        math.ceil(box[2] * width),
        math.ceil(box[3] * height),
    )
    pixels = (edges[2] - edges[0]) * (edges[3] - edges[1])
    truncated = min(box[0], box[1]) <= 0.005 or max(box[2], box[3]) >= 0.995
    quality = score * (0.5 if truncated else 1.0)
    if embedder is None or pixels < config.min_crop_pixels or quality < config.min_quality:
        return None
    return {
        "frame_id": ref.frame_id,
        "quality": quality,
        "embedding": normalized_embedding(embedder.embed(image.crop(edges))),
        "crop_pixels": list(edges),
        "source_oriented_box": list(box),
    }


def _motion_gate(previous, current, config):
    gap = current["timestamp_sec"] - previous["timestamp_sec"]
    if not 0 < gap <= config.max_gap_sec:
        return None
    a, b = previous["box"], current["box"]
    areas = [(x[2] - x[0]) * (x[3] - x[1]) for x in (a, b)]
    ratio = max(areas) / min(areas)
    distance = math.dist(center(a), center(b))
    speed = distance / max(gap, config.cadence_sec)
    if ratio > config.max_area_ratio or speed > config.max_center_speed:
        return None
    return {"gap_sec": gap, "center_speed": speed, "area_ratio": ratio}


def reconcile_segments(segments, config):
    """Conservative causal fragment association using real appearance features.

    Greedy choices require a margin over all temporally/geometrically eligible
    candidates. Simultaneous segments cannot share a canonical identity. Mirror
    observations never enter the physical participant candidate pool.
    """
    participants, views, unresolved = [], [], []
    for segment in sorted(
        segments, key=lambda s: (s["observations"][0]["timestamp_sec"], s["segment_id"])
    ):
        if segment["reflection_zone_id"] is not None:
            segment["participant_id"] = None
            views.append(
                {
                    "segment_id": segment["segment_id"],
                    "view_kind": "reflection",
                    "zone_id": segment["reflection_zone_id"],
                    "canonical_person_id": None,
                    "review_status": "model_proposal",
                    "ownership": "unknown",
                    "evidence_frame_ids": [o["frame_id"] for o in segment["observations"]],
                }
            )
            continue
        candidates = []
        if config.mode == "reid" and segment["gallery"]:
            for person in participants:
                previous = person["track_segments"][-1]
                motion = _motion_gate(
                    previous["observations"][-1], segment["observations"][0], config
                )
                score = similarity(person["appearance_gallery"], segment["gallery"])
                if motion is not None and score is not None:
                    candidates.append((score, person, previous, motion))
        candidates.sort(key=lambda x: (-x[0], x[1]["participant_id"]))
        selected = None
        if candidates and candidates[0][0] >= config.min_similarity:
            if (
                len(candidates) == 1
                or candidates[0][0] - candidates[1][0] >= config.ambiguity_margin
            ):
                selected = candidates[0]
            else:
                unresolved.append(
                    {
                        "segment_id": segment["segment_id"],
                        "reason": "ambiguous_appearance",
                        "candidate_participant_ids": [
                            c[1]["participant_id"] for c in candidates[:3]
                        ],
                        "similarities": [c[0] for c in candidates[:3]],
                        "review_status": "unresolved",
                    }
                )
        if selected:
            score, person, previous, motion = selected
            person["association_evidence"].append(
                {
                    "from_segment_id": previous["segment_id"],
                    "to_segment_id": segment["segment_id"],
                    "origin": "frozen_reid_and_motion",
                    "similarity": score,
                    **motion,
                    "evidence_frame_ids": [
                        previous["observations"][-1]["frame_id"],
                        segment["observations"][0]["frame_id"],
                    ],
                    "review_status": "model_proposal",
                }
            )
            person["visibility_gaps"].append(
                {
                    "start_sec": previous["observations"][-1]["timestamp_sec"],
                    "end_sec": segment["observations"][0]["timestamp_sec"],
                    "state": "unobserved_between_samples",
                }
            )
        else:
            person = {
                "participant_id": f"p{len(participants) + 1:04d}",
                "identity_status": "model_proposal",
                "track_segments": [],
                "association_evidence": [],
                "appearance_gallery": [],
                "conflicts": [],
                "visibility_gaps": [],
                "role_hypotheses": [],
            }
            participants.append(person)
        segment["participant_id"] = person["participant_id"]
        person["track_segments"].append(segment)
        person["appearance_gallery"] = bounded_gallery(
            person["appearance_gallery"] + segment["gallery"], config.gallery_size
        )
        person["conflicts"].extend(segment["conflicts"])
        for before, after in zip(
            segment["observations"][:-1], segment["observations"][1:], strict=True
        ):
            if after["timestamp_sec"] - before["timestamp_sec"] > config.cadence_sec * 1.5:
                person["visibility_gaps"].append(
                    {
                        "start_sec": before["timestamp_sec"],
                        "end_sec": after["timestamp_sec"],
                        "state": "missing_detection_samples",
                    }
                )
    return participants, views, unresolved


def analyze_participants(
    source,
    work_dir: Path,
    config: TrackingConfig | dict,
    *,
    deadline=None,
    detector=None,
    tracker=None,
    embedder=None,
):
    """Analyze source PTS frames once, preserving recording-local proposal IDs.

    ``source`` accepts a Path, VideoRegistry or iterable of DecodedFrame. Runtime
    components may be injected for synthetic tests; network denial is still
    required. A new output directory is mandatory, so previous review artifacts
    can never be replaced. Missing ReID assets fail rather than silently degrade.
    """
    isolation = require_outbound_blocked()
    if isinstance(config, dict):
        config = TrackingConfig(**config)
    work_dir = private_directory(work_dir)
    target = work_dir / "participants.json"
    if target.exists():
        raise FileExistsError("Participant run already exists; choose a new revision directory")
    deadline = deadline if deadline is not None else time.monotonic() + 270
    if config.mode == "reid" and embedder is None:
        if config.reid_manifest is None:
            raise ValueError("ReID mode requires a real local pretrained ONNX manifest")
        embedder = LocalReIDONNX(config.reid_manifest)
    if detector is None:
        if config.detector_weights is None:
            raise ValueError("Detector weights are required")
        detector_cfg = config.detector_config or detector_configuration()
        if isinstance(detector_cfg, (str, Path)):
            detector_cfg = json.loads(Path(detector_cfg).read_bytes())
        detector = YoloxONNX(Path(config.detector_weights), detector_cfg)
    tracker = tracker if tracker is not None else LocalByteTrack(config.cadence_sec)
    if isinstance(source, (str, Path)):
        source = decode_video(Path(source), work_dir / "decode-cache", deadline)
    if isinstance(source, VideoRegistry):
        if sha256(source.path) != source.source_sha256:
            raise ValueError("Tracking source changed after decode")
        selected = detection_schedule(source.frames, config.cadence_sec)
        selected |= {f.ordinal for f in source.frames if f.frame_id in source.cached}
        frames = source_frames(source, selected, deadline)
        fingerprint = source.source_sha256
        full_refs = [asdict(f) for f in source.frames]
        duration = source.duration
    else:
        frames, full_refs, duration = iter(source), [], None
        fingerprint = config.source_sha256
    if (
        not fingerprint
        or len(fingerprint) != 64
        or any(c not in "0123456789abcdef" for c in fingerprint)
    ):
        raise ValueError("Source recording SHA256 is required")
    segments, active, source_table = [], {}, []
    last_timestamp, last_ordinal, seen_ids, pts_origin = -1.0, -1, set(), None
    started = time.monotonic()
    for frame in frames:
        if time.monotonic() >= deadline:
            raise TimeoutError("Participant tracking deadline exhausted")
        ref = frame.ref
        if (
            not math.isfinite(ref.timestamp_sec)
            or ref.timestamp_sec < 0
            or ref.timestamp_sec <= last_timestamp
            or ref.ordinal <= last_ordinal
            or ref.frame_id in seen_ids
        ):
            raise ValueError("Participant frames must preserve unique source PTS order")
        base = Fraction(frame.time_base)
        if base <= 0 or not isinstance(ref.source_pts, int):
            raise ValueError("Invalid original source PTS/time base")
        source_time = float(ref.source_pts * base)
        pts_origin = source_time - ref.timestamp_sec if pts_origin is None else pts_origin
        if not math.isclose(source_time - pts_origin, ref.timestamp_sec, abs_tol=1e-6):
            raise ValueError("Source PTS and normalized timestamp disagree")
        expected_size = (frame.source_width, frame.source_height)
        if frame.rotation % 180:
            expected_size = expected_size[::-1]
        if frame.image.size != expected_size or min(expected_size) <= 0:
            raise ValueError("Oriented image dimensions disagree with source transform")
        seen_ids.add(ref.frame_id)
        last_timestamp, last_ordinal = ref.timestamp_sec, ref.ordinal
        source_table.append(
            {
                **asdict(ref),
                "time_base": frame.time_base,
                "source_dimensions": [frame.source_width, frame.source_height],
                "oriented_dimensions": list(frame.image.size),
                "rotation": frame.rotation,
                "source_to_oriented_affine": source_transform(
                    frame.source_width, frame.source_height, frame.rotation
                ),
            }
        )
        updates = tracker.update(detector.detect(frame.image), ref.timestamp_sec)
        seen_track_ids = set()
        for tracker_id, box, score in updates:
            box = [float(v) for v in box]
            if (
                len(box) != 4
                or any(not math.isfinite(v) or not 0 <= v <= 1 for v in box)
                or not box[0] < box[2]
                or not box[1] < box[3]
                or not math.isfinite(score)
                or not 0 <= score <= 1
                or tracker_id in seen_track_ids
            ):
                raise ValueError("Invalid or duplicate tracked detection")
            seen_track_ids.add(tracker_id)
            zone_id = view_zone(box, config.camera_zones)
            entry = _box_embedding(
                frame.image, box, score, ref, config, embedder if config.mode == "reid" else None
            )
            segment = active.get(tracker_id)
            conflict = None
            if segment and entry and segment["gallery"]:
                if similarity(segment["gallery"], [entry]) < config.switch_similarity:
                    conflict = {
                        "frame_id": ref.frame_id,
                        "reason": "appearance_conflicts_with_tracker_id",
                        "review_status": "unresolved",
                    }
            if (
                segment is None
                or conflict
                or ref.timestamp_sec - segment["observations"][-1]["timestamp_sec"]
                > config.continuous_gap_sec
                or segment["reflection_zone_id"] != zone_id
            ):
                segment = {
                    "segment_id": f"s{len(segments) + 1:05d}",
                    "tracker_id": int(tracker_id),
                    "participant_id": None,
                    "reflection_zone_id": zone_id,
                    "observations": [],
                    "gallery": [],
                    "conflicts": [conflict] if conflict else [],
                    "review_status": "model_proposal",
                }
                segments.append(segment)
                active[tracker_id] = segment
            segment["observations"].append(
                {
                    "frame_id": ref.frame_id,
                    "source_pts": ref.source_pts,
                    "timestamp_sec": ref.timestamp_sec,
                    "box": box,
                    "confidence": float(score),
                    "origin": "detector",
                    "geometry_origin": "yolox_person_detection",
                    "tracker_id_origin": "ByteTrack_motion_association",
                    "geometry_review": "unreviewed",
                }
            )
            if entry:
                segment["gallery"] = bounded_gallery(
                    segment["gallery"] + [entry], config.gallery_size
                )
    if not source_table:
        raise ValueError("No participant source frames")
    participants, views, unresolved = reconcile_segments(segments, config)
    frame_boxes = {f["frame_id"]: {} for f in source_table}
    for segment in segments:
        if segment["participant_id"] is not None:
            for obs in segment["observations"]:
                frame_boxes[obs["frame_id"]][segment["participant_id"]] = obs["box"]
    result = {
        "schema_version": 1,
        "source_sha256": fingerprint,
        "participant_id_scope": "recording_local_model_proposals",
        "box_coordinate_space": "oriented_normalized_xyxy",
        "participants": participants,
        "segments": segments,
        "frame_boxes": frame_boxes,
        "source_frames": full_refs
        or [{k: f[k] for k in asdict(FrameRef("", 0, 0, 0))} for f in source_table],
        "sampled_source_frames": source_table,
        "view_observations": views,
        "unresolved_matches": unresolved,
        "camera_zones": config.camera_zones,
        "coverage": {
            "duration_sec": duration,
            "detection_frame_ids": [f["frame_id"] for f in source_table],
            "cadence_sec": config.cadence_sec,
            "complete_continuous_visibility": False,
            "state": "sampled_observations_only",
        },
        "provenance": {
            "origin": "model",
            "purpose": "frozen_inference_not_training_truth",
            "mode": config.mode,
            "detector": detector.provenance,
            "tracker": "trackers.ByteTrackTracker via supervision.Detections",
            "appearance_reconciliation_executed": config.mode == "reid",
            "reid": getattr(embedder, "provenance", None),
            "weights_frozen": True,
            "human_approval_created": False,
            "network_isolation": isolation,
            "elapsed_sec": time.monotonic() - started,
        },
    }
    with target.open("x") as output:
        output.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    target.chmod(0o600)
    return result


def continuity_metrics(registry, reviewed_assignments):
    """Evaluate only explicit reviewed (frame, segment)->anonymous person labels.

    Missing labels are excluded. This measures continuity errors among matched
    detections; it is not detector recall or legal/role accuracy.
    """
    predicted = {
        (o["frame_id"], s["segment_id"]): s["participant_id"]
        for s in registry["segments"]
        for o in s["observations"]
        if s["participant_id"] is not None
    }
    pairs = [
        (key, truth, predicted[key])
        for key, truth in reviewed_assignments.items()
        if key in predicted
    ]
    truth_counts = Counter(truth for _, truth, _ in pairs)
    prediction_counts = Counter(prediction for _, _, prediction in pairs)
    joint_counts = Counter((truth, prediction) for _, truth, prediction in pairs)

    def count_pairs(counts):
        return sum(n * (n - 1) // 2 for n in counts.values())

    correctly_shared = count_pairs(joint_counts)
    return {
        "reviewed_observations": len(pairs),
        "reviewed_pairs": len(pairs) * (len(pairs) - 1) // 2,
        "false_merge_pairs": count_pairs(prediction_counts) - correctly_shared,
        "false_split_pairs": count_pairs(truth_counts) - correctly_shared,
        "unmatched_reviewed_observations": len(reviewed_assignments) - len(pairs),
        "scope": "matched_reviewed_identity_pairs_only",
    }


def benchmark_continuity(byte_track, reid, baseline_assignments, reid_assignments):
    """Compare two offline runs against the same reviewed observation population.

    Assignments use each run's own (source frame ID, segment ID) keys. The caller
    matches reviewed geometry to detections locally; labels are never generated
    from the predictions. Different unmatched counts preclude an improvement
    claim, and empty supervision is explicitly unmeasured.
    """
    if byte_track["source_sha256"] != reid["source_sha256"]:
        raise ValueError("Continuity comparison requires the identical source recording")
    if Counter((key[0], value) for key, value in baseline_assignments.items()) != Counter(
        (key[0], value) for key, value in reid_assignments.items()
    ):
        raise ValueError("Continuity comparison requires identical reviewed actor populations")
    before = continuity_metrics(byte_track, baseline_assignments)
    after = continuity_metrics(reid, reid_assignments)
    matched = (
        before["unmatched_reviewed_observations"] == after["unmatched_reviewed_observations"] == 0
    )
    return {
        "byte_track": before,
        "reid": after,
        "comparable_complete_reviewed_population": matched,
        "quality_measured": bool(before["reviewed_pairs"] and after["reviewed_pairs"] and matched),
        "scope": "reviewed_matched_detection_identity_continuity_only",
        "weights_updated": False,
    }
