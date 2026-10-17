"""Offline source-bound rule checks over predicted visual facts.

One operational category is executable: acceptance-phase cashier departure.
Other retrieved cards remain unresolved candidates. No legal review is invented.
"""

import json
from datetime import date

from forte.annotations import RuleCard, validate_cards
from forte.legal import load_release
from forte.person_proposals import sha256

DEPARTURES = {"leaves_workstation", "workstation_departure"}


def overlaps(a, b):
    return max(a["start_sec"], b["start_sec"]) <= min(a["end_sec"], b["end_sec"])


def temporal_checks(report, config):
    corpus = load_release(config.legal_release)
    cards = [RuleCard.model_validate(c) for c in json.loads(config.rule_cards.read_bytes())]
    validate_cards(cards, corpus)
    policy = json.loads(config.rule_policy.read_bytes())
    clauses = {c.id: c for c in corpus.clauses}
    applicability = policy.get("applicability_by_source", {}).get(report["source_sha256"], {})
    facts = report["visual_timeline"]
    checks = []
    for i, event in enumerate(facts):
        if event["kind"] != "action" or event["value"] == "unclear":
            continue
        # Open discovery is retained. Retrieval proposes sources; it never creates
        # a duty or enables a card. Inference uses only the staged corpus.
        retrieved = corpus.search(event["value"].replace("_", " "), limit=3)
        ids = ["acceptance_cashier_departure"] if event["value"] in DEPARTURES else []
        if not ids:
            checks.append(
                {
                    "event_index": i,
                    "decision": "unresolved",
                    "reason": "category_not_operational",
                    "retrieved_sources": [h["clause"]["url"] for h in retrieved],
                }
            )
            continue
        card = next(c for c in cards if c.id == ids[0])
        linked = [
            f
            for f in facts
            if f["actor_id"] == event["actor_id"]
            and f["segments"] == event["segments"]
            and not f.get("contradiction")
            and f["visibility"] == "observed"
        ]
        role = [
            f
            for f in linked
            if f["kind"] == "role"
            and f["value"] == card.actor_role
            and f["start_sec"] <= event["start_sec"] <= f["end_sec"]
            and len(set(f["evidence_frame_ids"])) >= 2
        ]

        def context(value, linked=linked, event=event):
            return [
                f
                for f in linked
                if f["kind"] == "context" and f["value"] == value and overlaps(f, event)
            ]

        conflicts = any(
            set(c["segments"]) & set(event["segments"]) for c in report.get("role_conflicts", [])
        )
        dates = applicability.get("recording_date")
        try:
            legal_date = bool(
                dates
                and date.fromisoformat(dates)
                and applicability.get("version_ids")
                and all(
                    clauses[c].version_id in applicability["version_ids"] for c in card.clause_ids
                )
                and applicability.get("edition_basis")
            )
        except ValueError:
            legal_date = False
        # A reviewed independent policy receipt binds the card bytes. A name in
        # JSON alone is not authenticated approval; its receipt remains private.
        approved = (
            card.review_status == "approved"
            and bool(card.reviewer)
            and policy.get("approved_cards_sha256") == sha256(config.rule_cards)
            and bool(policy.get("independent_review_receipt_sha256"))
        )
        ongoing = context("service_ongoing")
        predicates = {
            "legal_date_applicable": legal_date,
            "institution_in_scope": applicability.get("institution_in_scope") is True
            and bool(applicability.get("scope_basis")),
            "acceptance": bool(context("cash_acceptance")),
            "service_ongoing": bool(ongoing)
            and all(not f["service_completion_uncertain"] for f in ongoing),
            "departure": event["visibility"] == "observed"
            and not event["continues_before_window"]
            and not event["continues_after_window"]
            and event["start_sec"] < event["end_sec"]
            and not event.get("contradiction"),
            "cashier_role": bool(role) and not conflicts,
            "work_area_crossing": area_crossing(event, report),
        }
        supported = approved and all(predicates.values())
        evidence = list(
            dict.fromkeys(
                [
                    *(role[0]["evidence_frame_ids"][:1] if role else []),
                    event["start_frame_id"],
                    event["end_frame_id"],
                ]
            )
        )
        sources = [
            {
                **clauses[c].model_dump(),
                "document_title": next(
                    s.title
                    for s in corpus.sources
                    if s.act_id == clauses[c].act_id and s.version_id == clauses[c].version_id
                ),
            }
            for c in card.clause_ids
        ]
        checks.append(
            {
                "event_index": i,
                "card_id": card.id,
                "decision": "supported" if supported else "unresolved",
                "prerequisites": {
                    k: "satisfied" if v else "unknown" for k, v in predicates.items()
                },
                "exceptions": {},
                "card_approved": approved,
                "sources": sources,
                "applicability_basis": applicability,
                "evidence_frame_ids": evidence[:3],
                "visual_origin": "model",
                "limits": card.visual_limits,
                "timecode_frame_id": event["end_frame_id"],
            }
        )
    return {
        "checks": checks,
        "operational_categories": ["acceptance_cashier_departure"],
        "corpus_acts": len(corpus.sources),
        "cards": len(cards),
        "approved_cards": sum(c.review_status == "approved" for c in cards),
        "comprehensive_law_coverage": False,
        "legal_manifest_sha256": sha256(config.legal_release / "manifest.json"),
        "cards_sha256": sha256(config.rule_cards),
        "policy_sha256": sha256(config.rule_policy),
    }


def area_crossing(event, report):
    from forte_visual.scan import inside

    boxes = report.get("source_track_boxes", {})
    start = boxes.get(event["start_frame_id"], {}).get(event["actor_id"], [])
    end = boxes.get(event["end_frame_id"], {}).get(event["actor_id"], [])
    # Multiple direct/reflected boxes cannot choose a convenient crossing.
    if len(start) != 1 or len(end) != 1:
        return False

    def point(b):
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

    return any(
        inside(point(start[0]), a["points"]) and not inside(point(end[0]), a["points"])
        for a in report.get("predicted_work_areas", [])
    )
