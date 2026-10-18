"""Frozen, source-bound whole-recording observations and bounded local evidence tools.

This module does not establish legal truth or human review. Every model assertion
retains its source pointers, sampled visibility and unreviewed origin.
"""

import base64
import fcntl
import hashlib
import io
import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from PIL import Image
from pydantic import Field

from forte.contracts import StrictModel
from forte.jobs import atomic_json
from forte.video import VideoRegistry, jpeg_bytes, make_windows, nearest, open_video, oriented


def private_directory(path: Path) -> Path:
    path = Path(path).resolve()
    repository = Path(__file__).resolve().parents[2]
    if path.is_relative_to(repository):
        raise ValueError("Private inference artifacts must remain outside the Git checkout")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def write_private(path: Path, payload):
    atomic_json(path, payload)
    path.chmod(0o600)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_frame_table(registry: VideoRegistry, deadline: float) -> dict:
    """Recover each frame's actual time base, checking the existing registry.

    Normalized seconds are derived from presentation timestamps, never frame rate.
    The final-frame duration estimate is explicitly separate from frame timing.
    """
    if sha256(registry.path) != registry.source_sha256:
        raise ValueError("Source changed after decoding")
    rows = []
    with open_video(registry.path) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        origin = None
        for ordinal, frame in enumerate(container.decode(stream)):
            if time.monotonic() >= deadline:
                raise TimeoutError("Source-table deadline exceeded")
            if ordinal >= len(registry.frames):
                raise ValueError("Source frame count changed")
            ref = registry.frames[ordinal]
            if frame.pts is None or frame.pts != ref.source_pts or frame.is_corrupt:
                raise ValueError("Source PTS association changed")
            absolute = frame.pts * frame.time_base
            if origin is None:
                origin = absolute
            if abs(float(absolute - origin) - ref.timestamp_sec) > 1e-8:
                raise ValueError("Source time base association changed")
            angle = frame.rotation or registry.rotation
            if angle % 90:
                raise ValueError("Unsupported orientation")
            width, height = frame.width, frame.height
            oriented_size = [height, width] if angle % 180 else [width, height]
            rows.append(
                {
                    "frame_id": ref.frame_id,
                    "ordinal": ordinal,
                    "source_pts": frame.pts,
                    "time_base": str(frame.time_base),
                    "timestamp_sec": ref.timestamp_sec,
                    "absolute_presentation_time": str(absolute),
                    "source_size": [width, height],
                    "oriented_size": oriented_size,
                    "rotation_degrees": angle,
                }
            )
    if len(rows) != len(registry.frames):
        raise ValueError("Source frame count changed")
    return {
        "schema_version": "forte.source-frames/1",
        "source_sha256": registry.source_sha256,
        "duration_sec": registry.duration,
        "duration_is_decoded_envelope": True,
        "frames": rows,
    }


ShortNote = Annotated[str, Field(min_length=1, max_length=120)]


class Observation(StrictModel):
    kind: Literal["action", "interaction", "role", "object", "context"]
    value: str = Field(min_length=1, max_length=160)
    start_frame_id: str
    end_frame_id: str
    decisive_frame_id: str
    actor_ids: list[str] = Field(max_length=4)
    recipient_ids: list[str] = Field(max_length=4)
    evidence_frame_ids: list[str] = Field(min_length=1, max_length=3)
    visibility: Literal["visible_samples", "partly_occluded", "unclear"]
    contradictory_frame_ids: list[str] = Field(default_factory=list, max_length=3)
    uncertainty: list[ShortNote] = Field(max_length=2)
    continues_before_window: bool
    continues_after_window: bool


class Reinspection(StrictModel):
    start_frame_id: str
    end_frame_id: str
    actor_ids: list[str] = Field(max_length=2)
    question: str = Field(min_length=1, max_length=160)


class ScanAnswer(StrictModel):
    observations: list[Observation] = Field(max_length=2)
    visibility: Literal["visible_samples", "partly_occluded", "unclear"]
    unresolved_questions: list[ShortNote] = Field(max_length=2)
    reinspection_requests: list[Reinspection] = Field(max_length=1)
    capacity_limited: bool


