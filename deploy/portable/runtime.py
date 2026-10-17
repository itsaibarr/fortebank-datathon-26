"""Render and operate installer-owned Compose projects without touching shared services.

The integration manifest is an operator-reviewed release handoff, not an approval
created by this tool. Validation cannot establish detection or legal accuracy.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IMAGE = re.compile(r"(?:[a-zA-Z0-9][a-zA-Z0-9._:/-]*@)?sha256:[0-9a-f]{64}")
PROJECT = re.compile(r"[a-z][a-z0-9-]{2,47}")
SHA = re.compile(r"[0-9a-f]{64}")
DEFAULTS = {
    "bind_address": "127.0.0.1",
    "https_port": 8443,
    "access_mode": "browser-session",
    "multi_user_uploads": False,
}


def _config(config):
    return DEFAULTS | config


def _absolute(value):
    return isinstance(value, str) and Path(value).is_absolute() and "\n" not in value


def _relative(value):
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
        and "\n" not in value
    )


def validate(config: dict) -> list[str]:
    """Validate structure only; never open resources or start a process."""
    c = _config(config)
    errors = []
    if c.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if c.get("mode") not in {"private", "attach"}:
        errors.append("mode must be private or attach")
    if not PROJECT.fullmatch(str(c.get("project_name", ""))):
        errors.append("project_name must be 3–48 lowercase letters, digits and hyphens")
    try:
        url = urllib.parse.urlsplit(c.get("origin", ""))
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError
        port = url.port or 443
        if port != c["https_port"]:
            errors.append("origin port must match https_port")
    except (ValueError, TypeError):
        errors.append("origin must be an HTTPS origin without credentials or a path")
    for name in ("https_port", "bridge_port"):
        value = c.get(name, 18001)
        if type(value) is not int or not 1024 <= value <= 65535:
            errors.append(f"{name} must be an unprivileged TCP port")
    # These explicit listen addresses prevent an accidental public default.
    if c["bind_address"] not in {"127.0.0.1", "0.0.0.0"}:
        errors.append("bind_address must be 127.0.0.1 or explicitly 0.0.0.0")
    for name in ("proxy_image",):
        if not IMAGE.fullmatch(str(c.get(name, ""))):
            errors.append(
                f"{name} requires an immutable repository digest or local sha256 image ID"
            )
    if c.get("mode") == "private" and not IMAGE.fullmatch(str(c.get("core_image", ""))):
        errors.append("core_image requires an immutable repository digest or local sha256 image ID")
    for name in (
        "integration_manifest",
        "resources_root",
        "data_root",
        "secrets_root",
        "tls_cert",
        "tls_key",
    ):
        if not _absolute(c.get(name)):
            errors.append(f"{name} must be an absolute path")
    if c.get("manifest_sha256") is not None and not SHA.fullmatch(str(c["manifest_sha256"])):
        errors.append("manifest_sha256 must be a SHA256 hash")
    if type(c["multi_user_uploads"]) is not bool:
        errors.append("multi_user_uploads must be boolean")
    if c["access_mode"] not in {"browser-session", "gateway-single-admin"}:
        errors.append("access_mode must be browser-session or gateway-single-admin")
    if c["access_mode"] == "gateway-single-admin":
        if not _absolute(c.get("htpasswd_file")):
            errors.append("gateway-single-admin requires an absolute htpasswd_file")
        if c["multi_user_uploads"]:
            errors.append("gateway-single-admin cannot enable multi_user_uploads")
    if c.get("mode") == "attach":
        try:
            upstream = urllib.parse.urlsplit(c.get("attach_upstream", "http://127.0.0.1:18000"))
            if (
                upstream.scheme != "http"
                or upstream.hostname != "127.0.0.1"
                or upstream.username
                or upstream.password
                or upstream.path not in {"", "/"}
                or upstream.query
                or upstream.fragment
                or not upstream.port
                or upstream.port == 8001
            ):
                raise ValueError
        except (ValueError, TypeError):
            errors.append("attach_upstream must be a literal loopback HTTP origin with a port")
    return errors


def _load_manifest(c):
    try:
        raw = Path(c["integration_manifest"]).read_bytes()
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise ValueError
        return manifest, hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError("Integration manifest is missing or invalid JSON") from exc


def _manifest_errors(c, manifest, *, require_release=True):
    errors = []
    core, model = manifest.get("core", {}), manifest.get("model", {})
    if not isinstance(core, dict) or not isinstance(model, dict):
        return ["manifest core and model must be objects"]
    if manifest.get("schema_version") != 1:
        errors.append("integration manifest schema_version must be 1")
    if not isinstance(manifest.get("verification", {}), dict):
        errors.append("manifest verification must be an object")
    if require_release and not re.fullmatch(r"[0-9a-f]{40}", str(core.get("commit", ""))):
        errors.append("manifest requires a stable core commit")
    if require_release and not IMAGE.fullmatch(str(core.get("image", ""))):
        errors.append("manifest requires a stable immutable core image")
    if require_release and c.get("mode") == "private" and core.get("image") != c.get("core_image"):
        errors.append("configured core image differs from integration manifest")
    if require_release and not SHA.fullmatch(str(core.get("contract_sha256", ""))):
        errors.append("manifest requires the canonical API contract hash")
    if require_release and (
        not all(model.get(k) for k in ("identity", "revision", "profile"))
        or model.get("frozen") is not True
    ):
        errors.append("manifest requires frozen model identity, revision and explicit profile")
    if require_release and (
        not isinstance(manifest.get("corpus"), dict) or not manifest["corpus"].get("version")
    ):
        errors.append("manifest requires the official local corpus version")
    runtime = manifest.get("runtime", {})
    if not isinstance(runtime, dict):
        return errors + ["manifest runtime must be an object"]
    if c.get("mode") == "private" and runtime.get("ipc") != "host":
        errors.append("private IPC setting must match the canonical tested host IPC profile")
    environment = runtime.get("environment", {})
    if not isinstance(environment, dict):
        errors.append("runtime.environment must be an object")
    else:
        for key, value in environment.items():
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"FORTE_[A-Z0-9_]+", key)
                or any(word in key for word in ("SECRET", "PASSWORD", "TOKEN", "API_KEY"))
                or key in {"FORTE_PRIVATE_ROOT", "FORTE_FRONTEND_ROOT"}
                or not isinstance(value, str)
                or "\n" in value
            ):
                errors.append("manifest contains an unsupported runtime environment setting")
                break
        for key in ("FORTE_MODEL_URL",):
            if key in environment and not environment[key].startswith("http://127.0.0.1:"):
                errors.append("model URL must remain container loopback")
    mounts = runtime.get("mounts", [])
    if not isinstance(mounts, list):
        errors.append("runtime.mounts must be an array")
    else:
        targets = set()
        for mount in mounts:
            if (
                not isinstance(mount, dict)
                or not _relative(mount.get("source"))
                or mount.get("target") not in {"/models", "/legal"}
                or mount["target"] in targets
            ):
                errors.append("resource mounts require unique /models or /legal read-only targets")
                break
            targets.add(mount["target"])
    return errors


def prerequisites(config: dict) -> list[str]:
    """Read-only release/resource/security checks. No Docker or GPU operations."""
    c = _config(config)
    errors = validate(c)
    if errors:
        return errors
    try:
        manifest, digest = _load_manifest(c)
    except ValueError as exc:
        return [str(exc)]
    errors += _manifest_errors(c, manifest)
    if c.get("manifest_sha256") != digest:
        errors.append("integration manifest hash has not been pinned or no longer matches")
    verification = manifest.get("verification", {})
    if not isinstance(verification, dict):
        return errors + ["manifest verification must be an object"]
    for key in ("release", "model_workload", "offline_analysis"):
        if verification.get(key) is not True:
            errors.append(f"core handoff has no verified {key} receipt")
    if c["access_mode"] == "browser-session":
        if verification.get("browser_session") is not True:
            errors.append("browser session authentication is not verified")
        if verification.get("ownership") is not True:
            errors.append("per-principal job and media ownership enforcement is not verified")
    if c["multi_user_uploads"] and verification.get("ownership") is not True:
        errors.append("multi-user uploads require verified ownership enforcement")
    root = Path(c["resources_root"]).resolve()
    assets = manifest.get("assets", [])
    if not isinstance(assets, list) or not assets:
        errors.append("manifest must inventory pinned model, tracking and legal resource files")
        assets = []
    for asset in assets:
        if (
            not isinstance(asset, dict)
            or not _relative(asset.get("path"))
            or not SHA.fullmatch(str(asset.get("sha256", "")))
        ):
            errors.append("invalid resource asset entry")
            continue
        path = (root / asset["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            errors.append("a pinned resource file is missing or escapes resources_root")
            continue
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != asset["sha256"]:
                errors.append("a pinned resource file failed SHA256 verification")
        except OSError:
            errors.append("a pinned resource file could not be read")
    receipt = verification.get("receipt")
    if (
        not _relative(receipt)
        or not (root / receipt).resolve().is_relative_to(root)
        or not (root / receipt).is_file()
    ):
        errors.append("local release/workload verification receipt is unavailable")
    tls_available = True
    for name in ("tls_cert", "tls_key"):
        if not Path(c[name]).is_file():
            errors.append(f"{name} file is unavailable")
            tls_available = False
    if tls_available:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(c["tls_cert"], c["tls_key"])
        except (OSError, ssl.SSLError):
            errors.append("supplied TLS certificate/key could not be loaded as a matching pair")
    if c["access_mode"] == "gateway-single-admin":
        if not Path(c["htpasswd_file"]).is_file():
            errors.append("single-administrator password file is unavailable")
    if c["mode"] == "private" or c["access_mode"] == "gateway-single-admin":
        keyfile = Path(c["secrets_root"]) / "core-api.key"
        try:
            key = keyfile.read_text().strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", key):
                raise ValueError
        except (OSError, ValueError):
            errors.append(
                "private core-api.key must be a generated 32–256 character URL-safe secret"
            )
    return errors


def host_prerequisites(config: dict) -> list[str]:
    """Bounded read-only checks of the one supported Linux/A10080 target."""
    c, errors = _config(config), []
    if sys.platform != "linux" or platform.machine() not in {"x86_64", "amd64"}:
        return ["Runtime supports Linux x86_64 only; render/preview works elsewhere"]
    try:
        release = platform.freedesktop_os_release()
        if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
            errors.append("Validated runtime target is Ubuntu 24.04 x86_64")
    except OSError:
        errors.append("Supported host OS version could not be verified")
    if not shutil.which("docker"):
        return ["Docker Engine with Compose v2 is required"]
    try:
        result = _docker(["compose", "version", "--short"])
        if result.returncode or not result.stdout.strip():
            errors.append("Docker Compose v2 is unavailable")
    except (OSError, subprocess.TimeoutExpired):
        return ["Docker Engine or Compose is unavailable"]
    if c["mode"] == "private":
        try:
            docker_runtime = _docker(["info", "--format", "{{json .Runtimes}}"])
            if docker_runtime.returncode or "nvidia" not in json.loads(docker_runtime.stdout):
                errors.append(
                    "NVIDIA Container Toolkit Docker runtime is unavailable; "
                    "no driver/runtime changes made"
                )
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            errors.append("NVIDIA Container Toolkit Docker runtime could not be verified")
        try:
            manifest, _ = _load_manifest(c)
            requirements = manifest.get("runtime", {}).get("requirements", {})
            ram_gib = requirements["min_host_ram_gib"]
            disk_gib = requirements["min_free_disk_gib"]
            driver_major = requirements["driver_major"]
            if (
                type(ram_gib) not in {int, float}
                or ram_gib <= 0
                or type(disk_gib) not in {int, float}
                or disk_gib <= 0
                or type(driver_major) is not int
                or driver_major <= 0
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return errors + [
                "Reviewed private workload RAM, free-disk and driver requirements are missing"
            ]
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if result.returncode or len(lines) != 1:
                raise ValueError
            name, memory, driver = lines[0].rsplit(",", 2)
            if "A100" not in name or "80GB" not in name.upper() or int(memory.strip()) < 79000:
                raise ValueError
            if int(driver.strip().split(".")[0]) != driver_major:
                errors.append(
                    "Installed driver family differs from the reviewed workload; "
                    "no driver changes made"
                )
            occupied = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if occupied.returncode or occupied.stdout.strip():
                errors.append(
                    "GPU is occupied or its allocation cannot be verified; no model was started"
                )
        except (OSError, ValueError, subprocess.TimeoutExpired):
            errors.append(
                "Private runtime supports exactly one verified NVIDIA A100 80 GB; "
                "no fallback selected"
            )
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if pages * page_size < ram_gib * 1024**3:
                errors.append("Host RAM is below the reviewed workload requirement")
        except (OSError, ValueError):
            errors.append("Host physical memory could not be verified")
        for name in ("data_root", "resources_root", "secrets_root"):
            if not Path(c[name]).is_dir():
                errors.append(
                    f"{name} must already exist; startup never creates shared resource directories"
                )
        if (
            Path(c["data_root"]).is_dir()
            and shutil.disk_usage(c["data_root"]).free < disk_gib * 1024**3
        ):
            errors.append(
                "Private storage is below the reviewed free-disk requirement "
                "after resource preparation"
            )
    for port in (
        [c["https_port"], c.get("bridge_port", 18001)]
        if c["mode"] == "private"
        else [c["https_port"]]
    ):
        bind = (
            "127.0.0.1"
            if port == c.get("bridge_port", 18001) and c["mode"] == "private"
            else c["bind_address"]
        )
        try:
            with socket.socket() as listener:
                listener.bind((bind, port))
        except OSError:
            errors.append(
                "A selected installer listener port is already occupied; no service was stopped"
            )
    return errors


def _write(path, value):
    import tempfile

    descriptor, temporary = tempfile.mkstemp(prefix=".forte-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def _volume(source, target):
    return {
        "type": "bind",
        "source": str(source),
        "target": target,
        "read_only": True,
        "bind": {"create_host_path": False},
    }


def render(config: dict, target: Path) -> list[Path]:
    """Write only generated files inside target. No resource or secret mutation."""
    c = _config(config)
    errors = validate(c)
    if errors:
        raise ValueError("; ".join(errors))
    target = Path(target).absolute()
    if target.is_symlink():
        raise ValueError("Installer output directory cannot be a symbolic link")
    previous = target / "installation.json"
    if previous.exists():
        try:
            prior = json.loads(previous.read_text())
        except (OSError, ValueError):
            raise ValueError("Existing installation identity could not be verified") from None
        if any(prior.get(key) != c[key] for key in ("project_name", "mode")):
            raise ValueError(
                "Use a separate installer directory for a different project or profile"
            )
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.chmod(0o700)
    try:
        manifest, _ = _load_manifest(c)
    except ValueError:
        manifest = {}
    manifest_errors = _manifest_errors(c, manifest, require_release=False)
    if manifest and manifest_errors:
        raise ValueError("; ".join(manifest_errors))
    upstream = (
        c.get("attach_upstream", "http://127.0.0.1:18000")
        if c["mode"] == "attach"
        else f"http://127.0.0.1:{c.get('bridge_port', 18001)}"
    )
    # An unverified session layer never becomes an open shared-key gateway.
    verified = manifest.get("verification", {})
    api_enabled = c["access_mode"] == "gateway-single-admin" or (
        verified.get("browser_session") is True and verified.get("ownership") is True
    )
    key_setting = 'set $forte_service_key "";'
    secret_paths = []
    files = []
    if c["access_mode"] == "gateway-single-admin":
        key_setting = "include /run/secrets/upstream-auth.conf;"
        key_path = Path(c["secrets_root"]) / "core-api.key"
        if key_path.is_file():
            key = key_path.read_text().strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", key):
                raise ValueError("core-api.key is not a generated URL-safe secret")
            files.append(
                _write(target / "upstream-auth.conf", f'set $forte_service_key "{key}";\n')
            )
        else:
            files.append(
                _write(
                    target / "upstream-auth.conf",
                    'set $forte_service_key ""; # Missing service key; up is gated.\n',
                )
            )
        secret_paths = [
            _volume(c["htpasswd_file"], "/run/secrets/admin.htpasswd"),
            _volume(target / "upstream-auth.conf", "/run/secrets/upstream-auth.conf"),
        ]
    auth = (
        'auth_basic "Forte administrator";\n'
        "        auth_basic_user_file /run/secrets/admin.htpasswd;"
        if c["access_mode"] == "gateway-single-admin"
        else ""
    )
    api = f"proxy_pass {upstream};" if api_enabled else "return 503;"
    authorization = (
        'proxy_set_header Authorization "";' if c["access_mode"] == "gateway-single-admin" else ""
    )
    nginx = f"""# Generated; no request/access logs or cache of case data.
