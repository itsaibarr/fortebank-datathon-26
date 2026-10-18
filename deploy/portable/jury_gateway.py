"""Unactivated, loopback-only jury-key boundary for the exact legacy v1 transport.

Browser sessions remain a separate gateway. This component never implements v1
model dispatch or approves uploads, quality, installation, or publication.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import hmac
import http.client
import json
import os
import re
import signal
import socket
import stat
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

# Only the shipped repository-relative session transport is imported. No discovery,
# configured plugin location, package download, or session database is involved.
SESSION_SOURCE = Path(__file__).resolve().parents[2] / "tools" / "forte-session"
sys.path.insert(0, str(SESSION_SOURCE))
from session_gateway import (  # noqa: E402
    HEADER_NAME,
    LIMITS,
    RESPONSE_HEADERS,
    SENSITIVE,
    Gateway,
    GatewayHandler,
    GatewayServer,
    Unavailable,
    _length,
)

SCHEMA = "forte.jury-keys/1"
KEY = re.compile(r"[A-Za-z0-9_-]{43,128}")
HASH = re.compile(r"[0-9a-f]{64}")
PRINCIPAL = re.compile(r"jury_[0-9a-f]{32}")
JOB = re.compile(r"/api/v1/jobs/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def private_bytes(value, maximum):
    """Read a bounded owner-private regular file through pinned, no-follow FDs."""
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw.startswith("/") or "\x00" in raw:
        raise ValueError("Use canonical absolute private file paths")
    parts = raw.split("/")[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Use canonical absolute private file paths")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    descriptor = None
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_mode & 0o077
            or before.st_nlink != 1
            or not 0 < before.st_size <= maximum
        ):
            raise ValueError("Invalid owner-private regular file")
        data = bytearray()
        while len(data) <= maximum:
            block = os.read(descriptor, maximum + 1 - len(data))
            if not block:
                break
            data.extend(block)
        after = os.fstat(descriptor)
        attributes = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(data) != before.st_size or any(
            getattr(before, name) != getattr(after, name) for name in attributes
        ):
            raise ValueError("Private file changed during read")
        return bytes(data)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def secret(path, minimum):
    value = private_bytes(path, 1024).decode("ascii").strip()
    if not minimum <= len(value) <= 256 or not all(33 <= ord(char) <= 126 for char in value):
        raise ValueError("Invalid credential file")
    return value


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


class JuryGateway(Gateway):
    def __init__(self, config):
        allowed = {
            "origin",
            "upstream",
            "listen_host",
            "listen_port",
            "service_key_file",
            "gateway_token_file",
            "jury_keys_file",
            "jury_uploads_enabled",
            "limits",
        }
        if not isinstance(config, dict) or set(config) - allowed:
            raise ValueError("Invalid jury gateway configuration")
        if any(not isinstance(config.get(name), str) for name in ("origin", "upstream")):
            raise ValueError("Origin and upstream must be literal strings")
        origin, upstream = urlsplit(config["origin"]), urlsplit(config["upstream"])
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
            or not origin.netloc.isascii()
            or not 1 <= (origin.port or 443) <= 65535
        ):
            raise ValueError("Configure one exact HTTPS origin without a path")
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
            raise ValueError("Core upstream must be literal loopback, excluding the model port")
        self.origin, self.authority = config["origin"], origin.netloc
        self.upstream = (upstream.hostname, upstream.port)
        self.service_key = secret(config["service_key_file"], 16)
        self.gateway_token = secret(config["gateway_token_file"], 32)
        if hmac.compare_digest(self.service_key, self.gateway_token):
            raise ValueError("Service and gateway credentials must differ")
        self.keys_file = config["jury_keys_file"]
        self.forbidden_hashes = {
            hashlib.sha256(value.encode("ascii")).hexdigest()
            for value in (self.service_key, self.gateway_token)
        }
        self.bindings = {}
        self.keys_lock = threading.Lock()
        self.load_keys()
        if not isinstance(config.get("limits", {}), dict):
            raise ValueError("Limits must be a mapping")
        self.limits = LIMITS | config.get("limits", {})
        if set(self.limits) != set(LIMITS) or any(
            type(value) is not int or not 0 < value <= LIMITS[name]
            for name, value in self.limits.items()
        ):
            raise ValueError("Jury limits must be positive and cannot exceed core bounds")
        if type(config.get("jury_uploads_enabled", False)) is not bool:
            raise ValueError("Jury upload activation must be an explicit boolean")
        self.uploads = config.get("jury_uploads_enabled", False)

    def load_keys(self):
        with self.keys_lock:
            value = json.loads(
                private_bytes(self.keys_file, 65536), object_pairs_hook=unique_object
            )
            if (
                not isinstance(value, dict)
                or set(value) != {"schema_version", "keys"}
                or value["schema_version"] != SCHEMA
                or not isinstance(value["keys"], list)
                or not 1 <= len(value["keys"]) <= 64
            ):
                raise ValueError("Invalid jury credential inventory")
            keys, principals = {}, set()
            for item in value["keys"]:
                if (
                    not isinstance(item, dict)
                    or set(item) != {"key_sha256", "principal", "enabled"}
                    or not isinstance(item["key_sha256"], str)
                    or HASH.fullmatch(item["key_sha256"]) is None
                    or not isinstance(item["principal"], str)
                    or PRINCIPAL.fullmatch(item["principal"]) is None
                    or type(item["enabled"]) is not bool
                    or item["key_sha256"] in keys
                    or item["principal"] in principals
                    or item["key_sha256"] in self.forbidden_hashes
                    or self.bindings.get(item["key_sha256"], item["principal"]) != item["principal"]
                ):
                    raise ValueError("Invalid or changed jury credential identity")
                keys[item["key_sha256"]] = (item["principal"], item["enabled"])
                principals.add(item["principal"])
            self.bindings.update({key: identity[0] for key, identity in keys.items()})
            return keys

    def jury_ready_on(self, connection, original):
        self.same_socket(connection, original)
        connection.request("GET", "/health/ready")
        response = connection.getresponse()
        size = _length(response.headers)
        if (
            response.will_close
            or size is None
            or size > 4096
            or response.headers.get_all("Transfer-Encoding")
        ):
            raise Unavailable
        raw = response.read(4097)
        if len(raw) != size:
            raise Unavailable
        value = json.loads(raw, object_pairs_hook=unique_object)
        self.same_socket(connection, original)
        if response.status == 200 and value == {"status": "ready"}:
            return True
        if (
            response.status == 503
            and response.headers.get_all("Retry-After") == ["5"]
            and value
            == {"error": {"code": "model_not_ready", "message": "The local model is not ready."}}
        ):
            return False
        raise Unavailable

    def authenticate(self, credential):
        keys = self.load_keys()  # Revocation is effective on the next admitted request.
        if not isinstance(credential, str) or KEY.fullmatch(credential) is None:
            return None
        digest = hashlib.sha256(credential.encode("ascii")).hexdigest()
        principal = None
        for known, (identity, enabled) in keys.items():
            if hmac.compare_digest(digest, known) and enabled:
                principal = identity
        return principal


def shutdown_socket(connection, how):
    try:
        connection.shutdown(how)
    except OSError:
        pass


class UploadPump:
    """One bounded uploader while the handler reads the same socket's response.

    The uploader only uses the already checked socket's sendall: it cannot ask
    HTTPConnection to reconnect. Response parsing stays in the handler thread.
    Shutdown of these request-owned socket halves wakes an idle reader or writer.
    """

    def __init__(self, handler, upstream, length, timeout):
        self.handler, self.upstream, self.length = handler, upstream, length
        self.deadline = time.monotonic() + timeout
        self.stop = threading.Event()
        self.done = threading.Event()
        self.failed = False
        self.sent = 0
        self.worker = threading.Thread(target=self.run, name="forte-jury-upload", daemon=True)
        self.timer = threading.Timer(timeout, self.abort)
        self.timer.name = "forte-jury-upload-deadline"
        self.timer.daemon = True

    def start(self):
        self.timer.start()
        self.worker.start()

    def abort(self):
        if not self.done.is_set() and not self.stop.is_set():
            self.failed = True
            self.stop.set()
            shutdown_socket(self.handler.connection, socket.SHUT_RD)
            shutdown_socket(self.upstream, socket.SHUT_RDWR)

    def run(self):
        try:
            while self.sent < self.length and not self.stop.is_set():
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                self.handler.connection.settimeout(remaining)
                block = self.handler.rfile.read1(min(65536, self.length - self.sent))
                if self.stop.is_set():
                    break
                if not block or time.monotonic() >= self.deadline:
                    raise ValueError
                self.upstream.sendall(block)
                self.sent += len(block)
                if time.monotonic() >= self.deadline:
                    raise TimeoutError
        except Exception:
            if not self.stop.is_set():
                self.failed = True
                self.stop.set()
                shutdown_socket(self.upstream, socket.SHUT_RDWR)
        finally:
            self.done.set()
            self.timer.cancel()

    def close(self):
        self.stop.set()
        self.timer.cancel()
        if not self.done.is_set():
            shutdown_socket(self.handler.connection, socket.SHUT_RD)
            shutdown_socket(self.upstream, socket.SHUT_WR)
        if self.worker.ident is not None:
            self.worker.join(1)
        if self.timer.ident is not None:
            self.timer.join(1)
        if self.worker.is_alive() or self.timer.is_alive():
            shutdown_socket(self.upstream, socket.SHUT_RDWR)
            shutdown_socket(self.handler.connection, socket.SHUT_RD)
            if self.worker.ident is not None:
                self.worker.join(1)
            if self.timer.ident is not None:
                self.timer.join(1)
            if self.worker.is_alive() or self.timer.is_alive():
                raise Unavailable


class JuryHandler(GatewayHandler):
    server_version = "ForteJury"

    def forward_jury(self, length, principal):
        # Derived from the frozen session transport, with v1-specific response
        # validation. Shared browser helper globals and behavior are untouched.
        upload = self.command == "POST"
        if length > self.gateway.limits["upload_max_bytes"]:
            return self.json_response(413, {"error": {"code": "request_too_large"}})
        if upload and not self.gateway.uploads:
            return self.json_response(403, {"error": {"code": "uploads_disabled"}})
        connection, original = self.gateway.checked_connection(principal)
        pump = response = watchdog = None
        try:
            if upload and not self.gateway.jury_ready_on(connection, original):
                return self.json_response(
                    503,
                    {
                        "error": {
                            "code": "model_not_ready",
                            "message": "The local model is not ready.",
                        }
                    },
                    {"Retry-After": "5"},
                )
            self.gateway.same_socket(connection, original)
            connection.putrequest(self.command, self.path, skip_accept_encoding=True)
            for key, value in self.headers.items():
                if key.lower() in {"content-type", "accept"}:
                    connection.putheader(key, value)
            for key, value in self.gateway._auth(principal).items():
                connection.putheader(key, value)
            connection.putheader("Accept-Encoding", "identity")
            if upload:
                connection.putheader("Content-Length", str(length))
            connection.endheaders()
            deadline = time.monotonic() + self.gateway.limits["job_timeout_seconds"]
            original.settimeout(self.gateway.limits["job_timeout_seconds"])

            def expire_response():
                # Closing the checked request socket bounds header parsing too;
                # an idle or trickling upstream cannot reset this absolute timer.
                shutdown_socket(original, socket.SHUT_RDWR)
                if pump is not None:
                    pump.stop.set()
                    shutdown_socket(self.connection, socket.SHUT_RD)

            watchdog = threading.Timer(self.gateway.limits["job_timeout_seconds"], expire_response)
            watchdog.name = "forte-jury-response-deadline"
            watchdog.daemon = True
            watchdog.start()
            if upload:
                pump = UploadPump(
                    self, original, length, self.gateway.limits["upload_timeout_seconds"]
                )
                pump.start()
            # HTTPResponse parses only the already checked socket. Direct use
            # avoids HTTPConnection's response-driven close racing the uploader.
            response = http.client.HTTPResponse(original, method=self.command)
            response.begin()
            if pump is not None:
                pump.close()  # Early final response stops even a headers-only client.
                if response.status < 400 and (pump.failed or pump.sent != length):
                    raise Unavailable
            headers = response.headers
            counts = collections.Counter(key.lower() for key in headers)
            if (
                any(
                    counts[key] > 1
                    for key in SENSITIVE | RESPONSE_HEADERS | {"location", "retry-after"}
                )
                or any(
                    HEADER_NAME.fullmatch(key) is None
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)
                    for key, value in headers.items()
                )
                or sum(len(key) + len(value) + 4 for key, value in headers.items()) > 16384
                or 300 <= response.status < 400
                or headers.get_all("X-Forte-Ownership-Mode") != ["principal-v1"]
                or headers.get_all("Transfer-Encoding")
            ):
                raise Unavailable
            size = _length(headers)
            maximum = self.gateway.limits["upload_max_bytes"] + 16 * 1024**2
            if size is None or size > maximum:
                raise Unavailable
            location, retry = headers.get_all("Location", []), headers.get_all("Retry-After", [])
            accepted = upload and response.status == 202
            if (location and not accepted) or (
                retry and (response.status not in {429, 503} or retry != ["5"])
            ):
                raise Unavailable
            if response.status in {429, 503} and retry != ["5"]:
                raise Unavailable
            if accepted and (
                len(location) != 1 or JOB.fullmatch(location[0]) is None or size > 4096
            ):
                raise Unavailable

            def blocks():
                copied = 0
                while copied < size:
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        raise TimeoutError
                    if connection.sock is not None:
                        connection.sock.settimeout(timeout)
                    block = response.read1(min(65536, size - copied))
                    if not block:
                        raise Unavailable
                    copied += len(block)
                    yield block

            buffered = None
            if accepted:
                buffered = b"".join(blocks())
                value = json.loads(buffered, object_pairs_hook=unique_object)
                if (
                    not isinstance(value, dict)
                    or set(value) != {"job_id"}
                    or not isinstance(value["job_id"], str)
                    or location != ["/api/v1/jobs/" + str(value["job_id"])]
                ):
                    raise Unavailable
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise TimeoutError
            self.connection.settimeout(timeout)
            self.send_response(response.status)
            self.response_started = True
            for key, value in headers.items():
                if key.lower() in RESPONSE_HEADERS | {"location", "retry-after"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if buffered is not None:
                self.wfile.write(buffered)
            else:
                for block in blocks():
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        raise TimeoutError
                    self.connection.settimeout(timeout)
                    self.wfile.write(block)
        finally:
            try:
                if pump is not None:
                    pump.close()
            finally:
                if watchdog is not None:
                    watchdog.cancel()
                    if watchdog.ident is not None:
                        watchdog.join(1)
                if response is not None:
                    response.close()
                connection.close()

    def dispatch(self):
        try:
            # BaseHTTPRequestHandler folds an initial // before dispatch. Reject
            # normalization rather than accidentally admitting another target.
            if self.requestline.split()[1] != self.path:
                raise ValueError
            path, length = self.validated_request()
            if "?" in self.path or any(
                self.headers.get_all(name)
                for name in ("Cookie", "X-CSRF-Token", "Origin", "Range", "If-Range")
            ):
                raise ValueError
        except (ValueError, Unavailable):
            return self.json_response(400, {"error": {"code": "request_rejected"}})
        job_path = re.fullmatch(r"/api/v1/jobs/[^/]+", path) is not None
        method = "POST" if path == "/api/v1/analyze" else "GET" if job_path else None
        if method is None:
            return self.json_response(404, {"error": {"code": "not_found"}})
        try:
            principal = self.gateway.authenticate(self.headers.get("X-API-Key"))
        except (OSError, ValueError, UnicodeError, TypeError, KeyError):
            return self.json_response(
                503, {"error": {"code": "jury_access_unavailable"}}, {"Retry-After": "5"}
            )
        if principal is None:
            return self.json_response(401, {"error": {"code": "authentication_required"}})
        if self.command != method:
            return self.json_response(405, {"error": {"code": "method_not_allowed"}})
        if job_path and JOB.fullmatch(path) is None:
            return self.json_response(
                422,
                {
                    "error": {
                        "code": "invalid_request",
                        "message": "Invalid request fields or job ID.",
                    }
                },
            )
        if method == "POST" and not self.headers.get_all("Content-Length"):
            return self.json_response(411, {"error": {"code": "request_rejected"}})
        return self.forward_jury(length, principal)


class JuryServer(GatewayServer):
    def __init__(self, address, gateway):
        # Inherit the bounded thread admission and silent error handling unchanged.
        super().__init__(address, gateway)
        self.RequestHandlerClass = JuryHandler


def create_server(config):
    if not isinstance(config, dict):
        raise ValueError("Invalid jury gateway configuration")
    host, port = config.get("listen_host", "127.0.0.1"), config.get("listen_port", 18003)
    if host != "127.0.0.1" or type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Jury listener must bind literal host loopback")
    return JuryServer((host, port), JuryGateway(config))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve the unactivated loopback jury-v1 boundary")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    server = None
    try:
        config = json.loads(private_bytes(args.config, 65536), object_pairs_hook=unique_object)
        server = create_server(config)
        signal.signal(
            signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start()
        )
        server.serve_forever()
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"ok": False, "error": "jury_gateway_unavailable"}))
        return 2
    finally:
        if server:
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
