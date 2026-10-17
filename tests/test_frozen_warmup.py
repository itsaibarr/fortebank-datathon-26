"""Warm-up must check the actual served route and selected context budget."""

import json
import runpy
import sys
from pathlib import Path

from forte import inference


def test_warmup_uses_custom_route_and_records_actual_16k_context(tmp_path, monkeypatch):
    calls = []

    class SyntheticLocalModel:
        last_usage = {"prompt_tokens": 800, "completion_tokens": 8}

        def __init__(self, url, *, model, expected_revision, max_context_tokens, enable_thinking):
            self.max_context_tokens = max_context_tokens
            self.loaded = {"route": model, "revision": expected_revision}
            calls.append((url, model, max_context_tokens, enable_thinking))

        def ready(self):
            return True

        def request(self, registry, frames, instruction, schema, pixels, tokens):
            assert len(frames) == 16
            assert registry.image_bytes(frames[0], pixels).startswith(b"\xff\xd8")
            return {"frame_id": f"F{registry.red_index:02}"}

    monkeypatch.setattr(inference, "LocalVLM", SyntheticLocalModel)
    output = tmp_path / "synthetic-warmup.json"
    script = Path(__file__).resolve().parents[1] / "scripts/check_frozen_visual.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "--revision",
            "a" * 40,
            "--model-name",
            "custom-frozen-model",
            "--max-context-tokens",
            "16384",
            "--output",
            str(output),
        ],
    )
    runpy.run_path(str(script), run_name="__main__")
    report = json.loads(output.read_text())
    assert calls == [("http://127.0.0.1:8001", "custom-frozen-model", 16384, False)]
    assert report["max_context_tokens"] == 16384
    assert report["model"]["route"] == "custom-frozen-model"
    assert all(call["correct"] for call in report["calls"])
