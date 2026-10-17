"""Synthetic continuity and training-gate cases; no competition media."""

import copy

import pytest

from forte.annotations import Annotation
from forte.tracking import Box, SegmentBuilder, TrackManifest, training_targets, transform_box


def test_box_transforms_preserve_oriented_full_frame_and_reject_bad_boxes():
    assert transform_box([64, 36, 320, 180], scale=0.5, width=1280, height=720) == (
        0.1,
        0.1,
        0.5,
        0.5,
    )
    assert transform_box(
        [74, 56, 330, 200], scale=0.5, width=1280, height=720, offset=(10, 20)
    ) == (0.1, 0.1, 0.5, 0.5)
    for box in [[0.4, 0, 0.2, 1], [-0.1, 0, 1, 1], [0, 0, float("nan"), 1]]:
        with pytest.raises(ValueError):
            Box(frame_id="f000000", xyxy=box)


def test_windows_do_not_reset_ids_and_gaps_create_separate_unverified_segments():
    b = SegmentBuilder(cadence_sec=0.2)
    b.update("f000000", 0, [(7, (0.1, 0.1, 0.3, 0.7), 0.9)])
    first = b.segments[0]
    # Same builder is consumed across any analysis window boundaries.
    b.update("f000001", 0.2, [(7, (0.11, 0.1, 0.31, 0.7), 0.9)])
    assert len(b.segments) == 1
    b.update("f000002", 0.4, [])
    b.update("f000003", 0.6, [(7, (0.12, 0.1, 0.32, 0.7), 0.8)])
    assert len(b.segments) == 2
    assert b.segments[1].person_id != first.person_id
    assert b.joins[0].review.status == "draft"
    assert b.joins[0].reason == "missed_detection_or_occlusion"
    assert b.gaps[0].start_sec == 0.2 and b.gaps[0].end_sec == 0.6


def test_crossing_and_uncertain_reentry_never_silently_transfer_identity():
    b = SegmentBuilder(cadence_sec=0.2)
    b.update("f000000", 0, [(1, (0.1, 0.1, 0.4, 0.9), 0.9), (2, (0.6, 0.1, 0.9, 0.9), 0.9)])
    b.update("f000001", 0.2, [(1, (0.3, 0.1, 0.6, 0.9), 0.9), (2, (0.4, 0.1, 0.7, 0.9), 0.9)])
    assert len(b.segments) == 4
    assert len(b.joins) == 2
    assert all(j.review.status == "draft" for j in b.joins)
    b.update("f000002", 0.4, [])
    b.update("f000003", 2, [(3, (0.3, 0.1, 0.6, 0.9), 0.9)])
    assert b.segments[-1].person_id not in {s.person_id for s in b.segments[:-1]}
    assert any(j.reason == "possible_reentry" for j in b.joins)


def pair():
    manifest = dict(
        schema_version=1,
        clip_id="clip000",
        source_sha256="0" * 64,
        annotation_file="annotation.json",
        annotation_sha256="1" * 64,
        duration_sec=2,
        source_width=100,
        source_height=50,
        oriented_width=100,
        oriented_height=50,
        rotation=0,
        time_base="1/10",
        frames=[
            dict(frame_id="f000000", ordinal=0, source_pts=10, timestamp_sec=0),
            dict(frame_id="f000001", ordinal=1, source_pts=20, timestamp_sec=1),
        ],
        detection_frame_ids=["f000000", "f000001"],
        cadence_sec=1,
        segments=[
            dict(
                id="s0001",
                person_id="p0001",
                upstream_id=1,
                boxes=[
                    dict(frame_id="f000000", xyxy=[0.1, 0.1, 0.4, 0.9]),
                    dict(frame_id="f000001", xyxy=[0.1, 0.1, 0.4, 0.9]),
                ],
            )
        ],
        recording_group="0" * 64,
        regression_only=False,
    )
    annotation = Annotation(
        source_sha256="0" * 64,
        duration_sec=2,
        frames={"f000000": 0, "f000001": 1},
        facts=[],
        claims=[],
    )
    return manifest, annotation


