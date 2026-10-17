"""Recording-local proposal contracts. Association is never semantic approval."""

import math
from datetime import datetime
from fractions import Fraction
from typing import Literal

from pydantic import Field, model_validator

from forte.annotations import Annotation, Strict

XYXY = tuple[float, float, float, float]


def checked_box(box) -> XYXY:
    x1, y1, x2, y2 = box
    if not all(math.isfinite(x) for x in box) or not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("Invalid normalized full-frame box")
    return tuple(box)


def transform_box(box, *, scale, width, height, offset=(0, 0)) -> XYXY:
    """Invert top-left letterbox/crop coordinates, on an already oriented frame."""
    if scale <= 0 or width <= 0 or height <= 0:
        raise ValueError("Invalid transform")
    return checked_box(
        tuple((v - offset[i % 2]) / scale / (width, height)[i % 2] for i, v in enumerate(box))
    )


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0


class Review(Strict):
    status: Literal["draft", "confirmed", "rejected"] = "draft"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    notes: str = ""

    @model_validator(mode="after")
    def named_review(self):
        if self.status != "draft" and (
            not self.reviewer
            or not self.reviewer.strip()
            or not self.reviewed_at
            or not self.reviewed_at.tzinfo
        ):
            raise ValueError("Review requires actual reviewer and timezone-aware review time")
        return self


class SourceFrame(Strict):
    frame_id: str
    ordinal: int = Field(ge=0)
    source_pts: int
    timestamp_sec: float = Field(ge=0, allow_inf_nan=False)


class Box(Strict):
    frame_id: str
    xyxy: XYXY
    origin: Literal["detector", "interpolation", "human", "cvat_import"] = "detector"
    automatic_score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    occluded: bool = False
    outside: bool = False
    keyframe: bool = True
    role_attribute: Literal["cashier", "customer", "unclear"] = "unclear"
    review: Review = Field(default_factory=Review)

    @model_validator(mode="after")
    def bounds(self):
        checked_box(self.xyxy)
        return self


class Segment(Strict):
    id: str
    person_id: str
    upstream_id: int
    identity_uncertain: bool = False
    review: Review = Field(default_factory=Review)
    boxes: list[Box] = Field(min_length=1)


class Join(Strict):
    id: str
    from_segment: str
    to_segment: str
    reason: str
    origin: Literal["tracker", "human"] = "tracker"
    review: Review = Field(default_factory=Review)


class Gap(Strict):
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(ge=0, allow_inf_nan=False)
    reason: str
    segment_ids: list[str] = Field(default_factory=list)


class WorkArea(Strict):
    id: str
    frame_ids: list[str] = Field(min_length=1)
    points: list[tuple[float, float]] = Field(min_length=3)
    boundary_uncertain: bool = True
    review: Review = Field(default_factory=Review)
    notes: str = ""


class Correction(Strict):
    operation: Literal[
        "split",
        "join",
        "box",
        "fact",
        "area",
        "review",
        "cvat_import",
        "role_binding",
        "view_relation",
        "view_observation",
    ]
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    before_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    affected_ids: list[str]
    reason: str
    artifact: str

    @model_validator(mode="after")
    def provenance(self):
        if not self.reviewer.strip() or not self.reviewed_at.tzinfo or not self.reason.strip():
            raise ValueError("Correction requires actual reviewer, reason and aware timestamp")
        return self


class RoleBinding(Strict):
    """Human segment/role mapping, pending complete interval/work-area evidence.

    This review record is not a VisualFact or an eligible training target.
    Candidate frames are source anchors, not claims of human frame approval.
    """

    id: str
    segment_id: str
    canonical_person_id: str | None
    role: Literal["cashier", "customer", "unclear"]
    view_kind: Literal["direct", "reflection"]
    candidate_frame_ids: list[str] = Field(min_length=1)
    reviewed_frame_ids: list[str] = Field(default_factory=list)
    review_scope: str
    review: Review = Field(default_factory=Review)
    interval_review_status: Literal["pending"] = "pending"
    work_area_review_status: Literal["pending"] = "pending"
    visible_basis_review_status: Literal["pending"] = "pending"


