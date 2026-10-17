"""Public synthetic scene-plus-crop check of the actual local visual processor."""

import argparse
import io
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from forte.inference import LocalVLM
from forte.jobs import atomic_json


@dataclass
class Frame:
    frame_id: str
    timestamp_sec: float


class Shapes:
    def __init__(self, red_index):
        self.red_index = red_index

    def image_bytes(self, frame, pixels):
        index = int(frame.frame_id[1:])
        size = (512, 384) if index < 12 else (128, 256)
        image = Image.new("RGB", size, "red" if index == self.red_index else "blue")
        output = io.BytesIO()
        image.save(output, "JPEG")
        return output.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--model-name", default=os.environ.get("FORTE_MODEL_NAME", "forte-vlm"))
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        default=int(os.environ.get("FORTE_MAX_CONTEXT_TOKENS", "8192")),
    )
    parser.add_argument("--wait-seconds", type=float, default=0)
    args = parser.parse_args()
    backend = LocalVLM(
        "http://127.0.0.1:8001",
        model=args.model_name,
        expected_revision=args.revision,
        max_context_tokens=args.max_context_tokens,
        enable_thinking=False,
    )
    deadline = time.monotonic() + args.wait_seconds
    while not backend.ready() and time.monotonic() < deadline:
        time.sleep(2)
    if not backend.ready():
        raise SystemExit("Pinned local visual model is not ready")
    frames = [Frame(f"F{i:02}", float(i)) for i in range(16)]
    schema = {
        "type": "object",
        "properties": {"frame_id": {"type": "string", "enum": [f.frame_id for f in frames]}},
        "required": ["frame_id"],
        "additionalProperties": False,
    }
    rows = []
    for red_index in (5, 14):
        started = time.monotonic()
        value = backend.request(
            Shapes(red_index),
            frames,
            "Select the supplied frame whose whole image is red. Return its exact frame_id.",
            schema,
            196608,
            64,
        )
        rows.append(
            {
                "correct": value == {"frame_id": f"F{red_index:02}"},
                "seconds": time.monotonic() - started,
                "usage": backend.last_usage,
            }
        )
    report = {
        "input": "public synthetic solid colors; 12 scenes plus 4 participant-size crops",
        "model": backend.loaded,
        "calls": rows,
        "images_per_call": 16,
        "max_pixels": 196608,
        "max_context_tokens": backend.max_context_tokens,
        "training_performed": False,
    }
    atomic_json(args.output, report)
    print(json.dumps(report, allow_nan=False))
    if not all(row["correct"] for row in rows):
        raise SystemExit("Visual processor selection check failed")


if __name__ == "__main__":
    main()
