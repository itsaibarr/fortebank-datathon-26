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
        backend.request(registry, frames, "Synthetic observation", {"type": "object"}, 196608, 256)
    assert calls == ["/tokenize"]
