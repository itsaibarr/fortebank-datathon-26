"""Actual synthetic MOV/PTS/JPEG exports and real offline legal adjudication.

The temporary cards are explicitly synthetic approvals for test logic only. The
repository's real draft cards and original model output are never changed.
"""

import copy
import hashlib
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import jsonschema
import pytest
from test_video import make_mov

from forte.jury_projection import project_reasoning_to_v1
from forte.legal_reasoning import LegalEvidenceService
from forte.pipeline import export_event_evidence, load_reasoning_config
from forte.settings import Settings
from forte.timeline import merge_observations, source_frame_table, write_private
from forte.video import decode_video, make_windows

ROOT = Path(__file__).resolve().parents[1]


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _persist(fixture):
    write_private(fixture.revision / "result.json", fixture.report)
    write_private(fixture.revision / "scan/timeline.json", fixture.report["timeline"])
    write_private(fixture.revision / "legal-assessments.json", fixture.report["legal"])


def _fixture(
    tmp_path,
    *,
    state="satisfied",
    complete=False,
    draft=False,
    known_date=True,
    cards=1,
    max_calls=None,
    role=False,
    people=1,
    condition_key="action_visible",
    metadata=False,
    extra_unbound_support=False,
):
    directory = tmp_path / "job"
    directory.mkdir()
    source = make_mov(directory / "input.mov")
    registry = decode_video(source, tmp_path / "sampled")
    table = source_frame_table(registry, time.monotonic() + 30)
    revision = directory / ("reasoning-" + uuid4().hex)
    (revision / "scan").mkdir(parents=True)
    (revision / "legal").mkdir()
    (directory / "immutable").mkdir()
    original = json.loads((ROOT / "legal/rule-cards.json").read_text())[0]
    public_id = original["clause_ids"][0]
    act_id, version_id, _ = public_id.split(":")
    synthetic_cards = [
        {
            "id": f"synthetic_rule_{index}",
            "clause_ids": [public_id],
            "scope": "Synthetic test condition; no semantic or legal acceptance.",
            "actor_role": "unclear",
            "prerequisites": {condition_key: "The synthetic fixture condition is established."},
            "exceptions": {},
            "visual_limits": ["Synthetic logic fixture, not a reviewed production rule."],
            "review_status": "draft" if draft else "approved",
            "reviewer": None if draft else "explicit-synthetic-test-reviewer",
        }
        for index in range(cards)
    ]
    card_file = tmp_path / "synthetic-cards.json"
    write_private(card_file, synthetic_cards)
    config = {
        "tracking": {},
        "legal": {
            "release": str(ROOT / "legal/2026-10-17"),
            "cards": str(card_file),
            "event_date": "2026-10-18" if known_date else None,
            "operation_context": {"date_source": "human_review"},
            "applicability": [
                {
                    "act_id": act_id,
                    "version_id": version_id,
                    "effective_from": "2026-01-01",
                    "authority_provision_ids": [public_id],
                    "reviewer": "explicit-synthetic-applicability-test",
                }
            ],
            "metadata_evidence": [
                {
                    "id": "synthetic-metadata",
                    "kind": "metadata",
                    "source_id": registry.source_sha256,
                    "participant_ids": ["p0"],
                    "origin": "authorized_metadata",
                    "value": "Explicit synthetic operation metadata fixture.",
                }
            ]
            if metadata
            else [],
        },
    }
    settings = Settings("synthetic-test-key-long-enough", directory, reasoning_config=config)
    config = load_reasoning_config(settings)
    config_path = directory / "immutable/request-config.json"
    write_private(config_path, config)
    config_path.chmod(0o400)
    settings.reasoning_config = config_path
    write_private(revision / "configuration.json", config)
    write_private(revision / "source-frames.json", table)
    participants = [
        {
            "participant_id": f"p{index}",
            "identity_status": "model_proposal",
            "track_segments": [],
            "role_hypotheses": [],
            "conflicts": [],
            "visibility_gaps": [],
        }
        for index in range(people)
    ]
    observations = []
    for index in range(people):
        observations.append(
            {
                "observation_id": f"obs-{index}",
                "kind": "action",
                "value": f"Synthetic participant {index} performs a visible test action.",
                "actor_ids": [f"p{index}"],
                "recipient_ids": [],
                "start_frame_id": registry.frames[0].frame_id,
                "end_frame_id": registry.frames[-1].frame_id,
                "decisive_frame_id": registry.frames[2].frame_id,
                "evidence_frame_ids": [registry.frames[i].frame_id for i in (0, 2, 4)],
                "start_sec": registry.frames[0].timestamp_sec,
                "end_sec": registry.frames[-1].timestamp_sec,
                "decisive_sec": registry.frames[2].timestamp_sec,
                "visibility": "visible_samples",
                "uncertainty": [],
                "continues_before_window": False,
                "continues_after_window": False,
                "source_sha256": registry.source_sha256,
                "origin": "model",
                "review_status": "unreviewed",
            }
        )
    if role:
        role_observation = copy.deepcopy(observations[0])
        role_observation.update(
            observation_id="obs-role",
            kind="role",
            value="Synthetic interval-scoped role proposal.",
        )
        observations.append(role_observation)
    if extra_unbound_support:
        additional = copy.deepcopy(observations[0])
        frame = registry.frames[1]
        additional.update(
            observation_id="obs-unbound-context",
            kind="context",
            start_frame_id=frame.frame_id,
            end_frame_id=frame.frame_id,
            decisive_frame_id=frame.frame_id,
            evidence_frame_ids=[frame.frame_id],
            start_sec=frame.timestamp_sec,
            end_sec=frame.timestamp_sec,
            decisive_sec=frame.timestamp_sec,
        )
        observations.append(additional)
    windows = [
        {
            "phase": phase,
            "start_sec": start,
            "end_sec": end,
            "source_frame_ids": [f.frame_id for f in registry.frames],
            "visibility": "visible_samples",
            "capacity_limited": False,
        }
        for phase, start, end in (
            [("window", start, end) for start, end in make_windows(registry.duration, 16, 12)]
        )
    ]
    scheduled = [list(interval) for interval in make_windows(registry.duration, 16, 12)]
    timeline = {
        "schema_version": "forte.timeline/1",
        "source_sha256": registry.source_sha256,
        "duration_sec": registry.duration,
        "status": "complete_schedule" if complete else "budget_exhausted",
        "observations": observations,
        "events": merge_observations(observations),
        "participants": participants,
        "role_conflicts": [],
        "unresolved_questions": [],
        "coverage": {
            "scheduled_intervals": scheduled,
            "examined_intervals": scheduled,
            "unexamined_intervals": [] if complete else [[0, registry.duration]],
            "unclear_intervals": [],
            "pending_reinspections": 0,
            "output_capacity_limited_intervals": [],
            "continuous_visibility_validated": False,
            "sampling_does_not_establish_absence": True,
            "windows": windows,
        },
    }
    law = config["legal"]
    service = LegalEvidenceService(
        Path(law["release"]), card_file, applicability=law["applicability"]
    )
    calls = []

    class SyntheticConditions:
        def propose(self, packet, questions, *, deadline):
            index = len(calls)
            calls.append(index)
            return {
                key: {
                    "choice": state,
                    "probabilities": {
                        label: float(label == state)
                        for label in ("satisfied", "contradicted", "unknown")
                    },
                }
                for key in questions
            }

    legal = service.evaluate_timeline(
        timeline,
        registry,
        SyntheticConditions(),
        revision / "legal",
        time.monotonic() + 30,
        event_date=law.get("event_date"),
        operation_context=law["operation_context"],
        max_calls=cards * people if max_calls is None else max_calls,
        table=table,
        metadata_evidence=law["metadata_evidence"],
    )
    events, _ = export_event_evidence(registry, timeline, revision, time.monotonic() + 30, table)
    for event in events:
        linked = [
            a
            for a in legal["assessments"]
            if set(a["observation_ids"]) & set(event["observation_ids"])
        ]
        event["legal_assessment_ids"] = [a["assessment_id"] for a in linked]
        event["legal_assessments"] = linked
        if any(a["assessment"] == "supported_violation" for a in linked):
            event["assessment"] = "supported_violation"
    report = {
        "schema_version": "forte.reasoning/1",
        "source_sha256": registry.source_sha256,
        "source": {
            "duration_sec": registry.duration,
            "frame_count": len(registry.frames),
            "frame_table": "source-frames.json",
        },
        "execution": {
            "status": "completed" if complete else "partial",
            "budget_exhausted": not complete,
            "weights_frozen": True,
        },
        "assessment": "supported_violation" if state == "satisfied" else "no_violation_observed",
        "timeline": timeline,
        "participants": {
            "source_sha256": registry.source_sha256,
            "participants": participants,
            "unresolved_matches": [],
        },
        "legal": legal,
        "events": events,
        "provenance": {"config_sha256": _hash(revision / "configuration.json")},
        "artifacts": {"revision": revision.name},
    }
    fixture = SimpleNamespace(
        directory=directory,
        revision=revision,
        registry=registry,
        report=report,
        settings=settings,
        job_id=uuid4(),
        calls=calls,
    )
    _persist(fixture)
    return fixture


