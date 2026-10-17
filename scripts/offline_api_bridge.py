#!/usr/bin/env python3
"""Expose only the offline container's application API to host loopback.

No Docker networking changes, HTTP inspection, credentials, or request logging.
The fixed destination is app port 8000, never the model port. Use an SSH tunnel
to host loopback for a human browser; do not expose this listener publicly.
"""

import argparse
import os
import re
import signal
import socket
import socketserver
import subprocess
import threading

BIND = ("127.0.0.1", 18000)
MAX_CONNECTIONS = 16
IDLE_SECONDS = 120

# Executed inside the existing --network none container. A bounded os.read/write
# loop preserves binary bodies, header bytes, streaming, and TCP half-closes.
CONTAINER_RELAY = r"""
import os, selectors, socket
s = socket.create_connection(('127.0.0.1', 8000), timeout=10)
s.settimeout(120)
poll = selectors.DefaultSelector()
poll.register(0, selectors.EVENT_READ, 'input')
poll.register(s, selectors.EVENT_READ, 'socket')
try:
    while True:
        events = poll.select(120)
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


def container_name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise argparse.ArgumentTypeError("Expected a Docker container name or ID")
    return value


def docker_command(container):
    container_name(container)
    return ["docker", "exec", "-i", container, "python3", "-u", "-c", CONTAINER_RELAY]


def relay_connection(client, command, *, spawn=subprocess.Popen):
    """Stream one TCP connection through stdio; never decode or log payloads."""
    process = spawn(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
    )
    client.settimeout(IDLE_SECONDS)

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
            except OSError:
                pass

    writer = threading.Thread(target=upload, daemon=True)
    writer.start()
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
        writer.join(timeout=2)
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()
        client.close()


class LoopbackBridge(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, container):
        self.command = docker_command(container)
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(BIND, BridgeHandler)
        self.timeout = 1

    def verify_request(self, request, client_address):
        return client_address[0] == "127.0.0.1"

    def handle_error(self, request, client_address):
        # No exception text, URLs, headers, bodies or client addresses in logs.
        pass


class BridgeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            relay_connection(self.request, self.server.command)
        finally:
            self.server.slots.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("container", type=container_name)
    args = parser.parse_args()
    stopping = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stopping.set())
    with LoopbackBridge(args.container) as server:
        print("Offline application bridge listening at http://127.0.0.1:18000", flush=True)
        while not stopping.is_set():
            server.handle_request()


if __name__ == "__main__":
    main()
