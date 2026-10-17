"""Strict multi-fact scan interface, independent of evaluation references."""

from typing import Literal

from pydantic import Field

from forte_visual.inputs import Answer
from forte_visual.release import Strict


class Proposal(Strict):
    actor_id: str
    frame_id: str


class AreaProposal(Strict):
    frame_ids: list[str] = Field(min_length=1, max_length=16)
    points: list[tuple[float, float]] = Field(min_length=3, max_length=12)


class Visibility(Strict):
    start_frame_id: str
    end_frame_id: str
    state: Literal["visible_samples", "occluded", "unclear"]
    object_resolution_adequate: bool


class ScanResponse(Strict):
    facts: list[Answer] = Field(default_factory=list, max_length=8)
    proposals: list[Proposal] = Field(default_factory=list, max_length=8)
    work_areas: list[AreaProposal] = Field(default_factory=list, max_length=4)
    visibility: list[Visibility] = Field(default_factory=list, max_length=8)


def validate_response(case, value):
    response = ScanResponse.model_validate(value)
    for fact in response.facts:
        if fact.visibility == "reviewed_absent":
            raise ValueError("Sparse model outputs cannot establish reviewed absence")
    for p in response.proposals:
        if (
            p.actor_id not in case.actors
            or p.frame_id not in case.frames
            or not case.track_boxes.get(p.actor_id, {}).get(p.frame_id)
        ):
            raise ValueError("Proposal lacks supplied actor/source membership")
    for area in response.work_areas:
        if not set(area.frame_ids) <= case.frames.keys() or any(
            not 0 <= x <= 1 or not 0 <= y <= 1 for x, y in area.points
        ):
            raise ValueError("Invalid source-bound work-area proposal")
    for v in response.visibility:
        if (
            v.start_frame_id not in case.frames
            or v.end_frame_id not in case.frames
            or case.frames[v.start_frame_id] > case.frames[v.end_frame_id]
        ):
            raise ValueError("Invalid sampled visibility interval")
    return response
