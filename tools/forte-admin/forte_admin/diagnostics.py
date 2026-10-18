"""Bounded, read-only diagnostics. No case content, credentials or raw logs."""

import json
import subprocess
from pathlib import Path


def run(command, timeout=8):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def diagnose(config, validate, *, system=None):
    """Keep capability checks separate from release/access acceptance."""
    from forte_admin.hardware import inspect_host

    try:
        manifest = json.loads(Path(config["integration_manifest"]).read_text())
    except (OSError, ValueError, KeyError):
        manifest = {}
    capabilities = inspect_host(config, manifest)
    checks = [
        {"check": "host_capability", "ok": False, "detail": message}
        for message in capabilities["blockers"]
    ]
    if not checks:
        checks.append(
            {
                "check": "host_capability",
                "ok": True,
                "detail": (
                    "Host is a candidate for bounded load; actual workload validation is separate."
                ),
            }
        )
    for message in validate(config):
        checks.append({"check": "release_prerequisite", "ok": False, "detail": message})
    return {
        "schema_version": 1,
        "mode": config["mode"],
        "processing_destination": config["origin"],
        "ready_to_attempt_load": capabilities["can_attempt"],
        "ready_to_install": all(item["ok"] for item in checks),
        "hardware": capabilities,
        "warnings": capabilities["warnings"],
        "checks": checks,
    }


def safe_logs(config, target):
    # Application logs may contain model output. Support output exposes metadata only.
    return {
        "schema_version": 1,
        "raw_logs_exported": False,
        "reason": (
            "Core logs can contain private case content. Inspect locally under the "
            "application's private storage; support output includes only status and"
            " diagnostics."
        ),
        "processing_destination": config["origin"],
    }
