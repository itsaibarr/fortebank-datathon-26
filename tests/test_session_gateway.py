"""Synthetic HTTP boundary checks; full FastAPI/TLS integration lives separately."""

import http.client
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/forte-session"))
from session_gateway import COOKIE, SECURITY, Gateway, LoginLimiter, create_server  # noqa: E402
from session_store import SessionStore  # noqa: E402

ORIGIN = "https://review.invalid"
PASSWORD = "synthetic local browser password"
SERVICE = "synthetic-service-secret-" + "a" * 32
GATEWAY = "synthetic-gateway-secret-" + "b" * 32


@pytest.fixture
def boundary(tmp_path):
    state = SimpleNamespace(
        mode="normal", ready=True, calls=[], binary=b"x" * 180000, inject_auth_headers=False
    )

    class Core(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def respond(self, value, status=200, *, marker=True, close=False, headers=None):
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header(
                "Content-Type",
                "application/octet-stream" if isinstance(value, bytes) else "application/json",
            )
            if marker:
                self.send_header("X-Forte-Ownership-Mode", "principal-v1")
            if close:
                self.send_header("Connection", "close")
                self.close_connection = True
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            if state.inject_auth_headers:
                self.send_header("X-API-Key", SERVICE)
                self.send_header("X-Forte-Gateway-Token", GATEWAY)
                self.send_header("X-Forte-Principal", "synthetic-upstream-principal")
                self.send_header("Set-Cookie", "synthetic-upstream-cookie=untrusted")
            self.end_headers()
            self.wfile.write(raw)

        def record(self, body=b""):
            state.calls.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "socket": self.connection,
                    "headers": dict(self.headers.items()),
                    "body": body,
                }
            )

        def do_GET(self):
            self.record()
            if self.path == "/api/internal/security":
                if state.mode == "legacy":
                    return self.respond({}, 404, marker=False)
                if state.mode == "ambiguous_handshake":
                    return self.respond(SECURITY, headers={"Transfer-Encoding": "chunked"})
                return self.respond(SECURITY, close=state.mode == "closed_handshake")
            if self.path == "/health/ready":
                extra = (
                    {"Transfer-Encoding": "chunked"} if state.mode == "ambiguous_readiness" else {}
                )
                return self.respond(
                    {"status": "ready" if state.ready else "not_ready"},
                    200 if state.ready else 503,
                    headers=extra,
                )
            if state.mode == "redirect":
                return self.respond({}, 307, headers={"Location": "https://untrusted.invalid/"})
            return self.respond(
                state.binary if self.path.endswith("/source") else {"ok": True},
                marker=state.mode != "missing_marker",
            )

        def do_POST(self):
            self.record(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            self.respond({"accepted": True}, 202, marker=state.mode != "missing_marker")

    class QuietCoreServer(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            pass  # Intentionally rejected framing may reset this synthetic core connection.

    core = QuietCoreServer(("127.0.0.1", 0), Core)
    core.daemon_threads = True
    core_thread = threading.Thread(target=core.serve_forever, daemon=True)
    core_thread.start()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    for filename, value in (("service.key", SERVICE), ("gateway.key", GATEWAY)):
        path = private / filename
        path.write_text(value)
        path.chmod(0o600)
    store = SessionStore(private / "users.db")
    user = store.add_user("reviewer", PASSWORD)
    config = {
        "origin": ORIGIN,
        "upstream": f"http://127.0.0.1:{core.server_port}",
        "listen_port": 0,
        "service_key_file": str(private / "service.key"),
        "gateway_token_file": str(private / "gateway.key"),
        "browser_uploads_enabled": True,
    }
    gateway = create_server(config, store=store)
    gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
    gateway_thread.start()

    def request(method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", gateway.server_port, timeout=5)
        selected = {"Host": "review.invalid", **(headers or {})}
        connection.request(method, path, body=body, headers=selected)
        response = connection.getresponse()
        result = SimpleNamespace(
            status=response.status, headers=dict(response.headers.items()), body=response.read()
        )
        connection.close()
        return result

    def login():
        response = request(
            "POST",
            "/auth/login",
            json.dumps({"username": "reviewer", "password": PASSWORD}),
            {"Origin": ORIGIN, "Content-Type": "application/json"},
        )
        assert response.status == 200
        session = json.loads(response.body)
        cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        return (
            session,
            {"Cookie": cookie, "Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]},
            response,
        )

    try:
        yield SimpleNamespace(
            state=state,
            server=gateway,
            request=request,
            login=login,
            store=store,
            user=user,
            config=config,
        )
    finally:
        gateway.shutdown()
        gateway.server_close()
        core.shutdown()
        core.server_close()
        gateway_thread.join(timeout=2)
        core_thread.join(timeout=2)


def test_login_cookie_private_identity_and_same_connection_forwarding(boundary, capsys):
    assert json.loads(boundary.request("GET", "/auth/session").body) == {"authenticated": False}
    session, headers, response = boundary.login()
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith(COOKIE + "=")
    assert all(flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/"))
    assert "Domain=" not in cookie
    assert session["principal"] == {"id": boundary.user, "username": "reviewer"}
    forged = headers | {
        "X-API-Key": "forged",
        "X-Forte-Gateway-Token": "forged",
        "X-Forte-Principal": "other-user",
    }
    result = boundary.request("GET", "/api/v2/jobs/synthetic", headers=forged)
    assert result.status == 200
    handshake, forwarded = boundary.state.calls[-2:]
    assert handshake["path"] == "/api/internal/security"
    assert handshake["socket"] is forwarded["socket"]
    assert forwarded["headers"]["X-API-Key"] == SERVICE
    assert forwarded["headers"]["X-Forte-Gateway-Token"] == GATEWAY
    assert forwarded["headers"]["X-Forte-Principal"] == boundary.user
    assert "Cookie" not in forwarded["headers"]
    assert "X-CSRF-Token" not in forwarded["headers"]
    assert SERVICE.encode() not in result.body and GATEWAY.encode() not in result.body
    assert capsys.readouterr().out == ""


def test_csrf_upload_activation_readiness_streaming_and_logout(boundary):
    _, headers, _ = boundary.login()
    path = "/api/v2/analyze"
    assert boundary.request("POST", path, b"synthetic", {"Cookie": headers["Cookie"]}).status == 403
    assert (
        boundary.request(
            "POST", path, b"synthetic", headers | {"Origin": "https://other.invalid"}
        ).status
        == 403
    )
    boundary.server.gateway.uploads = False
    assert boundary.request("POST", path, b"synthetic", headers).status == 403
    boundary.server.gateway.uploads = True
    boundary.state.ready = False
    assert boundary.request("POST", path, b"synthetic", headers).status == 502
    assert not any(call["method"] == "POST" for call in boundary.state.calls)
    boundary.state.ready = True
    payload = b"synthetic-stream-" * 20000
    response = boundary.request("POST", path, payload, headers)
    assert response.status == 202 and boundary.state.calls[-1]["body"] == payload
    response = boundary.request("GET", "/api/v2/jobs/synthetic/source", headers=headers)
    assert response.status == 200 and response.body == boundary.state.binary
    assert boundary.request("POST", "/auth/logout", headers=headers).status == 204
    assert boundary.request("GET", "/api/v2/jobs/synthetic", headers=headers).status == 401


@pytest.mark.parametrize(
    "path,method",
    [
        ("/%61pi/internal/security", "GET"),
        ("/api/v2/%61nalyze", "POST"),
        ("/api/v2/%2561nalyze", "POST"),
        ("/api/internal/security", "GET"),
    ],
)
def test_noncanonical_and_internal_paths_never_reach_core(boundary, path, method):
    _, headers, _ = boundary.login()
    boundary.server.gateway.uploads = False
    calls = len(boundary.state.calls)
    assert boundary.request(
        method, path, b"synthetic" if method == "POST" else None, headers
    ).status in {400, 404}
    assert len(boundary.state.calls) == calls


@pytest.mark.parametrize(
    "mode", ["legacy", "closed_handshake", "ambiguous_handshake", "ambiguous_readiness"]
)
def test_invalid_or_closed_security_connection_never_forwards_mutation(boundary, mode):
    _, headers, _ = boundary.login()
    boundary.state.mode = mode
    response = boundary.request("POST", "/api/v2/analyze", b"synthetic", headers)
    assert response.status == 502
    assert not any(call["method"] == "POST" for call in boundary.state.calls)
    metadata = json.loads(boundary.request("GET", "/deployment.json").body)
    assert metadata["ready"] is False and metadata["browser_uploads_enabled"] is False
    assert boundary.request("GET", "/health/ready").status == 503


@pytest.mark.parametrize("mode", ["missing_marker", "redirect"])
def test_response_marker_or_redirect_failure_returns_no_upstream_api_bytes(boundary, mode):
    _, headers, _ = boundary.login()
    boundary.state.mode = mode
    response = boundary.request("GET", "/api/v2/jobs/synthetic", headers=headers)
    assert response.status == 502
    assert b'"ok"' not in response.body
    assert sum(call["path"] == "/api/v2/jobs/synthetic" for call in boundary.state.calls) == 1


@pytest.mark.parametrize(
    "extra",
    [
        "Content-Length: 1\r\nContent-Length: 1\r\n",
        "Content-Length: 1\r\nTransfer-Encoding: chunked\r\n",
        "Transfer-Encoding: chunked\r\n",
        "X-Forte-Principal: a\r\nX-Forte-Principal: b\r\n",
        "Cookie: one\r\nCookie: two\r\n",
        "Content-Length: 8193\r\n",
    ],
)
def test_duplicate_headers_framing_and_login_size_deny_before_body(boundary, extra):
    with socket.create_connection(
        ("127.0.0.1", boundary.server.server_port), timeout=2
    ) as connection:
        raw = (
            "POST /auth/login HTTP/1.1\r\nHost: review.invalid\r\n"
            f"Origin: {ORIGIN}\r\nContent-Type: application/json\r\n{extra}\r\n"
        ).encode()
        connection.sendall(raw)
        assert connection.recv(1024).startswith(b"HTTP/1.1 400")
    assert boundary.state.calls == []


def test_limiter_expiry_and_public_metadata_are_bounded_and_identity_free(boundary):
    now = [0.0]
    limiter = LoginLimiter(clock=lambda: now[0], per_account=2, per_client=3)
    assert limiter.allow("client", "one") and limiter.allow("client", "one")
    assert not limiter.allow("client", "one")
    assert limiter.allow("client", "two")
    assert not limiter.allow("client", "three")
    now[0] = 61
    assert limiter.allow("client", "one")
    boundary.login()
    metadata = boundary.request("GET", "/deployment.json")
    payload = json.loads(metadata.body)
    assert payload["schema_version"] == "forte.deployment/1"
    assert payload["ready"] is True and payload["auth_mode"] == "browser_session"
    assert payload["destination"] == ORIGIN
    assert b"reviewer" not in metadata.body and boundary.user.encode() not in metadata.body
    assert SERVICE.encode() not in metadata.body and GATEWAY.encode() not in metadata.body
    assert boundary.request("GET", "/health/live").status == 200


def test_response_authentication_headers_are_never_forwarded_to_browser(boundary):
    _, headers, _ = boundary.login()
    boundary.state.inject_auth_headers = True
    for path in ("/", "/api/v2/jobs/synthetic", "/deployment.json"):
        response = boundary.request("GET", path, headers=headers)
        assert response.status == 200
        for key in (
            "X-API-Key",
            "X-Forte-Gateway-Token",
            "X-Forte-Principal",
            "X-Forte-Ownership-Mode",
            "Set-Cookie",
        ):
            assert key not in response.headers
        assert SERVICE.encode() not in response.body and GATEWAY.encode() not in response.body


@pytest.mark.parametrize(
    "selection,expected",
    [
        ({}, "private"),
        ({"deployment_mode": "private"}, "private"),
        ({"deployment_mode": "hosted"}, "hosted"),
    ],
)
def test_deployment_mode_labels_metadata_without_activating_uploads(boundary, selection, expected):
    boundary.server.gateway = Gateway(
        boundary.config | selection | {"browser_uploads_enabled": False}, boundary.store
    )
    metadata = json.loads(boundary.request("GET", "/deployment.json").body)
    assert metadata["mode"] == expected
    assert metadata["ready"] is True and metadata["browser_uploads_enabled"] is False
    assert metadata["auth_mode"] == "browser_session"
    boundary.state.ready = False
    metadata = json.loads(boundary.request("GET", "/deployment.json").body)
    assert metadata["mode"] == expected
    assert metadata["ready"] is False and metadata["browser_uploads_enabled"] is False


@pytest.mark.parametrize("selection", ["public", None, ["hosted"]])
def test_deployment_mode_rejects_invalid_configuration(boundary, selection):
    with pytest.raises(ValueError, match="deployment_mode"):
        create_server(boundary.config | {"deployment_mode": selection}, store=boundary.store)


@pytest.mark.parametrize(
    "limits",
    [{"job_timeout_seconds": 271}, {"job_timeout_seconds": 270.0}, {"max_video_seconds": True}],
)
def test_gateway_rejects_limits_that_disagree_with_browser_core_bounds(boundary, limits):
    with pytest.raises(ValueError, match="limits"):
        create_server(boundary.config | {"limits": limits}, store=boundary.store)
