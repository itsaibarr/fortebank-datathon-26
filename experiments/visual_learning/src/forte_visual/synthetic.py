"""Public synthetic fixtures only: colored blocks, no people or competition labels."""

from fractions import Fraction
from pathlib import Path

import av
from forte.video import decode_video, open_video
from PIL import Image, ImageDraw

from forte_visual.io import digest, private_dir, write


def create(root: Path, count=2, duration=8):
    frame_count = int(duration * 2)
    if frame_count < 16 or frame_count > 360:
        raise ValueError("Synthetic duration must be between 8 and 180 seconds")
    private_dir(root)
    files, clips = {}, []
    review = {
        "status": "confirmed",
        "reviewer": "synthetic-reviewer",
        "reviewed_at": "2026-10-17T00:00:00Z",
    }
    for n in range(count):
        directory = root / f"clip{n:03d}"
        directory.mkdir(mode=0o700)
        media = directory / "source.mov"
        with av.open(str(media), "w", format="mov") as out:
            stream = out.add_stream("mpeg4", rate=2)
            stream.width, stream.height, stream.pix_fmt = 96, 64, "yuv420p"
            for i in range(frame_count):
                image = Image.new("RGB", (96, 64), (n * 27 % 255, 20, 40))
                ImageDraw.Draw(image).rectangle((10 + i, 8, 35 + i, 56), fill="white")
                frame = av.VideoFrame.from_image(image)
                frame.pts, frame.time_base = i, Fraction(1, 2)
                for packet in stream.encode(frame):
                    out.mux(packet)
            for packet in stream.encode():
                out.mux(packet)
        registry = decode_video(media, directory / "images")
        with open_video(media) as container:
            time_base = str(container.streams.video[0].time_base)
        ids = [f.frame_id for f in registry.frames]
        annotation = {
            "source_sha256": registry.source_sha256,
            "duration_sec": registry.duration,
            "frames": {f.frame_id: f.timestamp_sec for f in registry.frames},
            "facts": [],
            "claims": [],
        }
        for kind, value, selected in [
            ("role", "cashier", [ids[round(i * (len(ids) - 1) / 5)] for i in range(6)]),
            ("action", "exchange", ids[:8]),
            ("context", "unknown", ids[:8]),
        ]:
            annotation["facts"].append(
                {
                    "id": kind,
                    "kind": kind,
                    "value": value,
                    "actor_id": "p0001",
                    "counterpart_actor_id": "p0002" if kind == "action" else None,
                    "counterpart_segment_ids": ["s0002"] if kind == "action" else [],
                    "counterpart_frame_ids": selected if kind == "action" else [],
                    "actor_participation": "giver" if kind == "action" else "unclear",
                    "start_sec": 0,
                    "end_sec": duration - 0.5,
                    "frame_ids": selected,
                    "continuity_supported": True,
                    "review_status": "confirmed",
                    "reviewer": "synthetic-reviewer",
                    "segment_ids": ["s0001"],
                    "work_area_id": "a1",
                    "observation_state": "observed",
                    "target_kind": "fact",
                    "visibility_limits": "Synthetic blocks only",
                    "visible_basis": "Synthetic",
                    "reviewed_at": review["reviewed_at"],
                    "origin": "human",
                    "playback_interval": [0, duration],
                    "boundary_uncertain": False,
                }
            )
        write(directory / "annotation.json", annotation)
        manifest = {
            "schema_version": 1,
            "clip_id": directory.name,
            "source_sha256": registry.source_sha256,
            "annotation_file": "annotation.json",
            "annotation_sha256": digest(directory / "annotation.json"),
            "duration_sec": registry.duration,
            "source_width": 96,
            "source_height": 64,
            "oriented_width": 96,
            "oriented_height": 64,
            "rotation": 0,
            "time_base": time_base,
            "frames": [vars(f) for f in registry.frames],
            "detection_frame_ids": ids,
            "cadence_sec": 0.5,
            "segments": [
                {
                    "id": f"s000{p}",
                    "person_id": f"p000{p}",
                    "upstream_id": p,
                    "review": review,
                    "boxes": [
                        {
                            "frame_id": f,
                            "xyxy": [0.05 if p == 1 else 0.5, 0.05, 0.48 if p == 1 else 0.95, 0.95],
                            "review": review,
                        }
                        for f in ids
                    ],
                }
                for p in (1, 2)
            ],
            "work_areas": [
                {"id": "a1", "frame_ids": ids, "points": [[0, 0], [1, 0], [1, 1]], "review": review}
            ],
            "recording_group": registry.source_sha256,
            "session_group": f"session{n}",
            "split": "development",
            "regression_only": n == 0,
            "provenance": {"producer_code_commit": "b" * 40},
        }
        write(directory / "tracks.json", manifest)
        for path in directory.rglob("*"):
            if path.is_file():
                files[str(path.relative_to(root))] = digest(path)
        clips.append(
            {
                "manifest": f"{directory.name}/tracks.json",
                "annotation": f"{directory.name}/annotation.json",
                "media": f"{directory.name}/source.mov",
                "images": {f: str(p.relative_to(root)) for f, p in registry.cached.items()},
            }
        )
    write(
        root / "release.json",
        {
            "schema_version": "forte-visual-release/1",
            "producer_schema": "forte-track/1",
            "producer_code_commit": "b" * 40,
            "export_complete": True,
            "completed_by": "synthetic-generator",
            "completed_at": review["reviewed_at"],
            "synthetic": True,
            "files": files,
            "clips": clips,
        },
    )
    return root / "release.json"
