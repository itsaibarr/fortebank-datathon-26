"""Reviewed installation adapters: public artifacts and explicit local accounts."""

from __future__ import annotations

import getpass
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

from forte_admin.config import ConfigError, private_write, read_json
from forte_admin.resources import prepare_resources

PINNED_PROXY = "nginx@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de"
IMAGE = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9._:/-]*@)?sha256:[0-9a-f]{64}")


def _image_ready(image, *, apply, online):
    if not isinstance(image, str) or not IMAGE.fullmatch(image):
        return False, "Select an immutable application/proxy image before preparation."
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0:
            return True, "Pinned image is already present."
        if not apply:
            return False, "Pinned image is missing locally; preview never pulls images."
        if not online or "@sha256:" not in image:
            return (
                False,
                "Pinned image is missing; provide its approved artifact or allow "
                "public digest preparation.",
            )
        result = subprocess.run(
            ["docker", "pull", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1800,
            check=False,
        )
        if result.returncode:
            return False, "Pinned public image preparation failed; retry to resume layers."
        checked = subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        return checked.returncode == 0, "Pinned image preparation could not be verified."
    except (OSError, subprocess.TimeoutExpired):
        return False, "Container runtime or public image preparation is unavailable."


def prepare_application(
    manifest,
    resources_root,
    *,
    apply=False,
    online=False,
    source_dir=None,
    image_artifact=None,
    config=None,
    qualification=False,
    build_core=False,
    core_source=None,
    node_image=None,
    installation=None,
):
    selected = config or {}
    build_report = None
    if build_core:
        from forte_admin.source_image import build_source_image

        bundle = Path(core_source) if core_source else Path(__file__).resolve().parents[3]
        release = read_json(bundle / "RELEASE.json")
        commit = release.get("core_source_commit")
        build_report = build_source_image(
            bundle,
            installation,
            node_image=node_image,
            publisher_core_commit=commit,
            apply=apply,
            online=online,
        )
        if build_report.get("ok") is not True:
            return {
                "ok": False,
                "source_build": build_report,
                "unresolved_prerequisites": build_report.get("unresolved_prerequisites")
                or [
                    "Explicit public source build is incomplete; no previous release was selected."
                ],
            }
        if apply and build_report.get("ok"):
            manifest = select_local_build(manifest, selected, installation, bundle, build_report)
    report = prepare_resources(
        manifest,
        resources_root,
        apply=apply,
        online=online,
        source_dir=source_dir,
        image_artifact=image_artifact,
    )
    proxy_ok, reason = (
        (True, "No ingress image is used for local qualification.")
        if qualification
        else _image_ready(selected.get("proxy_image", ""), apply=apply, online=online)
    )
    if not proxy_ok:
        report["unresolved_prerequisites"].append(reason)
    report["proxy_image_prepared"] = proxy_ok
    if build_report:
        report["source_build"] = build_report
    report["ok"] = report.get("ok", False) and proxy_ok
    return report


def select_local_build(manifest, config, installation, bundle, built):
    """Derive a separate unapproved candidate; never alter publisher attestations."""
    source = read_json(Path(bundle) / "core-source/SOURCE.json")
    contract = source.get("files", {}).get("contracts/reasoning-api-contract.json", {})
    digest = contract.get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ConfigError("Bundled canonical contract is missing from the source build inventory.")
    candidate = json.loads(json.dumps(manifest))
    candidate["core"] = {
        "commit": built["core_commit"],
        "image": built["local_image_id"],
        "contract_sha256": digest,
    }
    candidate["verification"] = {
        "release": False,
        "model_workload": False,
        "offline_analysis": False,
        "browser_session": False,
        "ownership": False,
        "receipt": "verification/acceptance.json",
    }
    candidate["provenance"] = {
        "derived_status": "Local source build; runtime and browser acceptance remain unapproved.",
        "base_candidate_sha256": hashlib.sha256(
            Path(config["integration_manifest"]).read_bytes()
        ).hexdigest(),
        "build_receipt": built["receipt"],
        "source_manifest_sha256": built["source_manifest_sha256"],
    }
    path = (
        Path(installation)
        / "local-releases"
        / (built["core_commit"][:12] + "-" + built["local_image_id"][7:19] + ".json")
    )
    data = json.dumps(candidate, indent=2, sort_keys=True) + "\n"
    # Resuming a completed build must not rewrite its ancestry against itself.
    if path.exists():
        existing = read_json(path)
        if (
            existing.get("core") != candidate["core"]
            or existing.get("assets") != candidate.get("assets")
            or any(
                existing.get("verification", {}).get(key) is not False
                for key in (
                    "release",
                    "model_workload",
                    "offline_analysis",
                    "browser_session",
                    "ownership",
                )
            )
        ):
            raise ConfigError(
                "The local build candidate changed; preserve it and use a separate installation."
            )
        candidate, data = existing, path.read_text()
    else:
        private_write(path, data)
    config.update(
        integration_manifest=str(path),
        manifest_sha256=hashlib.sha256(data.encode()).hexdigest(),
        core_image=built["local_image_id"],
    )
    return candidate


def bootstrap_administrator(config, root, *, username=None, password_file=None, preview=False):
    if config.get("access_mode") != "browser-session":
        return {
            "ok": True,
            "account_created": False,
            "notice": "Administrative gateway mode has no browser account bootstrap.",
        }
    script = Path(__file__).resolve().parents[3] / "tools/forte-session/session_store.py"
    if not script.is_file():
        return {
            "ok": False,
            "unresolved_prerequisites": [
                "The accepted browser session account component is not included in this release."
            ],
        }
    if preview:
        return {
            "ok": True,
            "account_created": False,
            "notice": (
                "First account is created locally during apply; no account or password "
                "is generated in preview."
            ),
        }
    try:
        spec = importlib.util.spec_from_file_location("forte_install_session_store", script)
        if spec is None or spec.loader is None:
            raise ValueError
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        database = Path(config.get("session_db", Path(root) / "auth/sessions.sqlite3"))
        if not database.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError
        store = module.SessionStore(database)
        users = store.list_users()
        enabled = [item for item in users if item.get("enabled")]
        if enabled and (not username or any(item.get("username") == username for item in enabled)):
            return {"ok": True, "account_created": False, "existing_account_preserved": True}
        if not username:
            if not sys.stdin.isatty():
                return {
                    "ok": False,
                    "unresolved_prerequisites": [
                        "Supply --administrator and a private --admin-password-file, "
                        "or run interactively for first account setup."
                    ],
                }
            username = input("First administrator username: ").strip()
        if password_file:
            path = Path(password_file).expanduser()
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as source:
                info = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_mode & 0o077
                    or info.st_size > 1025
                ):
                    raise ValueError
                raw = source.read(1026)
                password = raw.removesuffix(b"\n").decode("utf-8")
        else:
            if not sys.stdin.isatty():
                return {
                    "ok": False,
                    "unresolved_prerequisites": [
                        "First account needs an interactive password prompt "
                        "or an owner-only password file."
                    ],
                }
            password = getpass.getpass("Administrator password: ")
            if password != getpass.getpass("Confirm administrator password: "):
                raise ValueError
        store.add_user(username, password)
        return {"ok": True, "account_created": True}
    except (OSError, ValueError, UnicodeError, RuntimeError, sqlite3.Error):
        return {
            "ok": False,
            "unresolved_prerequisites": [
                "Local account bootstrap is incomplete; verify the private credential file "
                "or account input. Existing accounts were preserved."
            ],
        }
