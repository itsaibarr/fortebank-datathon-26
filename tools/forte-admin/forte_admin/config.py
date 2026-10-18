"""Nonsecret installation state, separate from endpoint credential profiles."""

import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    pass


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError("Cannot read the selected JSON configuration.") from exc
    if not isinstance(value, dict):
        raise ConfigError("Configuration must be a JSON object.")
    return value


def private_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def installation_root(path):
    root = Path(path).expanduser().resolve()
    # Never put credentials, writable case volumes or deployment state in a checkout.
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ConfigError("Installation state must be outside a Git checkout.")
    return root


def plan(root, changes):
    root = installation_root(root)
    previous = (
        read_json(root / "installation.json") if (root / "installation.json").exists() else {}
    )
    result = {
        "schema_version": 1,
        "mode": "private",
        "project_name": "forte-" + hashlib.sha256(str(root).encode()).hexdigest()[:12],
        "origin": "https://localhost:8443",
        "bind_address": "127.0.0.1",
        "https_port": 8443,
        "bridge_port": 18001,
        "gpu_index": None,
        "gpu_uuid": None,
        "backend": "cuda",
        "qualification_timeout": 360,
        "session_port": 18002,
        "session_db": str(root / "auth" / "sessions.sqlite3"),
        "attach_upstream": "http://127.0.0.1:18000",
        "core_image": "",
        "proxy_image": (
            "nginx@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de"
        ),
        "deployment_mode": "private",
        "integration_manifest": "",
        "manifest_sha256": "",
        "resources_root": str(root / "resources"),
        "data_root": str(root / "data"),
        "secrets_root": str(root / "secrets"),
        "tls_cert": str(root / "tls" / "fullchain.pem"),
        "tls_key": str(root / "tls" / "privkey.pem"),
        "multi_user_uploads": False,
        "access_mode": "browser-session",
        "retention": (
            "manual; originals, derivatives, corrections and backups persist until "
            "administrator deletion"
        ),
        "training_use": "disabled; uploads are not training data",
    }
    allowed = set(result) | {"htpasswd_file"}
    if set(previous) - allowed or set(changes) - allowed:
        raise ConfigError(
            "Unknown installation fields were rejected; never put credentials in installation JSON."
        )
    result.update(previous)
    result.update({key: value for key, value in changes.items() if value is not None})
    for name in (
        "integration_manifest",
        "resources_root",
        "data_root",
        "secrets_root",
        "tls_cert",
        "tls_key",
        "htpasswd_file",
        "session_db",
    ):
        if result.get(name):
            result[name] = str(Path(result[name]).expanduser().resolve())
    if result.get("backend") != "cuda":
        raise ConfigError(
            "This release implements the CUDA backend only; no CPU or hosted fallback was selected."
        )
    if result.get("gpu_index") is not None and (
        type(result["gpu_index"]) is not int or result["gpu_index"] < 0
    ):
        raise ConfigError("Select a nonnegative GPU index.")
    if result.get("gpu_uuid") is not None and not re.fullmatch(
        r"GPU-[A-Za-z0-9-]+", str(result["gpu_uuid"])
    ):
        raise ConfigError("Invalid selected GPU UUID.")
    if result["mode"] not in {"private", "attach"}:
        raise ConfigError("Choose private or attach mode.")
    if result["deployment_mode"] not in {"private", "hosted"}:
        raise ConfigError("Choose a private or hosted processing destination label.")
    if not re.fullmatch(r"forte-[a-z0-9-]{1,40}", result["project_name"]):
        raise ConfigError(
            "Project name must begin forte- and use lowercase letters, digits or hyphens."
        )
    origin = urlsplit(result["origin"])
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in {"", "/"}
    ):
        raise ConfigError("Application origin must be a credential-free HTTPS origin.")
    try:
        port = origin.port or 443
    except ValueError as exc:
        raise ConfigError("Invalid application port.") from exc
    if port != result["https_port"]:
        raise ConfigError("Origin port and HTTPS listener port must agree.")
    if result.get("integration_manifest"):
        manifest_path = Path(result["integration_manifest"])
        manifest = read_json(manifest_path)
        if not isinstance(manifest.get("core"), dict):
            raise ConfigError("Integration manifest requires a core object.")
        result["core_image"] = manifest.get("core", {}).get("image", "")
        result["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return result, previous


def apply(root, config, render):
    root = installation_root(root)
    if root.exists() and any(root.iterdir()) and not (root / "installation.json").is_file():
        raise ConfigError(
            "Choose an empty installation directory; unrelated existing files were preserved."
        )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise ConfigError(
            "Installation directory must be owner-only; existing permissions were preserved."
        )
    for name in ("data_root", "secrets_root"):
        directory = installation_root(config[name])
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
            raise ConfigError(
                "Data and secret directories must be owner-only; existing permissions "
                "were preserved."
            )
    secret = Path(config["secrets_root"]) / "core-api.key"
    if config["mode"] == "private" and not secret.exists():
        fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(secrets.token_urlsafe(48) + "\n")
    if config["access_mode"] == "browser-session":
        token = Path(config["secrets_root"]) / "gateway-token"
        if not token.exists():
            descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write(secrets.token_urlsafe(48) + "\n")
    # No imaginary administrator account: browser bootstrap is the core session layer's job.
    paths = render(config, root / "runtime")
    private_write(root / "installation.json", json.dumps(config, indent=2) + "\n")
    return paths
