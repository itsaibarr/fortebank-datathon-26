"""Loopback browser-session boundary for an explicitly trusted, offline core.

Every forward uses a single TCP connection: authenticate its security capability,
then send exactly one request on that same socket without reconnect or retry.
Only the TLS ingress should expose this loopback service to a browser.
"""

from __future__ import annotations

import argparse
import collections
import hmac
import http.client
import json
import math
import os
import re
import select
import signal
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from session_store import SessionStore

COOKIE = "__Host-forte_session"
SECURITY = {
    "schema_version": "forte.gateway-security/1",
    "trusted_gateway_required": True,
    "principal_ownership": True,
    "ownerless_jobs_denied": True,
}
LIMITS = {
    "upload_max_bytes": 268435456,
    "max_video_seconds": 180,
    "upload_timeout_seconds": 30,
    "job_timeout_seconds": 270,
}
LOGIN_BODY_TIMEOUT_SECONDS = 5
SENSITIVE = {
    "host",
    "cookie",
    "origin",
    "content-length",
    "transfer-encoding",
    "authorization",
    "x-csrf-token",
    "x-api-key",
    "x-forte-gateway-token",
    "x-forte-principal",
    "x-forte-ownership-mode",
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-user",
    "expect",
    "range",
    "content-type",
    "connection",
    "trailer",
    "proxy-authorization",
}
FORWARD_HEADERS = {
    "content-type",
    "accept",
    "range",
    "if-range",
    "if-none-match",
    "if-modified-since",
}
RESPONSE_HEADERS = {
    "content-type",
    "content-range",
    "accept-ranges",
    "etag",
    "last-modified",
    "content-disposition",
}
LENGTH = re.compile(r"0|[1-9][0-9]{0,11}")
HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


class Unavailable(Exception):
    """A generic boundary failure; never carries private upstream details."""


def _secret(path, minimum):
    path = Path(path).absolute()
    if path.is_symlink() or path.parent.resolve() != path.parent:
        raise ValueError("Credential files cannot traverse symlinks")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Credential files must be private regular files owned by this user")
    if info.st_size > 1024:
        raise ValueError("Invalid credential file")
    secret = path.read_text(encoding="ascii").strip()
    if not minimum <= len(secret) <= 256 or not all(33 <= ord(c) <= 126 for c in secret):
        raise ValueError("Invalid credential file")
    return secret


def _length(headers):
    values = headers.get_all("Content-Length", [])
    if len(values) > 1 or values and LENGTH.fullmatch(values[0]) is None:
        raise Unavailable
    return int(values[0]) if values else None


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


class OneConnection(http.client.HTTPConnection):
    def connect(self):
        if getattr(self, "connected_once", False):
            raise Unavailable
        super().connect()
        self.connected_once = True


class LoginLimiter:
    def __init__(self, clock=time.monotonic, per_account=8, per_client=30):
        self.clock, self.per_account, self.per_client = clock, per_account, per_client
        self.records = {}
        self.lock = threading.Lock()

    def allow(self, address, username):
        # The bounded body limits username size; no names or credentials enter logs.
        account = hmac.digest(b"forte-login-rate-bucket", username.encode("utf-8"), "sha256")
        now = self.clock()
        with self.lock:
            for key in list(self.records):
                values = self.records[key]
                while values and values[0] <= now - 60:
                    values.popleft()
                if not values:
                    del self.records[key]
            client_key, account_key = (address, None), (address, account)
            client = self.records.setdefault(client_key, collections.deque())
            user = self.records.setdefault(account_key, collections.deque())
            if len(client) >= self.per_client or len(user) >= self.per_account:
                return False
            client.append(now)
            user.append(now)
            return True


