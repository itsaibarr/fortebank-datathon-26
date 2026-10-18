"""Synthetic Docker identity receipts; no real daemon, GPU or services are used."""

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
from forte_admin import cli, hardware  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "runtime_ownership_subject", ROOT / "deploy/portable/runtime.py"
)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
CORE = "registry.example.invalid/core@sha256:" + "1" * 64
PROXY = "registry.example.invalid/proxy@sha256:" + "2" * 64
CORE_IMAGE_ID = "sha256:" + "3" * 64
PROXY_IMAGE_ID = "sha256:" + "4" * 64
CORE_ID, INGRESS_ID = "a" * 64, "b" * 64
GPU = "GPU-synthetic-0001"


@pytest.fixture
def owned(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    target = tmp_path / "installation/runtime"
    target.mkdir(parents=True)
    config = {
        "schema_version": 1,
        "mode": "private",
        "project_name": "forte-owned-synthetic",
        "origin": "https://localhost:8443",
        "core_image": CORE,
        "proxy_image": PROXY,
        "gpu_uuid": GPU,
        "data_root": str(tmp_path / "cases"),
        "resources_root": str(tmp_path / "public-resources"),
    }
    (target / "compose.json").write_text('{"synthetic":"ownership sentinel"}')

    def container(identity, service, image, network, mounts):
        return {
            "Id": identity,
            "Config": {
                "Image": CORE if service == "core" else PROXY,
                "Labels": {
                    "org.forte.installation": runtime._installation_identity(target),
                    "com.docker.compose.project": config["project_name"],
                    "com.docker.compose.service": service,
                },
            },
            "Image": image,
            "State": {"Running": True},
            "HostConfig": {
                "NetworkMode": network,
                "DeviceRequests": [
                    {"Driver": "nvidia", "DeviceIDs": [GPU], "Capabilities": [["gpu"]]}
                ]
                if service == "core"
                else [],
            },
            "Mounts": mounts,
        }

    core = container(
        CORE_ID,
        "core",
        CORE_IMAGE_ID,
        "none",
        [
            {"Type": "bind", "Destination": "/data", "Source": config["data_root"], "RW": True},
            {
                "Type": "bind",
                "Destination": "/resources",
                "Source": config["resources_root"],
                "RW": False,
            },
        ],
    )
    ingress = container(
        INGRESS_ID,
        "ingress",
        PROXY_IMAGE_ID,
        "host",
        [
            {
                "Type": "bind",
                "Destination": "/etc/nginx/nginx.conf",
                "Source": str(target / "nginx.conf"),
                "RW": False,
            }
        ],
    )
    state = SimpleNamespace(
        config=config,
        target=target,
        records={CORE_ID: core, INGRESS_ID: ingress},
        identities=[CORE_ID, INGRESS_ID],
        calls=[],
        context="unix:///var/run/docker.sock",
        context_code=0,
        inventory_code=0,
        inspect_code=0,
        inspect_raw=None,
        image_code=0,
    )

    def docker(arguments):
        state.calls.append(arguments)
        if arguments[:2] == ["context", "inspect"]:
            return SimpleNamespace(returncode=state.context_code, stdout=json.dumps(state.context))
        if arguments[0] == "ps":
            assert "label=com.docker.compose.project=" + config["project_name"] in arguments
            return SimpleNamespace(
                returncode=state.inventory_code, stdout="\n".join(state.identities)
            )
        if arguments[0] == "inspect":
            assert len(arguments) == 2
            raw = state.inspect_raw
            if raw is None:
                raw = json.dumps([state.records[arguments[1]]])
            return SimpleNamespace(returncode=state.inspect_code, stdout=raw)
        if arguments[:2] == ["image", "inspect"]:
            if len(arguments) == 3:
                identity = {CORE: CORE_IMAGE_ID, PROXY: PROXY_IMAGE_ID}[arguments[2]]
                return SimpleNamespace(
                    returncode=state.image_code, stdout=json.dumps([{"Id": identity}])
                )
            assert arguments[2:4] == ["--format", "{{.Id}}"]
            identity = {CORE: CORE_IMAGE_ID, PROXY: PROXY_IMAGE_ID}[arguments[4]]
            return SimpleNamespace(returncode=state.image_code, stdout=identity + "\n")
        pytest.fail("Unexpected Docker operation in read-only ownership check")

    monkeypatch.setattr(runtime, "_docker", docker)
    return state


def test_exact_owned_core_and_ingress_are_recognized_read_only(owned):
    expected = {
        "core": {"id": CORE_ID, "running": True},
        "ingress": {"id": INGRESS_ID, "running": True},
    }
    assert runtime._owned_services(owned.config, owned.target) == expected
    assert runtime.owned_running(owned.config, owned.target)
    assert runtime._container(owned.config, owned.target) == CORE_ID
    assert all(call[0] in {"context", "ps", "inspect", "image"} for call in owned.calls)


@pytest.mark.parametrize(
    ("service", "path", "replacement"),
    [
        (CORE_ID, ("Config", "Labels", "org.forte.installation"), "foreign-installation"),
        (INGRESS_ID, ("Config", "Labels", "org.forte.installation"), "foreign-installation"),
        (CORE_ID, ("Config", "Labels", "com.docker.compose.project"), "forte-other-project"),
        (INGRESS_ID, ("Config", "Labels", "com.docker.compose.project"), "forte-other-project"),
        (CORE_ID, ("Image",), "sha256:" + "f" * 64),
        (INGRESS_ID, ("Image",), "sha256:" + "e" * 64),
        (CORE_ID, ("HostConfig", "NetworkMode"), "bridge"),
        (INGRESS_ID, ("HostConfig", "NetworkMode"), "bridge"),
        (CORE_ID, ("HostConfig", "DeviceRequests", 0, "DeviceIDs"), ["GPU-other"]),
        (CORE_ID, ("HostConfig", "DeviceRequests"), []),
        (CORE_ID, ("Mounts", 0, "Source"), "/unrelated/cases"),
        (CORE_ID, ("Mounts", 0, "RW"), False),
        (CORE_ID, ("Mounts", 1, "Source"), "/unrelated/resources"),
        (CORE_ID, ("Mounts", 1, "RW"), True),
        (INGRESS_ID, ("Mounts", 0, "Source"), "/foreign/nginx.conf"),
        (INGRESS_ID, ("Mounts", 0, "RW"), True),
        (CORE_ID, ("Config", "Labels", "com.docker.compose.service"), "unknown-worker"),
    ],
)
def test_foreign_release_gpu_network_or_mount_is_rejected(owned, service, path, replacement):
    selected = owned.records[service]
    for key in path[:-1]:
        selected = selected[key]
    selected[path[-1]] = replacement
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target)
    assert all(call[0] in {"context", "ps", "inspect", "image"} for call in owned.calls)


