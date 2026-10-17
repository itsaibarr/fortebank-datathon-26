"""Versioned frozen inference: source -> participants -> timeline -> official rules.

The original binary detector remains independently reproducible. This route
persists uncertainty and provisional findings without inventing a clean negative.
"""

import hashlib
import html
import json
import time
from pathlib import Path
from uuid import uuid4

from forte.inference import LocalVLM
from forte.timeline import (
    EvidenceTools,
    ScanBounds,
    private_directory,
    scan_recording,
    sha256,
    source_frame_table,
    write_private,
)
from forte.video import decode_video


def source_code_fingerprints():
    """Fingerprint shipped application sources, including optional analysis paths.

    These hashes identify code bytes in the installed package; they do not claim
    that every optional module executed. Public weights, legal snapshots and
    the effective run configuration retain their separate provenance records.
    """
    modules = {
        "pipeline": "reasoning_pipeline",
        "timeline": "timeline",
        "video": "video",
        "inference": "inference",
        "model_profile": "model_profile",
        "frozen_tracking": "frozen_tracking",
        "person_proposals": "person_proposals",
        "tracking": "tracking",
        "legal_reasoning": "legal_reasoning",
        "legal": "legal",
        "retrieval": "retrieval",
        "annotations": "annotations",
        "contracts": "contracts",
        "contracts_v2": "contracts_v2",
        "settings": "settings",
        "jobs": "jobs",
        "worker": "worker",
        "api": "api",
        "manifest": "manifest",
    }
    package = Path(__file__).resolve().parent
    return {name: sha256(package / f"{module}.py") for name, module in modules.items()}


def load_reasoning_config(settings):
    supplied = getattr(settings, "reasoning_config", None)
    if supplied is None:
        raise ValueError("An explicit frozen reasoning configuration is required")
    config = (
        dict(supplied) if isinstance(supplied, dict) else json.loads(Path(supplied).read_bytes())
    )
    if not isinstance(config, dict) or not {"tracking", "legal"} <= config.keys():
        raise ValueError("Reasoning configuration requires tracking and legal sections")
    unknown = set(config) - {
        "tracking",
        "legal",
        "bounds",
        "model",
        "schema_version",
        "model_profile",
        "training",
        "status",
    }
    if unknown:
        raise ValueError("Unknown frozen reasoning configuration sections")
    if not isinstance(config["tracking"], dict) or not isinstance(config["legal"], dict):
        raise ValueError("Invalid reasoning configuration sections")
    if config.get("schema_version", 1) != 1:
        raise ValueError("Unsupported frozen reasoning configuration version")
    training = config.get("training", {})
    if not isinstance(training, dict) or any(
        training.get(key, False) is not False for key in ("enabled", "weight_updates_permitted")
    ):
        raise ValueError("Frozen reasoning prohibits training or weight updates")
    model = config.get("model", {})
    if not isinstance(model, dict):
        raise ValueError("Invalid frozen model configuration")
    # A training path is deliberately absent. Reject accidental adapter routing.
    if model.get("adapter_path") or model.get("adapters"):
        raise ValueError("Frozen reasoning does not permit trained adapters")
    if model.get("quantization") is not None or model.get("precision", "bfloat16") != "bfloat16":
        raise ValueError("Frozen reasoning requires unquantized BF16 weights")
    if model.get("revision", settings.model_revision) != settings.model_revision:
        raise ValueError("Frozen model revision differs from serving configuration")
    limits = config.get("bounds", {})
    for name, default, maximum in (
        ("max_calls", 32, 64),
        ("max_tokens", 80000, 200000),
        ("max_reinspections", 4, 12),
        ("legal_max_calls", 6, 12),
    ):
        value = limits.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
            raise ValueError("Invalid bounded reasoning budget: " + name)
        limits[name] = value
    config["bounds"] = limits
    return config


def model_backend(settings):
    # Root runtime owns exact checkpoint/revision verification; the baseline
    # adapter has the same request interface and remains an explicit rollback.
    return LocalVLM(
        settings.model_url,
        settings.model_name,
        expected_revision=settings.model_revision,
        max_context_tokens=settings.max_context_tokens,
        enable_thinking=False,
        request_timeout=100,
    )