def _project(fixture, **kwargs):
    return project_reasoning_to_v1(
        fixture.job_id, fixture.report, fixture.directory, fixture.settings, **kwargs
    )


def test_supported_positive_survives_unrelated_partial_rule_coverage(tmp_path):
    fixture = _fixture(tmp_path, cards=2, max_calls=1)
    before = {path: _hash(path) for path in fixture.revision.rglob("*") if path.is_file()}
    result = _project(fixture)
    assert result.verdict == "violation" and len(result.violations) == 1
    assert "Other work is incomplete" in result.violations[0].description
    assert "Unreviewed model proposal" in result.violations[0].description
    assert "https://adilet.zan.kz/" in result.violations[0].description
    assert result.violations[0].timecode_sec == pytest.approx(1.1)
    assert [e.timestamp_sec for e in result.violations[0].evidence_frames] == pytest.approx(
        [0, 1.1, 3]
    )
    assert fixture.calls == [0]
    assert before == {path: _hash(path) for path in before}
    receipt = json.loads((fixture.directory / "jury-v1-projection.json").read_text())
    assert receipt["assessment_ids"] == ["assessment-00000"]
    assert not receipt["coverage"]["clearance_supported"]
    assert "image_base64" not in json.dumps(receipt)


def test_supported_assessment_role_and_action_event_links_do_not_duplicate(tmp_path):
    fixture = _fixture(tmp_path, role=True)
    assert sum(e["assessment"] == "supported_violation" for e in fixture.report["events"]) == 2
    result = _project(fixture)
    assert len(result.violations) == 1
    assert "performs a visible test action" in result.violations[0].description


