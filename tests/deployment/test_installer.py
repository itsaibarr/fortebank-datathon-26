"""Installer invariants: repeatability, credential separation and honest diagnostics."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
from forte_admin import config  # noqa: E402
from forte_admin.cli import main  # noqa: E402


def test_preview_does_not_create_any_state(tmp_path, capsys):
    root = tmp_path / "never-created"
    assert main(["setup", "--installation", str(root), "--preview"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert not root.exists()
    assert report["unresolved_prerequisites"]
    assert report["services_started"] is False


def test_repeated_setup_preserves_secret_cases_and_corrections(tmp_path, capsys):
    root = tmp_path / "installation"
    arguments = ["setup", "--installation", str(root), "--apply"]
    assert main(arguments) == 0
    first = (root / "secrets/core-api.key").read_bytes()
    case = root / "data/corrections.json"
    case.write_text('{"synthetic":true}')
    assert main(arguments) == 0
    assert (root / "secrets/core-api.key").read_bytes() == first
    assert case.read_text() == '{"synthetic":true}'
    assert os.stat(root / "secrets/core-api.key").st_mode & 0o777 == 0o600
    assert first.decode().strip() not in capsys.readouterr().out


def test_attach_setup_never_generates_or_takes_ownership_of_core_key(tmp_path, capsys):
    root = tmp_path / "attach"
    assert main(["setup", "--installation", str(root), "--mode", "attach", "--apply"]) == 0
    assert not (root / "secrets/core-api.key").exists()
    assert json.loads(capsys.readouterr().out)["mode"] == "attach"


def test_secret_fields_rejected_before_any_mutation(tmp_path):
    with pytest.raises(config.ConfigError, match="Unknown"):
        config.plan(tmp_path / "install", {"api_key": "never-print-this"})
    assert not (tmp_path / "install").exists()


def test_installation_inside_git_checkout_rejected():
    with pytest.raises(config.ConfigError, match="outside"):
        config.plan(ROOT / ".install-test", {})


def test_storage_change_preserves_existing_install(tmp_path, capsys):
    root = tmp_path / "install"
    assert main(["setup", "--installation", str(root), "--apply"]) == 0
    previous = (root / "installation.json").read_bytes()
    assert (
        main(
            [
                "setup",
                "--installation",
                str(root),
                "--data-root",
                str(tmp_path / "other"),
                "--apply",
            ]
        )
        == 2
    )
    assert (root / "installation.json").read_bytes() == previous
    assert not (tmp_path / "other").exists()


def test_client_profile_cannot_be_used_as_installation(tmp_path, capsys):
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps({"endpoint": "https://example.invalid", "key_file": "/private/key"})
    )
    assert (
        main(
            [
                "setup",
                "--installation",
                str(tmp_path / "install"),
                "--config",
                str(profile),
                "--apply",
            ]
        )
        == 2
    )
    assert not (tmp_path / "install").exists()


def test_release_archive_reproducible_and_contains_only_allowed_files(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "forte_build", ROOT / "tools/forte-admin/build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first, second = tmp_path / "first.tar.gz", tmp_path / "second.tar.gz"
    module.build(first)
    module.build(second)
    assert first.read_bytes() == second.read_bytes()
    import tarfile

    with tarfile.open(first) as archive:
        names = archive.getnames()
        assert any(name.endswith("/deploy/portable/runtime.py") for name in names)
        assert all(
            not any(part in name for part in (".env", ".mov", "__pycache__", ".pem", ".key"))
            for name in names
        )


def test_existing_unrelated_directory_is_not_taken_over(tmp_path):
    root = tmp_path / "occupied"
    root.mkdir()
    unrelated = root / "other-team.txt"
    unrelated.write_text("keep")
    selected, _ = config.plan(root, {})
    with pytest.raises(config.ConfigError, match="empty installation"):
        config.apply(root, selected, lambda config, target: [])
    assert unrelated.read_text() == "keep"
    assert not (root / "secrets").exists()


def test_unsuccessful_stop_has_nonzero_exit(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    from forte_admin import cli

    root = tmp_path / "installation"
    root.mkdir()
    (root / "installation.json").write_text('{"schema_version":1}')
    monkeypatch.setattr(
        cli,
        "portable",
        lambda: SimpleNamespace(
            lifecycle=lambda *args: {"ok": False, "error": "owned_process_not_stopped"}
        ),
    )
    assert main(["stop", "--installation", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_importing_core_handoff_cannot_approve_itself():
    spec = importlib.util.spec_from_file_location(
        "handoff_import", ROOT / "deploy/portable/import_handoff.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.convert(
        ROOT / "contracts/frozen-runtime-manifest-v1.json",
        "111234c885f0a23d323fe72a81450dfca5aa7e60",
    )
    assert result["core"]["image"].startswith("sha256:")
    assert result["assets"] == []
    assert all(
        result["verification"][key] is False
        for key in ("release", "model_workload", "offline_analysis", "browser_session", "ownership")
    )
    assert result["runtime"]["requirements"]["min_host_ram_gib"] is None
    assert result["provenance"]["source_schema"] == "forte.integration/1"


def test_core_build_preview_uses_pinned_git_snapshot_and_no_runtime(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "build_core", ROOT / "deploy/portable/build_core.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt = tmp_path / "unused-receipt.json"
    result = module.prepare(
        ROOT,
        "111234c885f0a23d323fe72a81450dfca5aa7e60",
        "example.invalid/node@sha256:" + "a" * 64,
        "forte26-synthetic:preview",
        receipt,
        preview=True,
    )
    assert result["preview"] and result["private_inputs"] is False
    assert not receipt.exists()
    assert "git archive" in result["source"]
