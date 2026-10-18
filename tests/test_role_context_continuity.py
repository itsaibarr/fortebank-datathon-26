"""Earlier source-bound role hypotheses stay available without assigning identities."""

import copy
import json
import time

import pytest
from test_video import make_mov

from forte import timeline
from forte.timeline import (
    ScanBounds,
    compact_participants,
    scan_recording,
)
from forte.video import decode_video


def role(actor, identifier="role-1", **changes):
    return {
        "kind": "role",
        "observation_id": identifier,
        "actor_ids": [actor],
        "value": "Synthetic operational-role hypothesis.",
        "start_sec": 0,
        "end_sec": 9,
        "evidence_frame_ids": ["f0", "f9"],
        "origin": "model",
        "review_status": "unreviewed",
        "source_sha256": "a" * 64,
        "visibility": "visible_samples",
        "uncertainty": ["Synthetic incomplete role interval."],
        **changes,
    }


def observation(ids, actor, *, kind="action", value="Synthetic visible activity."):
    return {
        "kind": kind,
        "value": value,
        "start_frame_id": ids[0],
        "end_frame_id": ids[1],
        "decisive_frame_id": ids[1],
        "actor_ids": [actor],
        "recipient_ids": [],
        "evidence_frame_ids": ids[:2],
        "visibility": "visible_samples",
        "uncertainty": ["Synthetic unresolved role extent."],
        "continues_before_window": False,
        "continues_after_window": False,
    }


@pytest.mark.parametrize("later_invalid", [False, True])
def test_two_people_keep_validated_roles_in_later_context_after_prior_preview_expires(
    tmp_path, later_invalid
):
    registry = decode_video(
        make_mov(tmp_path / "synthetic.mov", pts=range(100, 1541, 10)), tmp_path / "cache"
    )
    people = [
        {"participant_id": actor, "role_hypotheses": [], "track_segments": []}
        for actor in ("p1", "p2")
    ]
    participants = {
        "participants": people,
        "frame_boxes": {
            f.frame_id: {"p1": [1, 1, 20, 40], "p2": [30, 1, 50, 40]} for f in registry.frames
        },
    }
    calls = []

    class Backend:
        last_usage = {"total_tokens": 1}
        last_finish_reason = "stop"

        def request(self, tools, refs, instruction, schema, pixels, tokens):
            context = json.loads(instruction.split("JSON schema. Context: ", 1)[1])
            # Context derivation does not mutate tracking proposals during scanning.
            assert all(person["role_hypotheses"] == [] for person in people)
            calls.append(context)
            ids = [item["frame_id"] for item in context["source_frames"]]
            if len(calls) == 1:
                observations = [
                    observation(
                        ids,
                        actor,
                        kind="role",
                        value="Synthetic shared operational-role hypothesis.",
                    )
                    for actor in ("p1", "p2")
                ]
            elif later_invalid and len(calls) == 8:
                observations = [observation(ids, "unavailable", kind="role")]
            else:
                observations = [
                    observation(ids, actor, value=f"Synthetic call {len(calls)} activity.")
                    for actor in ("p1", "p2")
                ]
            return {
                "observations": observations,
                "visibility": "visible_samples",
                "unresolved_questions": [],
                "reinspection_requests": [],
                "capacity_limited": False,
            }

    deadline = time.monotonic() + 30
    report = scan_recording(
        registry,
        participants,
        Backend(),
        tmp_path / "scan",
        deadline,
        ScanBounds(deadline, max_reinspections=0),
    )
    assert report["status"] == ("failed_pass" if later_invalid else "complete_schedule")
    assert len(calls) >= 8
    late = calls[6]
    assert not any(item["kind"] == "role" for item in late["prior_observations"])
    role_observations = [item for item in report["observations"] if item["kind"] == "role"]
    assert len(role_observations) == 2
    for context in calls[1:]:
        for person in context["participants"]:
            own = next(
                item for item in role_observations if person["participant_id"] in item["actor_ids"]
            )
            history = person["role_hypotheses"]
            assert len(history) == 1
            assert history[0]["observation_id"] == own["observation_id"]
            for key in (
                "start_sec",
                "end_sec",
                "evidence_frame_ids",
                "origin",
                "review_status",
                "uncertainty",
                "visibility",
                "source_sha256",
            ):
                assert history[0][key] == own[key]
            assert "not_current_or_permanent_role_approval" in person["role_history_semantics"]
    assert len(report["participants"]) == 2  # identical role words never join people
    assert all(len(person["role_hypotheses"]) == 1 for person in report["participants"])
    assert all(
        person["role_hypotheses"][0]["review_status"] == "unreviewed"
        for person in report["participants"]
    )


def test_same_observation_enriches_once_but_conflicting_claims_survive_without_mutation():
    original = role("p1")
    partial = {key: original[key] for key in ("observation_id", "value", "start_sec", "end_sec")}
    conflict = {**partial, "value": "Synthetic conflicting role hypothesis."}
    person = {"participant_id": "p1", "role_hypotheses": [partial, conflict]}
    before = copy.deepcopy(person)
    history = timeline.participant_role_history(person, [original, original, role("p2", "role-2")])
    assert person == before
    assert len(history) == 2
    assert history[0]["uncertainty"] == original["uncertainty"]
    assert history[1] == conflict
    assert (
        timeline.participant_role_history({**person, "role_hypotheses": history}, [original])
        == history
    )


def test_bounded_role_context_prefers_overlapping_then_recent_history_without_extending_scope():
    histories = [role("p1", f"role-{i}", start_sec=i * 10, end_sec=i * 10 + 2) for i in range(8)]
    person = {"participant_id": "p1", "role_hypotheses": histories}
    before = copy.deepcopy(person)
    context = compact_participants([person], interval=(0, 1))[0]
    assert len(context["role_hypotheses"]) == 4
    assert [item["observation_id"] for item in context["role_hypotheses"]] == [
        "role-0",
        "role-7",
        "role-6",
        "role-5",
    ]
    assert context["role_hypotheses"][0]["end_sec"] == 2
    assert context["history_counts"]["role_hypotheses"] == 8
    assert person == before
    latest = compact_participants([person])[0]
    assert [item["observation_id"] for item in latest["role_hypotheses"]] == [
        "role-7",
        "role-6",
        "role-5",
        "role-4",
    ]


def test_unknown_person_does_not_inherit_another_persons_role():
    person = {"participant_id": "p2", "role_hypotheses": []}
    assert timeline.participant_role_history(person, [role("p1")]) == []
    assert compact_participants([person], interval=(0, 9))[0]["role_hypotheses"] == []


def test_role_context_preserves_exact_source_time_and_provenance_without_extending_interval():
    original = role(
        "p1",
        start_sec=0.123456789,
        end_sec=0.987654321,
        phase="window",
        localization="sampled_source_envelope_not_exact_action_boundaries",
        start_frame_id="f0",
        end_frame_id="f9",
        decisive_frame_id="f9",
    )
    person = {"participant_id": "p1", "role_hypotheses": []}
    history = timeline.participant_role_history(person, [original])
    record = compact_participants([{**person, "role_hypotheses": history}], interval=(10, 12))[0]
    for key in (
        "start_sec",
        "end_sec",
        "source_sha256",
        "phase",
        "localization",
        "start_frame_id",
        "end_frame_id",
        "decisive_frame_id",
        "uncertainty",
    ):
        assert record["role_hypotheses"][0][key] == original[key]
    assert person["role_hypotheses"] == []
