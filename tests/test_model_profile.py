"""Synthetic asset inventories verify fail-closed snapshot identity checks."""

import json

import httpx
import pytest

from forte.inference import LocalVLM
from forte.model_profile import PROFILES, hash_file, verify_snapshot


@pytest.fixture
def snapshot(tmp_path):
    spec = PROFILES["frozen27b"]
    root = tmp_path / spec["revision"]
    root.mkdir()
    payloads = {
        "config.json": {
            "architectures": [spec["architecture"]],
            "vision_config": {"depth": 27},
            "text_config": {"dtype": "bfloat16"},
        },
        "preprocessor_config.json": {"processor_class": "synthetic"},
        "tokenizer_config.json": {},
        "model.safetensors.index.json": {
            "weight_map": {"a": "a.safetensors", "b": "b.safetensors"}
        },
    }
    for name, data in payloads.items():
        (root / name).write_text(json.dumps(data))
    for name in ("a.safetensors", "b.safetensors"):
        (root / name).write_bytes(b"synthetic hash fixture; not a loadable model")
    manifest = {
        "model": spec["checkpoint"],
        "revision": spec["revision"],
        "files": {p.name: hash_file(p) for p in root.iterdir()},
    }
    (root / "model-hashes.json").write_text(json.dumps(manifest))
    return root


def test_frozen_manifest_requires_all_indexed_shards(snapshot):
    assert verify_snapshot(snapshot, "frozen27b")["all_weight_hashes_verified"]
    path = snapshot / "model-hashes.json"
    manifest = json.loads(path.read_text())
    del manifest["files"]["b.safetensors"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="shard inventory"):
        verify_snapshot(snapshot, "frozen27b")


def test_changed_weights_and_text_only_configs_fail(snapshot):
    (snapshot / "a.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="fingerprint"):
        verify_snapshot(snapshot, "frozen27b")
    config = json.loads((snapshot / "config.json").read_text())
    config["language_model_only"] = True
    (snapshot / "config.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="multimodal"):
        verify_snapshot(snapshot, "frozen27b")


def test_config_must_declare_bf16(snapshot):
    config = json.loads((snapshot / "config.json").read_text())
    config["text_config"]["dtype"] = "float16"
    (snapshot / "config.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="BF16"):
        verify_snapshot(snapshot, "frozen27b")


@pytest.mark.parametrize("suffix,parent", [("/adapter", None), ("", "base-route")])
def test_readiness_rejects_adapter_routes_even_with_revision_in_path(suffix, parent):
    revision = PROFILES["baseline8b"]["revision"]

    def reply(request):
        return httpx.Response(
            200,
            json={}
            if request.url.path == "/health"
            else {
                "data": [
                    {"id": "forte-vlm", "root": "/models/" + revision + suffix, "parent": parent}
                ]
            },
        )

    backend = LocalVLM(
        "http://localhost:8001", client=httpx.Client(transport=httpx.MockTransport(reply))
    )
    assert not backend.ready()