def validate_answer(value, frames, participants, frame_boxes) -> ScanAnswer:
    answer = ScanAnswer.model_validate(value)
    by_id = {f.frame_id: f for f in frames}
    actors = {p["participant_id"] for p in participants}
    for item in [*answer.observations, *answer.reinspection_requests]:
        references = {item.start_frame_id, item.end_frame_id}
        if isinstance(item, Observation):
            references |= {
                item.decisive_frame_id,
                *item.evidence_frame_ids,
                *item.contradictory_frame_ids,
            }
            actor_ids = {*item.actor_ids, *item.recipient_ids}
        else:
            actor_ids = set(item.actor_ids)
        if not references <= by_id.keys():
            raise ValueError("Model referenced an unsupplied source frame")
        if not actor_ids <= actors:
            raise ValueError("Model referenced an unsupplied participant")
        start, end = (
            by_id[item.start_frame_id].timestamp_sec,
            by_id[item.end_frame_id].timestamp_sec,
        )
        if start > end:
            raise ValueError("Model reversed the source interval")
        if isinstance(item, Observation):
            if any(not start <= by_id[f].timestamp_sec <= end for f in references):
                raise ValueError("Evidence outside observation source envelope")
            if item.decisive_frame_id not in item.evidence_frame_ids:
                raise ValueError("Decisive source frame lacks evidence")
            # A supplied participant cannot be attached to unrelated source frames.
            for actor in actor_ids:
                if not any(actor in frame_boxes.get(f, {}) for f in item.evidence_frame_ids):
                    raise ValueError("Participant lacks membership in supplied evidence")
    return answer


def participant_role_history(person, observations):
    """Keep source-bound role proposals separate for each recording-local person.

    Only already validated observations enter here. Matching observation IDs
    enrich compatible records; different claims/origins remain independent.
    A historical interval never establishes a current or permanent role.
    """
    history = [dict(row) for row in person.get("role_hypotheses", [])]
    for observation in observations:
        if (
            observation["kind"] != "role"
            or person["participant_id"] not in observation["actor_ids"]
        ):
            continue
        role = {
            key: observation[key]
            for key in (
                "observation_id",
                "value",
                "start_sec",
                "end_sec",
                "evidence_frame_ids",
                "review_status",
                "origin",
                "uncertainty",
                "visibility",
                "source_sha256",
                "phase",
                "localization",
                "start_frame_id",
                "end_frame_id",
                "decisive_frame_id",
            )
            if key in observation
        }
        for index, previous in enumerate(history):
            if previous.get("observation_id") != role["observation_id"]:
                continue
            if all(previous[key] == role[key] for key in previous.keys() & role.keys()):
                history[index] = {**previous, **role}
                break
        else:
            history.append(role)
    return history


def compact_participants(participants, *, interval=None):
    """Bound prompt history; full records remain recoverable in the registry.

    Tokenizers split long numeric arrays very finely. Per-frame galleries,
    unbounded conflict lists and float precision must not consume the visual
    context budget. These summaries never replace the canonical source records.
    """

    def compact(item, depth=0):
        if isinstance(item, float):
            return round(item, 3)
        if isinstance(item, str):
            return item[:240]
        if isinstance(item, list):
            return [compact(value, depth + 1) for value in item[:4]]
        if isinstance(item, dict):
            return {
                key: compact(value, depth + 1)
                for key, value in item.items()
                if key not in {"embedding", "gallery", "appearance_gallery", "observations"}
                and depth < 4
            }
        return item

    result = []
    for person in participants:
        value = {
            k: compact(person[k])
            for k in (
                "participant_id",
                "identity_status",
                "conflicts",
                "visibility_gaps",
                "role_hypotheses",
            )
            if k in person
        }
        value["registry_ref"] = "participant_registry:" + person["participant_id"]
        value["history_counts"] = {
            key: len(person.get(key, []))
            for key in ("conflicts", "visibility_gaps", "role_hypotheses", "track_segments")
        }
        value["history_is_bounded_summary"] = True
        roles = person.get("role_hypotheses", [])

        def role_priority(index, roles=roles):
            row = roles[index]
            start, end = row.get("start_sec"), row.get("end_sec")
            timed = (
                not isinstance(start, bool)
                and isinstance(start, (int, float))
                and not isinstance(end, bool)
                and isinstance(end, (int, float))
                and math.isfinite(start)
                and math.isfinite(end)
                and start <= end
            )
            overlaps = (
                timed and interval is not None and max(start, interval[0]) <= min(end, interval[1])
            )
            return overlaps, end if timed else -math.inf, index

        chosen = sorted(range(len(roles)), key=role_priority, reverse=True)[:4]
        value["role_hypotheses"] = [
            {
                **compact(roles[index]),
                **{
                    key: roles[index][key]
                    for key in ("start_sec", "end_sec")
                    if key in roles[index]
                },
            }
            for index in chosen
        ]
        value["role_history_semantics"] = (
            "source_evidence_intervals_only_not_current_or_permanent_role_approval"
        )
        segments = []
        for segment in person.get("track_segments", [])[:4]:
            if isinstance(segment, str):
                segments.append({"segment_id": segment})
                continue
            observations = segment.get("observations", [])
            segments.append(
                {
                    "segment_id": segment["segment_id"],
                    "start_frame_id": observations[0]["frame_id"] if observations else None,
                    "end_frame_id": observations[-1]["frame_id"] if observations else None,
                    "review_status": segment.get("review_status", "unreviewed"),
                }
            )
        value["track_segments"] = segments
        result.append(value)
    return result


