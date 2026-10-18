"""Synthetic evidence-binding checks; no test here attests real deployment acceptance."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "acceptance_receipt_tested", ROOT / "deploy/portable/acceptance_receipt.py"
)
receipt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receipt)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def accepted(tmp_path):
    # The declared real levels below are synthetic metadata fixtures only. The
    # validator checks consistency; it does not independently certify a real run.
    root = tmp_path.resolve()
    resources, deployed = root / "resources", root / "deployed"
    (resources / "verification/evidence").mkdir(parents=True)
    files = {}
    for name in sorted(receipt.REQUIRED_FILES):
        path = deployed / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("# synthetic helper fixture: " + name).encode())
        files[name] = sha(path.read_bytes())
    manifest = {
        "schema_version": 1,
        "core": {"commit": "1" * 40, "image": "sha256:" + "2" * 64, "contract_sha256": "3" * 64},
        "model": {
            "identity": "fixture-model",
            "revision": "4" * 40,
            "profile": "frozen-fixture",
            "frozen": True,
        },
        "corpus": {"version": "fixture", "manifest_sha256": "5" * 64},
        "runtime": {"ipc": "host", "environment": {"FORTE_MODEL_PROFILE": "frozen-fixture"}},
        "assets": [{"path": "public/model.fixture", "sha256": "6" * 64, "size_bytes": 1}],
        "deployment": {
            "schema_version": "forte.deployment-identity/1",
            "proxy_image": "nginx@sha256:" + "7" * 64,
            "files": files,
        },
        "verification": {
            **dict.fromkeys(receipt.FLAGS, True),
            "receipt": "verification/acceptance.json",
            "receipt_sha256": "0" * 64,
        },
    }
    checks = {}
    for flag in receipt.FLAGS:
        relative = "verification/evidence/" + flag + ".json"
        raw = json.dumps({"synthetic_fixture": True, "check": flag}).encode()
        (resources / relative).write_bytes(raw)
        checks[flag] = {
            "status": "passed",
            "evidence_level": receipt.LEVELS[flag],
            "evidence": [{"path": relative, "sha256": sha(raw), "size_bytes": len(raw)}],
        }
    document = {
        "schema_version": "forte.deployment-acceptance/1",
        "subject_sha256": receipt.subject_sha256(manifest),
        "completed_at": "2026-10-18T02:00:00Z",
        "checks": checks,
    }

    def save(*, subject=False, raw=None):
        if subject:
            document["subject_sha256"] = receipt.subject_sha256(manifest)
        content = raw if raw is not None else json.dumps(document).encode()
        (resources / manifest["verification"]["receipt"]).write_bytes(content)
        manifest["verification"]["receipt_sha256"] = sha(content)

    save()
    return manifest, resources, deployed, document, save


def validate(accepted, **kwargs):
    manifest, resources, deployed, _, _ = accepted
    return receipt.validate(manifest, resources, deployed, **kwargs)


def test_matching_fixture_is_consistent_and_does_not_mutate(accepted):
    manifest, resources, _, _, _ = accepted
    before = json.dumps(manifest, sort_keys=True)
    stored = (resources / "verification/acceptance.json").read_bytes()
    assert validate(accepted) == []
    assert json.dumps(manifest, sort_keys=True) == before
    assert (resources / "verification/acceptance.json").read_bytes() == stored


@pytest.mark.parametrize("field", ["core", "model", "corpus", "runtime", "assets", "deployment"])
def test_every_subject_field_is_bound(accepted, field):
    manifest, _, _, _, _ = accepted
    if field == "assets":
        manifest[field][0]["sha256"] = "8" * 64
    elif field == "deployment":
        manifest[field]["proxy_image"] = "nginx@sha256:" + "8" * 64
    else:
        manifest[field]["changed_fixture"] = True
    assert validate(accepted)


@pytest.mark.parametrize(
    "field,value",
    [("commit", "8" * 40), ("image", "sha256:" + "8" * 64), ("contract_sha256", "8" * 64)],
)
def test_source_image_and_contract_mutations_are_rejected(accepted, field, value):
    accepted[0]["core"][field] = value
    assert validate(accepted)


@pytest.mark.parametrize(
    "field,value",
    [("revision", "8" * 40), ("profile", "other-profile"), ("identity", "other-model")],
)
def test_model_identity_mutations_are_rejected(accepted, field, value):
    accepted[0]["model"][field] = value
    assert validate(accepted)


def test_provenance_and_verification_are_excluded_from_subject(accepted):
    manifest = accepted[0]
    before = receipt.subject_sha256(manifest)
    manifest["provenance"] = {"notice": "A distinct accepted manifest preserves its candidate."}
    manifest["verification"]["receipt_sha256"] = "8" * 64
    assert receipt.subject_sha256(manifest) == before
    assert validate(accepted)  # Its receipt pin is still independently required.


def test_asset_inventory_order_is_canonical_and_duplicates_are_invalid(accepted):
    manifest = accepted[0]
    manifest["assets"].append({"path": "a.fixture", "sha256": "9" * 64})
    before = receipt.subject_sha256(manifest)
    manifest["assets"].reverse()
    assert receipt.subject_sha256(manifest) == before
    manifest["assets"].append(dict(manifest["assets"][0]))
    assert validate(accepted)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"synthetic":true}',
        b"{}",
        b"[]",
        b"null",
        b"not-json",
        b"\xff",
        b'{"schema_version":1,"schema_version":2}',
        b'{"value":NaN}',
    ],
)
def test_trivial_malformed_or_duplicate_json_cannot_approve(accepted, raw):
    accepted[4](raw=raw)
    assert validate(accepted)


@pytest.mark.parametrize("flag", receipt.FLAGS)
@pytest.mark.parametrize("level", ["synthetic", "qualification", "cached_example", "unknown", None])
def test_synthetic_and_qualification_never_approve_a_true_flag(accepted, flag, level):
    accepted[3]["checks"][flag]["evidence_level"] = level
    accepted[4]()
    assert validate(accepted)


@pytest.mark.parametrize("flag", receipt.FLAGS)
def test_false_failed_or_missing_check_cannot_satisfy_required_flag(accepted, flag):
    manifest, _, _, document, save = accepted
    document["checks"][flag]["status"] = "failed"
    save()
    assert validate(accepted)
    manifest["verification"][flag] = False
    document["checks"][flag] = {"status": "not_run", "evidence_level": None, "evidence": []}
    save()
    assert validate(accepted)


def test_existing_single_admin_policy_can_require_only_its_three_flags(accepted):
    manifest, _, _, document, save = accepted
    required = receipt.FLAGS[:3]
    for flag in receipt.FLAGS[3:]:
        manifest["verification"][flag] = False
        document["checks"][flag] = {"status": "not_run", "evidence_level": None, "evidence": []}
    save()
    assert validate(accepted, required_flags=required) == []
    assert validate(accepted)


def test_true_assertion_outside_required_subset_still_needs_real_evidence(accepted):
    accepted[3]["checks"]["ownership"]["evidence_level"] = "synthetic"
    accepted[4]()
    assert validate(accepted, required_flags=receipt.FLAGS[:3])


@pytest.mark.parametrize(
    "policy", [(), [], "release", None, ("unknown",), ("release", "release"), (1,)]
)
def test_invalid_required_policy_is_rejected(accepted, policy):
    assert validate(accepted, required_flags=policy)


@pytest.mark.parametrize("value", [1, "true", None, [], {}])
def test_flags_are_exact_booleans(accepted, value):
    accepted[0]["verification"]["ownership"] = value
    assert validate(accepted)


@pytest.mark.parametrize("section", ["verification", "deployment"])
def test_unknown_identity_or_flag_schema_is_rejected(accepted, section):
    accepted[0][section]["unexpected"] = "fixture"
    assert validate(accepted)


def test_changed_gateway_or_missing_component_blocks(accepted):
    path = accepted[2] / "tools/forte-session/session_gateway.py"
    path.write_bytes(b"changed helper")
    assert validate(accepted)
    path.unlink()
    assert validate(accepted)


def test_jury_gateway_identity_is_optional_but_checked_when_included(accepted):
    manifest, _, deployed, _, save = accepted
    path = deployed / "deploy/portable/jury_gateway.py"
    path.write_bytes(b"# synthetic jury helper")
    manifest["deployment"]["files"]["deploy/portable/jury_gateway.py"] = sha(path.read_bytes())
    save(subject=True)
    assert validate(accepted) == []
    path.write_bytes(b"changed")
    assert validate(accepted)


@pytest.mark.parametrize(
    "name",
    [
        "src/forte/api.py",
        "../outside.py",
        "deploy/portable/../outside.py",
        "deploy/portable/unknown.py",
    ],
)
def test_deployment_file_allowlist_is_exact(accepted, name):
    accepted[0]["deployment"]["files"][name] = "8" * 64
    accepted[4](subject=True)
    assert validate(accepted)


def test_missing_mandatory_helper_blocks_even_with_updated_subject(accepted):
    del accepted[0]["deployment"]["files"]["deploy/portable/host_daemon.py"]
    accepted[4](subject=True)
    assert validate(accepted)


def test_changed_or_missing_evidence_blocks_without_content_in_errors(accepted):
    path = accepted[1] / "verification/evidence/release.json"
    path.write_bytes(b"private-content-sentinel-secret")
    errors = validate(accepted)
    assert errors and "sentinel" not in str(errors) and str(path) not in str(errors)
    path.unlink()
    assert validate(accepted)


@pytest.mark.parametrize("target", ["receipt", "evidence", "helper"])
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory"])
def test_nonregular_or_aliased_files_rejected_without_blocking(accepted, tmp_path, target, kind):
    manifest, resources, deployed, document, save = accepted
    path = {
        "receipt": resources / "verification/acceptance.json",
        "evidence": resources / "verification/evidence/release.json",
        "helper": deployed / "deploy/portable/runtime.py",
    }[target]
    original = path.read_bytes()
    outside = tmp_path / "outside-sentinel"
    outside.write_bytes(original)
    path.unlink()
    if kind == "symlink":
        path.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, path)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()
    assert validate(accepted)


@pytest.mark.parametrize("target", ["resources", "evidence", "deployed", "helper"])
def test_symlink_directory_components_are_rejected(accepted, tmp_path, target):
    manifest, resources, deployed, _, _ = accepted
    root = {
        "resources": resources,
        "evidence": resources / "verification/evidence",
        "deployed": deployed,
        "helper": deployed / "tools/forte-session",
    }[target]
    moved = tmp_path / (target + "-moved")
    root.rename(moved)
    root.symlink_to(moved, target_is_directory=True)
    assert receipt.validate(manifest, resources, deployed)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.json",
        "/tmp/outside.json",
        "verification/../outside.json",
        "verification//receipt.json",
        "verification/./receipt.json",
        "verification/receipt.json\n",
        "https://example.invalid/receipt.json",
    ],
)
def test_receipt_paths_are_strict_and_never_external(accepted, path):
    accepted[0]["verification"]["receipt"] = path
    assert validate(accepted)


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/tmp/outside",
        "verification/../outside",
        "verification//outside",
        "case-data/video.mov",
        "verification/acceptance.json",
    ],
)
def test_evidence_paths_are_strict_and_cannot_read_receipt_or_case_root(accepted, path):
    accepted[3]["checks"]["release"]["evidence"][0]["path"] = path
    accepted[4]()
    assert validate(accepted)


@pytest.mark.parametrize(
    "field,value",
    [
        ("size_bytes", True),
        ("size_bytes", 0),
        ("size_bytes", -1),
        ("size_bytes", receipt.EVIDENCE_LIMIT + 1),
        ("sha256", "Z" * 64),
    ],
)
def test_evidence_entry_size_and_hash_types_are_strict(accepted, field, value):
    accepted[3]["checks"]["release"]["evidence"][0][field] = value
    accepted[4]()
    assert validate(accepted)


def test_oversized_receipt_and_helper_are_rejected(accepted):
    accepted[4](raw=b"x" * (receipt.RECEIPT_LIMIT + 1))
    assert validate(accepted)
    accepted[4]()
    helper = accepted[2] / "deploy/portable/runtime.py"
    helper.write_bytes(b"x" * (receipt.DEPLOYMENT_FILE_LIMIT + 1))
    assert validate(accepted)


def test_evidence_wrong_size_oversize_and_empty_inventory_are_rejected(accepted):
    manifest, resources, _, document, save = accepted
    item = document["checks"]["release"]["evidence"][0]
    item["size_bytes"] += 1
    save()
    assert validate(accepted)
    path = resources / item["path"]
    path.write_bytes(b"x" * (receipt.EVIDENCE_LIMIT + 1))
    save()
    assert validate(accepted)
    document["checks"]["release"]["evidence"] = []
    save()
    assert validate(accepted)


def test_evidence_cannot_supply_conflicting_or_duplicate_identities(accepted):
    document, save = accepted[3:]
    entry = document["checks"]["release"]["evidence"][0]
    document["checks"]["release"]["evidence"].append(dict(entry))
    save()
    assert validate(accepted)
    document["checks"]["release"]["evidence"].pop()
    other = dict(entry, sha256="8" * 64)
    document["checks"]["model_workload"]["evidence"] = [other]
    save()
    assert validate(accepted)


@pytest.mark.parametrize(
    "stamp", ["2026-02-30T01:02:03Z", "2026-10-18", "2026-10-18T01:02:03+00:00", None]
)
def test_receipt_timestamp_is_explicit_valid_utc(accepted, stamp):
    accepted[3]["completed_at"] = stamp
    accepted[4]()
    assert validate(accepted)


def test_changed_file_during_read_is_rejected(accepted, monkeypatch):
    original = receipt.os.read
    changed = False
    path = accepted[2] / sorted(receipt.REQUIRED_FILES)[0]

    def read(descriptor, count):
        nonlocal changed
        raw = original(descriptor, count)
        if not changed and raw:
            changed = True
            path.write_bytes(path.read_bytes() + b"# raced")
        return raw

    monkeypatch.setattr(receipt.os, "read", read)
    assert validate(accepted)


@pytest.mark.parametrize("suffix", ["/../resources", "/./", "//"])
def test_noncanonical_root_components_are_rejected(accepted, suffix):
    manifest, resources, deployed, _, _ = accepted
    assert receipt.validate(manifest, str(resources) + suffix, deployed)


def test_nonfinite_subject_is_rejected(accepted):
    accepted[0]["runtime"]["bad_fixture"] = float("nan")
    assert validate(accepted)


@pytest.mark.parametrize("version", [None, True, "1", 2])
def test_manifest_schema_is_exact_known_integer(accepted, version):
    accepted[0]["schema_version"] = version
    assert validate(accepted)


def test_canonical_installation_root_may_contain_spaces(accepted, tmp_path):
    manifest, resources, deployed, _, _ = accepted
    moved = tmp_path.resolve() / "installation resources"
    resources.rename(moved)
    assert receipt.validate(manifest, moved, deployed) == []


def test_replaced_file_during_read_is_rejected_even_when_bytes_match(accepted, monkeypatch):
    original = receipt.os.read
    path = accepted[2] / sorted(receipt.REQUIRED_FILES)[0]
    replaced = False

    def read(descriptor, count):
        nonlocal replaced
        raw = original(descriptor, count)
        if raw and not replaced:
            replaced = True
            content = path.read_bytes()
            path.unlink()
            path.write_bytes(content)
        return raw

    monkeypatch.setattr(receipt.os, "read", read)
    assert validate(accepted)


def test_aggregate_evidence_bytes_are_bounded(accepted):
    _, resources, _, document, save = accepted
    entries = []
    raw = b"x" * receipt.EVIDENCE_LIMIT
    for index in range(17):
        relative = f"verification/evidence/bounded-{index}.bin"
        (resources / relative).write_bytes(raw)
        entries.append({"path": relative, "sha256": sha(raw), "size_bytes": len(raw)})
    document["checks"]["release"]["evidence"] = entries
    save()
    assert validate(accepted)


def test_aggregate_unique_evidence_count_is_bounded(accepted):
    _, resources, _, document, save = accepted
    entries = []
    for index in range(29):
        relative = f"verification/evidence/count-{index}.bin"
        raw = str(index).encode()
        (resources / relative).write_bytes(raw)
        entries.append({"path": relative, "sha256": sha(raw), "size_bytes": len(raw)})
    document["checks"]["release"]["evidence"] = entries
    save()
    assert validate(accepted)
