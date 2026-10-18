"""Synthetic loopback transport/security checks, never model or jury-quality acceptance."""

import asyncio
import hashlib
import http.client
import importlib.util
import json
import os
import socket
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from test_api import negative  # noqa: E402
from test_browser_session_integration import core_http  # noqa: E402
from test_video import make_mov  # noqa: E402

from forte.api import create_app  # noqa: E402
from forte.contracts import DoneJob  # noqa: E402
from forte.jobs import atomic_json  # noqa: E402
from forte.settings import Settings  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "jury_gateway", ROOT / "deploy/portable/jury_gateway.py"
)
jury = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jury)
from session_gateway import SECURITY  # noqa: E402
from session_gateway import create_server as browser_server  # noqa: E402
from session_store import SessionStore  # noqa: E402

SERVICE, TOKEN = "synthetic-service-" + "s" * 48, "synthetic-gateway-" + "t" * 48
A, B = "a" * 43, "b" * 43
PA, PB = "jury_" + "1" * 32, "jury_" + "2" * 32
ORIGIN, HOST = "https://jury.invalid", "jury.invalid"
JOB = "/api/v1/jobs/00000000-0000-0000-0000-000000000000"


def write_private(path, value):
    path.write_text(value)
    path.chmod(0o600)
    return str(path)


def entry(key=A, principal=PA, enabled=True):
    return {
        "key_sha256": hashlib.sha256(key.encode()).hexdigest(),
        "principal": principal,
        "enabled": enabled,
    }


def write_keys(config, entries=None):
    write_private(
        Path(config["jury_keys_file"]),
        json.dumps({"schema_version": jury.SCHEMA, "keys": entries or [entry(), entry(B, PB)]}),
    )


@pytest.fixture
def config(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    value = {
        "origin": ORIGIN,
        "upstream": "http://127.0.0.1:18000",
        "listen_port": 0,
        "service_key_file": write_private(private / "service.key", SERVICE),
        "gateway_token_file": write_private(private / "gateway.key", TOKEN),
        "jury_keys_file": str(private / "jury-keys.json"),
        "jury_uploads_enabled": True,
    }
    write_keys(value)
    return value


@contextmanager
def running(server):
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)
        assert not worker.is_alive()


