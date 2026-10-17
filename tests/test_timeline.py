"""Synthetic provenance and failure checks; these are not accuracy benchmarks."""

import json
import time

import httpx
import pytest
from PIL import Image
from test_video import make_mov

from forte.inference import LocalVLM
from forte.timeline import (
    EvidenceTools,
    ScanBounds,
    append_correction,
    merge_observations,
    private_directory,
    scan_recording,
    source_frame_table,
    validate_answer,
)
from forte.video import decode_video


def test_participant_prompt_history_is_bounded_without_mutating_registry():
    import copy
    import json

    from forte.timeline import compact_participants

    person = {
        "participant_id": "P1",
        "identity_status": "unreviewed",
        "conflicts": [{"reason": "ambiguous", "score": 0.1234567890123456}] * 1000,
        "visibility_gaps": [[0.123456789, 9.87654321]] * 1000,
        "role_hypotheses": [{"value": "unresolved", "evidence_frame_ids": ["F1"]}] * 1000,
        "track_segments": [
            {
                "segment_id": f"S{i}",
                "observations": [{"frame_id": "F1", "embedding": [0.123456789] * 512}],
            }
            for i in range(1000)
        ],
    }
    original = copy.deepcopy(person)
    compact = compact_participants([person])[0]
    assert len(json.dumps(compact)) < 3000
    assert compact["participant_id"] == "P1"
    assert compact["registry_ref"] == "participant_registry:P1"
    assert compact["history_counts"]["visibility_gaps"] == 1000
    assert compact["history_counts"]["track_segments"] == 1000
    assert len(compact["track_segments"]) == 4
    assert compact["track_segments"][0]["start_frame_id"] == "F1"
    assert person == original


def empty_answer():
    return {
        "observations": [],
        "visibility": "visible_samples",
        "unresolved_questions": [],
        "reinspection_requests": [],
        "capacity_limited": False,
    }


def observation(ids, actor_ids=None):
    return {
        "kind": "action",
        "value": "Synthetic visible action.",
        "start_frame_id": ids[0],
        "end_frame_id": ids[-1],
        "decisive_frame_id": ids[-1],
        "actor_ids": actor_ids or [],
        "recipient_ids": [],
        "evidence_frame_ids": [ids[-1]],
        "visibility": "visible_samples",
        "uncertainty": [],
        "continues_before_window": False,
        "continues_after_window": False,
    }


def test_source_table_uses_actual_vfr_timebase_and_rotation(tmp_path):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov", rotation=90), tmp_path / "cache")
    table = source_frame_table(registry, time.monotonic() + 10)
    assert [r["timestamp_sec"] for r in table["frames"]] == pytest.approx([0, 0.4, 1.1, 2, 3])
    assert all(r["time_base"] and r["oriented_size"] == [64, 96] for r in table["frames"])
    assert table["frames"][2]["source_pts"] == registry.frames[2].source_pts


def test_loopback_adapter_receives_real_images_for_every_hierarchical_phase(tmp_path):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")
    image_counts, routes = [], []

    def respond(request):
        routes.append(request.url.path)
        body = json.loads(request.content)
        if request.url.path == "/tokenize":
            images = [
                part for part in body["messages"][1]["content"] if part["type"] == "image_url"
            ]
            assert images and all(
                p["image_url"]["url"].startswith("data:image/jpeg;base64,") for p in images
            )
            image_counts.append(len(images))
            return httpx.Response(200, json={"count": 800})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(empty_answer())}}
                ],
                "usage": {"total_tokens": 900},
            },
        )

    backend = LocalVLM(
        "http://127.0.0.1:8001", client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    report = scan_recording(
        registry,
        {"participants": [], "frame_boxes": {}},
        backend,
        tmp_path / "scan",
        time.monotonic() + 20,
    )
    assert report["status"] == "complete_schedule"
    assert report["coverage"]["unexamined_intervals"] == []
    assert report["coverage"]["continuous_visibility_validated"] is False
    assert [c["phase"] for c in report["metrics"]["receipts"]] == [
        "overview",
        "window",
        "reconcile",
    ]
    assert image_counts and routes.count("/v1/chat/completions") == 3
    assert json.loads((tmp_path / "scan/view-transforms.json").read_text())


def test_tool_bounds_original_evidence_and_crop_geometry(tmp_path):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov", rotation=90), tmp_path / "cache")
    ref = registry.frames[-1]
    people = {
        "participants": [{"participant_id": "p1"}],
        "frame_boxes": {ref.frame_id: {"p1": [5.2, 10.4, 50.7, 80.1]}},
    }
    tools = EvidenceTools(registry, people, tmp_path / "tools", time.monotonic() + 20)
    refs, mapping = tools.views_for([ref], 196608, crops=True)
    crop = next(v for v in mapping if v["kind"] == "participant_crop")
    assert crop["source_rect"] == [5, 10, 51, 81]
    sx, sy, dx, dy = crop["source_to_view"]
    assert 5 * sx + dx == pytest.approx(0)
    assert 10 * sy + dy == pytest.approx(0)
    assert len(refs) == 2
    with Image.open(
        __import__("io").BytesIO(tools.original_jpegs([ref.frame_id])[ref.frame_id])
    ) as image:
        assert image.size == (64, 96)
    with pytest.raises(ValueError):
        tools.get_clip(-1, 2)
    with pytest.raises(ValueError):
        tools.get_frames(["invented"])
    with pytest.raises(ValueError):
        tools.get_participant_history("other", 0, 2)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.update(decisive_frame_id="invented"),
        lambda o: o.update(actor_ids=["other"]),
        lambda o: o.update(start_frame_id=o["end_frame_id"], end_frame_id="f000000"),
        lambda o: o.update(evidence_frame_ids=["f000000"]),
    ],
)
def test_rejects_invented_frames_actors_reversed_times_and_unbacked_moment(tmp_path, mutate):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")
    answer = empty_answer()
    item = observation([f.frame_id for f in registry.frames])
    mutate(item)
    answer["observations"] = [item]
    with pytest.raises(ValueError):
        validate_answer(answer, registry.frames, [], {})


