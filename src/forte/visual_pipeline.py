"""Production upload -> automatic proposals -> resident model -> rules -> JPEGs."""

import base64
import time
from pathlib import Path

from forte.contracts import DoneJob, Violation
from forte.jobs import atomic_json
from forte.live_tracking import automatic_tracks
from forte.person_proposals import sha256
from forte.temporal_rules import temporal_checks
from forte.video import decode_video
from forte_visual.inputs import aliases
from forte_visual.scan import Bounds, scan


def analyze_visual(path, work, job_id, backend, deadline, stats=None, *, tracking=None):
    stats = stats if stats is not None else {}
    started = time.monotonic()
    if not backend.ready():
        raise ValueError("model_identity_unavailable")
    atomic_json(
        work / "model-provenance.json",
        {
            "loaded": backend.loaded,
            "warmup": backend.warm_receipt,
            "runtime": "forte.visual_pipeline/1",
            "reference_input": False,
            "application_source_hashes": {
                name: sha256(Path(module.__file__))
                for name, module in (
                    ("pipeline", __import__(__name__, fromlist=["analyze_visual"])),
                    ("scanner", __import__("forte_visual.scan", fromlist=["scan"])),
                    ("runtime", __import__("forte.visual_runtime", fromlist=["ResidentScanner"])),
                    ("tracking", __import__("forte.live_tracking", fromlist=["automatic_tracks"])),
                    ("rules", __import__("forte.temporal_rules", fromlist=["temporal_checks"])),
                )
            },
        },
    )
    registry = decode_video(path, work / "frames", deadline)
    manifest = (tracking or automatic_tracks)(registry, backend.config.detector_weights, deadline)
    atomic_json(work / "automatic-tracks.json", manifest.model_dump(mode="json"))
    report = scan(
        manifest,
        path,
        work / "scan",
        backend,
        Bounds(deadline=deadline - 3),
        upload_started=started,
        registry=registry,
    )
    # Source boxes for deterministic area checks retain the same anonymous map.
    people = aliases(manifest, 0)
    report["source_track_boxes"] = {
        f.frame_id: {
            actor: [
                b.xyxy
                for s in manifest.segments
                if s.id in segments
                for b in s.boxes
                if b.frame_id == f.frame_id and not b.outside
            ]
            for actor, segments in people.items()
        }
        for f in manifest.frames
    }
    legal = temporal_checks(report, backend.config)
    atomic_json(work / "temporal-checks.json", legal)
    atomic_json(work / "private-timeline.json", report)
    incomplete = (
        report["status"] != "complete_schedule"
        or bool(report["role_conflicts"])
        or bool(report["coverage"]["unresolved_ranges"])
        or not report["coverage"]["continuous_visibility_validated"]
    )
    accepted = [c for c in legal["checks"] if c["decision"] == "supported"]
    stats.update(
        source_sha256=registry.source_sha256,
        duration_sec=registry.duration,
        decoded_frames=len(registry.frames),
        tracking_segments=len(manifest.segments),
        calls=report["calls"],
        tokens=report["tokens"],
        peak_memory_bytes=report["peak_memory_bytes"],
        scan_status=report["status"],
        confirmed_events=len(accepted),
        model_route=backend.model,
        base_manifest_sha256=backend.loaded["base_manifest_sha256"],
        training_receipt_sha256=backend.loaded["training_receipt_sha256"],
        total_seconds=time.monotonic() - started,
    )
    if time.monotonic() >= deadline:
        raise ValueError("processing_timeout")
    # Empty predictions and sparse coverage never prove a normal transaction.
    # No category has yet validated full normal-opportunity/absence acceptance.
    if not accepted:
        raise ValueError("insufficient_evidence")
    frames = {f.frame_id: f for f in registry.frames}
    violations = []
    association = []
    for check in accepted:
        ids = check["evidence_frame_ids"]
        evidence = registry.evidence(ids)
        source = check["sources"][-1]
        visible = (
            "Модель выделила перемещение того же предполагаемого кассира за пределы "
            "предложенной рабочей области во время продолжающегося приема наличных."
        )
        citation = (
            f"{source['document_title']}, пункт {source['provision']}; {source['url']}. "
            f"Редакция {source['version_id']}; "
            "основание применимости сохранено в частном протоколе."
        )
        limits = (
            " Видимые признаки не устанавливают намерение, содержание документов или скрытый учет."
        )
        if incomplete:
            limits += " Другие фрагменты записи остаются неразрешенными."
        violations.append(
            Violation(
                type="Оставление рабочего места при приеме наличных",
                timecode_sec=frames[check["timecode_frame_id"]].timestamp_sec,
                description=visible + " " + citation + limits,
                evidence_frames=evidence,
            )
        )
        for fid, ev in zip(
            sorted(ids, key=lambda f: frames[f].timestamp_sec), evidence, strict=True
        ):
            target = work / f"evidence-{len(association):03d}.jpg"
            target.write_bytes(base64.b64decode(ev.image_base64))
            target.chmod(0o600)
            association.append(
                {
                    "file": target.name,
                    "frame_id": fid,
                    "source_pts": frames[fid].source_pts,
                    "timestamp_sec": ev.timestamp_sec,
                    "source_sha256": registry.source_sha256,
                }
            )
    atomic_json(work / "evidence-association.json", association)
    return DoneJob(job_id=job_id, verdict="violation", violations=violations)
