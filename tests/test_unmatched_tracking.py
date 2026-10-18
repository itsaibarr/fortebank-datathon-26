"""Unassociated detector geometry must not manufacture canonical participants."""

import json
import time

import pytest
from test_frozen_tracking import BOX, SyntheticEmbedder, frames
from test_video import make_mov

from forte.frozen_tracking import TrackingConfig, analyze_participants
from forte.timeline import EvidenceTools, compact_participants, validate_answer
from forte.video import decode_video


class Detector:
    provenance = {"synthetic": True}

    def __init__(self, score=0.2, count=1):
        self.score, self.count = score, count

    def detect(self, image):
        return [(BOX, self.score)] * self.count


class Tracker:
    def __init__(self, ids):
        self.ids = iter(ids)

    def update(self, boxes, timestamp):
        return [(next(self.ids), box, score) for box, score in boxes]


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        "forte.frozen_tracking.require_outbound_blocked", lambda: {"synthetic": True}
    )


def analyze(tmp_path, ids, *, score=0.2, count=1, zones=None, mode="reid"):
    return analyze_participants(
        frames((0, 0.2)),
        tmp_path / "run",
        TrackingConfig(source_sha256="a" * 64, camera_zones=zones or [], mode=mode),
        detector=Detector(score, count),
        tracker=Tracker(ids),
        embedder=SyntheticEmbedder(),
    )


@pytest.mark.parametrize("score", [0.2, 0.9])
def test_unmatched_geometry_is_retained_without_identity_even_with_clear_appearance(
    tmp_path, offline, score
):
    registry = analyze(tmp_path, [-1, -2], score=score)
    assert registry["participants"] == compact_participants(registry["participants"]) == []
    assert registry["frame_boxes"] == {"f000000": {}, "f000001": {}}
    assert len(registry["segments"]) == len(registry["unresolved_matches"]) == 2
    for segment, frame in zip(registry["segments"], frames((0, 0.2)), strict=True):
        assert segment["participant_id"] is None
        assert segment["association_status"] == "unassociated_detection"
        assert segment["gallery"] == []
        observation = segment["observations"][0]
        assert observation["box"] == BOX
        assert observation["frame_id"] == frame.ref.frame_id
        assert observation["source_pts"] == frame.ref.source_pts
        assert observation["geometry_origin"] == "yolox_person_detection"
        assert observation["tracker_id_origin"] is None
        assert observation["geometry_review"] == "unreviewed"
    assert json.loads((tmp_path / "run/participants.json").read_text()) == registry


def test_repeated_unmatched_sentinel_never_links_geometry_across_time_or_same_frame(
    tmp_path, offline
):
    registry = analyze(tmp_path, [-1] * 4, count=2)
    assert len(registry["segments"]) == 4
    assert all(len(s["observations"]) == 1 for s in registry["segments"])
    assert registry["participants"] == []


def test_valid_zero_tracker_identity_does_not_retroactively_claim_unmatched_geometry(
    tmp_path, offline
):
    registry = analyze(tmp_path, [-1, 0], score=0.9)
    assert len(registry["participants"]) == 1
    assert registry["segments"][0]["participant_id"] is None
    assert registry["segments"][1]["participant_id"] == "p0001"
    assert registry["frame_boxes"]["f000000"] == {}
    assert registry["frame_boxes"]["f000001"] == {"p0001": BOX}
    assert registry["participants"][0]["association_evidence"] == []
    assert registry["segments"][1]["observations"][0]["tracker_id_origin"] == (
        "ByteTrack_motion_association"
    )


def test_nonnegative_tracks_without_gallery_remain_explicit_unreviewed_proposals(tmp_path, offline):
    registry = analyze(tmp_path, [0, 0], mode="byte_track")
    assert len(registry["participants"]) == len(registry["segments"]) == 1
    person = registry["participants"][0]
    assert person["appearance_gallery"] == []
    assert person["identity_status"] == "model_proposal"
    assert len(person["track_segments"][0]["observations"]) == 2


def test_unmatched_reflection_retains_view_with_unknown_owner_without_physical_person(
    tmp_path, offline
):
    registry = analyze(
        tmp_path,
        [-1, -2],
        score=0.9,
        zones=[
            {
                "zone_id": "mirror",
                "kind": "reflection",
                "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]],
            }
        ],
    )
    assert registry["participants"] == []
    assert len(registry["view_observations"]) == 2
    assert all(v["canonical_person_id"] is None for v in registry["view_observations"])
    assert all(v["ownership"] == "unknown" for v in registry["view_observations"])


def test_unassociated_registry_keeps_original_scene_evidence_without_actor_crops(tmp_path, offline):
    source = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")
    registry = analyze_participants(
        source,
        tmp_path / "run",
        TrackingConfig(mode="byte_track"),
        detector=Detector(),
        tracker=Tracker([-1] * len(source.frames)),
    )
    tools = EvidenceTools(source, registry, tmp_path / "evidence", time.monotonic() + 10)
    original = tools.original_jpegs([source.frames[0].frame_id])
    assert original[source.frames[0].frame_id]
    refs, views = tools.views_for([source.frames[0]], 196608, crops=True)
    assert len(refs) == len(views) == 1
    assert views[0]["kind"] == "scene"
    assert "participant_id" not in views[0]
    observation = {
        "kind": "action",
        "value": "Synthetic unresolved action.",
        "start_frame_id": source.frames[0].frame_id,
        "end_frame_id": source.frames[0].frame_id,
        "decisive_frame_id": source.frames[0].frame_id,
        "actor_ids": [],
        "recipient_ids": [],
        "evidence_frame_ids": [source.frames[0].frame_id],
        "visibility": "unclear",
        "uncertainty": ["Actor unresolved."],
        "continues_before_window": False,
        "continues_after_window": False,
    }
    answer = {
        "observations": [observation],
        "visibility": "unclear",
        "unresolved_questions": [],
        "reinspection_requests": [],
        "capacity_limited": False,
    }
    assert validate_answer(answer, source.frames, [], registry["frame_boxes"]).observations
    observation["actor_ids"] = ["p0001"]
    with pytest.raises(ValueError, match="unsupplied participant"):
        validate_answer(answer, source.frames, [], registry["frame_boxes"])
