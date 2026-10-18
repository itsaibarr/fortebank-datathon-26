"""Synthetic host facts exercise capability qualification without starting a GPU."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "forte_hardware_test", ROOT / "tools/forte-admin/forte_admin/hardware.py"
)
hardware = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hardware)


@pytest.fixture
def host():
    return {
        "system": {
            "os": "Linux",
            "arch": "x86_64",
            "distribution": "ubuntu",
            "version": "24.04",
        },
        "docker": {
            "available": True,
            "engine": True,
            "compose": True,
            "nvidia_runtime": True,
            "local_engine": True,
        },
        "available_ram_bytes": 100 * hardware.GIB,
        "disk_free_bytes": {
            key: 200 * hardware.GIB for key in ("data_root", "resources_root", "secrets_root")
        },
        "gpu_probe_ok": True,
        "allocation_probe_ok": True,
        "allocations": {},
        "gpus": [
            {
                "index": 0,
                "uuid": "GPU-synthetic-0",
                "name": "NVIDIA Different Model",
                "total_vram_bytes": 96 * hardware.GIB,
                "free_vram_bytes": 94 * hardware.GIB,
                "driver_version": "590.10.2",
                "compute_capability": "9.0",
            }
        ],
    }


@pytest.fixture
def manifest():
    return {
        "runtime": {
            "requirements": {
                "min_driver_version": "570.10",
                "min_compute_capability": "8.0",
                "min_gpu_vram_gib": 72,
                "min_host_ram_gib": 64,
                "min_free_disk_gib": 100,
            }
        },
        "assets": [
            {"path": "models/model-1.safetensors", "size_bytes": 52 * hardware.GIB},
            {"path": "legal/corpus.json", "size_bytes": 1024},
        ],
        "verification": {"model_workload": True},
    }


def inspect(host, manifest, **config):
    return hardware.inspect_host({"mode": "private", **config}, manifest, probe=host)


def test_compatible_device_does_not_need_tested_gpu_name_or_driver_family(host, manifest):
    report = inspect(host, manifest)
    assert report["can_attempt"]
    assert report["status"] == "compatible"
    assert report["selected_gpu"]["index"] == 0
    assert report["resource_qualification"]["verified_workload"] is False
    assert report["resource_qualification"]["release_workload_receipt"] is True


def test_unknown_sizing_is_candidate_not_named_host_refusal(host, manifest):
    manifest["runtime"]["requirements"] = {
        "min_host_ram_gib": None,
        "min_free_disk_gib": None,
        "driver_major": None,
    }
    report = inspect(host, manifest)
    assert report["can_attempt"] and report["status"] == "candidate"
    assert report["resource_qualification"]["requires_bounded_model_warmup"]
    assert any("lower bound" in warning for warning in report["warnings"])
    assert any("system RAM" in warning for warning in report["warnings"])


def test_other_linux_distro_is_unvalidated_candidate(host, manifest):
    host["system"].update(distribution="debian", version="13")
    report = inspect(host, manifest)
    assert report["can_attempt"] and report["status"] == "candidate"
    assert any("unvalidated" in warning for warning in report["warnings"])


def test_multiple_devices_selects_single_suitable_free_device(host, manifest):
    second = copy.deepcopy(host["gpus"][0])
    second.update(index=1, uuid="GPU-synthetic-1")
    host["gpus"].append(second)
    host["allocations"]["GPU-synthetic-0"] = 2
    report = inspect(host, manifest)
    assert report["can_attempt"]
    assert report["selected_gpu"]["index"] == 1
    assert report["gpus"][0]["active_allocations"] == 2


def test_explicit_selected_device_is_not_replaced_when_busy(host, manifest):
    second = copy.deepcopy(host["gpus"][0])
    second.update(index=1, uuid="GPU-synthetic-1")
    host["gpus"].append(second)
    host["allocations"]["GPU-synthetic-0"] = 1
    report = inspect(host, manifest, gpu_index=0)
    assert not report["can_attempt"] and report["status"] == "blocked"
    assert report["selected_gpu"] is None
    assert any("active compute" in blocker for blocker in report["blockers"])


def test_gpu_uuid_prevents_changed_index_binding(host, manifest):
    report = inspect(host, manifest, gpu_index=0, gpu_uuid="GPU-previous-device")
    assert not report["can_attempt"]
    assert any("unavailable or changed" in blocker for blocker in report["blockers"])


def test_free_vram_not_total_vram_determines_headroom(host, manifest):
    host["gpus"][0]["free_vram_bytes"] = 60 * hardware.GIB
    report = inspect(host, manifest)
    assert not report["can_attempt"]
    assert any("Free VRAM" in blocker for blocker in report["blockers"])


def test_incompatible_small_devices_are_never_aggregated(host, manifest):
    for index in range(4):
        gpu = copy.deepcopy(host["gpus"][0])
        gpu.update(
            index=index,
            uuid=f"GPU-synthetic-{index}",
            total_vram_bytes=24 * hardware.GIB,
            free_vram_bytes=23 * hardware.GIB,
        )
        if index == 0:
            host["gpus"] = []
        host["gpus"].append(gpu)
    assert not inspect(host, manifest)["can_attempt"]


def test_weights_alone_establish_lower_bound_when_headroom_unknown(host, manifest):
    manifest["runtime"]["requirements"]["min_gpu_vram_gib"] = None
    host["gpus"][0]["free_vram_bytes"] = 40 * hardware.GIB
    assert not inspect(host, manifest)["can_attempt"]


@pytest.mark.parametrize("minimum,actual", [("570.20", "570.10"), ("580.1", "570.100")])
def test_pinned_driver_minimum_is_numeric(host, manifest, minimum, actual):
    manifest["runtime"]["requirements"]["min_driver_version"] = minimum
    host["gpus"][0]["driver_version"] = actual
    assert not inspect(host, manifest)["can_attempt"]


def test_legacy_driver_major_is_minimum_not_exact_family(host, manifest):
    requirements = manifest["runtime"]["requirements"]
    del requirements["min_driver_version"]
    requirements["driver_major"] = 570
    assert inspect(host, manifest)["can_attempt"]


@pytest.mark.parametrize("capability", ["7.5", None, "unavailable"])
def test_pinned_compute_capability_is_enforced(host, manifest, capability):
    host["gpus"][0]["compute_capability"] = capability
    assert not inspect(host, manifest)["can_attempt"]


def test_ram_alone_does_not_create_cpu_fallback(host, manifest):
    host["gpus"] = []
    report = inspect(host, manifest)
    assert report["status"] == "unsupported" and not report["can_attempt"]
    assert any("System RAM alone" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("backend", ["cpu", "mps", "rocm"])
def test_unimplemented_providers_are_explicit(host, manifest, backend):
    report = inspect(host, manifest, backend=backend)
    assert report["status"] == "unsupported" and not report["can_attempt"]
    assert any("separately implemented provider" in blocker for blocker in report["blockers"])


def test_unreadable_allocations_blocks_start_without_interrupting_process(host, manifest):
    host["allocation_probe_ok"] = False
    report = inspect(host, manifest)
    assert not report["can_attempt"]
    assert any("allocations could not be verified" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("minimum_key", ["min_host_ram_gib", "min_free_disk_gib"])
def test_available_ram_and_storage_below_pinned_minimum_block(host, manifest, minimum_key):
    manifest["runtime"]["requirements"][minimum_key] = 500
    assert not inspect(host, manifest)["can_attempt"]


def test_attach_never_requires_or_probes_gpu(host, manifest):
    host["gpus"] = []
    host["docker"]["nvidia_runtime"] = False
    host["gpu_probe_ok"] = host["allocation_probe_ok"] = False
    report = hardware.inspect_host({"mode": "attach"}, manifest, probe=host)
    assert report["can_attempt"] and report["backend"] == "attach"
    assert report["selected_gpu"] is None
    assert report["resource_qualification"]["requires_bounded_model_warmup"] is False


def test_native_probe_is_read_only_and_does_not_collect_process_arguments(monkeypatch):
    calls = []

    def run(arguments):
        calls.append(arguments)
        if arguments[0] == "docker":
            if "info" in arguments:
                return 0, '{"runc":{},"nvidia":{}}'
            return 0, "2.40.0"
        if "--query-compute-apps=gpu_uuid" in arguments:
            return 0, "GPU-synthetic-0\n"
        return 0, "0, GPU-synthetic-0, Different NVIDIA, 98304, 96256, 590.10.2, 9.0\n"

    monkeypatch.setattr(hardware, "_run", run)
    monkeypatch.setattr(hardware.shutil, "which", lambda _: "/usr/bin/docker")
    snapshot = hardware._native_probe({"mode": "private"})
    assert snapshot["gpus"][0]["free_vram_bytes"] == 96256 * hardware.MIB
    assert snapshot["allocations"] == {"GPU-synthetic-0": 1}
    assert all(
        arguments[1] in {"info", "compose", "context"}
        for arguments in calls
        if arguments[0] == "docker"
    )
    assert all("pid" not in " ".join(arguments) for arguments in calls)
    assert not any("run" in arguments or "stop" in arguments for arguments in calls)


def test_probe_raw_logs_pids_case_and_credentials_are_excluded(host, manifest):
    host["raw_log"] = "case-content-private-key"
    host["gpus"][0]["process_arguments"] = "private-recording.mov --credential secret"
    report = inspect(host, manifest)
    serialized = json.dumps(report)
    assert "case-content-private-key" not in serialized
    assert "private-recording" not in serialized
    assert "credential" not in serialized


def test_resource_inventory_checks_missing_asset_space_not_case_data(host, manifest, tmp_path):
    host["disk_free_bytes"]["resources_root"] = 20 * hardware.GIB
    report = inspect(host, manifest, resources_root=str(tmp_path))
    assert not report["can_attempt"]
    assert report["resource_qualification"]["resource_inventory_bytes"] > 52 * hardware.GIB
    assert any("asset inventory" in blocker for blocker in report["blockers"])


def test_existing_resource_sizes_reduce_preparation_space(host, manifest, tmp_path):
    manifest["assets"] = [{"path": "public/config.json", "size_bytes": 2}]
    target = tmp_path / "public/config.json"
    target.parent.mkdir()
    target.write_text("{}")
    report = inspect(host, manifest, resources_root=str(tmp_path))
    assert report["resource_qualification"]["resource_inventory_bytes"] == 2
    assert report["resource_qualification"]["unprepared_resource_bytes"] == 0
    assert report["resource_qualification"]["verified_workload"] is False


def test_resource_inventory_does_not_follow_symlink_outside_public_root(host, manifest, tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("{}")
    (root / "link.json").symlink_to(outside)
    manifest["assets"] = [{"path": "link.json", "size_bytes": 2}]
    report = inspect(host, manifest, resources_root=str(root))
    assert report["resource_qualification"]["unprepared_resource_bytes"] == 2


def test_pinned_minimum_does_not_understate_weight_bytes(host, manifest):
    manifest["runtime"]["requirements"]["min_gpu_vram_gib"] = 1
    host["gpus"][0]["free_vram_bytes"] = 40 * hardware.GIB
    assert not inspect(host, manifest)["can_attempt"]


def test_native_attach_does_not_query_nvidia(monkeypatch):
    calls = []

    def run(arguments):
        calls.append(arguments)
        return 127, ""

    monkeypatch.setattr(hardware, "_run", run)
    hardware._native_probe({"mode": "attach"})
    assert all(arguments[0] != "nvidia-smi" for arguments in calls)


def test_native_fallback_reports_unknown_capability_without_fabricating_it(monkeypatch):
    calls = []

    def run(arguments):
        calls.append(arguments)
        if arguments[0] == "docker":
            return 0, '{"nvidia":{}}' if "info" in arguments else "2.40.0"
        if "--query-compute-apps=gpu_uuid" in arguments:
            return 0, ""
        if "compute_cap" in " ".join(arguments):
            return 1, "unsupported query field"
        return 0, "0, GPU-synthetic-0, Different NVIDIA, 98304, 96256, 590.10.2\n"

    monkeypatch.setattr(hardware, "_run", run)
    snapshot = hardware._native_probe({"mode": "private"})
    assert snapshot["gpu_probe_ok"]
    assert snapshot["gpus"][0]["compute_capability"] is None
    assert len([arguments for arguments in calls if "--query-gpu=" in " ".join(arguments)]) == 2


def test_native_unknown_allocation_does_not_become_empty_gpu(monkeypatch):
    def run(arguments):
        if arguments[0] == "docker":
            return 127, ""
        if "--query-compute-apps=gpu_uuid" in arguments:
            return 0, "[Not Supported]\n"
        return 0, "0, GPU-synthetic-0, Different NVIDIA, 98304, 96256, 590.10.2, 9.0\n"

    monkeypatch.setattr(hardware, "_run", run)
    snapshot = hardware._native_probe({"mode": "private"})
    assert not snapshot["allocation_probe_ok"]


def test_remote_docker_context_is_not_qualified_by_local_gpu(host, manifest):
    host["docker"]["local_engine"] = False
    report = inspect(host, manifest)
    assert not report["can_attempt"]
    assert any("local Unix socket" in blocker for blocker in report["blockers"])


def test_attach_also_requires_local_engine_for_its_bridge(host, manifest):
    host["docker"]["local_engine"] = False
    report = hardware.inspect_host({"mode": "attach"}, manifest, probe=host)
    assert not report["can_attempt"]


@pytest.mark.parametrize(
    "endpoint,expected",
    [("unix:///run/user/1000/docker.sock", True), ("ssh://secret@remote", False)],
)
def test_native_context_endpoint_never_leaves_capability_report(
    monkeypatch, manifest, endpoint, expected
):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)

    def run(arguments):
        if arguments[0] == "docker":
            if "context" in arguments:
                return 0, json.dumps(endpoint)
            if "info" in arguments:
                return 0, '{"nvidia":{}}'
            return 0, "2.40.0"
        if "--query-compute-apps=gpu_uuid" in arguments:
            return 0, ""
        return 0, "0, GPU-synthetic-0, Different NVIDIA, 98304, 96256, 590.10.2, 9.0\n"

    monkeypatch.setattr(hardware, "_run", run)
    snapshot = hardware._native_probe({"mode": "private"})
    assert snapshot["docker"]["local_engine"] is expected
    report = hardware.inspect_host({"mode": "private"}, manifest, probe=snapshot)
    assert endpoint not in json.dumps(report)


def test_docker_host_override_does_not_hide_remote_engine(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://private-credential@remote:2376")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(hardware, "_run", lambda _: (0, '"unix:///var/run/docker.sock"'))
    snapshot = hardware._native_probe({"mode": "attach"})
    assert snapshot["docker"]["local_engine"] is False
    assert "private-credential" not in json.dumps(snapshot)


@pytest.mark.parametrize("value", [None, [], "private-value", 1, True])
@pytest.mark.parametrize("field", ["runtime", "verification", "requirements"])
def test_malformed_nested_manifest_is_blocked_before_any_host_probe(manifest, field, value):
    def forbidden(_):
        raise AssertionError("Malformed metadata must not trigger host probing")

    if field == "requirements":
        manifest["runtime"]["requirements"] = value
    else:
        manifest[field] = value
    report = hardware.inspect_host({"mode": "private"}, manifest, probe=forbidden)
    assert report["status"] == "blocked" and not report["can_attempt"]
    assert report["selected_gpu"] is None
    assert report["resource_qualification"]["verified_workload"] is False
    assert "private-value" not in json.dumps(report)


@pytest.mark.parametrize(
    "manifest",
    [
        None,
        [],
        "private-value",
        {"assets": None},
        {"assets": {}},
        {"runtime": {"requirements": {"architectures": None}}},
        {"runtime": {"requirements": {"architectures": "x86_64"}}},
    ],
)
def test_malformed_manifest_shapes_return_safe_blockers(manifest):
    report = hardware.inspect_host({"mode": "private"}, manifest, probe={})
    assert not report["can_attempt"] and report["blockers"]
    assert "private-value" not in json.dumps(report)


def test_very_large_integer_minimum_is_a_blocker_without_float_overflow(host, manifest):
    manifest["runtime"]["requirements"]["min_host_ram_gib"] = 10**1000
    assert not inspect(host, manifest)["can_attempt"]