class Gateway:
    def __init__(self, config, store):
        self.config = dict(config)
        self.deployment_mode = config.get("deployment_mode", "private")
        if not isinstance(self.deployment_mode, str) or self.deployment_mode not in {
            "private",
            "hosted",
        }:
            raise ValueError("deployment_mode must be private or hosted")
        origin = urlsplit(config.get("origin", ""))
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
            or not origin.netloc.isascii()
        ):
            raise ValueError("Configure one exact HTTPS origin without a path")
        if not 1 <= (origin.port or 443) <= 65535:
            raise ValueError("Invalid HTTPS origin port")
        upstream = urlsplit(config.get("upstream", ""))
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
            raise ValueError("Core upstream must be a literal loopback HTTP origin")
        self.origin, self.authority = config["origin"], origin.netloc
        self.upstream = (upstream.hostname, upstream.port)
        self.service_key = _secret(config["service_key_file"], 16)
        self.gateway_token = _secret(config["gateway_token_file"], 32)
        if hmac.compare_digest(self.service_key, self.gateway_token):
            raise ValueError("Gateway token must differ from the service key")
        self.store = store if store is not None else SessionStore(config["session_db"])
        self.limits = LIMITS | config.get("limits", {})
        if set(self.limits) != set(LIMITS) or any(
            type(value) is not int or not math.isfinite(value) or value <= 0
            for value in self.limits.values()
        ):
            raise ValueError("Invalid gateway limits")
        if (
            type(self.limits["upload_max_bytes"]) is not int
            or self.limits["upload_max_bytes"] > LIMITS["upload_max_bytes"]
            or self.limits["max_video_seconds"] > 180
            or self.limits["upload_timeout_seconds"] > 30
            or self.limits["job_timeout_seconds"] > 270
        ):
            raise ValueError("Gateway limits cannot exceed core bounds")
        if type(config.get("browser_uploads_enabled", False)) is not bool:
            raise ValueError("Browser upload activation must be an explicit boolean")
        self.uploads = config.get("browser_uploads_enabled", False)
        self.limiter = LoginLimiter()

    def _auth(self, principal):
        return {
            "X-API-Key": self.service_key,
            "X-Forte-Gateway-Token": self.gateway_token,
            "X-Forte-Principal": principal,
        }

    @staticmethod
    def same_socket(connection, original):
        if connection.sock is not original or original is None or original.fileno() < 0:
            raise Unavailable
        # A FIN or unsolicited response already waiting cannot authorize a new request.
        if select.select([original], [], [], 0)[0]:
            raise Unavailable

    def checked_connection(self, principal):
        connection = OneConnection(*self.upstream, timeout=5)
        try:
            connection.connect()
            original = connection.sock
            connection.request("GET", "/api/internal/security", headers=self._auth(principal))
            response = connection.getresponse()
            size = _length(response.headers)
            if (
                response.status != 200
                or response.will_close
                or size is None
                or size > 4096
                or response.headers.get_all("X-Forte-Ownership-Mode") != ["principal-v1"]
                or response.headers.get_all("Transfer-Encoding")
            ):
                raise Unavailable
            raw = response.read(4097)
            if len(raw) != size:
                raise Unavailable
            value = json.loads(raw)
            if (
                not isinstance(value, dict)
                or set(value) != set(SECURITY)
                or value.get("schema_version") != SECURITY["schema_version"]
                or any(value.get(key) is not True for key in SECURITY if key != "schema_version")
            ):
                raise Unavailable
            self.same_socket(connection, original)
            return connection, original
        except Exception:
            connection.close()
            raise Unavailable from None

    def ready_on(self, connection, original):
        self.same_socket(connection, original)
        connection.request("GET", "/health/ready")
        response = connection.getresponse()
        size = _length(response.headers)
        if (
            response.status != 200
            or response.will_close
            or size is None
            or size > 4096
            or response.headers.get_all("Transfer-Encoding")
        ):
            raise Unavailable
        raw = response.read(4097)
        if len(raw) != size:
            raise Unavailable
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("status") != "ready":
            raise Unavailable
        self.same_socket(connection, original)

    def ready(self):
        connection = None
        try:
            connection, original = self.checked_connection("gateway_probe")
            self.ready_on(connection, original)
            return True
        except Exception:
            return False
        finally:
            if connection:
                connection.close()


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, gateway):
        self.gateway = gateway
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, GatewayHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n"
                    b"Connection: close\r\n\r\n"
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Request paths, cookies, credentials and bodies never enter logs.


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ForteSession"
    sys_version = ""

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.response_started = False

    def send_error(self, code, message=None, explain=None):
        self.json_response(code, {"error": {"code": "request_rejected"}})

    def handle_expect_100(self):
        self.send_error(417)
        return False

    @property
    def gateway(self):
        return self.server.gateway

    def json_response(self, status, value, headers=None):
        raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        self.send_response(status)
        self.response_started = True
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(0 if status == 204 else len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if getattr(self, "command", None) != "HEAD" and status != 204:
            self.wfile.write(raw)

    def validated_request(self):
        # BaseHTTPRequestHandler normalizes leading // before dispatch. Reject
        # the original target, rather than accepting its rewritten path.
        words = self.raw_requestline.decode("iso-8859-1").split()
        if len(words) != 3:
            raise ValueError
        target = words[1]
        if (
            target != self.path
            or len(target) > 8192
            or not target.startswith("/")
            or target.startswith("//")
        ):
            raise ValueError
        parsed = urlsplit(target)
        decoded = unquote(parsed.path)
        if (
            (
                parsed.scheme
                or parsed.netloc
                or parsed.fragment
                or "\\" in decoded
                or decoded != parsed.path
                or "%" in parsed.path
                or not parsed.path.isascii()
            )
            or any(part in {".", ".."} for part in decoded.split("/"))
            or any(ord(char) < 32 or ord(char) == 127 for char in self.path)
        ):
            raise ValueError
        items = self.headers.items()
        if sum(len(key) + len(value) + 4 for key, value in items) > 16384:
            raise ValueError
        counts = collections.Counter(key.lower() for key in self.headers)
        if any(counts[key] > 1 for key in SENSITIVE) or any(
            HEADER_NAME.fullmatch(key) is None or any(ord(c) < 32 or ord(c) == 127 for c in value)
            for key, value in self.headers.items()
        ):
            raise ValueError
        if self.headers.get("Host") != self.gateway.authority:
            raise ValueError
        if self.headers.get_all("Transfer-Encoding") or self.headers.get_all("Expect"):
            raise ValueError
        length = _length(self.headers)
        if self.command in {"GET", "HEAD"} and length:
            raise ValueError
        return parsed.path, length or 0

    def body_blocks(self, length, deadline):
        """Read available bytes once, then recheck the absolute body deadline.

        Buffered read(n) may perform many socket reads to fill n; a continuous
        trickle can reset its idle timeout indefinitely. read1 performs at most
        one raw read, so every incoming block returns to the monotonic check.
        """
        remaining = length
        while remaining:
            self.connection.settimeout(_remaining(deadline))
            block = self.rfile.read1(min(65536, remaining))
            _remaining(deadline)
            if not block:
                raise ValueError
            remaining -= len(block)
            yield block

    def session_token(self):
        tokens = []
        for part in self.headers.get("Cookie", "").split(";"):
            key, separator, value = part.strip().partition("=")
            if separator and key == COOKIE:
                tokens.append(value)
        return tokens[0] if len(tokens) == 1 else None

    def session(self):
        return self.gateway.store.get_session(self.session_token())

    def origin_valid(self):
        return self.headers.get("Origin") == self.gateway.origin

    def csrf_valid(self, session):
        token = self.headers.get("X-CSRF-Token", "")
        return bool(
            self.origin_valid() and token and hmac.compare_digest(token, session["csrf_token"])
        )

    @staticmethod
    def cookie(token, *, expire=False):
        return (
            f"{COOKIE}={token}; Max-Age={0 if expire else 28800}; Path=/; "
            "Secure; HttpOnly; SameSite=Strict"
        )

    def login(self, length):
        if not self.origin_valid():
            return self.json_response(403, {"error": {"code": "request_rejected"}})
        if (
            not 0 < length <= 8192
            or self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json"
        ):
            return self.json_response(400, {"error": {"code": "request_rejected"}})
        raw = b"".join(self.body_blocks(length, time.monotonic() + LOGIN_BODY_TIMEOUT_SECONDS))
        try:
            credentials = json.loads(raw)
            if not isinstance(credentials, dict) or set(credentials) != {"username", "password"}:
                raise ValueError
            username, password = credentials["username"], credentials["password"]
            if not isinstance(username, str) or not isinstance(password, str):
                raise ValueError
        except (ValueError, UnicodeError):
            return self.json_response(400, {"error": {"code": "request_rejected"}})
        if not self.gateway.limiter.allow(self.client_address[0], username):
            return self.json_response(
                429, {"error": {"code": "login_unavailable"}}, {"Retry-After": "60"}
            )
        issued = self.gateway.store.login(username, password, self.session_token())
        if issued is None:
            return self.json_response(401, {"error": {"code": "login_failed"}})
        token, session = issued
        self.json_response(
            200, {"authenticated": True, **session}, {"Set-Cookie": self.cookie(token)}
        )

    def forward(self, length, session, *, api):
        upload = self.command == "POST" and urlsplit(self.path).path in {
            "/api/v1/analyze",
            "/api/v2/analyze",
        }
        if length > self.gateway.limits["upload_max_bytes"]:
            return self.json_response(413, {"error": {"code": "request_too_large"}})
        if upload and not self.gateway.uploads:
            return self.json_response(403, {"error": {"code": "uploads_disabled"}})
        principal = session["principal"]["id"] if session else "gateway_probe"
        connection, original = self.gateway.checked_connection(principal)
        try:
            if upload:
                self.gateway.ready_on(connection, original)
            self.gateway.same_socket(connection, original)
            connection.putrequest(self.command, self.path, skip_accept_encoding=True)
            for key, value in self.headers.items():
                if key.lower() in FORWARD_HEADERS:
                    connection.putheader(key, value)
            for key, value in self.gateway._auth(principal).items():
                connection.putheader(key, value)
            connection.putheader("Accept-Encoding", "identity")
            if self.command not in {"GET", "HEAD"}:
                connection.putheader("Content-Length", str(length))
            connection.endheaders()
            upload_deadline = time.monotonic() + self.gateway.limits["upload_timeout_seconds"]
            for block in self.body_blocks(length, upload_deadline):
                connection.sock.settimeout(_remaining(upload_deadline))
                connection.send(block)
                _remaining(upload_deadline)
            deadline = time.monotonic() + self.gateway.limits["job_timeout_seconds"]
            connection.sock.settimeout(self.gateway.limits["job_timeout_seconds"])
            response = connection.getresponse()
            headers = response.headers
            counts = collections.Counter(key.lower() for key in headers)
            if (
                any(counts[key] > 1 for key in SENSITIVE | RESPONSE_HEADERS)
                or any(
                    HEADER_NAME.fullmatch(key) is None
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)
                    for key, value in headers.items()
                )
                or sum(len(key) + len(value) + 4 for key, value in headers.items()) > 16384
            ):
                raise Unavailable
            size = _length(headers)
            encoding = headers.get("Transfer-Encoding")
            if encoding and (encoding.lower() != "chunked" or size is not None):
                raise Unavailable
            if (
                300 <= response.status < 400
                or api
                and headers.get("X-Forte-Ownership-Mode") != "principal-v1"
            ):
                raise Unavailable
            maximum = self.gateway.limits["upload_max_bytes"] + 16 * 1024**2
            if size is not None and size > maximum:
                raise Unavailable
            self.send_response(response.status)
            self.response_started = True
            for key, value in headers.items():
                if key.lower() in RESPONSE_HEADERS:
                    self.send_header(key, value)
            if size is not None:
                self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if self.command == "HEAD":
                return
            copied = 0
            while True:
                timeout = _remaining(deadline)
                if connection.sock is not None:
                    connection.sock.settimeout(timeout)
                block = response.read1(min(65536, maximum - copied + 1))
                _remaining(deadline)
                if not block:
                    break
                copied += len(block)
                if copied > maximum:
                    raise Unavailable
                self.connection.settimeout(_remaining(deadline))
                self.wfile.write(block)
                _remaining(deadline)
            if size is not None and copied != size:
                raise Unavailable
        finally:
            connection.close()

    def dispatch(self):
        try:
            path, length = self.validated_request()
        except (ValueError, Unavailable):
            return self.json_response(400, {"error": {"code": "request_rejected"}})
        if self.command not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
            return self.json_response(405, {"error": {"code": "method_not_allowed"}})
        if path == "/health/live" and self.command in {"GET", "HEAD"}:
            return self.json_response(200, {"status": "alive"})
        if path in {"/deployment.json", "/health/ready"} and self.command in {"GET", "HEAD"}:
            ready = self.gateway.ready()
            if path == "/health/ready":
                return self.json_response(
                    200 if ready else 503, {"status": "ready" if ready else "not_ready"}
                )
            return self.json_response(
                200,
                {
                    "schema_version": "forte.deployment/1",
                    "mode": self.gateway.deployment_mode,
                    "auth_mode": "browser_session",
                    "destination": self.gateway.origin,
                    "browser_uploads_enabled": bool(self.gateway.uploads and ready),
                    "ready": ready,
                    "retention": "manual",
                    "training_enabled": False,
                    "limits": self.gateway.limits,
                },
            )
        if path == "/auth/login" and self.command == "POST":
            return self.login(length)
        if path == "/auth/session" and self.command == "GET":
            session = self.session()
            return self.json_response(200, {"authenticated": bool(session), **(session or {})})
        if path == "/auth/logout" and self.command == "POST":
            session = self.session()
            if not session:
                return self.json_response(401, {"error": {"code": "authentication_required"}})
            if not self.csrf_valid(session) or length:
                return self.json_response(403, {"error": {"code": "request_rejected"}})
            self.gateway.store.revoke_session(self.session_token())
            return self.json_response(204, {}, {"Set-Cookie": self.cookie("", expire=True)})
        if path.startswith(("/api/v1/", "/api/v2/")):
            session = self.session()
            if not session:
                return self.json_response(401, {"error": {"code": "authentication_required"}})
            if self.command not in {"GET", "HEAD"} and not self.csrf_valid(session):
                return self.json_response(403, {"error": {"code": "request_rejected"}})
            return self.forward(length, session, api=True)
        if path.startswith(("/api", "/auth")):
            return self.json_response(404, {"error": {"code": "not_found"}})
        if self.command in {"GET", "HEAD"}:
            return self.forward(0, None, api=False)
        return self.json_response(404, {"error": {"code": "not_found"}})

    def handle_request(self):
        try:
            self.dispatch()
        except Exception:
            self.close_connection = True
            if not self.response_started:
                self.json_response(502, {"error": {"code": "upstream_unavailable"}})

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = handle_request
    do_OPTIONS = do_TRACE = do_CONNECT = handle_request


def create_server(config, *, store=None):
    """Construct an unstarted loopback server; callers may wrap its socket in TLS for tests."""
    host, port = config.get("listen_host", "127.0.0.1"), config.get("listen_port", 18002)
    if host != "127.0.0.1" or type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Session gateway must listen on literal host loopback")
    return GatewayServer((host, port), Gateway(config, store))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Serve the private loopback browser-session gateway"
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    server = None
    try:
        config = json.loads(args.config.read_bytes())
        server = create_server(config)
        signal.signal(
            signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start()
        )
        server.serve_forever()
        return 0
    except (OSError, ValueError, KeyError):
        print(json.dumps({"ok": False, "error": "session_gateway_unavailable"}))
        return 2
    finally:
        if server:
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
