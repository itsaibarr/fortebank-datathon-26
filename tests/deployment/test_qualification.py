"""Synthetic qualification isolation, ownership and cleanup; no actual GPU runs."""

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "forte_qualification_test", ROOT / "deploy/portable/qualification.py"
)
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)
IMAGE = "sha256:" + "1" * 64
CONTAINER = "2" * 64
GIB = 1024**3


class Clock:
    def __init__(self):
        self.current = 0
        self.waits = []

    def now(self):
        return self.current

    def wait(self, seconds):
        self.waits.append(seconds)
        self.current += seconds


class Runtime:
    def __init__(self):
        self.errors = []
        self.prerequisite_calls = []
        self.config = None
        self.manifest = {
            "runtime": {"requirements": {}},
            "assets": [],
            "verification": {"release": False, "model_workload": False},
        }

    def prerequisites(self, config, **options):
        self.prerequisite_calls.append(options)
        return self.errors

    def _load_manifest(self, config):
        return self.manifest, "3" * 64

    def render(self, config, target, *, qualification=False):
        assert qualification is True
        self.config = config
        core = {
            "image": config["core_image"],
            "network_mode": "none",
            "restart": "unless-stopped",
            "gpus": [{"driver": "nvidia", "device_ids": [config["gpu_uuid"]]}],
            "logging": {"driver": "none"},
            "volumes": [
                {"source": config["data_root"], "target": "/data"},
                {"source": config["resources_root"], "target": "/resources", "read_only": True},
            ],
            "environment": {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
            },
        }
        (target / "compose.json").write_text(
            json.dumps({"name": config["project_name"], "services": {"core": core, "ingress": {}}})
        )


class Driver:
    def __init__(self, runtime):
        self.runtime = runtime
        self.container = None
        self.calls = []
        self.removed = []
        self.compose = None
        self.ready_after = 1
        self.ready_calls = 0
        self.interrupt = False
        self.foreign = None
        self.start_failure = False
        self.start_timeout = False
        self.existing = False
        self.cleanup_failure = False
        self.image_id = IMAGE

    def run(self, arguments, *, timeout):
        self.calls.append((arguments, timeout))
        code, raw = 0, ""
        if arguments[1:3] == ["image", "inspect"]:
            raw = self.image_id
        elif arguments[1] == "ps":
            raw = CONTAINER if self.container is not None or self.existing else ""
        elif arguments[1] == "compose":
            path = Path(arguments[arguments.index("--file") + 1])
            self.compose = json.loads(path.read_text())
            config = self.runtime.config
            labels = {
                "com.docker.compose.project": config["project_name"],
                "com.docker.compose.service": "core",
                **self.compose["services"]["core"]["labels"],
            }
            self.container = {
                "Id": CONTAINER,
                "Image": IMAGE,
                "Config": {"Labels": labels},
                "HostConfig": {
                    "NetworkMode": "none",
                    "PortBindings": {},
                    "DeviceRequests": [{"DeviceIDs": [config["gpu_uuid"]]}],
                },
                "Mounts": [
                    {"Source": config["data_root"], "Destination": "/data", "RW": True},
                    {"Source": config["resources_root"], "Destination": "/resources", "RW": False},
                ],
                "State": {"Running": True},
            }
            if self.foreign:
                self.foreign(self.container)
            if self.start_timeout:
                raise subprocess.TimeoutExpired(arguments, timeout, output="private-output")
            code = 1 if self.start_failure else 0
        elif arguments[1] == "inspect":
            raw = json.dumps([self.container])
        elif arguments[1] == "exec":
            if self.interrupt:
                raise KeyboardInterrupt
            self.ready_calls += 1
            code = 0 if self.ready_calls >= self.ready_after else 1
        elif arguments[1] == "rm":
            if self.cleanup_failure:
                code = 1
            else:
                self.removed.append(arguments[-1])
                self.container = None
        else:
            raise AssertionError(f"Unexpected operation {arguments[:2]}")
        return subprocess.CompletedProcess(arguments, code, stdout=raw, stderr="private-output")


