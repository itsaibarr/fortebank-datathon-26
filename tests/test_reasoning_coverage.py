"""Completed sampling cannot conceal unresolved visibility or refinement work."""

import pytest
from synthetic_decisions import UnknownDecisions
from test_video import make_mov

from forte import frozen_tracking, pipeline
from forte.settings import Settings


@pytest.mark.parametrize(
    "unclear,pending,expected",
    [
        (False, 0, "no_violation_observed"),
        (True, 0, "insufficient_evidence"),
        (False, 1, "insufficient_evidence"),
    ],
)
def test_unresolved_coverage_cannot_be_exported_as_completed_clearance(
    tmp_path, monkeypatch, unclear, pending, expected
):
    monkeypatch.setattr(frozen_tracking, "require_outbound_blocked", lambda: {"synthetic": True})

    def scan(registry, *args, **kwargs):
        return {
            "source_sha256": registry.source_sha256,
            "events": [],
            "participants": [],
            "observations": [],
            "status": "complete_schedule",
            "metrics": {},
            "coverage": {
                "unexamined_intervals": [],
                "unclear_intervals": [[0, registry.duration]] if unclear else [],
                "pending_reinspections": pending,
            },
        }

    class Backend:
        def ready(self):
            return True

    class Law:
        def evaluate_timeline(self, *args, **kwargs):
            return {
                "status": "complete_scoped_schedule",
                "assessments": [{"assessment": "no_violation_observed"}],
                "metrics": {},
            }

    monkeypatch.setattr(pipeline, "scan_recording", scan)
    result = pipeline.analyze_reasoning(
        make_mov(tmp_path / "synthetic.mov"),
        tmp_path / "run",
        Settings(
            "synthetic-key-long-enough", tmp_path, reasoning_config={"tracking": {}, "legal": {}}
        ),
        decision_backend=UnknownDecisions(),
        backend=Backend(),
        legal=Law(),
        tracking=lambda *args, **kwargs: {"participants": [], "frame_boxes": {}},
    )
    assert result["assessment"] == expected
    assert result["execution"]["status"] == (
        "completed" if expected == "no_violation_observed" else "partial"
    )
