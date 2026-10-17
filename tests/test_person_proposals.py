import hashlib
import json

import pytest
from PIL import Image
from test_video import make_mov

from forte.person_proposals import allowlisted_sources, prepare_clip, verify_source


def test_allowlist_uses_only_neutral_hash_split_and_rejects_mutated_source(tmp_path):
    src = tmp_path / "clip000.mov"
    src.write_bytes(b"not decoded for this test")
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "recording_id": digest,
                        "neutral_file": "clip000.mov",
                        "split": "development",
                        "positive": "DO NOT USE",
                        "label_points_sec": ["DO NOT USE"],
                    },
                    {"recording_id": "a" * 64, "neutral_file": "clip001.mov", "split": "reserved"},
                ]
            }
        )
    )
    records = allowlisted_sources(selection, tmp_path)
    assert len(records) == 1 and records[0]["clip_id"] == "clip000"
    verify_source(records[0])
    src.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="hash"):
        verify_source(records[0])
    selection.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "recording_id": digest,
                        "neutral_file": "../clip000.mov",
                        "split": "development",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        allowlisted_sources(selection, tmp_path)


def test_real_decode_pipeline_binds_complete_source_and_keeps_derivatives_separate(tmp_path):
    source = tmp_path / "clip000.mov"
    make_mov(source, pts=(100, 101, 102, 120, 130))
    record = dict(
        clip_id="clip000",
        source=source,
        recording_group=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    template = tmp_path / "old.json"
    from forte.video import decode_video

    registry = decode_video(source, tmp_path / "cache")
    template.write_text(
        json.dumps(
            dict(
                source_sha256=record["recording_group"],
                duration_sec=registry.duration + 0.01,
                frames={},
                facts=[],
                claims=[],
            )
        )
    )
    original = template.read_bytes()

    class Detector:
        provenance = {"synthetic": True}

        def detect(self, image):
            return [((0.1, 0.1, 0.5, 0.9), 0.9)]

    class Tracker:
        def update(self, boxes, timestamp):
            return [(1, b, s) for b, s in boxes]

    output = tmp_path / "out"
    m = prepare_clip(
        record, template, output, Detector(), Tracker(), cadence_sec=0.2, regression_only=True
    )
    assert m.frames[-1].timestamp_sec == registry.frames[-1].timestamp_sec
    assert m.detection_frame_ids[0] == "f000000"
    assert m.detection_frame_ids[-1] == registry.frames[-1].frame_id
    assert len(m.segments) == 1 and not m.training_eligible
    assert m.regression_only
    assert template.read_bytes() == original
    assets = json.loads((output / "review-assets.json").read_text())
    for item in assets:
        assert item["frame_id"] in {f.frame_id for f in m.frames}
        for rel in ["full_scene", "overlay"]:
            assert (output / item[rel]).is_file()
        for crop in item["crops"]:
            with Image.open(output / crop["path"]) as im:
                assert im.width > 0 and im.height > 0
    with pytest.raises(FileExistsError):
        prepare_clip(record, template, output, Detector(), Tracker())


def test_cli_rejects_non_allowlisted_clip_before_loading_models(tmp_path, capsys):
    from forte.cli import main

    (tmp_path / "batch-selection.json").write_text(json.dumps({"groups": []}))
    assert (
        main(
            [
                "tracks-prepare",
                "--private-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "out"),
                "--clip",
                "clip999",
                "--weights",
                str(tmp_path / "absent"),
                "--config",
                str(tmp_path / "absent"),
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert "Traceback" not in output.err


def test_stale_review_receipt_is_preserved_as_unresolved_without_blocking_proposals(tmp_path):
    from forte.tracking_cli import review_receipts

    review = tmp_path / "review.json"
    review.write_text('{"items": []}')
    receipt = review_receipts(review, {"review_file_sha256": "0" * 64})
    assert not receipt["reference_review_hash_matches_current"]
    assert receipt["original_reference_review_sha256"] == "0" * 64
    assert receipt["current_review_sha256"] == hashlib.sha256(review.read_bytes()).hexdigest()
    assert receipt["binding_review_status"] == "pending"


def test_internal_pts_consistency_does_not_substitute_for_actual_source_binding(tmp_path):
    from dataclasses import asdict
    from fractions import Fraction

    from forte.person_proposals import verify_manifest_source
    from forte.tracking import TrackManifest
    from forte.video import decode_video, open_video, probe_video

    source = make_mov(tmp_path / "clip000.mov")
    registry = decode_video(source, tmp_path / "cache")
    with open_video(source) as c:
        base = str(c.streams.video[0].time_base)
    info = probe_video(source)
    m = TrackManifest(
        clip_id="clip000",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        annotation_file="annotation.json",
        annotation_sha256="0" * 64,
        duration_sec=registry.duration,
        source_width=info["width"],
        source_height=info["height"],
        oriented_width=info["width"],
        oriented_height=info["height"],
        rotation=0,
        time_base=base,
        frames=[asdict(f) for f in registry.frames],
        detection_frame_ids=[f.frame_id for f in registry.frames],
        cadence_sec=0.2,
        segments=[],
        recording_group=registry.source_sha256,
    )
    verify_manifest_source(m, source)
    m.frames[1].source_pts += 1
    m.frames[1].timestamp_sec = float(
        (m.frames[1].source_pts - m.frames[0].source_pts) * Fraction(base)
    )
    m = TrackManifest.model_validate(m.model_dump())
    with pytest.raises(ValueError, match="source frame"):
        verify_manifest_source(m, source)


def test_review_cli_preserves_proposals_and_refreshes_revision_receipts(tmp_path):
    from forte.cli import main
    from forte.video import decode_video

    source = make_mov(tmp_path / "clip000.mov")
    reg = decode_video(source, tmp_path / "cache")
    template = tmp_path / "template.json"
    template.write_text(
        json.dumps(
            dict(
                source_sha256=reg.source_sha256,
                duration_sec=reg.duration,
                frames={},
                facts=[],
                claims=[],
            )
        )
    )
    record = dict(clip_id="clip000", source=source, recording_group=reg.source_sha256)

    class Detector:
        provenance = {"synthetic": True}

        def detect(self, image):
            return [((0.1, 0.1, 0.5, 0.9), 0.9)]

    class Tracker:
        def update(self, boxes, timestamp):
            return [(1, b, s) for b, s in boxes]

    original = tmp_path / "original"
    prepare_clip(record, template, original, Detector(), Tracker(), extra_frame_ids=["f000001"])
    original_bytes = (original / "tracks.json").read_bytes()
    operations = tmp_path / "operations.json"
    operations.write_text(json.dumps([{"operation": "review", "segment_id": "s00001"}]))
    revised = tmp_path / "reviewed"
    assert (
        main(
            [
                "tracks-review",
                "--directory",
                str(original),
                "--source",
                str(source),
                "--output",
                str(revised),
                "--operations",
                str(operations),
                "--reviewer",
                "synthetic reviewer",
                "--reason",
                "Synthetic identity review",
            ]
        )
        == 0
    )
    assert (original / "tracks.json").read_bytes() == original_bytes
    receipt = json.loads((revised / "complete.json").read_text())
    assert (
        receipt["manifest_sha256"]
        == hashlib.sha256((revised / "tracks.json").read_bytes()).hexdigest()
    )
    assert (revised / "review-operations.json").read_bytes() == operations.read_bytes()
    old_frames = {a["frame_id"] for a in json.loads((original / "review-assets.json").read_text())}
    new_frames = {a["frame_id"] for a in json.loads((revised / "review-assets.json").read_text())}
    assert old_frames <= new_frames
    m = json.loads((revised / "tracks.json").read_text())
    assert m["segments"][0]["review"]["status"] == "confirmed"
    assert all(box["review"]["status"] == "draft" for box in m["segments"][0]["boxes"])
    assert not m["training_eligible"]
    for name, digest in m["provenance"]["review_media"].items():
        assert hashlib.sha256((revised / name).read_bytes()).hexdigest() == digest

    # A second review must preserve the exact input behind earlier corrections.
    # Reusing review-operations.json for the latest input cannot rewrite history.
    prior_manifest = (revised / "tracks.json").read_bytes()
    first_input = operations.read_bytes()
    second_input = tmp_path / "second-operations.json"
    second_input.write_text(
        json.dumps([{"operation": "review", "segment_id": "s00001", "status": "rejected"}])
    )
    latest = tmp_path / "reviewed-again"
    assert (
        main(
            [
                "tracks-review",
                "--directory",
                str(revised),
                "--source",
                str(source),
                "--output",
                str(latest),
                "--operations",
                str(second_input),
                "--reviewer",
                "synthetic reviewer",
                "--reason",
                "Synthetic second review",
            ]
        )
        == 0
    )
    assert (revised / "tracks.json").read_bytes() == prior_manifest
    history = json.loads((latest / "tracks.json").read_bytes())["corrections"]
    assert (latest / history[0]["artifact"]).read_bytes() == first_input
    assert (latest / history[-1]["artifact"]).read_bytes() == second_input.read_bytes()


def test_actual_source_duration_limits_even_an_internally_valid_manifest(tmp_path):
    from dataclasses import asdict

    from forte.person_proposals import verify_manifest_source
    from forte.tracking import TrackManifest
    from forte.video import decode_video, open_video, probe_video

    source = make_mov(tmp_path / "clip000.mov")
    reg = decode_video(source, tmp_path / "cache")
    info = probe_video(source)
    with open_video(source) as c:
        base = str(c.streams.video[0].time_base)
    m = TrackManifest(
        clip_id="clip000",
        source_sha256=reg.source_sha256,
        annotation_file="a.json",
        annotation_sha256="0" * 64,
        duration_sec=reg.duration + 10,
        source_width=info["width"],
        source_height=info["height"],
        oriented_width=info["width"],
        oriented_height=info["height"],
        rotation=0,
        time_base=base,
        frames=[asdict(f) for f in reg.frames],
        detection_frame_ids=[f.frame_id for f in reg.frames],
        cadence_sec=0.2,
        segments=[],
        recording_group=reg.source_sha256,
    )
    with pytest.raises(ValueError, match="duration"):
        verify_manifest_source(m, source)