@pytest.fixture
def setup(tmp_path):
    resources, secrets, cases = [tmp_path / name for name in ("resources", "secrets", "cases")]
    for path in (resources, secrets, cases):
        path.mkdir()
    (cases / "case.json").write_text("private-case-content")
    (secrets / "core-api.key").write_text("private-secret-never-log")
    config = {
        "mode": "private",
        "project_name": "real-installation",
        "origin": "https://localhost:8443",
        "bind_address": "127.0.0.1",
        "multi_user_uploads": False,
        "core_image": IMAGE,
        "resources_root": str(resources),
        "secrets_root": str(secrets),
        "data_root": str(cases),
        "qualification_timeout": 5,
    }
    host = {
        "system": {"os": "Linux", "arch": "x86_64", "distribution": "ubuntu", "version": "24.04"},
        "docker": {"available": True, "engine": True, "compose": True, "nvidia_runtime": True},
        "available_ram_bytes": 100 * GIB,
        "disk_free_bytes": {
            key: 200 * GIB for key in ("data_root", "resources_root", "secrets_root")
        },
        "gpu_probe_ok": True,
        "allocation_probe_ok": True,
        "allocations": {},
        "gpus": [
            {
                "index": 1,
                "uuid": "GPU-synthetic-1",
                "name": "NVIDIA compatible device",
                "total_vram_bytes": 96 * GIB,
                "free_vram_bytes": 94 * GIB,
                "driver_version": "590.10",
                "compute_capability": "9.0",
            }
        ],
    }
    runtime, clock = Runtime(), Clock()
    return config, tmp_path / "installation", runtime, Driver(runtime), clock, host


def qualify(setup):
    config, target, runtime, driver, clock, host = setup
    return qualification.qualify(
        config,
        target,
        runtime,
        driver=driver,
        clock=clock.now,
        wait=clock.wait,
        hardware_probe=host,
    )


def test_success_only_starts_offline_scratch_core_and_always_removes_it(setup):
    config, _, runtime, driver, _, _ = setup
    before = copy.deepcopy(config)
    report = qualify(setup)
    assert report["ok"] and report["core_ready"] and report["qualification_complete"]
    assert report["services_stopped"]
    assert report["browser_access_verified"] is report["externally_verified"] is False
    assert report["acceptance_flags_changed"] is report["existing_cases_mounted"] is False
    assert "origin" not in report and "application_url" not in report
    assert config == before
    assert runtime.prerequisite_calls == [{"qualification": True}]
    assert runtime.manifest["verification"] == {"release": False, "model_workload": False}
    assert set(driver.compose["services"]) == {"core"}
    assert driver.compose["services"]["core"]["restart"] == "no"
    assert driver.removed == [CONTAINER]
    start = next(arguments for arguments, _ in driver.calls if arguments[1] == "compose")
    assert start[-1] == "core" and start[start.index("--pull") + 1] == "never"
    assert "--no-deps" in start and "--no-build" in start


def test_existing_case_secret_and_corrections_are_untouched(setup):
    config, _, runtime, _, _, _ = setup
    watched = [
        Path(config["data_root"]) / "case.json",
        Path(config["secrets_root"]) / "core-api.key",
    ]
    before = {path: path.read_bytes() for path in watched}
    report = qualify(setup)
    assert report["ok"]
    assert runtime.config["data_root"] != config["data_root"]
    assert Path(runtime.config["data_root"]).is_dir()
    assert os.stat(runtime.config["data_root"]).st_mode & 0o777 == 0o700
    assert {path: path.read_bytes() for path in watched} == before
    assert "private-case" not in json.dumps(report)
    assert "private-secret" not in json.dumps(report)
    assert "private-output" not in json.dumps(report)
    receipt = Path(report["receipt_path"])
    assert receipt.exists() and receipt.stat().st_mode & 0o777 == 0o600
    assert json.loads(receipt.read_text()) == report


def test_fixed_internal_application_readiness_only_no_modelport_or_hostbridge(setup):
    _, _, _, driver, _, _ = setup
    assert qualify(setup)["ok"]
    execute = [arguments for arguments, _ in driver.calls if arguments[1] == "exec"]
    assert execute and all(arguments[2:5] == [CONTAINER, "python3", "-c"] for arguments in execute)
    assert "127.0.0.1:8000/health/ready" in execute[0][-1]
    assert "8001" not in execute[0][-1]
    assert all(
        arguments[1] not in {"port", "logs", "restart", "stop"} for arguments, _ in driver.calls
    )


def test_timeout_stops_owned_scratch_core_and_preserves_receipt(setup):
    _, _, _, driver, clock, _ = setup
    driver.ready_after = 100
    report = qualify(setup)
    assert not report["ok"] and not report["core_ready"]
    assert report["services_stopped"] and driver.removed == [CONTAINER]
    assert any("within the bound" in error for error in report["errors"])
    assert clock.current == 5 and max(clock.waits) <= 2
    assert Path(report["receipt_path"]).exists()