def test_multiple_independent_people_and_findings_are_preserved(tmp_path):
    fixture = _fixture(tmp_path, people=2, cards=2)
    result = _project(fixture)
    assert len(result.violations) == 4
    assert {v.type for v in result.violations} == {"synthetic_rule_0", "synthetic_rule_1"}
    assert "participant 0" in result.violations[0].description
    assert "participant 1" in result.violations[1].description


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "unknown"},
        {"state": "contradicted"},
        {"state": "contradicted", "complete": True, "draft": True},
        {"state": "contradicted", "complete": True, "known_date": False},
    ],
)
def test_insufficient_partial_draft_and_unknown_dates_cannot_be_clean(tmp_path, changes):
    fixture = _fixture(tmp_path, **changes)
    with pytest.raises(ValueError, match="^insufficient_evidence$"):
        _project(fixture)
    receipt = json.loads((fixture.directory / "jury-v1-projection.json").read_text())
    assert receipt["status"] == "failed"


def test_complete_approved_known_date_single_subject_negative(tmp_path):
    fixture = _fixture(tmp_path, state="contradicted", complete=True)
    result = _project(fixture)
    assert result.verdict == "no_violation" and result.violations == []
    assert fixture.report["legal"]["validated_legal_conclusion"] is False


def test_not_applicable_alone_cannot_be_clearance(tmp_path):
    fixture = _fixture(
        tmp_path,
        state="contradicted",
        complete=True,
        condition_key="institution_in_scope",
        metadata=True,
    )
    assert fixture.report["legal"]["assessments"][0]["assessment"] == "not_applicable"
    with pytest.raises(ValueError, match="^insufficient_evidence$"):
        _project(fixture)


def test_sparse_frame_evidence_never_gains_complete_opportunity_in_replay(tmp_path):
    fixture = _fixture(tmp_path, complete=True, condition_key="count_omitted")
    record = fixture.report["legal"]["assessments"][0]
    assert record["assessment"] == "insufficient_evidence"
    assert record["conditions"][0]["result"] == "unknown"
    with pytest.raises(ValueError, match="^insufficient_evidence$"):
        _project(fixture)


