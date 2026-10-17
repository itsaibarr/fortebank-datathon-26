"""Offline compatibility check using generated shapes, never competition media.

Run inside the pinned vLLM container with --network none after downloading weights.
"""

import base64
import io
import json
import os
import time
from pathlib import Path

from PIL import Image, ImageDraw
from vllm import LLM, SamplingParams
from vllm.sampling_params import StructuredOutputsParams

MODEL = os.environ["FORTE_MODEL_PATH"]
OUTPUT = Path(os.environ.get("FORTE_SMOKE_OUTPUT", "/work/gpu-smoke-result.json"))
SCHEMA = {
    "type": "object",
    "properties": {
        "frame_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["frame_ids"],
    "additionalProperties": False,
}


def messages(width, height):
    content = [
        {
            "type": "text",
            "text": (
                "These are 16 ordered synthetic frames F00 through F15. "
                "Return the IDs of every frame containing a red rectangle. "
                "Ignore blue rectangles. Use only IDs supplied before each image."
            ),
        }
    ]
    for i in range(16):
        frame_id = f"F{i:02}"
        im = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(im)
        draw.rectangle(
            (width // 4, height // 4, width * 3 // 4, height * 3 // 4),
            fill="red" if i == 7 else "blue",
        )
        draw.text((20, 20), frame_id, fill="black")
        data = io.BytesIO()
        im.save(data, format="PNG")
        encoded = base64.b64encode(data.getvalue()).decode("ascii")
        content.extend(
            [
                {"type": "text", "text": f"Frame {frame_id}:"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ]
        )
    return [{"role": "user", "content": content}]


def main():
    started = time.perf_counter()
    llm = LLM(
        model=MODEL,
        dtype="bfloat16",
        max_model_len=8192,
        max_num_seqs=2,
        gpu_memory_utilization=0.85,
        enforce_eager=True,
        limit_mm_per_prompt={"image": 16},
        mm_processor_kwargs={"max_pixels": 393216},
        trust_remote_code=False,
    )
    report = {"model_load_seconds": time.perf_counter() - started, "runs": []}
    params = SamplingParams(
        temperature=0,
        max_tokens=64,
        structured_outputs=StructuredOutputsParams(json=SCHEMA),
    )
    for name, width, height in [("coarse", 512, 384), ("fine", 768, 512)]:
        t = time.perf_counter()
        result = llm.chat(messages(width, height), sampling_params=params, use_tqdm=False)[0]
        answer = json.loads(result.outputs[0].text)
        row = {
            "name": name,
            "frames": 16,
            "image_pixels": width * height,
            "seconds": time.perf_counter() - t,
            "prompt_tokens": len(result.prompt_token_ids),
            "output_tokens": len(result.outputs[0].token_ids),
            "answer": answer,
            "synthetic_grounding_pass": answer["frame_ids"] == ["F07"],
        }
        report["runs"].append(row)
        print(json.dumps(row), flush=True)
    import torch

    report["gpu"] = torch.cuda.get_device_name()
    report["torch"] = torch.__version__
    report["cuda_runtime"] = torch.version.cuda
    report["network"] = "Docker --network none; verify container inspection separately"
    report["total_seconds"] = time.perf_counter() - started
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    if not all(x["synthetic_grounding_pass"] for x in report["runs"]):
        raise SystemExit("Synthetic frame selection did not pass; inspect saved report")


if __name__ == "__main__":
    main()
