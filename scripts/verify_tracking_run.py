"""Private mechanical provenance checks, with aggregate-only stdout.

Does not inspect semantic content or establish that a person/action is correct.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path

from forte.person_proposals import allowlisted_sources, sha256, write_json
from forte.tracking_cli import load_pair
from forte.video import open_video, oriented


def digest_jpeg(image):
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95)
    return hashlib.sha256(out.getvalue()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    sources = {
        r["clip_id"]: r
        for r in allowlisted_sources(
            args.private_root / "batch-selection.json",
            args.private_root / "annotation-review/sources",
        )
    }
    index = json.loads((args.directory / "index.json").read_bytes())
    results = []
    for row in index["records"]:
        record = sources[row["clip_id"]]
        directory = (args.directory / row["manifest"]).parent
        m, _ = load_pair(directory, record["source"])
        for name, expected in m.provenance["review_media"].items():
            if sha256(directory / name) != expected:
                raise ValueError("Review derivative checksum mismatch")
        for name in ["review.mp4", "oriented-source.mp4"]:
            count = 0
            with open_video(directory / name) as container:
                stream = container.streams.video[0]
                for i, frame in enumerate(container.decode(stream)):
                    if (
                        i >= len(m.frames)
                        or abs(float(frame.pts * frame.time_base) - m.frames[i].timestamp_sec)
                        > 1e-4
                        or (frame.width, frame.height) != (m.oriented_width, m.oriented_height)
                    ):
                        raise ValueError("Review derivative source timing/dimensions mismatch")
                    count += 1
            if count != len(m.frames):
                raise ValueError("Review playback dropped source frames")
        assets = json.loads((directory / "review-assets.json").read_bytes())
        selected = {a["frame_id"]: a for a in [assets[0], assets[len(assets) // 2], assets[-1]]}
        binding = directory / "correction-binding-pending.json"
        if binding.exists():
            ref = json.loads(binding.read_bytes()).get("preserved_role_reference")
            if ref:
                ids = {f["frame_id"] for v in ref["variants"] for f in v["frames"]}
                selected.update({a["frame_id"]: a for a in assets if a["frame_id"] in ids})
        crop_count = 0
        with open_video(record["source"]) as container:
            stream = container.streams.video[0]
            for i, frame in enumerate(container.decode(stream)):
                ref = m.frames[i]
                if ref.frame_id not in selected:
                    continue
                a = selected[ref.frame_id]
                if (
                    frame.pts != a["source_pts"]
                    or abs(ref.timestamp_sec - a["timestamp_sec"]) > 1e-6
                ):
                    raise ValueError("Asset source frame mismatch")
                image = oriented(frame, stream, m.rotation)
                if (
                    digest_jpeg(image) != a["full_scene_sha256"]
                    or sha256(directory / a["full_scene"]) != a["full_scene_sha256"]
                ):
                    raise ValueError("Full-scene pixels do not match actual source")
                for crop in a["crops"]:
                    coords = crop["full_frame_pixel_crop"]
                    if (
                        digest_jpeg(image.crop(coords)) != crop["sha256"]
                        or sha256(directory / crop["path"]) != crop["sha256"]
                    ):
                        raise ValueError("Crop pixels/source transform mismatch")
                    crop_count += 1
        results.append(
            dict(
                clip_id=m.clip_id,
                source_frames=len(m.frames),
                playback_frames_checked=2 * len(m.frames),
                source_images_reextracted=len(selected),
                source_crops_reextracted=crop_count,
                binding_verified=True,
                semantic_review=False,
            )
        )
    report = dict(
        recordings_verified=len(results),
        source_frames_verified=sum(r["source_frames"] for r in results),
        playback_frames_verified=sum(r["playback_frames_checked"] for r in results),
        source_images_reextracted=sum(r["source_images_reextracted"] for r in results),
        source_crops_reextracted=sum(r["source_crops_reextracted"] for r in results),
        semantic_quality_established=False,
    )
    write_json(args.directory / "source-verification.json", dict(aggregate=report, records=results))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
