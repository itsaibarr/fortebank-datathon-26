#!/usr/bin/env python3
"""Produce an offline-installable admin archive from explicitly allowed source paths."""

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "forte-admin-0.1.0"


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
        "core-111234c.candidate.json",
    ):
        path = ROOT / "deploy/portable" / name
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
    entries = {str(path.relative_to(ROOT)): path.read_bytes() for path in selected}
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
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(buffer.getvalue())
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
