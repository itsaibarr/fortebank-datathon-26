"""Separate private visual facts and legal assessments, with explicit review gates."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from forte.legal import Corpus


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleCard(Strict):
    id: str
    clause_ids: list[str] = Field(min_length=1)
    scope: str
    actor_role: Literal["cashier", "customer", "unclear"]
    prerequisites: dict[str, str]
    exceptions: dict[str, str]
    visual_limits: list[str] = Field(min_length=1)
    review_status: Literal["draft", "approved"] = "draft"
    reviewer: str | None = None


class VisualFact(Strict):
    id: str
    kind: Literal["role", "action", "context"]
    actor_id: str | None = None
    value: str
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(ge=0, allow_inf_nan=False)
    frame_ids: list[str] = Field(min_length=1)
    continuity_supported: bool = False
    review_status: Literal["draft", "confirmed", "rejected"] = "draft"
    reviewer: str | None = None
    # Optional track-sidecar bindings. Legacy annotations remain readable; the
    # versioned tracking workflow applies the stronger gates in validate_pair.
    segment_ids: list[str] = Field(default_factory=list)
    work_area_id: str | None = None
    counterpart_actor_id: str | None = None
    observation_state: Literal[
        "observed", "not_reviewed", "not_visible", "not_observed_in_reviewed_interval"
    ] = "not_reviewed"
    target_kind: Literal["fact", "abstention", "unresolved"] = "unresolved"
    visibility_limits: str = ""
    visible_basis: str = ""
    reviewed_at: datetime | None = None
    origin: Literal["human", "model", "legacy"] = "legacy"
    playback_interval: tuple[float, float] | None = None
    boundary_uncertain: bool = True


class Predicate(Strict):
    state: Literal["satisfied", "contradicted", "unknown"] = "unknown"
    fact_ids: list[str] = Field(default_factory=list)


class LegalClaim(Strict):
    card_id: str
    actor_id: str | None = None
    decision: Literal["supported", "not_supported", "unresolved"] = "unresolved"
    prerequisites: dict[str, Predicate]
    exceptions: dict[str, Predicate]
    reviewer: str | None = None


class Annotation(Strict):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_sec: float = Field(gt=0, le=180, allow_inf_nan=False)
    frames: dict[str, float]
    facts: list[VisualFact]
    claims: list[LegalClaim]

    @model_validator(mode="after")
    def source_bindings(self):
        if len({f.id for f in self.facts}) != len(self.facts):
            raise ValueError("Duplicate visual fact")
        if any(not 0 <= t <= self.duration_sec for t in self.frames.values()):
            raise ValueError("Frame timestamp outside recording")
        for fact in self.facts:
            if not 0 <= fact.start_sec <= fact.end_sec <= self.duration_sec:
                raise ValueError("Fact interval outside recording")
            if not set(fact.frame_ids) <= self.frames.keys() or any(
                not fact.start_sec <= self.frames[id] <= fact.end_sec for id in fact.frame_ids
            ):
                raise ValueError("Fact evidence outside supplied interval/frames")
            if fact.review_status != "draft" and not fact.reviewer:
                raise ValueError("Reviewed fact requires a reviewer")
            if fact.kind == "role":
                if not fact.actor_id or fact.value not in {"cashier", "customer", "unclear"}:
                    raise ValueError("Role fact requires an anonymous actor and allowed role")
                if fact.value != "unclear" and (
                    len(set(fact.frame_ids)) < 2 or not fact.continuity_supported
                ):
                    raise ValueError("Certain role requires temporal evidence and continuity")
        return self


def validate_cards(cards: list[RuleCard], corpus: Corpus):
    if len({c.id for c in cards}) != len(cards):
        raise ValueError("Duplicate rule card")
    live = {c.id for c in corpus.clauses if not c.repealed}
    for card in cards:
        if not set(card.clause_ids) <= live:
            raise ValueError("Rule card cites missing or repealed clause")
        if card.review_status == "approved" and not card.reviewer:
            raise ValueError("Approved card requires a reviewer")


def validate_annotation(annotation: Annotation, cards: list[RuleCard], corpus: Corpus):
    """Structural validation is not independent visual or legal adjudication."""
    # Revalidate mutable instances; the models are also convenient for local review edits.
    annotation = Annotation.model_validate(annotation.model_dump())
    validate_cards(cards, corpus)
    by_id, facts = {c.id: c for c in cards}, {f.id: f for f in annotation.facts}
    for claim in annotation.claims:
        if claim.card_id not in by_id:
            raise ValueError("Unknown rule card")
        card = by_id[claim.card_id]
        if set(claim.prerequisites) != set(card.prerequisites):
            raise ValueError("Every prerequisite must be assessed, including unknowns")
        if set(claim.exceptions) != set(card.exceptions):
            raise ValueError("Every exception must be assessed, including unknowns")
        predicates = list(claim.prerequisites.values()) + list(claim.exceptions.values())
        for predicate in predicates:
            if not set(predicate.fact_ids) <= facts.keys():
                raise ValueError("Assessment cites an unknown fact")
            if predicate.state != "unknown" and not predicate.fact_ids:
                raise ValueError("Assessed predicate requires factual support")
        if claim.decision == "unresolved":
            continue
        if not claim.reviewer or card.review_status != "approved":
            raise ValueError("Resolved legal claim requires a reviewer and approved rule card")
        used = {id for p in predicates if p.state != "unknown" for id in p.fact_ids}
        if any(facts[id].review_status != "confirmed" for id in used):
            raise ValueError("Resolved legal claim requires confirmed visual facts")
        if claim.decision == "not_supported":
            if not (
                any(p.state == "contradicted" for p in claim.prerequisites.values())
                or any(p.state == "satisfied" for p in claim.exceptions.values())
            ):
                raise ValueError("Not-supported claim requires a contradicted duty or exception")
            continue
        if any(p.state != "satisfied" for p in claim.prerequisites.values()) or any(
            p.state != "contradicted" for p in claim.exceptions.values()
        ):
            raise ValueError(
                "Supported claim cannot contain an unknown or contradicted prerequisite"
            )
        roles = [f for f in annotation.facts if f.kind == "role" and f.actor_id == claim.actor_id]
        if not roles or any(f.value != card.actor_role for f in roles):
            raise ValueError("Claim actor role does not match the obligation")
        if any(f.review_status != "confirmed" for f in roles):
            raise ValueError("Supported claim requires a confirmed actor role")
    return annotation
