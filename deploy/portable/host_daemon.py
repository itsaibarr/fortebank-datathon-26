"""Own one loopback host helper by PID, process start time and private token."""

import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path


def _process(pid):
    root = Path("/proc") / str(pid)
    stat = (root / "stat").read_text()
    # The command name may contain spaces or parentheses; fields start after its last ')'.
    fields = stat.rsplit(")", 1)[1].split()
    if fields[0] == "Z":
        raise FileNotFoundError
    started = fields[19]
    command = (root / "cmdline").read_bytes().split(b"\0")
    environment = (root / "environ").read_bytes().split(b"\0")
    return started, command, environment


def _owned(state):
    started, command, environment = _process(state["pid"])
    expected = [state["script"].encode(), b"--config", state["config"].encode()]
    token = ("FORTE_DAEMON_OWNER=" + state["owner_token"]).encode()
    return (
        started == state["started"]
        and all(item in command for item in expected)
        and token in environment
    )


def _read(path):
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise RuntimeError("Host helper state is not private; no process was changed")
    try:
        state = json.loads(path.read_text())
    except ValueError:
        raise RuntimeError("Host helper identity is invalid; no process was changed") from None
    if not isinstance(state, dict) or type(state.get("pid")) is not int or state["pid"] <= 1:
        raise RuntimeError("Host helper identity is invalid; no process was changed")
    if any(
        not isinstance(state.get(key), str)
        for key in ("started", "script", "config", "owner_token", "config_sha256")
    ):
        raise RuntimeError("Host helper identity is invalid; no process was changed")
    if (
        not state["started"].isdigit()
        or not re.fullmatch(r"[0-9a-f]{48}", state["owner_token"])
        or not re.fullmatch(r"[0-9a-f]{64}", state["config_sha256"])
    ):
        raise RuntimeError("Host helper identity is invalid; no process was changed")
    return state


def start(script, config, state_path):
    script, config, state_path = (Path(item).absolute() for item in (script, config, state_path))
    if (
        not script.is_file()
        or script.is_symlink()
        or not config.is_file()
        or config.is_symlink()
        or config.stat().st_uid != os.getuid()
        or config.stat().st_mode & 0o077
    ):
        raise RuntimeError("Accepted host helper or private configuration is unavailable")
    if state_path.exists():
        state = _read(state_path)
        try:
            if not _owned(state):
                raise RuntimeError("Host helper identity differs; no process was changed")
            if state["script"] != str(script) or state["config"] != str(config):
                raise RuntimeError("Host helper belongs to another profile; no process was changed")
            if state["config_sha256"] != hashlib.sha256(config.read_bytes()).hexdigest():
                raise RuntimeError(
                    "Host helper configuration changed; stop this installation "
                    "before applying changes"
                )
            return {"started": False, "already_running": True}
        except FileNotFoundError:
            state_path.unlink()
    token = secrets.token_hex(24)
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONUNBUFFERED": "1",
        "FORTE_DAEMON_OWNER": token,
    }
    process = subprocess.Popen(
        [sys.executable, str(script), "--config", str(config)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        start_new_session=True,
    )
    try:
        started, _, _ = _process(process.pid)
        if process.poll() is not None:
            raise RuntimeError("Owned host helper exited during startup")
        state = {
            "pid": process.pid,
            "started": started,
            "script": str(script),
            "config": str(config),
            "owner_token": token,
            "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        }
        descriptor = os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(state, output)
            output.write("\n")
        return {"started": True, "already_running": False}
    except BaseException:
        if process.poll() is None:
            process.terminate()
        raise


def stop(state_path):
    path = Path(state_path).absolute()
    if not path.exists():
        return {"stopped": True}
    state = _read(path)
    try:
        if not _owned(state):
            raise RuntimeError("Host helper identity could not be verified; no signal sent")
        os.kill(state["pid"], signal.SIGTERM)
    except FileNotFoundError:
        path.unlink(missing_ok=True)
        return {"stopped": True}
    for _ in range(50):
        try:
            if not _owned(state):
                raise RuntimeError("Host helper PID changed; no further signal sent")
        except FileNotFoundError:
            path.unlink(missing_ok=True)
            return {"stopped": True}
        time.sleep(0.1)
    raise RuntimeError("Owned host helper is still stopping; no force kill was issued")
