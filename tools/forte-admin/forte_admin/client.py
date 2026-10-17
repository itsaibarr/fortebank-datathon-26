"""Origin-bound, streaming stdlib client for the verified Forte application API.

This module deliberately returns completed result dictionaries unchanged. Execution
status is not an assessment: ``done`` can contain insufficient evidence, and a
failed or unfamiliar response never becomes a clean verdict. No request follows
redirects, consults proxy environment variables, retries an upload, or fails over
to another processing location. TLS uses the system trust store (and Python's
standard SSL_CERT_FILE/SSL_CERT_DIR configuration for an administrator's CA).

``save_profile`` explicitly binds a key file to one canonical origin. Constructing
an APIClient is nonmutating; it validates an existing binding when present. The
CLI must use saved profiles. Direct library callers explicitly select the origin.
"""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import math
import os
import re
import secrets
import ssl
import stat
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

_CHUNK = 1024 * 1024
_MAX_BODY = 256 * 1024 * 1024
_MAX_RESPONSE = 64 * 1024 * 1024
_MESSAGES = {
    "invalid_endpoint": "Use an HTTPS origin, or HTTP on an explicit loopback host.",
    "invalid_api_version": "Select supported API version 1 or 2.",
    "invalid_timeout": "Timeout and poll interval must be positive finite numbers.",
    "invalid_key_file": "The API key file must be a private regular file with a valid key.",
    "invalid_gateway_credentials_file": (
        "Gateway credentials must be a private regular file containing ASCII username:password."
    ),
    "invalid_profile": "The connection profile or credential binding is invalid.",
    "profile_write_failed": "The private connection profile could not be saved.",
    "endpoint_mismatch": "This credential file is bound to a different application origin.",
    "invalid_upload": "Select a readable, nonempty regular MOV file.",
    "upload_too_large": "The multipart upload exceeds the application's 256 MiB limit.",
    "upload_changed": "The upload changed while being read; submission was not retried.",
    "invalid_job_id": "The job ID must be a UUID.",
    "transport_error": "The application could not be reached; the request was not retried.",
    "tls_error": "TLS verification failed; check the application certificate and trusted CA.",
    "request_timeout": "The application request timed out; an upload may already be admitted.",
    "redirect_refused": "The application redirected the request; credentials were not forwarded.",
    "http_error": "The application rejected the request; response content was withheld.",
    "invalid_response": "The application returned an invalid or oversized JSON response.",
    "unknown_job_status": "The application returned an unfamiliar execution status.",
    "job_mismatch": "The returned job ID differs from the requested job.",
    "poll_timeout": "Polling timed out; the job may still be processing at the same origin.",
}


class ClientError(Exception):
    """Sanitized diagnostic, with stable codes and no response or case content."""

    def __init__(self, code: str, *, status: int | None = None):
        self.code = code if code in _MESSAGES else "transport_error"
        self.status = status
        self.exit_code = (
            2
            if self.code
            in {
                "invalid_endpoint",
                "invalid_api_version",
                "invalid_timeout",
                "invalid_key_file",
                "invalid_gateway_credentials_file",
                "invalid_profile",
                "profile_write_failed",
                "endpoint_mismatch",
                "invalid_upload",
                "upload_too_large",
                "invalid_job_id",
            }
            else 3
        )
        if self.code in {"poll_timeout", "request_timeout"}:
            self.exit_code = 4
        super().__init__(_MESSAGES[self.code])

    def as_dict(self) -> dict[str, Any]:
        result = {"code": self.code, "message": str(self)}
        if self.status is not None:
            result["http_status"] = self.status
        return result


def _origin(endpoint: str) -> str:
    try:
        if not isinstance(endpoint, str) or not endpoint or any(c.isspace() for c in endpoint):
            raise ValueError
        if any(c in endpoint for c in ("?", "#", "\\", "%")):
            raise ValueError
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.path not in {"", "/"}:
            raise ValueError
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError
        # urlsplit otherwise tolerates junk after a closing IPv6 bracket.
        if parsed.netloc.startswith("["):
            closing = parsed.netloc.index("]")
            if not re.fullmatch(r"(?::[0-9]+)?", parsed.netloc[closing + 1 :]):
                raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
            if len(host) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                for part in host.split(".")
            ):
                raise ValueError from None
        if (
            parsed.scheme == "http"
            and host != "localhost"
            and not (address and address.is_loopback)
        ):
            raise ValueError
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        if parsed.netloc.endswith(":"):
            raise ValueError
        if address:
            host = address.compressed
        authority = f"[{host}]" if ":" in host else host
        if port is not None and port != (443 if parsed.scheme == "https" else 80):
            authority += f":{port}"
        return f"{parsed.scheme}://{authority}"
    except (ValueError, UnicodeError, AttributeError):
        raise ClientError("invalid_endpoint") from None


