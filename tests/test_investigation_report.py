"""Synthetic immutable-export/sidecar checks; no inference or private content."""

import copy
import fcntl
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from forte.investigation_report import (
    InvalidCorrectionHistory,
    build_investigation_report,
    correction_snapshot,
    result_digest,
)
from forte.timeline import append_correction


@pytest.fixture
def original():
    return {
        "source_sha256": "a" * 64,
        "execution": {"status": "partial"},
        "assessment": "insufficient_evidence",
        "events": [
            {"event_id": "event-a", "start_sec": 0, "end_sec": 1, "actor_ids": ["p1"]},
            {"event_id": "event-b", "start_sec": 1, "end_sec": 2, "actor_ids": ["p2"]},
        ],
        "timeline": {
            "observations": [{"observation_id": "obs-a", "source_pts": 7, "time_base": "1/90"}],
            "events": [{"event_id": "event-a"}, {"event_id": "event-b"}],
            "participants": [{"participant_id": "p1"}],
            "coverage": {"unexamined_intervals": [[2, 5]], "unknown": None},
        },
        "legal": {"assessments": [], "rule_coverage": [{"rule_id": "rule-a", "status": "skipped"}]},
    }


def change(result, parent=None):
    return {
        "source_sha256": result["source_sha256"],
        "parent_revision": parent,
        "scope": "visual",
        "target_id": "obs-a",
        "reviewer": "synthetic-reviewer",
        "change": {"note": "Synthetic review", "unknown_owner": None},
    }


def test_complete_export_preserves_adjacent_events_pts_unknowns_and_history(tmp_path, original):
    before = copy.deepcopy(original)
    path = append_correction(tmp_path / "corrections", original, change(original))
    revisions = correction_snapshot(path.parent, original)
    report = build_investigation_report(uuid4(), original, revisions)
    assert report["result"] == before == original
    assert report["corrections"] == revisions
    assert (
        report["base_result_sha256"]
        == hashlib.sha256(
            json.dumps(original, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()
    )
    assert report["review_head"] == path.name
    assert report["corrections_match_current_result"] is True
    assert all(value.startswith("/api/v2/jobs/") for value in report["links"].values())
    report["result"]["events"].clear()
    assert original == before


def test_snapshot_retains_ancestry_order_and_old_base_without_reapplying(tmp_path, original):
    first = append_correction(tmp_path / "corrections", original, change(original))
    second = append_correction(first.parent, original, change(original, first.name))
    updated = copy.deepcopy(original)
    updated["assessment"] = "not_applicable"
    updated["timeline"]["observations"] = []
    revisions = correction_snapshot(first.parent, updated)
    assert [item["revision_id"] + ".json" for item in revisions] == [first.name, second.name]
    report = build_investigation_report(uuid4(), updated, revisions)
    assert report["corrections_match_current_result"] is False
    assert report["result"] == updated
    assert revisions[0]["base_result_sha256"] == result_digest(original)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha256", "b" * 64),
        ("base_result_sha256", "bad"),
        ("revision_id", "wrong"),
        ("parent_revision", "f" * 32 + ".json"),
        ("target_id", "invented"),
        ("origin", "model"),
        ("other_scopes_approved", True),
        ("created_unix_sec", float("nan")),
    ],
)
def test_corrupt_or_unbound_history_fails_closed(tmp_path, original, field, value):
    path = append_correction(tmp_path / "corrections", original, change(original))
    revision = json.loads(path.read_text())
    revision[field] = value
    path.write_text(json.dumps(revision))
    with pytest.raises(InvalidCorrectionHistory):
        correction_snapshot(path.parent, original)


@pytest.mark.parametrize("target", ["directory", "lock", "revision"])
def test_snapshot_rejects_symlinks(tmp_path, original, target):
    path = append_correction(tmp_path / "corrections", original, change(original))
    directory = path.parent
    if target == "directory":
        link = tmp_path / "linked"
        link.symlink_to(directory, target_is_directory=True)
        directory = link
    else:
        selected = directory / ".revision.lock" if target == "lock" else path
        other = tmp_path / "outside"
        selected.rename(other)
        selected.symlink_to(other)
    with pytest.raises(InvalidCorrectionHistory):
        correction_snapshot(directory, original)


def test_snapshot_waits_for_writer_before_reading_incomplete_json(tmp_path, original):
    path = append_correction(tmp_path / "corrections", original, change(original))
    complete = path.read_bytes()
    started = threading.Event()
    with (path.parent / ".revision.lock").open("r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path.write_text('{"incomplete":')
        with ThreadPoolExecutor() as executor:

            def read():
                started.set()
                return correction_snapshot(path.parent, original)

            pending = executor.submit(read)
            assert started.wait(1)
            assert not pending.done()
            path.write_bytes(complete)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            assert pending.result(timeout=2)[0]["revision_id"] + ".json" == path.name


def test_missing_history_is_explicitly_empty(tmp_path, original):
    assert correction_snapshot(tmp_path / "absent", original) == []


def test_nonregular_revision_is_rejected_without_blocking(tmp_path, original):
    directory = tmp_path / "corrections"
    directory.mkdir()
    import os

    os.mkfifo(directory / ("f" * 32 + ".json"))
    with pytest.raises(InvalidCorrectionHistory):
        correction_snapshot(directory, original)
