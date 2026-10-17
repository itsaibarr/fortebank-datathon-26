"""Prepare/verify a synthetic CVAT Community server round trip, without real footage.

Upload the prepared oriented-source.mp4 and cvat.xml to the local server, then
export CVAT for video 1.1 and pass the extracted XML to verify. This offline
checker does not claim that an adapter-only round trip exercised the server.
"""

import argparse
import json
import math
import time
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path

import av
from PIL import Image

from forte.annotations import Annotation
from forte.person_proposals import build_packet, sha256, write_json
from forte.track_review import import_cvat
from forte.tracking import Box, Segment, TrackManifest, WorkArea
from forte.tracking_cli import load_pair, private_output
from forte.video import decode_video


def prepare(directory):
    private_output(directory)
    directory.mkdir(mode=0o700)  # Refuse to overwrite any previous check.
    source = directory / "synthetic.mov"
    with av.open(str(source), "w", format="mov") as out:
        stream = out.add_stream("mpeg4", rate=10)
        stream.width, stream.height = 96, 64
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 10)
        for i, pts in enumerate([100, 104, 111, 120, 130]):
            frame = av.VideoFrame.from_image(
                Image.new("RGB", (96, 64), "red" if i == 2 else "blue")
            )
            frame.pts, frame.time_base = pts, Fraction(1, 10)
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    registry = decode_video(source, directory / "samples", deadline=time.monotonic() + 30)
    annotation = Annotation(
        source_sha256=registry.source_sha256,
        duration_sec=registry.duration,
        frames={f.frame_id: f.timestamp_sec for f in registry.frames},
        facts=[],
        claims=[],
    )
    write_json(directory / "annotation.json", annotation.model_dump(mode="json"))
    with av.open(str(source)) as container:
        time_base = str(container.streams.video[0].time_base)
    m = TrackManifest(
        clip_id="clip999",
        source_sha256=registry.source_sha256,
        annotation_file="annotation.json",
        annotation_sha256=sha256(directory / "annotation.json"),
        duration_sec=registry.duration,
        source_width=96,
        source_height=64,
        oriented_width=96,
        oriented_height=64,
        rotation=0,
        time_base=time_base,
        frames=[asdict(f) for f in registry.frames],
        detection_frame_ids=[f.frame_id for f in registry.frames],
        cadence_sec=1,
        segments=[
            Segment(
                id="s00001",
                person_id="p00001",
                upstream_id=1,
                boxes=[
                    Box(
                        frame_id=f.frame_id,
                        xyxy=(0.1, 0.1, 0.6, 0.9),
                        role_attribute="cashier" if i < 2 else "customer",
                        occluded=i < 2,
                        outside=i == 3,
                        keyframe=i != 1,
                    )
                    for i, f in enumerate(registry.frames)
                ],
            )
        ],
        work_areas=[
            WorkArea(
                id="synthetic-area",
                frame_ids=["f000000", "f000002"],
                points=[(0.1, 0.1), (0.8, 0.1), (0.8, 0.8)],
            )
        ],
        recording_group=registry.source_sha256,
        regression_only=True,
        exclusion_reasons=["synthetic_check_only"],
    )
    build_packet(source, directory, m)
    write_json(directory / "tracks.json", m.model_dump(mode="json"))
    return dict(synthetic_packet_prepared=True, frames=len(m.frames))


def verify(directory, xml):
    private_output(directory)
    m, _ = load_pair(directory, directory / "synthetic.mov")
    if m.clip_id != "clip999" or len(m.frames) != 5 or not m.regression_only:
        raise ValueError("Expected the five-frame synthetic fixture")
    after = import_cvat(m, xml, directory / "cvat-source-map.json")
    if len(after.segments) != 1:
        raise ValueError("Synthetic person track lost or duplicated")
    original, imported = m.segments[0], after.segments[0]
    if original.id != imported.id or original.person_id != imported.person_id:
        raise ValueError("Immutable synthetic identity changed")
    if len(imported.boxes) != len(original.boxes):
        raise ValueError("Synthetic source-frame boxes lost or duplicated")
    for before, box in zip(original.boxes, imported.boxes, strict=True):
        for key in ["frame_id", "outside", "occluded", "keyframe", "role_attribute"]:
            if getattr(before, key) != getattr(box, key):
                raise ValueError(f"Native round trip changed {key}")
        if any(
            not math.isclose(a, b, abs_tol=0.0001)
            for a, b in zip(before.xyxy, box.xyxy, strict=True)
        ):
            raise ValueError("Native round trip changed box coordinates")
        if box.review.status != "draft" or box.origin != "cvat_import":
            raise ValueError("CVAT import unexpectedly approved a synthetic box")
    if len(after.work_areas) != 1:
        raise ValueError("Synthetic polygon lost or duplicated")
    area = after.work_areas[0]
    if (
        area.id != "synthetic-area"
        or not {"f000000", "f000002"} <= set(area.frame_ids)
        or "f000003" in area.frame_ids
        or not area.boundary_uncertain
        or area.review.status != "draft"
        or any(
            not math.isclose(a, b, abs_tol=0.0001)
            for p, q in zip(area.points, m.work_areas[0].points, strict=True)
            for a, b in zip(p, q, strict=True)
        )
    ):
        raise ValueError("Native round trip changed polygon extent/attributes")
    result = dict(
        synthetic_exchange_verified=True,
        native_export_sha256=sha256(xml),
        manifest_sha256=sha256(directory / "tracks.json"),
        source_map_sha256=sha256(directory / "cvat-source-map.json"),
        frames=len(m.frames),
        source_pts_preserved=after.frames == m.frames,
        box_flags_mutable_roles_and_polygon_preserved=True,
        imported_review_status="draft",
        training_targets_released=0,
        server_execution_must_be_recorded_separately=True,
    )
    write_json(directory / "roundtrip-verification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "verify"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--xml", type=Path)
    args = parser.parse_args()
    if args.action == "verify" and args.xml is None:
        parser.error("verify requires --xml from the local CVAT export")
    print(
        json.dumps(
            prepare(args.directory)
            if args.action == "prepare"
            else verify(args.directory, args.xml)
        )
    )


if __name__ == "__main__":
    main()