# Worker stays in this container's root identity to read mode-0600 bind secrets.
# All Linux capabilities are removed; no shared application volumes are mounted.
user root;
pid /tmp/nginx.pid;
error_log /dev/null crit;
events {{ worker_connections 128; }}
http {{
    access_log off;
    error_log /dev/null crit;
    client_body_temp_path /tmp/body;
    proxy_temp_path /tmp/proxy;
    fastcgi_temp_path /tmp/fastcgi;
    uwsgi_temp_path /tmp/uwsgi;
    scgi_temp_path /tmp/scgi;
    client_max_body_size 256m;
    client_body_timeout 35s;
    send_timeout 330s;
    server {{
        listen {c["bind_address"]}:{c["https_port"]} ssl;
        server_name _;
        ssl_certificate /run/secrets/tls.crt;
        ssl_certificate_key /run/secrets/tls.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        {auth}
        {key_setting}
        add_header Cache-Control "no-store" always;
        add_header X-Content-Type-Options nosniff always;
        proxy_http_version 1.1;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_connect_timeout 10s;
        proxy_read_timeout 330s;
        proxy_send_timeout 35s;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-API-Key $forte_service_key;
        {authorization}
        proxy_set_header X-Forte-Principal "";
        proxy_set_header X-Forte-Gateway-Token "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header Connection "";
        location /api/ {{ {api} }}
        location / {{ proxy_pass {upstream}; }}
    }}
}}
"""
    files.append(_write(target / "nginx.conf", nginx))
    services = {
        "ingress": {
            "image": c["proxy_image"],
            "network_mode": "host",
            "restart": "unless-stopped",
            "read_only": True,
            "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m"],
            "entrypoint": ["nginx"],
            "command": ["-g", "daemon off;", "-c", "/etc/nginx/nginx.conf"],
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "logging": {"driver": "none"},
            "volumes": [
                _volume(target / "nginx.conf", "/etc/nginx/nginx.conf"),
                _volume(c["tls_cert"], "/run/secrets/tls.crt"),
                _volume(c["tls_key"], "/run/secrets/tls.key"),
                *secret_paths,
            ],
        }
    }
    if c["mode"] == "private":
        mounts = [
            _volume(c["resources_root"], "/resources"),
            _volume(Path(c["secrets_root"]) / "core-api.key", "/run/secrets/core-api.key"),
            {
                "type": "bind",
                "source": c["data_root"],
                "target": "/data",
                "bind": {"create_host_path": False},
            },
        ]
        for mount in manifest.get("runtime", {}).get("mounts", []):
            source = (Path(c["resources_root"]) / mount["source"]).resolve()
            if not source.is_relative_to(Path(c["resources_root"]).resolve()):
                raise ValueError("resource mount escapes resources_root")
            mounts.append(_volume(source, mount["target"]))
        environment = manifest.get("runtime", {}).get("environment", {}) | {
            "FORTE_PRIVATE_ROOT": "/data",
            "FORTE_API_KEY_FILE": "/run/secrets/core-api.key",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
            "VLLM_NO_USAGE_STATS": "1",
        }
        services["core"] = {
            "image": c["core_image"],
            "network_mode": "none",
            "gpus": "all",
            "restart": "unless-stopped",
            "init": True,
            "ipc": manifest.get("runtime", {}).get("ipc", "host"),
            "security_opt": ["no-new-privileges:true"],
            "environment": environment,
            "volumes": mounts,
            "logging": {"driver": "none"},
        }
    compose = {"name": c["project_name"], "services": services}
    files.append(_write(target / "compose.json", json.dumps(compose, indent=2) + "\n"))
    files.append(_write(target / "installation.json", json.dumps(c, indent=2) + "\n"))
    return files


def compose_command(config: dict, target: Path, action: str) -> list[str]:
    c = _config(config)
    errors = validate(c)
    if action == "up":
        errors += prerequisites(c)
    if errors:
        raise ValueError("; ".join(dict.fromkeys(errors)))
    operations = {
        "up": ["up", "-d", "--pull", "never"],
        "stop": ["stop"],
        "status": ["ps", "--format", "json"],
        "logs": ["logs", "--tail", "50"],
    }
    if action not in operations:
        raise ValueError("unsupported deployment operation")
    return [
        "docker",
        "compose",
        "--project-name",
        c["project_name"],
        "--file",
        str(Path(target).absolute() / "compose.json"),
        *operations[action],
    ]


def _docker(args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30)


def _container(c, target):
    result = subprocess.run(
        compose_command(c, target, "status")[:-3] + ["ps", "-q", "core"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[0-9a-f]{12,64}", value):
        raise RuntimeError("Installer-owned core container is not available")
    inspected = _docker(["inspect", value])
    try:
        item = json.loads(inspected.stdout)[0]
        labels = item["Config"]["Labels"]
        if (
            labels["com.docker.compose.project"] != c["project_name"]
            or labels["com.docker.compose.service"] != "core"
            or item["HostConfig"]["NetworkMode"] != "none"
        ):
            raise ValueError
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError(
            "Core container ownership or offline network identity does not match"
        ) from None
    return value


def _bridge_start(c, target, container):
    target = Path(target).absolute()
    pidfile = target / "bridge.json"
    if pidfile.exists():
        # Never silently replace a daemon; its endpoint may still be in use.
        raise RuntimeError("Bridge state already exists; run status then stop this installation")
    import secrets

    token = secrets.token_hex(16)
    command = [
        sys.executable,
        str(Path(__file__).with_name("bridge.py")),
        "--container",
        container,
        "--port",
        str(c.get("bridge_port", 18001)),
        "--token",
        token,
        "--state",
        str(pidfile),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(30):
        if process.poll() is not None:
            raise RuntimeError(
                "Private loopback bridge failed to bind; no other process was changed"
            )
        if pidfile.exists():
            return
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("Private bridge did not report startup")


def _bridge_stop(c, target):
    path = Path(target).absolute() / "bridge.json"
    if not path.exists():
        return
    if sys.platform != "linux":
        raise RuntimeError("Bridge process identity verification requires the supported Linux host")
    try:
        state = json.loads(path.read_text())
        pid = int(state["pid"])
        # Linux process command line verifies token, script, state and container.
        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        expected = [
            str(Path(__file__).with_name("bridge.py")),
            "--token",
            state["token"],
            "--state",
            str(path),
            "--container",
            state["container"],
        ]
        if not all(value.encode() in command for value in expected):
            raise ValueError
        os.kill(pid, signal.SIGTERM)
    except FileNotFoundError:
        path.unlink(missing_ok=True)
        return
    except (ValueError, KeyError, OSError):
        raise RuntimeError(
            "Bridge process identity could not be verified; no signal sent"
        ) from None
    for _ in range(30):
        if not path.exists():
            return
        time.sleep(0.1)
    raise RuntimeError("Owned bridge has not finished stopping; no force kill issued")


def status(config: dict, target: Path) -> dict:
    c = _config(config)
    errors = validate(c)
    if errors:
        return {"ok": False, "errors": errors}
    upstream = (
        c.get("attach_upstream", "http://127.0.0.1:18000")
        if c["mode"] == "attach"
        else f"http://127.0.0.1:{c.get('bridge_port', 18001)}"
    )
    result = {
        "mode": c["mode"],
        "origin": c["origin"],
        "live": False,
        "ready": False,
        "core_ready": False,
        "access_ready": False,
        "externally_verified": False,
        "browser_access_verified": False,
        "case_content_read": False,
    }

    # Fixed health paths only; never follow a redirect to an external target.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for field, endpoint, expected in (
        ("live", "/health/live", "ok"),
        ("ready", "/health/ready", "ready"),
    ):
        try:
            with opener.open(upstream.rstrip("/") + endpoint, timeout=3) as response:
                raw = response.read(4097)
                payload = json.loads(raw)
                result[field] = (
                    response.status == 200
                    and len(raw) <= 4096
                    and isinstance(payload, dict)
                    and payload.get("status") == expected
                )
        except (OSError, ValueError, urllib.error.URLError):
            pass
    try:
        manifest, _ = _load_manifest(c)
        verification = manifest.get("verification", {})
        if not isinstance(verification, dict):
            raise ValueError
        result["browser_access_verified"] = (
            c["access_mode"] == "browser-session"
            and verification.get("browser_session") is True
            and verification.get("ownership") is True
        )
    except ValueError:
        pass
    result["core_ready"] = result["ready"]
    # Probe this installation's actual HTTPS listener on loopback. Use the
    # configured hostname for SNI and certificate matching; never resolve it to
    # an external service or use a reviewer/client loopback address in the UI.
    try:
        origin = urllib.parse.urlsplit(c["origin"])
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=c["tls_cert"])
        with socket.create_connection(("127.0.0.1", c["https_port"]), timeout=3) as plain:
            with context.wrap_socket(plain, server_hostname=origin.hostname) as secured:
                request = (
                    "GET /health/ready HTTP/1.1\r\nHost: "
                    + origin.netloc
                    + "\r\nConnection: close\r\n\r\n"
                )
                secured.sendall(request.encode("ascii"))
                response = http.client.HTTPResponse(secured)
                response.begin()
                if c["access_mode"] == "gateway-single-admin":
                    result["access_ready"] = response.status == 401 and response.getheader(
                        "WWW-Authenticate", ""
                    ).startswith("Basic ")
                else:
                    raw = response.read(4097)
                    payload = json.loads(raw)
                    result["access_ready"] = (
                        response.status == 200
                        and len(raw) <= 4096
                        and isinstance(payload, dict)
                        and payload.get("status") == "ready"
                    )
    except (OSError, ValueError, http.client.HTTPException, UnicodeError):
        pass
    result["ready"] = result["core_ready"] and result["access_ready"]
    result["ok"] = result["live"] and result["ready"]
    return result


def lifecycle(config: dict, target: Path, action: str) -> dict:
    """Run only this installation's services; return sanitized operational facts."""
    c, target = _config(config), Path(target).absolute()
    if action == "status":
        return status(c, target)
    if action == "logs":
        # Model/API logs may contain private prompts. Do not read them through a
        # diagnostics command. Ingress logging is disabled by construction.
        return {
            "ok": True,
            "logs": "Case-bearing service logs are not collected. Use health diagnostics.",
        }
    try:
        command = compose_command(c, target, action)
        if action == "up":
            host_errors = host_prerequisites(c)
            if host_errors:
                raise ValueError("; ".join(host_errors))
            render(c, target)
            # No implicit downloads and no rebuild of a changing application.
            for image in {c["proxy_image"], *([c["core_image"]] if c["mode"] == "private" else [])}:
                if _docker(["image", "inspect", image]).returncode:
                    raise ValueError(
                        "A pinned image is not prepared locally; "
                        "acquire it explicitly before startup"
                    )
            if c["mode"] == "private":
                # Create no duplicate model if the project is already running.
                running = subprocess.run(
                    compose_command(c, target, "status"), capture_output=True, text=True, timeout=30
                )
                if running.returncode == 0 and running.stdout.strip() not in {"", "[]"}:
                    raise ValueError(
                        "Installation already has services; "
                        "use status or stop before applying a release"
                    )
                core_command = command[:-4] + ["up", "-d", "--pull", "never", "core"]
                started = subprocess.run(core_command, capture_output=True, text=True, timeout=120)
                if started.returncode:
                    raise RuntimeError(
                        "Owned core startup failed; existing services were not changed"
                    )
                _bridge_start(c, target, _container(c, target))
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        elif action == "stop":
            try:
                compose = json.loads((target / "compose.json").read_text())
                expected = {"ingress", "core"} if c["mode"] == "private" else {"ingress"}
                if compose.get("name") != c["project_name"] or set(compose["services"]) != expected:
                    raise ValueError
            except (OSError, ValueError, KeyError, TypeError):
                raise RuntimeError(
                    "Rendered profile ownership does not match; no services stopped"
                ) from None
            if c["mode"] == "private":
                _bridge_stop(c, target)
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        else:
            raise ValueError("unsupported deployment operation")
        if result.returncode:
            raise RuntimeError("Compose operation failed; sensitive runtime output was withheld")
        if action == "up":
            report = status(c, target)
            report["started"] = True
            if not report["core_ready"]:
                report["message"] = (
                    "Services started; model warmup/readiness is still pending. Run status."
                )
            elif not report["access_ready"]:
                report["message"] = (
                    "Core is ready; HTTPS listener or supplied certificate/hostname check failed."
                )
            elif c["access_mode"] == "gateway-single-admin":
                report["message"] = (
                    "Administrator API gateway is ready; browser session integration is unverified."
                )
            return report
        return {"ok": True, "mode": c["mode"], "stopped": True, "data_preserved": True}
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        # Only our own fixed validation errors are returned; process output and
        # exception strings from external libraries never become support logs.
        message = (
            str(exc)
            if isinstance(exc, (ValueError, RuntimeError))
            else "Local runtime operation unavailable or timed out"
        )
        return {"ok": False, "errors": [message], "mode": c.get("mode")}
