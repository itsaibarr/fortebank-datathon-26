"""Isolated decoder/pipeline process. Private outputs never go to stdout or logs."""

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

import httpx
from pydantic import ValidationError

from forte.inference import LocalVLM
from forte.jobs import atomic_json, failure
from forte.pipeline import analyze_video
from forte.video import probe_video


def failure_diagnostics(exc):
    details = {"error_type": type(exc).__name__}
    reasons = {
        "Model answer was incomplete": "model_output_truncated",
        "Visual input exceeds context budget": "visual_context_exceeded",
        "invalid_event_order": "invalid_event_order",
        "Unsupported legal, accounting or intent claim": "unsupported_description",
    }
    if str(exc) in reasons:
        details["reason"] = reasons[str(exc)]
    if isinstance(exc, httpx.HTTPStatusError):
        details["http_status"] = exc.response.status_code
    if isinstance(exc, ValidationError):
        details["validation_types"] = dict(
            Counter(e["type"] for e in exc.errors(include_input=False, include_context=False))
        )
    return details


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--job-id", type=UUID)
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--model-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model", default="forte-vlm")
    parser.add_argument("--visual-config", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if sys.platform == "linux":
        import ctypes
        import resource
        import signal

        ctypes.CDLL(None).prctl(1, signal.SIGKILL)
        limit = 12 * 1024**3 if args.visual_config and not args.probe else 3 * 1024**3
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    if args.probe:
        try:
            print(json.dumps(probe_video(args.probe)))
        except ValueError as exc:
            status = 422 if any(x in str(exc) for x in ["duration", "dimensions"]) else 415
            print(json.dumps({"error": {"status": status}}))
        return
    if not args.job or not args.job_id or args.deadline is None:
        parser.error("A job, ID and deadline are required")
    stats = {}
    try:
        if args.visual_config:
            from forte.visual_pipeline import analyze_visual
            from forte.visual_runtime import ResidentScanner, VisualConfig

            backend = ResidentScanner(VisualConfig.load(args.visual_config), full=False)
            if not backend.warm():
                raise ValueError("model_identity_unavailable")
            analyze = analyze_visual
        else:
            backend = LocalVLM(args.model_url, args.model)
            analyze = analyze_video
        result = analyze(
            args.job / "input.mov", args.job, args.job_id, backend, args.deadline, stats
        )
    except Exception as exc:
        stats.update(failure_diagnostics(exc))
        code = (
            str(exc)
            if str(exc) in {"processing_timeout", "insufficient_evidence"}
            else "analysis_failed"
        )
        result = failure(args.job_id, code)
    finally:
        if "backend" in locals():
            backend.client.close()
        shutil.rmtree(args.job / "frames", ignore_errors=True)
    atomic_json(args.job / "metrics.json", stats)
    atomic_json(args.job / "worker-result.json", result.model_dump(mode="json", exclude_none=True))


if __name__ == "__main__":
    main()