class ViewRelation(Strict):
    """Same person's direct/reflected views, independent of temporal joins."""

    id: str
    direct_segment_id: str
    reflected_segment_id: str
    canonical_person_id: str
    kind: Literal["reflection"] = "reflection"
    review: Review = Field(default_factory=Review)
    temporal_continuity_review: Review = Field(default_factory=Review)


class ViewObservation(Strict):
    """View kind alone, without a role, reflection owner or continuity claim."""

    id: str
    segment_id: str
    view_kind: Literal["direct", "reflection", "unclear"]
    candidate_frame_ids: list[str] = Field(min_length=1)
    reviewed_frame_ids: list[str] = Field(default_factory=list)
    review_scope: str
    review: Review = Field(default_factory=Review)


def confirmed_person_groups(segments, joins):
    """Resolve local identity groups using confirmed temporal joins only."""
    people = {s.id: s.person_id for s in segments}
    parent = {person: person for person in people.values()}

    def root(person):
        while person != parent[person]:
            parent[person] = parent[parent[person]]
            person = parent[person]
        return person

    for join in joins:
        if join.review.status == "confirmed":
            first, second = root(people[join.from_segment]), root(people[join.to_segment])
            parent[max(first, second)] = min(first, second)
    return {person: root(person) for person in parent}


