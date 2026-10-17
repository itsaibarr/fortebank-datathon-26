"""No allocator. Explicit reviewed-data receipts and exclusive existing-resource ownership."""

import fcntl
from contextlib import contextmanager
from datetime import UTC, datetime

from forte_visual.io import digest, read
from forte_visual.release import gate, verify


def data_gate(release_path, pilot_path, inputs_path, *, training=False):
    release, pairs, receipt = verify(release_path)
    reasons = gate(pairs, training=training)
    if release.synthetic:
        reasons.append("Synthetic fixtures cannot open real execution gates")
    if pilot_path is None:
        reasons.append("Missing completed reviewed pilot receipt")
    else:
        pilot = read(pilot_path)
        if (
            pilot.get("release_sha256") != receipt["release_sha256"]
            or pilot.get("training_input_sha256" if training else "input_sha256")
            != digest(inputs_path)
            or not pilot.get("reviewer")
            or not pilot.get("independent_review")
            or not pilot.get("regression_reviewed")
            or not pilot.get("near_misses_reviewed")
            or not pilot.get("source_mapping_reviewed")
            or not pilot.get("continuity_reviewed")
            or not pilot.get("selection_frozen")
            or not pilot.get("task_semantics_reviewed")
            or not pilot.get("all_assertions_adjudicated")
            or pilot.get("split") not in {"development", "validation"}
        ):
            reasons.append("Pilot does not bind frozen independently reviewed selection inputs")
    return reasons


@contextmanager
def resource(path, *, seconds=270):
    if path is None:
        raise ValueError("Pending explicit resource ownership; no allocation attempted")
    # The coordinating owner provides this receipt; do not replace producer lease.
    with path.open("r+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = read(path)
        now = datetime.now(UTC)
        checked = datetime.fromisoformat(receipt["live_checked_at"])
        expiry = datetime.fromisoformat(receipt["expires_at"])
        if checked.tzinfo is None or expiry.tzinfo is None:
            raise ValueError("Resource receipt requires timezone-aware times")
        if (
            receipt.get("owner") != "visual-learning"
            or receipt.get("project") != "forte26"
            or receipt.get("network_mode") != "none"
            or not receipt.get("project_resource_id")
            or not receipt.get("live_state_sha256")
            or not receipt.get("cleanup_armed")
            or not 0 <= (now - checked).total_seconds() < 300
            or (expiry - now).total_seconds() < seconds
            or receipt.get("remaining_project_usd", 0) <= receipt.get("reserve_usd", 1)
            or receipt.get("total_project_ceiling_usd") != 30
        ):
            raise ValueError("Resource ownership/offline/live-budget receipt gate closed")
        yield receipt
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
