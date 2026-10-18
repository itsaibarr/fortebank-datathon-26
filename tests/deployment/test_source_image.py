"""Pinned-source proof and isolated command-level image build tests; no Docker/GPU."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
from forte_admin.config import ConfigError  # noqa: E402
from forte_admin.source_image import (  # noqa: E402
    REQUIRED,
    build_source_image,
    source_entries,
)

CORE_COMMIT = "a" * 40
NODE = "node@sha256:" + "b" * 64
BASE = "vllm/vllm-openai@sha256:" + "c" * 64
BUILT = "sha256:" + "d" * 64


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / "released/core-source"
    source.mkdir(parents=True)
    files = {name: b"synthetic public source\n" for name in REQUIRED}
    files.update(
        {
            "Dockerfile": ("FROM " + BASE + "\nCOPY web/out /app/web\n").encode(),
            "src/forte/__init__.py": b"# frozen synthetic core\n",
        }
    )
    metadata = {}
    for name, data in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        metadata[name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "mode": 0o644,
        }
    manifest = {
        "schema_version": 1,
        "kind": "git-archive-public-build-inputs",
        "core_commit": CORE_COMMIT,
        "files": metadata,
        "inputs": [],
        "skipped_nonbuild_links": [],
    }
    (source / "SOURCE.json").write_text(json.dumps(manifest))
    calls = []

    def runner(command, *, timeout):
        calls.append((command, timeout))
        if command[1] == "run":
            snapshot = Path(command[command.index("--volume") + 1].removesuffix(":/snapshot"))
            output = snapshot / "web/out/index.html"
            output.parent.mkdir(parents=True)
            output.write_text("<html>Synthetic build output</html>")
        if command[1:3] == ["image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=BUILT + "\n")
        return SimpleNamespace(returncode=0, stdout="")

    return SimpleNamespace(
        source=source, root=tmp_path / "installation", calls=calls, manifest=manifest, runner=runner
    )


def build(bundle, **changes):
    options = {"node_image": NODE, "publisher_core_commit": CORE_COMMIT, "runner": bundle.runner}
    options.update(changes)
    return build_source_image(bundle.source.parent, bundle.root, **options)


def update_manifest(bundle, name, data):
    path = bundle.source / name
    path.write_bytes(data)
    bundle.manifest["files"][name] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "mode": 0o644,
    }
    (bundle.source / "SOURCE.json").write_text(json.dumps(bundle.manifest))


def test_build_preview_has_no_mutations_or_docker_calls(bundle):
    result = build(bundle, online=True)
    assert result["ok"] and result["preview"] and not result["runtime_verified"]
    assert result["core_commit"] == CORE_COMMIT and result["local_image_id"] is None
    assert not bundle.root.exists() and bundle.calls == []
    assert not (bundle.source / "web/out").exists()


def test_build_uses_isolated_pinned_sources_and_records_immutable_identity(bundle):
    before = {
        path.relative_to(bundle.source): path.read_bytes()
        for path in bundle.source.rglob("*")
        if path.is_file()
    }
    result = build(bundle, apply=True, online=True)
    assert result["ok"] and result["local_image_id"] == BUILT and not result["preview"]
    assert (
        not result["private_inputs"] and not result["gpu_used"] and not result["runtime_verified"]
    )
    assert not result["browser_access_verified"] and not result["quality_accepted"]
    receipt = Path(result["receipt"])
    assert json.loads(receipt.read_text())["local_image_id"] == BUILT
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert before == {
        path.relative_to(bundle.source): path.read_bytes()
        for path in bundle.source.rglob("*")
        if path.is_file()
    }
    node = next(command for command, _ in bundle.calls if command[1] == "run")
    docker_build = next(command for command, _ in bundle.calls if command[1] == "build")
    snapshot = Path(docker_build[-1])
    assert snapshot != bundle.source and not snapshot.exists()
    assert "--network=bridge" in node and NODE in node
    assert "--network=default" in docker_build
    assert "--pull=false" in docker_build and "--pull=never" in node
    assert node.count("--volume") == 1
    assert not any(
        "--gpus" in command or "compose" in command or "prune" in command
        for command, _ in bundle.calls
    )
    assert result["image_tag"].startswith("forte26-build-")


def test_offline_build_has_no_network_or_implicit_downloads(bundle):
    result = build(bundle, apply=True)
    assert result["ok"] and not result["online_public_preparation"]
    node = next(command for command, _ in bundle.calls if command[1] == "run")
    docker_build = next(command for command, _ in bundle.calls if command[1] == "build")
    assert "--network=none" in node and "npm ci --offline" in node[-1]
    assert "--network=none" in docker_build
    assert not any(command[1] == "pull" for command, _ in bundle.calls)


def test_explicit_online_build_pulls_only_pinned_missing_images(bundle):
    original = bundle.runner

    def missing(command, *, timeout):
        if command[1:3] == ["image", "inspect"] and command[-1] in {NODE, BASE}:
            bundle.calls.append((command, timeout))
            return SimpleNamespace(returncode=1, stdout="")
        return original(command, timeout=timeout)

    bundle.runner = missing
    assert build(bundle, apply=True, online=True)["ok"]
    pulls = [command[-1] for command, _ in bundle.calls if command[1] == "pull"]
    assert pulls == [NODE, BASE]


def test_missing_offline_image_is_actionable_without_start(bundle):
    bundle.runner = lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="")
    result = build(bundle, apply=True)
    assert not result["ok"] and "explicit online" in result["unresolved_prerequisites"][0]
    assert result["local_image_id"] is None
    assert not Path(result["receipt"]).exists()


def test_repeat_reuses_exact_receipt_and_image_without_building(bundle):
    first = build(bundle, apply=True)
    bundle.calls.clear()
    second = build(bundle, apply=True)
    assert second["ok"] and second["reused"] and second["local_image_id"] == first["local_image_id"]
    assert not any(command[1] in {"run", "build", "pull"} for command, _ in bundle.calls)


def test_repeat_does_not_overwrite_a_different_build_receipt(bundle):
    first = build(bundle, apply=True)
    receipt = Path(first["receipt"])
    before = json.loads(receipt.read_text())
    before["node_image"] = "node@sha256:" + "e" * 64
    receipt.write_text(json.dumps(before))
    existing = receipt.read_bytes()
    bundle.calls.clear()
    result = build(bundle, apply=True)
    assert not result["ok"] and receipt.read_bytes() == existing
    assert not any(command[1] in {"run", "build"} for command, _ in bundle.calls)


@pytest.mark.parametrize(
    "mode", ["tamper", "extra", "symlink", "parent_symlink", "missing", "commit", "traversal"]
)
def test_bundle_rejects_untrusted_sources_before_any_mutation(bundle, tmp_path, mode):
    if mode == "tamper":
        (bundle.source / "Dockerfile").write_text("changed")
    elif mode == "extra":
        (bundle.source / "private.key").write_text("synthetic secret")
    elif mode == "symlink":
        path = bundle.source / "README.md"
        path.unlink()
        path.symlink_to(tmp_path / "outside")
    elif mode == "parent_symlink":
        (bundle.source / "web").rename(tmp_path / "outside-web")
        (bundle.source / "web").symlink_to(tmp_path / "outside-web", target_is_directory=True)
    elif mode == "missing":
        (bundle.source / "web/package.json").unlink()
    elif mode == "commit":
        bundle.manifest["core_commit"] = "b" * 40
        (bundle.source / "SOURCE.json").write_text(json.dumps(bundle.manifest))
    else:
        bundle.manifest["files"]["../private.key"] = {
            "sha256": "a" * 64,
            "size_bytes": 0,
            "mode": 0o644,
        }
        (bundle.source / "SOURCE.json").write_text(json.dumps(bundle.manifest))
    with pytest.raises(ConfigError):
        build(bundle, apply=True)
    assert not bundle.root.exists() and not bundle.calls


def test_node_and_docker_bases_require_digest_pins(bundle):
    with pytest.raises(ConfigError, match="Node build image"):
        build(bundle, node_image="node:22", apply=True)
    update_manifest(bundle, "Dockerfile", b"FROM vllm/vllm-openai:latest\n")
    with pytest.raises(ConfigError, match="immutable"):
        build(bundle, apply=True)
    assert not bundle.root.exists() and not bundle.calls


def test_build_never_claims_unrelated_existing_directory(bundle):
    bundle.root.mkdir(mode=0o700)
    marker = bundle.root / "other-team.txt"
    marker.write_text("keep")
    with pytest.raises(ConfigError, match="unrelated"):
        build(bundle, apply=True)
    assert marker.read_text() == "keep" and not bundle.calls


def test_case_directory_is_not_copied_or_mounted(bundle):
    bundle.root.mkdir(mode=0o700)
    (bundle.root / "installation.json").write_text("{}")
    private = bundle.root / "data/private-case.mov"
    private.parent.mkdir(mode=0o700)
    private.write_text("synthetic case content")
    result = build(bundle, apply=True)
    assert result["ok"] and private.read_text() == "synthetic case content"
    node = next(command for command, _ in bundle.calls if command[1] == "run")
    assert str(private.parent) not in " ".join(node)
    assert "synthetic case content" not in json.dumps(result)


def test_runner_failures_redact_output_and_remove_build_scratch(bundle):
    marker = "synthetic-credential-never-report"

    def failing(command, *, timeout):
        raise RuntimeError(marker)

    bundle.runner = failing
    result = build(bundle, apply=True)
    assert not result["ok"] and marker not in json.dumps(result)
    assert not list((bundle.root / "public-builds").glob("source-*"))


def test_missing_frontend_output_does_not_build_core(bundle):
    def no_output(command, *, timeout):
        bundle.calls.append((command, timeout))
        return SimpleNamespace(returncode=0, stdout=BUILT + "\n")

    bundle.runner = no_output
    result = build(bundle, apply=True)
    assert not result["ok"] and "static entry point" in result["unresolved_prerequisites"][0]
    assert not any(command[1] == "build" for command, _ in bundle.calls)
    assert not list((bundle.root / "public-builds").glob("source-*"))


def test_actual_git_export_uses_only_pinned_tracked_build_inputs():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    entries = source_entries(ROOT, commit)
    proof = json.loads(entries["core-source/SOURCE.json"])
    expected = subprocess.check_output(["git", "show", commit + ":Dockerfile"], cwd=ROOT)
    assert entries["core-source/Dockerfile"] == expected
    assert proof["core_commit"] == commit
    assert not any(name.startswith("core-source/tools/") for name in entries)
    assert not any(".git/" in name or ".venv/" in name for name in entries)
    for name, info in proof["files"].items():
        assert hashlib.sha256(entries["core-source/" + name]).hexdigest() == info["sha256"]


def test_export_rejects_nonfull_commit_before_git_access():
    with pytest.raises(ConfigError, match="full pinned"):
        source_entries(ROOT, "HEAD")


def test_export_does_not_include_live_or_untracked_files(tmp_path):
    repo = tmp_path / "public-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for name in REQUIRED | {"src/forte/__init__.py"}:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("committed-public-source")
    inventory = repo / "deploy/portable/build_core.py"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(
        "INPUTS = "
        + repr(
            tuple(sorted({Path(name).parts[0] for name in REQUIRED | {"src/forte/__init__.py"}}))
        )
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "public fixture",
        ],
        cwd=repo,
        check=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "Dockerfile").write_text("uncommitted-change-never-export")
    (repo / "web/private-recording.mov").write_text("untracked-private-never-export")
    first, second = source_entries(repo, commit), source_entries(repo, commit)
    assert first == second
    assert first["core-source/Dockerfile"] == b"committed-public-source"
    assert not any(name.endswith(".mov") for name in first)
    assert b"untracked-private-never-export" not in first.values()
