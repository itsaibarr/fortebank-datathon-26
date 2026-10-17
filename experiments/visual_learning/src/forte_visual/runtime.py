"""Optional heavyweight runtime. Import only after data/resource gates pass.

Inference profile: existing digest-pinned vLLM image, one process/model at a time.
SFT profile: runtime/sft/uv.lock; no heavyweight dependencies in CPU environment.
"""

import base64
import gc
import hashlib
import io
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image

from forte_visual.benchmark import CANDIDATES, Result
from forte_visual.inputs import messages
from forte_visual.io import digest, local, read, write
from forte_visual.training import admit, loss_labels


class DeviceMemory:
    """Sample total device use, including vLLM child workers, not parent-only Torch."""

    def __init__(self):
        self.peak = 0
        self.samples = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while not self.stop.is_set():
            try:
                raw = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                )
                values = [int(v) * 1024**2 for v in raw.splitlines()]
                self.peak = max(self.peak, sum(values))
                self.samples += 1
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            self.stop.wait(0.2)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)


def offline():
    import os
    import socket

    if any(name != "lo" for _, name in socket.if_nameindex()):
        raise ValueError("Private model runtime requires a network-none namespace")

    for name, value in {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        "WANDB_DISABLED": "true",
        "TOKENIZERS_PARALLELISM": "false",
    }.items():
        os.environ[name] = value


def verify_model(path, key):
    receipt = read(path / "model-hashes.json")
    if (
        receipt["model"] != CANDIDATES[key]["model"]
        or receipt["revision"] != CANDIDATES[key]["revision"]
    ):
        raise ValueError("Unpinned base model")
    actual = {
        str(p.relative_to(path))
        for p in path.rglob("*")
        if p.is_file() and p.name != "model-hashes.json"
    }
    if actual != set(receipt["files"]):
        raise ValueError("Base file inventory mismatch")
    if any(digest(local(path, f)) != h for f, h in receipt["files"].items()):
        raise ValueError("Base content hash mismatch")
    if read(path / "config.json")["architectures"] != [CANDIDATES[key]["architecture"]]:
        raise ValueError("Unexpected multimodal model architecture")
    return digest(path / "model-hashes.json")


def hf_messages(case, root):
    content = []
    for item in messages(case, root)[0]["content"]:
        if item["type"] == "image_url":
            image = Image.open(
                io.BytesIO(base64.b64decode(item["image_url"]["url"].split(",", 1)[1]))
            )
            content.append({"type": "image", "image": image.convert("RGB")})
        else:
            content.append(item)
    return [{"role": "user", "content": content}]


def prepare(processor, case, root, answer=None):
    conversation = hf_messages(case, root)
    kwargs = dict(tokenize=True, return_dict=True, return_tensors="pt", enable_thinking=False)
    prefix = processor.apply_chat_template(conversation, add_generation_prompt=True, **kwargs)
    n = prefix["input_ids"].shape[-1]
    admit(n, 768, len(case.views))
    if answer is None:
        return prefix, n
    conversation.append({"role": "assistant", "content": json.dumps(answer, separators=(",", ":"))})
    full = processor.apply_chat_template(conversation, add_generation_prompt=False, **kwargs)
    if not full["input_ids"][0, :n].equal(prefix["input_ids"][0]):
        raise ValueError("Processor assistant prefix is not stable; refusing guessed loss mask")
    if full["input_ids"].shape[-1] > 8192:
        raise ValueError("Full answer over sequence bound")
    ids = full["input_ids"][0].numpy()
    special = [
        processor.tokenizer.convert_tokens_to_ids(x)
        for x in ["<|image_pad|>", "<|video_pad|>", "<|vision_start|>", "<|vision_end|>"]
    ]
    labels = loss_labels(ids, n, image_ids=special, attention=full["attention_mask"][0].numpy())
    import torch

    full["labels"] = torch.tensor(labels).unsqueeze(0)
    return full, n


