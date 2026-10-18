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
PREFIX = "forte-admin-0.2.0"
PUBLIC_CONTRACTS = (
    "contracts/frozen-runtime-manifest-v1.json",
    "contracts/frozen-assets-v1.json",
    "contracts/frozen-effective-config-v1.json",
    "contracts/frozen-model-hashes-v1.json",
    "contracts/reasoning-api-contract.json",
    "contracts/browser-session-contract-v1.json",
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


def build(output, *, with_public_resources=False, public_artifacts_root=None, core_commit=None):
    selected = [ROOT / "tools/forte-admin/build.py"]
    selected.extend(sorted((ROOT / "tools/forte-admin/forte_admin").glob("*.py")))
    for name in (
        "__init__.py",
        "README.md",
        "runtime.py",
        "qualification.py",
        "host_daemon.py",
        "build_core.py",
        "bridge.py",
        "import_handoff.py",
        "core-current.candidate.json",
    ):
        path = ROOT / "deploy/portable" / name
        if path.is_file():
            selected.append(path)
    for name in ("session_gateway.py", "session_store.py"):
        path = ROOT / "tools/forte-session" / name
        if path.is_file():
            selected.append(path)
    for name in PUBLIC_CONTRACTS:
        path = ROOT / name
        if path.is_file():
            selected.append(path)
    for name in (
        "README.md",
        "administrator.md",
        "guided-install.md",
        "resource-preparation.md",
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
    if with_public_resources:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "forte_public_bundle", ROOT / "tools/forte-admin/forte_admin/public_bundle.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        entries.update(module.bundle_entries(ROOT, public_artifacts_root=public_artifacts_root))
    if core_commit:
        import sys

        sys.path.insert(0, str(ROOT / "tools/forte-admin"))
        from forte_admin.source_image import source_entries

        entries.update(source_entries(ROOT, core_commit))
    entries["RELEASE.json"] = (
        json.dumps(
            {
                "admin_version": "0.2.0",
                "source_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "core_included": False,
                "core_source_commit": core_commit,
                "core_source_included": bool(core_commit),
                "public_resources_included": with_public_resources,
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
                "core_source_commit": core_commit,
                "public_resources_included": with_public_resources,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--with-public-resources", action="store_true")
    parser.add_argument("--public-artifacts-root")
    parser.add_argument(
        "--core-commit", help="Include public build inputs from this full verified Git commit"
    )
    args = parser.parse_args()
    build(
        args.output,
        with_public_resources=args.with_public_resources,
        public_artifacts_root=args.public_artifacts_root,
        core_commit=args.core_commit,
    )
