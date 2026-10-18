"""Export a pinned public source snapshot and build it without a live checkout.

A publisher's verified Git export and release archive attest to source identity.
An extracted customer bundle does not need Git. Builds acquire public software
only when explicitly online; they never mount recordings, load a GPU, deploy an
application or promote runtime/security/quality acceptance.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from forte_admin.config import ConfigError, private_write
from forte_admin.config import installation_root as checked_installation_root

COMMIT = re.compile(r"[0-9a-f]{40}")
SHA = re.compile(r"[0-9a-f]{64}")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
PUBLIC_INPUTS = {
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
}
SKIPPED_LINKS = {"web/CLAUDE.md", "web/AGENTS.md"}
PRIVATE_SUFFIXES = {
    ".mov",
    ".mp4",
    ".avi",
    ".mkv",
    ".zip",
    ".xlsx",
    ".key",
    ".pem",
    ".safetensors",
    ".onnx",
    ".pt",
    ".pth",
    ".bin",
    ".sqlite",
    ".db",
}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".next",
    "out",
    "private",
    "runs",
    "adapters",
    "weights",
    "models",
    ".cache",
    ".npmrc",
    ".netrc",
    ".pypirc",
    ".ssh",
    ".aws",
}
REQUIRED = {
    "Dockerfile",
    ".dockerignore",
    "requirements.runtime.txt",
    "pyproject.toml",
    "README.md",
    "web/package.json",
    "web/package-lock.json",
    "scripts/container-entrypoint.sh",
    "scripts/check_frozen_visual.py",
}


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or "\n" in value or "\0" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and str(path) == value and not ({".", ".."} & set(path.parts))


def _public(value):
    path = PurePosixPath(value)
    return (
        _relative(value)
        and path.parts[0] in PUBLIC_INPUTS
        and not (set(path.parts) & EXCLUDED_PARTS)
        and not any(part.startswith(".env") for part in path.parts)
        and path.suffix.lower() not in PRIVATE_SUFFIXES
    )


def _inputs(repository):
    """Read the actual public publisher build allowlist without executing it."""
    path = repository / "deploy/portable/build_core.py"
    if path.is_symlink():
        raise ConfigError("Publisher build-input inventory must be a regular repository file.")
    try:
        tree = ast.parse(path.read_text())
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "INPUTS" for target in node.targets
            )
        )
        values = ast.literal_eval(assignment.value)
    except (OSError, SyntaxError, ValueError, StopIteration) as exc:
        raise ConfigError("Publisher build-input inventory is unavailable or invalid.") from exc
    if (
        not isinstance(values, (tuple, list))
        or not values
        or any(not isinstance(value, str) or value not in PUBLIC_INPUTS for value in values)
        or len(set(values)) != len(values)
    ):
        raise ConfigError("Publisher build-input inventory contains an unsupported path.")
    return tuple(values)


def source_entries(repository_root, core_commit):
    """Return archive entries exported from a full verified commit, never worktree bytes."""
    repository = Path(repository_root).expanduser().resolve()
    if not isinstance(core_commit, str) or not COMMIT.fullmatch(core_commit):
        raise ConfigError("Source export requires the full pinned core commit.")
    inputs = _inputs(repository)
    try:
        verified = subprocess.check_output(
            ["git", "rev-parse", "--verify", core_commit + "^{commit}"],
            cwd=repository,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        ).strip()
        if verified != core_commit:
            raise ConfigError("Source export commit verification failed.")
        archive = subprocess.check_output(
            ["git", "archive", core_commit, *inputs],
            cwd=repository,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigError(
            "Pinned core source is not available in the publisher repository."
        ) from exc
    entries, metadata, skipped = {}, {}, []
    try:
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source:
                if member.isdir():
                    continue
                if member.issym() and member.name in SKIPPED_LINKS:
                    skipped.append(member.name)
                    continue
                if not member.isfile() or not _relative(member.name):
                    raise ConfigError(
                        "Public source export rejected a link or unsafe archive entry."
                    )
                if not _public(member.name):
                    raise ConfigError("Public source export contains an excluded artifact.")
                if member.name in metadata:
                    raise ConfigError("Public source export contains a duplicate entry.")
                stream = source.extractfile(member)
                if stream is None:
                    raise ConfigError("Public source export contains an unreadable entry.")
                data = stream.read()
                entries["core-source/" + member.name] = data
                metadata[member.name] = {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                    "mode": 0o755 if member.mode & 0o111 else 0o644,
                }
    except tarfile.TarError as exc:
        raise ConfigError("Pinned public source archive could not be read.") from exc
    if not REQUIRED <= metadata.keys() or not any(
        name.startswith("src/forte/") for name in metadata
    ):
        raise ConfigError("Pinned source is missing required application or build inputs.")
    entries["core-source/SOURCE.json"] = (
        json.dumps(
            {
                "schema_version": 1,
                "kind": "git-archive-public-build-inputs",
                "core_commit": core_commit,
                "inputs": list(inputs),
                "skipped_nonbuild_links": sorted(skipped),
                "files": metadata,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    return entries


def _open_source(root, name):
    """Open regular source without following final or intermediate symlinks."""
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = PurePosixPath(name).parts
        for part in parts[:-1]:
            following = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = following
        final = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
        if not stat.S_ISREG(os.fstat(final).st_mode):
            os.close(final)
            raise ConfigError("Public source must contain regular files only.")
        return os.fdopen(final, "rb")
    finally:
        os.close(descriptor)


def _verified_bundle(bundle_root, core_commit):
    if not isinstance(core_commit, str) or not COMMIT.fullmatch(core_commit):
        raise ConfigError("Source build requires the publisher's full pinned core commit.")
    bundle = Path(bundle_root).expanduser()
    if bundle.is_symlink():
        raise ConfigError("Source bundle must not be a symlink.")
    bundle = bundle.resolve()
    source = bundle if bundle.name == "core-source" else bundle / "core-source"
    if source.is_symlink() or not source.is_dir():
        raise ConfigError("The released public core-source bundle is unavailable.")
    manifest_path = source / "SOURCE.json"
    if manifest_path.is_symlink():
        raise ConfigError("Source manifest must not be a symlink.")
    try:
        with _open_source(source, "SOURCE.json") as stream:
            raw = stream.read()
        manifest = json.loads(raw)
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("kind") != "git-archive-public-build-inputs"
            or manifest.get("core_commit") != core_commit
            or not isinstance(manifest.get("files"), dict)
        ):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise ConfigError(
            "Public source manifest is unavailable or does not match the pinned core commit."
        ) from exc
    files = manifest["files"]
    if not REQUIRED <= files.keys() or not any(name.startswith("src/forte/") for name in files):
        raise ConfigError("Public source manifest is missing required application/build inputs.")
    for name, info in files.items():
        if (
            not _public(name)
            or not isinstance(info, dict)
            or not SHA.fullmatch(str(info.get("sha256", "")))
            or type(info.get("size_bytes")) is not int
            or info["size_bytes"] < 0
            or type(info.get("mode")) is not int
            or info["mode"] not in {0o644, 0o755}
        ):
            raise ConfigError("Public source manifest contains an invalid or excluded file entry.")
    observed = set()
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ConfigError("Public source bundle rejected a symlink.")
        if path.is_dir():
            continue
        name = path.relative_to(source).as_posix()
        if not path.is_file() or name not in {*files, "SOURCE.json"}:
            raise ConfigError("Public source bundle contains an extra or nonregular file.")
        if name == "SOURCE.json":
            continue
        observed.add(name)
        info = files[name]
        with _open_source(source, name) as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != info["size_bytes"] or digest != info["sha256"]:
            raise ConfigError("Public source file failed its pinned size/hash verification.")
    if observed != set(files):
        raise ConfigError("A pinned public source file is missing.")
    dockerfile = (source / "Dockerfile").read_text()
    bases = []
    for line in dockerfile.splitlines():
        match = re.match(r"\s*FROM\s+(\S+)(?:\s+AS\s+[A-Za-z0-9_-]+)?\s*$", line, re.I)
        if match:
            if not IMAGE.fullmatch(match[1]):
                raise ConfigError(
                    "Every Dockerfile base image must use an immutable repository digest."
                )
            bases.append(match[1])
        elif re.match(r"\s*FROM\b", line, re.I):
            raise ConfigError("Unsupported Dockerfile base-image syntax was rejected.")
    if not bases:
        raise ConfigError("Pinned Dockerfile has no verified immutable base image.")
    return source, manifest, hashlib.sha256(raw).hexdigest(), list(dict.fromkeys(bases))


def _run(command, *, timeout):
    inspect = command[1:3] == ["image", "inspect"]
    return subprocess.run(
        command,
        stdout=subprocess.PIPE if inspect else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
        timeout=timeout,
    )


def _ensure_image(image, online, runner):
    found = runner(["docker", "image", "inspect", "--format", "{{.Id}}", image], timeout=30)
    if found.returncode == 0:
        return
    if not online:
        raise ConfigError(
            "A pinned public build image is missing; import it or select explicit "
            "online build preparation."
        )
    pulled = runner(["docker", "pull", image], timeout=1800)
    if pulled.returncode:
        raise ConfigError("Pinned public build image acquisition failed; retry the same digest.")


def _owned_build_root(root):
    marker = root / "source-build-owner.json"
    identity = hashlib.sha256(str(root).encode()).hexdigest()
    if root.exists():
        if not root.is_dir() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
            raise ConfigError(
                "Source-build installation directory must be administrator-owned and mode 0700."
            )
        if any(root.iterdir()) and not (root / "installation.json").is_file():
            try:
                if marker.is_symlink() or json.loads(marker.read_text()) != {
                    "schema_version": 1,
                    "installation_sha256": identity,
                }:
                    raise ValueError
            except (OSError, ValueError) as exc:
                raise ConfigError(
                    "Source build will not claim an unrelated nonempty installation directory."
                ) from exc
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(marker, json.dumps({"schema_version": 1, "installation_sha256": identity}) + "\n")
    target = root / "public-builds"
    if target.is_symlink():
        raise ConfigError("Public build state must remain inside the installation directory.")
    target.mkdir(exist_ok=True, mode=0o700)
    if target.stat().st_uid != os.getuid() or target.stat().st_mode & 0o077:
        raise ConfigError("Public build state must be administrator-owned and mode 0700.")
    return target


def build_source_image(
    bundle_root,
    installation_root,
    *,
    node_image,
    publisher_core_commit,
    apply=False,
    online=False,
    runner=None,
):
    """Build the actual source Dockerfile; return an immutable local image receipt.

    ``online=True`` is an explicit public software acquisition operation, distinct
    from case processing. Offline mode gives Node and Docker no outbound network.
    ``runner(command, timeout=seconds)`` is injectable for transport tests; raw
    runner errors/output never appear in the public result.
    """
    source, manifest, source_hash, bases = _verified_bundle(bundle_root, publisher_core_commit)
    if not isinstance(node_image, str) or not IMAGE.fullmatch(node_image):
        raise ConfigError("Node build image must use an immutable repository digest.")
    root = checked_installation_root(installation_root)
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ConfigError("Source bundle and installation storage must be separate directories.")
    identity = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    tag = "forte26-build-" + identity + ":" + publisher_core_commit[:12] + "-" + source_hash[:12]
    receipt_path = (
        root / "public-builds" / (publisher_core_commit[:12] + "-" + source_hash[:12] + ".json")
    )
    result = {
        "ok": False,
        "preview": not apply,
        "core_commit": publisher_core_commit,
        "node_image": node_image,
        "base_images": bases,
        "image_tag": tag,
        "local_image_id": None,
        "receipt": str(receipt_path),
        "source_manifest_sha256": source_hash,
        "private_inputs": False,
        "gpu_used": False,
        "runtime_verified": False,
        "browser_access_verified": False,
        "quality_accepted": False,
        "online_public_preparation": bool(online),
        "unresolved_prerequisites": [],
        "dependency_limit": (
            "Pinned source/base/lockfiles; apt repositories are not a hermetic OS snapshot."
        ),
    }
    if not apply:
        result["ok"] = True
        return result
    runner = runner or _run
    target = _owned_build_root(root)
    import fcntl

    descriptor = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConfigError(
                "Another public source build owns this installation; no image was replaced."
            ) from None
        for image in dict.fromkeys([node_image, *bases]):
            _ensure_image(image, online, runner)
        # Reuse only a receipt bound to this exact source, Node image and image ID.
        if receipt_path.exists():
            if receipt_path.is_symlink():
                raise ConfigError("Build receipt must remain a regular owned file.")
            previous = json.loads(receipt_path.read_text())
            image_id = previous.get("local_image_id") if isinstance(previous, dict) else None
            if (
                isinstance(previous, dict)
                and previous.get("core_commit") == publisher_core_commit
                and previous.get("node_image") == node_image
                and previous.get("source_manifest_sha256") == source_hash
                and isinstance(image_id, str)
                and IMAGE_ID.fullmatch(image_id)
            ):
                inspected = runner(
                    ["docker", "image", "inspect", "--format", "{{.Id}}", image_id], timeout=30
                )
                if inspected.returncode == 0 and inspected.stdout.strip() == image_id:
                    result.update(ok=True, local_image_id=image_id, reused=True)
                    return result
            raise ConfigError(
                "Existing build receipt cannot be reused; preserve it and select "
                "a separate installation."
            )
        with tempfile.TemporaryDirectory(prefix="source-", dir=target) as temporary:
            snapshot = Path(temporary) / "snapshot"
            snapshot.mkdir(mode=0o700)
            for name, info in manifest["files"].items():
                destination = snapshot / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with _open_source(source, name) as original, destination.open("xb") as output:
                    shutil.copyfileobj(original, output)
                    os.fchmod(output.fileno(), stat.S_IMODE(info["mode"]))
            # Do not follow a changing source bundle between validation and copy.
            for name, info in manifest["files"].items():
                with (snapshot / name).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != info["sha256"]:
                        raise ConfigError(
                            "Source changed during isolated copy; no image was built."
                        )
            script = "npm ci && npm run build" if online else "npm ci --offline && npm run build"
            node = [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network=" + ("bridge" if online else "none"),
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--user",
                str(os.getuid()) + ":" + str(os.getgid()),
                "--env",
                "NEXT_TELEMETRY_DISABLED=1",
                "--env",
                "npm_config_cache=/snapshot/.npm-cache",
                "--env",
                "npm_config_audit=false",
                "--env",
                "npm_config_fund=false",
                "--volume",
                str(snapshot) + ":/snapshot",
                "--workdir",
                "/snapshot/web",
                "--entrypoint",
                "sh",
                node_image,
                "-c",
                script,
            ]
            if runner(node, timeout=1800).returncode:
                raise ConfigError(
                    "Pinned frontend build failed; check public dependency access/cache and retry."
                )
            # npm output is generated only inside the isolated public build tree.
            if not (snapshot / "web/out/index.html").is_file():
                raise ConfigError(
                    "The frontend build did not produce the application's static entry point."
                )
            # The one-off dependency cache is public preparation state, not an
            # application asset or a shared cache that this tool may prune.
            cache = snapshot / ".npm-cache"
            if cache.exists():
                shutil.rmtree(cache)
            build = [
                "docker",
                "build",
                "--pull=false",
                "--network=" + ("default" if online else "none"),
                "--tag",
                tag,
                str(snapshot),
            ]
            if runner(build, timeout=3600).returncode:
                raise ConfigError(
                    "Pinned core image build failed; no application or GPU service was started."
                )
            inspected = runner(
                ["docker", "image", "inspect", "--format", "{{.Id}}", tag], timeout=30
            )
            image_id = inspected.stdout.strip() if inspected.returncode == 0 else ""
            if not IMAGE_ID.fullmatch(image_id):
                raise ConfigError(
                    "Built image identity could not be verified; no runtime was activated."
                )
        result.update(ok=True, preview=False, local_image_id=image_id, reused=False)
        private_write(receipt_path, json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    except ConfigError as exc:
        result["unresolved_prerequisites"] = [str(exc)]
        return result
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        result["unresolved_prerequisites"] = [
            "Public source preparation failed or timed out; retry locally. "
            "Credentials and subprocess output were withheld."
        ]
        return result
    finally:
        os.close(descriptor)
