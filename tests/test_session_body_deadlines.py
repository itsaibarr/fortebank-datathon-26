"""Raw loopback regressions for continuous-progress bodies and request targets."""

import http.client
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_session_gateway import ORIGIN, PASSWORD, SECURITY
from test_session_gateway import boundary as boundary_fixture

boundary = boundary_fixture


def raw_headers(method, target, *, headers=None, length=0):
    lines = [f"{method} {target} HTTP/1.1", "Host: review.invalid"]
    lines.extend(f"{key}: {value}" for key, value in (headers or {}).items())
    lines.extend([f"Content-Length: {length}", "Connection: close", "", ""])
    return "\r\n".join(lines).encode()


def trickle_request(boundary, headers, fragments, interval):
    """Read the reply concurrently so rejection time excludes the sender's sleep."""
    with socket.create_connection(("127.0.0.1", boundary.server.server_port), timeout=8) as client:
        client.sendall(headers + fragments[0])
        started = time.monotonic()

        def send():
            try:
                for fragment in fragments[1:]:
                    time.sleep(interval)
                    client.sendall(fragment)
            except OSError:
                pass  # Closing a rejected body is the expected boundary behavior.

        sender = threading.Thread(target=send, daemon=True)
        sender.start()
        response = http.client.HTTPResponse(client)
        response.begin()
        body = response.read()
        elapsed = time.monotonic() - started
        sender.join(timeout=interval * len(fragments) + 1)
        assert not sender.is_alive()
        return response.status, body, elapsed


@pytest.mark.parametrize("target", ["//api/v2/jobs/synthetic", "///api/v2/jobs/synthetic"])
def test_original_leading_slashes_reject_before_core_dispatch(boundary, target):
    _, headers, _ = boundary.login()
    before = len(boundary.state.calls)
    with socket.create_connection(("127.0.0.1", boundary.server.server_port), timeout=3) as client:
        client.sendall(raw_headers("GET", target, headers=headers))
        response = http.client.HTTPResponse(client)
        response.begin()
        assert response.status == 400
        assert json.loads(response.read()) == {"error": {"code": "request_rejected"}}
    assert len(boundary.state.calls) == before


def test_canonical_target_keeps_query_bytes_and_same_socket(boundary):
    _, headers, _ = boundary.login()
    target = "/api/v2/jobs/synthetic?cursor=%2F%25&match=one"
    assert boundary.request("GET", target, headers=headers).status == 200
    handshake, forwarded = boundary.state.calls[-2:]
    assert forwarded["path"] == target
    assert handshake["socket"] is forwarded["socket"]


def test_upload_absolute_deadline_rejects_continuous_progress(boundary):
    _, headers, _ = boundary.login()
    boundary.server.gateway.limits["upload_timeout_seconds"] = 1
    status, body, elapsed = trickle_request(
        boundary,
        raw_headers("POST", "/api/v2/analyze", headers=headers, length=3),
        [b"a", b"b", b"c"],
        0.7,
    )
    assert status == 502
    assert json.loads(body) == {"error": {"code": "upstream_unavailable"}}
    assert elapsed < 1.35
    assert not any(
        call["method"] == "POST" and call["body"] == b"abc" for call in boundary.state.calls
    )


def test_login_absolute_deadline_rejects_unauthenticated_continuous_progress(boundary):
    body = json.dumps({"username": "reviewer", "password": PASSWORD}).encode()
    status, response, elapsed = trickle_request(
        boundary,
        raw_headers(
            "POST",
            "/auth/login",
            headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            length=len(body),
        ),
        [body[:1], *[body[index : index + 1] for index in range(1, 6)], body[6:]],
        0.9,
    )
    assert status == 502
    assert json.loads(response) == {"error": {"code": "upstream_unavailable"}}
    assert elapsed < 5.35
    assert boundary.state.calls == []


def test_response_body_deadline_rejects_continuous_upstream_progress(boundary):
    """Once response headers are sent, timeout closes the incomplete response."""
    _, headers, _ = boundary.login()
    boundary.server.gateway.limits["job_timeout_seconds"] = 1

    class SlowCore(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            capability = self.path == "/api/internal/security"
            body = json.dumps(SECURITY).encode() if capability else b"abc"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Forte-Ownership-Mode", "principal-v1")
            self.end_headers()
            if capability:
                self.wfile.write(body)
            else:
                try:
                    for index, byte in enumerate(body):
                        if index:
                            time.sleep(0.7)
                        self.wfile.write(bytes([byte]))
                except OSError:
                    pass

    core = ThreadingHTTPServer(("127.0.0.1", 0), SlowCore)
    core.daemon_threads = True
    worker = threading.Thread(target=core.serve_forever, daemon=True)
    worker.start()
    boundary.server.gateway.upstream = ("127.0.0.1", core.server_port)
    try:
        with socket.create_connection(
            ("127.0.0.1", boundary.server.server_port), timeout=3
        ) as client:
            client.sendall(raw_headers("GET", "/api/v2/jobs/synthetic", headers=headers))
            started = time.monotonic()
            response = http.client.HTTPResponse(client)
            response.begin()
            assert response.status == 200
            with pytest.raises(http.client.IncompleteRead) as failure:
                response.read()
            assert failure.value.partial != b"abc"
            assert time.monotonic() - started < 1.35
    finally:
        core.shutdown()
        core.server_close()
        worker.join(timeout=2)
