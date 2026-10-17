#!/usr/bin/env python3
"""Produce an offline-installable admin archive from explicitly allowed source paths."""

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "forte-admin-0.1.0"
PUBLIC_CONTRACTS = (
    "contracts/frozen-runtime-manifest-v1.json",
    "contracts/frozen-assets-v1.json",
    "contracts/frozen-effective-config-v1.json",
    "contracts/frozen-model-hashes-v1.json",
    "contracts/reasoning-api-contract.json",
)
CURRENT_CANDIDATE = "deploy/portable/core-current.candidate.json"
ACCEPTANCE_FLAGS = ("release", "model_workload", "offline_analysis", "browser_session", "ownership")


def validate_candidate(entries):
    if CURRENT_CANDIDATE not in entries:
        return
    canonical = entries.get("contracts/frozen-runtime-manifest-v1.json")
    if canonical is None:
        raise ValueError("Current candidate requires the canonical runtime manifest")
    candidate = json.loads(entries[CURRENT_CANDIDATE])
    provenance = candidate.get("provenance") if isinstance(candidate, dict) else None
    if (
        not isinstance(provenance, dict)
        or provenance.get("source_sha256") != hashlib.sha256(canonical).hexdigest()
    ):
        raise ValueError("Current candidate differs from the canonical runtime manifest")
    verification = candidate.get("verification", {})
    if not isinstance(verification, dict) or any(
        verification.get(key) is not False for key in ACCEPTANCE_FLAGS
    ):
        raise ValueError("Current installation candidate must remain unapproved")


def build(output):
    selected = [ROOT / "tools/forte-admin/build.py"]
    selected.extend(sorted((ROOT / "tools/forte-admin/forte_admin").glob("*.py")))
    for name in (
        "__init__.py",
        "README.md",
        "runtime.py",
        "build_core.py",
        "bridge.py",
        "import_handoff.py",
        "core-current.candidate.json",
    ):
        path = ROOT / "deploy/portable" / name
        if path.is_file():
            selected.append(path)
    for name in PUBLIC_CONTRACTS:
        path = ROOT / name
        if path.is_file():
            selected.append(path)
    for name in (
        "README.md",
        "administrator.md",
        "reviewer.md",
        "operations.md",
        "observed-contract.md",
        "api-client.md",
        "handoff.md",
        "verification.json",
        "integration-manifest.example.json",
    ):
        path = ROOT / "docs/deployment" / name
        if path.is_file():
            selected.append(path)
    launcher = ROOT / "tools/forte-admin/forte-admin"
    selected.append(launcher)
    if any(path.is_symlink() or path.resolve() != path for path in selected):
        raise ValueError("Archive inputs must be regular repository files without symlinks")
    entries = {str(path.relative_to(ROOT)): path.read_bytes() for path in selected}
    validate_candidate(entries)
    entries["RELEASE.json"] = (
        json.dumps(
            {
                "admin_version": "0.1.0",
                "source_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "core_included": False,
                "files": {
                    name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())
                },
            },
            indent=2,
        )
        + "\n"
    ).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(entries.items()):
            info = tarfile.TarInfo(PREFIX + "/" + name)
            info.size, info.mode, info.mtime = (
                len(data),
                0o755 if name.endswith("/forte-admin") else 0o644,
                0,
            )
            archive.addfile(info, io.BytesIO(data))
    output = Path(output)
    if output.is_symlink():
        raise ValueError("Archive destination must not be a symlink")
    output = output.parent.resolve() / output.name
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".forte-admin-", suffix=".tar.gz", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as zipped:
                zipped.write(buffer.getvalue())
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "archive": str(output),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "core_included": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    build(parser.parse_args().output)
