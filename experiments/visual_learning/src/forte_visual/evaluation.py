"""Separate tracking and complete-scan reference scoring, grouped by source session."""

from forte.tracking import iou

from forte_visual.adapter import reviewed_targets
from forte_visual.benchmark import fraction, maximum_edge_matching, maximum_matches
from forte_visual.scan import union


def track_metrics(oracle, automatic):
    if oracle.source_sha256 != automatic.source_sha256 or oracle.frames != automatic.frames:
        raise ValueError("Tracker evaluation must share exact source registry")
    # Only independent confirmed oracle geometry contributes to denominators.
    previous, lost, switches, fragments, matched, visible, false = {}, set(), 0, 0, 0, 0, 0
    for frame in oracle.frames:
        truth = [
            (s.id, b.xyxy)
            for s in oracle.segments
            if s.review.status == "confirmed"
            for b in s.boxes
            if b.frame_id == frame.frame_id
            and not b.outside
            and not b.occluded
            and b.review.status == "confirmed"
        ]
        predicted = [
            (s.id, b.xyxy)
            for s in automatic.segments
            for b in s.boxes
            if b.frame_id == frame.frame_id and not b.outside
        ]
        # Geometry matching is maximum-cardinality at IoU .5, never model role labels.
        edges = {
            i: [j for j, (_, box) in enumerate(truth) if iou(pbox, box) >= 0.5]
            for i, (_, pbox) in enumerate(predicted)
        }
        pairs = maximum_edge_matching(list(edges.values()))
        visible += len(truth)
        matched += len(pairs)
        false += len(predicted) - len(pairs)
        matched_truth = set()
        for i, j in pairs:
            target, detected = truth[j][0], predicted[i][0]
            matched_truth.add(target)
            if target in previous and previous[target] != detected:
                switches += 1
            if target in lost:
                fragments += 1
                lost.remove(target)
            previous[target] = detected
        lost.update(
            target for target, _ in truth if target not in matched_truth and target in previous
        )
    return {
        "group_id": oracle.session_group or oracle.recording_group,
        "reviewed_visible_boxes": visible,
        "matched_boxes": matched,
        "missing_boxes": visible - matched,
        "false_boxes": false,
        "id_switches": switches,
        "fragments": fragments,
        "geometry_recall": fraction(matched, visible),
        "scope": "reviewed visible oracle ranges only; no role correctness inference",
    }


def scan_metrics(manifest, annotation, report):
    if report["clip_id"] != manifest.clip_id or report["source_sha256"] != manifest.source_sha256:
        raise ValueError("Timeline/reference source mismatch")
    refs = [
        f
        for f in reviewed_targets(manifest, annotation)
        if f.kind == "action" and f.value != "unclear" and f.observation_state == "observed"
    ]
    proposed = sum(
        any(
            p["segment_id"] in f.segment_ids
            and max(0, p["center_sec"] - 4) <= f.end_sec
            and min(manifest.duration_sec, p["center_sec"] + 4) >= f.start_sec
            for p in report["proposals"]
        )
        for f in refs
    )
    expected = [
        {
            "relation": (
                tuple(sorted(f.segment_ids)),
                f.counterpart_actor_id,
                f.actor_participation,
                f.value,
            ),
            "interval": (f.start_sec, f.end_sec),
        }
        for f in refs
    ]
    segments = {s.id: s for s in manifest.segments}

    def counterpart_id(alias):
        ss = report["actor_segments"].get(alias, [])
        return segments[ss[0]].person_id if len(ss) == 1 else None

    predictions = [
        {
            "relation": (
                tuple(sorted(f["segments"])),
                counterpart_id(f["other_actor_id"]),
                f.get("actor_participation", "unclear"),
                f["value"],
            ),
            "interval": (f["start_sec"], f["end_sec"]),
        }
        for f in report["visual_timeline"]
        if f["kind"] == "action" and f["visibility"] == "observed" and f["value"] != "unclear"
    ]
    scores = {}
    for threshold in (0.5, 0.75):
        matches = maximum_matches(predictions, expected, threshold)
        tp, fp, fn = len(matches), len(predictions) - len(matches), len(expected) - len(matches)
        errors = [
            abs(predictions[i]["interval"][k] - expected[j]["interval"][k])
            for i, j in matches
            for k in (0, 1)
        ]
        scores[str(threshold)] = {
            "tp": tp,
            "fp": None,
            "unadjudicated_predictions": fp,
            "fn": fn,
            "precision": None,
            "recall": fraction(tp, tp + fn),
            "f1": None,
            "boundary_mae_sec": fraction(sum(errors), len(errors)),
        }
    inspected = sum(b - a for a, b in union(report["coverage"]["closely_inspected_ranges"]))
    return {
        "group_id": manifest.session_group or manifest.recording_group,
        "reviewed_events": len(refs),
        "proposed_reviewed_events": proposed,
        "proposal_recall": fraction(proposed, len(refs)),
        "events": scores,
        "false_events_per_minute": None,
        "unadjudicated_predictions": scores["0.5"]["unadjudicated_predictions"],
        "closely_inspected_fraction": inspected / manifest.duration_sec,
        "unresolved_fraction": sum(b - a for a, b in report["coverage"]["unresolved_ranges"])
        / manifest.duration_sec,
        "scan_status": report["status"],
        "omission_eligible": False,
        "warning": (
            "Unmatched predictions require adjudication. "
            "Incomplete action references cannot establish false events."
        ),
    }
