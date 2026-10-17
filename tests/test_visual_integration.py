"""Synthetic boundary tests; none of these fake weights establish model loading."""

import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from test_video import make_mov

from forte.live_tracking import automatic_tracks
from forte.person_proposals import sha256
from forte.video import decode_video
from forte.visual_pipeline import analyze_visual
from forte.visual_runtime import ResidentScanner, VisualConfig, identity, model_command


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def config(tmp_path):
    base = tmp_path / "base"
    save(base / "config.json", {"architectures": ["Qwen3VLForConditionalGeneration"]})
    (base / "model.safetensors").write_bytes(b"synthetic fixture - not actual model weights")
    save(
        base / "model-hashes.json",
        {
            "model": "Qwen/Qwen3-VL-8B-Instruct",
            "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
            "files": {p.name: sha256(p) for p in base.iterdir()},
        },
    )
    adapter = tmp_path / "training/adapter"
    save(adapter / "adapter_config.json", {"peft_type": "LORA", "r": 8, "lora_alpha": 16})
    (adapter / "adapter_model.safetensors").write_bytes(b"synthetic fixture - not trained")
    save(
        adapter.parent / "training.json",
        {
            "base_hash_manifest": sha256(base / "model-hashes.json"),
            "adapter_files": {p.name: sha256(p) for p in adapter.iterdir()},
        },
    )
    return VisualConfig(
        candidate="8b",
        mode="tuned",
        base=base,
        base_manifest_sha256=sha256(base / "model-hashes.json"),
        adapter=adapter,
        training_receipt_sha256=sha256(adapter.parent / "training.json"),
        detector_weights=tmp_path / "detector.onnx",
        legal_release=tmp_path / "legal",
        rule_cards=tmp_path / "cards.json",
        rule_policy=tmp_path / "policy.json",
    )


def test_explicit_adapter_cannot_fall_back_and_base_control_is_distinct(config):
    tuned = identity(config)
    assert tuned["route"].startswith("forte-tuned-")
    assert "--enable-lora" in model_command(config)
    control = config.model_copy(
        update={"mode": "base_control", "adapter": None, "training_receipt_sha256": None}
    )
    assert identity(control)["route"] != tuned["route"]
    assert "--enable-lora" not in model_command(control)
    (config.adapter / "adapter_model.safetensors").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        identity(config)


def test_adapter_wrong_base_and_changed_content_rejected(config):
    path = config.adapter.parent / "training.json"
    receipt = json.loads(path.read_bytes())
    receipt["base_hash_manifest"] = "f" * 64
    save(path, receipt)
    config.training_receipt_sha256 = sha256(path)
    with pytest.raises(ValueError, match="another base"):
        identity(config)
    receipt["base_hash_manifest"] = config.base_manifest_sha256
    save(path, receipt)
    config.training_receipt_sha256 = sha256(path)
    (config.adapter / "adapter_model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="content"):
        identity(config)


def engine(config, *, wrong_route=False):
    loaded = identity(config)
    requests = []

    def respond(request):
        body = json.loads(request.content) if request.content else {}
        requests.append((request.url.path, body))
        if request.url.path == "/health":
            data = {}
        elif request.url.path == "/v1/models":
            data = {
                "data": [
                    {"id": loaded["base_route"], "root": str(config.base)},
                    {
                        "id": loaded["route"],
                        "root": str(config.adapter),
                        "parent": loaded["base_route"],
                    },
                ]
            }
        elif request.url.path == "/tokenize":
            data = {"count": 100}
        else:
            data = {
                "model": loaded["base_route"] if wrong_route else loaded["route"],
                "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            }
        return httpx.Response(200, json=data)

    return ResidentScanner(
        config, client=httpx.Client(transport=httpx.MockTransport(respond)), require_memory=False
    ), requests


def test_admission_requires_multimodal_warmup_on_exact_adapter_route(config):
    backend, requests = engine(config)
    assert not backend.ready()
    assert backend.warm() and backend.ready()
    generation = [b for p, b in requests if p == "/v1/chat/completions"]
    assert generation and all(b["model"] == backend.loaded["route"] for b in generation)
    assert generation[0]["messages"][0]["content"][1]["type"] == "image_url"
    (config.base / "model.safetensors").write_bytes(b"mutated")
    assert not backend.ready()


def test_old_base_response_is_never_accepted_as_tuned(config):
    backend, _ = engine(config, wrong_route=True)
    assert not backend.warm()
    assert not backend.ready()


class Detector:
    provenance = {"synthetic": True}

    def detect(self, image):
        return [((0.1, 0.1, 0.4, 0.9), 0.9)]


class Tracker:
    def update(self, boxes, timestamp):
        return [(1, box, score) for box, score in boxes]


def test_automatic_upload_tracking_has_no_allowlist_or_review_labels(tmp_path):
    registry = decode_video(make_mov(tmp_path / "never-seen.mov"), tmp_path / "frames")
    m = automatic_tracks(
        registry, None, time.monotonic() + 10, detector=Detector(), tracker=Tracker()
    )
    assert m.source_sha256 == registry.source_sha256
    assert {f.frame_id for f in registry.frames if f.frame_id in registry.cached} <= {
        b.frame_id for s in m.segments for b in s.boxes
    }
    assert not m.training_eligible and not m.role_bindings
    assert all(s.review.status == "draft" for s in m.segments)
    assert [f.source_pts for f in m.frames] == [f.source_pts for f in registry.frames]


def test_empty_live_scan_keeps_private_model_provenance_and_fails_unknown(tmp_path, monkeypatch):
    import forte.visual_pipeline as module

    source = make_mov(tmp_path / "upload.mov")
    work = tmp_path / "job"
    work.mkdir()

    class Backend:
        loaded = {"base_manifest_sha256": "a" * 64, "training_receipt_sha256": "b" * 64}
        warm_receipt = {"synthetic": True}
        model = "synthetic-adapter-route"
        config = SimpleNamespace(detector_weights=None)

        def ready(self):
            return True

        def __call__(self, case, root, timeout):
            return {"facts": [], "proposals": [], "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(module, "temporal_checks", lambda *args: {"checks": []})

    def track(registry, weights, deadline):
        return automatic_tracks(registry, weights, deadline, detector=Detector(), tracker=Tracker())

    with pytest.raises(ValueError, match="insufficient_evidence"):
        analyze_visual(source, work, uuid4(), Backend(), time.monotonic() + 20, tracking=track)
    assert json.loads((work / "model-provenance.json").read_bytes())["loaded"] == Backend.loaded
    assert (work / "private-timeline.json").exists()
