"""Synthetic transport tests only; no footage, inference, or detection-quality claims."""

import base64
import hashlib
import http.client
import json
import os
import ssl
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/forte-admin"))

from forte_admin.client import APIClient, ClientError, load_profile, save_profile  # noqa: E402

JOB = "820da8ee-1bd0-446a-8888-f9c97110f96a"
KEY = "synthetic-secret-for-transport-tests"


@pytest.fixture
def key_file(tmp_path):
    path = tmp_path / "synthetic.key"
    path.write_text(KEY + "\n")
    path.chmod(0o600)
    return path


@contextmanager
def synthetic_server(responder=None):
    """Clearly synthetic service, implementing only transport contract fixtures."""
    observed = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def handle_request(self):
            record = {
                "method": self.command,
                "path": self.path,
                "key": self.headers.get("X-API-Key"),
                "authorization": self.headers.get("Authorization"),
            }
            observed.append(record)
            if self.command == "POST":
                boundary = self.headers["Content-Type"].split("boundary=", 1)[1]
                suffix = f"\r\n--{boundary}--\r\n".encode()
                prefix = b""
                while not prefix.endswith(b"\r\n\r\n"):
                    part = self.rfile.readline(1024)
                    if not part:
                        return
                    prefix += part
                size = int(self.headers["Content-Length"]) - len(prefix) - len(suffix)
                digest = hashlib.sha256()
                remaining = size
                while remaining:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        return
                    digest.update(chunk)
                    remaining -= len(chunk)
                record.update(
                    {
                        "size": size,
                        "sha256": digest.hexdigest(),
                        "prefix": prefix,
                        "suffix_valid": self.rfile.read(len(suffix)) == suffix,
                    }
                )
            if responder:
                status, payload, headers = responder(record)
            elif self.command == "POST":
                status, payload, headers = 202, {"job_id": JOB}, {}
            elif self.path == "/health/ready":
                status, payload, headers = 200, {"status": "ready"}, {}
            else:
                status, payload, headers = 200, {"job_id": JOB, "status": "processing"}, {}
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observed
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com",
        "http://127.1",
        "http://0.0.0.0",
        "http://localhost.evil.test",
        "https://user:secret@example.com",
        "https://example.com/api",
        "https://example.com?",
        "https://example.com#fragment",
        "https://example.com:0",
        "https://example.com:65536",
        "https://example.com:",
        "https://exa mple.com",
        "ftp://example.com",
        "",
        "https://example.com/%2f",
        "https://example.com\\@evil.test",
        "https://[::1]unexpected-host",
        None,
    ],
)
def test_rejects_unsafe_origins_before_reading_secret(endpoint, key_file):
    with pytest.raises(ClientError) as error:
        APIClient(endpoint, key_file)
    assert error.value.code == "invalid_endpoint"


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("HTTPS://EXAMPLE.COM:443/", "https://example.com"),
        ("http://localhost:80", "http://localhost"),
        ("http://[::1]:1234/", "http://[::1]:1234"),
        ("http://127.0.0.2", "http://127.0.0.2"),
    ],
)
def test_canonical_origins_and_constructor_is_nonmutating(endpoint, expected, key_file):
    before = sorted(key_file.parent.iterdir())
    assert APIClient(endpoint, key_file).endpoint == expected
    assert sorted(key_file.parent.iterdir()) == before


def test_large_synthetic_mov_streams_correct_field_and_auth(tmp_path, key_file, monkeypatch):
    # 32 MiB public synthetic bytes exercise more than the supplied MOV sizes.
    path = tmp_path / "synthetic.MOV"
    block = b"synthetic transport only\x00" * 4096
    expected = hashlib.sha256()
    with path.open("wb") as out:
        for _ in range(342):
            out.write(block)
            expected.update(block)
    assert path.stat().st_size > 29 * 1024 * 1024
    calls = []
    original_send = http.client.HTTPConnection.send

    def send(connection, data):
        calls.append(len(data))
        return original_send(connection, data)

    monkeypatch.setattr(http.client.HTTPConnection, "send", send)
    with synthetic_server() as (endpoint, observed):
        result = APIClient(endpoint, key_file).upload(path)
    assert result == {"job_id": JOB}
    assert len(observed) == 1
    assert observed[0]["path"] == "/api/v2/analyze"
    assert observed[0]["key"] == KEY
    assert observed[0]["sha256"] == expected.hexdigest()
    assert observed[0]["size"] == path.stat().st_size
    assert observed[0]["suffix_valid"]
    assert b'name="file"; filename="input.mov"' in observed[0]["prefix"]
    assert path.name.encode() not in observed[0]["prefix"]
    assert max(calls) <= 1024 * 1024
    assert len(calls) > 30


