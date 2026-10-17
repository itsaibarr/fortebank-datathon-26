from uuid import uuid4

import pytest
from test_video import make_mov

from forte.contracts import EventObservation, EvidenceCheck, WindowObservation
from forte.pipeline import analyze_video
from forte.rules import load_rules


class Observations:
    def __init__(self, uncertain=False):
        self.uncertain = uncertain

    def analyze(self, registry, frames, rules, pixels, max_tokens):
        rule = rules[0]
        event = EventObservation(
            rule_id=rule["id"],
            start_id=frames[0].frame_id,
            end_id=frames[-1].frame_id,
            decisive_id=frames[-1].frame_id,
            evidence_ids=[frames[-1].frame_id],
            visible_facts="Синтетическая проверка.",
            preconditions=rule["required"],
        )
        return WindowObservation(complete=True, events=[event])

    def verify(self, registry, frames, event, rule):
        return EvidenceCheck(
            verdict="unclear" if self.uncertain else "supported",
            evidence_ids=event.evidence_ids,
            preconditions=rule["required"],
        )


def test_positive_has_real_source_evidence_and_catalog_citation(tmp_path):
    result = analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), Observations())
    assert result.verdict == "violation"
    assert len(result.violations) == 1
    event = result.violations[0]
    assert "V1900019680" in event.description
    assert "окончательный" in event.description
    assert event.evidence_frames[0].timestamp_sec <= 3.1


def test_unresolved_evidence_does_not_become_clean_negative(tmp_path):
    with pytest.raises(ValueError, match="insufficient_evidence"):
        analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), Observations(True))


def test_legal_source_and_omission_prerequisites_are_not_optional():
    rules = load_rules()
    assert len(rules) == 3
    assert all(r["required"] and r["citation"].startswith("Постановление") for r in rules)
