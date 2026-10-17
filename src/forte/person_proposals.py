"""Private local YOLOX → ByteTrack proposals and source-linked review packets.

YOLOX preprocessing/decoding follows Megvii's Apache-2.0 ONNX demo at
6ddff4824372906469a7fae2dc3206c7aa4bbaee. No inference/hosted SDK is used.
"""

import bisect
import hashlib
import html
import json
import math
import os
import re
import shutil
import time
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path

import av
from PIL import ImageDraw

from forte.annotations import Annotation
from forte.tracking import SegmentBuilder, TrackManifest, validate_pair
from forte.video import decode_video, open_video, oriented, probe_video


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    Path(path).chmod(0o600)


def allowlisted_sources(selection: Path, source_dir: Path):
    """Project only neutral/hash/split fields. Never read supplied semantic labels."""
    records = []
    for group in json.loads(selection.read_bytes())["groups"]:
        if group["split"] != "development":
            continue
        neutral = Path(group["neutral_file"])
        if not re.fullmatch(r"clip\d{3}\.mov", neutral.name) or neutral.name != str(neutral):
            raise ValueError("Expected neutral allowlist basename")
        fingerprint = group["recording_id"]
        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError("Invalid allowlist recording hash")
        source = source_dir / neutral
        if source.resolve().parent != source_dir.resolve():
            raise ValueError("Source escaped neutral directory")
        records.append(dict(clip_id=neutral.stem, source=source, recording_group=fingerprint))
    if len({r["clip_id"] for r in records}) != len(records) or len(
        {r["recording_group"] for r in records}
    ) != len(records):
        raise ValueError("Duplicate allowlisted recording or clip")
    return records


def verify_source(record):
    if sha256(record["source"]) != record["recording_group"]:
        raise ValueError("Allowlisted source hash mismatch")


def verify_manifest_source(manifest, source):
    """Decode actual media again; self-consistent JSON alone proves no binding."""
    if sha256(source) != manifest.source_sha256:
        raise ValueError("Source hash mismatch")
    info = probe_video(source)
    if (info["width"], info["height"], info["rotation"]) != (
        manifest.source_width,
        manifest.source_height,
        manifest.rotation,
    ):
        raise ValueError("Source dimensions/orientation changed")
    count = 0
    last_span = 0
    with open_video(source) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        if str(stream.time_base) != manifest.time_base:
            raise ValueError("Source time base mismatch")
        for i, frame in enumerate(container.decode(stream)):
            if (
                i >= len(manifest.frames)
                or frame.pts != manifest.frames[i].source_pts
                or frame.is_corrupt
            ):
                raise ValueError("Actual source frame association mismatch")
            count += 1
            last_span = float(frame.duration * frame.time_base) if frame.duration else 0
        if last_span <= 0:
            last_span = 1 / float(stream.average_rate) if stream.average_rate else 0.04
    if count != len(manifest.frames):
        raise ValueError("Incomplete source frame mapping")
    if not math.isclose(
        manifest.duration_sec, manifest.frames[-1].timestamp_sec + last_span, abs_tol=1e-6
    ):
        raise ValueError("Actual source duration mismatch")