def test_actor_membership_is_independent_of_known_participant_id(tmp_path):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")
    answer = empty_answer()
    answer["observations"] = [observation([f.frame_id for f in registry.frames], ["p1"])]
    with pytest.raises(ValueError, match="membership"):
        validate_answer(answer, registry.frames, [{"participant_id": "p1"}], {})


def test_budget_exhaustion_preserves_partial_observations_and_unexamined_ranges(tmp_path):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")

    class Synthetic:
        last_usage = {"total_tokens": 100}

        def request(self, *args):
            return empty_answer()

    deadline = time.monotonic() + 20
    report = scan_recording(
        registry, {}, Synthetic(), tmp_path / "scan", deadline, ScanBounds(deadline, max_calls=1)
    )
    assert report["status"] == "budget_exhausted"
    assert report["coverage"]["unexamined_intervals"] == [[0, registry.duration]]
    assert (tmp_path / "scan/reply-001.json").is_file()


def test_dedup_requires_actor_action_overlap_and_shared_evidence():
    base = {
        **observation(["f0", "f2"], ["p1"]),
        "observation_id": "obs1",
        "start_sec": 0,
        "end_sec": 2,
        "decisive_sec": 2,
        "origin": "model",
        "review_status": "unreviewed",
    }
    shared = {**base, "observation_id": "obs2", "end_sec": 3, "end_frame_id": "f3"}
    distinct = {
        **base,
        "observation_id": "obs3",
        "evidence_frame_ids": ["f1"],
        "decisive_frame_id": "f1",
    }
    other_actor = {**base, "observation_id": "obs4", "actor_ids": ["p2"]}
    merged = merge_observations([base, shared, distinct, other_actor])
    assert len(merged) == 3
    assert any(e["observation_ids"] == ["obs1", "obs2"] for e in merged)


def test_correction_revisions_are_immutable_source_bound_and_separate(tmp_path):
    result = {
        "source_sha256": "a" * 64,
        "observations": [{"observation_id": "obs1"}],
        "events": [],
        "participants": [],
    }
    correction = {
        "reviewer": "human",
        "scope": "role",
        "target_id": "obs1",
        "change": {"value": "synthetic correction"},
        "source_sha256": "a" * 64,
        "parent_revision": None,
    }
    first = append_correction(tmp_path / "reviews", result, correction)
    original = first.read_bytes()
    second = append_correction(
        tmp_path / "reviews", result, {**correction, "parent_revision": first.name}
    )
    assert first.read_bytes() == original and second != first
    assert json.loads(second.read_text())["other_scopes_approved"] is False
    assert result["observations"] == [{"observation_id": "obs1"}]
    with pytest.raises(ValueError):
        append_correction(tmp_path / "reviews", result, {**correction, "source_sha256": "b" * 64})
    with pytest.raises(ValueError):
        append_correction(
            tmp_path / "reviews", result, {**correction, "parent_revision": "../escape"}
        )


def test_private_artifacts_cannot_be_placed_inside_checkout():
    from pathlib import Path

    with pytest.raises(ValueError):
        private_directory(Path(__file__).resolve().parents[1] / "private-timeline-test")


def test_output_capacity_is_explicit_and_cannot_become_complete_coverage(tmp_path):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")

    class Limited:
        def request(self, *args):
            return {**empty_answer(), "capacity_limited": True}

    deadline = time.monotonic() + 10
    report = scan_recording(
        registry,
        {},
        Limited(),
        tmp_path / "scan",
        deadline,
        ScanBounds(deadline, max_reinspections=0),
    )
    assert report["status"] == "output_limited"
    assert report["coverage"]["output_capacity_limited_intervals"]
    assert report["coverage"]["pending_reinspections"] == 1
    assert report["coverage"]["unclear_intervals"]
    answer = empty_answer()
    del answer["capacity_limited"]
    with pytest.raises(ValueError):
        validate_answer(answer, registry.frames, [], {})


@pytest.mark.parametrize("later_failure", [False, True])
def test_valid_observations_survive_budget_crossing_or_later_invalid_pass(tmp_path, later_failure):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov"), tmp_path / "cache")

    class Backend:
        calls = 0
        last_usage = {"total_tokens": 101}

        def request(self, _registry, _frames, _instruction, schema, *_args):
            self.calls += 1
            if later_failure and self.calls == 2:
                raise ValueError("Synthetic incomplete response; never parsed")
            ids = schema["$defs"]["Observation"]["properties"]["start_frame_id"]["enum"]
            return {**empty_answer(), "observations": [observation(ids)]}

    deadline = time.monotonic() + 10
    bounds = ScanBounds(deadline, max_tokens=100000 if later_failure else 100)
    report = scan_recording(registry, {}, Backend(), tmp_path / "scan", deadline, bounds)
    assert report["status"] == ("failed_pass" if later_failure else "budget_exhausted")
    assert len(report["observations"]) == 1
    assert report["observations"][0]["source_sha256"] == registry.source_sha256
    assert report["coverage"]["unexamined_intervals"] == [[0, registry.duration]]
    assert json.loads((tmp_path / "scan/observations.json").read_text()) == report["observations"]
