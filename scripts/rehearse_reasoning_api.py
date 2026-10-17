"""Local-only v2 upload/poll/source/JPEG provenance rehearsal.

Full results and media stay in a new private output directory. Stdout contains
only aggregate execution/provenance checks, never scene or role descriptions.
This client creates no human correction or semantic approval.
"""

import argparse
import hashlib
import json
import math
import os
import re
import time
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from forte.contracts_v2 import ReasoningDoneJob
from forte.frozen_tracking import private_directory, require_outbound_blocked
from forte.person_proposals import sha256
from forte.video import jpeg_bytes, open_video, oriented, probe_video


def save(path, value):
    with path.open("x") as output:
        output.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    path.chmod(0o600)


def eligible_source(path, digest):
    data = json.loads(path.read_bytes())
    records = data.get("records", data.get("groups", []))
    matches = [
        record
        for record in records
        if record.get("recording_id", record.get("source_sha256")) == digest
    ]
    if len(matches) != 1 or matches[0].get("split") != "development":
        raise ValueError("Source is not in the neutral/hash development allowlist")


def verify_evidence(source, result, fetched, output, deadline):
    """Independently re-decode source PTS and exact full-size quality-90 JPEGs."""
    events = result["events"]
    expected, links = {}, []
    duration = result["source"]["duration_sec"]
    for event in events:
        start, end = event["start_sec"], event["end_sec"]
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= duration):
            raise ValueError("Invalid event source interval")
        event_ids = set(event["evidence_frame_ids"])
        decisive = event["decisive_frame_id"]
        if decisive not in event_ids:
            raise ValueError("Event marker lacks source-frame evidence membership")
        for item in event["evidence"]:
            frame_id = item["frame_id"]
            if frame_id not in event_ids or not start <= item["timestamp_sec"] <= end:
                raise ValueError("Evidence/marker source interval linkage failed")
            if not re.fullmatch(r"f\d{6}", frame_id):
                raise ValueError("Unexpected source frame ID")
            expected_hash = item.get("image_sha256", item.get("jpeg_sha256"))
            if not expected_hash or hashlib.sha256(fetched[frame_id]).hexdigest() != expected_hash:
                raise ValueError("API evidence bytes differ from declared source image hash")
            if frame_id in expected and expected[frame_id] != item:
                raise ValueError("Conflicting evidence metadata for the same source frame")
            expected[frame_id] = item
            links.append(
                {
                    "event_id": event["event_id"],
                    "frame_id": frame_id,
                    "timestamp_sec": item["timestamp_sec"],
                    "source_pts": item["source_pts"],
                    "within_source_interval": True,
                    "decisive": frame_id == decisive,
                }
            )
        if event.get("evidence_export_complete") and decisive not in {
            item["frame_id"] for item in event["evidence"]
        }:
            raise ValueError("Complete evidence export omits the decisive marker")
    metadata = probe_video(source)
    rows, checked, origin = [], set(), None
    with open_video(source) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        for ordinal, frame in enumerate(container.decode(stream)):
            if time.monotonic() >= deadline:
                raise TimeoutError("Source verification deadline exhausted")
            if frame.pts is None or frame.is_corrupt:
                raise ValueError("Untrustworthy original source frame")
            absolute = frame.pts * frame.time_base
            origin = absolute if origin is None else origin
            stamp = float(absolute - origin)
            fid = f"f{ordinal:06d}"
            rows.append(
                {
                    "frame_id": fid,
                    "source_pts": frame.pts,
                    "time_base": str(frame.time_base),
                    "timestamp_sec": stamp,
                }
            )
            if fid not in expected:
                continue
            item = expected[fid]
            image = oriented(frame, stream, metadata["rotation"])
            raw = jpeg_bytes(image, image.width * image.height)
            if (
                frame.pts != item["source_pts"]
                or Fraction(item["time_base"]) != frame.time_base
                or not math.isclose(stamp, item["timestamp_sec"], abs_tol=1e-8)
                or list(image.size) != item["oriented_size"]
                or raw != fetched[fid]
            ):
                raise ValueError(
                    "API evidence differs from independently re-extracted original source"
                )
            checked.add(fid)
    if len(rows) != result["source"]["frame_count"] or checked != expected.keys():
        raise ValueError("Incomplete original source/evidence verification")
    # Validate every event marker, even when an explicit export budget omitted its JPEG.
    by_id = {row["frame_id"]: row for row in rows}
    for event in events:
        row = by_id[event["decisive_frame_id"]]
        if not event["start_sec"] <= row["timestamp_sec"] <= event["end_sec"]:
            raise ValueError("Seek marker does not lie within its source interval")
    save(output / "verified-source-frame-table.json", rows)
    save(output / "marker-evidence-links.json", links)
    return {
        "decoded_source_frames": len(rows),
        "evidence_jpegs_verified": len(checked),
        "event_markers_verified": len(events),
    }


