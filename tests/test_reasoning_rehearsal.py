import hashlib
import importlib.util
import time
from pathlib import Path

import pytest
from test_video import make_mov

from forte.timeline import EvidenceTools, source_frame_table
from forte.video import decode_video

spec = importlib.util.spec_from_file_location(
    "reasoning_rehearsal", Path(__file__).resolve().parents[1] / "scripts/rehearse_reasoning_api.py"
)
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)


def fixture(tmp_path):
    source = tmp_path / "synthetic.mov"
    make_mov(source, pts=(100, 101, 120))
    registry = decode_video(source, tmp_path / "cache")
    deadline = time.monotonic() + 10
    table = source_frame_table(registry, deadline)
    ref = registry.frames[1]
    raw = EvidenceTools(registry, {}, tmp_path / "tools", deadline, table).original_jpegs(
        [ref.frame_id]
    )[ref.frame_id]
    item = {
        "frame_id": ref.frame_id,
        "source_pts": ref.source_pts,
        "timestamp_sec": ref.timestamp_sec,
        "time_base": table["frames"][1]["time_base"],
        "oriented_size": table["frames"][1]["oriented_size"],
        "image_sha256": hashlib.sha256(raw).hexdigest(),
    }
    result = {
        "source": {"duration_sec": registry.duration, "frame_count": len(registry.frames)},
        "events": [
            {
                "event_id": "synthetic-event",
                "start_sec": 0,
                "end_sec": registry.duration,
                "decisive_frame_id": ref.frame_id,
                "evidence_frame_ids": [ref.frame_id],
                "evidence": [item],
                "evidence_export_complete": True,
            }
        ],
    }
    output = tmp_path / "verification"
    output.mkdir()
    return source, result, {ref.frame_id: raw}, output, deadline


def test_independent_api_verifier_binds_vfr_markers_and_exact_source_jpeg(tmp_path):
    args = fixture(tmp_path)
    receipt = rehearsal.verify_evidence(*args)
    assert receipt == {
        "decoded_source_frames": 3,
        "evidence_jpegs_verified": 1,
        "event_markers_verified": 1,
    }


def test_consistent_fake_image_hash_cannot_replace_original_jpeg(tmp_path):
    source, result, fetched, output, deadline = fixture(tmp_path)
    frame_id = next(iter(fetched))
    fetched[frame_id] = b"altered-api-evidence"
    result["events"][0]["evidence"][0]["image_sha256"] = hashlib.sha256(
        fetched[frame_id]
    ).hexdigest()
    with pytest.raises(ValueError, match="independently re-extracted"):
        rehearsal.verify_evidence(source, result, fetched, output, deadline)


def test_invented_source_pts_cannot_pass_marker_membership(tmp_path):
    source, result, fetched, output, deadline = fixture(tmp_path)
    result["events"][0]["evidence"][0]["source_pts"] += 999
    with pytest.raises(ValueError, match="independently re-extracted"):
        rehearsal.verify_evidence(source, result, fetched, output, deadline)
