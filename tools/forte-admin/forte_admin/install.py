"""Resumable local installation orchestration; no case processing or hosted failover.

The installer calls only explicitly supplied release/resource/runtime helpers. It
never invents an administrator account, marks an acceptance flag true, changes a
host driver, deletes storage, or substitutes an inference service.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import ssl
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from forte_admin.config import ConfigError, installation_root, plan, private_write, read_json
from forte_admin.config import apply as apply_config

PHASES = (
    "capabilities",
    "configuration",
    "tls",
    "public_resources",
    "administrator",
    "release_checks",
    "startup",
    "readiness",
)
STATES = {"planned", "running", "complete", "blocked", "interrupted", "skipped"}
IMMUTABLE = ("mode", "project_name", "data_root", "secrets_root")


def _read_manifest(config):
    path = config.get("integration_manifest")
    if not path:
        return None
    return read_json(path)


def _pinned_release(config, manifest):
    core = manifest.get("core", {})
    if (
        not isinstance(core, dict)
        or not re.fullmatch(r"[0-9a-f]{40}", str(core.get("commit", "")))
        or not re.fullmatch(
            r"(?:[A-Za-z0-9./:_-]+@)?sha256:[0-9a-f]{64}", str(core.get("image", ""))
        )
        or not re.fullmatch(r"[0-9a-f]{64}", str(core.get("contract_sha256", "")))
        or (config["mode"] == "private" and core["image"] != config["core_image"])
    ):
        return [
            "Public preparation requires a stable core commit, immutable image "
            "and canonical contract hash."
        ]
    return []


def _host_result(check, config):
    if check is None:
        return {"can_attempt": False}, [
            "Host capability integration is unavailable; run the reviewed host prerequisite checks."
        ]
    result = check(config)
    if not isinstance(result, dict):
        return {"can_attempt": False}, ["Host capability checks did not return a valid report."]
    allowed = result.get("can_attempt", result.get("ready_to_install", False)) is True
    errors = result.get("unresolved_prerequisites", result.get("blockers", []))
    if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
        errors = []
    if not allowed and not errors:
        errors = [
            item["detail"]
            for item in result.get("checks", [])
            if isinstance(item, dict)
            and item.get("ok") is False
            and isinstance(item.get("detail"), str)
        ]
    if not allowed and not errors:
        errors = ["Host prerequisites are unresolved; no drivers or shared services were changed."]
    report = {"can_attempt": allowed}
    for field in ("status", "warnings", "selected_gpu", "resource_qualification"):
        if field in result:
            report[field] = result[field]
    return report, errors


def _root_available(root):
    if root.exists():
        if not root.is_dir() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
            raise ConfigError(
                "Installation directory must be owned by this administrator and mode 0700."
            )
        if any(root.iterdir()) and not (root / "installation.json").is_file():
            raise ConfigError(
                "Choose an empty installation directory; unrelated files were preserved."
            )
    for name in ("installation.json", "install-journal.json"):
        if (root / name).is_symlink():
            raise ConfigError(
                "Installation state must be regular files inside the installation root."
            )


@contextmanager
def _claim(root):
    """Lock the owned directory without creating an unrelated lock-file bootstrap."""
    import fcntl

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConfigError(
                "Another installer owns this directory; inspect it before retrying."
            ) from None
        _root_available(root)
        yield
    finally:
        os.close(descriptor)


def _journal(root, config):
    path = root / "install-journal.json"
    previous = read_json(path) if path.exists() else {}
    if previous and (
        previous.get("schema_version") != 1
        or previous.get("project_name") != config["project_name"]
        or type(previous.get("attempt")) is not int
        or previous["attempt"] < 1
    ):
        raise ConfigError(
            "Installation journal does not match this installation; state was preserved."
        )
    # This receipt intentionally contains no resource paths, case identifiers,
    # account names, passwords, API keys, raw subprocess output or exceptions.
    return {
        "schema_version": 1,
        "project_name": config["project_name"],
        "mode": config["mode"],
        "attempt": previous.get("attempt", 0) + 1,
        "configuration_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "phases": [{"phase": phase, "status": "planned"} for phase in PHASES],
    }


def _tls(config, root, *, apply, mode):
    if mode not in {"supplied", "local-self-signed"}:
        raise ConfigError("TLS mode must be supplied or explicitly local-self-signed.")
    cert, key = Path(config["tls_cert"]), Path(config["tls_key"])
    trust = "supplied-certificate; browser trust must be provided by the administrator"
    if mode == "local-self-signed":
        hostname = urlsplit(config["origin"]).hostname
        if hostname not in {"localhost", "127.0.0.1"} or config["bind_address"] != "127.0.0.1":
            raise ConfigError(
                "Local self-signed TLS is restricted to an explicit loopback-only origin."
            )
        tls_root = (root / "tls").resolve()
        if not all(path.resolve().is_relative_to(tls_root) for path in (cert, key)):
            raise ConfigError(
                "Generated local TLS files must stay inside the installation tls directory."
            )
        trust = (
            "local-self-signed; import this installation certificate "
            "into the reviewer's local trust store"
        )
        if cert.exists() != key.exists():
            return [
                "A partial TLS pair exists; preserve it and supply a matching certificate/key."
            ], trust
        if not cert.exists():
            if not apply:
                return [], trust
            cert.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                ipaddress.ip_address(hostname)
                san = "IP:" + hostname
            except ValueError:
                san = "DNS:" + hostname
            # Exclusive temporary names and atomic moves avoid replacing an existing pair.
            import secrets

            suffix = "." + secrets.token_hex(8) + ".tmp"
            temporary_cert, temporary_key = (
                cert.with_name(cert.name + suffix),
                key.with_name(key.name + suffix),
            )
            try:
                result = subprocess.run(
                    [
                        "openssl",
                        "req",
                        "-x509",
                        "-newkey",
                        "rsa:3072",
                        "-nodes",
                        "-days",
                        "365",
                        "-subj",
                        "/CN=" + hostname,
                        "-addext",
                        "subjectAltName=" + san,
                        "-keyout",
                        str(temporary_key),
                        "-out",
                        str(temporary_cert),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                    check=False,
                )
                if result.returncode:
                    return [
                        "Local TLS generation failed; install OpenSSL or supply "
                        "a matching certificate/key."
                    ], trust
                temporary_key.chmod(0o600)
                temporary_cert.chmod(0o600)
                # link is exclusive: even an unexpected concurrent writer is preserved.
                os.link(temporary_key, key)
                os.link(temporary_cert, cert)
            except (OSError, subprocess.TimeoutExpired):
                return [
                    "Local TLS generation incomplete; inspect the local TLS pair and retry."
                ], trust
            finally:
                temporary_cert.unlink(missing_ok=True)
                temporary_key.unlink(missing_ok=True)
    if not cert.is_file() or not key.is_file():
        return [
            "Supply a matching TLS certificate/key, or select explicit loopback "
            "local-self-signed TLS."
        ], trust
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
    except (OSError, ssl.SSLError):
        return ["The supplied TLS certificate/key cannot be loaded as a matching pair."], trust
    return [], trust


def _bootstrap(callback, config, root, *, preview):
    if config["access_mode"] != "browser-session":
        return [
            "The administrator API gateway does not provide the reviewer browser session workflow."
        ]
    if callback is None:
        return [
            "Core local administrator bootstrap integration is unavailable; "
            "supply the reviewed account tool."
        ]
    result = callback(config, root, preview=preview)
    if not isinstance(result, dict) or result.get("ok") is not True:
        errors = result.get("unresolved_prerequisites", []) if isinstance(result, dict) else []
        if isinstance(errors, list) and errors and all(isinstance(item, str) for item in errors):
            return errors
        return [
            "Core administrator bootstrap is incomplete; no account or password was fabricated."
        ]
    return []


def _ready(result, config):
    return (
        isinstance(result, dict)
        and result.get("ready") is True
        and result.get("core_ready") is True
        and result.get("access_ready") is True
        and (
            config["access_mode"] != "browser-session"
            or result.get("browser_access_verified") is True
        )
    )


def install(
    config,
    root,
    *,
    apply=False,
    runtime,
    prepare_resources=None,
    resource_options=None,
    host_check=None,
    bootstrap=None,
    tls_mode="supplied",
    qualification=False,
    readiness_timeout=300,
    poll_interval=2,
    reporter=None,
):
    """Run the administrator's local installation pipeline and return a safe report.

    ``runtime`` supplies validate/prerequisites/render/lifecycle from the portable
    release. ``host_check(config)`` returns ``can_attempt`` and safe blockers.
    ``prepare_resources(manifest, resources_root, apply=..., **options)`` handles
    pinned public assets. ``bootstrap(config, root, preview=...)`` must call the
    actual reviewed core administrator tool; the default blocks browser access.
    No helper is permitted to mutate when preview=True/apply=False.
    """
    if (
        isinstance(readiness_timeout, bool)
        or not isinstance(readiness_timeout, (int, float))
        or not math.isfinite(readiness_timeout)
        or not 0 <= readiness_timeout <= 1800
        or isinstance(poll_interval, bool)
        or not isinstance(poll_interval, (int, float))
        or not math.isfinite(poll_interval)
        or not 0 < poll_interval <= 30
    ):
        raise ConfigError(
            "Readiness timeout must be 0–1800 seconds and poll interval 0–30 seconds."
        )
    root = installation_root(root)
    _root_available(root)
    selected, previous = plan(root, config)
    if previous and any(previous.get(key) != selected.get(key) for key in IMMUTABLE):
        raise ConfigError(
            "Changing profile ownership or storage requires a separate installation and migration."
        )
    config = selected
    if qualification and (
        config["mode"] != "private"
        or config["bind_address"] != "127.0.0.1"
        or urlsplit(config["origin"]).hostname not in {"localhost", "127.0.0.1"}
    ):
        raise ConfigError(
            "Local qualification requires the private profile and an explicit loopback-only origin."
        )
    options = dict(resource_options or {})
    if "config" in options:
        options["config"] = config
    if "apply" in options:
        raise ConfigError("Resource mutation is controlled by the install --apply selection.")
    result = {
        "schema_version": 1,
        "ok": False,
        "applied": False,
        "preview": not apply,
        "ready": False,
        "exit_code": 2,
        "mode": config["mode"],
        "operation": "local-qualification" if qualification else "browser-installation",
        "qualification_complete": False,
        "processing_destination": config["origin"],
        "application_url": None,
        "services_started": False,
        "data_preserved": True,
        "remote_fallback": False,
        "case_processing_started": False,
        "externally_verified": False,
        "phases": [{"phase": phase, "status": "planned"} for phase in PHASES],
        "unresolved_prerequisites": [],
        "retention": config["retention"],
        "training_use": config["training_use"],
    }
    current_phase = "capabilities"
    journal = None

    def mark(phase, status):
        nonlocal current_phase
        current_phase = phase
        if phase not in PHASES or status not in STATES:
            raise ConfigError("Invalid installer phase transition.")
        for item in result["phases"]:
            if item["phase"] == phase:
                item["status"] = status
        if journal is not None:
            journal["phases"] = [dict(item) for item in result["phases"]]
            private_write(root / "install-journal.json", json.dumps(journal, indent=2) + "\n")
        if reporter:
            reporter({"phase": phase, "status": status})

    def block(errors):
        result["unresolved_prerequisites"] = list(dict.fromkeys(errors))
        mark(current_phase, "blocked")
        return result

    try:
        mark("capabilities", "running")
        structural = runtime.validate(config)
        if structural:
            return block(structural)
        manifest = _read_manifest(config)
        if manifest is None:
            return block(
                ["Select a pinned core integration manifest before public preparation or startup."]
            )
        pinned_errors = _pinned_release(config, manifest)
        if pinned_errors:
            return block(pinned_errors)
        host, host_errors = _host_result(host_check, config)
        result["host_capabilities"] = host
        if not host["can_attempt"]:
            return block(host_errors)
        mark("capabilities", "complete")
        if not apply:
            errors = []
            if not qualification:
                errors, result["tls_trust"] = _tls(config, root, apply=False, mode=tls_mode)
            if config["mode"] == "private":
                if prepare_resources is None:
                    errors.append("Pinned public resource preparation integration is unavailable.")
                else:
                    resources = prepare_resources(
                        manifest, config["resources_root"], apply=False, **options
                    )
                    if not isinstance(resources, dict) or resources.get("ok") is not True:
                        errors += (
                            resources.get(
                                "unresolved_prerequisites",
                                ["Pinned public resources are not prepared."],
                            )
                            if isinstance(resources, dict)
                            else [
                                "Pinned public resource preparation did not return a valid report."
                            ]
                        )
            if qualification:
                qualification_checks = getattr(runtime, "qualification_prerequisites", None)
                if qualification_checks is None:
                    errors.append("Bounded local model qualification integration is unavailable.")
                else:
                    errors += qualification_checks(config)
            else:
                errors += _bootstrap(bootstrap, config, root, preview=True)
                # Full release checks are read-only and may list expected absent
                # secrets/resources. Preview never manufactures them to pass a gate.
                errors += runtime.prerequisites(config)
            result["unresolved_prerequisites"] = list(dict.fromkeys(errors))
            result["ok"] = not errors
            result["exit_code"] = 0 if not errors else 2
            return result
        with _claim(root):
            mark("configuration", "running")
            apply_config(root, config, lambda config, target: [])
            result["applied"] = True
            journal = _journal(root, config)
            mark("configuration", "complete")
            if not qualification:
                mark("tls", "running")
                errors, result["tls_trust"] = _tls(config, root, apply=True, mode=tls_mode)
                if errors:
                    return block(errors)
                mark("tls", "complete")
            else:
                mark("tls", "skipped")
            mark("public_resources", "running")
            if config["mode"] == "private":
                if prepare_resources is None:
                    return block(["Pinned public resource preparation integration is unavailable."])
                resources = prepare_resources(
                    manifest, config["resources_root"], apply=True, **options
                )
                if not isinstance(resources, dict) or resources.get("ok") is not True:
                    return block(
                        resources.get(
                            "unresolved_prerequisites",
                            ["Pinned public resource preparation remains incomplete."],
                        )
                        if isinstance(resources, dict)
                        else ["Pinned public resource preparation did not return a valid report."]
                    )
            mark("public_resources", "complete")
            # An explicit source build may select a new, unapproved local image
            # and a separate manifest. Preserve that selection for a resumed run.
            apply_config(root, config, lambda config, target: [])
            if qualification:
                mark("administrator", "skipped")
                mark("readiness", "skipped")
                mark("release_checks", "running")
                qualification_checks = getattr(runtime, "qualification_prerequisites", None)
                if qualification_checks is None:
                    return block(["Bounded local model qualification integration is unavailable."])
                errors = qualification_checks(config)
                if errors:
                    return block(errors)
                mark("release_checks", "complete")
                mark("startup", "running")
                qualified = runtime.lifecycle(config, root / "runtime", "qualify")
                if not isinstance(qualified, dict) or not (
                    qualified.get("ok") is True
                    and qualified.get("core_ready") is True
                    and qualified.get("qualification_complete") is True
                    and qualified.get("services_stopped") is True
                ):
                    return block(
                        [
                            "Bounded local model qualification is incomplete; inspect status "
                            "and the local qualification receipt. No browser application "
                            "or hosted fallback was enabled."
                        ]
                    )
                mark("startup", "complete")
                result.update(
                    ok=True, exit_code=0, qualification_complete=True, services_stopped=True
                )
                return result
            mark("administrator", "running")
            errors = _bootstrap(bootstrap, config, root, preview=False)
            if errors:
                return block(errors)
            mark("administrator", "complete")
            mark("release_checks", "running")
            errors = runtime.prerequisites(config)
            if errors:
                return block(errors)
            # Render only after assets, TLS, access and unchanged release receipts
            # pass. The renderer never approves the model or legal quality.
            apply_config(root, config, runtime.render)
            mark("release_checks", "complete")
            mark("startup", "running")
            started = runtime.lifecycle(config, root / "runtime", "up")
            result["services_started"] = (
                isinstance(started, dict) and started.get("started") is True
            )
            if not isinstance(started, dict) or not (
                started.get("ok") is True
                or started.get("started") is True
                or started.get("already_running") is True
            ):
                return block(
                    [
                        "Owned service startup is incomplete; run status locally "
                        "and retry this installation."
                    ]
                )
            mark("startup", "complete")
            mark("readiness", "running")
            deadline = time.monotonic() + readiness_timeout
            status = started
            while True:
                if _ready(status, config):
                    result.update(
                        ok=True, ready=True, exit_code=0, application_url=config["origin"]
                    )
                    mark("readiness", "complete")
                    return result
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return block(
                        [
                            "The bounded readiness window expired; model warmup, HTTPS "
                            "or browser access is not ready. Run status and retry; existing "
                            "cases and the chosen processing destination were preserved."
                        ]
                    )
                time.sleep(min(poll_interval, remaining))
                status = runtime.lifecycle(config, root / "runtime", "status")
    except KeyboardInterrupt:
        result["exit_code"] = 130
        result["unresolved_prerequisites"] = [
            "Installation interrupted; run status and repeat the same command to resume. "
            "No services were stopped and persistent data was preserved."
        ]
        mark(current_phase, "interrupted")
        return result
    except ConfigError:
        raise
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        # External helper/subprocess errors can contain credentials or case data.
        return block(
            [
                "Installation phase failed; inspect the selected phase locally and retry. "
                "Credentials, subprocess output and case content were withheld."
            ]
        )