def test_complete_schedule_does_not_clear_uncited_action_episode(tmp_path):
    fixture = _fixture(tmp_path, state="contradicted", complete=True)
    additional = copy.deepcopy(fixture.report["timeline"]["observations"][0])
    additional["observation_id"] = "obs-another-episode"
    fixture.report["timeline"]["observations"].append(additional)
    _persist(fixture)
    with pytest.raises(ValueError, match="^insufficient_evidence$"):
        _project(fixture)


def test_context_duty_keeps_its_own_source_anchor(tmp_path):
    fixture = _fixture(tmp_path)
    fixture.report["timeline"]["observations"][0]["kind"] = "context"
    _persist(fixture)
    result = _project(fixture)
    assert len(result.violations) == 1


def test_extra_condition_frames_without_bound_observation_cannot_disappear(tmp_path):
    fixture = _fixture(tmp_path, extra_unbound_support=True)
    assessment = fixture.report["legal"]["assessments"][0]
    assert assessment["assessment"] == "supported_violation"
    assert fixture.registry.frames[1].frame_id in assessment["evidence_frame_ids"]
    assert "obs-unbound-context" in assessment["observation_ids"]
    # Four required source frames exceed the three-JPEG contract.
    with pytest.raises(ValueError, match="^insufficient_evidence$"):
        _project(fixture)


def test_duplicate_legal_assessment_is_integrity_failure(tmp_path):
    fixture = _fixture(tmp_path)
    duplicate = copy.deepcopy(fixture.report["legal"]["assessments"][0])
    duplicate["assessment_id"] = "assessment-duplicate"
    fixture.report["legal"]["assessments"].append(duplicate)
    _persist(fixture)
    with pytest.raises(ValueError, match="^Invalid reasoning projection provenance$"):
        _project(fixture)


@pytest.mark.parametrize(
    "blocker",
    [
        "second_subject",
        "unclear",
        "pending",
        "capacity",
        "missing_window",
        "role_conflict",
        "identity_gap",
        "question",
        "missing_rule",
    ],
)
def test_clearance_needs_every_subject_and_actual_complete_schedule(tmp_path, blocker):
    fixture = _fixture(
        tmp_path,
        state="contradicted",
        complete=True,
        people=2 if blocker == "second_subject" else 1,
    )
    timeline = fixture.report["timeline"]
    if blocker == "unclear":
        timeline["coverage"]["unclear_intervals"] = [[0, 1]]
    elif blocker == "pending":
        timeline["coverage"]["pending_reinspections"] = 1
    elif blocker == "capacity":
        timeline["coverage"]["windows"][0]["capacity_limited"] = True
    elif blocker == "missing_window":
        timeline["coverage"]["windows"].pop()
    elif blocker == "role_conflict":
        timeline["role_conflicts"] = [{"status": "unresolved"}]
    elif blocker == "identity_gap":
        fixture.report["participants"]["participants"][0]["visibility_gaps"] = [
            {"state": "unobserved"}
        ]
    elif blocker == "question":
        timeline["unresolved_questions"] = ["Synthetic unresolved question"]
    elif blocker == "missing_rule":
        fixture.report["legal"]["rule_coverage"] = []
    _persist(fixture)
    with pytest.raises(ValueError, match="^insufficient_evidence$"):
        _project(fixture)


@pytest.mark.parametrize(
    "tamper",
    [
        "jpeg",
        "input",
        "cross_source",
        "source_pts",
        "condition",
        "citation",
        "config",
        "saved_result",
    ],
)
def test_tampered_source_evidence_conditions_and_provenance_fail_closed(tmp_path, tamper):
    fixture = _fixture(tmp_path)
    if tamper == "jpeg":
        path = next((fixture.revision / "evidence").glob("*.jpg"))
        path.write_bytes(path.read_bytes() + b"tampered")
    elif tamper == "input":
        path = fixture.directory / "input.mov"
        path.write_bytes(path.read_bytes() + b"tampered")
    elif tamper == "cross_source":
        path = fixture.revision / "evidence-association.json"
        values = json.loads(path.read_text())
        values[0]["source_sha256"] = "0" * 64
        write_private(path, values)
    elif tamper == "source_pts":
        path = fixture.revision / "source-frames.json"
        values = json.loads(path.read_text())
        values["frames"][1]["source_pts"] += 1
        write_private(path, values)
    elif tamper == "condition":
        fixture.report["legal"]["assessments"][0]["conditions"][0]["result"] = "contradicted"
        _persist(fixture)
    elif tamper == "citation":
        fixture.report["legal"]["assessments"][0]["citations"][0]["url"] = (
            "https://untrusted.invalid/"
        )
        _persist(fixture)
    elif tamper == "config":
        values = json.loads(fixture.settings.reasoning_config.read_text())
        values["bounds"]["max_calls"] -= 1
        write_private(fixture.settings.reasoning_config, values)
    elif tamper == "saved_result":
        fixture.report["execution"]["status"] = "completed"
    with pytest.raises(ValueError, match="^Invalid reasoning projection provenance$"):
        _project(fixture)