class VLLMExecutor:
    def __init__(self, path: Path, key, adapter=None):
        offline()
        self.base_hash = verify_model(path, key)
        self.adapter = adapter
        self.adapter_hash = None
        if adapter is not None:
            training = read(adapter.parent / "training.json")
            if training["base_hash_manifest"] != self.base_hash:
                raise ValueError("Adapter belongs to another base snapshot")
            if any(
                digest(adapter / name) != sha for name, sha in training["adapter_files"].items()
            ):
                raise ValueError("Adapter content changed")
            self.adapter_hash = digest(adapter.parent / "training.json")
        self.memory = DeviceMemory()
        from transformers import AutoProcessor
        from vllm import LLM

        self.processor = AutoProcessor.from_pretrained(
            str(path), local_files_only=True, trust_remote_code=False, max_pixels=196608
        )
        began = time.monotonic()
        self.llm = LLM(
            model=str(path),
            dtype="bfloat16",
            max_model_len=8192,
            max_num_seqs=1,
            enforce_eager=True,
            trust_remote_code=False,
            gpu_memory_utilization=0.90,
            seed=0,
            limit_mm_per_prompt={"image": 16},
            mm_processor_kwargs={"max_pixels": 196608},
            enable_lora=adapter is not None,
            max_lora_rank=8,
        )
        self.cold_seconds = time.monotonic() - began

    def __call__(self, case, root):
        import torch
        from vllm import SamplingParams
        from vllm.sampling_params import StructuredOutputsParams

        from forte_visual.inputs import Answer

        tensors, measured = prepare(self.processor, case, root)
        grids = tensors.get("image_grid_thw")
        params = SamplingParams(
            temperature=0,
            seed=0,
            max_tokens=768,
            structured_outputs=StructuredOutputsParams(json=Answer.model_json_schema()),
        )
        torch.cuda.reset_peak_memory_stats()
        extra = {}
        if self.adapter is not None:
            from vllm.lora.request import LoRARequest

            extra["lora_request"] = LoRARequest("visual_adapter", 1, str(self.adapter))
        result = self.llm.chat(
            messages(case, root),
            sampling_params=params,
            use_tqdm=False,
            chat_template_kwargs={"enable_thinking": False},
            **extra,
        )[0]
        if result.outputs[0].finish_reason != "stop":
            raise ValueError("Incomplete model answer")
        return Result(
            json.loads(result.outputs[0].text),
            len(result.prompt_token_ids),
            len(result.outputs[0].token_ids),
            self.memory.peak or None,
            {
                "class": type(self.processor).__name__,
                "preflight_input_tokens": measured,
                "image_grid_thw": grids.tolist() if grids is not None else None,
                "max_pixels": 196608,
                "base_hash_manifest": self.base_hash,
                "adapter_receipt_sha256": self.adapter_hash,
                "cold_seconds": self.cold_seconds,
                "memory_samples": self.memory.samples,
                "memory_measurement": "total_device_sampled_200ms",
            },
        )


def tensor_hash(model, *, frozen_only=True):
    h = hashlib.sha256()
    for name, parameter in model.named_parameters():
        if frozen_only and parameter.requires_grad:
            continue
        h.update(name.encode())
        # Copy one tensor at a time; never another full model allocation.
        raw = parameter.detach().contiguous().cpu().view(__import__("torch").uint8).numpy()
        h.update(raw.tobytes())
    return h.hexdigest()


