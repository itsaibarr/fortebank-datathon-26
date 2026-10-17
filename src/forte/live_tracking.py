"""Automatic upload proposals using the producer detector/tracker, without truth.

No allowlist is consulted here: admission accepts genuinely new MOV uploads.
Development evaluation/training eligibility remains in the release reader.
"""

import json
import time
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from forte.person_proposals import LocalByteTrack, YoloxONNX, detection_schedule
from forte.tracking import SegmentBuilder, TrackManifest
from forte.video import open_video, oriented, probe_video


def detector_config():
    asset = files("forte").joinpath("data/person-tracking.json")
    if asset.is_file():
        return json.loads(asset.read_text())
    # Source checkout development; deployed wheels carry the same pinned asset.
    return json.loads(
        (Path(__file__).resolve().parents[2] / "configs/person-tracking.json").read_text()
    )


def automatic_tracks(registry, weights, deadline, *, detector=None, tracker=None):
    cadence = 0.2
    detector = detector or YoloxONNX(weights, detector_config())
    tracker = tracker or LocalByteTrack(cadence)
    selected = detection_schedule(registry.frames, cadence)
    # Include every VLM sampling instant so source membership needs no guessed
    # interpolation. Detector boxes and interpolated display boxes stay distinct.
    selected |= {f.ordinal for f in registry.frames if f.frame_id in registry.cached}
    builder = SegmentBuilder(cadence)
    info = probe_video(registry.path)
    with open_video(registry.path) as container:
        stream = container.streams.video[0]
        base = str(stream.time_base)
        stream.codec_context.thread_count = 1
        for i, frame in enumerate(container.decode(stream)):
            if time.monotonic() >= deadline:
                raise TimeoutError("Automatic tracking deadline exhausted")
            if (
                i >= len(registry.frames)
                or frame.pts != registry.frames[i].source_pts
                or frame.is_corrupt
            ):
                raise ValueError("Tracking source association changed")
            if i in selected:
                ref = registry.frames[i]
                boxes = detector.detect(oriented(frame, stream, registry.rotation))
                builder.update(
                    ref.frame_id, ref.timestamp_sec, tracker.update(boxes, ref.timestamp_sec)
                )
    swapped = info["rotation"] % 180 != 0
    return TrackManifest(
        clip_id="clip000",
        source_sha256=registry.source_sha256,
        annotation_file="runtime-no-reference",
        annotation_sha256="0" * 64,
        duration_sec=registry.duration,
        source_width=info["width"],
        source_height=info["height"],
        oriented_width=info["height"] if swapped else info["width"],
        oriented_height=info["width"] if swapped else info["height"],
        rotation=registry.rotation,
        time_base=base,
        frames=[asdict(f) for f in registry.frames],
        detection_frame_ids=[f.frame_id for f in registry.frames if f.ordinal in selected],
        cadence_sec=cadence,
        segments=builder.segments,
        joins=builder.joins,
        gaps=builder.gaps,
        recording_group=registry.source_sha256,
        provenance={
            "origin": "model",
            "purpose": "runtime_prediction_not_training_truth",
            "detector": detector.provenance,
            "areas": "proposed_by_live_scanner",
            "undecodable_ranges": [],
            "automatic_interpolation_approved": False,
        },
    )