def test_another_target_cannot_claim_same_named_project(owned):
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target.parent / "foreign-runtime")


def test_multiple_devices_or_missing_gpu_selection_is_rejected(owned):
    requests = owned.records[CORE_ID]["HostConfig"]["DeviceRequests"]
    requests.append(copy.deepcopy(requests[0]))
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target)
    requests.pop()
    owned.config.pop("gpu_uuid")
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target)


def test_duplicate_core_or_unknown_service_inventory_is_rejected(owned):
    duplicate_id = "c" * 64
    owned.records[duplicate_id] = copy.deepcopy(owned.records[CORE_ID])
    owned.records[duplicate_id]["Id"] = duplicate_id
    owned.identities.append(duplicate_id)
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target)
    owned.records[duplicate_id]["Config"]["Labels"]["com.docker.compose.service"] = "worker"
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target)


@pytest.mark.parametrize("field", ["context_code", "inventory_code", "inspect_code", "image_code"])
def test_failed_inventory_or_inspection_fails_closed(owned, field):
    setattr(owned, field, 1)
    with pytest.raises(RuntimeError, match="no .*changed"):
        runtime._owned_services(owned.config, owned.target)


@pytest.mark.parametrize("raw", ["not-json", "{}", "[]", '[{"Config":{"Labels":null}}]'])
def test_malformed_inspection_cannot_establish_ownership(owned, raw):
    owned.inspect_raw = raw
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target)


