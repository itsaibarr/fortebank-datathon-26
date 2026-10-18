"""Check frozen local multimodal assets before serving; never downloads weights."""

import hashlib
import json
from pathlib import Path

SELECTED_MODEL = {
    "checkpoint": "Qwen/Qwen3-VL-8B-Instruct",
    "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
    "architecture": "Qwen3VLForConditionalGeneration",
}


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_snapshot(root: Path, *, verify_weights=True) -> dict:
    """A hash manifest establishes bytes/provenance, not model accuracy."""
    spec = SELECTED_MODEL
    root = root.resolve()
    manifest_path = root / "model-hashes.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("model") != spec["checkpoint"] or manifest.get("revision") != spec["revision"]:
        raise ValueError("Model snapshot differs from selected profile")
    config = json.loads((root / "config.json").read_text())
    if (
        spec["architecture"] not in config.get("architectures", [])
        or not config.get("vision_config")
        or config.get("language_model_only", False)
        or config.get("quantization_config")
    ):
        raise ValueError("Expected the frozen BF16 multimodal architecture")
    dtype = config.get("text_config", config).get("dtype", config.get("torch_dtype"))
    if dtype != "bfloat16":
        raise ValueError("Expected BF16 frozen weight configuration")
    if root.name != spec["revision"]:
        raise ValueError("Serve a path whose final component is the pinned revision")
    inventory = manifest.get("files", {})
    required = {"config.json", "preprocessor_config.json", "tokenizer_config.json"}
    if not required <= inventory.keys() or not any(n.endswith(".safetensors") for n in inventory):
        raise ValueError("Model manifest lacks required visual/tokenizer/weight assets")
    actual_weights = {p.name for p in root.glob("*.safetensors")}
    listed_weights = {n for n in inventory if n.endswith(".safetensors")}
    index = root / "model.safetensors.index.json"
    if index.exists():
        shards = set(json.loads(index.read_text()).get("weight_map", {}).values())
        if not shards or shards != actual_weights or shards != listed_weights:
            raise ValueError("Model index and frozen shard inventory differ")
        if index.name not in inventory:
            raise ValueError("Model weight index is not hash bound")
    elif actual_weights != listed_weights or len(listed_weights) != 1:
        raise ValueError("Unindexed model weights differ from frozen manifest")
    for name, expected in inventory.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Unsafe or missing model asset")
        if (verify_weights or not name.endswith(".safetensors")) and hash_file(path) != expected:
            raise ValueError("Model asset fingerprint changed")
    return {
        **spec,
        "manifest_sha256": hash_file(manifest_path),
        "architecture": config["architectures"],
        "precision": "bfloat16",
        "quantization": None,
        "adapters": [],
        "weights_frozen": True,
        "visual_processor": json.loads((root / "preprocessor_config.json").read_text()),
        "assets_verified": len(inventory),
        "all_weight_hashes_verified": verify_weights,
        "model_path": str(root),
    }
