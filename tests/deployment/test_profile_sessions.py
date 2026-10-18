"""Real session component compatibility with rendered private deployment settings."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
sys.path.insert(0, str(ROOT / "tools/forte-session"))
from forte_admin import config as configuration  # noqa: E402
from forte_admin.preparation import bootstrap_administrator  # noqa: E402
from session_gateway import Gateway  # noqa: E402
from session_store import SessionStore  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_account_bootstrap_real_store_is_repeatable_and_never_prints_password(tmp_path, capsys):
    root = tmp_path / "install"
    selected, _ = configuration.plan(root, {})
    configuration.apply(root, selected, lambda *args: [])
    secret = tmp_path / "password"
    secret.write_text("synthetic-administrator-password\n")
    secret.chmod(0o600)
    first = bootstrap_administrator(selected, root, username="reviewer", password_file=secret)
    assert first["ok"] and first["account_created"]
    store = SessionStore(selected["session_db"])
    before = store.list_users()
    second = bootstrap_administrator(selected, root, username="reviewer", password_file=secret)
    assert second["ok"] and second["existing_account_preserved"]
    assert store.list_users() == before
    assert secret.read_text().strip() not in capsys.readouterr().out


def test_rendered_config_is_accepted_by_real_session_gateway(tmp_path):
    root = tmp_path / "install"
    selected, _ = configuration.plan(root, {"mode": "attach"})
    selected["core_image"] = "sha256:" + "1" * 64
    manifest = tmp_path / "manifest.json"
    # The render path intentionally uses an unapproved but structurally valid manifest.
    manifest.write_text(json.dumps({"schema_version": 1, "runtime": {}, "verification": {}}))
    selected["integration_manifest"] = str(manifest)
    selected["manifest_sha256"] = __import__("hashlib").sha256(manifest.read_bytes()).hexdigest()
    configuration.apply(root, selected, lambda *args: [])
    service = Path(selected["secrets_root"]) / "core-api.key"
    service.write_text("a" * 48)
    service.chmod(0o600)
    runtime = load("rendered_session_runtime", "deploy/portable/runtime.py")
    runtime.render(selected, root / "runtime")
    settings = json.loads((root / "runtime/session-config.json").read_text())
    assert set(
        ("listen_host", "listen_port", "service_key_file", "gateway_token_file", "session_db")
    ).issubset(settings)
    assert settings["browser_uploads_enabled"] is False
    instance = Gateway(settings, SessionStore(selected["session_db"]))
    assert instance.uploads is False
    assert service.read_text() not in (root / "runtime/nginx.conf").read_text()


def test_daemon_stop_refuses_an_unrelated_live_pid(tmp_path, monkeypatch):
    daemon = load("owned_session_daemon", "deploy/portable/host_daemon.py")
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "pid": 424242,
                "started": "17",
                "script": "/owned/gateway.py",
                "config": "/owned/config.json",
                "owner_token": "a" * 48,
                "config_sha256": "b" * 64,
            }
        )
    )
    state.chmod(0o600)
    monkeypatch.setattr(daemon, "_process", lambda pid: ("18", [b"/other/process"], []))
    sent = []
    monkeypatch.setattr(os, "kill", lambda *args: sent.append(args))
    with pytest.raises(RuntimeError, match="no signal"):
        daemon.stop(state)
    assert sent == []


def test_stale_daemon_state_is_removed_without_a_signal(tmp_path, monkeypatch):
    daemon = load("stale_session_daemon", "deploy/portable/host_daemon.py")
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "pid": 424242,
                "started": "17",
                "script": "/owned/gateway.py",
                "config": "/owned/config.json",
                "owner_token": "a" * 48,
                "config_sha256": "b" * 64,
            }
        )
    )
    state.chmod(0o600)

    def missing(pid):
        raise FileNotFoundError

    monkeypatch.setattr(daemon, "_process", missing)
    sent = []
    monkeypatch.setattr(os, "kill", lambda *args: sent.append(args))
    assert daemon.stop(state)["stopped"]
    assert not state.exists() and sent == []


def test_daemon_reuses_its_identity_and_refuses_configuration_replacement(tmp_path, monkeypatch):
    import hashlib

    daemon = load("repeat_session_daemon", "deploy/portable/host_daemon.py")
    script, config, state = [
        tmp_path / name for name in ("gateway.py", "config.json", "state.json")
    ]
    script.write_text("# synthetic helper; never executed\n")
    config.write_text('{"synthetic":true}\n')
    config.chmod(0o600)
    launched = []
    alive = True

    class Process:
        pid = 424242

        def __init__(self, command, **options):
            launched.append((command, options))

        def poll(self):
            return None

        def terminate(self):
            raise AssertionError("A reused helper must not be replaced")

    def identity(pid):
        if not alive:
            raise FileNotFoundError
        command, options = launched[0]
        environment = [f"{key}={value}".encode() for key, value in options["env"].items()]
        return "17", [part.encode() for part in command], environment

    def terminate_owned(pid, sig):
        nonlocal alive
        assert pid == Process.pid
        alive = False

    monkeypatch.setattr(daemon.subprocess, "Popen", Process)
    monkeypatch.setattr(daemon, "_process", identity)
    monkeypatch.setattr(daemon.os, "kill", terminate_owned)
    assert daemon.start(script, config, state)["started"]
    saved = json.loads(state.read_text())
    assert saved["config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert daemon.start(script, config, state)["already_running"]
    assert len(launched) == 1
    config.write_text('{"synthetic":"changed"}\n')
    with pytest.raises(RuntimeError, match="configuration changed"):
        daemon.start(script, config, state)
    assert len(launched) == 1 and alive
    assert daemon.stop(state)["stopped"]
    assert not state.exists()
