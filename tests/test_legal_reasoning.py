import copy
import time
from datetime import date
from pathlib import Path

import pytest
from test_video import make_mov

from forte.legal_reasoning import (
    ConditionCandidate,
    ConditionPlan,
    EvidenceItem,
    LegalEvidenceService,
    bounded_observation_evidence,
    build_condition_prompt,
    evaluate_candidate,
    fingerprint,
    require_official_act,
)
from forte.video import decode_video

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def service():
    return LegalEvidenceService(ROOT / "legal/2026-10-17", ROOT / "legal/rule-cards.json")


def plan(*, draft=False, version="applicable", polarity="contradicted", category="action"):
    data = {
        "rule_id": "synthetic_obligation",
        "snapshot_sha256": "0" * 64,
        "source_provision_ids": ["synthetic-act:version:1"],
        "conditions": [
            {
                "id": "obligation_performed",
                "proposition": "The required action was performed.",
                "category": category,
                "violation_when": polarity,
                "requires_metadata": False,
                "requires_complete_opportunity": False,
            }
        ],
        "interpretation_status": "draft" if draft else "approved",
        "interpretation_reviewer": None if draft else "synthetic-reviewer",
        "version_applicability": version,
        "limitations": [],
    }
    return ConditionPlan.model_validate({**data, "plan_id": fingerprint(data)})


def candidate(p, state="satisfied", *, support=None, counter=None):
    return {
        "plan_id": p.plan_id,
        "source_provision_ids": p.source_provision_ids,
        "participant_ids": ["person-1"],
        "conditions": [
            {
                "condition_id": "obligation_performed",
                "result": state,
                "participant_ids": ["person-1"],
                "supporting_evidence_ids": ["f1"] if support is None else support,
                "contradictory_evidence_ids": [] if counter is None else counter,
                "unresolved_dependencies": [],
            }
        ],
        "explanation": "Synthetic condition proposal, not a semantic benchmark.",
    }


def evidence(**changes):
    return EvidenceItem.model_validate(
        {
            "id": "f1",
            "kind": "frame",
            "source_id": "synthetic-recording",
            "participant_ids": ["person-1"],
            "frame_ids": ["f1"],
            **changes,
        }
    )


def observation_evidence(**changes):
    return evidence(**{"id": "o1", "kind": "observation", "actor_ids": ["person-1"], **changes})


@pytest.mark.parametrize(
    "url,kind,redirects",
    [
        ("https://adilet.zan.kz.evil.example/rus/docs/V1900019680", "enacted_act", []),
        ("https://nationalbank.kz/news/example", "news", []),
        ("https://nationalbank.kz/draft/example", "draft", []),
        (
            "https://adilet.zan.kz/rus/docs/V1900019680",
            "enacted_act",
            ["https://unverified.example/x"],
        ),
        ("http://adilet.zan.kz/rus/docs/V1900019680", "enacted_act", []),
        ("https://api.nationalbank.kz/act", "enacted_act", []),
    ],
)
def test_official_hostname_alone_never_establishes_authority(url, kind, redirects):
    with pytest.raises(ValueError):
        require_official_act(url, kind, redirects=redirects)


def test_verified_release_audit_and_exact_source_context_preserve_suspension(service):
    audit = service.audit()
    assert audit["main_clause_records"] == 272
    assert audit["non_repealed_clause_records"] == 266
    assert audit["draft_rule_cards"] == 12 and audit["approved_rule_cards"] == 0
    assert len(audit["sources"]) == 3
    source = next(s for s in audit["sources"] if s["act_id"] == "V2000020075")
    item = service.get_source_provision(source["act_id"], source["version_id"], "16")
    assert "закрывающейся на замок дверью" in item["clause"]["text"]
    # The legacy numbered-clause parser omits these <font> notices. The source
    # context restores them from the hash-verified raw HTML without changing it.
    notices = item["source_effect_notices"]
    assert any("пункта 16" in n["text"] and "01.01.2027" in n["text"] for n in notices)
    assert any("V2400035552" in r for n in notices for r in n["references"])
    assert item["snapshot_sha256"] == service.snapshot_sha256
    assert item["parent_headings"] and item["context_provisions"]
    with pytest.raises(ValueError, match="pinned"):
        service.get_source_provision(source["act_id"], "invented-version", "16")


