"""Installer invariants: repeatability, credential separation and honest diagnostics."""

import hashlib
import importlib.util
import json
import os
import sys
import tarfile
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


@pytest.fixture
def public_archive_repo(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "forte_public_build", ROOT / "tools/forte-admin/build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "public-repository"

    def write(relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    write("tools/forte-admin/build.py", b"# synthetic archive builder\n")
    write("tools/forte-admin/forte-admin", b"# synthetic launcher\n")
    write("tools/forte-admin/forte_admin/__init__.py", b"")
    for name in module.PUBLIC_CONTRACTS:
        write(name, json.dumps({"public_metadata": name}).encode())
    canonical = (root / module.PUBLIC_CONTRACTS[0]).read_bytes()
    candidate = {
        "provenance": {"source_sha256": hashlib.sha256(canonical).hexdigest()},
        "verification": {key: False for key in module.ACCEPTANCE_FLAGS},
    }
    write(module.CURRENT_CANDIDATE, json.dumps(candidate).encode())
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    return module, root, write


def test_archive_public_attestations_candidate_integrity_and_exclusions(
    public_archive_repo, tmp_path
):
    module, root, write = public_archive_repo
    marker = b"synthetic-private-secret-never-package"
    for excluded in (
        "contracts/private-backup-receipt.json",
        "contracts/credentials.key",
        "contracts/input.mov",
        "contracts/model.safetensors",
        "deploy/portable/core-111234c.candidate.json",
        "deploy/portable/core-unreviewed.candidate.json",
        "src/forte/api.py",
        ".env",
    ):
        write(excluded, marker)
    output = tmp_path / "admin.tar.gz"
    module.build(output)
    with tarfile.open(output) as archive:
        entries = {
            member.name.removeprefix(module.PREFIX + "/"): archive.extractfile(member).read()
            for member in archive.getmembers()
        }
    assert set(module.PUBLIC_CONTRACTS) <= entries.keys()
    assert module.CURRENT_CANDIDATE in entries
    assert all(marker not in data for data in entries.values())
    release = json.loads(entries["RELEASE.json"])
    assert release["core_included"] is False
    assert not any(name.startswith("src/") for name in entries)
    for name in (*module.PUBLIC_CONTRACTS, module.CURRENT_CANDIDATE):
        assert entries[name] == (root / name).read_bytes()
        assert release["files"][name] == hashlib.sha256(entries[name]).hexdigest()
    candidate = json.loads(entries[module.CURRENT_CANDIDATE])
    assert all(candidate["verification"][key] is False for key in module.ACCEPTANCE_FLAGS)
    canonical_path = root / module.PUBLIC_CONTRACTS[0]
    original_canonical = canonical_path.read_bytes()
    canonical_path.write_bytes(original_canonical + b"\n")
    original_archive = output.read_bytes()
    with pytest.raises(ValueError, match="canonical runtime manifest"):
        module.build(output)
    assert output.read_bytes() == original_archive
    missing = tmp_path / "must-not-create" / "stale.tar.gz"
    with pytest.raises(ValueError, match="canonical runtime manifest"):
        module.build(missing)
    assert not missing.parent.exists()
    canonical_path.write_bytes(original_canonical)
    candidate["verification"]["release"] = True
    write(module.CURRENT_CANDIDATE, json.dumps(candidate).encode())
    with pytest.raises(ValueError, match="remain unapproved"):
        module.build(missing)
    assert not missing.exists()


@pytest.mark.parametrize("traversal", ["contract_file", "contract_parent", "output"])
def test_archive_rejects_symlink_traversal(public_archive_repo, tmp_path, traversal):
    module, root, _ = public_archive_repo
    outside = tmp_path / "outside"
    outside.mkdir()
    private = outside / "private.key"
    private.write_bytes(b"synthetic-secret")
    output = tmp_path / "admin.tar.gz"
    if traversal == "contract_file":
        source = root / module.PUBLIC_CONTRACTS[-1]
        source.unlink()
        source.symlink_to(private)
    elif traversal == "contract_parent":
        (root / "contracts").rename(outside / "contracts")
        (root / "contracts").symlink_to(outside / "contracts", target_is_directory=True)
    else:
        output.symlink_to(private)
    with pytest.raises(ValueError, match="symlink"):
        module.build(output)
    assert private.read_bytes() == b"synthetic-secret"
    if traversal != "output":
        assert not output.exists()


def test_archive_supports_output_parent_alias(public_archive_repo, tmp_path):
    module, _, _ = public_archive_repo
    destination = tmp_path / "canonical-output"
    destination.mkdir()
    alias = tmp_path / "output-alias"
    alias.symlink_to(destination, target_is_directory=True)
    module.build(alias / "admin.tar.gz")
    with tarfile.open(destination / "admin.tar.gz") as archive:
        assert module.PREFIX + "/RELEASE.json" in archive.getnames()


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