def test_source_pts_and_box_bindings_reject_mutation_or_inconsistent_times():
    raw, _ = pair()
    TrackManifest.model_validate(raw)
    for change in ["frame", "time", "box"]:
        bad = copy.deepcopy(raw)
        if change == "frame":
            bad["segments"][0]["boxes"][0]["frame_id"] = "missing"
        if change == "time":
            bad["frames"][1]["timestamp_sec"] = 0.5
        if change == "box":
            bad["segments"][0]["boxes"][0]["xyxy"] = [0.4, 0.1, 0.1, 0.9]
        with pytest.raises(ValueError):
            TrackManifest.model_validate(bad)


def test_draft_regression_and_unfrozen_targets_are_ineligible():
    raw, a = pair()
    m = TrackManifest.model_validate(raw)
    assert training_targets(m, a) == []
    a.facts.append(dict())  # mutation cannot bypass validation
    with pytest.raises(ValueError):
        training_targets(m, a)


def test_role_cannot_inherit_across_a_proposed_join_or_invalid_interval():
    raw, a = pair()
    raw["segments"].append(
        dict(
            id="s0002",
            person_id="p0002",
            upstream_id=2,
            boxes=[dict(frame_id="f000001", xyxy=[0.5, 0.1, 0.8, 0.9])],
        )
    )
    raw["joins"] = [
        dict(id="j1", from_segment="s0001", to_segment="s0002", reason="possible_reentry")
    ]
    m = TrackManifest.model_validate(raw)
    from forte.tracking import validate_pair

    a.facts = [
        dict(
            id="role",
            kind="role",
            actor_id="p0001",
            value="cashier",
            start_sec=0,
            end_sec=1,
            frame_ids=["f000000", "f000001"],
            continuity_supported=True,
            segment_ids=["s0001", "s0002"],
        )
    ]
    with pytest.raises(ValueError, match="identity|join"):
        validate_pair(m, a)
    a.facts[0]["segment_ids"] = ["s0001"]
    a.facts[0]["end_sec"] = 3
    with pytest.raises(ValueError):
        validate_pair(m, a)


def test_conflicting_reviewed_roles_cannot_silently_replace_same_person():
    from forte.annotations import VisualFact
    from forte.tracking import validate_pair

    raw, a = pair()
    for value in ["cashier", "customer"]:
        a.facts.append(
            VisualFact(
                id=value,
                kind="role",
                value=value,
                actor_id="p0001",
                start_sec=0,
                end_sec=1,
                frame_ids=["f000000", "f000001"],
                continuity_supported=True,
                segment_ids=["s0001"],
            )
        )
    with pytest.raises(ValueError, match="Conflicting"):
        validate_pair(TrackManifest.model_validate(raw), a)


def test_role_review_does_not_approve_geometry_or_identity_for_training():
    from datetime import UTC, datetime

    from forte.annotations import VisualFact
    from forte.tracking import Review, WorkArea

    raw, a = pair()
    raw.update(
        training_eligible=True,
        session_group="synthetic-session",
        split="train",
        split_frozen=True,
        exclusion_reasons=[],
    )
    m = TrackManifest.model_validate(raw)
    reviewed = Review(
        status="confirmed", reviewer="synthetic reviewer", reviewed_at=datetime.now(UTC)
    )
    m.work_areas = [
        WorkArea(
            id="area1",
            frame_ids=["f000000", "f000001"],
            points=[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9)],
            review=reviewed,
        )
    ]
    a.facts = [
        VisualFact(
            id="role",
            kind="role",
            actor_id="p0001",
            value="cashier",
            start_sec=0,
            end_sec=1,
            frame_ids=["f000000", "f000001"],
            continuity_supported=True,
            segment_ids=["s0001"],
            work_area_id="area1",
            review_status="confirmed",
            reviewer="synthetic reviewer",
            reviewed_at=datetime.now(UTC),
            origin="human",
            visible_basis="Synthetic service sequence",
            visibility_limits="Synthetic clear view",
            playback_interval=(0, 2),
            observation_state="observed",
            target_kind="fact",
        )
    ]
    assert training_targets(m, a) == []
    m.segments[0].review = reviewed
    assert training_targets(m, a) == []
    for box in m.segments[0].boxes:
        box.review = reviewed
    assert len(training_targets(m, a)) == 1
    m.segments[0].identity_uncertain = True
    assert training_targets(m, a) == []
    m.segments[0].identity_uncertain = False
    m.regression_only = True
    with pytest.raises(ValueError, match="eligibility"):
        training_targets(m, a)


