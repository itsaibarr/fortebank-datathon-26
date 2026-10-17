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
    make_mov(source)
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
                duration_sec=registry.duration,
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