@pytest.mark.parametrize("failure", ["start_failure", "start_timeout", "interrupt"])
def test_start_failure_timeout_and_interruption_all_cleanup(setup, failure):
    _, _, _, driver, _, _ = setup
    setattr(driver, failure, True)
    report = qualify(setup)
    assert not report["ok"] and report["services_stopped"]
    assert driver.removed == [CONTAINER]
    assert "private-output" not in json.dumps(report)


@pytest.mark.parametrize("identity", ["project", "token", "image", "network", "gpu", "mount"])
def test_foreign_or_changed_container_is_never_removed(setup, identity):
    _, _, _, driver, _, _ = setup

    def change(item):
        if identity == "project":
            item["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
        elif identity == "token":
            item["Config"]["Labels"][qualification.LABEL] = "foreign"
        elif identity == "image":
            item["Image"] = "sha256:" + "f" * 64
        elif identity == "network":
            item["HostConfig"]["NetworkMode"] = "host"
        elif identity == "gpu":
            item["HostConfig"]["DeviceRequests"][0]["DeviceIDs"] = ["GPU-foreign"]
        elif identity == "mount":
            item["Mounts"][0]["Source"] = "/private/foreign-cases"

    driver.foreign = change
    report = qualify(setup)
    assert not report["ok"] and not report["services_stopped"]
    assert not driver.removed
    assert not any(arguments[1] == "exec" for arguments, _ in driver.calls)


def test_existing_project_collision_is_refused_without_touching_it(setup):
    _, _, _, driver, _, _ = setup
    driver.existing = True
    report = qualify(setup)
    assert not report["ok"] and report["services_stopped"]
    assert not driver.removed
    assert not any(arguments[1] == "compose" for arguments, _ in driver.calls)


def test_cleanup_failure_is_honest_even_when_core_ready(setup):
    _, _, _, driver, _, _ = setup
    driver.cleanup_failure = True
    report = qualify(setup)
    assert report["core_ready"] and not report["services_stopped"] and not report["ok"]
    assert not report["qualification_complete"]


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "attach"},
        {"bind_address": "0.0.0.0"},
        {"origin": "https://example.invalid"},
        {"origin": "https://localhost.evil.invalid"},
        {"multi_user_uploads": True},
    ],
)
def test_nonlocal_or_multiuser_qualification_is_refused_without_mutation(setup, changes):
    config, target, _, driver, _, _ = setup
    config.update(changes)
    assert not qualify(setup)["ok"]
    assert not target.exists() and not driver.calls


@pytest.mark.parametrize("timeout", [0, -1, 901, True, 1.5])
def test_runtime_bound_is_explicit_and_limited(setup, timeout):
    config, target, _, driver, _, _ = setup
    config["qualification_timeout"] = timeout
    assert not qualify(setup)["ok"]
    assert not target.exists() and not driver.calls


def test_security_and_resource_prerequisite_errors_block_before_start(setup):
    _, target, runtime, driver, _, _ = setup
    runtime.errors = ["a pinned resource file failed SHA256 verification"]
    report = qualify(setup)
    assert not report["ok"] and report["errors"] == runtime.errors
    assert runtime.prerequisite_calls == [{"qualification": True}]
    assert not target.exists() and not driver.calls


def test_in_git_scratch_target_is_refused(setup):
    config, _, runtime, driver, clock, host = setup
    report = qualification.qualify(
        config,
        ROOT / ".synthetic-qualification",
        runtime,
        driver=driver,
        clock=clock.now,
        wait=clock.wait,
        hardware_probe=host,
    )
    assert not report["ok"] and not driver.calls
    assert not (ROOT / ".synthetic-qualification").exists()


def test_explicit_gpu_selection_is_preserved_and_busy_device_is_not_replaced(setup):
    config, _, _, driver, _, host = setup
    config.update(gpu_index=1, gpu_uuid="GPU-synthetic-1")
    host["allocations"] = {"GPU-synthetic-1": 1}
    report = qualify(setup)
    assert not report["ok"]
    assert not driver.calls


def test_no_prepared_image_means_no_pull_or_start(setup):
    _, _, _, driver, _, _ = setup
    driver.image_id = "not-installed"
    assert not qualify(setup)["ok"]
    assert not any(arguments[1] in {"compose", "pull", "run"} for arguments, _ in driver.calls)


def test_second_run_uses_different_project_and_scratch_without_promoting_acceptance(setup):
    config, _, runtime, driver, _, _ = setup
    original = copy.deepcopy(config)
    first = qualify(setup)
    first_project = runtime.config["project_name"]
    second = qualify(setup)
    assert first["ok"] and second["ok"]
    assert first["receipt_path"] != second["receipt_path"]
    assert first_project != runtime.config["project_name"]
    assert config == original and driver.removed == [CONTAINER, CONTAINER]


