"""Synthetic full orchestration against the actual pinned local legal corpus."""

import json
import time
from pathlib import Path

import pytest
from synthetic_decisions import UnknownDecisions
from test_video import make_mov

from forte.pipeline import analyze_reasoning, export_event_evidence, load_reasoning_config
from forte.settings import Settings


def test_frozen_orchestration_persists_source_evidence_conditions_and_revision(
    tmp_path, monkeypatch
):
    from forte import frozen_tracking

    monkeypatch.setattr(
        frozen_tracking, "require_outbound_blocked", lambda: {"synthetic_test": True}
    )
    repository = Path(__file__).resolve().parents[1]
    config = {
        "tracking": {"mode": "byte_track"},
        "legal": {
            "release": str(repository / "legal/2026-10-17"),
            "cards": str(repository / "legal/rule-cards.json"),
        },
        "bounds": {
            "max_calls": 8,
            "max_tokens": 80000,
            "max_reinspections": 1,
            "condition_max_questions": 12,
        },
    }
    settings = Settings("synthetic-key-long-enough", tmp_path, reasoning_config=config)

    def synthetic_tracks(registry, output, cfg, *, deadline):
        return {"source_sha256": registry.source_sha256, "participants": [], "frame_boxes": {}}

    class SyntheticVisualResponses:
        model = "explicit-synthetic-fixture"
        last_usage = {"total_tokens": 100}
        last_finish_reason = "stop"

        def ready(self):
            return True

        def request(self, registry, frames, instruction, schema, pixels, tokens):
            assert frames and registry.image_bytes(frames[0], pixels).startswith(b"\xff\xd8")
            ids = schema["$defs"]["Observation"]["properties"]["start_frame_id"]["enum"]
            return {
                "observations": [
                    {
                        "kind": "action",
                        "value": "Synthetic visible action.",
                        "start_frame_id": ids[0],
                        "end_frame_id": ids[-1],
                        "decisive_frame_id": ids[-1],
                        "actor_ids": [],
                        "recipient_ids": [],
                        "evidence_frame_ids": [ids[-1]],
                        "visibility": "visible_samples",
                        "uncertainty": ["Synthetic unresolved actor."],
                        "continues_before_window": False,
                        "continues_after_window": False,
                    }
                ],
                "visibility": "visible_samples",
                "unresolved_questions": [],
                "reinspection_requests": [],
                "capacity_limited": False,
            }

    path = make_mov(tmp_path / "synthetic.mov", rotation=90)
    result = analyze_reasoning(
        path,
        tmp_path / "runs",
        settings,
        decision_backend=UnknownDecisions(),
        backend=SyntheticVisualResponses(),
        tracking=synthetic_tracks,
    )
    revision = tmp_path / "runs" / result["artifacts"]["revision"]
    assert result["schema_version"] == "forte.reasoning/1"
    assert result["assessment"] == "insufficient_evidence"
    assert result["execution"]["status"] == "partial"
    assert result["execution"]["weights_frozen"] is True
    assert result["events"] and result["legal"]["assessments"]
    assert len(result["legal"]["rule_coverage"]) == 12
    frame = result["events"][0]["evidence"][0]
    target = revision / frame["file"]
    assert target.is_file() and frame["source_pts"] is not None and frame["time_base"]
    from PIL import Image

    with Image.open(target) as image:
        assert image.size == (64, 96)
    assert frame["image_sha256"] == __import__("hashlib").sha256(target.read_bytes()).hexdigest()
    assert (revision / "review.html").is_file()
    assert (
        json.loads((revision / "result.json").read_text())["source_sha256"]
        == result["source_sha256"]
    )
    assert (revision / result["source"]["frame_table"]).is_file()
    # Regression: the receipt formerly omitted the code that performs decoding,
    # appearance association, model validation and legal condition evaluation.
    hashes = result["provenance"]["source_code"]
    required = {
        "pipeline",
        "timeline",
        "video",
        "inference",
        "model_profile",
        "frozen_tracking",
        "person_proposals",
        "tracking",
        "legal_reasoning",
        "legal",
        "annotations",
        "contracts",
        "contracts_v2",
        "settings",
        "jobs",
        "worker",
        "api",
        "manifest",
    }
    assert required <= hashes.keys()
    from forte import inference

    assert (
        hashes["inference"]
        == __import__("hashlib").sha256(Path(inference.__file__).read_bytes()).hexdigest()
    )
    assert result["provenance"]["source_code_scope"] == "shipped_application_sources"
    assert json.loads((revision / "result.json").read_text())["provenance"]["source_code"] == hashes


def test_frozen_config_never_accepts_adapter_or_unbounded_calls(tmp_path):
    settings = Settings("synthetic-key-long-enough", tmp_path)
    with pytest.raises(ValueError, match="explicit"):
        load_reasoning_config(settings)
    settings.reasoning_config = {"tracking": {}, "legal": {}, "model": {"adapter_path": "/adapter"}}
    with pytest.raises(ValueError, match="adapters"):
        load_reasoning_config(settings)
    settings.reasoning_config = {"tracking": {}, "legal": {}, "bounds": {"max_calls": 100000}}
    with pytest.raises(ValueError, match="budget"):
        load_reasoning_config(settings)


def test_expired_evidence_export_retains_source_pointers_without_fake_jpegs(tmp_path):
    from forte.timeline import source_frame_table
    from forte.video import decode_video

    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")
    table = source_frame_table(registry, time.monotonic() + 10)
    event = {
        "event_id": "event-00000",
        "decisive_frame_id": registry.frames[0].frame_id,
        "evidence_frame_ids": [registry.frames[0].frame_id],
    }
    events, limited = export_event_evidence(
        registry, {"events": [event]}, tmp_path, time.monotonic() - 1, table
    )
    assert limited is True
    assert events[0]["evidence"] == []
    assert events[0]["evidence_export_complete"] is False
    assert events[0]["assessment"] == "insufficient_evidence"
