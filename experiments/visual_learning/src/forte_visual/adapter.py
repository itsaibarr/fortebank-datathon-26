"""Mapping producer TrackManifest v1/v2 through shared implementations.

The track/annotation mapping is implemented against actual committed interfaces.
The completed-export envelope is provisional until a producer export is received.
"""

from pathlib import Path

from forte.annotations import Annotation
from forte.tracking import TrackManifest, training_targets, validate_pair

from forte_visual.io import digest

MAPPING_VERSION = "forte-track-v1-v2/consumer-3-7d9a1ca"


def mapping_hash():
    return digest(Path(__file__))


def load_pair(manifest_path, annotation_path):
    m = TrackManifest.model_validate_json(manifest_path.read_bytes())
    if m.schema_version not in {1, 2}:
        raise ValueError("Unsupported producer schema mapping")
    a = Annotation.model_validate_json(annotation_path.read_bytes())
    m, a = validate_pair(m, a)
    validate_actor_targets(m, a)
    return m, a


def validate_actor_targets(m, a):
    """Consumer guard for the producer's actorless positive-action bypass.

    Do not alter the producer's annotations or confuse a context assertion with
    a person-action target. Reject the entire release instead of quietly omitting
    its invalid training truth.
    """
    segments = {s.id: s for s in m.segments}
    for fact in a.facts:
        if fact.kind != "action" or fact.review_status != "confirmed":
            continue
        if fact.target_kind != "fact" or fact.observation_state != "observed":
            continue
        if not fact.actor_id or not fact.segment_ids:
            raise ValueError("Positive person-action target requires actor and source segments")
        if any(s not in segments for s in fact.segment_ids) or not all(
            any(
                b.frame_id == f and not b.outside
                for s in fact.segment_ids
                for b in segments[s].boxes
            )
            for f in fact.frame_ids
        ):
            raise ValueError("Positive person-action target lacks participating source geometry")


def development_records(selection_path):
    # Reuse producer's neutral/hash/split projection; do not inspect labels/points
    # or duplicate its allowlist rules. No source decoding occurs here.
    from forte.person_proposals import allowlisted_sources

    return allowlisted_sources(selection_path, selection_path.parent / "neutral")


def reviewed_targets(m, a, *, training=False):
    validate_actor_targets(m, a)
    if training:
        eligible = {f.id for f in training_targets(m, a)}
    else:
        eligible = {f.id for f in a.facts}
    segments = {s.id: s for s in m.segments}
    areas = {x.id: x for x in m.work_areas}
    result = []
    for f in a.facts:
        participating = f.segment_ids + f.counterpart_segment_ids
        if f.id not in eligible or f.review_status != "confirmed":
            continue
        if not f.actor_id or f.target_kind == "unresolved" or f.boundary_uncertain:
            continue
        if f.origin != "human" or not f.reviewer or not f.reviewed_at:
            continue
        if f.target_kind == "abstention" and f.value != "unclear":
            continue
        if f.observation_state not in {"observed", "not_observed_in_reviewed_interval"}:
            if f.target_kind != "abstention":
                continue
        if any(
            segments[s].identity_uncertain or segments[s].review.status != "confirmed"
            for s in participating
        ):
            continue
        if any(
            b.review.status != "confirmed"
            or b.outside
            or (b.occluded and f.target_kind != "abstention")
            for s in participating
            for b in segments[s].boxes
            if b.frame_id in f.frame_ids + f.counterpart_frame_ids
        ):
            continue
        if f.work_area_id and areas[f.work_area_id].review.status != "confirmed":
            continue
        if any(
            j.review.status != "confirmed"
            and {j.from_segment, j.to_segment}.intersection(participating)
            for j in m.joins
        ):
            continue
        overlaps = [
            other
            for other in a.facts
            if other.id != f.id
            and other.kind == f.kind
            and other.actor_id == f.actor_id
            and max(other.start_sec, f.start_sec) <= min(other.end_sec, f.end_sec)
        ]
        # Simultaneous different actions are valid. Contradictory role/context or
        # rejected copies of the same target are not resolved by last-write-wins.
        if any(
            (o.kind != "action" and o.value != f.value)
            or (o.value == f.value and o.review_status == "rejected")
            for o in overlaps
        ):
            continue
        result.append(f)
    return result