def train_offline(model_path, key, inputs, references, output, *, max_updates=1):
    """One pass, max 30 updates; 27B requires its own measured compatibility receipt."""
    if not 1 <= max_updates <= 30:
        raise ValueError("Initial run limited to one pass / 30 updates")
    offline()
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForImageTextToText, AutoProcessor

    from forte_visual.benchmark import load_cases

    base_hash = verify_model(model_path, key)
    torch.manual_seed(0)
    memory = DeviceMemory()
    processor = AutoProcessor.from_pretrained(
        str(model_path), local_files_only=True, trust_remote_code=False, max_pixels=196608
    )
    model = AutoModelForImageTextToText.from_pretrained(
        str(model_path),
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=torch.bfloat16,
        device_map={"": "cuda:0"},
    )
    if type(model).__name__ != CANDIDATES[key]["architecture"]:
        raise ValueError("SFT architecture mismatch")
    for p in model.parameters():
        p.requires_grad = False
    # Deliberately full language attention projections only. The hybrid 27B
    # linear-attention and vision projections stay frozen; no VL trainer reuse.
    pattern = r".*language_model\.layers\.\d+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)$"
    targets = [n for n, module in model.named_modules() if re.fullmatch(pattern, n)]
    if not targets:
        raise ValueError("No verified language-attention projections")
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=targets,
            task_type="CAUSAL_LM",
            bias="none",
        ),
    )
    names = [n for n, p in model.named_parameters() if p.requires_grad]
    if not names or any(
        "lora_" not in n or "language_model" not in n or ".self_attn." not in n for n in names
    ):
        raise ValueError("Unexpected trainable tensor boundary")
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model.config.use_cache = False
    model.save_pretrained(output / "checkpoint-0", safe_serialization=True)
    refs = read(references)
    if refs["inputs_sha256"] != digest(inputs):
        raise ValueError("SFT reference/input mismatch")
    cases = load_cases(inputs)
    train = [c for c in cases if refs["cases"][c.case_id]["split"] == "train"]
    validation = [c for c in cases if refs["cases"][c.case_id]["split"] == "validation"]
    if not train or not validation:
        raise ValueError("SFT requires eligible train and validation examples")
    write(output / "trainable.json", {"names": names, "targets": targets, "base_hash": base_hash})
    frozen = tensor_hash(model)
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=5e-5, weight_decay=0.01
    )
    optimizer.zero_grad()
    losses, updates, begun = [], 0, time.monotonic()
    last_batch = None
    for i, case in enumerate(train):
        batch, _ = prepare(processor, case, inputs.parent, refs["cases"][case.case_id]["answer"])
        last_batch = {k: v.to("cuda") for k, v in batch.items()}
        model.train()
        loss = model(**last_batch).loss
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite training loss")
        (loss / 8).backward()
        losses.append(float(loss.detach()))
        if (i + 1) % 8 == 0 or i + 1 == len(train):
            partial = (i % 8) + 1
            if partial < 8:
                for parameter in model.parameters():
                    if parameter.grad is not None:
                        parameter.grad.mul_(8 / partial)
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1, error_if_nonfinite=True
            )
            optimizer.step()
            optimizer.zero_grad()
            updates += 1
            if updates % 10 == 0:
                model.save_pretrained(output / f"checkpoint-{updates}", safe_serialization=True)
            if updates >= max_updates:
                break
    model.eval()
    with torch.no_grad():
        expected = model(**last_batch).logits[:, -1].float().cpu()
        val_case = validation[0]
        val_batch, _ = prepare(
            processor, val_case, inputs.parent, refs["cases"][val_case.case_id]["answer"]
        )
        val_loss = float(model(**{k: v.to("cuda") for k, v in val_batch.items()}).loss)
        if not torch.isfinite(torch.tensor(val_loss)) or not torch.isfinite(expected).all():
            raise ValueError("Nonfinite evaluation smoke")
    if tensor_hash(model) != frozen:
        raise ValueError("Frozen base tensor mutation")
    model.save_pretrained(output / "adapter", safe_serialization=True)
    # Reload in a genuinely fresh interpreter, using an inference-only prefix.
    # The child receives neither the reference pack nor supervised answers.
    probe, _ = prepare(processor, val_case, inputs.parent)
    with torch.no_grad():
        expected = model(**{k: v.to("cuda") for k, v in probe.items()}).logits[:, -1].float().cpu()
    import numpy as np

    np.save(output / "reload-expected.npy", expected.numpy())
    job = {
        "base": str(model_path),
        "candidate": key,
        "adapter": str(output / "adapter"),
        "case": val_case.model_dump(),
        "images": str(inputs.parent),
        "output": str(output),
        "base_manifest_sha256": base_hash,
        "adapter_files": {p.name: digest(p) for p in (output / "adapter").iterdir() if p.is_file()},
    }
    write(output / "reload-job.json", job)
    torch_peak = torch.cuda.max_memory_allocated()
    del model, optimizer, last_batch, val_batch, probe
    gc.collect()
    torch.cuda.empty_cache()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "forte_visual.runtime",
            "--reload-job",
            str(output / "reload-job.json"),
        ],
        check=True,
        timeout=600,
    )
    reloaded = read(output / "fresh-process-reload.json")
    error = reloaded["max_abs_error"]
    if memory.samples == 0:
        raise ValueError("Training memory measurement unavailable")
    report = {
        "candidate": CANDIDATES[key],
        "multimodal_step_passed": True,
        "freeze_boundary_verified": True,
        "base_hash_manifest": base_hash,
        "input_sha256": digest(inputs),
        "runtime_code_sha256": digest(Path(__file__)),
        "runtime_lock_sha256": digest(Path(__file__).resolve().parents[2] / "runtime/sft/uv.lock"),
        "frozen_tensor_sha256": frozen,
        "updates": updates,
        "passes": 1,
        "losses": losses,
        "validation_smoke_loss": val_loss,
        "reload_max_abs_error": error,
        "fresh_process_reload": reloaded,
        "seed": 0,
        "reference_sha256": digest(references),
        "trainable_tensor_names": names,
        "processor_class": type(processor).__name__,
        "recipe": {
            "precision": "bfloat16",
            "rank": 8,
            "alpha": 16,
            "dropout": 0.05,
            "learning_rate": 5e-5,
            "batch_size": 1,
            "gradient_accumulation": 8,
            "gradient_checkpointing": True,
            "loss": "assistant_only_ce",
        },
        "peak_memory_bytes": memory.peak or None,
        "torch_peak_allocated_bytes": torch_peak,
        "seconds": time.monotonic() - begun,
        "quality_evaluation": "pending identical-input base/adapter comparison",
        "adapter_files": {p.name: digest(p) for p in (output / "adapter").iterdir() if p.is_file()},
    }
    write(output / "training.json", report)
    memory.close()
    return report