def _version(value: int) -> int:
    if type(value) is not int or value not in {1, 2}:
        raise ClientError("invalid_api_version")
    return value


def _seconds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClientError("invalid_timeout")
    if not math.isfinite(value) or value <= 0:
        raise ClientError("invalid_timeout")
    return float(value)


def _private_read(path: Path, *, limit: int, code: str) -> bytes:
    try:
        fd = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ValueError
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise ValueError
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError
            return data
    except (OSError, ValueError):
        raise ClientError(code) from None


def _key(path: Path) -> str:
    try:
        value = _private_read(path, limit=4096, code="invalid_key_file").decode("ascii").strip()
        if len(value) < 16 or not all(33 <= ord(char) <= 126 for char in value):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise ClientError("invalid_key_file") from None


def _gateway_auth(path: Path) -> str:
    """Read printable ASCII Basic credentials, allowing one terminal LF for file framing."""
    try:
        value = (
            _private_read(path, limit=4096, code="invalid_gateway_credentials_file")
            .decode("ascii")
            .removesuffix("\n")
        )
        username, separator, password = value.partition(":")
        if not separator or not username or not password:
            raise ValueError
        if not all(32 <= ord(char) <= 126 for char in value):
            raise ValueError
        return "Basic " + base64.b64encode(value.encode("ascii")).decode("ascii")
    except (ValueError, UnicodeError):
        raise ClientError("invalid_gateway_credentials_file") from None


def _binding_path(key_file: Path) -> Path:
    return key_file.with_name(key_file.name + ".forte-origin.json")


