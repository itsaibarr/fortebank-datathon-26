"""Assistant-only CE admission and small CPU tensor verification."""

from pathlib import Path

import numpy as np

from forte_visual.io import canonical, private_dir, write


def admit(input_tokens, answer_tokens=768, images=16):
    if not 0 < images <= 16 or input_tokens <= 0 or answer_tokens <= 0:
        raise ValueError("Invalid measured token/image counts")
    if input_tokens + answer_tokens > 8192:
        raise ValueError("Example exceeds bounded sequence; resample or exclude, never truncate")


def loss_labels(ids, prefix_length, *, image_ids=(), attention=None):
    ids = np.asarray(ids, dtype=np.int64)
    if ids.ndim != 1 or not 0 < prefix_length < len(ids):
        raise ValueError("Assistant boundary must be measured inside a nonempty sequence")
    labels = ids.copy()
    labels[:prefix_length] = -100
    labels[np.isin(ids, image_ids)] = -100
    if attention is not None:
        mask = np.asarray(attention)
        if mask.shape != ids.shape:
            raise ValueError("Padding mask shape mismatch")
        labels[mask == 0] = -100
    if not np.any(labels != -100):
        raise ValueError("No supervised answer tokens")
    return labels


def tiny_check(output: Path):
    """Manual tiny language-attention LoRA step, no full-model fit/quality claim."""
    private_dir(output)
    rng = np.random.default_rng(0)
    x = rng.normal(size=(8, 6))
    base = rng.normal(size=(6, 12))
    a, b = rng.normal(scale=0.01, size=(6, 2)), np.zeros((2, 12))
    ids = np.array([1, 2, 11, 3, 4, 5, 6, 0])
    labels = loss_labels(ids, 4, image_ids=[11], attention=[1, 1, 1, 1, 1, 1, 1, 0])
    frozen = canonical(base.tolist())
    before = b.copy()
    logits = x @ (base + a @ b)
    # Causal shift: position t predicts answer token t+1.
    active = labels[1:] != -100
    z = logits[:-1][active]
    target = labels[1:][active]
    probs = np.exp(z - z.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    loss = float(-np.log(probs[np.arange(len(target)), target]).mean())
    grad = probs.copy()
    grad[np.arange(len(target)), target] -= 1
    grad /= len(target)
    grad_w = x[:-1][active].T @ grad
    b -= 5e-5 * a.T @ grad_w
    assert canonical(base.tolist()) == frozen and not np.array_equal(b, before)
    np.savez(output / "adapter.npz", a=a, b=b)
    reloaded = np.load(output / "adapter.npz")
    error = float(np.max(np.abs(x @ (base + a @ b) - x @ (base + reloaded["a"] @ reloaded["b"]))))
    report = {
        "mode": "tiny_cpu_synthetic",
        "loss": loss,
        "finite": bool(np.isfinite(loss)),
        "masked_tokens": int(np.sum(labels == -100)),
        "supervised_tokens": int(np.sum(labels != -100)),
        "frozen_base_hash": frozen,
        "reload_max_abs_error": error,
        "trainable_tensor_names": [
            "language_attention.q_proj.lora_A",
            "language_attention.q_proj.lora_B",
        ],
        "establishes_full_model_fit": False,
        "establishes_visual_learning_quality": False,
        "paid_spend_usd": 0,
    }
    write(output / "training-check.json", report)
    return report