class TrackManifest(Strict):
    schema_version: Literal[1, 2] = 1
    clip_id: str = Field(pattern=r"^clip\d{3}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_file: str
    annotation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_sec: float = Field(gt=0, le=180, allow_inf_nan=False)
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    oriented_width: int = Field(gt=0)
    oriented_height: int = Field(gt=0)
    rotation: float
    time_base: str
    coordinate_convention: Literal["normalized_xyxy_oriented_full_frame"] = (
        "normalized_xyxy_oriented_full_frame"
    )
    frames: list[SourceFrame] = Field(min_length=1)
    detection_frame_ids: list[str]
    cadence_sec: float = Field(gt=0, allow_inf_nan=False)
    segments: list[Segment]
    joins: list[Join] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    work_areas: list[WorkArea] = Field(default_factory=list)
    role_bindings: list[RoleBinding] = Field(default_factory=list)
    view_relations: list[ViewRelation] = Field(default_factory=list)
    view_observations: list[ViewObservation] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)
    recording_group: str
    session_group: str | None = None
    split: Literal["development", "train", "validation", "test"] = "development"
    split_frozen: bool = False
    regression_only: bool = False
    training_eligible: bool = False
    exclusion_reasons: list[str] = Field(
        default_factory=lambda: ["unreviewed", "session_split_unfrozen"]
    )
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def source_binding(self):
        frames = {f.frame_id: f for f in self.frames}
        if self.recording_group != self.source_sha256:
            raise ValueError("Recording group must match the verified source hash")
        if len(frames) != len(self.frames) or self.rotation % 90:
            raise ValueError("Duplicate frame or invalid rotation")
        expected_size = (
            (self.source_height, self.source_width)
            if self.rotation % 180
            else (self.source_width, self.source_height)
        )
        if expected_size != (self.oriented_width, self.oriented_height):
            raise ValueError("Oriented source dimensions disagree")
        base = Fraction(self.time_base)
        if base <= 0:
            raise ValueError("Invalid source time base")
        origin = self.frames[0].source_pts
        for i, frame in enumerate(self.frames):
            if (
                frame.ordinal != i
                or frame.frame_id != f"f{i:06d}"
                or not math.isclose(
                    frame.timestamp_sec, float((frame.source_pts - origin) * base), abs_tol=1e-6
                )
                or frame.timestamp_sec >= self.duration_sec
                or (i and frame.timestamp_sec <= self.frames[i - 1].timestamp_sec)
            ):
                raise ValueError("Inconsistent source PTS/ordinal mapping")
        if (
            len(set(self.detection_frame_ids)) != len(self.detection_frame_ids)
            or not set(self.detection_frame_ids) <= frames.keys()
        ):
            raise ValueError("Unknown or duplicate detection frame")
        segments = {s.id: s for s in self.segments}
        if len(segments) != len(self.segments):
            raise ValueError("Duplicate segment")
        for segment in self.segments:
            ids = [b.frame_id for b in segment.boxes]
            if not set(ids) <= frames.keys() or len(ids) != len(set(ids)):
                raise ValueError("Unknown or duplicate source box frame")
            if ids != sorted(ids, key=lambda id: frames[id].ordinal):
                raise ValueError("Out of order segment boxes")
        if len({j.id for j in self.joins}) != len(self.joins):
            raise ValueError("Duplicate join")
        if (
            self.role_bindings or self.view_relations or self.view_observations
        ) and self.schema_version != 2:
            raise ValueError("View/role review bindings require explicit sidecar v2 migration")
        if len({b.id for b in self.role_bindings}) != len(self.role_bindings) or len(
            {v.id for v in self.view_relations}
        ) != len(self.view_relations):
            raise ValueError("Duplicate role binding or view relation")
        if len({v.id for v in self.view_observations}) != len(self.view_observations):
            raise ValueError("Duplicate view observation")
        for relation in self.view_relations:
            direct, reflected = relation.direct_segment_id, relation.reflected_segment_id
            if (
                direct not in segments
                or reflected not in segments
                or direct == reflected
                or segments[direct].person_id != relation.canonical_person_id
            ):
                raise ValueError("Invalid source segment in view relation")
        for binding in [*self.role_bindings, *self.view_observations]:
            if binding.segment_id not in segments:
                raise ValueError("Unknown view/role binding segment")
            segment = segments[binding.segment_id]
            actual = {b.frame_id for b in segment.boxes if not b.outside}
            if not set(binding.candidate_frame_ids) <= actual or not set(
                binding.reviewed_frame_ids
            ) <= set(binding.candidate_frame_ids):
                raise ValueError("View/role binding frame has no source box or candidate anchor")
        for binding in self.role_bindings:
            segment = segments[binding.segment_id]
            if binding.view_kind == "direct":
                if segment.person_id != binding.canonical_person_id:
                    raise ValueError("Direct role binding identity mismatch")
            elif binding.canonical_person_id is None:
                if not any(
                    v.segment_id == binding.segment_id
                    and v.view_kind == "reflection"
                    and v.review.status == "confirmed"
                    for v in self.view_observations
                ):
                    raise ValueError("Unknown reflection owner requires reviewed view observation")
            elif not any(
                v.reflected_segment_id == binding.segment_id
                and v.canonical_person_id == binding.canonical_person_id
                and v.review.status == "confirmed"
                for v in self.view_relations
            ):
                raise ValueError("Reflected role binding requires a reviewed view relation")
        for join in self.joins:
            if not {join.from_segment, join.to_segment} <= segments.keys() or (
                join.from_segment == join.to_segment
            ):
                raise ValueError("Invalid segment join")
        groups = confirmed_person_groups(self.segments, self.joins)
        accepted = [
            b
            for b in self.role_bindings
            if b.review.status == "confirmed" and b.canonical_person_id is not None
        ]
        for first in accepted:
            if any(
                groups[other.canonical_person_id] == groups[first.canonical_person_id]
                and other.role not in {first.role, "unclear"}
                and first.role != "unclear"
                for other in accepted
            ):
                raise ValueError("Conflicting human role bindings for the same physical person")
        for gap in self.gaps:
            if not 0 <= gap.start_sec <= gap.end_sec <= self.duration_sec:
                raise ValueError("Gap outside recording")
        if len({a.id for a in self.work_areas}) != len(self.work_areas):
            raise ValueError("Duplicate area")
        for area in self.work_areas:
            if not set(area.frame_ids) <= frames.keys() or any(
                not (0 <= x <= 1 and 0 <= y <= 1) for x, y in area.points
            ):
                raise ValueError("Invalid source-bound area")
        if self.training_eligible and (
            self.regression_only
            or not self.split_frozen
            or not self.session_group
            or self.exclusion_reasons
        ):
            raise ValueError("Training eligibility requires reviewed, frozen session split")
        return self


