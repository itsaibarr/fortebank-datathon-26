"""Synthetic evaluation-boundary regressions, never sponsor reference answers."""

import json
from pathlib import Path

import pytest

from forte.mechanic_validation import inference_inputs, select_smoke


def fixture():
    groups = [
        dict(
            recording_id=str(i) * 64,
            neutral_file=f"clip{i:03}.mov",
            split="development",
            positive=i % 2 == 1,
            label_points_sec=[123],
            canonical_file="private-original-name.mov",
        )
        for i in range(1, 6)
    ]
    groups.append(
        dict(
            recording_id="9" * 64, neutral_file="clip999.mov", split="locked_holdout", positive=True
        )
    )
    rows = [
        dict(clip_id=Path(g["neutral_file"]).stem, regression_only=i == 0, pilot=i == 3)
        for i, g in enumerate(groups)
    ]
    return {"groups": groups}, {"records": rows}


def test_selection_excludes_diagnostic_and_reserved_and_uses_distinct_groups():
    selection, index = fixture()
    chosen = select_smoke(selection, index)
    assert [g["neutral_file"] for g in chosen] == ["clip003.mov", "clip002.mov", "clip004.mov"]
    assert len({g["recording_id"] for g in chosen}) == 3
    assert all(g["split"] == "development" for g in chosen)


def test_inference_projection_cannot_contain_labels_timestamps_or_original_names():
    selection, index = fixture()
    inputs = inference_inputs(select_smoke(selection, index), Path("/private/neutral"))
    assert all(set(r) == {"neutral_file", "source_sha256", "source"} for r in inputs)
    assert "private-original-name" not in str(inputs)
    assert "123" not in str(inputs)


def test_unknown_diagnostic_status_is_ineligible():
    selection, index = fixture()
    for row in index["records"]:
        row.pop("regression_only")
    with pytest.raises(ValueError, match="positive and normal"):
        select_smoke(selection, index)


@pytest.mark.parametrize(
    "legal_outcome,expected",
    [
        ("supported_violation", "supported_violation"),
        ("no_violation_observed", "insufficient_evidence"),
    ],
)
def test_partial_orchestration_preserves_supported_event_and_never_cleans_skips(
    tmp_path, monkeypatch, legal_outcome, expected
):
    import time

    from test_video import make_mov

    from forte import frozen_tracking, legal_reasoning, reasoning_pipeline
    from forte.settings import Settings

    monkeypatch.setattr(frozen_tracking, "require_outbound_blocked", lambda: {"synthetic": True})

    def scan(registry, participants, *args, **kwargs):
        frames = registry.frames
        event = {
            "event_id": "synthetic-event",
            "observation_ids": ["synthetic-observation"],
            "evidence_frame_ids": [frames[0].frame_id, frames[-1].frame_id],
            "decisive_frame_id": frames[-1].frame_id,
            "start_sec": 0,
            "end_sec": frames[-1].timestamp_sec,
            "actor_ids": [],
            "value": "Synthetic event only.",
            "uncertainty": [],
        }
        return {
            "events": [event],
            "status": "failed_pass",
            "coverage": {"unexamined_intervals": [[0, registry.duration]]},
            "metrics": {},
        }

    monkeypatch.setattr(reasoning_pipeline, "scan_recording", scan)
    calls = {}

    class SyntheticLaw:
        def __init__(self, *args, **kwargs):
            calls["constructor"] = kwargs

        def evaluate_timeline(self, *args, **kwargs):
            calls["evaluator"] = kwargs
            return {
                "status": "incomplete",
                "assessments": [
                    {
                        "assessment_id": "synthetic-assessment",
                        "observation_ids": ["synthetic-observation"],
                        "assessment": legal_outcome,
                    },
                    {
                        "assessment_id": "unrelated-fragment",
                        "observation_ids": ["unrelated-observation"],
                        "assessment": "insufficient_evidence",
                    },
                ],
            }

    monkeypatch.setattr(legal_reasoning, "LegalEvidenceService", SyntheticLaw)

    class Backend:
        def ready(self):
            return True

    settings = Settings(
        "synthetic-smoke-only-key",
        tmp_path,
        reasoning_config={
            "tracking": {},
            "legal": {
                "release": "/synthetic-law",
                "cards": "/synthetic-cards",
                "operation_context": {"synthetic_context": True},
            },
            "bounds": {"legal_max_calls": 2},
        },
    )
    result = reasoning_pipeline.analyze_reasoning(
        make_mov(tmp_path / "synthetic.mov"),
        tmp_path / "output",
        settings,
        backend=Backend(),
        tracking=lambda *a, **k: {"participants": [], "frame_boxes": {}},
        deadline=time.monotonic() + 20,
    )
    assert result["assessment"] == expected
    assert result["execution"]["status"] == "partial"
    assert result["events"][0]["assessment"] == legal_outcome
    assert 1 <= len(result["events"][0]["evidence"]) <= 3
    assert calls["constructor"] == {}  # no reviewed applicability configured
    assert calls["evaluator"]["operation_context"] == {"synthetic_context": True}
    assert "metadata_evidence" not in calls["evaluator"]
    assert calls["evaluator"]["max_calls"] == 2


def test_actual_api_default_dispatch_uses_legacy_v1_even_with_reasoning_config(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from test_api_v2 import negative, submit, uncertain
    from test_video import make_mov

    from forte import api
    from forte.settings import Settings

    calls = []

    async def worker(
        directory, job_id, deadline, settings, *, reasoning=False, frozen_configuration=None
    ):
        calls.append(reasoning)
        if reasoning:
            assert frozen_configuration == directory / "immutable/request-config.json"
            assert json.loads(frozen_configuration.read_bytes())["tracking"] == {
                "mode": "byte_track"
            }
        else:
            assert frozen_configuration is None
        return await (uncertain if reasoning else negative)(directory, job_id, deadline)

    monkeypatch.setattr(api, "run_worker", worker)
    settings = Settings(
        "synthetic-version-two-key",
        tmp_path / "jobs",
        reasoning_config={"tracking": {"mode": "byte_track"}, "legal": {"release": "/synthetic"}},
    )
    with TestClient(api.create_app(settings, ready=lambda: True)) as client:
        media = make_mov(tmp_path / "synthetic.mov").read_bytes()
        v1 = submit(client, media, version=1)
        v2 = submit(client, media, version=2)
    assert calls == [False, True]
    assert set(v1) == {"job_id", "status", "verdict", "violations"}
    assert v2["result"]["assessment"] == "insufficient_evidence"
    assert "verdict" not in v2
