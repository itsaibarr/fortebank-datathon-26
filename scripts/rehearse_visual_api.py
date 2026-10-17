"""One private upload/poll/contract/source/model-identity rehearsal.

Run inside the offline container namespace. Prints only sanitized aggregates.
A failed result is retained as a failed result; never edit predictions to pass.
"""

import argparse
import base64
import json
import shutil
import time
from importlib.resources import files
from pathlib import Path
from uuid import UUID

import httpx
from forte_visual.io import private_dir, write
from jsonschema import Draft202012Validator

from forte.jobs import RESPONSE
from forte.person_proposals import sha256
from forte.video import decode_video
from forte.visual_runtime import VisualConfig, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("key-file", "file", "jobs-root", "config", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    private_dir(args.output)
    config = VisualConfig.load(args.config)
    expected = identity(config, full=False)
    headers = {"X-API-Key": args.key_file.read_text().strip()}
    receipts = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=35, trust_env=False) as client:
        assert client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000").status_code == 401
        ready = client.get("/health/ready")
        ready.raise_for_status()
        started = time.monotonic()
        with args.file.open("rb") as source:
            response = client.post(
                "/api/v1/analyze",
                headers=headers,
                files={"file": ("upload.mov", source, "video/quicktime")},
            )
        write(
            args.output / "upload-response.json",
            {"http_status": response.status_code, "body": response.json()},
        )
        if response.status_code != 202:
            print(json.dumps({"http_status": response.status_code, "status": "admission_failed"}))
            return 2
        job = UUID(response.json()["job_id"])
        while time.monotonic() - started < 300:
            poll = client.get(f"/api/v1/jobs/{job}", headers=headers)
            poll.raise_for_status()
            value = poll.json()
            receipts.append(
                {
                    "seconds": time.monotonic() - started,
                    "http_status": poll.status_code,
                    "status": value["status"],
                }
            )
            result = RESPONSE.validate_python(value)
            if result.status != "processing":
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("Client completion exceeded 300 seconds")
        elapsed = time.monotonic() - started
    contract = json.loads(files("forte").joinpath("data/api-contract.json").read_text())
    Draft202012Validator(
        {"$ref": "#/components/schemas/JobResponse", "components": contract["components"]}
    ).validate(value)
    write(args.output / "result.json", value)
    write(args.output / "poll-receipts.json", receipts)
    directory = args.jobs_root / str(job)
    copied = []
    for name in (
        "model-provenance.json",
        "metrics.json",
        "private-timeline.json",
        "temporal-checks.json",
        "automatic-tracks.json",
        "evidence-association.json",
    ):
        path = directory / name
        if path.exists():
            shutil.copyfile(path, args.output / name)
            (args.output / name).chmod(0o600)
            copied.append(name)
    provenance = json.loads((args.output / "model-provenance.json").read_bytes())
    loaded = provenance["loaded"]
    for field in (
        "mode",
        "route",
        "base_manifest_sha256",
        "base_files",
        "training_receipt_sha256",
        "adapter_files",
    ):
        if loaded[field] != expected[field]:
            raise ValueError("API job used a different model/adapter")
    if not provenance["warmup"]["multimodal_generation_completed"]:
        raise ValueError("No actual resident model warmup receipt")
    verified = 0
    if result.status == "done" and result.violations:
        registry = decode_video(args.file, args.output / "verification-frames")
        times = {f.timestamp_sec: f.frame_id for f in registry.frames}
        ids = list({times[e.timestamp_sec] for v in result.violations for e in v.evidence_frames})
        exact = {e.timestamp_sec: e.image_base64 for e in registry.evidence(ids)}
        for v in result.violations:
            for e in v.evidence_frames:
                if exact[e.timestamp_sec] != e.image_base64:
                    raise ValueError("API evidence differs from original source JPEG")
                target = args.output / f"evidence-{verified:03d}.jpg"
                target.write_bytes(base64.b64decode(e.image_base64))
                target.chmod(0o600)
                verified += 1
        shutil.rmtree(args.output / "verification-frames")
    summary = {
        "job_id": str(job),
        "status": result.status,
        "verdict": getattr(result, "verdict", None),
        "failure_code": result.error.code if result.status == "failed" else None,
        "seconds": elapsed,
        "client_under_300s": elapsed < 300,
        "events": len(getattr(result, "violations", [])),
        "verified_source_jpegs": verified,
        "model_route": loaded["route"],
        "mode": loaded["mode"],
        "base_manifest_sha256": loaded["base_manifest_sha256"],
        "training_receipt_sha256": loaded["training_receipt_sha256"],
        "source_sha256": sha256(args.file),
        "collected_job_artifacts": copied,
        "semantic_acceptance": "pending independent review",
    }
    write(args.output / "summary.json", summary)
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in {"source_sha256", "collected_job_artifacts"}
            }
        )
    )
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