def test_health_checks_readiness_and_bypasses_proxy_environment(key_file, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    with synthetic_server() as (endpoint, requests):
        assert APIClient(endpoint, key_file).health() == {"status": "ready"}
    assert [request["path"] for request in requests] == ["/health/ready"]


@pytest.mark.parametrize("http_status", [401, 413, 429, 503])
def test_http_failures_are_sanitized_without_server_content(http_status, key_file):
    sensitive = "never echo case content or " + KEY
    with synthetic_server(lambda _: (http_status, {"error": {"message": sensitive}}, {})) as (
        endpoint,
        _,
    ):
        with pytest.raises(ClientError) as error:
            APIClient(endpoint, key_file).health()
    assert error.value.status == http_status
    assert error.value.code == "http_error"
    assert sensitive not in str(error.value)
    assert KEY not in json.dumps(error.value.as_dict())
    assert "http_status" in error.value.as_dict()
    assert error.value.__cause__ is None


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_never_forwards_credentials_or_replays_post(status, tmp_path, key_file):
    path = tmp_path / "synthetic.mov"
    path.write_bytes(b"synthetic transport, not actual media")
    with synthetic_server() as (other, other_requests):
        with synthetic_server(lambda _: (status, {}, {"Location": other + "/leak"})) as (
            endpoint,
            requests,
        ):
            with pytest.raises(ClientError) as error:
                APIClient(endpoint, key_file).upload(path)
    assert error.value.code == "redirect_refused"
    assert len(requests) == 1
    assert other_requests == []


@pytest.mark.parametrize(
    "assessment",
    [
        "insufficient_evidence",
        "supported_violation",
        "no_violation_observed",
        "not_applicable",
        "future_uncertain_assessment",
    ],
)
def test_done_result_is_not_reinterpreted_and_additive_fields_survive(assessment, key_file):
    result = {
        "job_id": JOB,
        "status": "done",
        "api_version": 2,
        "future_field": [1, 2],
        "result": {
            "assessment": assessment,
            "execution": "partial",
            "events": [],
            "future_result_field": {"x": True},
        },
    }
    with synthetic_server(lambda _: (200, result, {})) as (endpoint, _):
        assert APIClient(endpoint, key_file).wait(JOB) == result
    assert "verdict" not in result


def test_wait_polls_processing_then_returns_failed_without_clean_result(key_file):
    responses = [
        {"job_id": JOB, "status": "processing", "progress": 1},
        {
            "job_id": JOB,
            "status": "failed",
            "error": {"code": "analysis_failed", "message": "Synthetic failure."},
        },
    ]
    with synthetic_server(lambda _: (200, responses.pop(0), {})) as (endpoint, requests):
        result = APIClient(endpoint, key_file).wait(JOB, poll_interval=0.001)
    assert result["status"] == "failed"
    assert "verdict" not in result and "result" not in result
    assert len(requests) == 2


@pytest.mark.parametrize(
    "response, code",
    [
        ({"job_id": JOB, "status": "unknown", "verdict": "no_violation"}, "unknown_job_status"),
        ({"job_id": JOB, "status": {}}, "unknown_job_status"),
        ({"job_id": JOB, "status": "done"}, "invalid_response"),
        ({"job_id": JOB, "status": "failed"}, "invalid_response"),
        ({"job_id": str(uuid4()), "status": "processing"}, "job_mismatch"),
        (b"not json or case content", "invalid_response"),
        (["not a response object"], "invalid_response"),
    ],
)
def test_invalid_or_unfamiliar_response_fails_closed(response, code, key_file):
    with synthetic_server(lambda _: (200, response, {})) as (endpoint, _):
        with pytest.raises(ClientError) as error:
            APIClient(endpoint, key_file).job(JOB)
    assert error.value.code == code


def test_v1_routes_preserve_legacy_contract(key_file, tmp_path):
    path = tmp_path / "synthetic.mov"
    path.write_bytes(b"synthetic")
    expected = {"job_id": JOB, "status": "done", "verdict": "no_violation", "violations": []}

    def respond(request):
        return (202, {"job_id": JOB}, {}) if request["method"] == "POST" else (200, expected, {})

    with synthetic_server(respond) as (endpoint, requests):
        client = APIClient(endpoint, key_file, api_version=1)
        assert client.upload(path) == {"job_id": JOB}
        assert client.job(JOB) == expected
    assert [request["path"] for request in requests] == ["/api/v1/analyze", f"/api/v1/jobs/{JOB}"]


def test_profile_is_idempotent_private_and_origin_bound(tmp_path, key_file):
    profile = tmp_path / "connection.json"
    first = save_profile(profile, "https://EXAMPLE.COM:443/", key_file)
    binding = key_file.with_name(key_file.name + ".forte-origin.json")
    binding_bytes, key_bytes = binding.read_bytes(), key_file.read_bytes()
    assert save_profile(profile, "https://example.com", key_file) == first
    assert load_profile(profile) == first
    assert profile.stat().st_mode & 0o777 == 0o600
    assert binding.stat().st_mode & 0o777 == 0o600
    assert binding.read_bytes() == binding_bytes
    assert key_file.read_bytes() == key_bytes
    assert KEY not in profile.read_text() + binding.read_text()
    with pytest.raises(ClientError, match="different application origin"):
        APIClient("https://other.example.com", key_file)
    with pytest.raises(ClientError, match="different application origin"):
        save_profile(profile, "https://other.example.com", key_file)
    assert load_profile(profile) == first


def test_tampered_profile_does_not_rebind_key(tmp_path, key_file):
    profile = tmp_path / "connection.json"
    value = save_profile(profile, "https://example.com", key_file)
    value["endpoint"] = "https://other.example.com"
    profile.write_text(json.dumps(value))
    with pytest.raises(ClientError) as error:
        load_profile(profile)
    assert error.value.code == "endpoint_mismatch"


def test_saving_profile_cannot_overwrite_key_even_via_alias_or_hardlink(tmp_path, key_file):
    alias = tmp_path / "alias"
    alias.hardlink_to(key_file)
    for target in (key_file, alias, tmp_path / ".." / tmp_path.name / key_file.name):
        with pytest.raises(ClientError):
            save_profile(target, "https://example.com", key_file)
    assert key_file.read_text().strip() == KEY


def test_insecure_or_symlinked_secret_and_profile_are_rejected(tmp_path, key_file):
    key_file.chmod(0o644)
    with pytest.raises(ClientError) as error:
        APIClient("https://example.com", key_file)
    assert error.value.code == "invalid_key_file"
    key_file.chmod(0o600)
    link = tmp_path / "key-link"
    link.symlink_to(key_file)
    with pytest.raises(ClientError):
        APIClient("https://example.com", link)
    profile = tmp_path / "profile.json"
    save_profile(profile, "https://example.com", key_file)
    profile.chmod(0o644)
    with pytest.raises(ClientError):
        load_profile(profile)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True, "1"])
