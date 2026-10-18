"""Validate bounded, operator-reviewed acceptance evidence for one exact release.

This is evidence consistency checking, not a signature or an independent claim
that a model/browser test occurred. Candidates and qualification receipts cannot
approve a release. The normal runtime must choose its required flag policy; this
module offers no CLI/environment bypass and never starts services.

Receipt schema ``forte.deployment-acceptance/1`` has exactly schema_version,
subject_sha256, completed_at and checks. Each of the five checks has status,
evidence_level and evidence (path/sha256/size_bytes). A true manifest flag needs
its exact real evidence level below; a false flag has a not_run/null/[] check.
The manifest verification object also pins receipt and receipt_sha256. Evidence
and receipts live below resources_root/verification, contain no credentials, and
are never included in returned errors. Keep case-bearing evidence outside Git.

The canonical subject comprises core/model/corpus/runtime/assets/deployment;
verification and provenance are excluded to avoid receipt/manifest hash cycles.
Deployment identity has exactly schema_version, proxy_image and files. It pins
the executable helper closure below, plus the jury gateway when installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path

FLAGS = (
    "release",
    "model_workload",
    "offline_analysis",
    "browser_session",
    "ownership",
)
LEVELS = dict(
    zip(
        FLAGS,
        (
            "real_runtime",
            "real_model",
            "real_offline_analysis",
            "real_browser_session",
            "real_multi_principal",
        ),
        strict=True,
    )
)
SUBJECT_FIELDS = ("core", "model", "corpus", "runtime", "assets", "deployment")
REQUIRED_FILES = frozenset(
    {
        "deploy/portable/runtime.py",
        "deploy/portable/bridge.py",
        "deploy/portable/host_daemon.py",
        "deploy/portable/acceptance_receipt.py",
        "tools/forte-session/session_gateway.py",
        "tools/forte-session/session_store.py",
    }
)
ALLOWED_FILES = REQUIRED_FILES | {"deploy/portable/jury_gateway.py"}
SHA = re.compile(r"[0-9a-f]{64}")
IMAGE = re.compile(r"(?:[a-zA-Z0-9][a-zA-Z0-9._:/-]*@)?sha256:[0-9a-f]{64}")
RECEIPT_LIMIT = 256 * 1024
EVIDENCE_LIMIT = 1024 * 1024
DEPLOYMENT_FILE_LIMIT = 2 * 1024 * 1024
TOTAL_EVIDENCE_LIMIT = 16 * 1024 * 1024
MAX_EVIDENCE_FILES = 32


class Invalid(ValueError):
    """A fixed validation category; never include supplied paths or file bytes."""


def _hash(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _relative(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._/-]*", value) is not None
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _object(value, fields):
    return isinstance(value, dict) and set(value) == set(fields)


def _canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise Invalid("Acceptance subject is invalid.") from None


def _subject(manifest):
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or any(key not in manifest for key in SUBJECT_FIELDS)
    ):
        raise Invalid("Acceptance subject is invalid.")
    subject = {key: manifest[key] for key in SUBJECT_FIELDS}
    for key in ("core", "model", "corpus", "runtime", "deployment"):
        if not isinstance(subject[key], dict):
            raise Invalid("Acceptance subject is invalid.")
    core, model, corpus = subject["core"], subject["model"], subject["corpus"]
    if (
        not isinstance(core.get("commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", core["commit"]) is None
        or not isinstance(core.get("image"), str)
        or IMAGE.fullmatch(core["image"]) is None
        or not _hash(core.get("contract_sha256"))
        or not all(
            isinstance(model.get(k), str) and model[k] for k in ("identity", "revision", "profile")
        )
        or model.get("frozen") is not True
        or not isinstance(corpus.get("version"), str)
        or not corpus["version"]
        or not _hash(corpus.get("manifest_sha256"))
    ):
        raise Invalid("Acceptance subject is invalid.")
    assets = subject["assets"]
    if not isinstance(assets, list) or not 1 <= len(assets) <= 512:
        raise Invalid("Acceptance asset inventory is invalid.")
    names = set()
    for asset in assets:
        if (
            not isinstance(asset, dict)
            or not {"path", "sha256"} <= set(asset) <= {"path", "sha256", "size_bytes"}
            or not _relative(asset["path"])
            or asset["path"] in names
            or not _hash(asset["sha256"])
            or (
                "size_bytes" in asset
                and (type(asset["size_bytes"]) is not int or asset["size_bytes"] <= 0)
            )
        ):
            raise Invalid("Acceptance asset inventory is invalid.")
        names.add(asset["path"])
    # Inventory order has no identity significance; duplicate paths are invalid.
    subject["assets"] = sorted(assets, key=lambda item: item["path"])
    return subject


def subject_sha256(manifest):
    """Return the reproducible subject digest, excluding verification/provenance."""
    return hashlib.sha256(_canonical(_subject(manifest))).hexdigest()


def _root(path):
    """Pin every absolute directory component without following any symlinks."""
    try:
        raw = os.fspath(path)
    except TypeError:
        raise Invalid("Acceptance root is invalid.") from None
    if (
        not isinstance(raw, str)
        or not raw.startswith("/")
        or any(ord(character) < 32 or ord(character) == 127 for character in raw)
        or any(part in {"", ".", ".."} for part in raw[1:].split("/"))
    ):
        raise Invalid("Acceptance root is invalid.")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in raw[1:].split("/"):
            following = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = following
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _regular(root, relative, limit):
    """Read one stable, bounded regular file through pinned no-follow directory FDs."""
    if not _relative(relative):
        raise Invalid("Acceptance file path is invalid.")
    directory = os.dup(root)
    descriptor = None
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            following = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = following
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= limit
        ):
            raise Invalid("Acceptance file is not a bounded regular file.")
        chunks, count = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, limit + 1 - count))
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
            if count > limit:
                raise Invalid("Acceptance file exceeds its size limit.")
        after = os.fstat(descriptor)
        current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        fields = (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
            "st_nlink",
            "st_mode",
        )
        if count != before.st_size or any(
            getattr(before, field) != getattr(item, field)
            for item in (after, current)
            for field in fields
        ):
            raise Invalid("Acceptance file changed during verification.")
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Invalid("Acceptance JSON has duplicate keys.")
            result[key] = value
        return result

    def constant(_):
        raise Invalid("Acceptance JSON contains a non-finite value.")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise Invalid("Acceptance receipt is invalid JSON.") from None


def _deployment(value, root):
    if (
        not _object(value, {"schema_version", "proxy_image", "files"})
        or value["schema_version"] != "forte.deployment-identity/1"
        or not isinstance(value["proxy_image"], str)
        or IMAGE.fullmatch(value["proxy_image"]) is None
        or not isinstance(value["files"], dict)
        or not REQUIRED_FILES <= set(value["files"]) <= ALLOWED_FILES
    ):
        raise Invalid("Deployment identity is invalid or incomplete.")
    for name, expected in value["files"].items():
        if not _hash(expected):
            raise Invalid("Deployment identity contains an invalid hash.")
        raw = _regular(root, name, DEPLOYMENT_FILE_LIMIT)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise Invalid("Deployed component differs from accepted identity.")


def _receipt(value, expected, verification, resources, receipt_path):
    if (
        not _object(value, {"schema_version", "subject_sha256", "completed_at", "checks"})
        or value["schema_version"] != "forte.deployment-acceptance/1"
        or value["subject_sha256"] != expected
    ):
        raise Invalid("Acceptance receipt does not match the selected release.")
    completed = value["completed_at"]
    if (
        not isinstance(completed, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", completed) is None
    ):
        raise Invalid("Acceptance receipt timestamp is invalid.")
    try:
        datetime.strptime(completed, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise Invalid("Acceptance receipt timestamp is invalid.") from None
    checks = value["checks"]
    if not _object(checks, FLAGS):
        raise Invalid("Acceptance checks are incomplete or unrecognized.")
    seen, total = {}, 0
    for flag in FLAGS:
        check = checks[flag]
        if not _object(check, {"status", "evidence_level", "evidence"}):
            raise Invalid("Acceptance check schema is invalid.")
        if not verification[flag]:
            if check != {"status": "not_run", "evidence_level": None, "evidence": []}:
                raise Invalid("Acceptance check contradicts its manifest flag.")
            continue
        if check["status"] != "passed" or check["evidence_level"] != LEVELS[flag]:
            raise Invalid("Acceptance check lacks the required real evidence level.")
        entries = check["evidence"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_EVIDENCE_FILES:
            raise Invalid("Acceptance evidence inventory is invalid.")
        local_names = set()
        for item in entries:
            if (
                not _object(item, {"path", "sha256", "size_bytes"})
                or not _relative(item["path"])
                or not item["path"].startswith("verification/")
                or item["path"] == receipt_path
                or item["path"] in local_names
                or not _hash(item["sha256"])
                or type(item["size_bytes"]) is not int
                or not 0 < item["size_bytes"] <= EVIDENCE_LIMIT
            ):
                raise Invalid("Acceptance evidence entry is invalid.")
            local_names.add(item["path"])
            identity = (item["sha256"], item["size_bytes"])
            if item["path"] in seen:
                if seen[item["path"]] != identity:
                    raise Invalid("Acceptance evidence has conflicting identities.")
                continue
            seen[item["path"]] = identity
            total += item["size_bytes"]
            if len(seen) > MAX_EVIDENCE_FILES or total > TOTAL_EVIDENCE_LIMIT:
                raise Invalid("Acceptance evidence exceeds the aggregate limit.")
            raw = _regular(resources, item["path"], EVIDENCE_LIMIT)
            if len(raw) != item["size_bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise Invalid("Acceptance evidence failed its size or hash check.")


def validate(manifest, resources_root, deployment_root=None, *, required_flags=FLAGS):
    """Return fixed sanitized errors; read no unbounded file or external target.

    The normal caller chooses a nonempty subset of FLAGS for its existing access
    policy. Every true assertion is verified, including assertions outside that
    subset. This function neither edits flags nor authorizes service activation.
    """
    resources = deployed = None
    try:
        if (
            not isinstance(required_flags, (tuple, list, set, frozenset))
            or not required_flags
            or any(not isinstance(flag, str) or flag not in FLAGS for flag in required_flags)
            or len(set(required_flags)) != len(required_flags)
        ):
            raise Invalid("Required acceptance policy is invalid.")
        expected = subject_sha256(manifest)
        verification = manifest.get("verification")
        if not _object(verification, {*FLAGS, "receipt", "receipt_sha256"}) or any(
            type(verification[flag]) is not bool for flag in FLAGS
        ):
            raise Invalid("Manifest acceptance assertions are invalid.")
        if any(verification[flag] is not True for flag in required_flags):
            raise Invalid("Required acceptance checks are incomplete.")
        path = verification["receipt"]
        if (
            not _relative(path)
            or not path.startswith("verification/")
            or not path.endswith(".json")
            or not _hash(verification["receipt_sha256"])
        ):
            raise Invalid("Manifest acceptance receipt reference is invalid.")
        resources = _root(resources_root)
        deployed = _root(
            deployment_root if deployment_root is not None else Path(__file__).resolve().parents[2]
        )
        _deployment(manifest["deployment"], deployed)
        raw = _regular(resources, path, RECEIPT_LIMIT)
        if hashlib.sha256(raw).hexdigest() != verification["receipt_sha256"]:
            raise Invalid("Acceptance receipt failed its pinned hash check.")
        _receipt(_json(raw), expected, verification, resources, path)
        return []
    except Invalid as exc:
        return [str(exc)]
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return ["Acceptance evidence is unavailable or invalid."]
    finally:
        for descriptor in (resources, deployed):
            if descriptor is not None:
                os.close(descriptor)