def test_resource_mount_cannot_include_existing_case_storage(setup):
    config, _, _, driver, _, _ = setup
    config["resources_root"] = str(Path(config["data_root"]).parent)
    report = qualify(setup)
    assert not report["ok"] and not driver.calls
    assert any("must not overlap" in error for error in report["errors"])


@pytest.fixture
def actual_runtime(setup):
    config, _, _, driver, _, _ = setup
    spec = importlib.util.spec_from_file_location(
        "forte_qualification_runtime_test", ROOT / "deploy/portable/runtime.py"
    )
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    secret = Path(config["secrets_root"]) / "core-api.key"
    secret.write_text("a" * 48)
    resource = Path(config["resources_root"]) / "synthetic-resource.json"
    resource.write_text('{"synthetic":true}')
    manifest = {
        "schema_version": 1,
        "core": {"commit": "3" * 40, "image": IMAGE, "contract_sha256": "4" * 64},
        "model": {
            "identity": "synthetic",
            "revision": "test-only",
            "profile": "synthetic",
            "frozen": True,
        },
        "corpus": {"version": "synthetic"},
        "runtime": {"ipc": "host", "environment": {}},
        "assets": [
            {"path": resource.name, "sha256": hashlib.sha256(resource.read_bytes()).hexdigest()}
        ],
        "verification": {
            "release": False,
            "model_workload": False,
            "offline_analysis": False,
            "browser_session": False,
            "ownership": False,
            "receipt": "missing-receipt.json",
        },
    }
    path = Path(config["resources_root"]).parent / "integration.json"
    path.write_text(json.dumps(manifest))
    config.update(
        schema_version=1,
        https_port=8443,
        bridge_port=18001,
        access_mode="browser-session",
        proxy_image="sha256:" + "9" * 64,
        integration_manifest=str(path),
        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        tls_cert=str(secret.parent / "missing.crt"),
        tls_key=str(secret.parent / "missing.key"),
    )
    original_render = runtime.render

    def render(config, target, *, qualification=False):
        driver.runtime.config = config
        return original_render(config, target, qualification=qualification)

    runtime.render = render
    return runtime, manifest, path, resource, secret


def test_actual_runtime_qualifies_without_tls_or_false_acceptance_promotion(setup, actual_runtime):
    config, target, _, driver, clock, host = setup
    runtime, manifest, path, _, _ = actual_runtime
    before = path.read_bytes()
    assert runtime.prerequisites(config, qualification=True) == []
    assert runtime.prerequisites(config)
    report = qualification.qualify(
        config,
        target,
        runtime,
        driver=driver,
        clock=clock.now,
        wait=clock.wait,
        hardware_probe=host,
    )
    assert report["ok"] and report["services_stopped"]
    assert path.read_bytes() == before
    scratch = Path(report["receipt_path"]).parent
    assert not (scratch / "session-config.json").exists()
    assert not (scratch / "session-daemon.json").exists()
    core = driver.compose["services"]["core"]
    assert "FORTE_TRUSTED_GATEWAY_TOKEN_FILE" not in core["environment"]
    assert not any(mount["target"] == "/run/secrets/gateway-token" for mount in core["volumes"])
    assert all(
        value is False for key, value in manifest["verification"].items() if key != "receipt"
    )


@pytest.mark.parametrize("invalid", ["core", "model", "corpus", "resource", "key", "manifest"])
def test_actual_runtime_preserves_provenance_resource_and_key_gates(setup, actual_runtime, invalid):
    config, target, _, driver, clock, host = setup
    runtime, manifest, path, resource, secret = actual_runtime
    if invalid == "core":
        manifest["core"]["commit"] = "not-a-stable-commit"
    elif invalid == "model":
        manifest["model"]["frozen"] = False
    elif invalid == "corpus":
        manifest["corpus"] = {}
    elif invalid == "resource":
        resource.write_text("changed")
    elif invalid == "key":
        secret.write_text("short")
    elif invalid == "manifest":
        config["manifest_sha256"] = "0" * 64
    if invalid in {"core", "model", "corpus"}:
        path.write_text(json.dumps(manifest))
        config["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = qualification.qualify(
        config,
        target,
        runtime,
        driver=driver,
        clock=clock.now,
        wait=clock.wait,
        hardware_probe=host,
    )
    assert not report["ok"] and not driver.calls
    assert not target.exists()