def test_unknown_dates_do_not_become_applicable_from_current_flag_or_pts(service):
    hits = service.retrieve_applicable_rules("пункт 22", {"act_ids": ["V1900019680"]})
    assert hits and all(h["date_applicability"] == "unknown" for h in hits)
    assert len(hits) == 1 and hits[0]["clause"]["provision"] == "22"
    assert service.retrieve_applicable_rules("syntheticunrelatedword") == []
    with pytest.raises(ValueError, match="calendar date"):
        service.retrieve_applicable_rules("пункт 22", event_date="2026-10-18")
    hits = service.retrieve_applicable_rules(
        "пункт 22", {"date_source": "recording_metadata"}, "2026-10-18"
    )
    assert hits[0]["date_applicability"] == "unknown"
    with pytest.raises(ValueError, match="unavailable acts"):
        service.retrieve_applicable_rules("пункт 22", {"act_ids": ["made-up-act"]})


def test_reviewed_effective_intervals_filter_dates_without_reusing_revision_semantics(service):
    source = service.audit()["sources"][0]
    id = f"{source['act_id']}:{source['version_id']}:2"
    reviewed = LegalEvidenceService(
        ROOT / "legal/2026-10-17",
        ROOT / "legal/rule-cards.json",
        applicability=[
            {
                "act_id": source["act_id"],
                "version_id": source["version_id"],
                "effective_from": date(2026, 8, 1),
                "effective_until": date(2026, 9, 1),
                "authority_provision_ids": [id],
                "reviewer": "synthetic-reviewer",
            }
        ],
    )
    context = {"act_ids": [source["act_id"]], "date_source": "human_review"}
    assert (
        reviewed.retrieve_applicable_rules("пункт 22", context, "2026-08-02")[0][
            "date_applicability"
        ]
        == "applicable"
    )
    assert reviewed.retrieve_applicable_rules("пункт 22", context, "2026-09-01") == []


def test_performing_an_obligation_defeats_violation_instead_of_satisfying_it():
    p = plan()
    result = evaluate_candidate(p, candidate(p), [evidence()], ["person-1"])
    assert result.assessment == "no_violation_observed"
    result = evaluate_candidate(
        p,
        candidate(p, "contradicted", support=[], counter=["f1", "o1"]),
        [evidence(), observation_evidence()],
        ["person-1"],
    )
    assert result.assessment == "supported_violation"
    assert not result.validated_legal_conclusion and result.review_status == "unreviewed"
    assert result.bound_observation_ids == ["o1"]


def test_frame_only_positive_and_wrong_actor_observation_cannot_bind_an_event():
    p = plan(polarity="satisfied", category="scope")
    result = evaluate_candidate(p, candidate(p), [evidence()], ["person-1"])
    assert result.candidate_assessment == "supported_violation"
    assert result.assessment == "insufficient_evidence"
    assert not result.bound_observation_ids and result.unresolved_dependencies
    assert result.conditions[0].result == "satisfied"
    wrong_actor = observation_evidence(
        id="o2", actor_ids=["person-2"], participant_ids=["person-2"]
    )
    result = evaluate_candidate(
        p, candidate(p, support=["f1", "o2"]), [evidence(), wrong_actor], ["person-1", "person-2"]
    )
    assert result.assessment == "insufficient_evidence" and not result.bound_observation_ids
    with pytest.raises(ValueError, match="source-frame"):
        evaluate_candidate(
            p,
            candidate(p, support=["o1"]),
            [observation_evidence(frame_ids=["invented-frame"])],
            ["person-1"],
        )


def test_draft_interpretation_cannot_promote_a_proposal_to_validated_violation():
    p = plan(draft=True)
    result = evaluate_candidate(
        p, candidate(p, "contradicted", support=[], counter=["f1"]), [evidence()], ["person-1"]
    )
    assert result.candidate_assessment == "supported_violation"
    assert result.assessment == "insufficient_evidence"
    assert any("Draft interpretation" in text for text in result.limitations)
    proposed = candidate(p)
    proposed["review_status"] = "approved"
    with pytest.raises(ValueError):
        ConditionCandidate.model_validate(proposed)