def test_timeouts_must_be_positive_finite_numbers(timeout, key_file):
    with pytest.raises(ClientError) as error:
        APIClient("https://example.com", key_file, timeout=timeout)
    assert error.value.code == "invalid_timeout"


def test_poll_timeout_is_bounded_without_retrying_upload(key_file):
    with synthetic_server() as (endpoint, requests):
        start = time.monotonic()
        with pytest.raises(ClientError) as error:
            APIClient(endpoint, key_file).wait(JOB, timeout=0.06, poll_interval=0.01)
        elapsed = time.monotonic() - start
    assert error.value.code == "poll_timeout"
    assert elapsed < 0.5
    assert requests and all(request["method"] == "GET" for request in requests)


def test_timeout_during_post_is_ambiguous_and_never_retried(tmp_path, key_file):
    path = tmp_path / "synthetic.mov"
    path.write_bytes(b"synthetic")

    def slow(_request):
        time.sleep(0.15)
        return 202, {"job_id": JOB}, {}

    with synthetic_server(slow) as (endpoint, requests):
        with pytest.raises(ClientError) as error:
            APIClient(endpoint, key_file, timeout=0.03).upload(path)
    assert error.value.code == "request_timeout"
    assert "may already be admitted" in str(error.value)
    assert len(requests) == 1