class YoloxONNX:
    """Official COCO person class (index 0), fixed 640 ONNX release, CPU only."""

    def __init__(self, weights: Path, config: dict):
        import numpy as np
        import onnxruntime as ort

        if sha256(weights) != config["weights_sha256"]:
            raise ValueError("Detector weight hash mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.enable_profiling = False
        self.session = ort.InferenceSession(
            str(weights), sess_options=options, providers=["CPUExecutionProvider"]
        )
        if self.session.get_inputs()[0].shape != [1, 3, 640, 640]:
            raise ValueError("Unexpected YOLOX input shape")
        self.name = self.session.get_inputs()[0].name
        self.provenance = config
        self.threshold = config.get("detector_score_floor", 0.1)
        self.grid = np.concatenate(
            [
                np.stack(np.meshgrid(np.arange(640 // s), np.arange(640 // s)), axis=-1).reshape(
                    -1, 2
                )
                for s in (8, 16, 32)
            ]
        )
        self.strides = np.concatenate([np.full(((640 // s) ** 2, 1), s) for s in (8, 16, 32)])

    def detect(self, image):
        import cv2
        import numpy as np

        rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]
        ratio = min(640 / height, 640 / width)
        rw, rh = int(width * ratio), int(height * ratio)
        resized = cv2.resize(rgb[:, :, ::-1], (rw, rh), interpolation=cv2.INTER_LINEAR)
        padded = np.full((640, 640, 3), 114, dtype=np.uint8)
        padded[:rh, :rw] = resized
        tensor = np.ascontiguousarray(padded.transpose(2, 0, 1), dtype=np.float32)[None]
        pred = self.session.run(None, {self.name: tensor})[0][0]
        if pred.shape != (8400, 85) or not np.isfinite(pred).all():
            raise ValueError("Unexpected YOLOX output")
        scores = pred[:, 4] * pred[:, 5]
        keep = (scores >= self.threshold) & (pred[:, 5:].argmax(axis=1) == 0)
        pred, scores = pred[keep], scores[keep]
        centers = (pred[:, :2] + self.grid[keep]) * self.strides[keep]
        sizes = np.exp(pred[:, 2:4]) * self.strides[keep]
        boxes = np.concatenate([centers - sizes / 2, centers + sizes / 2], axis=1)
        # Invert actual integer resize dimensions; remove top-left padding.
        boxes /= np.array([rw, rh, rw, rh])
        boxes = np.clip(boxes, 0, 1)
        valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
        boxes, scores = boxes[valid], scores[valid]
        indices = sorted(range(len(boxes)), key=lambda i: (-float(scores[i]), i))
        from forte.tracking import iou

        result = []
        while indices:
            current = indices.pop(0)
            result.append((tuple(float(x) for x in boxes[current]), float(scores[current])))
            indices = [i for i in indices if iou(boxes[current], boxes[i]) <= 0.45]
        return result


class LocalByteTrack:
    def __init__(self, cadence_sec):
        from trackers import ByteTrackTracker

        self.tracker = ByteTrackTracker(
            frame_rate=1 / cadence_sec,
            lost_track_buffer=30,
            track_activation_threshold=0.5,
            minimum_consecutive_frames=1,
            minimum_iou_threshold=0.1,
            high_conf_det_threshold=0.5,
        )
        self.unmatched = 0

    def update(self, boxes, timestamp):
        import numpy as np
        import supervision as sv

        detections = sv.Detections(
            xyxy=np.array([b for b, _ in boxes], dtype=np.float32).reshape(-1, 4),
            confidence=np.array([s for _, s in boxes], dtype=np.float32),
            class_id=np.zeros(len(boxes), dtype=int),
        )
        # Scale normalized boxes to a consistent virtual 1000px frame for Kalman
        # covariance. Returning to normalized coordinates loses no source mapping.
        detections.xyxy *= 1000
        tracked = self.tracker.update(detections, timestamp=timestamp)
        result = []
        for box, confidence, id in zip(
            tracked.xyxy, tracked.confidence, tracked.tracker_id, strict=True
        ):
            if id < 0:
                self.unmatched += 1
                id = -self.unmatched
            result.append((int(id), tuple(float(x) / 1000 for x in box), float(confidence)))
        return result


def detection_schedule(frames, cadence_sec):
    if not math.isfinite(cadence_sec) or cadence_sec <= 0:
        raise ValueError("Invalid detection cadence")
    selected, next_time = set(), 0.0
    for f in frames:
        if f.timestamp_sec + 1e-9 >= next_time:
            selected.add(f.ordinal)
            next_time = (math.floor((f.timestamp_sec + 1e-9) / cadence_sec) + 1) * cadence_sec
    selected.add(frames[-1].ordinal)
    return selected


def boxes_at(manifest, ordinal):
    """Display-only interpolation within a segment, never across uncertain joins."""
    frames = manifest.frames
    result = []
    for segment in manifest.segments:
        indices = [int(b.frame_id[1:]) for b in segment.boxes]
        pos = bisect.bisect_left(indices, ordinal)
        if pos < len(indices) and indices[pos] == ordinal:
            box = segment.boxes[pos]
            if not box.outside:
                result.append((segment, box.xyxy, box.origin))
        elif 0 < pos < len(indices):
            left, right = segment.boxes[pos - 1 : pos + 1]
            lo, hi = frames[indices[pos - 1]], frames[indices[pos]]
            if (
                not left.outside
                and not right.outside
                and hi.timestamp_sec - lo.timestamp_sec <= manifest.cadence_sec * 1.6
            ):
                fraction = (frames[ordinal].timestamp_sec - lo.timestamp_sec) / (
                    hi.timestamp_sec - lo.timestamp_sec
                )
                xyxy = tuple(
                    a + (b - a) * fraction for a, b in zip(left.xyxy, right.xyxy, strict=True)
                )
                result.append((segment, xyxy, "interpolation"))
    return result


def overlay(image, boxes, frame):
    output = image.copy()
    draw = ImageDraw.Draw(output)
    for segment, box, origin in boxes:
        coords = [
            box[0] * image.width,
            box[1] * image.height,
            box[2] * image.width,
            box[3] * image.height,
        ]
        draw.rectangle(coords, outline="#ffcc00", width=3)
        draw.text(
            (coords[0], max(0, coords[1] - 15)),
            f"{segment.person_id}/{segment.id} {origin} DRAFT",
            fill="#ffcc00",
            stroke_width=1,
            stroke_fill="black",
        )
    draw.text(
        (5, 5),
        f"{frame.frame_id} PTS={frame.source_pts} t={frame.timestamp_sec:.3f} DRAFT",
        fill="white",
        stroke_width=1,
        stroke_fill="black",
    )
    return output


def build_packet(source, output, manifest, extra_frame_ids=()):
    """Full dense playback + chronological before/during/after source frames/crops."""
    from forte.track_review import export_cvat

    assets_dir = output / "frames"
    assets_dir.mkdir(mode=0o700)
    selected = {int(id[1:]) for id in extra_frame_ids}
    for s in manifest.segments:
        indices = [int(b.frame_id[1:]) for b in s.boxes]
        # Retain surrounding full-scene context, including before/after the person.
        for index in (indices[0], indices[len(indices) // 2], indices[-1]):
            selected.add(index)
            times = [f.timestamp_sec for f in manifest.frames]
            for offset in (-2, 2):
                selected.add(
                    min(len(times) - 1, bisect.bisect_left(times, max(0, times[index] + offset)))
                )
    if not selected:
        selected = {0, len(manifest.frames) // 2, len(manifest.frames) - 1}
    assets = []
    with (
        open_video(source) as container,
        av.open(str(output / "review.mp4"), "w") as movie,
        av.open(str(output / "oriented-source.mp4"), "w") as clean,
    ):
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        streams = []
        for target in (movie, clean):
            dst = target.add_stream("libx264", rate=stream.average_rate or 25)
            dst.width, dst.height = manifest.oriented_width, manifest.oriented_height
            dst.pix_fmt = "yuv420p"
            dst.time_base = Fraction(manifest.time_base)
            # VFR timestamps can be closer than 1 / average_rate. Setting only
            # the muxer time base lets the encoder round distinct source PTS
            # onto the same tick (non-monotonic DTS). Preserve both time bases.
            dst.codec_context.time_base = Fraction(manifest.time_base)
            dst.options = {"crf": "23", "preset": "ultrafast", "tune": "zerolatency"}
            dst.codec_context.max_b_frames = 0
            streams.append(dst)
        for i, decoded in enumerate(container.decode(stream)):
            ref = manifest.frames[i]
            if decoded.pts != ref.source_pts:
                raise ValueError("Source changed while producing review media")
            image = oriented(decoded, stream, manifest.rotation)
            boxes = boxes_at(manifest, i)
            marked = overlay(image, boxes, ref)
            if i in selected:
                full = assets_dir / f"{ref.frame_id}.jpg"
                marked_path = assets_dir / f"{ref.frame_id}-overlay.jpg"
                image.save(full, "JPEG", quality=95)
                marked.save(marked_path, "JPEG", quality=95)
                item = dict(
                    frame_id=ref.frame_id,
                    source_pts=ref.source_pts,
                    timestamp_sec=ref.timestamp_sec,
                    full_scene=str(full.relative_to(output)),
                    full_scene_sha256=sha256(full),
                    overlay=str(marked_path.relative_to(output)),
                    overlay_sha256=sha256(marked_path),
                    crops=[],
                )
                for segment, box, origin in boxes:
                    crop_box = (
                        math.floor(box[0] * image.width),
                        math.floor(box[1] * image.height),
                        math.ceil(box[2] * image.width),
                        math.ceil(box[3] * image.height),
                    )
                    crop_path = assets_dir / f"{ref.frame_id}-{segment.id}.jpg"
                    image.crop(crop_box).save(crop_path, "JPEG", quality=95)
                    item["crops"].append(
                        dict(
                            segment_id=segment.id,
                            person_id=segment.person_id,
                            path=str(crop_path.relative_to(output)),
                            sha256=sha256(crop_path),
                            full_frame_pixel_crop=crop_box,
                            origin=origin,
                        )
                    )
                assets.append(item)
            for target, dst, im in zip((movie, clean), streams, (marked, image), strict=True):
                video_frame = av.VideoFrame.from_image(im)
                video_frame.pts = ref.source_pts - manifest.frames[0].source_pts
                video_frame.time_base = Fraction(manifest.time_base)
                for packet in dst.encode(video_frame):
                    target.mux(packet)
        for target, dst in zip((movie, clean), streams, strict=True):
            for packet in dst.encode():
                target.mux(packet)
    write_json(output / "review-assets.json", assets)
    export_cvat(manifest, output / "cvat.xml", output / "cvat-source-map.json")
    rows = []
    for item in assets:
        crops = "".join(
            f'<a href="{html.escape(c["path"])}">{html.escape(c["segment_id"])}</a> '
            for c in item["crops"]
        )
        rows.append(
            f"<p>{item['frame_id']} • {item['timestamp_sec']:.3f}s • PTS {item['source_pts']}"
            f' • <a href="{item["full_scene"]}">unchanged full scene</a> • crops {crops}<br>'
            f'<a href="{item["overlay"]}"><img width="640" loading="lazy" '
            f'src="{item["overlay"]}"></a></p>'
        )
    page = """<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' file: data:;
style-src 'unsafe-inline'">
<title>Private draft review</title><style>body{font:16px system-ui;max-width:1100px;margin:2em auto;
background:#181818;color:#eee}a{color:#9cd}video{width:100%}img{max-width:100%}</style>
<h1>Private draft review — CLIP</h1><p>All boxes/IDs are proposals. Roles, actions and work areas
require local human review. Interpolation is a separate display derivative.
Full playback establishes
context; a departure, cash handling, clothes or screen side alone cannot establish a role.</p>
<video controls preload="metadata" src="review.mp4"></video>
<p><a href="oriented-source.mp4">Clean full-scene playback</a>
 · <a href="review-questions.json">Exact review queue</a>
 · <a href="annotation.json">Visual annotations</a>
 · <a href="tracks.json">Track manifest</a></p>ROWS"""
    (output / "review.html").write_text(
        page.replace("CLIP", manifest.clip_id).replace("ROWS", "".join(rows))
    )


def prepare_clip(
    record,
    template,
    output,
    detector,
    tracker,
    *,
    cadence_sec=0.2,
    regression_only=False,
    extra_frame_ids=(),
):
    verify_source(record)
    if output.exists():
        raise FileExistsError("Proposal output already exists; choose a new run/version")
    started = time.monotonic()
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    original = Annotation.model_validate_json(template.read_bytes())
    if original.source_sha256 != record["recording_group"]:
        raise ValueError("Template source mismatch")
    shutil.copyfile(template, output / "annotation-before.json")
    registry = decode_video(
        record["source"], output / "source-samples", deadline=time.monotonic() + 1800
    )
    if not math.isclose(registry.duration, original.duration_sec, abs_tol=0.05):
        raise ValueError("Template duration mismatch")
    legacy_duration = original.duration_sec
    # Old empty templates used rounded probe durations. Migrate to the exact
    # decoded end; never loosen fact bounds or silently retime existing facts.
    original.duration_sec = registry.duration
    original = Annotation.model_validate(original.model_dump())
    metadata = probe_video(record["source"])
    selected = detection_schedule(registry.frames, cadence_sec)
    builder = SegmentBuilder(cadence_sec)
    with open_video(record["source"]) as container:
        stream = container.streams.video[0]
        time_base = str(stream.time_base)
        stream.codec_context.thread_count = 1
        for i, frame in enumerate(container.decode(stream)):
            if frame.pts != registry.frames[i].source_pts:
                raise ValueError("Detector source association changed")
            if i not in selected:
                continue
            image = oriented(frame, stream, registry.rotation)
            boxes = detector.detect(image)
            ref = registry.frames[i]
            builder.update(
                ref.frame_id, ref.timestamp_sec, tracker.update(boxes, ref.timestamp_sec)
            )
    original.frames.update({f.frame_id: f.timestamp_sec for f in registry.frames})
    write_json(output / "annotation.json", original.model_dump(mode="json"))
    swapped = metadata["rotation"] % 180 != 0
    m = TrackManifest(
        clip_id=record["clip_id"],
        source_sha256=registry.source_sha256,
        annotation_file="annotation.json",
        annotation_sha256=sha256(output / "annotation.json"),
        duration_sec=registry.duration,
        source_width=metadata["width"],
        source_height=metadata["height"],
        oriented_width=metadata["height"] if swapped else metadata["width"],
        oriented_height=metadata["width"] if swapped else metadata["height"],
        rotation=registry.rotation,
        time_base=time_base,
        frames=[asdict(f) for f in registry.frames],
        detection_frame_ids=[f.frame_id for f in registry.frames if f.ordinal in selected],
        cadence_sec=cadence_sec,
        segments=builder.segments,
        joins=builder.joins,
        gaps=builder.gaps,
        recording_group=record["recording_group"],
        regression_only=regression_only,
        exclusion_reasons=["unreviewed", "session_split_unfrozen"]
        + (["regression_only"] if regression_only else []),
        provenance=dict(
            detector=detector.provenance,
            tracker="roboflow/trackers ByteTrack",
            template_sha256=sha256(template),
            legacy_template_duration_sec=legacy_duration,
            source_mapping="forte.video.VideoRegistry",
            undecodable_ranges=[],
            sampled_out_frames=len(registry.frames) - len(selected),
            decoded_frames=len(registry.frames),
            automatic_interpolation_approved=False,
        ),
    )
    validate_pair(m, original)
    build_packet(record["source"], output, m, extra_frame_ids)
    verify_source(record)
    questions = [
        dict(
            kind="identity_join",
            join_id=j.id,
            segments=[j.from_segment, j.to_segment],
            question=(
                "Same visible person across these segments? Check full playback before joining."
            ),
            status="pending",
        )
        for j in m.joins
    ]
    questions.extend(
        [
            dict(
                kind="work_areas",
                status="pending",
                question=(
                    "Outline visible service/work areas on exact full-scene source frames; "
                    "flag uncertain boundaries."
                ),
            ),
            dict(
                kind="roles_actions",
                status="pending",
                question="Bind roles/actions to outlined segments, area and supported intervals. "
                "Use separated source frames and surrounding service context; preserve unknowns.",
            ),
        ]
    )
    write_json(output / "review-questions.json", questions)
    m.provenance["runtime_sec"] = time.monotonic() - started
    m.provenance["review_media"] = {
        name: sha256(output / name)
        for name in (
            "review.mp4",
            "oriented-source.mp4",
            "review-assets.json",
            "cvat.xml",
            "cvat-source-map.json",
        )
    }
    write_json(output / "tracks.json", m.model_dump(mode="json"))
    write_json(
        output / "complete.json",
        dict(
            source_sha256=m.source_sha256,
            manifest_sha256=sha256(output / "tracks.json"),
            runtime_sec=m.provenance["runtime_sec"],
        ),
    )
    return m
