"""Private local API rehearsal. Print aggregates only; save sensitive results privately."""

import argparse
import base64
import hashlib
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from forte.jobs import RESPONSE
from forte.video import decode_video


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if urlsplit(args.url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Rehearse through loopback or a controlled SSH tunnel")
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.chmod(0o700)
    key = args.key_file.read_text().strip()
    started = time.monotonic()
    with httpx.Client(
        base_url=args.url, timeout=35, trust_env=False, follow_redirects=False
    ) as client:
        assert client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000").status_code == 401
        with args.file.open("rb") as source:
            post = client.post(
                "/api/v1/analyze",
                files={"file": ("upload.mov", source, "video/quicktime")},
                headers={"X-API-Key": key},
            )
        if post.status_code != 202:
            print(
                json.dumps(
                    {
                        "http_status": post.status_code,
                        "error": post.json().get("error", {}).get("code"),
                    }
                )
            )
            return 1
        id = post.json()["job_id"]
        UUID(id)
        result = None
        while time.monotonic() - started < 300:
            response = client.get("/api/v1/jobs/" + id, headers={"X-API-Key": key})
            response.raise_for_status()
            result = RESPONSE.validate_python(response.json())
            if result.status != "processing":
                break
            time.sleep(0.5)
        elapsed = time.monotonic() - started
    if result is None or result.status == "processing":
        raise TimeoutError("Job did not reach a terminal state")
    path = args.output / "result.json"
    path.write_text(result.model_dump_json(exclude_none=True))
    path.chmod(0o600)
    metrics = {
        "source_sha256": hashlib.sha256(args.file.read_bytes()).hexdigest(),
        "job_id": id,
        "status": result.status,
        "seconds": elapsed,
        "verdict": getattr(result, "verdict", None),
        "events": len(getattr(result, "violations", [])),
    }
    if result.status == "failed":
        metrics["error"] = result.error.code
    else:
        registry = decode_video(args.file, args.output / "verification-frames")
        by_time = {f.timestamp_sec: f.frame_id for f in registry.frames}
        ids = []
        for event in result.violations:
            assert 0 <= event.timecode_sec <= registry.duration
            for evidence in event.evidence_frames:
                assert evidence.timestamp_sec in by_time
                ids.append(by_time[evidence.timestamp_sec])
        expected = {e.timestamp_sec: e.image_base64 for e in registry.evidence(ids)} if ids else {}
        for i, event in enumerate(result.violations):
            for j, evidence in enumerate(event.evidence_frames):
                assert evidence.image_base64 == expected[evidence.timestamp_sec]
                (args.output / f"evidence-{i}-{j}.jpg").write_bytes(
                    base64.b64decode(evidence.image_base64)
                )
        metrics["evidence_frames_checked"] = len(ids)
        metrics["source_evidence_verified"] = True if ids else None
        assert elapsed < 300
        shutil.rmtree(args.output / "verification-frames")
    (args.output / "summary.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({key: value for key, value in metrics.items() if key != "source_sha256"}))
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