def export_event_evidence(registry, timeline, run, deadline, table, max_frames=48):
    tools = EvidenceTools(registry, {}, run / "evidence", deadline, table)
    by_id = {row["frame_id"]: row for row in table["frames"]}
    chosen, per_event = [], {}
    for event in timeline["events"]:
        ids = sorted(set(event["evidence_frame_ids"]), key=lambda fid: by_id[fid]["timestamp_sec"])
        picks = list(dict.fromkeys([ids[0], event["decisive_frame_id"], ids[-1]]))
        per_event[event["event_id"]] = picks
        chosen.extend(fid for fid in picks if fid not in chosen)
    selected = chosen[:max_frames]
    associations = []
    for offset in range(0, len(selected), 16):
        if time.monotonic() >= deadline:
            break
        try:
            images = tools.original_jpegs(selected[offset : offset + 16])
        except TimeoutError:
            break
        for fid, raw in images.items():
            filename = fid + ".jpg"
            target = tools.output / filename
            target.write_bytes(raw)
            target.chmod(0o600)
            row = by_id[fid]
            associations.append(
                {
                    "frame_id": fid,
                    "file": "evidence/" + filename,
                    "source_sha256": registry.source_sha256,
                    "jpeg_sha256": hashlib.sha256(raw).hexdigest(),
                    "image_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_pts": row["source_pts"],
                    "time_base": row["time_base"],
                    "timestamp_sec": row["timestamp_sec"],
                    "oriented_size": row["oriented_size"],
                    "rotation_degrees": row["rotation_degrees"],
                    "kind": "decoded_source_jpeg_no_overlay_no_resize",
                }
            )
    exported = {item["frame_id"]: item for item in associations}
    events = []
    for event in timeline["events"]:
        events.append(
            {
                **event,
                "evidence": [
                    exported[fid] for fid in per_event[event["event_id"]] if fid in exported
                ],
                "evidence_export_complete": set(per_event[event["event_id"]]) <= exported.keys(),
                "assessment": "insufficient_evidence",
                "review_status": "unreviewed",
            }
        )
    write_private(run / "evidence-association.json", associations)
    return events, len(exported) < len(chosen)


def write_review_packet(run, result):
    rows = []
    for event in result["events"]:
        evidence = "".join(
            '<a href="'
            + html.escape(frame["file"], quote=True)
            + '"><img src="'
            + html.escape(frame["file"], quote=True)
            + '" width="240" alt="Source '
            + html.escape(frame["frame_id"], quote=True)
            + '"></a>'
            for frame in event["evidence"]
        )
        rows.append(
            "<article><h2>"
            + html.escape(event["event_id"])
            + "</h2><p>"
            + html.escape(str(event["start_sec"]) + "–" + str(event["end_sec"]) + " s")
            + " · "
            + html.escape(", ".join(event["actor_ids"]) or "unresolved actor")
            + "</p><p>"
            + html.escape(event["value"])
            + "</p>"
            + evidence
            + "<p>"
            + html.escape("; ".join(event["uncertainty"]))
            + "</p></article>"
        )
    body = (
        "<!doctype html><html lang=en><meta charset=utf-8>"
        '<meta name="referrer" content="no-referrer">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
        'img-src &#39;self&#39; data:; style-src &#39;unsafe-inline&#39;">'
        "<title>Local frozen inference review</title>"
        "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}"
        "article{border-top:1px solid #bbb;padding:1rem 0}img{margin:.3rem}</style>"
        "<h1>Local frozen inference review</h1><p>Provisional model observations; "
        "human visual, geometry, role and legal review are separate. Sampling does not "
        "establish absence or exact action boundaries.</p><p>Execution: "
        + html.escape(result["execution"]["status"])
        + "; assessment: "
        + html.escape(result["assessment"])
        + "</p>"
        + "".join(rows)
        + '<p><a href="result.json">Complete source/condition record</a></p></html>'
    )
    target = run / "review.html"
    target.write_text(body)
    target.chmod(0o600)


