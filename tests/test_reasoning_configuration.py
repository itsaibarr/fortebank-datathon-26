"""Trusted legal configuration reaches the real pipeline without inferred facts."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from test_video import make_mov

from forte.reasoning_pipeline import analyze_reasoning, load_reasoning_config
from forte.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def config():
    return {
        "tracking": {"mode": "byte_track"},
        "legal": {
            "release": str(ROOT / "legal/2026-10-17"),
            "cards": str(ROOT / "legal/rule-cards.json"),
        },
    }


def metadata(source):
    return {
        "id": "synthetic-operation-metadata",
        "kind": "metadata",
        "source_id": source,
        "origin": "authorized_metadata",
        "value": "Synthetic operator-supplied context, not a reviewed legal finding.",
    }


class ReadyBackend:
    model = "explicit-synthetic-fixture"

    def ready(self):
        return True


@pytest.mark.parametrize(
    "change",
    [
        {"origin": "model"},
        {"kind": "observation"},
    ],
)
def test_config_rejects_machine_or_visual_metadata(tmp_path, change):
    cfg = config()
    cfg["legal"]["metadata_evidence"] = [{**metadata("a" * 64), **change}]
    with pytest.raises(ValueError, match="authorized evidence"):
        load_reasoning_config(Settings("synthetic-key-long-enough", tmp_path, reasoning_config=cfg))


def test_config_rejects_duplicate_evidence_and_misspelled_bindings(tmp_path):
    cfg = config()
    cfg["legal"]["metadata_evidence"] = [metadata("a" * 64)] * 2
    settings = Settings("synthetic-key-long-enough", tmp_path, reasoning_config=cfg)
    with pytest.raises(ValueError, match="unique authorized"):
        load_reasoning_config(settings)
    cfg["legal"] = {"metadata_evidences": []}
    with pytest.raises(ValueError, match="Unknown legal"):
        load_reasoning_config(settings)


def test_foreign_metadata_fails_before_tracking_or_private_model_call(tmp_path, monkeypatch):
    from forte import frozen_tracking

    monkeypatch.setattr(frozen_tracking, "require_outbound_blocked", lambda: {"synthetic": True})
    cfg = config()
    cfg["legal"]["metadata_evidence"] = [metadata("a" * 64)]
    settings = Settings("synthetic-key-long-enough", tmp_path, reasoning_config=cfg)

    def forbidden(*args, **kwargs):
        pytest.fail("Foreign metadata must fail before tracking")

    with pytest.raises(ValueError, match="another source recording"):
        analyze_reasoning(
            make_mov(tmp_path / "synthetic.mov"),
            tmp_path / "run",
            settings,
            backend=ReadyBackend(),
            tracking=forbidden,
        )


def test_pipeline_forwards_explicit_bindings_and_preserves_unknown_result(tmp_path, monkeypatch):
    from forte import frozen_tracking, legal_reasoning, reasoning_pipeline

    monkeypatch.setattr(frozen_tracking, "require_outbound_blocked", lambda: {"synthetic": True})
    source = make_mov(tmp_path / "synthetic.mov")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cfg = config()
    real_service = legal_reasoning.LegalEvidenceService
    law = real_service(Path(cfg["legal"]["release"]), Path(cfg["legal"]["cards"]))
    clause = next(iter(law._clauses.values()))
    cfg["legal"].update(
        event_date="2026-10-18",
        operation_context={"date_source": "authorized_operation_metadata"},
        applicability=[
            {
                "act_id": clause.act_id,
                "version_id": clause.version_id,
                "effective_from": "2026-01-01",
                "authority_provision_ids": [clause.id],
                "reviewer": "synthetic-fixture-only",
            }
        ],
        metadata_evidence=[metadata(digest)],
    )
    before = copy.deepcopy(cfg)
    seen = {}

    def tracks(registry, *args, **kwargs):
        return {"source_sha256": registry.source_sha256, "participants": [], "frame_boxes": {}}

    def timeline(registry, *args, **kwargs):
        return {
            "source_sha256": registry.source_sha256,
            "participants": [],
            "events": [],
            "observations": [],
            "status": "budget_exhausted",
            "metrics": {},
            "coverage": {"unexamined_intervals": [[0, registry.duration]]},
        }

    class CaptureService:
        def __init__(self, release, cards, *, applicability):
            seen["bindings"] = applicability
            self.actual = real_service(release, cards, applicability=applicability)

        def evaluate_timeline(self, timeline, registry, backend, output, deadline, **kwargs):
            seen.update(kwargs)
            assert self.actual._applicability
            return {"status": "incomplete_scoped_schedule", "assessments": [], "metrics": {}}

    monkeypatch.setattr(legal_reasoning, "LegalEvidenceService", CaptureService)
    monkeypatch.setattr(reasoning_pipeline, "scan_recording", timeline)
    result = analyze_reasoning(
        source,
        tmp_path / "run",
        Settings("synthetic-key-long-enough", tmp_path, reasoning_config=cfg),
        backend=ReadyBackend(),
        tracking=tracks,
    )
    assert seen["bindings"] == [
        legal_reasoning.VersionApplicability.model_validate(binding).model_dump(mode="json")
        for binding in cfg["legal"]["applicability"]
    ]
    assert seen["metadata_evidence"][0]["source_id"] == digest
    assert seen["metadata_evidence"][0]["origin"] == "authorized_metadata"
    assert seen["event_date"] == "2026-10-18"
    assert cfg == before
    assert result["assessment"] == "insufficient_evidence"
    assert result["execution"]["status"] == "partial"
    saved = json.loads(
        (tmp_path / "run" / result["artifacts"]["revision"] / "configuration.json").read_bytes()
    )
    assert saved["legal"]["metadata_evidence"] == seen["metadata_evidence"]