@pytest.mark.parametrize(
    "endpoint", ["ssh://user@host", "tcp://192.0.2.1:2376", "npipe://pipe/docker", None]
)
def test_remote_or_unknown_docker_context_is_rejected_before_inventory(owned, endpoint):
    owned.context = endpoint
    with pytest.raises(RuntimeError, match="local Docker Unix socket"):
        runtime._owned_services(owned.config, owned.target)
    assert len(owned.calls) == 1 and owned.calls[0][:2] == ["context", "inspect"]


def test_remote_docker_host_environment_override_is_rejected(owned, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "ssh://operator@remote.invalid")
    with pytest.raises(RuntimeError, match="local Docker Unix socket"):
        runtime._owned_services(owned.config, owned.target)
    assert not owned.calls


def test_invalid_container_identity_rejected_before_inspect(owned):
    owned.identities = ["not-a-container-id"]
    with pytest.raises(RuntimeError, match="inventory is invalid"):
        runtime._owned_services(owned.config, owned.target)
    assert not any(call[0] == "inspect" for call in owned.calls)


def test_missing_compose_and_stopped_core_are_not_running(owned):
    (owned.target / "compose.json").unlink()
    assert runtime.owned_running(owned.config, owned.target) is False
    assert not owned.calls
    (owned.target / "compose.json").write_text("{}")
    owned.records[CORE_ID]["State"]["Running"] = False
    assert runtime.owned_running(owned.config, owned.target) is False
    with pytest.raises(RuntimeError, match="running core"):
        runtime._container(owned.config, owned.target)


def test_attach_recognizes_only_owned_ingress_and_refuses_core(owned):
    owned.config["mode"] = "attach"
    owned.identities = [INGRESS_ID]
    assert runtime.owned_running(owned.config, owned.target) is True
    assert set(runtime._owned_services(owned.config, owned.target)) == {"ingress"}
    owned.identities.append(CORE_ID)
    with pytest.raises(RuntimeError, match="ownership differs"):
        runtime._owned_services(owned.config, owned.target)


def test_cli_resume_preserves_owned_model_and_only_starts_ingress(owned, monkeypatch, capsys):
    root = owned.target.parent
    (root / "installation.json").write_text(json.dumps(owned.config))
    commands, bridge_calls = [], []

    def unexpected_probe(*args, **kwargs):
        pytest.fail("Owned runtime resume must not request another free GPU/model")

    def compose(config, target, action):
        assert action == "up"
        return [
            "docker",
            "compose",
            "--project-name",
            config["project_name"],
            "--file",
            str(target / "compose.json"),
            "up",
            "-d",
            "--pull",
            "never",
        ]

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(hardware, "inspect_host", unexpected_probe)
    monkeypatch.setattr(runtime, "host_prerequisites", unexpected_probe)
    monkeypatch.setattr(runtime, "compose_command", compose)
    monkeypatch.setattr(runtime, "render", lambda *args: [])
    monkeypatch.setattr(runtime, "_bridge_start", lambda *args: bridge_calls.append(args[-1]))
    monkeypatch.setattr(runtime, "_session_daemon", lambda *args: None)
    monkeypatch.setattr(runtime.subprocess, "run", run)
    monkeypatch.setattr(
        runtime,
        "status",
        lambda *args: {
            "ok": True,
            "ready": True,
            "core_ready": True,
            "access_ready": True,
        },
    )
    monkeypatch.setattr(cli, "portable", lambda: runtime)
    assert cli.main(["up", "--installation", str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["already_running"] is True
    assert len(commands) == 1 and commands[0][-1] == "ingress"
    assert "core" not in commands[0] and "down" not in commands[0]
    assert bridge_calls == [CORE_ID]
    assert json.loads((root / "installation.json").read_text())["gpu_uuid"] == GPU
