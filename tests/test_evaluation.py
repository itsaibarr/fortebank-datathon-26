import json
from uuid import uuid4

import pytest

from forte.evaluation import evaluate


def fixture_run(tmp_path, positive=True, status="done", verdict="no_violation"):
    group = {
        "recording_id": "a" * 64,
        "neutral_file": "clip000.mov",
        "split": "development",
        "positive": positive,
        "label_points_sec": [2],
        "strict_point_scoring_eligible": True,
    }
    manifest = {"split_status": "provisional", "code_commit": "fixture", "groups": [group]}
    directory = tmp_path / "clip000"
    directory.mkdir()
    result = {"job_id": str(uuid4()), "status": status}
    if status == "done":
        result.update(verdict=verdict, violations=[])
    else:
        result["error"] = {"code": "processing_timeout", "message": "Synthetic failure"}
    (directory / "result.json").write_text(json.dumps(result))
    summary = {"source_sha256": group["recording_id"], "seconds": 4.0}
    (directory / "summary.json").write_text(json.dumps(summary))
    return manifest, directory


def test_failed_positive_is_an_abstention_and_reduces_effective_recall(tmp_path):
    manifest, _ = fixture_run(tmp_path, status="failed")
    report = evaluate(manifest, tmp_path)
    assert report["counts"] == {
        "videos": 1,
        "positives": 1,
        "negatives": 0,
        "tp": 0,
        "tn": 0,
        "fp": 0,
        "fn": 0,
        "failed_positive": 1,
        "failed_negative": 0,
    }
    assert report["effective_recall"] == 0
    assert report["false_negative_rate_including_failed"] == 1
    assert report["completed_fraction"] == 0
    assert report["failure_codes"] == {"processing_timeout": 1}


def test_completed_negative_on_positive_is_counted_as_a_miss(tmp_path):
    manifest, _ = fixture_run(tmp_path)
    report = evaluate(manifest, tmp_path)
    assert report["counts"]["fn"] == 1
    assert report["accuracy_including_failed"] == 0


def test_reserved_or_duplicate_recordings_are_rejected(tmp_path):
    manifest, _ = fixture_run(tmp_path)
    manifest["groups"][0]["split"] = "locked_holdout"
    with pytest.raises(ValueError, match="development"):
        evaluate(manifest, tmp_path)
    manifest["groups"][0]["split"] = "development"
    manifest["groups"].append(manifest["groups"][0].copy())
    with pytest.raises(ValueError, match="duplicate"):
        evaluate(manifest, tmp_path)


def test_missing_or_misaligned_results_cannot_form_a_report(tmp_path):
    manifest, directory = fixture_run(tmp_path)
    (directory / "summary.json").write_text(json.dumps({"source_sha256": "b" * 64}))
    with pytest.raises(ValueError, match="source"):
        evaluate(manifest, tmp_path)
    (directory / "result.json").unlink()
    with pytest.raises(FileNotFoundError):
        evaluate(manifest, tmp_path)


def test_ambiguous_anchor_is_excluded_from_point_scoring(tmp_path):
    manifest, directory = fixture_run(tmp_path)
    from test_video import make_mov

    from forte.contracts import DoneJob, Violation
    from forte.video import decode_video

    registry = decode_video(make_mov(tmp_path / "s.mov"), tmp_path / "frames")
    result = DoneJob(
        job_id=uuid4(),
        verdict="violation",
        violations=[
            Violation(
                type="Synthetic",
                timecode_sec=1,
                description="Synthetic",
                evidence_frames=registry.evidence([registry.frames[0].frame_id]),
            )
        ],
    )
    (directory / "result.json").write_text(result.model_dump_json())
    report = evaluate(manifest, tmp_path)
    assert report["point_proximity"]["median_error_sec"] == 1
    manifest["groups"][0]["strict_point_scoring_eligible"] = False
    report = evaluate(manifest, tmp_path)
    assert report["point_proximity"]["eligible_positive_videos"] == 0
    assert report["point_proximity"]["median_error_sec"] is None
