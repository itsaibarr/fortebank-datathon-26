"""Actual core + session gateway over local TLS; generated media and fake inference.

These checks establish request isolation, not model, deployment or legal acceptance.
The TLS socket substitutes for the deployment lane's separately tested ingress.
"""

import hashlib
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from test_api_v2 import correction, negative, uncertain
from test_video import make_mov

from forte.api import create_app
from forte.settings import Settings

SESSION_SOURCE = Path(__file__).resolve().parents[1] / "tools/forte-session"
sys.path.insert(0, str(SESSION_SOURCE))
from session_gateway import create_server  # noqa: E402
from session_store import SessionStore  # noqa: E402


@contextmanager
def core_http(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            loop="asyncio",
            ws="none",
            log_level="critical",
            access_log=False,
            timeout_graceful_shutdown=1,
        )
    )
    worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            worker.join(0.01)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        worker.join(5)
        if worker.is_alive():
            server.force_exit = True
            worker.join(1)
        listener.close()
        assert not worker.is_alive()


@pytest.fixture
def tls_files(tmp_path):
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("OpenSSL required for actual loopback TLS integration")
    key, cert = tmp_path / "synthetic.key", tmp_path / "synthetic.crt"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    return cert, key


@contextmanager
def gateway_https(config, store, tls_files):
    # Reserve an ephemeral port to construct the exact configured HTTPS Origin.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    config = config | {"listen_port": port, "origin": f"https://127.0.0.1:{port}"}
    server = create_server(config, store=store)
    cert, key = tls_files
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield config["origin"], ssl.create_default_context(cafile=str(cert))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
        assert not worker.is_alive()


def login(client, username):
    response = client.post(
        "/auth/login",
        headers={"Origin": str(client.base_url).rstrip("/")},
        json={"username": username, "password": "synthetic-password-" + username},
    )
    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"]
    assert "__Host-forte_session=" in cookie
    assert all(
        flag in cookie.lower() for flag in ("secure", "httponly", "samesite=strict", "path=/")
    )
    assert "domain=" not in cookie.lower()
    session = client.get("/auth/session").json()
    assert session["authenticated"] is True
    return session


def mutation_headers(client, session):
    return {
        "Origin": str(client.base_url).rstrip("/"),
        "X-CSRF-Token": session["csrf_token"],
    }


@pytest.fixture
def stack(tmp_path, tls_files, monkeypatch, request):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    key, token = "synthetic-service-key-" + "k" * 32, "synthetic-gateway-token-" + "t" * 32
    for name, value in (("service.key", key), ("gateway.key", token)):
        path = secret_dir / name
        path.write_text(value + "\n")
        path.chmod(0o600)
    store = SessionStore(tmp_path / "sessions" / "users.sqlite3")
    a = store.add_user("alice", "synthetic-password-alice")
    b = store.add_user("bob", "synthetic-password-bob")
    assert a != b
    ready = {"value": True}
    settings = Settings(
        api_key=key,
        trusted_gateway_token=token,
        private_root=tmp_path / "cases",
    )
    app = create_app(
        settings,
        runner=negative,
        reasoning_runner=uncertain,
        ready=lambda: ready["value"],
    )
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with core_http(app) as upstream:
        config = {
            "upstream": upstream,
            "service_key_file": str(secret_dir / "service.key"),
            "gateway_token_file": str(secret_dir / "gateway.key"),
            "session_db": str(tmp_path / "sessions" / "users.sqlite3"),
            "browser_uploads_enabled": getattr(request, "param", True),
            "limits": {
                "upload_max_bytes": 268435456,
                "max_video_seconds": 180,
                "upload_timeout_seconds": 30,
                "job_timeout_seconds": 270,
            },
        }
        with gateway_https(config, store, tls_files) as (origin, trust):
            with (
                httpx.Client(base_url=origin, verify=trust, trust_env=False, timeout=15) as alice,
                httpx.Client(base_url=origin, verify=trust, trust_env=False, timeout=15) as bob,
            ):
                yield alice, bob, store, source, ready, settings


