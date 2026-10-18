"""Verify chronological source/crop images through the actual request serializer."""

import base64
import hashlib
import json
import re
import time

import httpx
import pytest
from test_video import make_mov

from forte.inference import LocalVLM
from forte.timeline import EvidenceTools
from forte.video import decode_video


def test_source_scenes_and_crops_reach_processor_in_paired_source_pts_order(tmp_path):
    registry = decode_video(make_mov(tmp_path / "synthetic.mov", rotation=90), tmp_path / "cache")
    people = {
        "participants": [{"participant_id": "p1"}],
        "frame_boxes": {
            frame.frame_id: {"p1": [5.2, 10.4, 50.7, 80.1]} for frame in registry.frames
        },
    }
    tools = EvidenceTools(registry, people, tmp_path / "tools", time.monotonic() + 20)
    frames = tools.get_frames([frame.frame_id for frame in registry.frames])
    refs, mapping = tools.views_for(frames, 393216, crops=True)
    assert len(refs) == 9
    assert [ref.timestamp_sec for ref in refs] == sorted(ref.timestamp_sec for ref in refs)
    assert [ref.frame_id for ref in refs] == [item["view_id"] for item in mapping]
    for frame in frames:
        same_source = [item for item in mapping if item["source_frame_id"] == frame.frame_id]
        assert same_source[0]["kind"] == "scene"
    for item in mapping:
        raw = tools.payloads[item["view_id"]]
        assert item["jpeg_sha256"] == hashlib.sha256(raw).hexdigest()
        x1, y1, x2, y2 = item["source_rect"]
        sx, sy, dx, dy = item["source_to_view"]
        assert [x1 * sx + dx, y1 * sy + dy] == pytest.approx([0, 0])
        assert [x2 * sx + dx, y2 * sy + dy] == pytest.approx(item["size"])
        assert item["rotation_degrees"] == 90
    actual_routes = []

    def respond(request):
        actual_routes.append(request.url.path)
        body = json.loads(request.content)
        parts = body["messages"][1]["content"]
        labels, images = parts[1::2], parts[2::2]
        assert len(labels) == len(images) == len(refs)
        for label, image, ref, item in zip(labels, images, refs, mapping, strict=True):
            match = re.fullmatch(r"Frame (.+) at ([0-9.]+)s:", label["text"])
            assert match and match[1] == item["view_id"] == ref.frame_id
            assert float(match[2]) == pytest.approx(ref.timestamp_sec)
            raw = base64.b64decode(image["image_url"]["url"].split(",", 1)[1])
            assert hashlib.sha256(raw).hexdigest() == item["jpeg_sha256"]
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 800})
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                "usage": {"total_tokens": 900},
            },
        )

    backend = LocalVLM(
        "http://127.0.0.1:8001", client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    assert (
        backend.request(
            tools, refs, "Synthetic ordered sequence.", {"type": "object"}, 393216, 1200
        )
        == {}
    )
    assert actual_routes == ["/tokenize", "/v1/chat/completions"]
