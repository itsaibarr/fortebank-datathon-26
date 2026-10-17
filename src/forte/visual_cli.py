"""Scan an explicitly configured source through the same production pipeline."""

import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from forte_visual.io import private_dir

from forte.jobs import atomic_json, failure
from forte.visual_pipeline import analyze_visual
from forte.visual_runtime import ResidentScanner, VisualConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=270)
    args = parser.parse_args()
    if not 0 < args.seconds <= 270:
        parser.error("Use a bounded deadline of at most 270 seconds")
    os.umask(0o077)
    private_dir(args.private_output)
    stats, job_id = {}, uuid4()
    backend = None
    try:
        backend = ResidentScanner(VisualConfig.load(args.config))
        if not backend.warm():
            raise ValueError("model_not_ready")
        result = analyze_visual(
            args.source,
            args.private_output,
            job_id,
            backend,
            time.monotonic() + args.seconds,
            stats,
        )
    except Exception as exc:
        code = (
            str(exc)
            if str(exc) in {"processing_timeout", "insufficient_evidence"}
            else "analysis_failed"
        )
        result = failure(job_id, code)
        stats["failure_class"] = type(exc).__name__
    finally:
        if backend:
            backend.client.close()
    atomic_json(
        args.private_output / "result.json", result.model_dump(mode="json", exclude_none=True)
    )
    atomic_json(args.private_output / "metrics.json", stats)
    print(
        json.dumps(
            {
                "status": result.status,
                "calls": stats.get("calls", 0),
                "seconds": stats.get("total_seconds"),
                "model_route": stats.get("model_route"),
            }
        )
    )
    return 0 if result.status == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
