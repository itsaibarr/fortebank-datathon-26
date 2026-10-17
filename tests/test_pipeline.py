from uuid import uuid4

import pytest
from test_video import make_mov

from forte.contracts import ActorGrounding, EventObservation, EvidenceCheck, WindowObservation
from forte.pipeline import analyze_video
from forte.rules import load_rules


class Observations:
    def __init__(self, uncertain=False):
        self.uncertain = uncertain

    def analyze(self, registry, frames, rules, pixels, max_tokens, phase="refine"):
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
            actor=ActorGrounding(
                role="cashier", role_evidence_ids=[frames[0].frame_id], continuity_supported=True
            ),
        )


def test_positive_has_real_source_evidence_and_catalog_citation(tmp_path):
    result = analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), Observations())
    assert result.verdict == "violation"
    assert len(result.violations) == 1
    event = result.violations[0]
    assert "V1900019680" in event.description
    assert "окончательный" in event.description
    assert event.evidence_frames[0].timestamp_sec <= 3.1
    assert len(event.evidence_frames) >= 2
    assert event.evidence_frames[0].timestamp_sec < event.timecode_sec


def test_unresolved_evidence_does_not_become_clean_negative(tmp_path):
    with pytest.raises(ValueError, match="insufficient_evidence"):
        analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), Observations(True))


def test_supported_departure_without_actor_grounding_cannot_be_reported(tmp_path):
    class NoActorGrounding(Observations):
        def verify(self, registry, frames, event, rule):
            return EvidenceCheck(
                verdict="supported", evidence_ids=event.evidence_ids, preconditions=rule["required"]
            )

    with pytest.raises(ValueError, match="insufficient_evidence"):
        analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), NoActorGrounding())


@pytest.mark.parametrize(
    "role,continuity,proof,expected",
    [
        ("customer", True, "earlier", "no_violation"),
        ("unclear", True, "earlier", "insufficient_evidence"),
        ("cashier", False, "earlier", "insufficient_evidence"),
        ("cashier", True, "empty", "insufficient_evidence"),
        ("cashier", True, "moment_only", "insufficient_evidence"),
        ("cashier", True, "invented", "insufficient_evidence"),
    ],
)
def test_departure_requires_prior_role_evidence_and_actor_continuity(
    tmp_path, role, continuity, proof, expected
):
    class ActorAssessment(Observations):
        def verify(self, registry, frames, event, rule):
            answer = super().verify(registry, frames, event, rule)
            ids = {
                "earlier": [frames[0].frame_id],
                "empty": [],
                "moment_only": [event.decisive_id],
                "invented": ["not-supplied"],
            }[proof]
            return answer.model_copy(
                update={
                    "actor": ActorGrounding(
                        role=role, role_evidence_ids=ids, continuity_supported=continuity
                    )
                }
            )

    def run():
        return analyze_video(
            make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), ActorAssessment()
        )

    if expected == "insufficient_evidence":
        with pytest.raises(ValueError, match=expected):
            run()
    else:
        assert run().verdict == expected


@pytest.mark.parametrize("first,second", [("cashier", "customer"), ("customer", "cashier")])
def test_conflicting_actor_roles_between_local_and_context_checks_remain_unclear(
    tmp_path, first, second
):
    class ConflictingRoles(Observations):
        checks = 0

        def verify(self, registry, frames, event, rule):
            self.checks += 1
            answer = super().verify(registry, frames, event, rule)
            answer.actor.role = first if self.checks == 1 else second
            return answer

    with pytest.raises(ValueError, match="insufficient_evidence"):
        analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), ConflictingRoles())


def test_partial_hypothesis_can_be_confirmed_only_after_expanded_verification(tmp_path):
    class Partial(Observations):
        checks = 0

        def analyze(self, *args):
            answer = super().analyze(*args)
            answer.events[0].preconditions = []
            return answer

        def verify(self, *args):
            self.checks += 1
            self.uncertain = self.checks == 1
            return super().verify(*args)

    backend = Partial()
    result = analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), backend)
    assert backend.checks == 2
    assert result.verdict == "violation"


def test_expanded_verification_retains_original_candidate_context(tmp_path):
    class NeedsEarlierContext(Observations):
        coarse_calls = 0
        checks = 0

        def analyze(self, registry, frames, rules, pixels, max_tokens, phase="refine"):
            if pixels == 196608:
                self.coarse_calls += 1
                if self.coarse_calls > 1:
                    return WindowObservation(complete=True, events=[])
            answer = super().analyze(registry, frames, rules, pixels, max_tokens)
            event = answer.events[0]
            event.decisive_id = min(frames, key=lambda f: abs(f.timestamp_sec - 15)).frame_id
            event.evidence_ids = [event.decisive_id]
            return answer

        def verify(self, registry, frames, event, rule):
            self.checks += 1
            assert len(frames) <= 16
            self.uncertain = registry.frames[0].frame_id not in {f.frame_id for f in frames}
            return super().verify(registry, frames, event, rule)

    backend = NeedsEarlierContext()
    path = make_mov(tmp_path / "s.mov", tuple(range(180)))
    result = analyze_video(path, tmp_path / "work", uuid4(), backend)
    assert backend.checks == 2
    assert result.verdict == "violation"


def test_context_counterevidence_overrules_a_locally_supported_hypothesis(tmp_path):
    class Counterevidence(Observations):
        checks = 0

        def verify(self, *args):
            self.checks += 1
            answer = super().verify(*args)
            if self.checks == 2:
                answer.verdict = "unsupported"
            return answer

    backend = Counterevidence()
    result = analyze_video(make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), backend)
    assert backend.checks == 2
    assert result.verdict == "no_violation"


def test_reversed_guessed_bounds_cannot_move_the_verified_source_moment(tmp_path):
    class ReversedBounds(Observations):
        def analyze(self, *args):
            answer = super().analyze(*args)
            event = answer.events[0]
            event.start_id, event.end_id = event.end_id, event.start_id
            return answer

    result = analyze_video(
        make_mov(tmp_path / "s.mov"), tmp_path / "work", uuid4(), ReversedBounds()
    )
    assert result.verdict == "violation"
    assert result.violations[0].timecode_sec == 3
    assert result.violations[0].evidence_frames[-1].timestamp_sec == 3


def test_legal_source_and_omission_prerequisites_are_not_optional():
    rules = load_rules()
    assert len(rules) == 3
    assert all(r["required"] and r["citation"].startswith("Постановление") for r in rules)
