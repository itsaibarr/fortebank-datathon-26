"""Synthetic legal preparation failures must preserve useful partial execution."""

import json
import time
from pathlib import Path

import pytest
from test_video import make_mov

from forte import legal_reasoning
from forte.legal_reasoning import LegalEvidenceService
from forte.timeline import EvidenceTools, source_frame_table
from forte.video import decode_video


@pytest.fixture
def legal_run(tmp_path):
    root = Path(__file__).resolve().parents[1]
    service = LegalEvidenceService(root / "legal/2026-10-17", root / "legal/rule-cards.json")
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")
    table = source_frame_table(registry, time.monotonic() + 20)
    frame = registry.frames[0]
    timeline = {
        "source_sha256": registry.source_sha256,
        "participants": [],
        "coverage": {"continuous_visibility_validated": False},
        "observations": [
            {
                "observation_id": "synthetic-observation",
                "source_sha256": registry.source_sha256,
                "value": "Synthetic visible context.",
                "actor_ids": [],
                "recipient_ids": [],
                "evidence_frame_ids": [frame.frame_id],
                "visibility": "visible_samples",
                **{f"{key}_frame_id": frame.frame_id for key in ["start", "end", "decisive"]},
                **{f"{key}_sec": frame.timestamp_sec for key in ["start", "end", "decisive"]},
            }
        ],
    }
    return service, registry, timeline, table


class SyntheticBackend:
    calls = 0
    last_usage = {"total_tokens": 42}
    last_finish_reason = "stop"

    def request(self, _registry, _frames, _prompt, schema, *_args):
        self.calls += 1
        conditions = schema["$defs"]["ConditionResult"]["properties"]
        return {
            "plan_id": schema["properties"]["plan_id"]["const"],
            "source_provision_ids": schema["properties"]["source_provision_ids"]["items"]["enum"],
            "conditions": [
                {"condition_id": cid, "result": "unknown"}
                for cid in conditions["condition_id"]["enum"]
            ],
            "explanation": "Synthetic unavailable conditions.",
        }


@pytest.mark.parametrize("stage", ["source_table", "source_evidence", "condition_prompt"])
def test_preparation_timeout_returns_incomplete_report_without_inference(
    legal_run, tmp_path, monkeypatch, stage
):
    service, registry, timeline, table = legal_run

    def timeout(*_args, **_kwargs):
        raise TimeoutError("Synthetic preparation deadline")

    if stage == "source_table":
        monkeypatch.setattr("forte.timeline.source_frame_table", timeout)
        table = None
    elif stage == "source_evidence":
        monkeypatch.setattr(EvidenceTools, "get_frames", timeout)
    else:
        monkeypatch.setattr(legal_reasoning, "build_condition_prompt", timeout)
    backend = SyntheticBackend()
    output = tmp_path / "legal"
    report = service.evaluate_timeline(
        timeline,
        registry,
        backend,
        output,
        time.monotonic() + 20,
        max_calls=1,
        table=table,
    )
    assert backend.calls == 0
    assert report["status"] == "incomplete" and report["assessments"] == []
    failed = report["rule_coverage"][0]
    assert failed["status"] == "evaluation_unavailable"
    assert failed["reason"] == "legal evidence preparation deadline exhausted"
    assert failed["stage"] == ("source_evidence" if stage == "source_table" else stage)
    assert len(report["rule_coverage"]) == 12
    assert report["metrics"]["calls"] == 0 and report["metrics"]["attempts"] == 1
    receipt = report["metrics"]["receipts"][0]
    assert receipt["error"] == "TimeoutError" and receipt["inference_attempted"] is False
    assert receipt["usage"] == {} and receipt["finish_reason"] is None
    assert timeline["observations"][0]["observation_id"] == "synthetic-observation"
    assert json.loads((output / "legal-assessments.json").read_text()) == report


def test_later_preparation_timeout_preserves_prior_validated_assessment(
    legal_run, tmp_path, monkeypatch
):
    service, registry, timeline, table = legal_run
    get_frames = EvidenceTools.get_frames
    preparations = 0

    def fail_second(tools, ids):
        nonlocal preparations
        preparations += 1
        if preparations == 2:
            raise TimeoutError("Synthetic later preparation deadline")
        return get_frames(tools, ids)

    monkeypatch.setattr(EvidenceTools, "get_frames", fail_second)
    backend = SyntheticBackend()
    report = service.evaluate_timeline(
        timeline,
        registry,
        backend,
        tmp_path / "legal",
        time.monotonic() + 20,
        max_calls=2,
        table=table,
    )
    assert backend.calls == 1
    assert len(report["assessments"]) == 1
    assert report["assessments"][0]["assessment"] == "insufficient_evidence"
    assert report["rule_coverage"][0]["status"] == "evaluated"
    assert report["rule_coverage"][1]["status"] == "evaluation_unavailable"
    assert report["metrics"]["calls"] == 1 and report["metrics"]["attempts"] == 2
    assert report["metrics"]["receipts"][1]["usage"] == {}


@pytest.mark.parametrize("invalid", ["source", "timestamp", "metadata"])
def test_invalid_ownership_or_metadata_still_fails_before_evidence_preparation(
    legal_run, tmp_path, monkeypatch, invalid
):
    service, registry, timeline, _table = legal_run
    metadata = []
    if invalid == "source":
        timeline["source_sha256"] = "0" * 64
    elif invalid == "timestamp":
        timeline["observations"][0]["start_sec"] += 1
    else:
        metadata = [
            {
                "id": "synthetic-metadata",
                "kind": "metadata",
                "source_id": "0" * 64,
                "origin": "authorized_metadata",
            }
        ]

    def unexpected_preparation(*_args, **_kwargs):
        pytest.fail("Invalid input must fail before evidence preparation")

    monkeypatch.setattr("forte.timeline.EvidenceTools", unexpected_preparation)
    backend = SyntheticBackend()
    with pytest.raises(ValueError):
        service.evaluate_timeline(
            timeline,
            registry,
            backend,
            tmp_path / "legal",
            time.monotonic() + 20,
            max_calls=1,
            metadata_evidence=metadata,
        )
    assert backend.calls == 0


def test_source_validation_failure_during_preparation_is_not_hidden(
    legal_run, tmp_path, monkeypatch
):
    service, registry, timeline, table = legal_run

    def invalid_source(*_args, **_kwargs):
        raise ValueError("Synthetic changed source")

    monkeypatch.setattr(EvidenceTools, "get_frames", invalid_source)
    backend = SyntheticBackend()
    with pytest.raises(ValueError, match="changed source"):
        service.evaluate_timeline(
            timeline,
            registry,
            backend,
            tmp_path / "legal",
            time.monotonic() + 20,
            max_calls=1,
            table=table,
        )
    assert backend.calls == 0
