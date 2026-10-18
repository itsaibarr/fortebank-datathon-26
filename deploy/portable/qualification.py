"""Bounded, offline, scratch-only first load of the pinned core image.

This is an administrator qualification action, not application activation. It
does not open ingress, mount existing cases, submit uploads, change acceptance
flags or claim browser access. The immutable image owns its synthetic visual
warmup; only its fixed application readiness endpoint is queried here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

LABEL = "org.forte.qualification"
CONTAINER = re.compile(r"[0-9a-f]{64}")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}")
READY = """import json,sys,urllib.request
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs): return None
try:
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 with opener.open('http://127.0.0.1:8000/health/ready',timeout=2) as response:
  raw=response.read(4097)
  payload=json.loads(raw)
  ok=(response.status==200 and len(raw)<=4096
      and isinstance(payload,dict) and payload.get('status')=='ready')
 sys.exit(0 if ok else 1)
except Exception:
 sys.exit(1)
"""


class QualificationError(Exception):
    """Only fixed, sanitized operational messages may reach the receipt."""


class LocalDriver:
    def run(self, arguments, *, timeout):
        return subprocess.run(
            arguments, capture_output=True, text=True, timeout=timeout, check=False
        )


def _hardware(config, manifest, probe):
    path = Path(__file__).resolve().parents[2] / "tools/forte-admin/forte_admin/hardware.py"
    spec = importlib.util.spec_from_file_location("forte_qualification_hardware", path)
    if spec is None or spec.loader is None:
        raise QualificationError("Hardware diagnostics are unavailable.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.inspect_host(config, manifest, probe=probe)


def _local_only(config):
    try:
        origin = urllib.parse.urlsplit(config.get("origin", ""))
        return (
            config.get("mode") == "private"
            and config.get("bind_address", "127.0.0.1") == "127.0.0.1"
            and origin.scheme == "https"
            and origin.hostname in {"localhost", "127.0.0.1", "::1"}
            and not origin.username
            and not origin.password
            and origin.path in {"", "/"}
            and not origin.query
            and not origin.fragment
            and config.get("multi_user_uploads", False) is False
        )
    except (TypeError, ValueError):
        return False


def _target(path):
    absolute = Path(path).absolute()
    for parent in (absolute, *absolute.parents):
        if parent.is_symlink() or (parent / ".git").exists():
            raise QualificationError("Qualification scratch must be outside Git and symlink paths.")
    if absolute.exists() and not absolute.is_dir():
        raise QualificationError("Qualification target must be an administrator directory.")
    return absolute


def _run(driver, arguments, timeout=15):
    try:
        return driver.run(arguments, timeout=max(0.1, timeout))
    except (OSError, subprocess.TimeoutExpired):
        raise QualificationError(
            "A bounded local container operation failed or timed out."
        ) from None


def _find(driver, project, timeout=15):
    result = _run(
        driver,
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        timeout,
    )
    values = result.stdout.split()
    if result.returncode or len(values) > 1 or any(not CONTAINER.fullmatch(v) for v in values):
        raise QualificationError("Scratch container identity could not be established safely.")
    return values[0] if values else None


def _verify(driver, container, config, token, image_id, timeout=15):
    result = _run(driver, ["docker", "inspect", container], timeout)
    try:
        item = json.loads(result.stdout)[0]
        labels = item["Config"]["Labels"]
        requests = item["HostConfig"]["DeviceRequests"]
        if (
            result.returncode
            or item["Id"] != container
            or labels.get("com.docker.compose.project") != config["project_name"]
            or labels.get("com.docker.compose.service") != "core"
            or labels.get(LABEL) != token
            or item["Image"] != image_id
            or item["HostConfig"]["NetworkMode"] != "none"
            or item["HostConfig"].get("PortBindings")
            or len(requests) != 1
            or requests[0].get("DeviceIDs") != [config["gpu_uuid"]]
        ):
            raise ValueError
        data = [mount for mount in item["Mounts"] if mount.get("Destination") == "/data"]
        if (
            len(data) != 1
            or data[0].get("Source") != config["data_root"]
            or data[0].get("RW") is not True
            or any(mount.get("RW") for mount in item["Mounts"] if mount not in data)
        ):
            raise ValueError
        return item
    except (ValueError, IndexError, KeyError, TypeError):
        raise QualificationError(
            "Scratch container labels, image, GPU, mounts or offline identity do not match; "
            "foreign services will not be changed."
        ) from None


def _core_only(config, scratch, token):
    path = scratch / "compose.json"
    try:
        compose = json.loads(path.read_text())
        core = compose["services"]["core"]
        devices = core.get("gpus", [])
        if (
            compose["name"] != config["project_name"]
            or core["image"] != config["core_image"]
            or core["network_mode"] != "none"
            or core.get("ports")
            or core.get("networks")
            or core.get("build")
            or len(devices) != 1
            or devices[0].get("driver") != "nvidia"
            or devices[0].get("device_ids") != [config["gpu_uuid"]]
            or core.get("logging", {}).get("driver") != "none"
            or "FORTE_TRUSTED_GATEWAY_TOKEN_FILE" in core.get("environment", {})
            or (scratch / "session-config.json").exists()
        ):
            raise ValueError
        for variable in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
            if core.get("environment", {}).get(variable) != "1":
                raise ValueError
        mounts = core["volumes"]
        data = [mount for mount in mounts if mount.get("target") == "/data"]
        if (
            len(data) != 1
            or data[0].get("source") != config["data_root"]
            or data[0].get("read_only", False)
            or any(not mount.get("read_only", False) for mount in mounts if mount not in data)
        ):
            raise ValueError
        resource_root = Path(config["resources_root"]).resolve()
        key_path = (Path(config["secrets_root"]) / "core-api.key").resolve()
        for mount in mounts:
            if mount in data:
                continue
            source = Path(mount["source"]).resolve()
            if source != key_path and not source.is_relative_to(resource_root):
                raise ValueError
        core["labels"] = {LABEL: token}
        core["restart"] = "no"
        compose = {"name": config["project_name"], "services": {"core": core}}
        path.write_text(json.dumps(compose, indent=2) + "\n")
        path.chmod(0o600)
    except (OSError, ValueError, KeyError, TypeError):
        raise QualificationError(
            "Rendered scratch core is not isolated; no container was started."
        ) from None


def qualify(
    config,
    target,
    runtime,
    *,
    driver=None,
    clock=time.monotonic,
    wait=time.sleep,
    hardware_probe=None,
):
    """Run and remove only a newly created, label-verified, offline scratch core."""
    driver = driver or LocalDriver()
    report = {
        "ok": False,
        "core_ready": False,
        "qualification_complete": False,
        "services_stopped": True,
        "browser_access_verified": False,
        "externally_verified": False,
        "acceptance_flags_changed": False,
        "existing_cases_mounted": False,
        "errors": [],
    }
    scratch, candidate, token, image_id = None, None, None, None
    launched = False
    try:
        if not _local_only(config):
            raise QualificationError(
                "First-load qualification requires private mode, literal loopback bind/origin "
                "and disabled multi-user uploads."
            )
        timeout = config.get("qualification_timeout", 360)
        if type(timeout) is not int or not 1 <= timeout <= 900:
            raise QualificationError("qualification_timeout must be 1–900 seconds.")
        errors = runtime.prerequisites(config, qualification=True)
        if errors:
            report["errors"] = errors
            return report
        manifest, _ = runtime._load_manifest(config)
        for name in ("resources_root", "secrets_root"):
            if not Path(config[name]).is_dir():
                raise QualificationError(
                    "Prepared public resources and private secrets are required."
                )
        resource_root = Path(config["resources_root"]).resolve()
        case_root = Path(config["data_root"]).resolve()
        if resource_root.is_relative_to(case_root) or case_root.is_relative_to(resource_root):
            raise QualificationError("Public resources and existing case storage must not overlap.")
        target = _target(target)
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        scratch = Path(tempfile.mkdtemp(prefix="qualification-", dir=target))
        scratch.chmod(0o700)
        data = scratch / "data"
        data.mkdir(mode=0o700)
        token = secrets.token_hex(12)
        candidate = dict(config, project_name=f"forte-q-{token}", data_root=str(data))
        hardware = _hardware(candidate, manifest, hardware_probe)
        if not hardware["can_attempt"]:
            report["errors"] = hardware["blockers"]
            return report
        gpu = hardware["selected_gpu"]
        candidate.update(gpu_index=gpu["index"], gpu_uuid=gpu["uuid"])
        report["selected_gpu"] = {"index": gpu["index"], "uuid": gpu["uuid"]}
        report["warnings"] = hardware["warnings"]
        runtime.render(candidate, scratch, qualification=True)
        _core_only(candidate, scratch, token)
        image = _run(
            driver, ["docker", "image", "inspect", candidate["core_image"], "--format", "{{.Id}}"]
        )
        image_id = image.stdout.strip()
        if image.returncode or not IMAGE.fullmatch(image_id):
            raise QualificationError(
                "Pinned core image is not prepared locally; no image was pulled."
            )
        if candidate["core_image"].startswith("sha256:") and candidate["core_image"] != image_id:
            raise QualificationError("Prepared image identity differs from the pinned core image.")
        if _find(driver, candidate["project_name"]) is not None:
            raise QualificationError(
                "Scratch project already has a service; no existing service was changed."
            )
        deadline = clock() + timeout
        command = [
            "docker",
            "compose",
            "--project-name",
            candidate["project_name"],
            "--file",
            str(scratch / "compose.json"),
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "core",
        ]
        launched = True
        report["services_stopped"] = False
        started = _run(driver, command, min(120, deadline - clock()))
        if started.returncode:
            raise QualificationError("Scratch core startup failed; sensitive output was withheld.")
        container = _find(driver, candidate["project_name"], min(15, deadline - clock()))
        if container is None:
            raise QualificationError("Scratch core container is unavailable after startup.")
        while clock() < deadline:
            item = _verify(
                driver, container, candidate, token, image_id, min(15, deadline - clock())
            )
            if not item.get("State", {}).get("Running"):
                raise QualificationError("Scratch core exited during model load or visual warmup.")
            ready = _run(
                driver,
                ["docker", "exec", container, "python3", "-c", READY],
                min(8, deadline - clock()),
            )
            if ready.returncode == 0:
                report["core_ready"] = True
                break
            wait(min(2, max(0, deadline - clock())))
        if not report["core_ready"]:
            raise QualificationError(
                "Actual model load and visual warmup did not become ready within the bound."
            )
    except QualificationError as exc:
        report["errors"].append(str(exc))
    except KeyboardInterrupt:
        report["errors"].append("Qualification interrupted; scratch service cleanup was attempted.")
    except Exception:
        report["errors"].append(
            "Local qualification failed; sensitive operational output was withheld."
        )
    finally:
        if launched:
            try:
                container = _find(driver, candidate["project_name"])
                if container is not None:
                    _verify(driver, container, candidate, token, image_id)
                    removed = _run(driver, ["docker", "rm", "--force", container], timeout=30)
                    if removed.returncode or _find(driver, candidate["project_name"]) is not None:
                        raise QualificationError(
                            "Owned scratch service removal could not be verified."
                        )
                report["services_stopped"] = True
            except (Exception, KeyboardInterrupt):
                report["services_stopped"] = False
                report["errors"].append(
                    "Scratch cleanup could not verify ownership or removal. No foreign service "
                    "was stopped; administrator inspection is required."
                )
        report["qualification_complete"] = (
            report["core_ready"] and report["services_stopped"] and not report["errors"]
        )
        report["ok"] = report["qualification_complete"]
        if scratch is not None:
            report["receipt_path"] = str(scratch / "qualification.json")
            try:
                path = scratch / "qualification.json"
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    json.dump(report, stream, indent=2)
                    stream.write("\n")
            except OSError:
                report["ok"] = report["qualification_complete"] = False
                report["errors"].append("Sanitized qualification receipt could not be preserved.")
    return report
