"""Read-only CUDA host qualification; a probe never establishes model readiness.

The selected frozen runtime uses one NVIDIA GPU. Its weights, vision workload,
KV cache and runtime overhead must fit that device; ordinary RAM or several
incompatible GPUs are not a substitute. No model, container or driver is started
or changed here. Only allowlisted hardware facts leave the probe.
"""

from __future__ import annotations

import csv
import json
import math
import os
import platform
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

GIB = 1024**3
MIB = 1024**2


def _run(arguments):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=8, check=False)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}", value):
        return None
    return tuple(int(part) for part in value.split("."))


def _at_least(actual, minimum):
    first, second = _version(actual), _version(str(minimum))
    if first is None or second is None:
        return False
    width = max(len(first), len(second))
    return first + (0,) * (width - len(first)) >= second + (0,) * (width - len(second))


def _number(value):
    return (type(value) is int and value > 0) or (
        type(value) is float and math.isfinite(value) and value > 0
    )


def _disk_free(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        return None
    target = Path(value)
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        return shutil.disk_usage(target).free
    except OSError:
        return None


def _native_probe(config):
    """Gather public host facts only; never include PIDs or process arguments."""
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    docker_available = shutil.which("docker") is not None
    code, raw = _run(["docker", "info", "--format", "{{json .Runtimes}}"])
    try:
        runtimes = json.loads(raw) if code == 0 else {}
        engine = isinstance(runtimes, dict) and code == 0
    except (ValueError, TypeError):
        runtimes, engine = {}, False
    compose_code, compose = _run(["docker", "compose", "version", "--short"])
    context_code, context = _run(
        ["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"]
    )
    endpoint = os.environ.get("DOCKER_HOST") if not os.environ.get("DOCKER_CONTEXT") else None
    if endpoint is None:
        try:
            endpoint = json.loads(context) if context_code == 0 else None
        except (ValueError, TypeError):
            endpoint = None
    # Never expose a context endpoint: remote transports can contain credentials.
    # Local probes cannot attest to a remote engine's GPUs or bind-mounted paths.
    local_engine = isinstance(endpoint, str) and endpoint.startswith("unix:///")
    available_ram = None
    try:
        fields = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available_ram = int(fields["MemAvailable"].split()[0]) * 1024
    except (OSError, KeyError, ValueError):
        pass
    snapshot = {
        "system": {
            "os": platform.system(),
            "arch": platform.machine(),
            "distribution": release.get("ID"),
            "version": release.get("VERSION_ID"),
        },
        "docker": {
            "available": docker_available,
            "engine": engine,
            "compose": compose_code == 0 and bool(compose.strip()),
            "nvidia_runtime": engine and "nvidia" in runtimes,
            "local_engine": local_engine,
        },
        "available_ram_bytes": available_ram,
        "disk_free_bytes": {
            name: _disk_free(config.get(name))
            for name in ("resources_root", "data_root", "secrets_root")
        },
        "gpus": [],
        "gpu_probe_ok": False,
        "allocations": {},
        "allocation_probe_ok": False,
    }
    if config.get("mode") == "attach":
        return snapshot
    fields = "index,uuid,name,memory.total,memory.free,driver_version,compute_cap"
    code, raw = _run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
    if code != 0:
        # Some drivers do not expose compute_cap. Unknown capability is reported
        # honestly and cannot satisfy a pinned minimum.
        fields = fields.rsplit(",", 1)[0]
        code, raw = _run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
    if code == 0:
        try:
            for row in csv.reader(raw.splitlines(), skipinitialspace=True):
                if not row:
                    continue
                if len(row) not in {6, 7}:
                    raise ValueError
                index, uuid, name, total, free, driver = (part.strip() for part in row[:6])
                snapshot["gpus"].append(
                    {
                        "index": int(index),
                        "uuid": uuid,
                        "name": name,
                        "total_vram_bytes": int(float(total) * MIB),
                        "free_vram_bytes": int(float(free) * MIB),
                        "driver_version": driver,
                        "compute_capability": row[6].strip() if len(row) == 7 else None,
                    }
                )
            snapshot["gpu_probe_ok"] = True
        except (ValueError, OverflowError):
            snapshot["gpus"] = []
    code, raw = _run(
        ["nvidia-smi", "--query-compute-apps=gpu_uuid", "--format=csv,noheader,nounits"]
    )
    if code == 0:
        allocations = Counter(line.strip() for line in raw.splitlines() if line.strip())
        known = {gpu["uuid"] for gpu in snapshot["gpus"]}
        if all(uuid in known for uuid in allocations):
            snapshot["allocations"] = dict(allocations)
            snapshot["allocation_probe_ok"] = True
    return snapshot


def _gpu_facts(item, allocations):
    """Filter all probe output instead of passing native output to support logs."""
    try:
        index = item["index"]
        uuid = item["uuid"]
        total, free = item["total_vram_bytes"], item["free_vram_bytes"]
        if (
            type(index) is not int
            or index < 0
            or not isinstance(uuid, str)
            or not re.fullmatch(r"(?:GPU|MIG)-[a-zA-Z0-9/-]{1,96}", uuid)
            or type(total) is not int
            or type(free) is not int
            or not 0 <= free <= total
            or total <= 0
        ):
            return None
        name = str(item.get("name", "NVIDIA GPU"))
        return {
            "index": index,
            "uuid": uuid,
            "name": re.sub(r"[^a-zA-Z0-9 ._()+/-]", "", name)[:96],
            "total_vram_bytes": total,
            "free_vram_bytes": free,
            "driver_version": item.get("driver_version")
            if _version(item.get("driver_version"))
            else None,
            "compute_capability": item.get("compute_capability")
            if _version(item.get("compute_capability"))
            else None,
            "active_allocations": max(0, int(allocations.get(uuid, 0))),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _resource_inventory(config, manifest):
    """Stat only public allowlisted assets; byte sizing is not hash verification."""
    root = config.get("resources_root")
    root = Path(root).resolve() if isinstance(root, str) and Path(root).is_absolute() else None
    total, unprepared, unknown = 0, 0, 0
    seen = set()
    for item in manifest.get("assets", []):
        if not isinstance(item, dict):
            continue
        relative = item.get("path")
        if not isinstance(relative, str) or relative in seen:
            continue
        seen.add(relative)
        size = item.get("size_bytes")
        if type(size) is not int or size < 0:
            unknown += 1
            continue
        total += size
        try:
            if root is None or Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError
            target = (root / relative).resolve()
            if (
                not target.is_relative_to(root)
                or not target.is_file()
                or target.stat().st_size != size
            ):
                raise ValueError
        except (OSError, ValueError):
            unprepared += size
    return total, unprepared, unknown


def inspect_host(config, manifest, *, probe=None):
    """Return capability facts, separately from release/workload acceptance.

    ``probe`` can be a snapshot mapping or ``callable(config)`` for synthetic
    tests. Pinned requirements may set min_driver_version,
    min_compute_capability, min_gpu_vram_gib, min_host_ram_gib and
    min_free_disk_gib. Unknown sizing allows a bounded warmup candidate, never a
    workload-success claim. gpu_index/gpu_uuid selects one host device.
    """
    mode = config.get("mode", "private")
    backend = "attach" if mode == "attach" else config.get("backend", "cuda")
    invalid = None
    if not isinstance(manifest, dict):
        invalid = "Integration manifest must be a JSON object."
    elif not isinstance(manifest.get("runtime", {}), dict):
        invalid = "Integration manifest runtime must be a JSON object."
    elif not isinstance(manifest.get("runtime", {}).get("requirements", {}), dict):
        invalid = "Integration manifest runtime requirements must be a JSON object."
    elif not isinstance(manifest.get("verification", {}), dict):
        invalid = "Integration manifest verification must be a JSON object."
    elif not isinstance(manifest.get("assets", []), list):
        invalid = "Integration manifest assets must be a JSON array."
    else:
        architectures = (
            manifest.get("runtime", {})
            .get("requirements", {})
            .get("architectures", ["x86_64", "amd64"])
        )
        if (
            not isinstance(architectures, list)
            or not architectures
            or not all(isinstance(value, str) and value for value in architectures)
        ):
            invalid = "Pinned runtime architectures must be a nonempty JSON array of strings."
    if invalid:
        # Reject malformed public metadata before probing the host. Do not pass
        # arbitrary values or parser exceptions into diagnostics/support output.
        return {
            "schema_version": 1,
            "backend": backend,
            "status": "blocked",
            "can_attempt": False,
            "blockers": [invalid],
            "warnings": [],
            "gpus": [],
            "selected_gpu": None,
            "resource_qualification": {
                "verified_workload": False,
                "release_workload_receipt": False,
                "requires_bounded_model_warmup": mode != "attach",
            },
        }
    snapshot = (probe(config) if callable(probe) else probe) if probe is not None else None
    snapshot = snapshot if snapshot is not None else _native_probe(config)
    blockers, warnings, unsupported = [], [], []
    requirements = manifest.get("runtime", {}).get("requirements", {})
    system, docker = snapshot.get("system", {}), snapshot.get("docker", {})
    if system.get("os") != "Linux":
        unsupported.append("The packaged runtime requires a Linux Docker host.")
    architectures = requirements.get("architectures", ["x86_64", "amd64"])
    if mode != "attach" and system.get("arch") not in architectures:
        unsupported.append("Host architecture is unsupported by the selected pinned runtime.")
    tested_os = (
        system.get("os") == "Linux"
        and system.get("arch") in {"x86_64", "amd64"}
        and system.get("distribution") == "ubuntu"
        and system.get("version") == "24.04"
    )
    if not tested_os:
        warnings.append("Ubuntu 24.04 x86_64 was tested; this host configuration is unvalidated.")
    for key, message in (
        ("available", "Docker Engine is not installed or not on PATH."),
        ("engine", "Docker Engine is unavailable to this administrator."),
        ("compose", "Docker Compose v2 is unavailable."),
    ):
        if not docker.get(key):
            blockers.append(message)
    if not docker.get("local_engine", True):
        blockers.append(
            "Docker must use a verified local Unix socket. Remote or unknown contexts cannot "
            "be qualified by local host probes; run the installer on the deployment host."
        )
    gpus = []
    selected = None
    weights = sum(
        item.get("size_bytes", 0)
        for item in manifest.get("assets", [])
        if isinstance(item, dict)
        and str(item.get("path", "")).endswith(".safetensors")
        and type(item.get("size_bytes")) is int
        and item["size_bytes"] > 0
    )
    inventory_bytes, unprepared_bytes, unknown_sizes = _resource_inventory(config, manifest)
    qualification = {
        "verified_workload": False,
        "release_workload_receipt": manifest.get("verification", {}).get("model_workload") is True,
        "requires_bounded_model_warmup": mode != "attach",
        "weights_inventory_bytes": weights or None,
        "resource_inventory_bytes": inventory_bytes,
        "unprepared_resource_bytes": unprepared_bytes,
        "unknown_resource_sizes": unknown_sizes,
        "available_host_ram_bytes": snapshot.get("available_ram_bytes"),
        "disk_free_bytes": {
            name: snapshot.get("disk_free_bytes", {}).get(name)
            for name in ("data_root", "resources_root", "secrets_root")
        },
    }
    if mode != "attach":
        if backend != "cuda":
            unsupported.append(
                "The packaged model provider implements NVIDIA CUDA only; CPU, Apple and AMD "
                "execution/offload require a separately implemented provider."
            )
        if not docker.get("nvidia_runtime"):
            blockers.append("NVIDIA Container Toolkit is not registered with Docker.")
        if not snapshot.get("gpu_probe_ok"):
            blockers.append("NVIDIA GPU inventory could not be read; no model will be started.")
        if not snapshot.get("allocation_probe_ok"):
            blockers.append(
                "GPU allocations could not be verified; no shared process will be interrupted."
            )
        for item in snapshot.get("gpus", []):
            gpu = _gpu_facts(item, snapshot.get("allocations", {}))
            if gpu is not None:
                gpus.append(gpu)
        if not gpus:
            unsupported.append(
                "No usable NVIDIA CUDA device was found. System RAM alone does not qualify "
                "the selected GPU runtime."
            )
        minimum_gpu = requirements.get("min_gpu_vram_gib")
        minimum_bytes = max(int(minimum_gpu * GIB), weights) if _number(minimum_gpu) else weights
        if not _number(minimum_gpu):
            warnings.append(
                "GPU workload headroom is unvalidated. Weight bytes are only a lower bound; "
                "vision/context/cache overhead requires a bounded model warmup."
            )
        minimum_driver = requirements.get("min_driver_version")
        if minimum_driver is None and _number(requirements.get("driver_major")):
            minimum_driver = str(requirements["driver_major"])
        minimum_compute = requirements.get("min_compute_capability")
        if minimum_driver is None:
            warnings.append("The pinned runtime has no declared minimum driver version.")
        if minimum_compute is None:
            warnings.append("The pinned runtime has no declared minimum compute capability.")
        for gpu in gpus:
            reasons = []
            if gpu["active_allocations"]:
                reasons.append("Device has active compute allocations; no process will be stopped.")
            if minimum_bytes and gpu["free_vram_bytes"] < minimum_bytes:
                reasons.append("Free VRAM is below the selected model/runtime requirement.")
            if minimum_driver is not None and not _at_least(gpu["driver_version"], minimum_driver):
                reasons.append("Driver does not satisfy the pinned runtime minimum.")
            if minimum_compute is not None and not _at_least(
                gpu["compute_capability"], minimum_compute
            ):
                reasons.append("Compute capability does not satisfy the pinned runtime minimum.")
            gpu["blockers"] = reasons
        chosen = gpus
        if config.get("gpu_index") is not None:
            chosen = [gpu for gpu in chosen if gpu["index"] == config["gpu_index"]]
        if config.get("gpu_uuid") is not None:
            chosen = [gpu for gpu in chosen if gpu["uuid"] == config["gpu_uuid"]]
        eligible = [gpu for gpu in chosen if not gpu["blockers"]]
        if eligible:
            selected = max(eligible, key=lambda gpu: (gpu["free_vram_bytes"], -gpu["index"]))
        elif chosen:
            for gpu in chosen:
                for reason in gpu["blockers"]:
                    if reason not in blockers:
                        blockers.append(reason)
        elif gpus:
            blockers.append("The explicitly selected GPU index/UUID is unavailable or changed.")
        for key, actual, label in (
            ("min_host_ram_gib", snapshot.get("available_ram_bytes"), "Available system RAM"),
            (
                "min_free_disk_gib",
                snapshot.get("disk_free_bytes", {}).get("data_root"),
                "Free case storage",
            ),
        ):
            minimum = requirements.get(key)
            if not _number(minimum):
                warnings.append(f"{label} sizing is unvalidated; no minimum was invented.")
            elif type(actual) is not int or actual < minimum * GIB:
                blockers.append(f"{label} does not meet the pinned workload minimum.")
        resource_free = snapshot.get("disk_free_bytes", {}).get("resources_root")
        if type(resource_free) is int and resource_free < unprepared_bytes:
            blockers.append("Free resource storage is below the unprepared public asset inventory.")
        if unknown_sizes:
            warnings.append(
                "Some public resource sizes are unknown; preparation must verify actual free space."
            )
        warnings.append(
            "Hardware qualification is not a performance, five-minute SLA or analysis-quality "
            "acceptance. Startup must verify the actual multimodal workload."
        )
    blockers = unsupported + blockers
    can_attempt = not blockers and (mode == "attach" or selected is not None)
    sizing_known = all(
        _number(requirements.get(key))
        for key in ("min_gpu_vram_gib", "min_host_ram_gib", "min_free_disk_gib")
    ) and all(
        requirements.get(key) is not None
        for key in ("min_driver_version", "min_compute_capability")
    )
    status = (
        "unsupported"
        if unsupported
        else "blocked"
        if not can_attempt
        else "compatible"
        if mode == "attach" or (tested_os and sizing_known)
        else "candidate"
    )
    return {
        "schema_version": 1,
        "backend": backend,
        "status": status,
        "can_attempt": can_attempt,
        "blockers": blockers,
        "warnings": warnings,
        "gpus": gpus,
        "selected_gpu": selected,
        "resource_qualification": qualification,
    }
