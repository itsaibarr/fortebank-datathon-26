"""Prepare official public pretrained OSNet weights for frozen local inference.

Run in a public-only staging environment, without private media/job mounts.
This downloads public model assets and exports frozen eval features; it performs
no training, optimizer update or case-dependent weight adaptation.
"""

import argparse
import hashlib
import importlib.util
import json
import urllib.request
from pathlib import Path

REPOSITORY = "KaiyangZhou/deep-person-reid"
CODE_REVISION = "f8cd150fdf77e8d9e1ed143b7f308c2c609ded50"
MODEL_REVISION = "a5c5cc037c24235cda3b21085b93ad77c9616224"
CHECKPOINT = (
    "osnet_x0_25_msmt17_combineall_256x128_amsgrad_ep150_stp60_"
    "lr0.0015_b64_fb10_softmax_labelsmooth_flip_jitter.pth"
)
MODEL_URL = f"https://huggingface.co/kaiyangzhou/osnet/resolve/{MODEL_REVISION}/{CHECKPOINT}"
CODE_URL = (
    f"https://raw.githubusercontent.com/{REPOSITORY}/{CODE_REVISION}/torchreid/models/osnet.py"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url, path):
    if not path.exists():
        with urllib.request.urlopen(url, timeout=60) as source:
            path.write_bytes(source.read())
    return digest(path)


def main():
    import numpy as np
    import onnxruntime as ort
    import torch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any((p / ".git").exists() for p in (output, *output.parents)):
        raise ValueError("Model artifacts belong outside Git")
    code, checkpoint, exported = output / "osnet.py", output / CHECKPOINT, output / "osnet.onnx"
    code_sha = download(CODE_URL, code)
    checkpoint_sha = download(MODEL_URL, checkpoint)
    license_sha = download(
        f"https://raw.githubusercontent.com/{REPOSITORY}/{CODE_REVISION}/LICENSE",
        output / "LICENSE",
    )
    spec = importlib.util.spec_from_file_location("public_osnet", code)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.osnet_x0_25(num_classes=1041, pretrained=False)
    loaded = torch.load(checkpoint, map_location="cpu", weights_only=True)
    state = loaded.get("state_dict", loaded)
    state = {k.removeprefix("module."): v for k, v in state.items()}
    body = {k: v for k, v in state.items() if not k.startswith("classifier.")}
    missing, unexpected = model.load_state_dict(body, strict=False)
    if set(missing) != {"classifier.weight", "classifier.bias"} or unexpected:
        raise ValueError("Every pretrained feature-extractor parameter must match exactly")
    model.eval().requires_grad_(False)
    torch.set_num_threads(2)
    # Synthetic deterministic input verifies export, never evaluates private media.
    generator = torch.Generator().manual_seed(2601)
    tensor = torch.randn((1, 3, 256, 128), generator=generator)
    with torch.inference_mode():
        expected = model(tensor).numpy()
        if expected.shape != (1, 512) or not np.isfinite(expected).all():
            raise ValueError("OSNet did not produce a 512-dimensional feature vector")
        torch.onnx.export(
            model,
            tensor,
            str(exported),
            input_names=["images"],
            output_names=["embedding"],
            opset_version=17,
            dynamo=False,
        )
    session = ort.InferenceSession(str(exported), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"images": tensor.numpy()})[0]
    difference = float(np.max(np.abs(actual - expected)))
    cosine_similarity = float(
        np.dot(actual.flatten(), expected.flatten())
        / (np.linalg.norm(actual) * np.linalg.norm(expected))
    )
    if not np.allclose(actual, expected, rtol=1e-3, atol=1e-4) or cosine_similarity < 0.99999:
        raise ValueError(
            f"ONNX export disagreement: max absolute {difference}, cosine {cosine_similarity}"
        )
    manifest = {
        "schema_version": 1,
        "weights": exported.name,
        "weights_sha256": digest(exported),
        "architecture": "osnet_x0_25",
        "output_kind": "embedding",
        "feature_dimension": 512,
        "input_size": [256, 128],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "pretrained": {
            "source": MODEL_URL,
            "revision": MODEL_REVISION,
            "checkpoint_sha256": checkpoint_sha,
            "dataset": "MSMT17 combineall; official author checkpoint",
        },
        "export": {
            "code_source": CODE_URL,
            "code_revision": CODE_REVISION,
            "code_sha256": code_sha,
            "license": "MIT",
            "license_sha256": license_sha,
            "torch_version": torch.__version__,
            "onnxruntime_version": ort.__version__,
            "opset": 17,
            "eval_mode": True,
            "parameters_require_grad": False,
            "body_parameter_tensors_loaded": len(body),
            "training_updates": 0,
            "synthetic_max_absolute_feature_difference": difference,
            "synthetic_feature_cosine_similarity": cosine_similarity,
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "public_pretrained_export": True,
                "weights_sha256": manifest["weights_sha256"],
                "feature_dimension": 512,
                "synthetic_export_max_difference": difference,
            }
        )
    )


if __name__ == "__main__":
    main()
