"""Synthetic persistent account/session lifecycle checks; no real users or media."""

import getpass
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/forte-session"))
from session_store import SessionStore, main  # noqa: E402

PASSWORD = "synthetic strong password for local tests"


def test_passwords_and_session_tokens_are_never_persisted_in_plaintext(tmp_path):
    path = tmp_path / "private" / "accounts.sqlite3"
    store = SessionStore(path)
    assert store.list_users() == []
    first = store.add_user("reviewer-a", PASSWORD)
    second = store.add_user("reviewer-b", PASSWORD)
    assert first != second and "reviewer" not in first
    assert store.authenticate("reviewer-a", PASSWORD) == {"id": first, "username": "reviewer-a"}
    assert store.authenticate("unknown", PASSWORD) is None
    assert store.authenticate("reviewer-a", "wrong password") is None
    token, session = store.login("reviewer-a", PASSWORD)
    assert session["principal"]["id"] == first
    assert isinstance(session["expires_at"], (int, float))
    with sqlite3.connect(path) as connection:
        salts = connection.execute("SELECT password_salt FROM users").fetchall()
        hashes = connection.execute("SELECT password_hash FROM users").fetchall()
        saved_token = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert salts[0] != salts[1] and hashes[0] != hashes[1]
    assert saved_token != token
    assert PASSWORD.encode() not in path.read_bytes()
    assert token.encode() not in path.read_bytes()
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.parent).st_mode & 0o777 == 0o700
    restarted = SessionStore(path)
    assert restarted.get_session(token)["principal"] == session["principal"]


def test_rotation_logout_idle_and_absolute_expiry(tmp_path):
    now = [1000.0]
    store = SessionStore(
        tmp_path / "private" / "users.db",
        clock=lambda: now[0],
        absolute_seconds=20,
        idle_seconds=5,
    )
    user = store.add_user("reviewer", PASSWORD)
    first, first_session = store.create_session(user)
    second, second_session = store.create_session(user, previous_token=first)
    assert first != second and first_session["csrf_token"] != second_session["csrf_token"]
    assert store.get_session(first) is None
    now[0] += 4
    assert store.get_session(second)["expires_at"] == 1009
    now[0] += 5
    assert store.get_session(second) is None
    token, _ = store.create_session(user)
    for _ in range(4):
        now[0] += 4
        assert store.get_session(token)
    now[0] += 4
    assert store.get_session(token) is None
    token, _ = store.create_session(user)
    store.revoke_session(token)
    assert store.get_session(token) is None


def test_disable_and_password_reset_revoke_every_session_across_restarts(tmp_path):
    path = tmp_path / "private" / "users.db"
    store = SessionStore(path)
    user = store.add_user("reviewer", PASSWORD)
    first, _ = store.create_session(user)
    second, _ = store.create_session(user)
    store.reset_password("reviewer", "different synthetic strong password")
    assert store.get_session(first) is None and store.get_session(second) is None
    assert store.login("reviewer", PASSWORD) is None
    active, _ = store.login("reviewer", "different synthetic strong password")
    SessionStore(path).disable_user("reviewer")
    assert store.get_session(active) is None
    assert store.login("reviewer", "different synthetic strong password") is None
    with pytest.raises(ValueError, match="cannot be created"):
        store.create_session(user)


def test_account_cli_uses_getpass_and_never_prints_password(tmp_path, monkeypatch, capsys):
    path = tmp_path / "private" / "users.db"
    monkeypatch.setattr(getpass, "getpass", lambda prompt: PASSWORD)
    assert main(["--db", str(path), "add", "reviewer"]) == 0
    assert PASSWORD not in capsys.readouterr().out
    assert main(["--db", str(path), "list"]) == 0
    assert "reviewer" in capsys.readouterr().out
    assert main(["--db", str(path), "reset-password", "reviewer"]) == 0
    assert main(["--db", str(path), "disable", "reviewer"]) == 0
    assert PASSWORD not in capsys.readouterr().out
    assert SessionStore(path).authenticate("reviewer", PASSWORD) is None


def test_private_path_and_account_validation_fail_closed(tmp_path):
    broad = tmp_path / "broad"
    broad.mkdir(mode=0o755)
    broad.chmod(0o755)
    with pytest.raises(ValueError, match="directory must be private"):
        SessionStore(broad / "users.db")
    path = tmp_path / "private" / "users.db"
    store = SessionStore(path)
    with pytest.raises(ValueError):
        store.add_user("invalid name", PASSWORD)
    with pytest.raises(ValueError):
        store.add_user("reviewer", "short")
    link = path.parent / "alias.db"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symlinks"):
        SessionStore(link)
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private regular file"):
        SessionStore(path)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    with pytest.raises(ValueError, match="outside a Git checkout"):
        SessionStore(checkout / "private" / "users.db")
