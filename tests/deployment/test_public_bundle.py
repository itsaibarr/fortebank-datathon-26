"""Publisher allowlist checks use synthetic public bytes, never real model weights."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
from forte_admin import public_bundle  # noqa: E402

REVISION = "1" * 40
SNAPSHOT = f"models/snapshots/{REVISION}/"
LEGAL = "legal/2026-10-17/V1900018545/0d776d3e-1c76-40f2-90ea-64f6de7868dc/source.html"


@pytest.fixture
def publisher(tmp_path):
    root, artifacts = tmp_path / "repository", tmp_path / "public-only"
    model_hashes, config = b'{"files":"synthetic-pinned-hashes"}', b'{"synthetic":"config"}'
    payloads = {
        "legal/2026-10-17/corpus.json": b'{"synthetic":"official-source-corpus"}',
        LEGAL: b"<html>synthetic official text bytes</html>",
        "repository/configs/person-tracking.json": b'{"synthetic":"tracking"}',
        "models/public/reid/osnet.onnx": b"synthetic ONNX never executable",
        "models/public/reid/manifest.json": b'{"synthetic":"reid-manifest"}',
        SNAPSHOT + "model-hashes.json": model_hashes,
        SNAPSHOT + "model-00001-of-00018.safetensors": b"must not be read or bundled",
        "config/frozen-inference.json": config,
    }
    assets, files = [], []

    def write(relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    for name, data in payloads.items():
        asset = {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
        assets.append(asset)
        if name == "config/frozen-inference.json":
            write("contracts/frozen-effective-config-v1.json", data)
            continue
        entry = {key: asset[key] for key in ("sha256", "size_bytes")}
        if name.startswith("repository/"):
            entry.update(root="repository", relative_path=name.removeprefix("repository/"))
            write(entry["relative_path"], data)
        else:
            entry.update(
                root=name.split("/")[0],
                container_path="/" + name,
                relative_path=name.split("/", 1)[1],
            )
            if name in {"models/public/reid/osnet.onnx", "models/public/reid/manifest.json"}:
                path = artifacts / name.removeprefix("models/public/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            elif name == SNAPSHOT + "model-hashes.json":
                write("contracts/frozen-model-hashes-v1.json", data)
            elif name.startswith("legal/"):
                write(name, data)
        files.append(entry)
    manifest = {"assets": assets}
    inventory = {
        "schema_version": "forte.public-assets/1",
        "model": {"revision": REVISION},
        "files": files,
    }

    def save():
        write("deploy/portable/core-current.candidate.json", json.dumps(manifest).encode())
        write("contracts/frozen-assets-v1.json", json.dumps(inventory).encode())

    save()
    return root, artifacts, payloads, manifest, inventory, save


def test_bundle_contains_only_exact_mapped_small_resources(publisher):
    root, artifacts, payloads, *_ = publisher
    (artifacts / "case.mov").write_bytes(b"PRIVATE CONTENT NEVER OPENED")
    (artifacts / "credentials.env").write_bytes(b"SECRET NEVER OPENED")
    entries = public_bundle.bundle_entries(root, public_artifacts_root=artifacts)
    expected = {
        "public-resources/" + name: data
        for name, data in payloads.items()
        if not name.endswith("safetensors")
    }
    assert entries == expected
    assert not any(b"PRIVATE CONTENT" in value or b"SECRET" in value for value in entries.values())
    assert len(entries) == 7


def test_27b_weight_file_is_never_opened(publisher, monkeypatch):
    root, artifacts, *_ = publisher
    opened = []
    original = public_bundle._read

    def record(path, *args, **kwargs):
        opened.append(str(path))
        assert not str(path).endswith("safetensors")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(public_bundle, "_read", record)
    public_bundle.bundle_entries(root, public_artifacts_root=artifacts)
    assert opened and not any(name.endswith("safetensors") for name in opened)


def test_missing_derived_artifact_requires_explicit_public_source(publisher):
    root, artifacts, *_ = publisher
    with pytest.raises(public_bundle.BundleError, match="approved public artifacts root"):
        public_bundle.bundle_entries(root)
    (artifacts / "reid/osnet.onnx").unlink()
    with pytest.raises(public_bundle.BundleError, match="unavailable"):
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)


def test_corrupt_derived_bytes_rejected_without_content_in_error(publisher):
    root, artifacts, *_ = publisher
    path = artifacts / "reid/osnet.onnx"
    old = path.read_bytes()
    path.write_bytes(b"s" * len(old))
    with pytest.raises(public_bundle.BundleError, match="SHA256") as error:
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)
    assert "s" * 10 not in str(error.value)


@pytest.mark.parametrize(
    "name", ["../case.mov", "/case.mov", "legal/../../credentials", "models/public/case.mov"]
)
def test_malicious_candidate_path_rejected(publisher, name):
    root, artifacts, _, manifest, _, save = publisher
    manifest["assets"][0]["path"] = name
    save()
    with pytest.raises(public_bundle.BundleError):
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)


def test_unknown_snapshot_filename_rejected_even_in_inventory(publisher):
    root, artifacts, _, manifest, inventory, save = publisher
    name = SNAPSHOT + "case.mov"
    manifest["assets"][-2]["path"] = name
    inventory["files"][-1]["container_path"] = "/" + name
    save()
    with pytest.raises(public_bundle.BundleError, match="filename"):
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)


@pytest.mark.parametrize("kind", ["file", "directory", "artifact-root", "manifest"])
def test_symlink_inputs_rejected(publisher, tmp_path, kind):
    root, artifacts, *_ = publisher
    if kind == "file":
        path = artifacts / "reid/osnet.onnx"
    elif kind == "directory":
        path = artifacts / "reid"
    elif kind == "manifest":
        path = root / "deploy/portable/core-current.candidate.json"
    else:
        link = tmp_path / "symlink-root"
        link.symlink_to(artifacts, target_is_directory=True)
        with pytest.raises(public_bundle.BundleError, match="symbolic"):
            public_bundle.bundle_entries(root, public_artifacts_root=link)
        return
    preserved = path.with_name(path.name + ".preserved")
    path.rename(preserved)
    path.symlink_to(preserved, target_is_directory=preserved.is_dir())
    with pytest.raises(public_bundle.BundleError, match="symbolic"):
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)


def test_huge_small_resource_rejected_before_read(publisher, monkeypatch):
    root, artifacts, _, manifest, inventory, save = publisher
    oversized = public_bundle.MAX_FILE_BYTES + 1
    manifest["assets"][0]["size_bytes"] = oversized
    inventory["files"][0]["size_bytes"] = oversized
    save()
    original = public_bundle._read

    def read(path, *args, **kwargs):
        assert not str(path).endswith("corpus.json")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(public_bundle, "_read", read)
    with pytest.raises(public_bundle.BundleError, match="size"):
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)


def test_optional_detector_is_included_only_if_hash_verified(publisher):
    root, artifacts, _, manifest, inventory, save = publisher
    data, name = b"synthetic public YOLOX", "models/public/yolox_s.onnx"
    asset = {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    manifest["assets"].append(asset)
    inventory["files"].append(
        {
            "root": "models",
            "relative_path": "yolox_s.onnx",
            "container_path": "/" + name,
            "sha256": asset["sha256"],
            "size_bytes": len(data),
        }
    )
    save()
    key = "public-resources/" + name
    assert key not in public_bundle.bundle_entries(root, public_artifacts_root=artifacts)
    (artifacts / "yolox_s.onnx").write_bytes(data)
    assert public_bundle.bundle_entries(root, public_artifacts_root=artifacts)[key] == data
    (artifacts / "yolox_s.onnx").write_bytes(b"wrong")
    with pytest.raises(public_bundle.BundleError):
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)


def test_candidate_cannot_change_canonical_resource_hash(publisher):
    root, artifacts, _, manifest, _, save = publisher
    manifest["assets"][0]["sha256"] = "f" * 64
    save()
    with pytest.raises(public_bundle.BundleError, match="canonical"):
        public_bundle.bundle_entries(root, public_artifacts_root=artifacts)
