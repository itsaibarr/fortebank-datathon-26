"""Bounded, read-only diagnostics. No case content, credentials or raw logs."""

import json
import platform
import shutil
import socket
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
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    system = system or {"os": platform.system(), "arch": platform.machine()}
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    add(
        "supported_host",
        system["os"] == "Linux"
        and system["arch"] in {"x86_64", "amd64"}
        and release.get("ID") == "ubuntu"
        and release.get("VERSION_ID") == "24.04",
        (
            "Supported runtime: Ubuntu 24.04 x86_64, Docker Engine + Compose v2; "
            "private GPU: A100 80GB."
        ),
    )
    docker_ok = shutil.which("docker") is not None
    code, _ = run(["docker", "info", "--format", "{{.ServerVersion}}"])
    add(
        "docker_engine",
        docker_ok and code == 0,
        "Docker Engine must be running and accessible to this administrator.",
    )
    code, _ = run(["docker", "compose", "version", "--short"])
    add("compose", code == 0, "Docker Compose v2 is required.")
    for error in validate(config):
        add("release_prerequisite", False, error)
    if config["mode"] == "private":
        code, runtimes = run(["docker", "info", "--format", "{{json .Runtimes}}"])
        try:
            toolkit_ready = code == 0 and "nvidia" in json.loads(runtimes)
        except (ValueError, TypeError):
            toolkit_ready = False
        add(
            "nvidia_container_runtime",
            toolkit_ready,
            "NVIDIA Container Toolkit must be registered with Docker; "
            "doctor never changes drivers or runtimes.",
        )
        code, raw = run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version,memory.used",
                "--format=csv,noheader,nounits",
            ]
        )
        supported = False
        unallocated = False
        if code == 0:
            rows = [line.split(",") for line in raw.splitlines()]
            for row in rows if len(rows) == 1 else []:
                if len(row) != 4:
                    continue
                try:
                    supported = supported or (
                        "A100" in row[0]
                        and float(row[1]) >= 79000
                        and int(row[2].strip().split(".")[0]) >= 570
                    )
                    unallocated = unallocated or float(row[3]) <= 1024
                except ValueError:
                    pass
        add(
            "gpu_hardware",
            supported,
            (
                "Require one NVIDIA A100 80GB with driver >=570; model workload receipt"
                " is a separate prerequisite."
            ),
        )
        add(
            "gpu_available",
            supported and unallocated,
            "GPU must be free for this installation; no processes will be stopped automatically.",
        )
        try:
            manifest = json.loads(Path(config["integration_manifest"]).read_text())
            requirements = manifest["runtime"]["requirements"]
        except (OSError, ValueError, KeyError, TypeError):
            requirements = {}
        min_ram = requirements.get("min_host_ram_gib")
        min_disk = requirements.get("min_free_disk_gib")
        memory = 0
        try:
            fields = dict(
                line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
            )
            memory = int(fields["MemAvailable"].split()[0]) * 1024
        except (OSError, KeyError, ValueError):
            pass
        add(
            "host_memory",
            isinstance(min_ram, (int, float)) and min_ram > 0 and memory >= min_ram * 1024**3,
            "Available RAM must meet the reviewed workload requirement in the release manifest.",
        )
        target = Path(config["data_root"])
        while not target.exists() and target != target.parent:
            target = target.parent
        free = shutil.disk_usage(target).free
        add(
            "disk_space",
            isinstance(min_disk, (int, float)) and min_disk > 0 and free >= min_disk * 1024**3,
            (
                "Free storage must meet the reviewed release requirement, including "
                "images and case reserve."
            ),
        )
    for key in ("https_port", "bridge_port"):
        if key == "bridge_port" and config["mode"] == "attach":
            continue
        try:
            with socket.socket() as sock:
                sock.bind(
                    (
                        config.get("bind_address", "127.0.0.1")
                        if key == "https_port"
                        else "127.0.0.1",
                        int(config[key]),
                    )
                )
            available = True
        except (OSError, ValueError):
            available = False
        add(
            key,
            available,
            (
                "Listener must be available before first startup; status inspects an "
                "already running installation."
            ),
        )
    return {
        "schema_version": 1,
        "mode": config["mode"],
        "processing_destination": config["origin"],
        "ready_to_install": all(item["ok"] for item in checks),
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
