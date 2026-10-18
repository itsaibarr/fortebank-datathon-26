"""Local build ancestry, public preparation and actual account error boundaries."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
from forte_admin import preparation  # noqa: E402
from forte_admin.cli import parser  # noqa: E402
from forte_admin.config import ConfigError  # noqa: E402
from forte_admin.source_image import source_entries  # noqa: E402

FLAGS = ("release", "model_workload", "offline_analysis", "browser_session", "ownership")
NODE = "node@sha256:" + "c" * 64


@pytest.fixture
def local_build(tmp_path):
    root = tmp_path / "installation"
    bundle = tmp_path / "published"
    source = bundle / "core-source"
    source.mkdir(parents=True)
    contract_hash = hashlib.sha256(b"synthetic-new-canonical-contract").hexdigest()
    (source / "SOURCE.json").write_text(
        json.dumps(
            {
                "core_commit": "b" * 40,
                "files": {"contracts/reasoning-api-contract.json": {"sha256": contract_hash}},
            }
        )
    )
    manifest = {
        "schema_version": 1,
        "core": {"commit": "a" * 40, "image": "sha256:" + "a" * 64, "contract_sha256": "a" * 64},
        "assets": [{"path": "legal/public-snapshot.json", "sha256": "e" * 64}],
        "model": {"identity": "synthetic-frozen-model", "frozen": True},
        "corpus": {"version": "synthetic-public-snapshot"},
        "runtime": {"ipc": "host"},
        "verification": {
            **{flag: False for flag in FLAGS},
            "receipt": "verification/acceptance.json",
        },
        "provenance": {
            "source_sha256": "f" * 64,
            "derived_status": "original-unapproved-candidate",
        },
    }
    original_path = tmp_path / "publisher-candidate.json"
    original_path.write_text(json.dumps(manifest, indent=2) + "\n")
    config = {
        "integration_manifest": str(original_path),
        "core_image": manifest["core"]["image"],
        "manifest_sha256": hashlib.sha256(original_path.read_bytes()).hexdigest(),
    }
    built = {
        "core_commit": "b" * 40,
        "local_image_id": "sha256:" + "d" * 64,
        "receipt": str(root / "public-builds/source-receipt.json"),
        "source_manifest_sha256": hashlib.sha256((source / "SOURCE.json").read_bytes()).hexdigest(),
    }
    return SimpleNamespace(
        root=root,
        bundle=bundle,
        manifest=manifest,
        original=original_path,
        config=config,
        built=built,
        contract_hash=contract_hash,
    )


def select(item, manifest=None):
    return preparation.select_local_build(
        item.manifest if manifest is None else manifest,
        item.config,
        item.root,
        item.bundle,
        item.built,
    )


def test_local_build_derives_separate_manifest_and_preserves_publisher_bytes(local_build):
    original = local_build.original.read_bytes()
    in_memory = json.loads(json.dumps(local_build.manifest))
    derived = select(local_build)
    path = Path(local_build.config["integration_manifest"])
    assert path.is_relative_to(local_build.root / "local-releases")
    assert path != local_build.original
    assert derived["core"] == {
        "commit": local_build.built["core_commit"],
        "image": local_build.built["local_image_id"],
        "contract_sha256": local_build.contract_hash,
    }
    assert all(derived["verification"][flag] is False for flag in FLAGS)
    for field in ("assets", "model", "corpus", "runtime"):
        assert derived[field] == in_memory[field]
    assert derived["provenance"]["base_candidate_sha256"] == hashlib.sha256(original).hexdigest()
    assert (
        derived["provenance"]["source_manifest_sha256"]
        == local_build.built["source_manifest_sha256"]
    )
    assert derived["provenance"]["build_receipt"] == local_build.built["receipt"]
    assert local_build.original.read_bytes() == original and local_build.manifest == in_memory
    assert local_build.config["core_image"] == local_build.built["local_image_id"]
    assert local_build.config["manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.stat().st_mode & 0o777 == 0o600


def test_repeated_local_build_keeps_original_ancestry_and_configuration(local_build):
    original = local_build.original.read_bytes()
    first = select(local_build)
    path = Path(local_build.config["integration_manifest"])
    before = path.read_bytes()
    selected_config = dict(local_build.config)
    second = select(local_build, first)
    assert second == first and local_build.config == selected_config
    assert path.read_bytes() == before and local_build.original.read_bytes() == original
    assert second["provenance"]["base_candidate_sha256"] == hashlib.sha256(original).hexdigest()
    assert second["provenance"]["base_candidate_sha256"] != hashlib.sha256(before).hexdigest()


@pytest.mark.parametrize("flag", FLAGS)
def test_existing_local_candidate_cannot_self_approve(local_build, flag):
    select(local_build)
    path = Path(local_build.config["integration_manifest"])
    existing = json.loads(path.read_text())
    existing["verification"][flag] = True
    path.write_text(json.dumps(existing))
    before, config = path.read_bytes(), dict(local_build.config)
    with pytest.raises(ConfigError, match="local build candidate changed"):
        select(local_build)
    assert path.read_bytes() == before and local_build.config == config


@pytest.mark.parametrize("field", ["core", "assets"])
def test_changed_existing_release_identity_or_resources_are_rejected(local_build, field):
    select(local_build)
    path = Path(local_build.config["integration_manifest"])
    existing = json.loads(path.read_text())
    if field == "core":
        existing["core"]["image"] = "sha256:" + "9" * 64
    else:
        existing["assets"][0]["sha256"] = "9" * 64
    path.write_text(json.dumps(existing))
    before = path.read_bytes()
    with pytest.raises(ConfigError, match="local build candidate changed"):
        select(local_build)
    assert path.read_bytes() == before


def test_missing_source_contract_hash_preserves_original_configuration(local_build):
    (local_build.bundle / "core-source/SOURCE.json").write_text('{"files": {}}')
    before = dict(local_build.config)
    with pytest.raises(ConfigError, match="canonical contract"):
        select(local_build)
    assert local_build.config == before and not local_build.root.exists()


def test_qualification_public_preparation_never_checks_or_acquires_proxy(monkeypatch, tmp_path):
    calls = []

    def resources(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "unresolved_prerequisites": []}

    def forbidden(*args, **kwargs):
        pytest.fail("Qualification attempted to prepare a proxy/ingress image")

    monkeypatch.setattr(preparation, "prepare_resources", resources)
    monkeypatch.setattr(preparation, "_image_ready", forbidden)
    manifest = {"core": {"image": "sha256:" + "a" * 64}}
    result = preparation.prepare_application(
        manifest,
        tmp_path / "resources",
        apply=True,
        online=True,
        qualification=True,
        config={"proxy_image": preparation.PINNED_PROXY},
    )
    assert result["ok"] and result["proxy_image_prepared"]
    assert len(calls) == 1 and calls[0][0] == (manifest, tmp_path / "resources")
    assert calls[0][1]["apply"] is True and calls[0][1]["online"] is True
    assert not (tmp_path / "resources").exists()


def test_browser_preparation_keeps_proxy_prerequisite(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        preparation,
        "prepare_resources",
        lambda *args, **kwargs: {"ok": True, "unresolved_prerequisites": []},
    )

    def missing_proxy(image, **kwargs):
        calls.append((image, kwargs))
        return False, "Pinned ingress image is unavailable."

    monkeypatch.setattr(preparation, "_image_ready", missing_proxy)
    result = preparation.prepare_application(
        {}, tmp_path / "resources", config={"proxy_image": preparation.PINNED_PROXY}
    )
    assert not result["ok"] and not result["proxy_image_prepared"]
    assert result["unresolved_prerequisites"] == ["Pinned ingress image is unavailable."]
    assert calls == [(preparation.PINNED_PROXY, {"apply": False, "online": False})]


def test_actual_source_build_preview_reads_export_without_mutating_or_running_docker(
    tmp_path, monkeypatch, local_build
):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    bundle = tmp_path / "published-source"
    for name, data in source_entries(ROOT, commit).items():
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (bundle / "RELEASE.json").write_text(json.dumps({"core_source_commit": commit}))
    before = {
        path.relative_to(bundle): path.read_bytes() for path in bundle.rglob("*") if path.is_file()
    }
    monkeypatch.setattr(
        preparation,
        "prepare_resources",
        lambda *args, **kwargs: {"ok": True, "unresolved_prerequisites": []},
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Source build preview attempted a subprocess operation")

    # Source export above is actual Git; the extracted-bundle build needs no Git or Docker.
    monkeypatch.setattr(preparation.subprocess, "run", forbidden)
    result = preparation.prepare_application(
        local_build.manifest,
        local_build.root / "resources",
        apply=False,
        online=True,
        qualification=True,
        build_core=True,
        core_source=bundle,
        node_image=NODE,
        installation=local_build.root,
        config=local_build.config,
    )
    assert result["ok"] and result["source_build"]["ok"] and result["source_build"]["preview"]
    assert result["source_build"]["local_image_id"] is None
    assert not result["source_build"]["runtime_verified"]
    assert not local_build.root.exists()
    assert before == {
        path.relative_to(bundle): path.read_bytes() for path in bundle.rglob("*") if path.is_file()
    }
    assert local_build.config["integration_manifest"] == str(local_build.original)


def test_actual_account_tool_invalid_sqlite_is_sanitized_and_preserved(tmp_path, capsys):
    root = tmp_path / "installation"
    database = root / "auth/sessions.sqlite3"
    database.parent.mkdir(parents=True, mode=0o700)
    marker = b"synthetic-case-or-credential-content-never-report"
    database.write_bytes(marker)
    database.chmod(0o600)
    result = preparation.bootstrap_administrator(
        {"access_mode": "browser-session", "session_db": str(database)}, root
    )
    assert (
        not result["ok"]
        and "Local account bootstrap is incomplete" in result["unresolved_prerequisites"][0]
    )
    assert marker.decode() not in json.dumps(result)
    assert capsys.readouterr().out == "" and database.read_bytes() == marker


def test_bootstrap_preview_creates_no_database(tmp_path):
    root = tmp_path / "installation"
    result = preparation.bootstrap_administrator(
        {"access_mode": "browser-session"}, root, preview=True
    )
    assert result["ok"] and result["account_created"] is False and not root.exists()


def test_cli_parses_explicit_source_build_controls():
    args = parser().parse_args(
        [
            "install",
            "--mode",
            "private",
            "--build-core",
            "--node-image",
            NODE,
            "--core-source",
            "/synthetic-public/release",
            "--qualification",
            "--online",
            "--preview",
        ]
    )
    assert args.command == "install" and args.mode == "private"
    assert args.build_core and args.node_image == NODE
    assert args.core_source == "/synthetic-public/release" and args.qualification and args.online
    assert args.preview and not args.apply


def test_cli_source_builder_is_explicit_and_default_node_is_pinned():
    args = parser().parse_args(["install", "--mode", "private"])
    assert not args.build_core and not args.online and not args.apply
    assert args.core_source is None
    assert preparation.IMAGE.fullmatch(args.node_image) and "@sha256:" in args.node_image


def test_explicit_source_build_failure_cannot_continue_with_an_old_ready_image(
    tmp_path, monkeypatch, local_build
):
    from forte_admin import source_image

    (local_build.bundle / "RELEASE.json").write_text(
        json.dumps({"core_source_commit": local_build.built["core_commit"]})
    )
    monkeypatch.setattr(
        source_image,
        "build_source_image",
        lambda *args, **kwargs: {
            "ok": False,
            "unresolved_prerequisites": ["Pinned source build did not complete."],
        },
    )
    # An older core may already exist, but explicit source-build selection must
    # remain failed rather than silently using that older image.
    monkeypatch.setattr(
        preparation,
        "prepare_resources",
        lambda *args, **kwargs: {"ok": True, "unresolved_prerequisites": []},
    )
    before = dict(local_build.config)
    result = preparation.prepare_application(
        local_build.manifest,
        tmp_path / "resources",
        qualification=True,
        build_core=True,
        core_source=local_build.bundle,
        node_image=NODE,
        config=local_build.config,
        installation=local_build.root,
    )
    assert result["ok"] is False
    assert "source build" in " ".join(result["unresolved_prerequisites"]).lower()
    assert result["source_build"]["ok"] is False
    assert local_build.config == before and not local_build.root.exists()