def test_tls_failure_is_sanitized_and_does_not_try_http(key_file, monkeypatch):
    destinations = []

    def reject_tls(host, port, **_kwargs):
        destinations.append((host, port))
        raise ssl.SSLError("synthetic sensitive failure " + KEY)

    monkeypatch.setattr(http.client, "HTTPSConnection", reject_tls)
    with pytest.raises(ClientError) as error:
        APIClient("https://example.com", key_file).health()
    assert destinations == [("example.com", None)]
    assert error.value.code == "tls_error"
    assert KEY not in str(error.value)
    assert error.value.__cause__ is None


def test_invalid_local_upload_and_job_id_never_connect(tmp_path, key_file):
    with synthetic_server() as (endpoint, requests):
        client = APIClient(endpoint, key_file)
        for name in ("missing.mov", "unsupported.mp4"):
            with pytest.raises(ClientError):
                client.upload(tmp_path / name)
        fifo = tmp_path / "pipe.mov"
        os.mkfifo(fifo)
        with pytest.raises(ClientError):
            client.upload(fifo)
        with pytest.raises(ClientError):
            client.job("../../health/ready")
    assert requests == []


def test_cli_transport_error_has_no_traceback_or_case_body(tmp_path, key_file, capsys):
    from forte_admin.cli import main

    private_message = "synthetic private case description " + KEY
    profile = tmp_path / "profile.json"
    with synthetic_server(lambda _: (503, {"error": {"message": private_message}}, {})) as (
        endpoint,
        _,
    ):
        save_profile(profile, endpoint, key_file)
        assert main(["job", "--profile", str(profile), "--job-id", JOB]) == 3
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "http_error"
    assert private_message not in captured.out + captured.err
    assert KEY not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err


def test_cli_submission_summary_withholds_case_content(tmp_path, key_file, capsys):
    from forte_admin.cli import main

    private_message = "synthetic private visual explanation"
    result = {
        "job_id": JOB,
        "status": "done",
        "result": {
            "assessment": "insufficient_evidence",
            "events": [{"description": private_message}],
        },
    }

    def respond(request):
        return (202, {"job_id": JOB}, {}) if request["method"] == "POST" else (200, result, {})

    path = tmp_path / "synthetic.mov"
    path.write_bytes(b"synthetic")
    profile = tmp_path / "profile.json"
    with synthetic_server(respond) as (endpoint, _):
        save_profile(profile, endpoint, key_file)
        assert (
            main(["analyze", "--profile", str(profile), "--file", str(path), "--submit", "--wait"])
            == 0
        )
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["status"] == "done"
    assert summary["full_result_saved"] is False
    assert endpoint in captured.err
    assert private_message not in captured.out + captured.err
    assert "no_violation" not in captured.out
    assert KEY not in captured.out + captured.err


@pytest.fixture
def gateway_file(tmp_path):
    path = tmp_path / "synthetic-gateway.credentials"
    path.write_text("synthetic-admin:synthetic-password:with-colon\n")
    path.chmod(0o600)
    return path


def test_optional_gateway_basic_auth_preserves_canonical_api_key(key_file, gateway_file, tmp_path):
    expected = "Basic " + base64.b64encode(gateway_file.read_bytes().removesuffix(b"\n")).decode()

    def gateway(request):
        if request["authorization"] != expected:
            return 401, {"error": {}}, {"WWW-Authenticate": 'Basic realm="synthetic"'}
        assert request["key"] == KEY
        if request["method"] == "POST":
            return 202, {"job_id": JOB}, {}
        return 200, {"status": "ready"}, {}

    path = tmp_path / "synthetic.mov"
    path.write_bytes(b"synthetic")
    with synthetic_server(gateway) as (endpoint, requests):
        with pytest.raises(ClientError) as error:
            APIClient(endpoint, key_file).health()
        assert error.value.status == 401
        assert len(requests) == 1  # A challenge never causes an implicit retry.
        client = APIClient(endpoint, key_file, gateway_credentials_file=gateway_file)
        assert client.health() == {"status": "ready"}
        assert client.upload(path) == {"job_id": JOB}
    assert requests[0]["authorization"] is None
    assert all(request["authorization"] == expected for request in requests[1:])
    assert all(request["key"] == KEY for request in requests)


