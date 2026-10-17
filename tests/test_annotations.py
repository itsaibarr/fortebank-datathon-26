import json
from pathlib import Path

import pytest
from test_legal import HTML, snapshot

from forte.annotations import Annotation, RuleCard, validate_annotation, validate_cards
from forte.cli import main
from forte.legal import Corpus, extract_clauses, load_release


def fixture():
    source = snapshot()
    corpus = Corpus(sources=[source], clauses=extract_clauses(source, HTML))
    card = RuleCard(
        id="departure",
        clause_ids=[corpus.clauses[-1].id],
        scope="Synthetic acceptance only",
        actor_role="cashier",
        prerequisites={"ongoing": "Service ongoing"},
        exceptions={},
        visual_limits=["Role must be established"],
        review_status="approved",
        reviewer="synthetic legal reviewer",
    )
    annotation = Annotation(
        source_sha256="0" * 64,
        duration_sec=10,
        frames={"f1": 1, "f2": 2},
        facts=[
            dict(
                id="role",
                kind="role",
                actor_id="p1",
                value="customer",
                start_sec=1,
                end_sec=2,
                frame_ids=["f1", "f2"],
                continuity_supported=True,
                review_status="confirmed",
                reviewer="synthetic visual reviewer",
            ),
            dict(
                id="service",
                kind="context",
                actor_id="p1",
                value="ongoing",
                start_sec=1,
                end_sec=2,
                frame_ids=["f1"],
                review_status="confirmed",
                reviewer="reviewer",
            ),
        ],
        claims=[
            dict(
                card_id="departure",
                actor_id="p1",
                decision="supported",
                prerequisites={"ongoing": dict(state="satisfied", fact_ids=["service"])},
                exceptions={},
                reviewer="synthetic legal reviewer",
            )
        ],
    )
    return annotation, [card], corpus


def test_a_customer_role_cannot_support_a_cashier_obligation():
    annotation, cards, corpus = fixture()
    with pytest.raises(ValueError, match="actor role"):
        validate_annotation(annotation, cards, corpus)


def test_draft_labels_unknown_prerequisites_and_unreviewed_cards_cannot_be_training_truth():
    annotation, cards, corpus = fixture()
    annotation.facts[0].value = "cashier"
    validate_annotation(annotation, cards, corpus)
    annotation.facts[0].review_status = "draft"
    with pytest.raises(ValueError, match="confirmed"):
        validate_annotation(annotation, cards, corpus)
    annotation.facts[0].review_status = "confirmed"
    cards[0].review_status = "draft"
    with pytest.raises(ValueError, match="approved"):
        validate_annotation(annotation, cards, corpus)
    annotation.claims[0].decision = "unresolved"
    annotation.claims[0].prerequisites["ongoing"].state = "unknown"
    validate_annotation(annotation, cards, corpus)


def test_unseen_fact_references_and_offscreen_or_missing_prerequisites_are_rejected():
    annotation, cards, corpus = fixture()
    annotation.claims[0].decision = "unresolved"
    annotation.claims[0].prerequisites["ongoing"].fact_ids = ["invented"]
    with pytest.raises(ValueError, match="unknown fact"):
        validate_annotation(annotation, cards, corpus)
    annotation.claims[0].prerequisites = {}
    with pytest.raises(ValueError, match="prerequisite"):
        validate_annotation(annotation, cards, corpus)


def test_real_draft_cards_bind_to_live_official_clauses_and_cli_stays_private(tmp_path, capsys):
    root = Path(__file__).resolve().parents[1]
    corpus = load_release(root / "legal/2026-10-17")
    cards_path = root / "legal/rule-cards.json"
    cards = [RuleCard.model_validate(c) for c in json.loads(cards_path.read_text())]
    validate_cards(cards, corpus)
    assert len(cards) == 12 and all(c.review_status == "draft" for c in cards)
    annotation = tmp_path / "private.json"
    annotation.write_text(
        json.dumps(dict(source_sha256="0" * 64, duration_sec=10, frames={}, facts=[], claims=[]))
    )
    assert (
        main(
            [
                "annotations-check",
                "--release",
                str(root / "legal/2026-10-17"),
                "--cards",
                str(cards_path),
                "--file",
                str(annotation),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output == dict(
        structurally_valid=True, facts=0, claims=0, independent_semantic_adjudication=False
    )