@dataclass
class ScanBounds:
    deadline: float
    max_calls: int = 32
    max_tokens: int = 80_000
    max_reinspections: int = 4
    calls: int = 0
    tokens: int = 0
    reinspections: int = 0
    receipts: list = field(default_factory=list)

    def check(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Analysis deadline exhausted")
        if self.calls >= self.max_calls or self.tokens >= self.max_tokens:
            raise TimeoutError("Analysis inference budget exhausted")


@dataclass(frozen=True)
class ViewRef:
    frame_id: str
    timestamp_sec: float


class EvidenceTools:
    """Application-owned tools; intervals/IDs/crops never escape this source."""

    def __init__(self, registry, participants, output, deadline, table=None):
        self.registry = registry
        self.participants = participants
        self.output = private_directory(output)
        self.deadline = deadline
        self.table = table or source_frame_table(registry, deadline)
        self.rows = {row["frame_id"]: row for row in self.table["frames"]}
        self.by_id = {f.frame_id: f for f in registry.frames}
        self.views = []
        self.payloads = {}
        self.observations = []
        self.tool_receipts = []

    def get_frames(self, ids: list[str]):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Evidence tool deadline exhausted")
        if not 0 < len(ids) <= 16 or len(ids) != len(set(ids)) or not set(ids) <= self.by_id.keys():
            raise ValueError("Invalid bounded source-frame request")
        missing = [fid for fid in ids if fid not in self.registry.cached]
        if missing:
            ordered = sorted(missing, key=lambda fid: self.by_id[fid].timestamp_sec)
            evidence = self.registry.evidence(ordered)
            for fid, ev in zip(ordered, evidence, strict=True):
                target = self.output / (fid + ".jpg")
                # Keep full decoded evidence separately from model resize/crops.
                target.write_bytes(base64.b64decode(ev.image_base64))
                target.chmod(0o600)
                self.registry.cached[fid] = target
        return sorted((self.by_id[fid] for fid in ids), key=lambda f: f.timestamp_sec)

    def original_jpegs(self, ids):
        """Re-decode original pixels, without sampling resize or annotation overlays."""
        refs = self.get_frames(ids)
        if sha256(self.registry.path) != self.registry.source_sha256:
            raise ValueError("Source changed after decoding")
        selected = {ref.ordinal: ref for ref in refs}
        result = {}
        with open_video(self.registry.path) as container:
            stream = container.streams.video[0]
            stream.codec_context.thread_count = 1
            for ordinal, frame in enumerate(container.decode(stream)):
                if time.monotonic() >= self.deadline:
                    raise TimeoutError("Evidence extraction deadline exhausted")
                if ordinal in selected:
                    ref = selected[ordinal]
                    if frame.pts != ref.source_pts or frame.is_corrupt:
                        raise ValueError("Original evidence PTS changed")
                    image = oriented(frame, stream, self.registry.rotation)
                    result[ref.frame_id] = jpeg_bytes(image, image.width * image.height)
                if ordinal >= max(selected):
                    break
        if set(result) != set(ids):
            raise ValueError("Incomplete original evidence extraction")
        return result

    def get_clip(self, start: float, end: float, fps: float = 1, max_frames: int = 16):
        if not (0 <= start < end <= self.registry.duration and 0 < fps <= 8):
            raise ValueError("Invalid source interval or cadence")
        if not 1 <= max_frames <= 16:
            raise ValueError("Invalid frame budget")
        candidates = [f for f in self.registry.frames if start <= f.timestamp_sec < end]
        # Prefer actually tracked source frames without interpolating geometry.
        # Tracking includes the legacy half-second cache plus its denser cadence.
        tracked = [f for f in candidates if f.frame_id in self.participants.get("frame_boxes", {})]
        if tracked:
            candidates = tracked
        if not candidates:
            raise ValueError("No source frames in requested interval")
        count = min(max_frames, max(1, math.ceil((end - start) * fps)))
        if count == 1:
            targets = [start]
        else:
            targets = [start + (end - start) * i / (count - 1) for i in range(count)]
        ids = {nearest(candidates, t).frame_id for t in targets}
        selected_times = sorted(self.by_id[fid].timestamp_sec for fid in ids)
        gaps = [b - a for a, b in zip(selected_times, selected_times[1:], strict=False)]
        self.tool_receipts.append(
            {
                "tool": "get_clip",
                "start_sec": start,
                "end_sec": end,
                "requested_fps": fps,
                "frame_ids": sorted(ids),
                "max_sample_gap_sec": max(gaps, default=end - start),
            }
        )
        return self.get_frames(sorted(ids))

    def get_participant_history(self, participant_id, start, end):
        if not 0 <= start <= end <= self.registry.duration:
            raise ValueError("Invalid participant-history interval")
        participant = next(
            (
                p
                for p in self.participants.get("participants", [])
                if p["participant_id"] == participant_id
            ),
            None,
        )
        if participant is None:
            raise ValueError("Unknown participant")
        return {
            "participant": participant,
            "observations": [
                o
                for o in self.observations
                if participant_id in [*o["actor_ids"], *o["recipient_ids"]]
                and max(start, o["start_sec"]) <= min(end, o["end_sec"])
            ],
        }

    def get_timeline(self, start, end):
        if not 0 <= start <= end <= self.registry.duration:
            raise ValueError("Invalid timeline interval")
        return [
            o for o in self.observations if max(start, o["start_sec"]) <= min(end, o["end_sec"])
        ]

    def views_for(self, frames, pixels, crops=False):
        refs, metadata = [], []
        for frame in frames:
            with Image.open(self.registry.cached[frame.frame_id]) as image:
                raw = jpeg_bytes(image, pixels)
            with Image.open(io.BytesIO(raw)) as view:
                size = view.size
            row = self.rows[frame.frame_id]
            width, height = row["oriented_size"]
            view_id = frame.frame_id
            self.payloads[view_id] = raw
            refs.append(ViewRef(view_id, frame.timestamp_sec))
            metadata.append(
                {
                    "view_id": view_id,
                    "source_frame_id": frame.frame_id,
                    "kind": "scene",
                    "source_rect": [0, 0, width, height],
                    "source_to_view": [size[0] / width, size[1] / height, 0, 0],
                    "size": list(size),
                    "rotation_degrees": row["rotation_degrees"],
                }
            )
        if crops:
            # Re-extract source pixels for precise oriented crop geometry. Cached
            # scene JPEGs may already have been resized by the legacy decoder.
            chosen = frames[:: max(1, len(frames) // 4)][:4]
            source_images = self.original_jpegs([f.frame_id for f in chosen])
            for frame in chosen:
                boxes = self.participants.get("frame_boxes", {}).get(frame.frame_id, {})
                for actor, box in sorted(boxes.items()):
                    if len(refs) >= 16:
                        break
                    with Image.open(io.BytesIO(source_images[frame.frame_id])) as image:
                        width, height = self.rows[frame.frame_id]["oriented_size"]
                        x1, y1, x2, y2 = box
                        space = self.participants.get(
                            "box_coordinate_space", "oriented_pixels_xyxy"
                        )
                        if space == "oriented_normalized_xyxy":
                            x1, y1, x2, y2 = x1 * width, y1 * height, x2 * width, y2 * height
                        elif space != "oriented_pixels_xyxy":
                            raise ValueError("Unknown participant coordinate space")
                        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                            raise ValueError("Participant crop outside oriented source")
                        x1, y1, x2, y2 = (
                            math.floor(x1),
                            math.floor(y1),
                            math.ceil(x2),
                            math.ceil(y2),
                        )
                        crop = image.crop((x1, y1, x2, y2))
                        raw = jpeg_bytes(crop, pixels)
                    with Image.open(io.BytesIO(raw)) as view:
                        size = view.size
                    view_id = frame.frame_id + "/participant/" + actor
                    self.payloads[view_id] = raw
                    refs.append(ViewRef(view_id, frame.timestamp_sec))
                    sx, sy = size[0] / (x2 - x1), size[1] / (y2 - y1)
                    metadata.append(
                        {
                            "view_id": view_id,
                            "source_frame_id": frame.frame_id,
                            "kind": "participant_crop",
                            "participant_id": actor,
                            "source_rect": [x1, y1, x2, y2],
                            "source_to_view": [sx, sy, -x1 * sx, -y1 * sy],
                            "size": list(size),
                            "rotation_degrees": self.rows[frame.frame_id]["rotation_degrees"],
                            "geometry_review_status": "unreviewed",
                        }
                    )
        for item in metadata:
            item["jpeg_sha256"] = hashlib.sha256(self.payloads[item["view_id"]]).hexdigest()
        # Keep each full scene beside its same-source crops in temporal order.
        # Stable sorting retains scene-before-crop order at identical source PTS
        # and moves view metadata with its payload reference.
        order = sorted(range(len(refs)), key=lambda index: refs[index].timestamp_sec)
        refs = [refs[index] for index in order]
        metadata = [metadata[index] for index in order]
        self.views.extend(metadata)
        return refs, metadata

    def image_bytes(self, ref, max_pixels):
        return self.payloads[ref.frame_id]


def merge_observations(observations):
    """Conservative deduplication: actor/action plus overlap and shared evidence.

    No stitching across gaps, no automatic same-person or same-role inference.
    Raw observations and their immutable IDs are always retained independently.
    """
    events = []
    for obs in sorted(observations, key=lambda o: (o["start_sec"], o["end_sec"])):
        matching = next(
            (
                e
                for e in events
                if all(
                    e[key] == obs[key]
                    for key in ("kind", "value", "actor_ids", "recipient_ids", "visibility")
                )
                and max(e["start_sec"], obs["start_sec"]) <= min(e["end_sec"], obs["end_sec"])
                and set(e["evidence_frame_ids"]) & set(obs["evidence_frame_ids"])
            ),
            None,
        )
        if matching is None:
            events.append(
                {
                    **obs,
                    "event_id": f"event-{len(events):05d}",
                    "observation_ids": [obs["observation_id"]],
                }
            )
        else:
            matching["observation_ids"].append(obs["observation_id"])
            if obs["end_sec"] > matching["end_sec"]:
                matching["end_sec"] = obs["end_sec"]
                matching["end_frame_id"] = obs["end_frame_id"]
                matching["continues_after_window"] = obs["continues_after_window"]
            matching["evidence_frame_ids"] = sorted(
                set(matching["evidence_frame_ids"]) | set(obs["evidence_frame_ids"])
            )
            matching["contradictory_frame_ids"] = sorted(
                set(matching.get("contradictory_frame_ids", []))
                | set(obs.get("contradictory_frame_ids", []))
            )
            matching["uncertainty"] = list(
                dict.fromkeys([*matching["uncertainty"], *obs["uncertainty"]])
            )
    return events


def uncovered(intervals, duration):
    cursor, gaps = 0.0, []
    for start, end in sorted(intervals):
        if start > cursor:
            gaps.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < duration:
        gaps.append([cursor, duration])
    return gaps


def scan_recording(registry, participants, backend, output, deadline, bounds=None, table=None):
    """Actual loopback visual calls; mocks belong exclusively to synthetic tests."""
    output = private_directory(output)
    tools = EvidenceTools(registry, participants, output / "evidence-tools", deadline, table)
    bounds = bounds or ScanBounds(deadline)
    participants_list = participants.get("participants", [])
    boxes = participants.get("frame_boxes", {})
    windows, pending, questions, observed_ranges = [], [], [], []
    status = "complete_schedule"

    def invoke(phase, start, end, frames, crops=False, question=None):
        bounds.check()
        refs, views = tools.views_for(frames, 393216 if crops else 196608, crops=crops)
        ids = [f.frame_id for f in frames]
        active_ids = {actor for fid in ids for actor in boxes.get(fid, {})}
        supplied = [p for p in participants_list if p["participant_id"] in active_ids]
        # Embeddings/gallery never enter the VLM prompt. Geometry and role evidence
        # are provisional; a tracker association cannot establish a role.
        participant_context = compact_participants(
            [
                {**person, "role_hypotheses": participant_role_history(person, tools.observations)}
                for person in supplied
            ],
            interval=(start, end),
        )
        prior = [
            {
                k: o[k]
                for k in (
                    "observation_id",
                    "start_sec",
                    "end_sec",
                    "actor_ids",
                    "recipient_ids",
                    "kind",
                    "value",
                    "evidence_frame_ids",
                    "uncertainty",
                )
            }
            for o in tools.observations[-8:]
        ]
        for item in prior:
            item["value"] = item["value"][:160]
            item["uncertainty"] = [text[:160] for text in item["uncertainty"][:2]]
            item["evidence_frame_ids"] = item["evidence_frame_ids"][:3]
        context = {
            "phase": phase,
            "window_sec": [start, end],
            "question": question,
            "source_frames": [
                {"frame_id": f.frame_id, "timestamp_sec": f.timestamp_sec} for f in frames
            ],
            # Full hashes and affine transforms are retained in view-transforms.json.
            # The VLM needs source/crop ownership and location, not their long hashes.
            "views": [
                {
                    key: view[key]
                    for key in (
                        "view_id",
                        "source_frame_id",
                        "kind",
                        "participant_id",
                        "source_rect",
                    )
                    if key in view
                }
                for view in views
            ],
            "participants": participant_context,
            "frame_boxes": {
                fid: {
                    actor: [
                        round(coord * tools.rows[fid]["oriented_size"][index % 2])
                        if participants.get("box_coordinate_space") == "oriented_normalized_xyxy"
                        else round(coord)
                        for index, coord in enumerate(box)
                    ]
                    for actor, box in boxes.get(fid, {}).items()
                }
                for fid in ids
            },
            "box_coordinate_space": "oriented_pixels_xyxy_rounded_for_prompt_only",
            "prior_observations": prior,
            "observation_store": {
                "reference": "scan/observations.json",
                "total_observations": len(tools.observations),
                "preview_is_bounded": True,
            },
        }
        instruction = (
            "Observe visible actions, interactions, operational context and their sequence. "
            "Do not decide legal violations or invent a required missing action. Sparse samples "
            "cannot establish absence. Preserve uncertainty about boundaries, gaps, mirrors, "
            "roles and unresolved objects. Tracker IDs are hypotheses, not identity truth. "
            "A reflection is not another physical actor. Clothing, proximity or image side "
            "cannot establish cashier/customer roles. State a role only with repeated visible "
            "operational activity and evidence, and restrict it to the supplied interval. "
            "Use only source frame IDs supplied in source_frames for all references, even "
            "when inspecting crops. Use only supplied participant IDs; use empty actor lists "
            "when ownership is unresolved. Preserve earlier observation IDs and evidence in "
            "context; disagreements become uncertainty, never silently override corrections. "
            "Each window observes actions and context; reinspect only the specified ambiguity. "
            "Preserve counterevidence in contradictory_frame_ids. Return the exact "
            "JSON schema, concisely: at most two observations, each under 25 words; "
            "at most two uncertainty notes under 12 words and one short reinspection request. "
            "Set capacity_limited=true if this pass omits requested observations "
            "because of the output cap; preserve unresolved candidates in short questions. "
            "Use empty lists when there is nothing supported to report. JSON only; no narrative. "
            "JSON schema. Context: " + json.dumps(context, ensure_ascii=False)
        )
        schema = ScanAnswer.model_json_schema()
        for name in ("Observation", "Reinspection"):
            props = schema["$defs"][name]["properties"]
            for key in ("start_frame_id", "end_frame_id", "decisive_frame_id"):
                if key in props:
                    props[key]["enum"] = ids
            for evidence_key in ("evidence_frame_ids", "contradictory_frame_ids"):
                if evidence_key in props:
                    props[evidence_key]["items"]["enum"] = ids
            for key in ("actor_ids", "recipient_ids"):
                if key in props:
                    if supplied:
                        props[key]["items"]["enum"] = [p["participant_id"] for p in supplied]
                    else:
                        props[key]["maxItems"] = 0
        began = time.monotonic()
        receipt = {
            "phase": phase,
            "start_sec": start,
            "end_sec": end,
            "source_frame_ids": ids,
            "images": len(refs),
        }
        bounds.calls += 1
        try:
            value = backend.request(
                tools, refs, instruction, schema, 393216 if crops else 196608, 768
            )
            write_private(output / f"reply-{bounds.calls:03d}.json", value)
            answer = validate_answer(value, frames, supplied, boxes)
            receipt["visibility"] = answer.visibility
            receipt["capacity_limited"] = answer.capacity_limited
        except Exception as exc:
            receipt["error"] = type(exc).__name__
            if isinstance(exc, httpx.TimeoutException):
                raise TimeoutError("Local visual request exhausted its time budget") from exc
            raise
        finally:
            usage = getattr(backend, "last_usage", {})
            receipt["seconds"] = time.monotonic() - began
            receipt["usage"] = usage
            receipt["finish_reason"] = getattr(backend, "last_finish_reason", None)
            bounds.tokens += usage.get(
                "total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
            )
            bounds.receipts.append(receipt)
            write_private(output / "call-receipts.json", bounds.receipts)
        observed_ranges.append([start, end])
        times = {f.frame_id: f.timestamp_sec for f in frames}
        for item in answer.observations:
            obs = item.model_dump(mode="json")
            obs.update(
                observation_id=f"obs-{len(tools.observations):05d}",
                origin="model",
                review_status="unreviewed",
                phase=phase,
                source_sha256=registry.source_sha256,
                start_sec=times[item.start_frame_id],
                end_sec=times[item.end_frame_id],
                decisive_sec=times[item.decisive_frame_id],
                localization="sampled_source_envelope_not_exact_action_boundaries",
            )
            tools.observations.append(obs)
        for request in answer.reinspection_requests:
            pending.append(
                {
                    **request.model_dump(mode="json"),
                    "start_sec": times[request.start_frame_id],
                    "end_sec": times[request.end_frame_id],
                }
            )
        questions.extend(answer.unresolved_questions)
        if answer.capacity_limited:
            questions.append(
                "A visual pass reached its observation output cap; further facts remain unresolved."
            )
            if phase == "window" and not answer.reinspection_requests:
                center = (start + end) / 2
                pending.append(
                    {
                        "start_sec": max(start, center - 2),
                        "end_sec": min(end, center + 2),
                        "question": "Inspect visible actions omitted by the earlier output cap.",
                    }
                )
        windows.append(receipt)
        write_private(output / "observations.json", tools.observations)
        # A fully validated answer remains useful even when its call crosses the
        # aggregate budget. Persist it before stopping subsequent work.
        if bounds.tokens > bounds.max_tokens or time.monotonic() >= deadline:
            raise TimeoutError("Analysis inference budget exceeded")
        return answer

    try:
        for start, end in make_windows(registry.duration, 16, 12):
            invoke("window", start, end, tools.get_clip(start, end, fps=1, max_frames=16))
        seen = []
        while pending and bounds.reinspections < bounds.max_reinspections:
            request = pending.pop(0)
            start, end = request["start_sec"], request["end_sec"]
            start = max(0, start - 0.5)
            end = min(registry.duration, end + 0.5, start + 8)
            if any(max(start, a) < min(end, b) or (start, end) == (a, b) for a, b in seen):
                questions.append(
                    "A repeated visual dependency remains unresolved after its bounded recheck."
                )
                continue
            seen.append((start, end))
            bounds.reinspections += 1
            invoke(
                "reinspect",
                start,
                end,
                tools.get_clip(start, end, fps=2, max_frames=16),
                crops=True,
                question=request["question"],
            )
    except TimeoutError:
        status = "budget_exhausted"
    except Exception:
        # Valid partial observations survive a failed model call, but never become
        # a clean negative. The parent pipeline receives an explicit failure.
        status = "failed_pass"
        if not windows:
            raise
        questions.append("A later visual pass failed; its unvalidated answer was not accepted.")
    finally:
        write_private(output / "view-transforms.json", tools.views)
        write_private(output / "tool-receipts.json", tools.tool_receipts)
        write_private(output / "observations.json", tools.observations)
    coarse = [w for w in windows if w["phase"] == "window"]
    reviewed = [[w["start_sec"], w["end_sec"]] for w in coarse]
    uncertain = [
        [w["start_sec"], w["end_sec"]]
        for w in coarse
        if w.get("visibility") != "visible_samples" or w.get("capacity_limited")
    ]
    limited = [[w["start_sec"], w["end_sec"]] for w in windows if w.get("capacity_limited")]
    if limited and status == "complete_schedule":
        status = "output_limited"
    role_conflicts = []
    for person in participants_list:
        roles = [
            o
            for o in tools.observations
            if o["kind"] == "role" and person["participant_id"] in o["actor_ids"]
        ]
        person["role_hypotheses"] = participant_role_history(person, tools.observations)
        for index, role in enumerate(roles):
            for other in roles[index + 1 :]:
                if role["value"] != other["value"] and max(
                    role["start_sec"], other["start_sec"]
                ) <= min(role["end_sec"], other["end_sec"]):
                    role_conflicts.append(
                        {
                            "participant_id": person["participant_id"],
                            "observation_ids": [role["observation_id"], other["observation_id"]],
                            "status": "unresolved",
                        }
                    )
    report = {
        "schema_version": "forte.timeline/1",
        "status": status,
        "source_sha256": registry.source_sha256,
        "duration_sec": registry.duration,
        "observations": tools.observations,
        "events": merge_observations(tools.observations),
        "participants": participants_list,
        "role_conflicts": role_conflicts,
        "coverage": {
            "scheduled_intervals": make_windows(registry.duration, 16, 12),
            "examined_intervals": reviewed,
            "unexamined_intervals": uncovered(reviewed, registry.duration),
            "unclear_intervals": uncertain,
            "continuous_visibility_validated": False,
            "sampling_does_not_establish_absence": True,
            "pending_reinspections": len(pending),
            "output_capacity_limited_intervals": limited,
            "windows": windows,
        },
        "unresolved_questions": list(dict.fromkeys(questions)),
        "metrics": {
            "calls": bounds.calls,
            "tokens": bounds.tokens,
            "reinspections": bounds.reinspections,
            "receipts": bounds.receipts,
        },
        "review_status": "unreviewed",
        "weights_frozen": True,
    }
    write_private(output / "timeline.json", report)
    return report


def append_correction(directory: Path, result: dict, correction: dict) -> Path:
    """Append an immutable human sidecar; never rewrite model output or old review.

    The supplied result must be the complete original result, not a mutable view.
    Corrections remain separate from detector/role/legal approval scopes.
    """
    directory = private_directory(directory)
    required = {"reviewer", "scope", "target_id", "change", "source_sha256", "parent_revision"}
    if set(correction) != required or not correction["reviewer"]:
        raise ValueError("Correction requires explicit reviewer, scope and lineage")
    if correction["scope"] not in {"visual", "identity", "geometry", "role", "legal"}:
        raise ValueError("Unknown independent review scope")
    if correction["source_sha256"] != result["source_sha256"]:
        raise ValueError("Correction belongs to another recording")
    timeline = result.get("timeline", result)
    targets = {o["observation_id"] for o in timeline.get("observations", [])}
    targets |= {e["event_id"] for e in timeline.get("events", [])}
    targets |= {p["participant_id"] for p in timeline.get("participants", [])}
    targets |= {a["assessment_id"] for a in result.get("legal", {}).get("assessments", [])}
    if correction["target_id"] not in targets:
        raise ValueError("Correction target not present in original result")
    digest = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()
    revision = {
        **correction,
        "schema_version": "forte.correction/1",
        "base_result_sha256": digest,
        "revision_id": uuid4().hex,
        "created_unix_sec": time.time(),
        "origin": "human",
        "other_scopes_approved": False,
    }
    lock_fd = os.open(directory / ".revision.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        parent = correction["parent_revision"]
        revisions = [p for p in directory.glob("*.json") if p.is_file() and not p.is_symlink()]
        histories = {p.name: json.loads(p.read_text()) for p in revisions}
        parents = {v["parent_revision"] for v in histories.values()}
        heads = set(histories) - parents
        if histories:
            if len(heads) != 1 or parent not in heads:
                raise ValueError("Stale correction parent; reload the latest revision")
            prior = histories[parent]
            if prior["source_sha256"] != result["source_sha256"]:
                raise ValueError("Correction parent belongs to another source")
            if prior["base_result_sha256"] != digest:
                raise ValueError("Correction parent belongs to another immutable result")
        elif parent is not None:
            raise ValueError("Correction parent is unavailable")
        path = directory / (revision["revision_id"] + ".json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(revision, out, ensure_ascii=False, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        return path