def upload(client, session, source, version=2):
    response = client.post(
        f"/api/v{version}/analyze",
        headers=mutation_headers(client, session),
        files={"file": ("synthetic.mov", source, "video/quicktime")},
    )
    assert response.status_code == 202, response.text
    path = f"/api/v{version}/jobs/" + response.json()["job_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(path)
        assert result.status_code == 200, result.text
        if result.json()["status"] != "processing":
            assert result.json()["status"] == "done", result.text
            return path, result.json()
        time.sleep(0.01)
    pytest.fail("Synthetic job did not complete")


@pytest.mark.parametrize("version", [1, 2])
def test_actual_https_principal_survives_gateway_core_and_media(stack, version):
    alice, bob, _, source, _, settings = stack
    session_a, session_b = login(alice, "alice"), login(bob, "bob")
    path, completed = upload(alice, session_a, source, version)
    denied = bob.get(path)
    assert denied.status_code == 404
    missing = bob.get(f"/api/v{version}/jobs/00000000-0000-0000-0000-000000000000")
    assert denied.content == missing.content
    # Client identity headers cannot override the session on the private app hop.
    forged = bob.get(
        path,
        headers={
            "X-Forte-Principal": session_a["principal"]["id"],
            "X-Forte-Gateway-Token": settings.trusted_gateway_token,
            "X-API-Key": settings.api_key,
        },
    )
    assert forged.status_code == 404
    assert alice.get("/api/internal/security").status_code in {403, 404}
    if version == 1:
        return
    result = completed["result"]
    evidence = result["events"][0]["evidence"][0]
    for resource in ("/source", "/evidence/" + evidence["frame_id"], "/corrections"):
        assert bob.get(path + resource).status_code == 404
        assert bob.get(path + resource, headers={"Range": "bytes=0-31"}).status_code == 404
    full = alice.get(path + "/source")
    assert full.content == source
    ranged = alice.get(path + "/source", headers={"Range": "bytes=7-36"})
    assert ranged.status_code == 206 and ranged.content == source[7:37]
    frame = alice.get(path + "/evidence/" + evidence["frame_id"])
    assert hashlib.sha256(frame.content).hexdigest() == evidence["image_sha256"]
    payload = correction(result, reviewer="client-forged-reviewer")
    assert (
        bob.post(
            path + "/corrections", headers=mutation_headers(bob, session_b), json=payload
        ).status_code
        == 404
    )
    saved = alice.post(
        path + "/corrections", headers=mutation_headers(alice, session_a), json=payload
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["correction"]["reviewer"] == session_a["principal"]["id"]


def test_https_csrf_revocation_and_readiness_are_independent(stack):
    alice, _, store, source, ready, _ = stack
    assert alice.get("/auth/session").json() == {"authenticated": False}
    assert (
        alice.post(
            "/auth/login", json={"username": "alice", "password": "synthetic-password-alice"}
        ).status_code
        == 403
    )
    session = login(alice, "alice")
    metadata = alice.get("/deployment.json")
    assert metadata.status_code == 200 and "no-store" in metadata.headers["cache-control"]
    assert metadata.json()["destination"] == str(alice.base_url).rstrip("/")
    assert metadata.json()["browser_uploads_enabled"] is True
    for headers in ({}, {"Origin": "https://wrong.example", "X-CSRF-Token": session["csrf_token"]}):
        assert (
            alice.post(
                "/api/v2/analyze", headers=headers, files={"file": ("synthetic.mov", source)}
            ).status_code
            == 403
        )
    path, _ = upload(alice, session, source)
    ready["value"] = False
    assert alice.get("/deployment.json").json()["browser_uploads_enabled"] is False
    assert alice.get("/health/ready").status_code == 503
    assert alice.get(path).status_code == 200  # Existing review survives readiness loss.
    store.disable_user("alice")
    assert alice.get(path).status_code == 401
    assert alice.get("/auth/session").json() == {"authenticated": False}


@pytest.mark.parametrize("stack", [False], indirect=True)
def test_encoded_upload_cannot_bypass_operator_gate_or_expose_internal_routes(stack):
    alice, _, _, source, _, settings = stack
    session = login(alice, "alice")
    assert alice.get("/deployment.json").json()["browser_uploads_enabled"] is False
    for path in ("/api/v2/analyze", "/api/v2/%61nalyze", "/%61pi/v2/analyze"):
        response = alice.post(
            path,
            headers=mutation_headers(alice, session),
            files={"file": ("synthetic.mov", source)},
        )
        assert response.status_code in {400, 403, 404}
    for path in ("/api/internal/security", "/%61pi/internal/security", "/api/%69nternal/security"):
        assert alice.get(path).status_code in {400, 403, 404}
    assert list(settings.private_root.glob("*/input.mov")) == []


def test_legacy_core_cannot_be_promoted_by_session_gateway(tmp_path, tls_files):
    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)
    for name in ("service", "gateway"):
        path = secrets / name
        path.write_text("synthetic-" + name + "-" + "x" * 40)
        path.chmod(0o600)
    store = SessionStore(tmp_path / "sessions" / "users.sqlite3")
    store.add_user("alice", "synthetic-password-alice")
    settings = Settings(api_key=(secrets / "service").read_text(), private_root=tmp_path / "cases")
    with core_http(create_app(settings, runner=negative, ready=lambda: True)) as upstream:
        config = {
            "upstream": upstream,
            "service_key_file": str(secrets / "service"),
            "gateway_token_file": str(secrets / "gateway"),
            "session_db": str(tmp_path / "sessions" / "users.sqlite3"),
            "browser_uploads_enabled": True,
        }
        with gateway_https(config, store, tls_files) as (origin, trust):
            with httpx.Client(base_url=origin, verify=trust, trust_env=False) as client:
                session = login(client, "alice")
                assert client.get("/deployment.json").json()["browser_uploads_enabled"] is False
                assert client.get("/health/ready").status_code == 503
                response = client.post(
                    "/api/v1/analyze",
                    headers=mutation_headers(client, session),
                    files={"file": ("synthetic.mov", make_mov(tmp_path / "fake.mov").read_bytes())},
                )
                assert response.status_code in {502, 503}
                assert list(settings.private_root.glob("*/input.mov")) == []
