#!/usr/bin/env python3
"""Installer-owned loopback bridge into port 8000 of a network-none container.

Streams bytes without HTTP parsing, payload logging, buffering an entire upload,
or exposing the model port. Adapted from the existing offline bridge mechanism.
"""

import argparse
import json
import os
import re
import signal
import socket
import socketserver
import subprocess
import threading
from pathlib import Path

RELAY = r"""
import os, selectors, socket
s = socket.create_connection(('127.0.0.1', 8000), timeout=10)
s.settimeout(330)
poll = selectors.DefaultSelector()
poll.register(0, selectors.EVENT_READ, 'input')
poll.register(s, selectors.EVENT_READ, 'socket')
try:
    while True:
        events = poll.select(330)
        if not events:
            break
        for key, _ in events:
            if key.data == 'input':
                data = os.read(0, 65536)
                if data:
                    s.sendall(data)
                else:
                    poll.unregister(0)
                    s.shutdown(socket.SHUT_WR)
            else:
                data = s.recv(65536)
                if not data:
                    raise SystemExit(0)
                view = memoryview(data)
                while view:
                    view = view[os.write(1, view):]
finally:
    s.close()
"""


def relay_connection(client, command, *, spawn=subprocess.Popen):
    """Bound memory for both directions, including binary uploads and ranges."""
    process = spawn(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
    )
    client.settimeout(330)

    def upload():
        try:
            while data := client.recv(65536):
                view = memoryview(data)
                while view:
                    view = view[os.write(process.stdin.fileno(), view) :]
        except (OSError, ValueError):
            pass
        finally:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass

    thread = threading.Thread(target=upload, daemon=True)
    thread.start()
    try:
        while data := process.stdout.read(65536):
            client.sendall(data)
    except (OSError, ValueError):
        pass
    finally:
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        thread.join(timeout=2)
        process.stdout.close()
        client.close()


class Bridge(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, container, port):
        if not re.fullmatch(r"[0-9a-f]{12,64}", container):
            raise ValueError("Expected a verified Docker container ID")
        self.command = ["docker", "exec", "-i", container, "python3", "-u", "-c", RELAY]
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", port), Handler)
        self.timeout = 1

    def handle_error(self, request, client_address):
        pass  # No URLs, headers, bodies, addresses or exception details in logs.


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            relay_connection(self.request, self.server.command)
        finally:
            self.server.slots.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not re.fullmatch(r"[0-9a-f]{32}", args.token):
        raise SystemExit(2)
    stopping = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stopping.set())
    with Bridge(args.container, args.port) as server:
        # Exclusive creation refuses to claim a different installation's bridge.
        descriptor = os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        state = {
            "pid": os.getpid(),
            "token": args.token,
            "container": args.container,
            "port": args.port,
        }
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream)
        try:
            while not stopping.is_set():
                server.handle_request()
        finally:
            args.state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
