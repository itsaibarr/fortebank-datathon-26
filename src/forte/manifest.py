"""Metadata-only recording groups, reviewed split freezing and honest evaluation.

No media, labels, date or session relationship is inferred from a filename.
These utilities do not train models or change the human annotation contract.
"""

import copy
import hashlib
import json
import math
import re


def _fingerprint(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Expected a recording SHA256")
    return value


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def prepare_manifest(selection: dict, original_frame_metadata: dict | None = None):
    """Upgrade the neutral split selection without reading any referenced file.

    Original coarse labels, aliases, point conflicts and selection metadata are
    retained verbatim under ``original_selection``. Session/camera/calendar-date
    fields start unknown even if a filename appears to encode them. A historical
    'frozen' selection string cannot approve new session grouping.
    """
    records, seen, neutral_names = [], set(), set()
    original_frame_metadata = original_frame_metadata or {}
    for group in selection["groups"]:
        source_hash = _fingerprint(group["recording_id"])
        if source_hash in seen:
            raise ValueError("One source hash must have exactly one duplicate/split group")
        seen.add(source_hash)
        split = {"locked_holdout": "reserved"}.get(group["split"], group["split"])
        if split not in {"development", "reserved"}:
            raise ValueError("Unknown recording split")
        neutral = group.get("neutral_file")
        if split == "reserved" and neutral is None:
            pass  # Metadata-only reserved inventory need not expose/create media aliases.
        elif not isinstance(neutral, str) or not re.fullmatch(r"clip\d{3}\.mov", neutral):
            raise ValueError("Expected a neutral source basename")
        if neutral is not None and neutral in neutral_names:
            raise ValueError("A neutral source name cannot identify different recordings")
        if neutral is not None:
            neutral_names.add(neutral)
        frame_metadata = copy.deepcopy(original_frame_metadata.get(source_hash, {}))
        if frame_metadata.get("source_sha256", source_hash) != source_hash:
            raise ValueError("Frame metadata must refer to the same source hash")
        records.append(
            {
                "recording_id": source_hash,
                "source_sha256": source_hash,
                "duplicate_group_id": source_hash,
                "neutral_file": neutral,
                "split": split,
                "original_selection": copy.deepcopy(group),
                "source_frame_metadata": frame_metadata,
                "session_group": {"session_id": None, "review_status": "unreviewed"},
                "camera_group": {"camera_id": None, "review_status": "unreviewed"},
                "recording_date": {"date": None, "basis": None, "review_status": "unreviewed"},
                "annotation_lineage": [],
                "correction_lineage": [],
                "exposure_audit": [],
                "training_permitted": False,
            }
        )
    if not records:
        raise ValueError("No recording groups")
    return {
        "schema_version": 1,
        "purpose": "frozen_inference_development_and_reviewed_evaluation",
        "source_selection_sha256": _digest(selection),
        "original_selection_metadata": copy.deepcopy(
            {k: v for k, v in selection.items() if k != "groups"}
        ),
        "split_status": "provisional_pending_session_review",
        "session_grouping_status": "unreviewed",
        "records": records,
        "history": [],
        "weights_updated": False,
    }


def _review_stamp(reviewer, reviewed_at, basis):
    if not all(isinstance(v, str) and v.strip() for v in (reviewer, reviewed_at, basis)):
        raise ValueError("Actual reviewer, review time and evidence basis are required")
    return {"reviewer": reviewer, "reviewed_at": reviewed_at, "basis": basis}


def record_group_review(
    manifest,
    recording_id,
    *,
    session_id,
    camera_id=None,
    reviewer,
    reviewed_at,
    basis,
):
    """Apply an explicit human grouping fact to a copy, retaining prior lineage.

    A singleton session must also be an explicit human decision. This function
    validates metadata structure, not whether a human actually made the claim.
    """
    if manifest["split_status"] == "frozen":
        raise ValueError("Frozen manifests require a new explicit evaluation revision")
    stamp = _review_stamp(reviewer, reviewed_at, basis)
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("An explicit reviewed session ID is required")
    result = copy.deepcopy(manifest)
    matches = [r for r in result["records"] if r["recording_id"] == recording_id]
    if len(matches) != 1:
        raise ValueError("Unknown or repeated recording ID")
    record = matches[0]
    previous = copy.deepcopy({k: record[k] for k in ("session_group", "camera_group")})
    record["session_group"] = {
        "session_id": session_id,
        "review_status": "human_confirmed",
        **stamp,
    }
    if camera_id is not None:
        if not isinstance(camera_id, str) or not camera_id.strip():
            raise ValueError("Camera ID must remain unknown or be explicitly reviewed")
        record["camera_group"] = {
            "camera_id": camera_id,
            "review_status": "human_confirmed",
            **stamp,
        }
    record["correction_lineage"].append(
        {"kind": "session_camera_grouping", "previous": previous, **stamp}
    )
    result["history"].append({"kind": "group_review", "recording_id": recording_id, **stamp})
    return result


def development_allowlist(manifest):
    """Return neutral/hash fields only, never coarse labels or original aliases."""
    return [
        {
            "recording_id": r["recording_id"],
            "neutral_file": r["neutral_file"],
            "split": "development",
        }
        for r in manifest["records"]
        if r["split"] == "development"
    ]


def assert_development_recording(manifest, recording_id, actual_sha256):
    expected = _fingerprint(recording_id)
    if _fingerprint(actual_sha256) != expected:
        raise ValueError("Development source hash mismatch")
    matches = [r for r in development_allowlist(manifest) if r["recording_id"] == expected]
    if len(matches) != 1:
        raise ValueError("Reserved or unknown recording is excluded from development")
    return matches[0]


def freeze_manifest(manifest, *, reviewer, reviewed_at, basis):
    """Freeze only explicit reviewed session groups, rejecting cross-split leakage."""
    stamp = _review_stamp(reviewer, reviewed_at, basis)
    if manifest["split_status"] == "frozen":
        raise ValueError("Manifest already frozen")
    sessions, seen = {}, set()
    for record in manifest["records"]:
        source_hash = _fingerprint(record["source_sha256"])
        if source_hash in seen or record["recording_id"] != source_hash:
            raise ValueError("Duplicate source groups must not cross split boundaries")
        seen.add(source_hash)
        group = record["session_group"]
        if group["review_status"] != "human_confirmed" or not group.get("session_id"):
            raise ValueError("Session continuity requires explicit human review before freezing")
        splits = sessions.setdefault(group["session_id"], set())
        splits.add(record["split"])
        if len(splits) != 1:
            raise ValueError("A continuous session cannot cross development/reserved splits")
        if record["split"] == "reserved" and any(
            entry.get("purpose")
            in {"development", "prompt_tuning", "model_selection", "calibration"}
            for entry in record["exposure_audit"]
        ):
            raise ValueError("Reserved development exposure must be adjudicated before evaluation")
    result = copy.deepcopy(manifest)
    result["split_status"] = "frozen"
    result["session_grouping_status"] = "human_confirmed"
    result["history"].append(
        {"kind": "freeze", "prior_manifest_sha256": _digest(manifest), **stamp}
    )
    result["frozen_manifest_sha256"] = _digest(result)
    return result


def evaluate_events(
    predictions,
    reviewed_events,
    *,
    tolerance_sec=1.0,
    require_actor=True,
    require_role=True,
    require_provision=True,
    complete_reviewed_population=False,
):
    """One-to-one event matching against explicitly human-confirmed targets.

    Inputs use start_sec/end_sec plus optional actor_id/role/provision_id/version.
    Reviewed abstention targets and model abstentions are reported separately.
    Unreviewed targets cannot contribute positives, negatives or accuracy. The
    input population must be a reviewed evaluation interval, not a full-video
    claim based on a few reviewed positive examples.
    """
    if not math.isfinite(tolerance_sec) or tolerance_sec < 0:
        raise ValueError("Invalid declared event matching tolerance")
    targets = [e for e in reviewed_events if e.get("review_status") == "human_confirmed"]
    abstention_targets = [e for e in targets if e.get("target_kind") == "abstention"]
    targets = [e for e in targets if e.get("target_kind") != "abstention"]
    abstentions = [
        p for p in predictions if p.get("assessment") in {"abstain", "insufficient_evidence"}
    ]
    predictions = [p for p in predictions if p not in abstentions]
    for event in [*targets, *predictions, *abstentions, *abstention_targets]:
        if not all(math.isfinite(event.get(k, math.nan)) for k in ("start_sec", "end_sec")):
            raise ValueError("Source event intervals must be finite")
        if not 0 <= event["start_sec"] <= event["end_sec"]:
            raise ValueError("Invalid source event interval")

    def temporal_match(prediction, target):
        return (
            abs(prediction["start_sec"] - target["start_sec"]) <= tolerance_sec
            and abs(prediction["end_sec"] - target["end_sec"]) <= tolerance_sec
        )

    def compatible(prediction, target):
        if not temporal_match(prediction, target):
            return False
        if prediction.get("event_type") != target.get("event_type"):
            return False
        required = []
        if require_actor:
            required += ["actor_id", "recipient_id"]
        if require_role:
            required += ["role"]
        if require_provision:
            required += ["provision_id", "provision_version"]
        return all(target.get(k) is None or prediction.get(k) == target[k] for k in required)

    edges = {
        i: sorted(
            [j for j, target in enumerate(targets) if compatible(prediction, target)],
            key=lambda j: (abs(prediction["start_sec"] - targets[j]["start_sec"]), j),
        )
        for i, prediction in enumerate(predictions)
    }
    # Maximum-cardinality bipartite matching; one prediction cannot cover several
    # real events, and an early ambiguous match cannot consume a unique target.
    matched = {}

    def augment(index, seen):
        for target_index in edges[index]:
            if target_index in seen:
                continue
            seen.add(target_index)
            if target_index not in matched or augment(matched[target_index], seen):
                matched[target_index] = index
                return True
        return False

    for index in sorted(edges, key=lambda i: (len(edges[i]), i)):
        augment(index, set())
    true_positives = len(matched)
    total_targets, total_predictions = len(targets), len(predictions)
    return {
        "reviewed_event_targets": total_targets,
        "unreviewed_targets_excluded": len(reviewed_events)
        - len(targets)
        - len(abstention_targets),
        "true_positives": true_positives,
        "unmatched_predictions": total_predictions - true_positives,
        "false_positives": total_predictions - true_positives
        if complete_reviewed_population
        else None,
        "false_negatives": total_targets - true_positives,
        "precision": true_positives / total_predictions
        if total_predictions and complete_reviewed_population
        else None,
        "recall": true_positives / total_targets if total_targets else None,
        "prediction_abstentions": len(abstentions),
        "reviewed_abstention_targets": len(abstention_targets),
        "reviewed_abstention_targets_covered": sum(
            any(temporal_match(p, target) for p in abstentions) for target in abstention_targets
        ),
        "reviewed_abstention_targets_missed": sum(
            not any(temporal_match(p, target) for p in abstentions) for target in abstention_targets
        ),
        "event_targets_with_overlapping_abstention": sum(
            any(temporal_match(p, target) for p in abstentions) for target in targets
        ),
        "matches": [{"target_index": j, "prediction_index": i} for j, i in sorted(matched.items())],
        "matching_policy": {
            "boundary_tolerance_sec": tolerance_sec,
            "actor": require_actor,
            "role": require_role,
            "provision_and_version": require_provision,
            "one_to_one": True,
        },
        "scope": "supplied_human_reviewed_evaluation_population_only",
        "complete_reviewed_population": complete_reviewed_population,
    }
