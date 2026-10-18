"""Private, immutable case exports and locked human-correction snapshots.

This module does not interpret corrections or alter model results. All resource
links are authenticated case-relative API paths, never filesystem locations.
"""

import copy
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
from pathlib import Path
from uuid import UUID

from forte.contracts_v2 import CorrectionRequest

REVISION = re.compile(r"[a-f0-9]{32}\.json")
MAX_REVISION_BYTES = 65536
MAX_HISTORY_BYTES = 16 * 1024 * 1024


class InvalidCorrectionHistory(ValueError):
    """History could not be verified; callers return a generic private error."""


def result_digest(result: dict) -> str:
    """Use precisely the serialization used by timeline.append_correction."""
    return hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _validate_history(histories: dict, result: dict) -> list[dict]:
    current_digest = result_digest(result)
    timeline = result.get("timeline", result)
    targets = {item["observation_id"] for item in timeline.get("observations", [])}
    targets |= {item["event_id"] for item in timeline.get("events", [])}
    targets |= {item["participant_id"] for item in timeline.get("participants", [])}
    targets |= {item["assessment_id"] for item in result.get("legal", {}).get("assessments", [])}
    children = {}
    bases = set()
    for filename, revision in histories.items():
        if not isinstance(revision, dict):
            raise InvalidCorrectionHistory
        request = CorrectionRequest.model_validate(
            {key: revision[key] for key in CorrectionRequest.model_fields}
        )
        stamp = revision["created_unix_sec"]
        if (
            revision.get("schema_version") != "forte.correction/1"
            or revision.get("revision_id") + ".json" != filename
            or re.fullmatch(r"[a-f0-9]{64}", revision.get("base_result_sha256", "")) is None
            or request.source_sha256 != result["source_sha256"]
            or (
                revision.get("base_result_sha256") == current_digest
                and request.target_id not in targets
            )
            or revision.get("origin") != "human"
            or revision.get("other_scopes_approved") is not False
            or isinstance(stamp, bool)
            or not isinstance(stamp, (float, int))
            or not math.isfinite(stamp)
            or request.parent_revision in children
        ):
            raise InvalidCorrectionHistory
        children[request.parent_revision] = filename
        bases.add(revision["base_result_sha256"])
    ordered, current = [], children.get(None)
    while current is not None:
        if len(ordered) >= len(histories) or current not in histories:
            raise InvalidCorrectionHistory
        ordered.append(histories[current])
        current = children.get(current)
    if len(ordered) != len(histories) or len(bases) > 1:
        raise InvalidCorrectionHistory
    return ordered


def correction_snapshot(directory: Path, result: dict) -> list[dict]:
    """Read complete sidecars under append_correction's existing shared lock.

    Directory-relative no-follow descriptors reject symlinks for the directory,
    lock and revisions. An absent directory is an empty snapshot at that instant.
    Malformed/mixed-source/forked histories fail closed instead of disappearing.
    """
    try:
        try:
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return []
        with _directory_fd(directory_fd):
            lock_fd = os.open(
                ".revision.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            with os.fdopen(lock_fd, "r+") as lock:
                if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
                    raise InvalidCorrectionHistory
                fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
                histories, total = {}, 0
                for filename in os.listdir(directory_fd):
                    if not filename.endswith(".json"):
                        continue
                    if REVISION.fullmatch(filename) is None:
                        raise InvalidCorrectionHistory
                    fd = os.open(
                        filename,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=directory_fd,
                    )
                    with os.fdopen(fd, "rb") as record:
                        info = os.fstat(record.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REVISION_BYTES:
                            raise InvalidCorrectionHistory
                        raw = record.read(MAX_REVISION_BYTES + 1)
                    total += len(raw)
                    if len(raw) > MAX_REVISION_BYTES or total > MAX_HISTORY_BYTES:
                        raise InvalidCorrectionHistory
                    histories[filename] = json.loads(raw)
                return _validate_history(histories, result)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        raise InvalidCorrectionHistory("Correction history could not be verified.") from exc


class _directory_fd:
    def __init__(self, descriptor):
        self.descriptor = descriptor

    def __enter__(self):
        return self.descriptor

    def __exit__(self, *_):
        os.close(self.descriptor)


def build_investigation_report(job_id: UUID, result: dict, revisions: list[dict]) -> dict:
    """Export the full unchanged result and independent human history, no media."""
    prefix = f"/api/v2/jobs/{UUID(str(job_id))}"
    digest = result_digest(result)
    return {
        "schema_version": "forte.investigation-report/1",
        "job_id": str(job_id),
        "exported_unix_sec": time.time(),
        "scope": "complete_case",
        "base_result_sha256": digest,
        "result": copy.deepcopy(result),
        "corrections": copy.deepcopy(revisions),
        "corrections_match_current_result": all(
            item["base_result_sha256"] == digest for item in revisions
        ),
        "review_head": revisions[-1]["revision_id"] + ".json" if revisions else None,
        "links": {
            "result": prefix,
            "source": prefix + "/source",
            "corrections": prefix + "/corrections",
        },
        "limitations": [
            "Original model result is unchanged; corrections are independent human sidecars.",
            "Saved corrections do not approve other scopes or establish model correction uptake.",
            "Media is referenced, not bundled; all linked resources require case ownership.",
            "Partial, skipped and unknown coverage remains unresolved; "
            "retrieval is not legal proof.",
        ],
    }