def test_condition_allowlists_reject_invented_sources_actors_frames_and_incomplete_tables():
    p = plan()
    for mutate in [
        lambda c: c.update(source_provision_ids=["invented-act:version:1"]),
        lambda c: c.update(participant_ids=["invented-person"]),
        lambda c: c["conditions"][0].update(supporting_evidence_ids=["invented-frame"]),
        lambda c: c.update(conditions=[]),
        lambda c: c["conditions"].append(copy.deepcopy(c["conditions"][0])),
    ]:
        proposed = candidate(p)
        mutate(proposed)
        with pytest.raises(ValueError):
            evaluate_candidate(p, proposed, [evidence()], ["person-1"])
    with pytest.raises(ValueError, match="different participant"):
        evaluate_candidate(
            p, candidate(p), [evidence(participant_ids=["person-2"])], ["person-1", "person-2"]
        )
    with pytest.raises(ValueError, match="ownership"):
        evaluate_candidate(
            p,
            candidate(p),
            [evidence(), evidence(id="f2", source_id="other-recording")],
            ["person-1"],
        )


def test_unknown_dependencies_counterevidence_and_nonvisual_conditions_force_abstention():
    p = plan(polarity="satisfied")
    proposed = candidate(p, support=["f1"], counter=["f2"])
    result = evaluate_candidate(p, proposed, [evidence(), evidence(id="f2")], ["person-1"])
    assert result.assessment == "insufficient_evidence"
    assert result.conditions[0].result == "unknown"
    proposed = candidate(p)
    proposed["conditions"][0]["unresolved_dependencies"] = ["operation end off camera"]
    assert evaluate_candidate(p, proposed, [evidence()], ["person-1"]).assessment == (
        "insufficient_evidence"
    )
    data = p.model_dump(exclude={"plan_id"})
    data["conditions"][0]["requires_metadata"] = True
    p = ConditionPlan.model_validate({**data, "plan_id": fingerprint(data)})
    assert evaluate_candidate(p, candidate(p), [evidence()], ["person-1"]).assessment == (
        "insufficient_evidence"
    )


def test_absence_requires_backend_established_visibility_and_role_needs_repeated_evidence():
    p = plan(polarity="satisfied")
    data = p.model_dump(exclude={"plan_id"})
    data["conditions"][0]["requires_complete_opportunity"] = True
    p = ConditionPlan.model_validate({**data, "plan_id": fingerprint(data)})
    assert evaluate_candidate(p, candidate(p), [evidence()], ["person-1"]).assessment == (
        "insufficient_evidence"
    )
    assert (
        evaluate_candidate(
            p,
            candidate(p, support=["f1", "o1"]),
            [evidence(complete_opportunity=True, visibility="clear"), observation_evidence()],
            ["person-1"],
        ).assessment
        == "supported_violation"
    )
    p = plan(category="role")
    with pytest.raises(ValueError, match="repeated"):
        evaluate_candidate(p, candidate(p), [evidence()], ["person-1"])


def test_model_cannot_override_application_version_or_mutate_polarity():
    p = plan(version="unknown", polarity="satisfied")
    assert evaluate_candidate(p, candidate(p), [evidence()], ["person-1"]).assessment == (
        "insufficient_evidence"
    )
    p = plan(category="version", version="unknown", polarity="satisfied")
    assert evaluate_candidate(p, candidate(p), [evidence()], ["person-1"]).assessment == (
        "insufficient_evidence"
    )
    p = plan(category="version", version="not_applicable", polarity="satisfied")
    assert evaluate_candidate(p, candidate(p), [evidence()], ["person-1"]).assessment == (
        "not_applicable"
    )
    p.conditions[0].violation_when = "contradicted"
    with pytest.raises(ValueError, match="fingerprint"):
        evaluate_candidate(p, candidate(p), [evidence()], ["person-1"])


def test_role_grounded_duty_holder_cannot_be_replaced_by_another_action_actor():
    p = plan(category="role")
    data = p.model_dump(exclude={"plan_id"})
    data["conditions"].append({**data["conditions"][0], "id": "action", "category": "action"})
    p = ConditionPlan.model_validate({**data, "plan_id": fingerprint(data)})
    proposed = candidate(p)
    proposed["participant_ids"].append("person-2")
    proposed["conditions"].append(
        {
            **proposed["conditions"][0],
            "condition_id": "action",
            "participant_ids": ["person-2"],
            "supporting_evidence_ids": ["f2"],
        }
    )
    with pytest.raises(ValueError, match="duty-holder"):
        evaluate_candidate(
            p,
            proposed,
            [evidence(frame_ids=["f1", "f3"]), evidence(id="f2", participant_ids=["person-2"])],
            ["person-1", "person-2"],
        )