def analyze_reasoning(
    source: Path,
    work_dir: Path,
    settings,
    *,
    deadline=None,
    backend=None,
    tracking=None,
    legal=None,
):
    """Execute real frozen inference; injectable components are for synthetic tests.

    All artifacts live in a fresh revision directory. External source/annotation
    producers are read-only. Existing correction sidecars are never regenerated.
    """
    from forte.frozen_tracking import analyze_participants, require_outbound_blocked
    from forte.legal_reasoning import LegalEvidenceService

    started = time.monotonic()
    deadline = deadline if deadline is not None else started + getattr(settings, "job_timeout", 270)
    config = load_reasoning_config(settings)
    isolation = require_outbound_blocked()
    backend = backend if backend is not None else model_backend(settings)
    backend.deadline = deadline
    if not backend.ready():
        raise ValueError("Frozen model identity/readiness unavailable")
    root = private_directory(work_dir)
    run = root / ("reasoning-" + uuid4().hex)
    run.mkdir(mode=0o700)
    write_private(run / "configuration.json", config)
    write_private(run / "execution.json", {"status": "processing", "weights_frozen": True})
    metrics = {}
    try:
        stage = time.monotonic()
        registry = decode_video(source, run / "sampled-frames", deadline)
        table = source_frame_table(registry, deadline)
        write_private(run / "source-frames.json", table)
        metrics["decoding_seconds"] = time.monotonic() - stage
        stage = time.monotonic()
        participant_report = (tracking or analyze_participants)(
            registry, run / "tracking", config["tracking"], deadline=deadline
        )
        if (
            participant_report.get("source_sha256", registry.source_sha256)
            != registry.source_sha256
        ):
            raise ValueError("Participant registry belongs to another source")
        write_private(run / "participants.json", participant_report)
        metrics["tracking_seconds"] = time.monotonic() - stage
        limits = config["bounds"]
        bounds = ScanBounds(
            deadline=deadline,
            max_calls=limits["max_calls"],
            max_tokens=limits["max_tokens"],
            max_reinspections=limits["max_reinspections"],
        )
        stage = time.monotonic()
        # Keep legal checks and original JPEG export reachable within the job deadline.
        timeline_deadline = min(
            deadline, time.monotonic() + max(1, (deadline - time.monotonic()) * 0.55)
        )
        backend.deadline = timeline_deadline
        timeline = scan_recording(
            registry,
            participant_report,
            backend,
            run / "scan",
            timeline_deadline,
            bounds=bounds,
            table=table,
        )
        backend.deadline = deadline
        metrics["timeline_seconds"] = time.monotonic() - stage
        law = config["legal"]
        service = legal or LegalEvidenceService(
            Path(law["release"]), Path(law["cards"]) if law.get("cards") else None
        )
        stage = time.monotonic()
        legal_deadline = max(time.monotonic(), deadline - 10)
        backend.deadline = legal_deadline
        legal_report = service.evaluate_timeline(
            timeline,
            registry,
            backend,
            run / "legal",
            legal_deadline,
            event_date=law.get("event_date"),
            operation_context=law.get("operation_context"),
            max_calls=limits["legal_max_calls"],
            table=table,
        )
        backend.deadline = deadline
        write_private(run / "legal-assessments.json", legal_report)
        metrics["legal_seconds"] = time.monotonic() - stage
        events, evidence_limited = export_event_evidence(registry, timeline, run, deadline, table)
        for event in events:
            linked = [
                assessment
                for assessment in legal_report.get("assessments", [])
                if set(assessment.get("observation_ids", [])) & set(event["observation_ids"])
            ]
            event["legal_assessment_ids"] = [a["assessment_id"] for a in linked]
            event["legal_assessments"] = linked
            outcomes = {a["assessment"] for a in linked}
            if "supported_violation" in outcomes and event["evidence_export_complete"]:
                event["assessment"] = "supported_violation"
            elif linked and outcomes == {"not_applicable"}:
                event["assessment"] = "not_applicable"
            elif linked and outcomes <= {"no_violation_observed", "not_applicable"}:
                event["assessment"] = "no_violation_observed"
        states = [
            a.get("assessment", a.get("decision")) for a in legal_report.get("assessments", [])
        ]
        supported = any(e["assessment"] == "supported_violation" for e in events)
        complete = (
            timeline["status"] == "complete_schedule"
            and not timeline["coverage"]["unexamined_intervals"]
            and not evidence_limited
            and legal_report.get("status") == "complete_scoped_schedule"
        )
        assessment = "supported_violation" if supported else "insufficient_evidence"
        if complete and states and all(s == "not_applicable" for s in states):
            assessment = "not_applicable"
        elif (
            complete
            and states
            and all(s in {"no_violation_observed", "not_applicable"} for s in states)
        ):
            assessment = "no_violation_observed"
        metrics.update(
            total_seconds=time.monotonic() - started,
            decoded_frames=len(registry.frames),
            source_duration_sec=registry.duration,
            scan=timeline["metrics"],
            legal=legal_report.get("metrics", {}),
        )
        result = {
            "schema_version": "forte.reasoning/1",
            "source_sha256": registry.source_sha256,
            "source": {
                "duration_sec": registry.duration,
                "frame_count": len(registry.frames),
                "original_name": source.name,
                "frame_table": "source-frames.json",
            },
            "execution": {
                "status": "completed" if complete else "partial",
                "weights_frozen": True,
                "network_isolation": isolation,
                "budget_exhausted": timeline["status"] == "budget_exhausted",
            },
            "assessment": assessment,
            "review_status": "unreviewed",
            "timeline": timeline,
            "participants": participant_report,
            "legal": legal_report,
            "events": events,
            "metrics": metrics,
            "provenance": {
                "model": getattr(backend, "loaded", None),
                "model_name": getattr(backend, "model", None),
                "config_sha256": sha256(run / "configuration.json"),
                "source_code": source_code_fingerprints(),
                "source_code_scope": "shipped_application_sources_including_optional_paths",
            },
            "artifacts": {
                "revision": run.name,
                "result": "result.json",
                "review": "review.html",
                "source_frames": "source-frames.json",
                "timeline": "scan/timeline.json",
                "evidence": "evidence-association.json",
            },
            "limitations": [
                "Model observations and rule interpretations require independent review.",
                "Sparse samples do not establish continuous visibility or missing actions.",
                "Source envelope timestamps are not exact action onset/offset.",
                *legal_report.get("limitations", []),
            ],
        }
        write_private(run / "result.json", result)
        write_private(run / "execution.json", result["execution"])
        write_review_packet(run, result)
        # Stable job-level pointer is atomic; revision artifacts remain untouched.
        write_private(root / "reasoning-result.json", result)
        return result
    except Exception as exc:
        write_private(
            run / "execution.json",
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "weights_frozen": True,
                "seconds": time.monotonic() - started,
            },
        )
        raise