def test_gateway_profile_binds_both_files_and_is_idempotent(key_file, gateway_file, tmp_path):
    path = tmp_path / "gateway-profile.json"
    endpoint = "https://example.com"
    profile = save_profile(path, endpoint, key_file, gateway_credentials_file=gateway_file)
    assert profile["gateway_credentials_file"] == str(gateway_file)
    assert load_profile(path) == profile
    assert save_profile(path, endpoint, key_file, gateway_credentials_file=gateway_file) == profile
    secret = gateway_file.read_text().strip()
    assert secret not in path.read_text()
    assert base64.b64encode(secret.encode()).decode() not in path.read_text()
    for credential in (key_file, gateway_file):
        binding = credential.with_name(credential.name + ".forte-origin.json")
        assert binding.stat().st_mode & 0o777 == 0o600
        assert json.loads(binding.read_text())["endpoint"] == endpoint
    other_key = tmp_path / "other.key"
    other_key.write_text(KEY + "-other")
    other_key.chmod(0o600)
    with pytest.raises(ClientError) as error:
        save_profile(
            tmp_path / "other-profile.json",
            "https://other.example.com",
            other_key,
            gateway_credentials_file=gateway_file,
        )
    assert error.value.code == "endpoint_mismatch"
    with pytest.raises(ClientError) as error:
        APIClient("https://other.example.com", other_key, gateway_credentials_file=gateway_file)
    assert error.value.code == "endpoint_mismatch"


@pytest.mark.parametrize(
    "contents",
    [
        b"",
        b"missing-separator",
        b":password",
        b"admin:",
        b"admin:pass\r\n",
        b"admin:pass\n\n",
        b"admin:pass\x00word",
        b"admin:pass\tword",
        b"admin:\xff",
    ],
)
def test_gateway_file_rejects_invalid_values_without_exposing_them(contents, tmp_path, key_file):
    path = tmp_path / "invalid.credentials"
    path.write_bytes(contents)
    path.chmod(0o600)
    with pytest.raises(ClientError) as error:
        APIClient("https://example.com", key_file, gateway_credentials_file=path)
    assert error.value.code == "invalid_gateway_credentials_file"
    assert error.value.exit_code == 2
    assert "Authorization" not in json.dumps(error.value.as_dict())
    assert "pass\u0000word" not in str(error.value)


def test_gateway_file_requires_private_regular_file(key_file, gateway_file, tmp_path):
    gateway_file.chmod(0o644)
    with pytest.raises(ClientError):
        APIClient("https://example.com", key_file, gateway_credentials_file=gateway_file)
    gateway_file.chmod(0o600)
    link = tmp_path / "symlink.credentials"
    link.symlink_to(gateway_file)
    with pytest.raises(ClientError):
        APIClient("https://example.com", key_file, gateway_credentials_file=link)
    fifo = tmp_path / "fifo.credentials"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(ClientError):
        APIClient("https://example.com", key_file, gateway_credentials_file=fifo)


def test_gateway_file_revalidated_on_profile_load_and_before_every_request(
    key_file, gateway_file, tmp_path
):
    path = tmp_path / "gateway-profile.json"
    with synthetic_server() as (endpoint, requests):
        save_profile(path, endpoint, key_file, gateway_credentials_file=gateway_file)
        client = APIClient(endpoint, key_file, gateway_credentials_file=gateway_file)
        gateway_file.write_text("invalid credential with no separator")
        with pytest.raises(ClientError) as error:
            load_profile(path)
        assert error.value.code == "invalid_gateway_credentials_file"
        with pytest.raises(ClientError) as error:
            client.health()
        assert error.value.code == "invalid_gateway_credentials_file"
    assert requests == []


def test_gateway_credentials_are_never_forwarded_on_redirect_or_error(key_file, gateway_file):
    secret = gateway_file.read_text().strip()
    encoded = base64.b64encode(secret.encode()).decode()
    with synthetic_server() as (other, other_requests):
        with synthetic_server(lambda _: (307, {"private": secret}, {"Location": other})) as (
            endpoint,
            requests,
        ):
            with pytest.raises(ClientError) as error:
                APIClient(endpoint, key_file, gateway_credentials_file=gateway_file).health()
    assert error.value.code == "redirect_refused"
    assert len(requests) == 1 and requests[0]["authorization"] == "Basic " + encoded
    assert other_requests == []
    assert secret not in str(error.value)
    assert encoded not in json.dumps(error.value.as_dict())


def test_gateway_profile_cannot_overwrite_credentials(key_file, gateway_file):
    original = gateway_file.read_bytes()
    with pytest.raises(ClientError):
        save_profile(
            gateway_file,
            "https://example.com",
            key_file,
            gateway_credentials_file=gateway_file,
        )
    assert gateway_file.read_bytes() == original