def test_prompt_schema_bounds_ids_and_omits_model_approval_fields():
    p = plan()
    prompt, schema = build_condition_prompt(p, [], ["person-1"], ["f1"], {})
    assert "polarity" in prompt and "actual attached source images" in prompt
    assert "assessment" not in schema["properties"]
    assert schema["properties"]["plan_id"]["const"] == p.plan_id
    refs = schema["$defs"]["ConditionResult"]["properties"]["supporting_evidence_ids"]
    assert refs["items"]["enum"] == ["f1"]


def test_legal_image_budget_selects_complete_observations_without_trimming_evidence():
    observations = [
        {
            "observation_id": "first",
            "evidence_frame_ids": [f"f{i}" for i in range(6)],
            "decisive_frame_id": "f5",
        },
        {
            "observation_id": "too-many",
            "evidence_frame_ids": [f"f{i}" for i in range(5, 11)],
            "decisive_frame_id": "f10",
        },
        {"observation_id": "last", "evidence_frame_ids": ["f7"], "decisive_frame_id": "f7"},
    ]
    chosen, ids = bounded_observation_evidence(observations)
    assert [o["observation_id"] for o in chosen] == ["first", "last"]
    assert len(ids) <= 8
    assert all(set(o["evidence_frame_ids"]) <= set(ids) for o in chosen)


def test_local_timeline_wrapper_attaches_original_images_and_reports_skipped_inventory(
    service, tmp_path
):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "frames")
    frame = registry.frames[0]
    timeline = {
        "source_sha256": registry.source_sha256,
        "observations": [
            {
                "observation_id": "obs-explicit",
                "source_sha256": registry.source_sha256,
                "value": "syntheticunrelatedword",
                "actor_ids": ["person-1"],
                "recipient_ids": [],
                "evidence_frame_ids": [frame.frame_id],
                "visibility": "visible_samples",
                **{f"{key}_frame_id": frame.frame_id for key in ["start", "end", "decisive"]},
                **{f"{key}_sec": frame.timestamp_sec for key in ["start", "end", "decisive"]},
            }
        ],
        "participants": [
            {"participant_id": "person-1"},
            *[{"participant_id": f"unrelated-{i}"} for i in range(54)],
        ],
        "coverage": {"continuous_visibility_validated": False},
    }

    class LocalSyntheticBackend:
        calls = 0

        def request(self, actual_registry, frames, prompt, schema, pixels, max_tokens):
            self.calls += 1
            assert actual_registry is registry and frames
            assert len(frames) <= 8 and "unrelated-" not in prompt
            assert schema["properties"]["participant_ids"]["items"]["enum"] == ["person-1"]
            assert actual_registry.image_bytes(frames[0], pixels).startswith(b"\xff\xd8")
            # Synthetic response verifies interface wiring and ID validation only.
            props = schema["$defs"]["ConditionResult"]["properties"]
            return {
                "plan_id": schema["properties"]["plan_id"]["const"],
                "source_provision_ids": schema["properties"]["source_provision_ids"]["items"][
                    "enum"
                ],
                "participant_ids": ["person-1"],
                "conditions": [
                    {
                        "condition_id": id,
                        "result": "unknown",
                        "supporting_evidence_ids": [frame.frame_id, "obs-explicit"],
                    }
                    for id in props["condition_id"]["enum"]
                ],
                "explanation": "Synthetic unavailable conditions.",
            }

    backend = LocalSyntheticBackend()
    report = service.evaluate_timeline(
        timeline, registry, backend, tmp_path / "legal", time.monotonic() + 30, max_calls=1
    )
    assert backend.calls == 1 and report["metrics"]["calls"] == 1
    assert report["assessments"][0]["assessment"] == "insufficient_evidence"
    assert report["assessments"][0]["condition_specs"][0]["proposition"]
    assert report["assessments"][0]["citations"][0]["text"]
    assert report["assessments"][0]["observation_ids"] == ["obs-explicit"]
    assert len(report["rule_coverage"]) == 12 and report["status"] == "incomplete"
    assert sum(c["status"] == "not_evaluated" for c in report["rule_coverage"]) == 11
    assert report["metrics"]["receipts"][0]["direction"] == "inventory"
    assert (tmp_path / "legal/legal-assessments.json").is_file()
