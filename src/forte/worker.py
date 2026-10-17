"""Isolated decoder/pipeline process. Private outputs never go to stdout or logs."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from uuid import UUID

from forte.inference import LocalVLM
from forte.jobs import atomic_json, failure
from forte.pipeline import analyze_video
from forte.video import probe_video


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--job-id", type=UUID)
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--model-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model", default="forte-vlm")
    args = parser.parse_args()
    os.umask(0o077)
    if sys.platform == "linux":
        import ctypes
        import resource
        import signal

        ctypes.CDLL(None).prctl(1, signal.SIGKILL)
        resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
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
        backend = LocalVLM(args.model_url, args.model)
        result = analyze_video(
            args.job / "input.mov", args.job, args.job_id, backend, args.deadline, stats
        )
    except Exception as exc:
        stats["error_type"] = type(exc).__name__
        code = (
            str(exc)
            if str(exc) in {"processing_timeout", "insufficient_evidence"}
            else "analysis_failed"
        )
        result = failure(args.job_id, code)
    finally:
        shutil.rmtree(args.job / "frames", ignore_errors=True)
    atomic_json(args.job / "metrics.json", stats)
    atomic_json(args.job / "worker-result.json", result.model_dump(mode="json", exclude_none=True))


if __name__ == "__main__":
    main()