def validate_pair(manifest: TrackManifest, annotation: Annotation):
    """Revalidate mutable edits and bind facts to actual source boxes/intervals."""
    m = TrackManifest.model_validate(manifest.model_dump())
    a = Annotation.model_validate(annotation.model_dump())
    if m.source_sha256 != a.source_sha256 or not math.isclose(m.duration_sec, a.duration_sec):
        raise ValueError("Annotation source binding mismatch")
    frames = {f.frame_id: f.timestamp_sec for f in m.frames}
    if any(
        id not in frames or not math.isclose(t, frames[id], abs_tol=1e-6)
        for id, t in a.frames.items()
    ):
        raise ValueError("Annotation frame binding mismatch")
    segs = {s.id: s for s in m.segments}
    people = {s.person_id for s in m.segments}
    areas = {x.id for x in m.work_areas}
    # Identity components contain ONLY independently confirmed joins.
    components = {s.id: {s.id} for s in m.segments}
    for j in m.joins:
        if j.review.status == "confirmed":
            merged = components[j.from_segment] | components[j.to_segment]
            for id in merged:
                components[id] = merged
    for f in a.facts:
        if f.kind == "role" and f.value != "unclear" and f.review_status != "rejected":
            for binding in m.role_bindings:
                if (
                    binding.review.status == "confirmed"
                    and binding.role != "unclear"
                    and binding.role != f.value
                    and binding.segment_id in f.segment_ids
                    and any(
                        f.start_sec <= frames[id] <= f.end_sec for id in binding.reviewed_frame_ids
                    )
                ):
                    raise ValueError("Role fact conflicts with an existing human role mapping")
        if f.work_area_id and f.work_area_id not in areas:
            raise ValueError("Unknown work area")
        if f.counterpart_actor_id and f.counterpart_actor_id not in people:
            raise ValueError("Unknown counterpart actor")
        if f.counterpart_actor_id:
            ids = f.counterpart_segment_ids
            owned = {s.id for s in m.segments if s.person_id == f.counterpart_actor_id}
            allowed = set().union(*(components[id] for id in owned)) if owned else set()
            if not ids or not set(ids) <= allowed or not f.counterpart_frame_ids:
                raise ValueError("Counterpart requires separately bound identity/source evidence")
            evidence = {b.frame_id for id in ids for b in segs[id].boxes if not b.outside}
            if not set(f.counterpart_frame_ids) <= evidence or any(
                not f.start_sec <= frames[id] <= f.end_sec for id in f.counterpart_frame_ids
            ):
                raise ValueError("Counterpart evidence outside the action interval")
        if f.actor_id:
            if not f.segment_ids or not set(f.segment_ids) <= segs.keys():
                raise ValueError("Actor fact requires source-bound segments")
            owned = {s.id for s in m.segments if s.person_id == f.actor_id}
            allowed = set().union(*(components[id] for id in owned)) if owned else set()
            if not set(f.segment_ids) <= allowed:
                raise ValueError("Unverified identity join cannot inherit a role/action")
            evidence = {b.frame_id for id in f.segment_ids for b in segs[id].boxes if not b.outside}
            if not set(f.frame_ids) <= evidence:
                raise ValueError("Fact has no actor box at cited source frame")
        if f.playback_interval and not (
            0
            <= f.playback_interval[0]
            <= f.start_sec
            <= f.end_sec
            <= f.playback_interval[1]
            <= m.duration_sec
        ):
            raise ValueError("Playback must contain the fact interval")
        if (
            f.kind == "role"
            and f.value != "unclear"
            and len({frames[id] for id in f.frame_ids}) < 2
        ):
            raise ValueError("Certain role requires temporally separated source frames")
        if f.review_status == "confirmed":
            if (
                f.origin != "human"
                or not f.reviewed_at
                or not f.reviewed_at.tzinfo
                or not f.visible_basis
                or not f.visibility_limits
                or not f.playback_interval
                or f.observation_state == "not_reviewed"
                or f.target_kind == "unresolved"
            ):
                raise ValueError("Confirmed fact requires independent evidence review")
            if f.kind == "role" and (not f.work_area_id or not f.segment_ids):
                raise ValueError("Confirmed role requires source-bound work area and actor")
    for i, first in enumerate(a.facts):
        if first.kind != "role" or first.value == "unclear" or first.review_status == "rejected":
            continue
        for other in a.facts[i + 1 :]:
            if (
                other.kind == "role"
                and other.review_status != "rejected"
                and other.value not in {"unclear", first.value}
                and (
                    first.actor_id == other.actor_id
                    or bool(set(first.segment_ids) & set(other.segment_ids))
                )
                and max(first.start_sec, other.start_sec) <= min(first.end_sec, other.end_sec)
            ):
                raise ValueError("Conflicting role assignments require specific local adjudication")
    return m, a


