"""Run one pinned model offline on a fixed private diagnostic input pack."""

import argparse
import hashlib
import time
from pathlib import Path

from forte.role_benchmark import RoleAnswer, load_inputs, messages, save_report, validate_answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new private output path")
    cases = load_inputs(args.inputs)
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    started = time.perf_counter()
    report = {
        "model_snapshot": args.model.name,
        "input_manifest_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
        "settings": {
            "dtype": "bfloat16",
            "max_model_len": 8192,
            "max_num_seqs": 1,
            "temperature": 0,
            "seed": 0,
            "max_tokens": 768,
            "enable_thinking": False,
        },
        "cases": [],
    }
    save_report(args.output, report)
    llm = LLM(
        model=str(args.model),
        dtype="bfloat16",
        max_model_len=8192,
        max_num_seqs=1,
        gpu_memory_utilization=0.90,
        enforce_eager=True,
        trust_remote_code=False,
        limit_mm_per_prompt={"image": 12},
        mm_processor_kwargs={"max_pixels": 196608},
    )
    report["load_seconds"] = time.perf_counter() - started
    params = SamplingParams(
        temperature=0,
        seed=0,
        max_tokens=768,
        structured_outputs=StructuredOutputsParams(json=RoleAnswer.model_json_schema()),
    )
    for case in cases:
        row = {"case_id": case.case_id}
        start = time.perf_counter()
        try:
            result = llm.chat(
                messages(case, args.inputs.parent),
                sampling_params=params,
                chat_template_kwargs={"enable_thinking": False},
                use_tqdm=False,
            )[0]
            row.update(
                prompt_tokens=len(result.prompt_token_ids),
                output_tokens=len(result.outputs[0].token_ids),
                finish_reason=result.outputs[0].finish_reason,
            )
            if result.outputs[0].finish_reason != "stop":
                raise ValueError("Truncated diagnostic response")
            answer = RoleAnswer.model_validate_json(result.outputs[0].text)
            row["answer"] = answer.model_dump()
            validate_answer(case, answer)
            row["status"] = "valid"
        except Exception as exc:
            row.update(status="failed", error=type(exc).__name__)
        row["seconds"] = time.perf_counter() - start
        report["cases"].append(row)
        save_report(args.output, report)
        print(f"Diagnostic case completed: {row['status']}", flush=True)
    report["total_seconds"] = time.perf_counter() - started
    save_report(args.output, report)


if __name__ == "__main__":
    main()
