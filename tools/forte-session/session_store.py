"""Private persistent local accounts and revocable opaque browser sessions.

There are no bootstrap accounts. Passwords use independently salted scrypt;
only SHA256 digests of random session identifiers are persisted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import time
from contextlib import contextmanager
from pathlib import Path

USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")
SESSION = re.compile(r"[A-Za-z0-9_-]{43,128}")


def _password_hash(password, salt):
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=32768, r=8, p=1, dklen=32, maxmem=64 * 1024**2
    )


def _new_password(password):
    if not isinstance(password, str) or not 12 <= len(password.encode("utf-8")) <= 1024:
        raise ValueError("Password must contain between 12 and 1024 UTF-8 bytes")
    salt = secrets.token_bytes(32)
    return salt, _password_hash(password, salt)


def _token_hash(token):
    if not isinstance(token, str) or SESSION.fullmatch(token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class SessionStore:
    def __init__(self, path, *, clock=time.time, absolute_seconds=28800, idle_seconds=1800):
        self.path = Path(path).absolute()
        if self.path.is_symlink() or self.path.parent.resolve() != self.path.parent:
            raise ValueError("Session database cannot traverse symlinks")
        if any((parent / ".git").exists() for parent in (self.path.parent, *self.path.parents)):
            raise ValueError("Session database must be outside a Git checkout")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent = self.path.parent.stat()
        if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise ValueError("Session database directory must be private and owned by this user")
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Session database must be a private regular file owned by this user")
        if not 0 < idle_seconds <= absolute_seconds <= 28800:
            raise ValueError("Session lifetimes exceed the supported bounds")
        self.clock = clock
        self.absolute_seconds = absolute_seconds
        self.idle_seconds = idle_seconds
        self._dummy_salt = secrets.token_bytes(32)
        self._dummy_hash = _password_hash("unavailable-account-password", self._dummy_salt)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1))
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    absolute_expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
                """
            )

    @contextmanager
    def _connection(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def add_user(self, username, password):
        if not isinstance(username, str) or USERNAME.fullmatch(username) is None:
            raise ValueError("Username must use 1–64 supported characters")
        salt, password_hash = _new_password(password)
        user_id = "usr_" + secrets.token_hex(16)
        try:
            with self._connection(write=True) as connection:
                connection.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, 1)",
                    (user_id, username, salt, password_hash),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Account cannot be created") from exc
        return user_id

    create_user = add_user

    def list_users(self):
        with self._connection() as connection:
            return [
                {"id": row["id"], "username": row["username"], "enabled": bool(row["enabled"])}
                for row in connection.execute(
                    "SELECT id, username, enabled FROM users ORDER BY username"
                )
            ]

    def _authenticate(self, connection, username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            return None
        if len(username) > 64 or len(password.encode("utf-8")) > 1024:
            return None
        row = connection.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        salt = row["password_salt"] if row is not None else self._dummy_salt
        expected = row["password_hash"] if row is not None else self._dummy_hash
        valid = hmac.compare_digest(_password_hash(password, salt), expected)
        if not valid or row is None or not row["enabled"]:
            return None
        return {"id": row["id"], "username": row["username"]}

    def authenticate(self, username, password):
        with self._connection() as connection:
            return self._authenticate(connection, username, password)

    def _create_session(self, connection, user_id, previous_token):
        user = connection.execute(
            "SELECT id, username FROM users WHERE id=? AND enabled=1", (user_id,)
        ).fetchone()
        if user is None:
            raise ValueError("Session cannot be created")
        previous = _token_hash(previous_token)
        if previous is not None:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (previous,))
        token, csrf, now = secrets.token_urlsafe(48), secrets.token_urlsafe(32), self.clock()
        expires = now + self.absolute_seconds
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            (_token_hash(token), user_id, csrf, now, now, expires),
        )
        return token, {
            "principal": {"id": user["id"], "username": user["username"]},
            "csrf_token": csrf,
            "expires_at": min(expires, now + self.idle_seconds),
        }

    def create_session(self, user_id, previous_token=None):
        with self._connection(write=True) as connection:
            return self._create_session(connection, user_id, previous_token)

    def login(self, username, password, previous_token=None):
        """Authenticate and issue atomically with password reset/disable operations."""
        with self._connection(write=True) as connection:
            user = self._authenticate(connection, username, password)
            return self._create_session(connection, user["id"], previous_token) if user else None

    def get_session(self, token, touch=True):
        token_hash = _token_hash(token)
        if token_hash is None:
            return None
        now = self.clock()
        with self._connection(write=True) as connection:
            row = connection.execute(
                """SELECT sessions.*, users.username, users.enabled FROM sessions
                JOIN users ON users.id=sessions.user_id WHERE token_hash=?""",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if (
                not row["enabled"]
                or now >= row["absolute_expires_at"]
                or now >= row["last_seen"] + self.idle_seconds
                or now < row["created_at"]
            ):
                connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
                return None
            seen = now if touch else row["last_seen"]
            if touch:
                connection.execute(
                    "UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, token_hash)
                )
            return {
                "principal": {"id": row["user_id"], "username": row["username"]},
                "csrf_token": row["csrf_token"],
                "expires_at": min(row["absolute_expires_at"], seen + self.idle_seconds),
            }

    def revoke_session(self, token):
        token_hash = _token_hash(token)
        if token_hash is not None:
            with self._connection(write=True) as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def disable_user(self, username):
        with self._connection(write=True) as connection:
            connection.execute("UPDATE users SET enabled=0 WHERE username=?", (username,))
            connection.execute(
                "DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username=?)",
                (username,),
            )

    def reset_password(self, username, password):
        salt, password_hash = _new_password(password)
        with self._connection(write=True) as connection:
            changed = connection.execute(
                "UPDATE users SET password_salt=?, password_hash=? WHERE username=?",
                (salt, password_hash, username),
            )
            if not changed.rowcount:
                raise ValueError("Account is unavailable")
            connection.execute(
                "DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username=?)",
                (username,),
            )


def main(argv=None):
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="Administer private local browser accounts")
    parser.add_argument("--db", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for action in ("add", "disable", "reset-password"):
        commands.add_parser(action).add_argument("username")
    commands.add_parser("list")
    args = parser.parse_args(argv)
    try:
        store = SessionStore(args.db)
        if args.command in {"add", "reset-password"}:
            password = getpass.getpass("New password: ")
            if password != getpass.getpass("Confirm password: "):
                raise ValueError("Passwords differ")
            if args.command == "add":
                store.add_user(args.username, password)
            else:
                store.reset_password(args.username, password)
        elif args.command == "disable":
            store.disable_user(args.username)
        else:
            print(json.dumps({"users": store.list_users()}))
            return 0
        print(json.dumps({"ok": True, "action": args.command}))
        return 0
    except (OSError, ValueError, sqlite3.Error):
        print(json.dumps({"ok": False, "error": "account_operation_failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
