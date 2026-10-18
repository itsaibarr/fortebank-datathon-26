"""Synthetic packaging/streaming checks; no model, VM, case media or paid work."""

import hashlib
import http.server
import importlib.util
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / "portable" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runtime = module("runtime")
bridge = module("bridge")
acceptance = module("acceptance_receipt")
CORE = "example.invalid/core@sha256:" + "1" * 64
PROXY = "example.invalid/nginx@sha256:" + "2" * 64


def bind_synthetic_acceptance(manifest, resources):
    # Consistent test evidence only; these fixtures never attest a real run.
    manifest["corpus"]["manifest_sha256"] = "5" * 64
    manifest["deployment"] = {
        "schema_version": "forte.deployment-identity/1",
        "proxy_image": PROXY,
        "files": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sorted(acceptance.REQUIRED_FILES)
        },
    }
    checks = {}
    (resources / "verification").mkdir(exist_ok=True)
    for flag in acceptance.FLAGS:
        if manifest["verification"][flag] is not True:
            checks[flag] = {"status": "not_run", "evidence_level": None, "evidence": []}
            continue
        relative = f"verification/{flag}.json"
        raw = json.dumps({"synthetic_fixture_only": True, "check": flag}).encode()
        (resources / relative).write_bytes(raw)
        checks[flag] = {
            "status": "passed",
            "evidence_level": acceptance.LEVELS[flag],
            "evidence": [
                {
                    "path": relative,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
            ],
        }
    raw = json.dumps(
        {
            "schema_version": "forte.deployment-acceptance/1",
            "subject_sha256": acceptance.subject_sha256(manifest),
            "completed_at": "2026-10-18T02:00:00Z",
            "checks": checks,
        }
    ).encode()
    relative = "verification/acceptance.json"
    (resources / relative).write_bytes(raw)
    manifest["verification"].update(
        receipt=relative, receipt_sha256=hashlib.sha256(raw).hexdigest()
    )


@pytest.fixture
def installation(tmp_path):
    tmp_path = tmp_path.resolve()
    resources, secrets, data = [tmp_path / name for name in ("resources", "secrets", "cases")]
    for path in (resources, secrets, data):
        path.mkdir()
    asset = resources / "synthetic-asset.txt"
    asset.write_text("Synthetic resource, never production model weights")
    (resources / "receipt.json").write_text('{"synthetic":true}')
    (secrets / "core-api.key").write_text("a" * 48)
    token = secrets / "gateway-token"
    token.write_text("b" * 48)
    token.chmod(0o600)
    (secrets / "admin.htpasswd").write_text("admin:synthetic-test-only")
    cert, key = secrets / "cert.pem", secrets / "tls.key"
    # A local synthetic matching cert/key, not a trusted production certificate.
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    manifest = {
        "schema_version": 1,
        "core": {"commit": "3" * 40, "image": CORE, "contract_sha256": "4" * 64},
        "model": {
            "identity": "synthetic-no-model",
            "revision": "synthetic",
            "profile": "test-only",
            "frozen": True,
        },
        "corpus": {"version": "synthetic"},
        "runtime": {
            "ipc": "host",
            "environment": {"FORTE_MODEL_PATH": "/models/snapshot"},
            "mounts": [{"source": "models", "target": "/models"}],
        },
        "assets": [{"path": asset.name, "sha256": hashlib.sha256(asset.read_bytes()).hexdigest()}],
        "verification": {
            "release": True,
            "model_workload": True,
            "offline_analysis": True,
            "browser_session": True,
            "ownership": True,
            "receipt": "receipt.json",
        },
    }
    manifest_path = tmp_path / "integration.json"
    bind_synthetic_acceptance(manifest, resources)
    manifest_path.write_text(json.dumps(manifest))
    config = {
        "schema_version": 1,
        "mode": "private",
        "project_name": "forte-synthetic",
        "origin": "https://localhost:8443",
        "https_port": 8443,
        "core_image": CORE,
        "proxy_image": PROXY,
        "integration_manifest": str(manifest_path),
        "resources_root": str(resources),
        "data_root": str(data),
        "secrets_root": str(secrets),
        "tls_cert": str(cert),
        "tls_key": str(key),
        "multi_user_uploads": False,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    return config, manifest, tmp_path / "installer"


def save_manifest(config, manifest):
    path = Path(config["integration_manifest"])
    path.write_text(json.dumps(manifest))
    config["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_render_private_is_offline_profile_and_never_changes_inputs(installation):
    config, _, target = installation
    watched = [Path(config[k]) for k in ("integration_manifest", "tls_cert", "tls_key")]
    key = Path(config["secrets_root"]) / "core-api.key"
    before = {p: p.read_bytes() for p in [*watched, key]}
    runtime.render(config, target)
    compose = json.loads((target / "compose.json").read_text())
    assert compose["services"]["core"]["network_mode"] == "none"
    assert compose["services"]["core"]["image"] == CORE
    assert "ports" not in compose["services"]["core"]
    assert "command" not in compose["services"]["core"]  # Canonical image starts its own serving.
    assert compose["services"]["ingress"]["network_mode"] == "host"
    assert all(p.read_bytes() == before[p] for p in before)
    assert all(p.parent == target for p in target.iterdir())
    assert key.read_text() not in (target / "nginx.conf").read_text()
    assert key.read_text() not in (target / "compose.json").read_text()
    assert "proxy_request_buffering off" in (target / "nginx.conf").read_text()
    assert "proxy_buffering off" in (target / "nginx.conf").read_text()


def test_attach_contains_only_ingress_and_preserves_running_core(installation):
    config, _, target = installation
    config.update(mode="attach", attach_upstream="http://127.0.0.1:18000")
    runtime.render(config, target)
    compose = json.loads((target / "compose.json").read_text())
    assert set(compose["services"]) == {"ingress"}
    assert "18002" in (target / "nginx.conf").read_text()
    assert (
        json.loads((target / "session-config.json").read_text())["upstream"]
        == "http://127.0.0.1:18000"
    )
    command = runtime.compose_command(config, target, "stop")
    assert command[-1] == "stop"
    assert "down" not in command and "-v" not in command


def test_repeated_render_preserves_external_case_and_secret_files(installation):
    config, _, target = installation
    case = Path(config["data_root"]) / "immutable-correction.json"
    case.write_text("synthetic correction")
    runtime.render(config, target)
    first = (target / "compose.json").read_bytes()
    runtime.render(config, target)
    assert (target / "compose.json").read_bytes() == first
    assert case.read_text() == "synthetic correction"
    assert (Path(config["secrets_root"]) / "core-api.key").read_text() == "a" * 48


def test_unverified_browser_auth_fails_closed(installation):
    config, manifest, target = installation
    manifest["verification"]["browser_session"] = False
    manifest["verification"]["ownership"] = False
    save_manifest(config, manifest)
    runtime.render(config, target)
    assert "location /api/ { return 503; }" in (target / "nginx.conf").read_text()
    errors = runtime.prerequisites(config)
    assert any("browser session" in item for item in errors)
    assert any("ownership" in item for item in errors)
    with pytest.raises(ValueError, match="browser session"):
        runtime.compose_command(config, target, "up")


def test_single_admin_key_remains_server_side_and_multiuser_disabled(installation):
    config, manifest, target = installation
    manifest["verification"]["browser_session"] = False
    manifest["verification"]["ownership"] = False
    bind_synthetic_acceptance(manifest, Path(config["resources_root"]))
    save_manifest(config, manifest)
    config.update(
        access_mode="gateway-single-admin",
        htpasswd_file=str(Path(config["secrets_root"]) / "admin.htpasswd"),
    )
    assert runtime.prerequisites(config) == []
    runtime.render(config, target)
    nginx = (target / "nginx.conf").read_text()
    assert "auth_basic_user_file" in nginx
    assert 'proxy_set_header Authorization "";' in nginx
    assert "proxy_set_header X-API-Key $forte_service_key;" in nginx
    assert "a" * 48 not in nginx
    assert "a" * 48 in (target / "upstream-auth.conf").read_text()
    assert (target / "upstream-auth.conf").stat().st_mode & 0o777 == 0o600
    config["multi_user_uploads"] = True
    assert any("cannot enable" in item for item in runtime.validate(config))


def test_resource_mutation_and_manifest_pin_changes_block_start(installation):
    config, _, target = installation
    assert runtime.prerequisites(config) == []
    (Path(config["resources_root"]) / "synthetic-asset.txt").write_text("changed")
    assert any("SHA256" in item for item in runtime.prerequisites(config))
    config["manifest_sha256"] = "f" * 64
    assert any("no longer matches" in item for item in runtime.prerequisites(config))


def test_arbitrary_receipt_cannot_authorize_startup(installation, monkeypatch):
    config, manifest, target = installation
    config["gpu_uuid"] = "GPU-synthetic-only"
    (Path(config["resources_root"]) / manifest["verification"]["receipt"]).write_text(
        '{"synthetic":true}'
    )
    operations = []
    monkeypatch.setattr(runtime, "_docker", lambda args: operations.append(args))
    assert runtime.prerequisites(config)
    report = runtime.lifecycle(config, target, "up")
    assert report["ok"] is False
    assert report["errors"]
    assert operations == []
    assert not target.exists()


@pytest.mark.parametrize("changed", ["model", "evidence", "helper", "ingress"])
def test_startup_rechecks_exact_acceptance_identity(installation, monkeypatch, changed):
    config, manifest, target = installation
    config["gpu_uuid"] = "GPU-synthetic-only"
    assert runtime.prerequisites(config) == []
    if changed == "model":
        manifest["model"]["revision"] = "changed-synthetic-revision"
        save_manifest(config, manifest)
    elif changed == "evidence":
        (Path(config["resources_root"]) / "verification/ownership.json").write_text("changed")
    elif changed == "helper":
        name = "deploy/portable/runtime.py"
        manifest["deployment"]["files"][name] = "9" * 64
        save_manifest(config, manifest)
    else:
        config["proxy_image"] = "example.invalid/different@sha256:" + "9" * 64
    operations = []
    monkeypatch.setattr(runtime, "_docker", lambda args: operations.append(args))
    report = runtime.lifecycle(config, target, "up")
    assert report["ok"] is False and report["errors"]
    assert operations == []
    assert not target.exists()


def test_missing_acceptance_component_blocks_startup(installation, monkeypatch, tmp_path):
    config, _, _ = installation
    monkeypatch.setattr(runtime, "__file__", str(tmp_path / "missing/runtime.py"))
    assert "Acceptance verification component is unavailable" in runtime.prerequisites(config)


def test_preview_does_not_claim_an_unreleased_candidate(installation):
    config, manifest, target = installation
    manifest["core"] = {"commit": None, "image": None, "contract_sha256": None}
    manifest["verification"] = {
        "release": False,
        "model_workload": False,
        "offline_analysis": False,
    }
    save_manifest(config, manifest)
    runtime.render(config, target)
    assert target.joinpath("compose.json").is_file()
    assert any("stable core" in item for item in runtime.prerequisites(config))
    with pytest.raises(ValueError):
        runtime.compose_command(config, target, "up")


@pytest.mark.parametrize(
    "change",
    [
        {"origin": "https://user:password@localhost:8443"},
        {"proxy_image": "nginx:latest"},
        {"mode": "attach", "attach_upstream": "https://external.invalid:443"},
        {"mode": "attach", "attach_upstream": "http://localhost:18000"},
        {"bind_address": "192.0.2.1"},
        {"https_port": 443},
        {"origin": "https://localhost:8443/case"},
        {"origin": "https://localhost:8443/"},
    ],
)
def test_unsafe_configuration_rejected_before_render(installation, change):
    config, _, target = installation
    config.update(change)
    assert runtime.validate(config)
    with pytest.raises(ValueError):
        runtime.render(config, target)
    assert not target.exists()


def test_noncanonical_direct_origin_blocks_before_any_runtime_operation(installation, monkeypatch):
    config, _, target = installation
    config["origin"] += "/"

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid origin must be rejected before any Docker or service operation")

    monkeypatch.setattr(runtime, "_docker", forbidden)
    monkeypatch.setattr(runtime.subprocess, "run", forbidden)
    result = runtime.lifecycle(config, target, "up")
    assert result["ok"] is False
    assert any("origin" in error for error in result["errors"])
    assert not target.exists()


def test_resource_mount_escape_or_remote_model_rejected(installation):
    config, manifest, target = installation
    manifest["runtime"]["mounts"] = [{"source": "../../private", "target": "/models"}]
    manifest["runtime"]["environment"]["FORTE_MODEL_URL"] = "https://outside.invalid"
    save_manifest(config, manifest)
    with pytest.raises(ValueError):
        runtime.render(config, target)
    assert any("loopback" in item for item in runtime.prerequisites(config))


def test_output_symlink_cannot_modify_outside_directory(installation, tmp_path):
    config, _, target = installation
    target.mkdir()
    outside = tmp_path / "external"
    outside.write_text("preserve")
    (target / "nginx.conf").symlink_to(outside)
    runtime.render(config, target)
    assert outside.read_text() == "preserve"
    assert not (target / "nginx.conf").is_symlink()


def test_bridge_streams_large_binary_request_and_partial_content_response():
    # Synthetic stdin/stdout peer emulates HTTP 206 without Docker or model work.
    body = bytes(range(256)) * 131072  # 32 MiB; much larger than the relay buffer.
    received = {}
    peer = r"""
import hashlib, os
length = int(os.environ['SYNTHETIC_LENGTH'])
h = hashlib.sha256()
while length:
    data = os.read(0, min(length, 65536))
    if not data: raise SystemExit(2)
    h.update(data); length -= len(data)
result = h.hexdigest().encode()
headers = b'HTTP/1.1 206 Partial Content\r\nContent-Length: 64\r\n'
headers += b'Content-Range: bytes 0-63/64\r\n\r\n'
os.write(1, headers + result)
"""
    client, server = socket.socketpair()

    def spawn(*args, **kwargs):
        return subprocess.Popen(
            *args, **kwargs, env=os.environ | {"SYNTHETIC_LENGTH": str(len(body))}
        )

    task = threading.Thread(
        target=bridge.relay_connection,
        args=(server, [sys.executable, "-u", "-c", peer]),
        kwargs={"spawn": spawn},
    )
    task.start()

    def upload():
        client.sendall(body)
        client.shutdown(socket.SHUT_WR)

    writer = threading.Thread(target=upload)
    writer.start()
    chunks = []
    while chunk := client.recv(65536):
        chunks.append(chunk)
    received["response"] = b"".join(chunks)
    client.close()
    writer.join(timeout=5)
    task.join(timeout=5)
    assert not task.is_alive() and not writer.is_alive()
    assert received["response"].startswith(b"HTTP/1.1 206 Partial Content")
    assert received["response"].endswith(hashlib.sha256(body).hexdigest().encode())


def test_stop_refuses_reused_pid_identity(installation, monkeypatch):
    config, _, target = installation
    target.mkdir()
    (target / "bridge.json").write_text(
        json.dumps({"pid": os.getpid(), "token": "foreign", "container": "a" * 64})
    )

    def forbidden(*args):
        raise AssertionError("Must not signal a foreign process")

    original_read = Path.read_bytes

    def fake_proc(path):
        return b"unrelated-command\0" if str(path).startswith("/proc/") else original_read(path)

    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(Path, "read_bytes", fake_proc)
    monkeypatch.setattr(runtime.os, "kill", forbidden)
    with pytest.raises(RuntimeError, match="identity"):
        runtime._bridge_stop(config, target)


def test_logs_do_not_read_case_content_or_raw_model_logs(installation):
    config, _, target = installation
    report = runtime.lifecycle(config, target, "logs")
    assert report["ok"] and "not collected" in report["logs"]


def test_status_distinguishes_healthy_core_from_failed_https_ingress(installation):
    config, _, target = installation

    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            value = "ready" if self.path == "/health/ready" else "ok"
            self.wfile.write(json.dumps({"status": value}).encode())

        def log_message(self, *args):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Health) as server:
        config.update(mode="attach", attach_upstream=f"http://127.0.0.1:{server.server_port}")
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            config["https_port"] = unused.getsockname()[1]
        config["origin"] = f"https://localhost:{config['https_port']}"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            report = runtime.status(config, target)
            assert report["live"] and report["core_ready"]
            assert not report["access_ready"] and not report["ready"] and not report["ok"]
            assert report["externally_verified"] is False
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_status_checks_real_tls_hostname_and_single_admin_challenge(installation):
    config, _, target = installation

    class Challenge(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Forte administrator"')
            self.end_headers()

        def log_message(self, *args):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Challenge) as server:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(config["tls_cert"], config["tls_key"])
        server.socket = context.wrap_socket(server.socket, server_side=True)
        config.update(
            mode="attach",
            access_mode="gateway-single-admin",
            htpasswd_file=str(Path(config["secrets_root"]) / "admin.htpasswd"),
            https_port=server.server_port,
            origin=f"https://localhost:{server.server_port}",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            report = runtime.status(config, target)
            assert report["access_ready"] and not report["core_ready"] and not report["ok"]
            config["origin"] = f"https://wrong-host.invalid:{server.server_port}"
            assert runtime.status(config, target)["access_ready"] is False
        finally:
            server.shutdown()
            thread.join(timeout=3)


@pytest.mark.skipif(
    os.environ.get("FORTE_TEST_DOCKER_PROXY") != "1",
    reason="Explicit opt-in for cached local Docker proxy; never a model or VM test",
)
def test_cached_nginx_starts_with_readonly_root_and_no_capabilities(installation):
    config, _, target = installation
    # Digest from the local pre-existing cache; never pulls a tag during a test.
    config["proxy_image"] = (
        "nginx@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de"
    )
    config.update(
        access_mode="gateway-single-admin",
        htpasswd_file=str(Path(config["secrets_root"]) / "admin.htpasswd"),
    )
    runtime.render(config, target)
    ingress = json.loads((target / "compose.json").read_text())["services"]["ingress"]
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
    ]
    for volume in ingress["volumes"]:
        command += ["--mount", f"type=bind,src={volume['source']},dst={volume['target']},readonly"]
    command += ["--entrypoint", "nginx", ingress["image"]]
    checked = subprocess.run(
        command + ["-t", "-c", "/etc/nginx/nginx.conf"], capture_output=True, text=True, timeout=30
    )
    assert checked.returncode == 0, "Synthetic nginx config validation failed"
    started = subprocess.run(
        command[:-3] + ["-d", *command[-3:], "-g", "daemon off;", "-c", "/etc/nginx/nginx.conf"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert started.returncode == 0, "Synthetic nginx start failed"
    container = started.stdout.strip()
    try:
        time.sleep(0.25)
        state = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.Running}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert state.returncode == 0 and state.stdout.strip() == "true"
        probe = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "wget",
                "--no-check-certificate",
                "-S",
                "-O",
                "/dev/null",
                "https://127.0.0.1:8443/health/live",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "401 Unauthorized" in probe.stderr
    finally:
        subprocess.run(
            ["docker", "stop", "--time", "3", container], capture_output=True, timeout=15
        )


def test_attach_never_targets_model_port(installation):
    config, _, _ = installation
    config.update(mode="attach", attach_upstream="http://127.0.0.1:8001")
    assert runtime.validate(config)