def rehearse(args):
    isolation = require_outbound_blocked()
    parsed = urlsplit(args.url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use a plain local loopback API origin")
    if not 1 <= args.timeout <= 300:
        raise ValueError("Rehearsal deadline must be within 300 seconds")
    source = args.file.resolve(strict=True)
    digest = sha256(source)
    if args.expected_sha256 and digest != args.expected_sha256:
        raise ValueError("Source SHA256 differs from the explicit expected fingerprint")
    if args.allowlist:
        eligible_source(args.allowlist, digest)
    output = private_directory(args.output)
    if any(output.iterdir()):
        raise FileExistsError("Choose a fresh empty private rehearsal directory")
    key = args.key_file.read_text().strip()
    started = time.monotonic()
    deadline = started + args.timeout
    origin = args.url.rstrip("/")
    headers = {"X-API-Key": key}

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("API rehearsal exceeded its end-to-end deadline")
        return value

    with httpx.Client(base_url=origin, trust_env=False, follow_redirects=False) as client:
        unauthenticated = client.post(
            "/api/v2/analyze", content=b"unauthenticated", timeout=min(10, remaining())
        )
        if unauthenticated.status_code != 401:
            raise ValueError("Unauthenticated v2 analyze did not reject access")
        with source.open("rb") as upload:
            response = client.post(
                "/api/v2/analyze",
                headers=headers,
                files={"file": ("upload.mov", upload, "video/quicktime")},
                timeout=min(35, remaining()),
            )
        response.raise_for_status()
        if response.status_code != 202:
            raise ValueError("V2 analyze did not accept an asynchronous job")
        admitted = response.json()
        save(output / "admission.json", admitted)
        job_id = str(__import__("uuid").UUID(admitted["job_id"]))
        path = "/api/v2/jobs/" + job_id
        while True:
            response = client.get(path, headers=headers, timeout=min(10, remaining()))
            response.raise_for_status()
            job = response.json()
            if job["status"] != "processing":
                break
            time.sleep(min(0.5, remaining()))
        save(output / "job-response.json", job)
        if job["status"] != "done":
            summary = {
                "status": job["status"],
                "job_id": job_id,
                "elapsed_sec": time.monotonic() - started,
                "authentication_401": True,
                "source_sha256": digest,
            }
            save(output / "verification.json", summary)
            return summary
        validated = ReasoningDoneJob.model_validate(job)
        result = validated.result
        if result["source_sha256"] != digest:
            raise ValueError("Completed API result belongs to a different source")
        if sha256(source) != digest:
            raise ValueError("Original source changed during the rehearsal")
        response = client.get(path + "/source", headers=headers, timeout=min(30, remaining()))
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != digest:
            raise ValueError("Source endpoint differs from original uploaded MOV")
        fetched = {}
        evidence_dir = output / "evidence"
        evidence_dir.mkdir(mode=0o700)
        for event in result["events"]:
            for item in event["evidence"]:
                fid = item["frame_id"]
                if fid in fetched:
                    continue
                response = client.get(
                    path + "/evidence/" + fid, headers=headers, timeout=min(10, remaining())
                )
                response.raise_for_status()
                fetched[fid] = response.content
                target = evidence_dir / (fid + ".jpg")
                with target.open("xb") as stream:
                    stream.write(response.content)
                target.chmod(0o600)
        # Read-only correction access is verified. No invented semantic review is submitted.
        response = client.get(path + "/corrections", headers=headers, timeout=min(10, remaining()))
        response.raise_for_status()
        save(output / "existing-corrections.json", response.json())
    checks = verify_evidence(source, result, fetched, output, deadline)
    summary = {
        "status": "done",
        "job_id": job_id,
        "assessment": result["assessment"],
        "execution_status": result["execution"]["status"],
        "events": len(result["events"]),
        "elapsed_sec": time.monotonic() - started,
        "source_sha256": digest,
        "authentication_401": True,
        "source_endpoint_hash_verified": True,
        "network_isolation": isolation,
        "corrections_read_only": True,
        "model_revision": result.get("provenance", {}).get("model", {}).get("revision"),
        **checks,
    }
    save(output / "verification.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path)
    parser.add_argument("--expected-sha256", "--source-sha256")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        summary = rehearse(args)
    except Exception as exc:
        # Exceptions may carry response/body/source facts; expose only the class.
        print(json.dumps({"status": "verification_failed", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(summary, allow_nan=False))
    if summary["status"] != "done":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