def call(server, method="GET", path=JOB, *, key=A, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    selected = {"Host": HOST, **({"X-API-Key": key} if key is not None else {}), **(headers or {})}
    connection.request(method, path, body=body, headers=selected)
    response = connection.getresponse()
    result = SimpleNamespace(
        status=response.status, headers=dict(response.headers), body=response.read()
    )
    connection.close()
    return result


@pytest.fixture
def boundary(config):
    state = SimpleNamespace(mode="normal", ready=True, calls=[])

    class Core(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def respond(self, status, value, marker=True, close=False):
            raw = json.dumps(value).encode()
            trickle = state.mode == "response_trickle" and self.path == JOB
            if trickle:
                raw = b"x" * 32
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Content-Type", "application/json")
            if status == 202:
                location = "/api/v1/jobs/" + value["job_id"]
                if state.mode == "external_location":
                    location = "https://untrusted.invalid" + location
                elif state.mode == "encoded_location":
                    location = location.replace("jobs", "%6aobs")
                elif state.mode == "query_location":
                    location += "?secret=untrusted"
                elif state.mode == "fragment_location":
                    location += "#untrusted"
                elif state.mode == "mismatch_location":
                    location = JOB
                if state.mode != "missing_location":
                    self.send_header("Location", location)
                if state.mode == "duplicate_location":
                    self.send_header("Location", location)
            if status in {429, 503}:
                self.send_header("Retry-After", "300" if state.mode == "invalid_retry" else "5")
                if state.mode == "duplicate_retry":
                    self.send_header("Retry-After", "5")
            if state.mode == "misplaced_retry" and self.path != "/api/internal/security":
                self.send_header("Retry-After", "5")
            if marker:
                self.send_header("X-Forte-Ownership-Mode", "principal-v1")
            if close:
                self.send_header("Connection", "close")
                self.close_connection = True
            if state.mode == "forged_response":
                for key, value in {
                    "X-API-Key": SERVICE,
                    "X-Forte-Gateway-Token": TOKEN,
                    "X-Forte-Principal": PA,
                    "Set-Cookie": "untrusted=value",
                }.items():
                    self.send_header(key, value)
            self.end_headers()
            if trickle:
                for byte in raw:
                    self.wfile.write(bytes([byte]))
                    time.sleep(0.2)
            else:
                self.wfile.write(raw)

        def record(self, body=b""):
            state.calls.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "socket": self.connection,
                    "headers": dict(self.headers),
                    "body": body,
                }
            )

        def do_GET(self):
            self.record()
            if self.path == "/api/internal/security":
                if state.mode == "legacy":
                    return self.respond(404, {}, marker=False)
                value = dict(SECURITY)
                if state.mode == "wrong_security":
                    value["ownerless_jobs_denied"] = False
                return self.respond(200, value, close=state.mode == "closed")
            if self.path == "/health/ready":
                return self.respond(
                    200 if state.ready else 503, {"status": "ready" if state.ready else "not_ready"}
                )
            return self.respond(
                307 if state.mode == "redirect" else 200,
                {"status": "processing"},
                marker=state.mode != "missing_marker",
            )

        def do_POST(self):
            self.record(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            status = (
                429 if state.mode in {"invalid_retry", "duplicate_retry", "valid_retry"} else 202
            )
            self.respond(status, {"job_id": str(uuid4())})

    class QuietServer(ThreadingHTTPServer):
        daemon_threads = True
        block_on_close = False

        def handle_error(self, *args):
            pass

    with running(QuietServer(("127.0.0.1", 0), Core)) as upstream:
        config["upstream"] = f"http://127.0.0.1:{upstream.server_port}"
        with running(jury.create_server(config)) as server:
            yield SimpleNamespace(server=server, state=state, config=config)


def test_existing_browser_gateway_rejects_key_only_v1(config):
    store = SessionStore(Path(config["jury_keys_file"]).parent / "sessions.sqlite3")
    selected = {key: value for key, value in config.items() if not key.startswith("jury_")}
    with running(browser_server(selected, store=store)) as browser:
        for key in [SERVICE, A]:
            assert call(browser, key=key).status == 401
            assert (
                call(browser, "POST", "/api/v1/analyze", key=key, body=b"synthetic").status == 401
            )


def test_stable_key_identity_and_same_socket_ignores_forged_core_headers(boundary, capsys):
    result = call(
        boundary.server,
        "POST",
        "/api/v1/analyze",
        body=b"synthetic",
        headers={
            "X-Forte-Principal": PB,
            "X-Forte-Gateway-Token": "forged",
            "Authorization": "forged",
        },
    )
    assert result.status == 202
    security, ready, submitted = boundary.state.calls
    assert security["socket"] is ready["socket"] is submitted["socket"]
    assert [item["path"] for item in boundary.state.calls] == [
        "/api/internal/security",
        "/health/ready",
        "/api/v1/analyze",
    ]
    for item in [security, submitted]:
        assert item["headers"]["X-Forte-Principal"] == PA
        assert item["headers"]["X-API-Key"] == SERVICE
        assert item["headers"]["X-Forte-Gateway-Token"] == TOKEN
        assert "Authorization" not in item["headers"]
    assert call(boundary.server).status == 200
    assert boundary.state.calls[-1]["headers"]["X-Forte-Principal"] == PA
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("credential", [None, "invalid", SERVICE, TOKEN, "c" * 43])
def test_missing_invalid_service_or_gateway_credentials_have_no_upstream_effect(
    boundary, credential
):
    assert call(boundary.server, key=credential).status == 401
    assert call(boundary.server, "POST", "/api/v1/analyze", key=credential, body=b"x").status == 401
    assert not boundary.state.calls


def test_cookie_csrf_origin_and_range_are_not_alternate_or_mixed_identity(boundary):
    for name in ["Cookie", "X-CSRF-Token", "Origin", "Range", "If-Range"]:
        assert call(boundary.server, headers={name: "synthetic"}).status == 400
    assert not boundary.state.calls


def test_reload_revocation_and_principal_binding_are_fail_closed(boundary):
    assert call(boundary.server).status == 200
    write_keys(boundary.config, [entry(enabled=False), entry(B, PB)])
    assert call(boundary.server).status == 401
    assert call(boundary.server, key=B).status == 200
    write_keys(boundary.config, [entry(principal="jury_" + "3" * 32)])
    previous = len(boundary.state.calls)
    assert call(boundary.server).status == 503
    assert len(boundary.state.calls) == previous
    Path(boundary.config["jury_keys_file"]).write_text("broken")
    assert call(boundary.server, key=B).status == 503


@pytest.mark.parametrize("mode", ["legacy", "wrong_security", "closed"])
def test_capability_failure_never_posts_or_retries(boundary, mode):
    boundary.state.mode = mode
    assert call(boundary.server, "POST", "/api/v1/analyze", body=b"x").status == 502
    assert [item["path"] for item in boundary.state.calls] == ["/api/internal/security"]


def test_loading_model_never_posts(boundary):
    boundary.state.ready = False
    assert call(boundary.server, "POST", "/api/v1/analyze", body=b"x").status == 502
    assert not any(item["method"] == "POST" for item in boundary.state.calls)


@pytest.mark.parametrize("mode", ["missing_marker", "redirect"])
def test_response_requires_owner_marker_and_never_follows_redirect(boundary, mode):
    boundary.state.mode = mode
    assert call(boundary.server).status == 502
    assert len(boundary.state.calls) == 2


def test_sensitive_upstream_response_headers_never_reach_client(boundary):
    boundary.state.mode = "forged_response"
    response = call(boundary.server)
    assert response.status == 200
    assert not {"x-api-key", "x-forte-gateway-token", "x-forte-principal", "set-cookie"} & {
        key.lower() for key in response.headers
    }
    assert SERVICE.encode() not in response.body and TOKEN.encode() not in response.body


@pytest.mark.parametrize(
    "path",
    [
        "/api/v2/analyze",
        "/api/v1/analyze/",
        "/api/v1/jobs/not-uuid",
        JOB + "/source",
        JOB + "/report",
        JOB + "/evidence/frame",
        "/api/internal/security",
        "/openapi.json",
        "/health/ready",
        "/auth/login",
        "http://untrusted.invalid/api/v1/analyze",
        "/api/v1/jobs/00000000-0000-0000-0000-00000000000A",
    ],
)
def test_unknown_routes_never_reach_upstream(boundary, path):
    assert call(boundary.server, path=path).status in {400, 404}
    assert not boundary.state.calls


@pytest.mark.parametrize(
    "path",
    [JOB + "?x=y", JOB + "?", "/api/v1/../v1/analyze", "/api/v1/%61nalyze", "//api/v1/analyze"],
)
def test_noncanonical_paths_never_reach_upstream(boundary, path):
    assert call(boundary.server, path=path).status == 400
    assert not boundary.state.calls


@pytest.mark.parametrize(
    "method,path",
    [("HEAD", JOB), ("POST", JOB), ("GET", "/api/v1/analyze"), ("OPTIONS", JOB), ("DELETE", JOB)],
)
def test_methods_are_exact(boundary, method, path):
    assert call(boundary.server, method, path).status == 405
    assert not boundary.state.calls


def raw(server, request):
    with socket.create_connection(("127.0.0.1", server.server_port), timeout=3) as client:
        client.sendall(request.encode())
        return client.recv(4096)


@pytest.mark.parametrize(
    "headers",
    [
        "X-API-Key: another\r\n",
        "Content-Length: 0\r\nContent-Length: 0\r\n",
        "Transfer-Encoding: chunked\r\n",
        "Expect: 100-continue\r\n",
        "Content-Length: 00\r\n",
        "Host: other.invalid\r\n",
        "X-Forte-Principal: a\r\nX-Forte-Principal: b\r\n",
    ],
)
def test_ambiguous_request_framing_has_no_upstream_effect(boundary, headers):
    response = raw(
        boundary.server, f"GET {JOB} HTTP/1.1\r\nHost: {HOST}\r\nX-API-Key: {A}\r\n{headers}\r\n"
    )
    assert response.startswith((b"HTTP/1.1 400", b"HTTP/1.1 417"))
    assert not boundary.state.calls


def test_upload_default_disabled_and_bounded_before_any_upstream(config):
    config.pop("jury_uploads_enabled")
    with running(jury.create_server(config)) as server:
        assert call(server, "POST", "/api/v1/analyze", body=b"x").status == 403
    config["limits"] = {"upload_max_bytes": 8}
    config["jury_uploads_enabled"] = True
    with running(jury.create_server(config)) as server:
        assert call(server, "POST", "/api/v1/analyze", body=b"x" * 9).status == 413
        response = raw(
            server, f"POST /api/v1/analyze HTTP/1.1\r\nHost: {HOST}\r\nX-API-Key: {A}\r\n\r\n"
        )
        assert response.startswith(b"HTTP/1.1 411")


def test_absolute_upload_deadline_survives_continuous_trickle(boundary):
    boundary.server.gateway.limits["upload_timeout_seconds"] = 1
    with socket.create_connection(("127.0.0.1", boundary.server.server_port), timeout=3) as client:
        client.sendall(
            (
                f"POST /api/v1/analyze HTTP/1.1\r\nHost: {HOST}\r\nX-API-Key: {A}\r\n"
                "Content-Length: 100\r\n\r\n"
            ).encode()
        )
        started = time.monotonic()
        for _ in range(8):
            try:
                client.sendall(b"x")
            except OSError:
                break
            time.sleep(0.2)
        assert client.recv(4096).startswith(b"HTTP/1.1 502")
        assert time.monotonic() - started < 2.5


@pytest.mark.parametrize(
    "changes",
    [
        {"listen_host": "0.0.0.0"},
        {"listen_port": True},
        {"upstream": "http://localhost:8000"},
        {"upstream": "http://127.0.0.1:8001"},
        {"upstream": "http://127.0.0.1:8000/path"},
        {"origin": "http://jury.invalid"},
        {"origin": ORIGIN + "/"},
        {"session_db": "forbidden"},
        {"jury_uploads_enabled": 1},
        {"limits": {"upload_max_bytes": 268435457}},
        {"limits": {"upload_timeout_seconds": 31}},
        {"limits": {"upload_timeout_seconds": 0}},
    ],
)
def test_listener_target_and_activation_config_are_fail_closed(config, changes):
    with pytest.raises((ValueError, KeyError)):
        jury.create_server(config | changes)


@pytest.mark.parametrize(
    "mutation",
    ["symlink", "directory_symlink", "fifo", "permissions", "oversize", "hardlink", "parent"],
)
def test_private_fd_reader_rejects_unsafe_files(config, tmp_path, mutation):
    path = Path(config["jury_keys_file"])
    if mutation == "symlink":
        other = path.with_name("other.json")
        path.rename(other)
        path.symlink_to(other)
    elif mutation == "directory_symlink":
        link = tmp_path / "link"
        link.symlink_to(path.parent, target_is_directory=True)
        path = link / path.name
    elif mutation == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif mutation == "permissions":
        path.chmod(0o644)
    elif mutation == "oversize":
        path.write_bytes(b"x" * 65537)
    elif mutation == "hardlink":
        os.link(path, path.with_name("link.json"))
    elif mutation == "parent":
        path = path.parent / ".." / path.parent.name / path.name
    with pytest.raises((ValueError, OSError)):
        jury.private_bytes(str(path), 65536)


@pytest.mark.parametrize(
    "entries",
    [
        [entry(), entry()],
        [entry(), entry(B, PA)],
        [entry(SERVICE)],
        [entry(TOKEN)],
        [entry(principal="reviewer-a")],
        [entry(enabled="yes")],
        [{"key_sha256": "not-hash", "principal": PA, "enabled": True}],
        [entry() | {"raw_key": A}],
    ],
)
def test_key_inventory_is_hash_only_unique_and_separate(config, entries):
    write_keys(config, entries)
    with pytest.raises(ValueError):
        jury.JuryGateway(config)


def test_duplicate_json_properties_and_file_mutation_are_rejected(config, monkeypatch):
    path = Path(config["jury_keys_file"])
    path.write_text('{"schema_version":"forte.jury-keys/1","keys":[],"keys":[]}')
    with pytest.raises(ValueError):
        jury.JuryGateway(config)
    write_keys(config)
    original = jury.os.read
    changed = False

    def read(descriptor, size):
        nonlocal changed
        value = original(descriptor, size)
        if not changed:
            changed = True
            path.write_bytes(b"x" * path.stat().st_size)
        return value

    monkeypatch.setattr(jury.os, "read", read)
    with pytest.raises(ValueError):
        jury.private_bytes(str(path), 65536)


def test_real_core_jury_keys_persist_owners_and_do_not_cross_browser(config, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    settings = Settings(SERVICE, tmp_path / "cases", trusted_gateway_token=TOKEN)
    application = create_app(settings, runner=negative, ready=lambda: True)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with core_http(application) as upstream:
        config["upstream"] = upstream
        with running(jury.create_server(config)) as server:
            base = f"http://127.0.0.1:{server.server_port}"
            with httpx.Client(
                base_url=base, trust_env=False, timeout=10, headers={"Host": HOST}
            ) as client:
                response = client.post(
                    "/api/v1/analyze",
                    headers={"X-API-Key": A},
                    files={"file": ("synthetic.mov", source, "video/quicktime")},
                )
                assert response.status_code == 202, response.text
                identifier = response.json()["job_id"]
                path = "/api/v1/jobs/" + identifier
                assert response.headers["location"] == path
                for _ in range(200):
                    result = client.get(path, headers={"X-API-Key": A})
                    assert result.status_code == 200, result.text
                    if result.json()["status"] != "processing":
                        break
                    time.sleep(0.01)
                assert result.json() == {
                    "job_id": identifier,
                    "status": "done",
                    "verdict": "no_violation",
                    "violations": [],
                }
                assert json.loads(
                    (settings.private_root / identifier / "request.json").read_bytes()
                ) == {"api_version": 1, "owner_principal": PA}
                cross = client.get(path, headers={"X-API-Key": B, "X-Forte-Principal": PA})
                missing = client.get(JOB, headers={"X-API-Key": B})
                assert cross.status_code == missing.status_code == 404
                assert cross.content == missing.content
                second = client.post(
                    "/api/v1/analyze",
                    headers={"X-API-Key": B},
                    files={"file": ("synthetic.mov", source, "video/quicktime")},
                )
                assert second.status_code == 202
                second_id = second.json()["job_id"]
                assert second.headers["location"] == "/api/v1/jobs/" + second_id
                assert json.loads(
                    (settings.private_root / second_id / "request.json").read_bytes()
                ) == {"api_version": 1, "owner_principal": PB}
                assert (
                    client.get(second.headers["location"], headers={"X-API-Key": A}).status_code
                    == 404
                )
                ownerless = uuid4()
                directory = settings.private_root / str(ownerless)
                directory.mkdir(mode=0o700)
                atomic_json(
                    directory / "state.json",
                    DoneJob(job_id=ownerless, verdict="no_violation", violations=[]).model_dump(
                        mode="json"
                    ),
                )
                denied = client.get("/api/v1/jobs/" + str(ownerless), headers={"X-API-Key": A})
                assert denied.status_code == 404 and denied.content == missing.content
                assert "set-cookie" not in result.headers
                assert result.headers["cache-control"] == "no-store"
                assert SERVICE not in result.text and TOKEN not in result.text


@pytest.mark.parametrize(
    "mode",
    [
        "external_location",
        "encoded_location",
        "query_location",
        "fragment_location",
        "mismatch_location",
        "duplicate_location",
        "missing_location",
        "invalid_retry",
        "duplicate_retry",
        "misplaced_retry",
    ],
)
def test_hostile_or_ambiguous_v1_response_headers_are_refused(boundary, mode):
    boundary.state.mode = mode
    result = call(boundary.server, "POST", "/api/v1/analyze", body=b"synthetic")
    assert result.status == 502
    assert "Location" not in result.headers and "Retry-After" not in result.headers
    assert SERVICE.encode() not in result.body and TOKEN.encode() not in result.body


def test_exact_v1_response_headers_are_preserved(boundary):
    response = call(boundary.server, "POST", "/api/v1/analyze", body=b"synthetic")
    assert response.status == 202
    assert response.headers["Location"] == "/api/v1/jobs/" + json.loads(response.body)["job_id"]
    boundary.state.mode = "valid_retry"
    response = call(boundary.server, "POST", "/api/v1/analyze", body=b"synthetic")
    assert response.status == 429
    assert response.headers["Retry-After"] == "5"


@pytest.mark.parametrize("status", [429, 503])
def test_real_core_v1_admission_failure_preserves_retry_after(
    config, tmp_path, monkeypatch, status
):
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    settings = Settings(SERVICE, tmp_path / "cases", trusted_gateway_token=TOKEN)
    releases = threading.Event()
    calls = 0

    def ready():
        nonlocal calls
        calls += 1
        # The first same-socket health is ready; admission then observes loading.
        return status != 503 or calls == 1

    async def pending(directory, job_id, deadline):
        while not releases.is_set():
            await asyncio.sleep(0.01)
        return await negative(directory, job_id, deadline)

    application = create_app(settings, runner=pending, ready=ready)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with core_http(application) as upstream:
        config["upstream"] = upstream
        with running(jury.create_server(config)) as server:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{server.server_port}",
                trust_env=False,
                timeout=10,
                headers={"Host": HOST, "X-API-Key": A},
            ) as client:
                try:
                    if status == 429:
                        for _ in range(2):
                            response = client.post(
                                "/api/v1/analyze", files={"file": ("synthetic.mov", source)}
                            )
                            assert response.status_code == 202
                            assert jury.JOB.fullmatch(response.headers["location"])
                    response = client.post(
                        "/api/v1/analyze", files={"file": ("synthetic.mov", source)}
                    )
                    assert response.status_code == status, response.text
                    assert response.headers["retry-after"] == "5"
                    assert response.json()["error"]["code"] == (
                        "capacity_full" if status == 429 else "model_not_ready"
                    )
                    assert "location" not in response.headers
                finally:
                    releases.set()


def test_response_body_trickle_cannot_extend_absolute_deadline(boundary):
    boundary.state.mode = "response_trickle"
    boundary.server.gateway.limits["job_timeout_seconds"] = 1
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", boundary.server.server_port), timeout=3) as client:
        client.sendall(f"GET {JOB} HTTP/1.1\r\nHost: {HOST}\r\nX-API-Key: {A}\r\n\r\n".encode())
        data = bytearray()
        while block := client.recv(4096):
            data.extend(block)
    assert time.monotonic() - started < 2.5
    headers, body = bytes(data).split(b"\r\n\r\n", 1)
    assert b"Content-Length: 32" in headers
    assert (
        len(body) < 32
    )  # A partial body is closed, never represented as a completed JSON response.