@pytest.mark.parametrize("target", ["jpeg", "revision", "input", "receipt"])
def test_symlink_artifacts_are_never_followed(tmp_path, target):
    fixture = _fixture(tmp_path)
    if target == "jpeg":
        path = next((fixture.revision / "evidence").glob("*.jpg"))
    elif target == "revision":
        path = fixture.revision
    elif target == "input":
        path = fixture.directory / "input.mov"
    else:
        path = fixture.directory / "jury-v1-projection.json"
        path.write_text("{}")
    destination = tmp_path / ("outside-" + target)
    path.rename(destination)
    path.symlink_to(destination, target_is_directory=destination.is_dir())
    with pytest.raises(ValueError, match="^Invalid reasoning projection provenance$"):
        _project(fixture)


@pytest.mark.parametrize("target", ["input", "config", "result", "jpeg"])
def test_fifo_artifacts_cannot_block_before_type_or_deadline_check(tmp_path, target):
    fixture = _fixture(tmp_path)
    report_path = tmp_path / "subprocess-report.json"
    write_private(report_path, fixture.report)
    paths = {
        "input": fixture.directory / "input.mov",
        "config": fixture.settings.reasoning_config,
        "result": fixture.revision / "result.json",
        "jpeg": next((fixture.revision / "evidence").glob("*.jpg")),
    }
    path = paths[target]
    path.unlink()
    os.mkfifo(path, 0o600)
    script = """
import json, sys, time
from pathlib import Path
from uuid import UUID
from forte.jury_projection import project_reasoning_to_v1
from forte.settings import Settings
directory, config, source, identifier = sys.argv[1:]
settings = Settings('synthetic-subprocess-key', Path(directory), reasoning_config=Path(config))
report = json.loads(Path(source).read_text())
try:
    project_reasoning_to_v1(UUID(identifier), report, Path(directory), settings,
                           deadline=time.monotonic() + 0.5)
except ValueError as exc:
    assert str(exc) == 'Invalid reasoning projection provenance'
else:
    raise AssertionError('FIFO was accepted')
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(fixture.directory),
            str(fixture.settings.reasoning_config),
            str(report_path),
            str(fixture.job_id),
        ],
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode()


def test_top_level_positive_label_cannot_approve_itself(tmp_path):
    fixture = _fixture(tmp_path, state="unknown")
    fixture.report["assessment"] = "supported_violation"
    _persist(fixture)
    with pytest.raises(ValueError, match="^insufficient_evidence$"):
        _project(fixture)


def test_projection_matches_unchanged_normative_contract(tmp_path):
    fixture = _fixture(tmp_path)
    path = ROOT / "contracts/api-contract.json"
    assert _hash(path) == "2f07ca38a89320a97edc1f18cf1401462ce89f6912698245bac4f67bd3cacc05"
    contract = json.loads(path.read_text())
    schema = {"$ref": "#/components/schemas/DoneJob", "components": contract["components"]}
    jsonschema.validate(_project(fixture).model_dump(mode="json"), schema)


def test_projection_deadline_does_not_start_another_inference(tmp_path):
    fixture = _fixture(tmp_path)
    with pytest.raises(TimeoutError, match="Projection deadline exhausted"):
        _project(fixture, deadline=time.monotonic() - 1)
    assert fixture.calls == [0]
    assert not (fixture.directory / "jury-v1-projection.json").exists()


def test_deadline_is_checked_during_bounded_artifact_reads(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    ticks = itertools.count()
    monkeypatch.setattr("forte.jury_projection.time.monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError, match="Projection deadline exhausted"):
        _project(fixture, deadline=3)
    assert fixture.calls == [0]
