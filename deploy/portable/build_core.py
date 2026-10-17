#!/usr/bin/env python3
"""Prepare the existing core from an immutable Git snapshot, never a live checkout.

This public-resource preparation stage has no recording/data/credential mounts.
It does not start inference, deploy ingress, publish images or use a GPU.
"""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}")
INPUTS = (
    "Dockerfile",
    ".dockerignore",
    "requirements.runtime.txt",
    "pyproject.toml",
    "README.md",
    "contracts",
    "configs",
    "src",
    "legal",
    "scripts",
    "web",
)


def prepare(repository, commit, node_image, tag, output, *, preview=False):
    repository, output = Path(repository).resolve(), Path(output).resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not IMAGE.fullmatch(node_image):
        raise ValueError("Select a full core commit and an immutable Node build image digest.")
    if not re.fullmatch(r"forte26-[a-z0-9-]+:[a-z0-9._-]+", tag):
        raise ValueError("Use a dedicated forte26-<installation>:<version> image tag.")
    verified = subprocess.check_output(
        ["git", "rev-parse", "--verify", commit + "^{commit}"],
        cwd=repository,
        text=True,
    ).strip()
    if verified != commit:
        raise ValueError("Commit verification failed.")
    if output.exists():
        raise ValueError("Choose a new build receipt file; existing outputs were preserved.")
    if preview:
        return {
            "preview": True,
            "core_commit": commit,
            "node_image": node_image,
            "image_tag": tag,
            "private_inputs": False,
            "source": "git archive; tracked build inputs only",
        }
    with tempfile.TemporaryDirectory(prefix="forte26-public-build-") as temporary:
        snapshot = Path(temporary)
        archive = subprocess.check_output(["git", "archive", commit, *INPUTS], cwd=repository)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(snapshot, filter="data")
        # Public preparation only. Dependency installation follows the pinned UI lockfile.
        command = [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--volume",
            f"{snapshot}:/snapshot",
            "--workdir",
            "/snapshot/web",
            "--entrypoint",
            "sh",
            node_image,
            "-c",
            "npm ci && npm run build",
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(
            ["docker", "build", "--pull=false", "--tag", tag, str(snapshot)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        identity = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", tag], text=True
        ).strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
            raise ValueError("Built image identity could not be verified.")
        result = {
            "core_commit": commit,
            "local_image_id": identity,
            "node_image": node_image,
            "dockerfile_sha256": hashlib.sha256((snapshot / "Dockerfile").read_bytes()).hexdigest(),
            "source_archive_sha256": hashlib.sha256(archive).hexdigest(),
            "private_inputs": False,
            "gpu_used": False,
            "runtime_verified": False,
            "dependency_limit": (
                "Core lockfiles/base are pinned; apt packages are not a hermetic OS "
                "snapshot. Deploy by the resulting immutable image ID."
            ),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as receipt:
        json.dump(result, receipt, indent=2)
        receipt.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".")
    parser.add_argument("--core-commit", required=True)
    parser.add_argument("--node-image", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        result = prepare(
            args.repository,
            args.core_commit,
            args.node_image,
            args.tag,
            args.output,
            preview=args.preview,
        )
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError, tarfile.TarError):
        print(
            json.dumps(
                {
                    "error": (
                        "Public core preparation incomplete. No inference, ingress or GPU "
                        "service was started; inspect prerequisites locally."
                    )
                }
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