def fresh_reload(job_path):
    """Private full-model reload probe, invoked only by gated supervised training."""
    offline()
    import os

    import numpy as np
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor

    from forte_visual.inputs import InputCase

    job = read(job_path)
    base, adapter = Path(job["base"]), Path(job["adapter"])
    if verify_model(base, job["candidate"]) != job["base_manifest_sha256"] or any(
        digest(adapter / name) != sha for name, sha in job["adapter_files"].items()
    ):
        raise ValueError("Fresh reload asset mismatch")
    model = AutoModelForImageTextToText.from_pretrained(
        str(base),
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=torch.bfloat16,
        device_map={"": "cuda:0"},
    )
    model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False)
    model.config.use_cache = False
    model.eval()
    processor = AutoProcessor.from_pretrained(
        str(base), local_files_only=True, trust_remote_code=False, max_pixels=196608
    )
    case = InputCase.model_validate(job["case"])
    prefix, _ = prepare(processor, case, Path(job["images"]))
    with torch.no_grad():
        actual = (
            model(**{k: v.to("cuda") for k, v in prefix.items()})
            .logits[:, -1]
            .float()
            .cpu()
            .numpy()
        )
    expected = np.load(Path(job["output"]) / "reload-expected.npy", allow_pickle=False)
    error = float(np.max(np.abs(actual - expected)))
    if not np.isfinite(actual).all() or error > 0.01:
        raise ValueError("Fresh-process adapter reload logits differ")
    write(
        Path(job["output"]) / "fresh-process-reload.json",
        {
            "pid": os.getpid(),
            "fresh_interpreter": True,
            "max_abs_error": error,
            "base_manifest_sha256": job["base_manifest_sha256"],
            "adapter_files": job["adapter_files"],
            "reference_pack_opened": False,
        },
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--reload-job", type=Path, required=True)
    fresh_reload(parser.parse_args().reload_job)
