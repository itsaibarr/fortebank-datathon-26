"""Guided installer mechanics with isolated lifecycle substitutes, never inference."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
from forte_admin.config import ConfigError, plan  # noqa: E402
from forte_admin.install import install  # noqa: E402


@pytest.fixture
def installer(tmp_path):
    manifest = tmp_path / "public-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "core": {
                    "commit": "a" * 40,
                    "image": "sha256:" + "a" * 64,
                    "contract_sha256": "b" * 64,
                },
                "verification": {
                    "release": False,
                    "model_workload": False,
                    "offline_analysis": False,
                    "browser_session": False,
                    "ownership": False,
                },
            }
        )
    )
    root = tmp_path / "installation"
    config, _ = plan(
        root, {"integration_manifest": str(manifest), "proxy_image": "sha256:" + "c" * 64}
    )
    calls = []
    status = {
        "ok": True,
        "ready": True,
        "core_ready": True,
        "access_ready": True,
        "browser_access_verified": True,
        "started": True,
    }

    def render(selected, target):
        calls.append("render")
        target.mkdir(parents=True, exist_ok=True)
        (target / "compose.json").write_text(json.dumps({"name": selected["project_name"]}))
        return [target / "compose.json"]

    def lifecycle(selected, target, action):
        calls.append((selected["mode"], action))
        return dict(status)

    def resources(selected, target, **options):
        calls.append(("resources", options["apply"]))
        if options["apply"]:
            Path(target).mkdir(parents=True, exist_ok=True)
            (Path(target) / "public-asset").write_text("synthetic-public-resource")
        return {"ok": True, "unresolved_prerequisites": []}

    def bootstrap(selected, target, **options):
        calls.append(("bootstrap", options["preview"]))
        return {"ok": True}

    runtime = SimpleNamespace(
        validate=lambda selected: [],
        prerequisites=lambda selected: [],
        render=render,
        lifecycle=lifecycle,
    )
    options = {
        "runtime": runtime,
        "host_check": lambda selected: {"can_attempt": True},
        "prepare_resources": resources,
        "bootstrap": bootstrap,
        "tls_mode": "local-self-signed",
        "readiness_timeout": 0,
    }
    return SimpleNamespace(
        root=root,
        config=config,
        calls=calls,
        status=status,
        runtime=runtime,
        options=options,
        manifest=manifest,
    )


def test_preview_has_zero_mutations_and_no_start(installer):
    result = install(installer.config, installer.root, **installer.options)
    assert result["preview"] is True and result["applied"] is False
    assert result["application_url"] is None and result["ready"] is False
    assert not installer.root.exists()
    assert ("resources", False) in installer.calls
    assert ("bootstrap", True) in installer.calls
    assert not any(isinstance(call, tuple) and call[-1] == "up" for call in installer.calls)


def test_one_command_configures_secret_tls_resources_and_owned_start(installer):
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert (
        result["ok"] and result["ready"] and result["application_url"] == installer.config["origin"]
    )
    assert result["externally_verified"] is False and result["case_processing_started"] is False
    assert result["remote_fallback"] is False
    assert all(item["status"] == "complete" for item in result["phases"])
    assert installer.calls == [
        ("resources", True),
        ("bootstrap", False),
        "render",
        ("private", "up"),
    ]
    assert "import" in result["tls_trust"]
    assert (installer.root / "secrets/core-api.key").stat().st_mode & 0o777 == 0o600
    journal = json.loads((installer.root / "install-journal.json").read_text())
    assert journal["attempt"] == 1 and journal["phases"] == result["phases"]
    assert "configuration_sha256" in journal
    # Completion of installer mechanics does not approve the unapproved release.
    assert not any(json.loads(installer.manifest.read_text())["verification"].values())


def test_repeated_install_preserves_secret_corrections_tls_and_retention(installer):
    first = install(installer.config, installer.root, apply=True, **installer.options)
    assert first["ok"]
    case = installer.root / "data/corrections.json"
    case.write_text('{"synthetic": "keep-corrections"}')
    protected = [
        case,
        installer.root / "secrets/core-api.key",
        installer.root / "tls/privkey.pem",
        installer.root / "tls/fullchain.pem",
    ]
    before = {path: path.read_bytes() for path in protected}
    second = install(installer.config, installer.root, apply=True, **installer.options)
    assert second["ok"] and second["data_preserved"]
    assert before == {path: path.read_bytes() for path in protected}
    assert second["retention"] == first["retention"]
    assert json.loads((installer.root / "install-journal.json").read_text())["attempt"] == 2


def test_missing_host_dependencies_do_not_mutate_or_acquire(installer):
    installer.options["host_check"] = lambda selected: {
        "can_attempt": False,
        "unresolved_prerequisites": ["Install Docker with Compose v2."],
    }
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert result["exit_code"] == 2 and result["unresolved_prerequisites"] == [
        "Install Docker with Compose v2."
    ]
    assert not installer.root.exists() and not installer.calls


def test_interruption_journal_allows_same_command_to_resume(installer):
    original = installer.options["prepare_resources"]

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    installer.options["prepare_resources"] = interrupted
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert result["exit_code"] == 130 and result["applied"] and result["data_preserved"]
    journal = json.loads((installer.root / "install-journal.json").read_text())
    assert {"phase": "public_resources", "status": "interrupted"} in journal["phases"]
    first_secret = (installer.root / "secrets/core-api.key").read_bytes()
    installer.options["prepare_resources"] = original
    resumed = install(installer.config, installer.root, apply=True, **installer.options)
    assert resumed["ok"]
    assert (installer.root / "secrets/core-api.key").read_bytes() == first_secret
    assert json.loads((installer.root / "install-journal.json").read_text())["attempt"] == 2


def test_unavailable_model_times_out_without_destination_change(installer):
    installer.status.update(ok=False, ready=False, core_ready=False)
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert result["services_started"] and not result["ok"] and result["exit_code"] == 2
    assert result["processing_destination"] == installer.config["origin"]
    assert result["application_url"] is None and result["remote_fallback"] is False
    assert "bounded readiness" in result["unresolved_prerequisites"][0]
    assert not any(isinstance(call, tuple) and call[-1] == "stop" for call in installer.calls)


def test_poll_waits_for_model_and_https_browser_access(installer, monkeypatch):
    import forte_admin.install as module

    installer.options.update(readiness_timeout=2, poll_interval=0.1)
    installer.status.update(ok=False, ready=False, core_ready=True, access_ready=False)
    ticks = iter([10, 10, 10.1])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(module.time, "sleep", lambda delay: None)
    initial = dict(installer.status)

    def lifecycle(selected, target, action):
        installer.calls.append((selected["mode"], action))
        if action == "up":
            return initial
        return dict(initial, ok=True, ready=True, access_ready=True)

    installer.runtime.lifecycle = lifecycle
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert result["ready"] and ("private", "status") in installer.calls


def test_attach_never_prepares_or_starts_another_model(installer):
    installer.config["mode"] = "attach"
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert result["ok"] and ("attach", "up") in installer.calls
    assert not any(isinstance(call, tuple) and call[0] == "resources" for call in installer.calls)
    assert not (installer.root / "secrets/core-api.key").exists()
    assert not (installer.root / "resources").exists()


def test_missing_actual_account_tool_blocks_before_start(installer):
    installer.options["bootstrap"] = None
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ready"] and not result["services_started"]
    assert "Core local administrator bootstrap" in result["unresolved_prerequisites"][0]
    assert (installer.root / "secrets/core-api.key").is_file()
    assert not (installer.root / "data/accounts.json").exists()


def test_shared_gateway_is_not_claimed_as_reviewer_browser_setup(installer):
    installer.config["access_mode"] = "gateway-single-admin"
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ready"]
    assert "reviewer browser session" in result["unresolved_prerequisites"][0]


def test_unapproved_core_gate_blocks_start_and_is_not_promoted(installer):
    installer.runtime.prerequisites = lambda selected: [
        "per-principal ownership enforcement is not verified"
    ]
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ok"] and not result["services_started"]
    assert result["unresolved_prerequisites"] == [
        "per-principal ownership enforcement is not verified"
    ]
    assert not any(json.loads(installer.manifest.read_text())["verification"].values())
    assert "render" not in installer.calls


def test_resource_failure_does_not_start_service_or_fall_back(installer):
    installer.options["prepare_resources"] = lambda *args, **kwargs: {
        "ok": False,
        "unresolved_prerequisites": ["Pinned resource is missing; import the approved local file."],
    }
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ok"] and not result["services_started"]
    assert (
        not result["remote_fallback"]
        and result["processing_destination"] == installer.config["origin"]
    )
    assert "render" not in installer.calls


def test_external_exception_and_journal_never_expose_credentials_or_cases(installer):
    marker = "synthetic-secret-or-case-content-never-report"
    events = []
    installer.options["reporter"] = events.append

    def fail(*args, **kwargs):
        raise RuntimeError(marker)

    installer.options["prepare_resources"] = fail
    result = install(installer.config, installer.root, apply=True, **installer.options)
    output = (
        json.dumps(result)
        + json.dumps(events)
        + (installer.root / "install-journal.json").read_text()
    )
    assert marker not in output
    assert (installer.root / "secrets/core-api.key").read_text().strip() not in output
    assert result["phases"][3] == {"phase": "public_resources", "status": "blocked"}


def test_installer_refuses_to_claim_unrelated_directory(installer):
    installer.root.mkdir(mode=0o700)
    arbitrary = installer.root / "unrelated.txt"
    arbitrary.write_text("keep")
    with pytest.raises(ConfigError, match="empty installation"):
        install(installer.config, installer.root, apply=True, **installer.options)
    assert arbitrary.read_text() == "keep" and not installer.calls
    assert not (installer.root / "installation.json").exists()


def test_mode_and_data_ownership_cannot_change_on_repeat(installer):
    install(installer.config, installer.root, apply=True, **installer.options)
    before = (installer.root / "installation.json").read_bytes()
    installer.config["mode"] = "attach"
    with pytest.raises(ConfigError, match="separate installation"):
        install(installer.config, installer.root, apply=True, **installer.options)
    assert (installer.root / "installation.json").read_bytes() == before


def test_self_signed_tls_cannot_expose_public_listener(installer):
    installer.config.update(origin="https://example.invalid:8443", bind_address="0.0.0.0")
    with pytest.raises(ConfigError, match="loopback-only"):
        install(installer.config, installer.root, **installer.options)
    assert not installer.root.exists()


def test_generated_tls_contains_correct_localhost_san_and_is_not_overwritten(installer):
    assert install(installer.config, installer.root, apply=True, **installer.options)["ok"]
    cert = installer.root / "tls/fullchain.pem"
    inspected = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "DNS:localhost" in inspected.stdout
    first = hashlib.sha256(cert.read_bytes()).hexdigest()
    install(installer.config, installer.root, apply=True, **installer.options)
    assert hashlib.sha256(cert.read_bytes()).hexdigest() == first


def test_partial_tls_pair_is_preserved_and_actionable(installer):
    installer.root.mkdir(mode=0o700)
    (installer.root / "installation.json").write_text(json.dumps(installer.config))
    tls = installer.root / "tls"
    tls.mkdir(mode=0o700)
    cert = tls / "fullchain.pem"
    cert.write_text("synthetic-incomplete-pair")
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ok"] and "partial TLS pair" in result["unresolved_prerequisites"][0]
    assert cert.read_text() == "synthetic-incomplete-pair"
    assert not (tls / "privkey.pem").exists()


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, 1801])
def test_readiness_wait_is_explicitly_bounded(installer, value):
    installer.options["readiness_timeout"] = value
    with pytest.raises(ConfigError, match="Readiness timeout"):
        install(installer.config, installer.root, **installer.options)
    assert not installer.root.exists()


def test_directory_lock_prevents_second_installer(installer):
    import fcntl

    install(installer.config, installer.root, apply=True, **installer.options)
    descriptor = os.open(installer.root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ConfigError, match="Another installer"):
            install(installer.config, installer.root, apply=True, **installer.options)
    finally:
        os.close(descriptor)


def test_real_portable_runtime_is_used_as_contract_gate_not_inference(installer):
    spec = importlib.util.spec_from_file_location(
        "real_install_runtime", ROOT / "deploy/portable/runtime.py"
    )
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    installer.options["runtime"] = runtime
    result = install(installer.config, installer.root, **installer.options)
    assert not result["ok"] and result["unresolved_prerequisites"]
    assert not installer.root.exists() and not result["services_started"]


def test_qualification_uses_only_local_core_and_never_claims_browser_install(installer):
    installer.options.update(qualification=True, bootstrap=None, tls_mode="supplied")
    installer.runtime.qualification_prerequisites = lambda selected: []

    def lifecycle(selected, target, action):
        installer.calls.append((selected["mode"], action))
        return {
            "ok": True,
            "core_ready": True,
            "qualification_complete": True,
            "services_stopped": True,
        }

    installer.runtime.lifecycle = lifecycle
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert result["ok"] and result["qualification_complete"] and result["services_stopped"]
    assert result["operation"] == "local-qualification"
    assert not result["ready"] and result["application_url"] is None
    assert not result["externally_verified"] and not result["remote_fallback"]
    assert installer.calls == [("resources", True), ("private", "qualify")]
    assert not (installer.root / "tls").exists()
    assert not any(json.loads(installer.manifest.read_text())["verification"].values())


def test_qualification_requires_owned_services_to_be_stopped(installer):
    installer.options.update(qualification=True)
    installer.runtime.qualification_prerequisites = lambda selected: []
    installer.runtime.lifecycle = lambda *args: {
        "ok": True,
        "core_ready": True,
        "qualification_complete": True,
        "services_stopped": False,
    }
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ok"] and not result["qualification_complete"]
    assert result["application_url"] is None


def test_qualification_preview_is_nonmutating_and_does_not_need_account_or_tls(installer):
    installer.options.update(qualification=True, bootstrap=None, tls_mode="supplied")
    installer.runtime.qualification_prerequisites = lambda selected: []
    result = install(installer.config, installer.root, **installer.options)
    assert result["ok"] and result["preview"]
    assert not result["qualification_complete"]
    assert installer.calls == [("resources", False)]
    assert not installer.root.exists()


def test_qualification_keeps_resource_provenance_gate(installer):
    installer.options.update(qualification=True)
    installer.runtime.qualification_prerequisites = lambda selected: [
        "Pinned model file hash mismatch."
    ]
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ok"] and not result["services_started"]
    assert result["unresolved_prerequisites"] == ["Pinned model file hash mismatch."]


def test_missing_stable_core_commit_blocks_resource_acquisition(installer):
    data = json.loads(installer.manifest.read_text())
    data["core"]["commit"] = "changing-worktree"
    installer.manifest.write_text(json.dumps(data))
    result = install(installer.config, installer.root, apply=True, **installer.options)
    assert not result["ok"] and "stable core commit" in result["unresolved_prerequisites"][0]
    assert not installer.root.exists() and not installer.calls


def test_hardware_notices_and_selected_device_are_preserved(installer):
    installer.options["host_check"] = lambda selected: {
        "can_attempt": True,
        "status": "candidate",
        "warnings": ["Headroom needs actual warmup."],
        "selected_gpu": {"index": 0, "uuid": "GPU-synthetic"},
        "resource_qualification": {"verified_workload": False},
    }
    result = install(installer.config, installer.root, **installer.options)
    assert result["host_capabilities"]["warnings"] == ["Headroom needs actual warmup."]
    assert result["host_capabilities"]["selected_gpu"]["uuid"] == "GPU-synthetic"
    assert result["host_capabilities"]["resource_qualification"]["verified_workload"] is False


def test_ipv6_loopback_origin_requires_an_actual_ipv6_listener(installer):
    installer.config["origin"] = "https://[::1]:8443"
    with pytest.raises(ConfigError, match="loopback-only"):
        install(installer.config, installer.root, **installer.options)
    assert not installer.root.exists()
