"""Publish only pinned small public installation resources into an admin archive.

This reads explicit allowlisted files, never directory trees or model shards.
Public derived ONNX files remain outside Git and enter only the release archive.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_BYTES = 128 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
LEGAL = re.compile(
    r"legal/(?:rule-cards\.json|\d{4}-\d{2}-\d{2}/(?:manifest\.json|corpus\.json|"
    r"V[0-9]+/[0-9a-f-]{36}/(?:metadata\.json|versions\.json|content\.json|source\.html)))"
)
CONFIGS = {"repository/configs/frozen-inference.json", "repository/configs/person-tracking.json"}
REID = {"models/public/reid/osnet.onnx", "models/public/reid/manifest.json"}
MODEL_FILES = {
    "LICENSE",
    "README.md",
    "chat_template.jinja",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors.index.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "video_preprocessor_config.json",
    "vocab.json",
} | {f"model-{number:05d}-of-00018.safetensors" for number in range(1, 19)}


class BundleError(ValueError):
    """Safe diagnostic identifying a public artifact class, never raw file data."""


def _relative(value):
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
        and "\\" not in value
        and not any(ord(char) < 32 for char in value)
    )


def _root(path):
    selected = Path(path).expanduser()
    if selected.is_symlink():
        raise BundleError("Public bundle roots must not be symbolic links.")
    return selected.resolve()


def _path(root, relative):
    if not _relative(relative):
        raise BundleError("Public bundle paths must be safe relative paths.")
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise BundleError("Public bundle inputs must not contain symbolic links.")
    if not path.resolve().is_relative_to(root):
        raise BundleError("Public bundle input escapes its selected public root.")
    return path


def _read(path, limit, *, size=None, digest=None):
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as source:
            status = os.fstat(source.fileno())
            if not stat.S_ISREG(status.st_mode) or status.st_size > limit:
                raise BundleError("A selected public bundle file exceeds its size/type bound.")
            if size is not None and status.st_size != size:
                raise BundleError("A selected public bundle file differs from its pinned size.")
            data = source.read(limit + 1)
            if len(data) > limit or (size is not None and len(data) != size):
                raise BundleError("A selected public bundle file exceeds its pinned byte bound.")
            if digest is not None and hashlib.sha256(data).hexdigest() != digest:
                raise BundleError(
                    "A selected public bundle file failed pinned SHA256 verification."
                )
            return data
    except OSError:
        raise BundleError("A required pinned public bundle file is unavailable.") from None


def _json(root, relative):
    try:
        value = json.loads(_read(_path(root, relative), MAX_METADATA_BYTES))
    except BundleError:
        raise
    except (ValueError, UnicodeError):
        raise BundleError("The pinned public bundle manifest is not valid JSON.") from None
    if not isinstance(value, dict):
        raise BundleError("The pinned public bundle manifest must be a JSON object.")
    return value


def _inventory(inventory):
    if inventory.get("schema_version") != "forte.public-assets/1":
        raise BundleError("The canonical public resource inventory schema is required.")
    files = inventory.get("files")
    model = inventory.get("model")
    if not isinstance(files, list) or not isinstance(model, dict):
        raise BundleError("The canonical public inventory has invalid file/model fields.")
    revision = model.get("revision")
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise BundleError("The public model snapshot revision must be immutable.")
    index = {}
    for item in files:
        if not isinstance(item, dict):
            raise BundleError("Invalid canonical public inventory entry.")
        container = item.get("container_path", "")
        if not isinstance(container, str):
            raise BundleError("Invalid canonical public mount path.")
        if container.startswith(("/models/", "/legal/")):
            destination = container.lstrip("/")
        elif item.get("root") == "repository" and _relative(item.get("relative_path")):
            destination = "repository/" + item["relative_path"]
        else:
            raise BundleError("Unsupported public inventory mount mapping.")
        if not _relative(destination) or destination in index:
            raise BundleError("Public inventory paths must be safe and unique.")
        index[destination] = item
    return index, revision


def bundle_entries(repository_root, *, public_artifacts_root=None):
    """Return archive entries prefixed ``public-resources/`` after verification.

    An explicit artifact root supplies ``reid/osnet.onnx`` and
    ``reid/manifest.json``. The detector ``yolox_s.onnx`` is optional because its
    pinned public download exists. Other model files are deliberately excluded.
    Missing derived artifacts, corrupt bytes or unsafe paths raise ``BundleError``.
    """
    root = _root(repository_root)
    artifacts = _root(public_artifacts_root) if public_artifacts_root is not None else None
    manifest = _json(root, "deploy/portable/core-current.candidate.json")
    inventory = _json(root, "contracts/frozen-assets-v1.json")
    index, revision = _inventory(inventory)
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise BundleError("The integration candidate must inventory its public resources.")
    entries, seen, total = {}, set(), 0
    for asset in assets:
        if not isinstance(asset, dict):
            raise BundleError("Invalid public installation resource entry.")
        path, digest, size = asset.get("path"), asset.get("sha256"), asset.get("size_bytes")
        if (
            not _relative(path)
            or path in seen
            or not isinstance(digest, str)
            or not SHA.fullmatch(digest)
            or (size is not None and (type(size) is not int or size <= 0))
        ):
            raise BundleError("Public resources require unique relative paths and pinned hashes.")
        seen.add(path)
        canonical = index.get(path)
        if path != "config/frozen-inference.json" and (
            canonical is None
            or digest != canonical.get("sha256")
            or size != canonical.get("size_bytes")
        ):
            raise BundleError("A bundle resource differs from the canonical public inventory.")
        if path == "config/frozen-inference.json":
            source = _path(root, "contracts/frozen-effective-config-v1.json")
        elif path == f"models/snapshots/{revision}/model-hashes.json":
            source = _path(root, "contracts/frozen-model-hashes-v1.json")
        elif LEGAL.fullmatch(path):
            source = _path(root, path)
        elif path in CONFIGS:
            source = _path(root, path.removeprefix("repository/"))
        elif path in REID:
            if artifacts is None:
                raise BundleError(
                    "Supply the approved public artifacts root "
                    "containing frozen ReID ONNX and manifest."
                )
            source = _path(artifacts, path.removeprefix("models/public/"))
        elif path == "models/public/yolox_s.onnx":
            if artifacts is None:
                continue
            source = _path(artifacts, "yolox_s.onnx")
            if not source.exists():
                continue
        elif path.startswith(f"models/snapshots/{revision}/"):
            # Downloadable snapshot files, including 27B shards, are not opened.
            if path.removeprefix(f"models/snapshots/{revision}/") not in MODEL_FILES:
                raise BundleError("The public model bundle filename is not allowlisted.")
            continue
        else:
            raise BundleError("Public bundle resource filename or mount root is not allowed.")
        if size is not None and size > MAX_FILE_BYTES:
            raise BundleError("A bundled public resource exceeds the allowed publisher size.")
        data = _read(source, MAX_FILE_BYTES, size=size, digest=digest)
        total += len(data)
        if total > MAX_BUNDLE_BYTES:
            raise BundleError("Public resource bundle exceeds the allowed publisher size.")
        entries["public-resources/" + path] = data
    return entries
