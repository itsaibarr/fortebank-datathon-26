"""Prepare only the pinned public files in the core installation handoff.

No case directories, credentials, model execution, export or inference are inputs.
The default is a nonmutating, offline inventory. Online preparation is explicit;
all downloaded bytes are hashed before publication and have a fixed size bound.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import secrets
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHA = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
CHUNK = 1024 * 1024
MAX_FILE_SECONDS = 2 * 60 * 60
HF_ORIGINS = frozenset(
    {
        "https://huggingface.co",
        "https://cdn-lfs.huggingface.co",
        "https://cdn-lfs-us-1.hf.co",
        "https://cdn-lfs-eu-1.hf.co",
        "https://cas-bridge.xethub.hf.co",
    }
)
GITHUB_ORIGINS = frozenset({"https://github.com", "https://release-assets.githubusercontent.com"})


class ResourceError(ValueError):
    """A fixed, safe diagnostic; never include response bodies or signed URLs."""


def _relative(value):
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
        and "\\" not in value
        and not any(ord(char) < 32 for char in value)
    )


def _path(root, relative):
    if not _relative(relative):
        raise ResourceError("Invalid public resource path.")
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ResourceError("Resource paths must not contain symbolic links.")
    if not path.resolve().is_relative_to(root):
        raise ResourceError("Resource path escapes the selected directory.")
    return path


def _open_file(path, flags=os.O_RDONLY):
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ResourceError("Public resources must be regular files.")
    return os.fdopen(fd, "rb" if flags == os.O_RDONLY else "r+b")


def _verified(path, spec):
    try:
        with _open_file(path) as source:
            if spec["size"] is not None and os.fstat(source.fileno()).st_size != spec["size"]:
                return False
            return hashlib.file_digest(source, "sha256").hexdigest() == spec["sha256"]
    except FileNotFoundError:
        return False


def _origin(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
            or parsed.fragment
        ):
            raise ValueError
        return "https://" + parsed.hostname.lower()
    except ValueError as exc:
        raise ResourceError("Public resource URL is not an approved HTTPS address.") from exc


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    def __init__(self, origins):
        self.origins = origins

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(newurl) not in self.origins:
            raise ResourceError("Public resource redirect targets an unapproved origin.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PublicTransport:
    """No environment proxies, netrc, cookies or authorization handlers."""

    def __init__(self, origins):
        self.origins = origins
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _RedirectGuard(origins)
        )

    def open(self, url, headers):
        if _origin(url) not in self.origins:
            raise ResourceError("Public resource origin is not approved.")
        response = self.opener.open(urllib.request.Request(url, headers=headers), timeout=30)
        if _origin(response.geturl()) not in self.origins:
            response.close()
            raise ResourceError("Public resource response origin is not approved.")
        return response


def _source_url(entry, inventory):
    """Treat legal page URLs as provenance, never as JSON download locations."""
    url = entry.get("source_url")
    if not url:
        return None, frozenset()
    model = inventory.get("model", {})
    if not isinstance(model, dict):
        raise ResourceError("Canonical model identity must be a JSON object.")
    repository, revision = model.get("repository"), model.get("revision")
    relative = entry.get("relative_path")
    if not _relative(relative):
        raise ResourceError("Canonical public source must have a safe relative path.")
    if (
        entry.get("root") == "models"
        and isinstance(repository, str)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        and isinstance(revision, str)
        and REVISION.fullmatch(revision)
        and relative.startswith(revision + "/")
    ):
        filename = relative.removeprefix(revision + "/")
        expected = f"https://huggingface.co/{repository}/resolve/{revision}/{filename}"
        if url != expected or not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
            raise ResourceError("Model source must name the exact pinned public snapshot file.")
        return url, HF_ORIGINS
    detector_url = (
        "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx"
    )
    if entry.get("container_path") == "/models/public/yolox_s.onnx" and url == detector_url:
        return url, GITHUB_ORIGINS
    if entry.get("root") == "legal":
        # The release contains the exact immutable official-source snapshot.
        # Fetching current official pages cannot reproduce its JSON/raw revision.
        return None, frozenset()
    raise ResourceError("No approved public download source exists for this resource.")


def _specifications(manifest, inventory):
    if inventory.get("schema_version") != "forte.public-assets/1":
        raise ResourceError("Expected the canonical public resource inventory.")
    indexed = {}
    files = inventory.get("files", [])
    if not isinstance(files, list):
        raise ResourceError("Canonical public resource files must be an array.")
    for entry in files:
        if not isinstance(entry, dict):
            raise ResourceError("Invalid canonical public resource entry.")
        container = entry.get("container_path", "")
        if not isinstance(container, str):
            raise ResourceError("Canonical public resource mount mapping must be a string.")
        if container.startswith(("/models/", "/legal/")):
            relative = container.lstrip("/")
        elif entry.get("root") == "repository":
            relative = "repository/" + entry.get("relative_path", "")
        else:
            raise ResourceError("Canonical public resource has no supported mount mapping.")
        if not _relative(relative) or relative in indexed:
            raise ResourceError("Canonical resource paths must be safe and unique.")
        indexed[relative] = entry
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ResourceError("The integration manifest must inventory pinned public resources.")
    specs, seen = [], set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ResourceError("Invalid integration resource entry.")
        path, digest, size = asset.get("path"), asset.get("sha256"), asset.get("size_bytes")
        if (
            not _relative(path)
            or path in seen
            or not isinstance(digest, str)
            or not SHA.fullmatch(digest)
            or (size is not None and (type(size) is not int or size <= 0))
        ):
            raise ResourceError("Integration resources require unique paths and SHA256 hashes.")
        seen.add(path)
        entry = indexed.get(path)
        if entry is None:
            if path != "config/frozen-inference.json":
                raise ResourceError(
                    "Integration resource is not in the canonical public inventory."
                )
            url, origins = None, frozenset()
            bundled = "contracts/frozen-effective-config-v1.json"
        else:
            if digest != entry.get("sha256") or size != entry.get("size_bytes"):
                raise ResourceError(
                    "Integration resource differs from the canonical public inventory."
                )
            url, origins = _source_url(entry, inventory)
            bundled = (
                "legal/" + entry["relative_path"]
                if entry["root"] == "legal"
                else entry["relative_path"]
                if entry["root"] == "repository"
                else None
            )
            if path.endswith("/model-hashes.json"):
                bundled = "contracts/frozen-model-hashes-v1.json"
        specs.append(
            {
                "path": path,
                "sha256": digest,
                "size": size,
                "url": url,
                "origins": origins,
                "bundled": bundled,
            }
        )
    return specs


def _write_json(path, value):
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _copy(source, destination, spec):
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_name(destination.name + "." + secrets.token_hex(8) + ".import")
    copied = 0
    try:
        with _open_file(source) as incoming:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as outgoing:
                while chunk := incoming.read(CHUNK):
                    copied += len(chunk)
                    if spec["size"] is not None and copied > spec["size"]:
                        raise ResourceError("Imported public resource exceeds its pinned size.")
                    outgoing.write(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
        if not _verified(temporary, spec):
            raise ResourceError("Imported public resource failed SHA256 verification.")
        os.replace(temporary, destination)
        return copied
    finally:
        temporary.unlink(missing_ok=True)


def _strong_etag(value):
    return isinstance(value, str) and bool(re.fullmatch(r'"[\x21\x23-\x7e]{0,200}"', value))


def _download(spec, destination, *, _transport=None):
    """Tests alone inject synthetic HTTP transport; installer exposes no such option."""
    size = spec["size"]
    if size is None:
        raise ResourceError("Online preparation requires an exact pinned byte size.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = _path(destination.parent, destination.name + ".part")
    metadata = _path(destination.parent, destination.name + ".part.json")
    identity = {"url": spec["url"], "sha256": spec["sha256"], "size": size}
    offset, previous_etag = 0, None
    if partial.exists():
        with _open_file(partial) as stream:
            offset = os.fstat(stream.fileno()).st_size
        if offset > size:
            raise ResourceError("Partial public resource exceeds its pinned byte size.")
        if offset == size:
            if not _verified(partial, spec):
                raise ResourceError("Complete partial resource failed SHA256 verification.")
            os.replace(partial, destination)
            metadata.unlink(missing_ok=True)
            return 0
        if offset:
            try:
                if metadata.stat().st_size > 4096:
                    raise ValueError
                with _open_file(metadata) as source:
                    previous = json.load(source)
                if not isinstance(previous, dict) or any(
                    previous.get(key) != value for key, value in identity.items()
                ):
                    raise ValueError
                previous_etag = previous.get("etag")
            except (OSError, ValueError):
                raise ResourceError("Partial public resource metadata is invalid.") from None
            # Without a strong validator, restart rather than combine representations.
            if not _strong_etag(previous_etag):
                offset = 0
    headers = {"Accept-Encoding": "identity", "User-Agent": "forte-admin-public-preparation/1"}
    if offset:
        headers.update({"Range": f"bytes={offset}-", "If-Range": previous_etag})
    transport = _transport or _PublicTransport(spec["origins"])
    started, written = time.monotonic(), 0
    try:
        with transport.open(spec["url"], headers) as response:
            status = response.status
            etag = response.headers.get("ETag")
            encoding = response.headers.get("Content-Encoding", "identity")
            if encoding.lower() != "identity":
                raise ResourceError("Public resource response unexpectedly encoded its bytes.")
            if status == 206 and offset:
                match = re.fullmatch(
                    r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", "")
                )
                if (
                    not match
                    or int(match[1]) != offset
                    or int(match[3]) != size
                    or not offset <= int(match[2]) < size
                    or etag != previous_etag
                ):
                    raise ResourceError(
                        "Public resource resume response has invalid range or ETag."
                    )
                expected = int(match[2]) - offset + 1
            elif status == 200 and not response.headers.get("Content-Range"):
                offset, expected = 0, size
            else:
                raise ResourceError(
                    "Public resource server did not return the requested representation."
                )
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdecimal() or int(length) != expected):
                raise ResourceError(
                    "Public resource response length differs from its pinned range."
                )
            _write_json(metadata, identity | {"etag": etag if _strong_etag(etag) else None})
            with _open_file(partial, os.O_RDWR | os.O_CREAT) as output:
                output.truncate(offset)
                output.seek(offset)
                while chunk := response.read(CHUNK):
                    if time.monotonic() - started > MAX_FILE_SECONDS:
                        raise ResourceError("Public resource preparation reached its time limit.")
                    if written + len(chunk) > expected:
                        raise ResourceError(
                            "Public resource response exceeds its pinned byte limit."
                        )
                    output.write(chunk)
                    written += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            if written != expected or offset + written != size:
                raise ResourceError(
                    "Public resource transfer is incomplete; verified resume is available."
                )
        if not _verified(partial, spec):
            raise ResourceError("Downloaded public resource failed SHA256 verification.")
        os.replace(partial, destination)
        metadata.unlink(missing_ok=True)
        return written
    except ResourceError:
        raise
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError):
        raise ResourceError(
            "Public resource transfer failed; retry to resume retained public bytes."
        ) from None


def _image(image, artifact, apply, runner):
    if not isinstance(image, str) or not IMAGE_ID.fullmatch(image):
        return {
            "status": "missing",
            "reason": (
                "Core image import requires a pinned local image ID; "
                "registry digests are prepared separately."
            ),
        }
    run = runner or subprocess.run

    def inspect():
        try:
            result = run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return result.returncode == 0 and result.stdout.strip() == image
        except (OSError, subprocess.SubprocessError):
            return False

    if inspect():
        return {"status": "present", "reason": "Pinned core image ID is installed."}
    if artifact is None:
        return {
            "status": "missing",
            "reason": "Supply the approved docker-save artifact for the pinned core image ID.",
        }
    artifact = Path(artifact).expanduser()
    try:
        if artifact.is_symlink():
            raise ResourceError("Image artifacts must be regular local files.")
        with _open_file(artifact):
            pass
        if not apply:
            return {
                "status": "available",
                "reason": (
                    "Explicit image import is planned; identity is verified after docker load."
                ),
            }
        run(
            ["docker", "load", "--input", str(artifact.resolve())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
            check=True,
        )
        if not inspect():
            raise ResourceError("Imported image does not provide the pinned core image ID.")
        return {
            "status": "prepared",
            "reason": "Imported core image ID matches the immutable handoff.",
        }
    except (OSError, subprocess.SubprocessError, ResourceError):
        return {
            "status": "missing",
            "reason": "Approved core image artifact import or identity verification failed.",
        }


def prepare_resources(
    manifest,
    resources_root,
    *,
    apply=False,
    online=False,
    source_dir=None,
    image_artifact=None,
    inventory=None,
    snapshot_root=None,
    runner=None,
):
    """Inventory/import/download exact public resources; never infer readiness.

    ``source_dir`` is an operator-prepared directory (or list of directories) with
    the same relative paths as ``manifest.assets``. A shipped ``public-resources``
    bundle is also searched. The isolated shipped snapshot supplies only pinned
    legal/config files. ``apply=False`` performs no writes or network requests.
    A report with ``ok=False`` is a prerequisite failure, never a hosted fallback.
    """
    report = {
        "ok": False,
        "preview": not apply,
        "online_requested": online,
        "items": [],
        "prepared": 0,
        "present": 0,
        "missing": 0,
        "corrupt": 0,
        "bytes": 0,
        "partial_bytes": 0,
        "unresolved_prerequisites": [],
    }
    try:
        if not isinstance(manifest, dict):
            raise ResourceError("The integration manifest must be a JSON object.")
        if inventory is None:
            inventory = json.loads((ROOT / "contracts/frozen-assets-v1.json").read_text())
        if not isinstance(inventory, dict):
            raise ResourceError("The public resource inventory must be a JSON object.")
        specs = _specifications(manifest, inventory)
        root = Path(resources_root).expanduser().resolve()
        if any((p / ".git").exists() for p in (root, *root.parents)):
            raise ResourceError("Prepared resources must be stored outside a Git checkout.")
        snapshot = Path(snapshot_root).resolve() if snapshot_root else ROOT
        selected_sources = source_dir if isinstance(source_dir, (list, tuple)) else [source_dir]
        sources = [Path(path).expanduser().resolve() for path in selected_sources if path]
        sources.append(snapshot / "public-resources")
        for spec in specs:
            item = {"path": spec["path"], "status": "missing", "bytes": 0, "partial_bytes": 0}
            try:
                destination = _path(root, spec["path"])
                exists = destination.exists()
                if exists and _verified(destination, spec):
                    item.update(status="present", reason="Pinned SHA256 and size match.")
                else:
                    candidates = []
                    for source in sources:
                        candidates.append(_path(source, spec["path"]))
                    if spec["bundled"]:
                        candidates.append(_path(snapshot, spec["bundled"]))
                    valid = None
                    corrupt_source = False
                    for candidate in candidates:
                        if candidate.exists():
                            if _verified(candidate, spec):
                                valid = candidate
                                break
                            corrupt_source = True
                    if exists or corrupt_source:
                        item["corruption_detected"] = True
                    if valid:
                        if apply:
                            item["bytes"] = _copy(valid, destination, spec)
                        item.update(
                            status="prepared" if apply else "available",
                            reason="Pinned local public resource imported."
                            if apply
                            else "Pinned local public resource is available for import.",
                        )
                    elif spec["url"] and online:
                        if apply:
                            item["bytes"] = _download(spec, destination)
                        item.update(
                            status="prepared" if apply else "available",
                            reason="Pinned public resource acquired."
                            if apply
                            else "Explicit pinned public download is planned.",
                        )
                    else:
                        item.update(
                            status="corrupt" if exists or corrupt_source else "missing",
                            reason="A local public resource failed its pinned SHA256 or size."
                            if exists or corrupt_source
                            else "Supply the approved local public resource bundle."
                            if not spec["url"]
                            else "Supply a local bundle or explicitly enable public downloads.",
                        )
            except ResourceError as exc:
                item.update(status="corrupt", reason=str(exc))
            except (OSError, ValueError):
                item.update(
                    status="missing", reason="Public resource could not be safely read or prepared."
                )
            if item["status"] in {"missing", "corrupt"}:
                try:
                    partial = _path(root, spec["path"] + ".part")
                    if partial.exists():
                        with _open_file(partial) as stream:
                            item["partial_bytes"] = os.fstat(stream.fileno()).st_size
                except (OSError, ResourceError):
                    pass
            report["items"].append(item)
            if item["status"] in {"prepared", "present", "missing", "corrupt"}:
                report[item["status"]] += 1
            report["bytes"] += item["bytes"]
            report["partial_bytes"] += item["partial_bytes"]
            if item["status"] in {"missing", "corrupt"}:
                report["unresolved_prerequisites"].append(f"{spec['path']}: {item['reason']}")
        core = manifest.get("core", {})
        if not isinstance(core, dict):
            raise ResourceError("The integration core identity must be a JSON object.")
        report["image"] = _image(core.get("image"), image_artifact, apply, runner)
        if report["image"]["status"] not in {"present", "prepared", "available"}:
            report["unresolved_prerequisites"].append(report["image"]["reason"])
        report["ok"] = not report["unresolved_prerequisites"]
    except (ResourceError, OSError, ValueError, TypeError) as exc:
        report["unresolved_prerequisites"].append(
            str(exc)
            if isinstance(exc, ResourceError)
            else "Pinned resource inventory could not be safely loaded."
        )
    return report
