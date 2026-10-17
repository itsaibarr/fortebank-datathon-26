"""Fetch only public model/framework metadata; never opens competition files."""

import hashlib
import json
import subprocess
from pathlib import Path

MODELS = {
    "8b": ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"),
    "27b": ("Qwen/Qwen3.8-27B", "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"),
}
GITHUB = [
    (
        "QwenLM/Qwen3-VL",
        "96588727e44c78b25ba03ea03b8e12f7e64fd0da",
        "qwen-vl-finetune/qwenvl/train/train_qwen.py",
    ),
    ("QwenLM/Qwen3.8", "2ea10dc725823bf7c3e21ce8557cbe15245132ae", "README.md"),
    ("huggingface/transformers", "v5.17.0", "src/transformers/models/qwen3_5/modeling_qwen3_5.py"),
    (
        "huggingface/transformers",
        "v5.17.0",
        "src/transformers/models/qwen3_vl/processing_qwen3_vl.py",
    ),
    ("vllm-project/vllm", "v0.31.0", "vllm/model_executor/models/qwen3_5.py"),
]


def main():
    sources, candidates = [], {}
    for key, (model, revision) in MODELS.items():
        data = {}
        for name in ("config.json", "preprocessor_config.json", "README.md"):
            url = f"https://huggingface.co/{model}/raw/{revision}/{name}"
            raw = subprocess.check_output(["curl", "-fsSL", "--max-time", "30", url])
            sources.append({"url": url, "sha256": hashlib.sha256(raw).hexdigest()})
            data[name] = raw
        config = json.loads(data["config.json"])
        preprocessor = json.loads(data["preprocessor_config.json"])
        candidates[key] = {
            "model": model,
            "revision": revision,
            "architecture": config["architectures"],
            "processor": preprocessor,
            "license_in_pinned_card": "apache-2.0" in data["README.md"].decode(),
            "training_memory_or_quality_verified": False,
        }
    for repo, revision, path in GITHUB:
        raw = subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/{repo}/contents/{path}?ref={revision}",
                "-H",
                "Accept: application/vnd.github.raw+json",
            ]
        )
        sources.append(
            {
                "url": f"https://github.com/{repo}/blob/{revision}/{path}",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    destination = Path(__file__).resolve().parents[1] / "configs/public-sources.json"
    destination.write_text(
        json.dumps(
            {"checked_at": "2026-10-17", "candidates": candidates, "sources": sources}, indent=2
        )
        + "\n"
    )
    print(json.dumps({"public_sources_checked": len(sources)}))


if __name__ == "__main__":
    main()