def _check_binding(key_file: Path, endpoint: str, *, required: bool = False) -> None:
    binding = _binding_path(key_file)
    if not binding.exists() and not binding.is_symlink():
        if required:
            raise ClientError("invalid_profile")
        return
    try:
        value = json.loads(_private_read(binding, limit=16384, code="invalid_profile"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError
        bound_origin = _origin(value.get("endpoint"))
    except (ValueError, TypeError, RecursionError, ClientError):
        raise ClientError("invalid_profile") from None
    if bound_origin != endpoint:
        raise ClientError("endpoint_mismatch")


def _bind(credential_file: Path, endpoint: str) -> None:
    binding = _binding_path(credential_file)
    try:
        fd = os.open(binding, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _check_binding(credential_file, endpoint, required=True)
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"schema_version": 1, "endpoint": endpoint}, stream)
            stream.flush()
            os.fsync(stream.fileno())


def save_profile(
    path: str | Path,
    endpoint: str,
    key_file: str | Path,
    api_version: int = 2,
    gateway_credentials_file: str | Path | None = None,
) -> dict[str, Any]:
    """Explicitly bind an existing private credential file and save a private profile.

    Secrets remain in their original file. Repeating this call preserves them.
    A different origin requires its own credential file; changing a profile never
    silently rebinds the original credential. Installation configuration is separate.
    """
    endpoint, api_version = _origin(endpoint), _version(api_version)
    key_file = Path(os.path.abspath(Path(key_file).expanduser()))
    _key(key_file)
    _check_binding(key_file, endpoint)
    credential_files = [key_file]
    if gateway_credentials_file is not None:
        gateway_credentials_file = Path(
            os.path.abspath(Path(gateway_credentials_file).expanduser())
        )
        _gateway_auth(gateway_credentials_file)
        _check_binding(gateway_credentials_file, endpoint)
        credential_files.append(gateway_credentials_file)
    value = {
        "schema_version": 1,
        "endpoint": endpoint,
        "key_file": str(key_file),
        "api_version": api_version,
    }
    if gateway_credentials_file is not None:
        value["gateway_credentials_file"] = str(gateway_credentials_file)
    path = Path(os.path.abspath(Path(path).expanduser()))
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        for credential_file in credential_files:
            _bind(credential_file, endpoint)
        protected = credential_files + [_binding_path(file) for file in credential_files]
        if (
            path in protected
            or path.is_symlink()
            or (path.exists() and any(path.samefile(file) for file in protected))
        ):
            raise ValueError
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except ClientError:
        raise
    except (OSError, ValueError):
        raise ClientError("profile_write_failed") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return value


def load_profile(path: str | Path) -> dict[str, Any]:
    """Read and validate a saved profile without returning credential contents."""
    try:
        value = json.loads(
            _private_read(Path(path).expanduser(), limit=16384, code="invalid_profile")
        )
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError
        endpoint, version = _origin(value["endpoint"]), _version(value["api_version"])
        key_file = Path(value["key_file"])
        if not key_file.is_absolute():
            raise ValueError
        _key(key_file)
        _check_binding(key_file, endpoint, required=True)
        result = {
            "schema_version": 1,
            "endpoint": endpoint,
            "key_file": str(key_file),
            "api_version": version,
        }
        if value.get("gateway_credentials_file") is not None:
            gateway_credentials_file = Path(value["gateway_credentials_file"])
            if not gateway_credentials_file.is_absolute():
                raise ValueError
            _gateway_auth(gateway_credentials_file)
            _check_binding(gateway_credentials_file, endpoint, required=True)
            result["gateway_credentials_file"] = str(gateway_credentials_file)
        return result
    except ClientError:
        raise
    except (KeyError, TypeError, ValueError, RecursionError):
        raise ClientError("invalid_profile") from None


class APIClient:
    """One explicit processing destination; no implicit submission or failover."""

    def __init__(
        self,
        endpoint: str,
        key_file: str | Path,
        api_version: int = 2,
        timeout: float = 30,
        gateway_credentials_file: str | Path | None = None,
    ):
        self.endpoint = _origin(endpoint)
        self.api_version = _version(api_version)
        self.timeout = _seconds(timeout)
        self.key_file = Path(os.path.abspath(Path(key_file).expanduser()))
        _key(self.key_file)
        _check_binding(self.key_file, self.endpoint)
        self.gateway_credentials_file = None
        if gateway_credentials_file is not None:
            self.gateway_credentials_file = Path(
                os.path.abspath(Path(gateway_credentials_file).expanduser())
            )
            _gateway_auth(self.gateway_credentials_file)
            _check_binding(self.gateway_credentials_file, self.endpoint)

    def _request(self, method: str, path: str, *, upload=None, timeout=None) -> dict[str, Any]:
        # Read again so credential rotation works without retaining a secret on the object.
        _check_binding(self.key_file, self.endpoint)
        key = _key(self.key_file)
        gateway_authorization = None
        if self.gateway_credentials_file is not None:
            _check_binding(self.gateway_credentials_file, self.endpoint)
            gateway_authorization = _gateway_auth(self.gateway_credentials_file)
        parsed = urlsplit(self.endpoint)
        duration = self.timeout if timeout is None else min(self.timeout, _seconds(timeout))
        deadline = time.monotonic() + duration
        connection = None

        def budget():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClientError("request_timeout")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            return remaining

        try:
            kind = (
                http.client.HTTPSConnection
                if parsed.scheme == "https"
                else http.client.HTTPConnection
            )
            connection = kind(parsed.hostname, parsed.port, timeout=duration)
            connection.connect()
            budget()
            connection.putrequest(method, path, skip_accept_encoding=True)
            connection.putheader("X-API-Key", key)
            if gateway_authorization is not None:
                connection.putheader("Authorization", gateway_authorization)
            connection.putheader("Accept", "application/json")
            connection.putheader("Connection", "close")
            if upload is not None:
                stream, size = upload
                original = os.fstat(stream.fileno())
                boundary = "forte-" + secrets.token_hex(24)
                prefix = (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="file"; filename="input.mov"\r\n'
                    "Content-Type: video/quicktime\r\n\r\n"
                ).encode("ascii")
                suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
                total = len(prefix) + size + len(suffix)
                if total > _MAX_BODY:
                    raise ClientError("upload_too_large")
                connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
                connection.putheader("Content-Length", str(total))
            connection.endheaders()
            if upload is not None:
                budget()
                connection.send(prefix)
                remaining = size
                while remaining:
                    data = stream.read(min(_CHUNK, remaining))
                    if not data:
                        raise ClientError("upload_changed")
                    budget()
                    connection.send(data)
                    remaining -= len(data)
                final = os.fstat(stream.fileno())
                if stream.read(1) or (final.st_size, final.st_mtime_ns) != (
                    size,
                    original.st_mtime_ns,
                ):
                    raise ClientError("upload_changed")
                budget()
                connection.send(suffix)
            budget()
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise ClientError("redirect_refused", status=response.status)
            expected = 202 if method == "POST" else 200
            if response.status != expected:
                raise ClientError("http_error", status=response.status)
            media_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                raise ClientError("invalid_response")
            output = bytearray()
            while True:
                budget()
                chunk = response.read1(min(65536, _MAX_RESPONSE + 1 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > _MAX_RESPONSE:
                    raise ClientError("invalid_response")
            try:
                value = json.loads(output)
            except (ValueError, UnicodeError, RecursionError):
                raise ClientError("invalid_response") from None
            if not isinstance(value, dict):
                raise ClientError("invalid_response")
            return value
        except ClientError:
            raise
        except TimeoutError:
            raise ClientError("request_timeout") from None
        except ssl.SSLError:
            raise ClientError("tls_error") from None
        except (OSError, http.client.HTTPException, ValueError):
            raise ClientError("transport_error") from None
        finally:
            if connection is not None:
                connection.close()

    def health(self) -> dict[str, Any]:
        """Check actual inference readiness, not merely HTTP liveness."""
        value = self._request("GET", "/health/ready")
        if value.get("status") != "ready":
            raise ClientError("invalid_response")
        return value

    def upload(self, path: str | Path) -> dict[str, Any]:
        """Submit once, streaming a MOV; the server validates actual media constraints."""
        path = Path(path).expanduser()
        if path.suffix.lower() != ".mov":
            raise ClientError("invalid_upload")
        try:
            stream = os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb")
        except OSError:
            raise ClientError("invalid_upload") from None
        with stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                raise ClientError("invalid_upload")
            if info.st_size >= _MAX_BODY:
                raise ClientError("upload_too_large")
            value = self._request(
                "POST", f"/api/v{self.api_version}/analyze", upload=(stream, info.st_size)
            )
        self._job_id(value.get("job_id"), response=True)
        return value

    @staticmethod
    def _job_id(value, *, response=False) -> str:
        try:
            if not isinstance(value, str):
                raise ValueError
            return str(UUID(value))
        except ValueError:
            raise ClientError("invalid_response" if response else "invalid_job_id") from None

    def _job(self, job_id: str, *, timeout=None) -> dict[str, Any]:
        identifier = self._job_id(job_id)
        value = self._request("GET", f"/api/v{self.api_version}/jobs/{identifier}", timeout=timeout)
        if self._job_id(value.get("job_id"), response=True) != identifier:
            raise ClientError("job_mismatch")
        status = value.get("status")
        if not isinstance(status, str) or status not in {"processing", "done", "failed"}:
            raise ClientError("unknown_job_status")
        if status == "done":
            if self.api_version == 2:
                if not isinstance(value.get("result"), dict):
                    raise ClientError("invalid_response")
            elif value.get("verdict") not in {"violation", "no_violation"} or not isinstance(
                value.get("violations"), list
            ):
                raise ClientError("invalid_response")
        if status == "failed" and not isinstance(value.get("error"), dict):
            raise ClientError("invalid_response")
        return value

    def job(self, job_id: str) -> dict[str, Any]:
        return self._job(job_id)

    def wait(self, job_id: str, timeout: float = 300, poll_interval: float = 1) -> dict[str, Any]:
        """Return the actual terminal response; failed jobs remain failed dictionaries."""
        timeout, poll_interval = _seconds(timeout), _seconds(poll_interval)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClientError("poll_timeout")
            value = self._job(job_id, timeout=remaining)
            if value["status"] != "processing":
                return value
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClientError("poll_timeout")
            time.sleep(min(poll_interval, remaining))