def training_targets(manifest, annotation):
    m, a = validate_pair(manifest, annotation)
    if not m.training_eligible:
        return []
    segs = {s.id: s for s in m.segments}
    areas = {x.id: x for x in m.work_areas}
    result = []
    for f in a.facts:
        if f.review_status != "confirmed" or f.target_kind == "unresolved":
            continue
        if f.kind == "role" and f.value == "unclear" and f.target_kind != "abstention":
            continue
        if f.target_kind != "abstention" and f.observation_state != "observed":
            # An exhaustive reviewed absence is explicit, never inferred from silence.
            if f.observation_state != "not_observed_in_reviewed_interval":
                continue
        if f.work_area_id and areas[f.work_area_id].review.status != "confirmed":
            continue
        participating = f.segment_ids + f.counterpart_segment_ids
        if any(
            segs[id].review.status != "confirmed"
            or segs[id].identity_uncertain
            or any(
                b.review.status != "confirmed"
                for b in segs[id].boxes
                if b.frame_id in f.frame_ids + f.counterpart_frame_ids
            )
            for id in participating
        ):
            continue
        if any(
            j.review.status == "draft"
            and (j.from_segment in participating or j.to_segment in participating)
            for j in m.joins
        ):
            continue
        result.append(f)
    return result


class SegmentBuilder:
    """Conservative guard around upstream IDs; does not implement a new tracker.

    Gaps and overlapping people start fresh anonymous segments. Proposed joins
    preserve the tracker hypothesis, but never transfer a semantic role.
    """

    def __init__(self, cadence_sec):
        self.cadence_sec = cadence_sec
        self.segments: list[Segment] = []
        self.joins: list[Join] = []
        self.gaps: list[Gap] = []
        self.active = {}
        self.last_time = {}
        self.last_update = None
        self.ambiguous = set()

    def _join(self, old, new, reason):
        self.joins.append(
            Join(
                id=f"j{len(self.joins) + 1:05d}",
                from_segment=old.id,
                to_segment=new.id,
                reason=reason,
            )
        )

    def update(self, frame_id, timestamp, tracked):
        if self.last_update is not None and timestamp <= self.last_update:
            raise ValueError("Tracking must consume increasing source timestamps")
        ambiguous = {
            id
            for id, box, _ in tracked
            for other, otherbox, _ in tracked
            if id != other and iou(box, otherbox) > 0.2
        }
        for upstream, box, score in tracked:
            old = self.active.get(upstream)
            gap = old is not None and self.last_time[upstream] != self.last_update
            crossing = old is not None and ((upstream in ambiguous) != (upstream in self.ambiguous))
            jump = old is not None and iou(old.boxes[-1].xyxy, box) == 0
            if old is None or gap or crossing or jump:
                number = len(self.segments) + 1
                new = Segment(
                    id=f"s{number:05d}",
                    person_id=f"p{number:05d}",
                    upstream_id=upstream,
                    identity_uncertain=upstream in ambiguous,
                    boxes=[Box(frame_id=frame_id, xyxy=box, automatic_score=score)],
                )
                self.segments.append(new)
                if old:
                    reason = (
                        "missed_detection_or_occlusion"
                        if gap
                        else "crossing_people"
                        if crossing
                        else "unsupported_displacement"
                    )
                    self._join(old, new, reason)
                    if gap:
                        self.gaps.append(
                            Gap(
                                start_sec=self.last_time[upstream],
                                end_sec=timestamp,
                                reason=reason,
                                segment_ids=[old.id, new.id],
                            )
                        )
                else:
                    # A new upstream ID is not a new verified person. Suggest only
                    # nearby recent endpoints, keeping every link unapproved.
                    candidates = [
                        s
                        for s in self.segments[:-1]
                        if s.upstream_id in self.last_time
                        and 0 < timestamp - self.last_time[s.upstream_id] <= 5
                        and self.last_time[s.upstream_id] != self.last_update
                        and iou(s.boxes[-1].xyxy, box) > 0.2
                    ]
                    for s in candidates[-3:]:
                        self._join(s, new, "possible_reentry")
                self.active[upstream] = new
            else:
                old.boxes.append(Box(frame_id=frame_id, xyxy=box, automatic_score=score))
            self.last_time[upstream] = timestamp
        self.ambiguous = ambiguous
        self.last_update = timestamp
