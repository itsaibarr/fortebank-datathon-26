"""Synthetic legal preparation failures must preserve useful partial execution."""

import time
from pathlib import Path

import pytest
from test_video import make_mov

from forte.legal_reasoning import LegalEvidenceService
from forte.timeline import source_frame_table
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
                "kind": "context",
                "uncertainty": [],
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
