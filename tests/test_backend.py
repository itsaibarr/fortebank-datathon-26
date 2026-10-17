import json

import httpx
import pytest
from test_video import make_mov

from forte.inference import LocalVLM
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
