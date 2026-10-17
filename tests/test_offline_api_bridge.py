"""Synthetic raw transport checks; no Docker or private input required."""

import argparse
import importlib.util
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "offline_api_bridge", Path(__file__).resolve().parents[1] / "scripts/offline_api_bridge.py"
)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def test_fixed_loopback_only_app_command_and_container_validation():
    assert bridge.BIND == ("127.0.0.1", 18000)
    command = bridge.docker_command("forte-app-1")
    assert command[:6] == ["docker", "exec", "-i", "forte-app-1", "python3", "-u"]
    assert "('127.0.0.1', 8000)" in command[-1]
    assert "8001" not in command[-1]
    for invalid in ["--privileged", "container;pwd", "a/b", "$(id)", ""]:
        with pytest.raises(argparse.ArgumentTypeError):
            bridge.docker_command(invalid)


def test_binary_http_headers_body_and_half_close_are_preserved_without_logs(capsys):
    client, relay = socket.socketpair()
    payload = (
        b"POST /upload HTTP/1.1\r\nX-API-Key: synthetic-private-canary\r\n\r\n"
        + bytes(range(256)) * 600
    )
    # A fake docker command returns the input byte-for-byte only after stdin EOF.
    command = [
        sys.executable,
        "-u",
        "-c",
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); sys.stdout.buffer.flush()",
    ]
    task = threading.Thread(target=bridge.relay_connection, args=(relay, command))
    task.start()
    client.settimeout(5)
    sender = threading.Thread(
        target=lambda: (client.sendall(payload), client.shutdown(socket.SHUT_WR))
    )
    sender.start()
    chunks = []
    while block := client.recv(65536):
        chunks.append(block)
    task.join(timeout=5)
    sender.join(timeout=5)
    client.close()
    relay.close()
    assert not task.is_alive()
    assert b"".join(chunks) == payload
    assert "synthetic-private-canary" not in capsys.readouterr().out
    assert bridge.subprocess is subprocess


def test_http_response_streams_before_client_stdin_eof():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    response = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\n\x00\xffabc"
    observed = []

    def application():
        with listener.accept()[0] as connection:
            request = b""
            while b"\r\n\r\n" not in request:
                request += connection.recv(4096)
            observed.append(request)
            connection.sendall(response)
        listener.close()

    server = threading.Thread(target=application)
    server.start()
    client, relay = socket.socketpair()
    # Substitute only the synthetic destination port; production has no target flag.
    command = [sys.executable, "-u", "-c", bridge.CONTAINER_RELAY.replace("8000", str(port))]
    task = threading.Thread(target=bridge.relay_connection, args=(relay, command))
    task.start()
    client.settimeout(5)
    client.sendall(b"GET /health/live HTTP/1.1\r\nHost: local\r\nX-API-Key: synthetic\r\n\r\n")
    received = b""
    while block := client.recv(4096):
        received += block
    client.close()
    task.join(timeout=5)
    server.join(timeout=5)
    assert received == response and b"X-API-Key: synthetic" in observed[0]
    assert not task.is_alive() and not server.is_alive()
