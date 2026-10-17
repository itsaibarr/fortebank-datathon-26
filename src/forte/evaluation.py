"""Aggregate private development results without emitting footage or scene narratives."""

import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

from forte.jobs import RESPONSE


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def evaluate(manifest: dict, results: Path) -> dict:
    groups = manifest["groups"]
    if not groups or any(g["split"] != "development" for g in groups):
        raise ValueError("Only an explicit nonempty development manifest is accepted")
    ids = [g["recording_id"] for g in groups]
    names = [g["neutral_file"] for g in groups]
    if len(set(ids)) != len(ids) or len(set(names)) != len(names):
        raise ValueError("Manifest contains duplicate recordings or result names")
    if any(not re.fullmatch(r"clip\d{3}\.mov", name) for name in names):
        raise ValueError("Use neutral clipNNN.mov names without paths")
    if any(not isinstance(g["positive"], bool) for g in groups):
        raise ValueError("Labels must be explicit booleans")
    counts = dict.fromkeys(
        [
            "videos",
            "positives",
            "negatives",
            "tp",
            "tn",
            "fp",
            "fn",
            "failed_positive",
            "failed_negative",
        ],
        0,
    )
    failures = Counter()
    latencies, errors = [], []
    eligible, localized, events = 0, 0, 0
    for group in groups:
        directory = results / Path(group["neutral_file"]).stem
        result = RESPONSE.validate_json((directory / "result.json").read_text())
        summary = json.loads((directory / "summary.json").read_text())
        if summary["source_sha256"] != group["recording_id"]:
            raise ValueError("Result source fingerprint does not match the manifest")
        seconds = summary["seconds"]
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid client timing")
        latencies.append(seconds)
        positive = group["positive"]
        counts["videos"] += 1
        counts["positives" if positive else "negatives"] += 1
        points = group.get("label_points_sec", [])
        point_eligible = positive and points and group.get("strict_point_scoring_eligible", False)
        eligible += bool(point_eligible)
        if result.status == "processing":
            raise ValueError("All results must be terminal before evaluation")
        if result.status == "failed":
            counts["failed_positive" if positive else "failed_negative"] += 1
            failures[result.error.code] += 1
            continue
        predicted = result.verdict == "violation"
        key = ("tp" if predicted else "fn") if positive else ("fp" if predicted else "tn")
        counts[key] += 1
        events += len(result.violations)
        if point_eligible and result.violations:
            error = min(abs(event.timecode_sec - p) for event in result.violations for p in points)
            errors.append(error)
            localized += error <= 5
    n, pos, neg = counts["videos"], counts["positives"], counts["negatives"]
    failed = counts["failed_positive"] + counts["failed_negative"]
    return {
        "split_status": manifest.get("split_status", "unspecified"),
        "code_commit": manifest.get("code_commit"),
        "evaluation_scope": "exploratory development, not independent validation",
        "counts": counts,
        "reported_events": events,
        "completed_fraction": (n - failed) / n,
        "accuracy_including_failed": (counts["tp"] + counts["tn"]) / n,
        "effective_recall": ratio(counts["tp"], pos),
        "false_negative_rate_including_failed": ratio(
            counts["fn"] + counts["failed_positive"], pos
        ),
        "false_positive_rate": ratio(counts["fp"], neg),
        "failure_codes": dict(failures),
        "point_proximity": {
            "eligible_positive_videos": eligible,
            "detected_videos_with_point_error": len(errors),
            "median_error_sec": statistics.median(errors) if errors else None,
            "fraction_within_5_sec_including_misses": ratio(localized, eligible),
            "limitation": "Approximate supplied points, no verified intervals or event categories. "
            "Closest prediction is a proximity diagnostic, not proof of the same action.",
        },
        "client_latency_sec": {
            "median": statistics.median(latencies),
            "p95": sorted(latencies)[math.ceil(0.95 * n) - 1],
            "max": max(latencies),
            "over_300_seconds": sum(t >= 300 for t in latencies),
        },
    }