def test_counterpart_identity_requires_boxes_during_the_action():
    from forte.annotations import VisualFact
    from forte.tracking import validate_pair

    raw, a = pair()
    raw["segments"].append(
        dict(
            id="s0002",
            person_id="p0002",
            upstream_id=2,
            boxes=[dict(frame_id="f000001", xyxy=[0.5, 0.1, 0.8, 0.9])],
        )
    )
    m = TrackManifest.model_validate(raw)
    a.facts = [
        VisualFact(
            id="action",
            kind="action",
            actor_id="p0001",
            value="handing_over_cash",
            start_sec=0,
            end_sec=0,
            frame_ids=["f000000"],
            segment_ids=["s0001"],
            counterpart_actor_id="p0002",
        )
    ]
    with pytest.raises(ValueError, match="Counterpart"):
        validate_pair(m, a)


def test_confirmed_unclear_role_requires_explicit_abstention_target():
    from datetime import UTC, datetime

    from forte.annotations import VisualFact
    from forte.tracking import Review, WorkArea

    raw, a = pair()
    raw.update(
        training_eligible=True,
        session_group="synthetic-session",
        split="train",
        split_frozen=True,
        exclusion_reasons=[],
    )
    m = TrackManifest.model_validate(raw)
    reviewed = Review(
        status="confirmed", reviewer="synthetic reviewer", reviewed_at=datetime.now(UTC)
    )
    m.work_areas = [
        WorkArea(
            id="area1",
            frame_ids=["f000000"],
            points=[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9)],
            review=reviewed,
        )
    ]
    m.segments[0].review = reviewed
    for box in m.segments[0].boxes:
        box.review = reviewed
    a.facts = [
        VisualFact(
            id="role",
            kind="role",
            actor_id="p0001",
            value="unclear",
            start_sec=0,
            end_sec=1,
            frame_ids=["f000000", "f000001"],
            segment_ids=["s0001"],
            work_area_id="area1",
            review_status="confirmed",
            reviewer="synthetic reviewer",
            reviewed_at=datetime.now(UTC),
            origin="human",
            visible_basis="Insufficient synthetic view",
            visibility_limits="Context absent",
            playback_interval=(0, 2),
            observation_state="observed",
            target_kind="fact",
        )
    ]
    assert training_targets(m, a) == []
    a.facts[0].target_kind = "abstention"
    assert len(training_targets(m, a)) == 1


def test_aggregate_counts_labels_without_calling_segments_distinct_people():
    from forte.annotations import VisualFact
    from forte.tracking_cli import aggregate

    raw, a = pair()
    m = TrackManifest.model_validate(raw)
    a.facts = [
        VisualFact(
            id="action",
            kind="action",
            actor_id="p0001",
            value="synthetic_action",
            start_sec=0,
            end_sec=1,
            frame_ids=["f000000"],
            segment_ids=["s0001"],
        )
    ]
    report = aggregate([({"clip_id": "clip000"}, m)], annotations=[a])
    assert report["pending_actions"] == 1
    assert report["confirmed_actions"] == 0
    assert report["people_reviewed"] is None
    assert report["human_unreviewed_sec"] == 2
