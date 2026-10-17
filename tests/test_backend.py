import json

import httpx
import pytest
from test_video import make_mov

from forte.contracts import EventObservation
from forte.inference import LocalVLM
from forte.rules import load_rules
from forte.video import decode_video, sample_window


def test_external_inference_or_redirect_is_never_allowed():
    with pytest.raises(ValueError):
        LocalVLM("https://external.example/v1")
    with pytest.raises(ValueError):
        LocalVLM("http://127.0.0.1.example/v1")


def test_token_budget_and_frame_references_are_checked(tmp_path):
    registry = decode_video(make_mov(tmp_path / "s.mov"), tmp_path / "frames")
    frames = sample_window(registry, 0, registry.duration, 1)
    calls = []

    def response(request):
        calls.append(request.url.path)
        body = json.loads(request.content)
        assert "image_url" in str(body)
        assert "source.mov" not in str(body)
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 8190})
        raise AssertionError("Over-budget input must not reach generation")

    client = httpx.Client(transport=httpx.MockTransport(response))
    backend = LocalVLM("http://127.0.0.1:8001", client=client)
    with pytest.raises(ValueError, match="context"):
        backend.analyze(registry, frames, [], 196608, 256)
    assert calls == ["/tokenize"]


def test_generation_schema_forbids_unsupplied_frame_and_condition_ids(tmp_path):
    from jsonschema import Draft202012Validator, ValidationError

    registry = decode_video(make_mov(tmp_path / "s.mov"), tmp_path / "frames")
    frames = sample_window(registry, 0, registry.duration, 1)
    captured = {}

    def response(request):
        body = json.loads(request.content)
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 100})
        captured.update(body["structured_outputs"]["json"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"complete":true,"events":[]}'},
                    }
                ],
                "usage": {},
            },
        )

    backend = LocalVLM(
        "http://127.0.0.1:8001", client=httpx.Client(transport=httpx.MockTransport(response))
    )
    backend.analyze(registry, frames, [{"id": "allowed", "required": ["observed"]}], 196608, 256)
    validator = Draft202012Validator(captured)
    event = {
        "rule_id": "allowed",
        "start_id": frames[0].frame_id,
        "end_id": frames[-1].frame_id,
        "decisive_id": frames[0].frame_id,
        "evidence_ids": [frames[0].frame_id],
        "visible_facts": "Synthetic",
        "preconditions": ["observed"],
    }
    validator.validate({"complete": True, "events": [event]})
    with pytest.raises(ValidationError):
        validator.validate({"complete": True, "events": [{**event, "start_id": "invented"}]})
    with pytest.raises(ValidationError):
        validator.validate({"complete": True, "events": [{**event, "preconditions": ["invented"]}]})


def test_role_check_precedes_and_does_not_receive_the_proposed_story(tmp_path):
    registry = decode_video(make_mov(tmp_path / "s.mov"), tmp_path / "frames")
    frames = sample_window(registry, 0, registry.duration, 1)
    marker = "SYNTHETIC_HYPOTHESIS_MARKER"
    event = EventObservation(
        rule_id="service_departure",
        start_id=frames[0].frame_id,
        end_id=frames[-1].frame_id,
        decisive_id=frames[-1].frame_id,
        evidence_ids=[frames[-1].frame_id],
        visible_facts=marker,
        preconditions=[],
    )
    generations = []

    def response(request):
        body = json.loads(request.content)
        assert marker not in json.dumps(body["messages"])
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 100})
        generations.append(body)
        answer = {"role": "unclear", "role_evidence_ids": [], "continuity_supported": False}
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}]
            },
        )

    backend = LocalVLM(
        "http://127.0.0.1:8001", client=httpx.Client(transport=httpx.MockTransport(response))
    )
    check = backend.verify(registry, frames, event, load_rules()[0])
    assert check.verdict == "unclear"
    assert len(generations) == 1


def test_role_grounding_is_bound_to_source_frames_and_preserved_after_rule_check(tmp_path):
    from jsonschema import Draft202012Validator, ValidationError

    registry = decode_video(make_mov(tmp_path / "s.mov"), tmp_path / "frames")
    frames = sample_window(registry, 0, registry.duration, 1)
    rule = load_rules()[0]
    event = EventObservation(
        rule_id=rule["id"],
        start_id=frames[0].frame_id,
        end_id=frames[-1].frame_id,
        decisive_id=frames[-1].frame_id,
        evidence_ids=[frames[-1].frame_id],
        visible_facts="Synthetic hypothesis",
        preconditions=[],
    )
    generated = []

    def response(request):
        body = json.loads(request.content)
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 100})
        generated.append(body)
        if len(generated) == 1:
            answer = {
                "role": "cashier",
                "role_evidence_ids": [frames[0].frame_id],
                "continuity_supported": True,
            }
            validator = Draft202012Validator(body["structured_outputs"]["json"])
            validator.validate(answer)
            with pytest.raises(ValidationError):
                validator.validate({**answer, "role_evidence_ids": ["invented"]})
        else:
            assert "Synthetic hypothesis" in json.dumps(body["messages"])
            assert "actor" not in body["structured_outputs"]["json"]["properties"]
            answer = {
                "verdict": "supported",
                "evidence_ids": [event.decisive_id],
                "preconditions": rule["required"],
            }
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}],
                "usage": {"total_tokens": 10 * len(generated)},
            },
        )

    backend = LocalVLM(
        "http://127.0.0.1:8001", client=httpx.Client(transport=httpx.MockTransport(response))
    )
    check = backend.verify(registry, frames, event, rule)
    assert len(generated) == 2
    assert check.verdict == "supported"
    assert check.actor.role == "cashier"
    assert check.actor.role_evidence_ids == [frames[0].frame_id]
    assert backend.last_actor_usage == {"total_tokens": 10}
    assert backend.last_usage == {"total_tokens": 20}
