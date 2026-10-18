"""Small private smoke harness; labels select cases and never enter inference.

Preparation reads provenance only. Execute the saved source snapshot with OS
network denial. This module never grants legal, human-review or training approval.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path

from forte.dataset import audit_archive
from forte.frozen_tracking import private_directory
from forte.person_proposals import allowlisted_sources, sha256, verify_source


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    Path(path).chmod(0o600)


def select_smoke(selection, index):
    """Deterministic debugging set, not an independent accuracy sample.

    Use supplied labels only for sampling. Prefer a prior tracking pilot for the
    continuity case, without reading human judgments or feeding them to models.
    The historical role diagnostic is excluded from this new smoke set.
    """
    rows = {row["clip_id"]: row for row in index["records"]}
    eligible = sorted(
        (
            g
            for g in selection["groups"]
            if g["split"] == "development"
            and Path(g["neutral_file"]).stem in rows
            and rows[Path(g["neutral_file"]).stem].get("regression_only") is False
        ),
        key=lambda g: g["neutral_file"],
    )
    if any(type(g["positive"]) is not bool for g in eligible):
        raise ValueError("Sampling requires explicit supplied boolean labels")
    chosen = []
    for positive in (True, False):
        matches = [g for g in eligible if g["positive"] is positive]
        if not matches:
            raise ValueError("A supplied positive and normal development case are required")
        chosen.append(matches[0])
    remaining = [g for g in eligible if g not in chosen]
    pilots = [g for g in remaining if rows[Path(g["neutral_file"]).stem].get("pilot")]
    if not remaining:
        raise ValueError("Three distinct non-diagnostic development groups are required")
    chosen.append((pilots or remaining)[0])
    if len({g["recording_id"] for g in chosen}) != 3:
        raise ValueError("Duplicate recordings cannot be separate smoke cases")
    return chosen


def inference_inputs(chosen, sources):
    """A strict projection prevents reference answers and original names leaking."""
    return [
        {
            "neutral_file": g["neutral_file"],
            "source_sha256": g["recording_id"],
            "source": str(sources / g["neutral_file"]),
        }
        for g in chosen
    ]


def prepare(args):
    root = private_directory(args.output)
    if any(root.iterdir()):
        raise FileExistsError("Use a new empty versioned private directory")
    repo = Path(__file__).resolve().parents[2]
    selection_path = args.private_root / "batch-selection.json"
    index_path = args.private_root / "person-tracking-v1/run-001/index.json"
    selection = json.loads(selection_path.read_bytes())
    index = json.loads(index_path.read_bytes())
    chosen = select_smoke(selection, index)
    archive = audit_archive(args.archive)
    if (archive["mov_files"], archive["annotation_files"]) != (42, 1):
        raise ValueError("Archive differs from the recorded inventory")
    # Enumerate reserved filenames but never open their extracted bytes. Only
    # development aliases are hashed; no reserved video is decoded or selected.
    extracted = {}
    for path in args.extracted.rglob("*"):
        if path.is_file():
            extracted.setdefault(path.name, []).append(path)
    allowed = allowlisted_sources(selection_path, args.private_root / "annotation-review/sources")
    by_hash = {r["recording_group"]: r for r in allowed}
    verified_aliases = 0
    for g in selection["groups"]:
        if g["split"] != "development":
            continue
        record = by_hash[g["recording_id"]]
        verify_source(record)
        for alias in g["files"]:
            matches = extracted.get(Path(alias).name, [])
            if len(matches) != 1 or sha256(matches[0]) != g["recording_id"]:
                raise ValueError("Extracted development alias differs from provenance")
            verified_aliases += 1
    snapshot = root / "snapshot"
    snapshot.mkdir(mode=0o700)
    for directory in ("src", "configs", "legal", "contracts"):
        shutil.copytree(
            repo / directory,
            snapshot / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for filename in ("uv.lock", "pyproject.toml"):
        shutil.copy2(repo / filename, snapshot / filename)
    sources = root / "sources"
    sources.mkdir(mode=0o700)
    for g in chosen:
        target = sources / g["neutral_file"]
        shutil.copyfile(by_hash[g["recording_id"]]["source"], target)
        target.chmod(0o400)
    config = json.loads((repo / "configs/frozen-inference.json").read_bytes())
    config["tracking"]["detector_weights"] = str(
        args.private_root / "person-tracking-v1/_runtime/public/yolox_s.onnx"
    )
    config["tracking"]["reid_manifest"] = str(args.reid_manifest)
    config["legal"]["release"] = str(snapshot / "legal/2026-10-17")
    config["legal"]["cards"] = str(snapshot / "legal/rule-cards.json")
    save(root / "effective-config.json", config)
    save(root / "inference-inputs.json", inference_inputs(chosen, sources))
    save(
        root / "evaluation-selection.json",
        {
            "groups": chosen,
            "sampling": "first supplied positive, first normal, then available tracking pilot",
            "supplied_labels_are_not_independent_reference": True,
            "diagnostic_excluded": True,
            "split_status": selection.get("split_status"),
            "session_split_frozen": False,
        },
    )
    fingerprints = {
        str(p.relative_to(snapshot)): sha256(p) for p in sorted(snapshot.rglob("*")) if p.is_file()
    }
    provenance = {
        "run_id": root.name,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo)
        .decode()
        .strip(),
        "git_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=repo).decode(),
        "snapshot_files": fingerprints,
        "snapshot_sha256": hashlib.sha256(
            json.dumps(fingerprints, sort_keys=True).encode()
        ).hexdigest(),
        "effective_config_sha256": sha256(root / "effective-config.json"),
        "inference_inputs_sha256": sha256(root / "inference-inputs.json"),
        "selection_sha256": sha256(selection_path),
        "tracking_index_sha256": sha256(index_path),
        "archive": archive,
        "verified_development_groups": len(allowed),
        "verified_extracted_development_aliases": verified_aliases,
        "reserved_extracted_media_opened": 0,
        "planned_cases": 3,
        "system": {"platform": platform.platform(), "machine": platform.machine()},
        "weights_updated": False,
    }
    save(root / "provenance.json", provenance)
    print(
        json.dumps(
            {
                k: provenance[k]
                for k in (
                    "run_id",
                    "verified_development_groups",
                    "verified_extracted_development_aliases",
                    "reserved_extracted_media_opened",
                    "planned_cases",
                    "snapshot_sha256",
                )
            }
        )
    )


def verify_snapshot(root):
    provenance = json.loads((root / "provenance.json").read_bytes())
    for relative, digest in provenance["snapshot_files"].items():
        if sha256(root / "snapshot" / relative) != digest:
            raise ValueError("Prepared source snapshot changed")
    for filename, key in (
        ("effective-config.json", "effective_config_sha256"),
        ("inference-inputs.json", "inference_inputs_sha256"),
    ):
        if sha256(root / filename) != provenance[key]:
            raise ValueError("Prepared experiment inputs changed")
    if Path(__file__).resolve() != root / "snapshot/src/forte/mechanic_validation.py":
        raise ValueError("Execute the saved snapshot using its src directory in PYTHONPATH")
    return provenance


def execute(args):
    from forte.frozen_tracking import analyze_participants, require_outbound_blocked
    from forte.legal_reasoning import LegalEvidenceService
    from forte.reasoning_pipeline import analyze_reasoning
    from forte.settings import Settings
    from forte.timeline import source_frame_table
    from forte.video import decode_video

    root = args.output.resolve(strict=True)
    verify_snapshot(root)
    isolation = require_outbound_blocked()
    executions = root / "executions"
    executions.mkdir(mode=0o700)  # immutable: a second invocation must use a new run
    config = json.loads((root / "effective-config.json").read_bytes())
    settings = Settings(
        "unused-local-scan-key",
        executions,
        model_url=args.model_url,
        model_revision=config["model"]["revision"],
        max_context_tokens=config["model"]["max_context_tokens"],
        reasoning_config=config,
    )
    save(
        root / "runtime.json",
        {
            "network_isolation": isolation,
            "packages": {d.metadata["Name"]: d.version for d in distributions()},
            "model_url": args.model_url,
            "inference": "frozen_bfloat16_no_adapters",
            "budget_seconds_per_automatic_attempt": 270,
            "tracking_is_a_separate_component_run": True,
        },
    )
    law = LegalEvidenceService(Path(config["legal"]["release"]), Path(config["legal"]["cards"]))
    save(
        root / "legal-readiness.json",
        {
            "audit": law.audit(),
            "plans": [law.prepare_card(c.id).model_dump(mode="json") for c in law._cards],
            "note": "Plans are public-source preparation; no sponsor legal inference has run.",
        },
    )
    summaries = []
    for item in json.loads((root / "inference-inputs.json").read_bytes()):
        if set(item) != {"neutral_file", "source_sha256", "source"}:
            raise ValueError("Reference material is forbidden in inference inputs")
        source = Path(item["source"])
        if sha256(source) != item["source_sha256"]:
            raise ValueError("Prepared source changed")
        case = executions / source.stem
        case.mkdir(mode=0o700)
        summary = {"source_sha256": item["source_sha256"], "automatic": {}, "tracking": {}}
        started = time.monotonic()
        try:
            result = analyze_reasoning(source, case / "automatic", settings)
            summary["automatic"] = {
                "status": "executed",
                "assessment": result["assessment"],
                "execution": result["execution"],
                "metrics": result["metrics"],
                "revision": result["artifacts"]["revision"],
            }
        except Exception as exc:
            save(case / "automatic-error.json", {"type": type(exc).__name__, "message": str(exc)})
            summary["automatic"] = {
                "status": "blocked"
                if str(exc) == "Frozen model identity/readiness unavailable"
                else "failed",
                "error_type": type(exc).__name__,
                "failure_stage": "runtime" if "readiness" in str(exc) else "execution",
            }
        summary["automatic"]["seconds"] = time.monotonic() - started
        # No synthetic/fallback semantic backend. Real tracking may still run
        # independently when the pinned resident VLM is unavailable.
        started = time.monotonic()
        try:
            deadline = started + 270
            registry = decode_video(source, case / "decode", deadline)
            table = source_frame_table(registry, deadline)
            save(case / "source-frames.json", table)
            decoding = time.monotonic() - started
            participants = analyze_participants(
                registry, case / "tracking", config["tracking"], deadline=deadline
            )
            summary["tracking"] = {
                "status": "executed",
                "decoding_seconds": decoding,
                "tracking_seconds": time.monotonic() - started - decoding,
                "source_frames": len(table["frames"]),
                "detection_samples": len(participants["coverage"]["detection_frame_ids"]),
                "source_duration_sec": registry.duration,
                "geometry_and_identity_accuracy": "not_evaluable_pending_independent_review",
                "continuous_visibility_validated": False,
                "role_hypotheses_created": sum(
                    len(p["role_hypotheses"]) for p in participants["participants"]
                ),
            }
            # Preserve predictions before generating review media or templates.
            save(
                case / "prediction-frozen.json",
                {
                    "participants_sha256": sha256(case / "tracking/participants.json"),
                    "saved_at": datetime.now(UTC).isoformat(),
                    "human_reference_consumed": False,
                },
            )
            packet_started = time.monotonic()
            packet = build_review_packet(case, source, registry, table, participants, summary)
            summary["tracking"]["packet_seconds"] = time.monotonic() - packet_started
            summary["tracking"]["packet_verification"] = packet
        except Exception as exc:
            save(case / "tracking-error.json", {"type": type(exc).__name__, "message": str(exc)})
            summary["tracking"].update(status="failed", error_type=type(exc).__name__)
        summary["tracking"]["component_total_seconds"] = time.monotonic() - started
        if sha256(source) != item["source_sha256"]:
            raise ValueError("Source changed during execution")
        save(case / "summary.json", summary)
        summaries.append(summary)
        print(
            json.dumps(
                {
                    "case_completed": len(summaries),
                    "automatic_status": summary["automatic"]["status"],
                    "tracking_status": summary["tracking"]["status"],
                }
            ),
            flush=True,
        )
    save(root / "stage-results.json", summaries)
    save(
        root / "aggregate.json",
        {
            "planned_recordings": len(summaries),
            "automatic_executed": sum(s["automatic"]["status"] == "executed" for s in summaries),
            "automatic_blocked": sum(s["automatic"]["status"] == "blocked" for s in summaries),
            "automatic_failed": sum(s["automatic"]["status"] == "failed" for s in summaries),
            "tracking_executed": sum(s["tracking"]["status"] == "executed" for s in summaries),
            "tracking_failed": sum(s["tracking"]["status"] == "failed" for s in summaries),
            "human_reviewed_recordings": 0,
            "accuracy": None,
            "accuracy_status": "not_evaluable",
            "upload_to_result_seconds": None,
            "reason": "Component runs and blocked automatic attempts are not API acceptance.",
            "weights_updated": False,
            "reserved_or_jury_media_used": False,
        },
    )
    links = "".join(
        f'<li><a href="executions/{Path(i["source"]).stem}/review.html">Local case {n + 1}</a></li>'
        for n, i in enumerate(json.loads((root / "inference-inputs.json").read_bytes()))
    )
    (root / "review.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Private mechanic validation</title>'
        "<h1>Private mechanic validation</h1><p>Predictions saved before review. "
        "Supplied labels are separate from independent visual judgments. "
        "No human must research legislation.</p><ul>" + links + "</ul>"
        '<p><a href="aggregate.json">Aggregate execution receipt</a></p>'
    )


def build_review_packet(case, source, registry, table, participants, summary):
    """Human-only full recording with sampled proposal overlays and source JPEGs.

    No interpolation, role hints or legal approval is created. The full frame
    table binds the oriented playback to original PTS; evidence is redecoded.
    """
    import html
    from fractions import Fraction

    import av

    from forte.video import jpeg_bytes, open_video, oriented

    (case / "original.mov").symlink_to(source)
    rows = table["frames"]
    picks = {rows[i]["frame_id"] for i in (0, len(rows) // 2, len(rows) - 1)}
    assets = []
    with open_video(source) as container, av.open(str(case / "source.mp4"), "w") as movie:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        dst = movie.add_stream("libx264", rate=stream.average_rate or 25)
        dst.width, dst.height = rows[0]["oriented_size"]
        dst.pix_fmt = "yuv420p"
        dst.time_base = dst.codec_context.time_base = Fraction(rows[0]["time_base"])
        dst.options = {"crf": "23", "preset": "ultrafast", "tune": "zerolatency"}
        dst.codec_context.max_b_frames = 0
        count = 0
        for ordinal, frame in enumerate(container.decode(stream)):
            row = rows[ordinal]
            if frame.pts != row["source_pts"] or frame.is_corrupt:
                raise ValueError("Review playback source PTS mismatch")
            image = oriented(frame, stream, row["rotation_degrees"])
            if row["frame_id"] in picks:
                raw = jpeg_bytes(image, image.width * image.height)
                target = case / (row["frame_id"] + ".jpg")
                target.write_bytes(raw)
                assets.append({**row, "file": target.name, "sha256": sha256(target)})
            decoded = av.VideoFrame.from_image(image)
            decoded.pts = frame.pts - rows[0]["source_pts"]
            decoded.time_base = frame.time_base
            for packet in dst.encode(decoded):
                movie.mux(packet)
            count += 1
        for packet in dst.encode():
            movie.mux(packet)
    if count != len(rows):
        raise ValueError("Incomplete review playback")
    # Independent full source decode verifies the selected original JPEG bytes.
    checked = 0
    with open_video(source) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        expected = {a["frame_id"]: a for a in assets}
        for ordinal, frame in enumerate(container.decode(stream)):
            fid = f"f{ordinal:06d}"
            if fid in expected:
                a = expected[fid]
                image = oriented(frame, stream, a["rotation_degrees"])
                if (
                    frame.pts != a["source_pts"]
                    or jpeg_bytes(image, image.width * image.height)
                    != (case / a["file"]).read_bytes()
                ):
                    raise ValueError("Review JPEG differs from source re-extraction")
                checked += 1
    save(case / "review-assets.json", assets)
    save(
        case / "human-review-template.json",
        {
            "reviewer": None,
            "reviewed_at": None,
            "prediction_sha256": sha256(case / "tracking/participants.json"),
            "scope": {
                k: {
                    "status": "pending"
                    if k in {"geometry", "identity", "view"}
                    else "not_evaluable_until_predictions_available",
                    "judgments": [],
                }
                for k in ("geometry", "identity", "view", "role", "action", "event", "legal")
            },
            "tracking_metrics": {
                k: None
                for k in (
                    "reviewed_person_instances",
                    "missed_people",
                    "spurious_people",
                    "identity_switches",
                    "fragmentations",
                    "reflections_as_physical_people",
                    "unresolved_continuity",
                )
            },
            "note": "Save actual review as a NEW revision; preserve predictions and template.",
        },
    )
    overlay = [
        {"t": r["timestamp_sec"], "boxes": participants["frame_boxes"][r["frame_id"]]}
        for r in participants["sampled_source_frames"]
    ]
    cards = "".join(
        f"<p>{a['frame_id']} · source PTS {a['source_pts']} · "
        f'{a["timestamp_sec"]:.3f}s<br><img width="400" src="{a["file"]}"></p>'
        for a in assets
    )
    full_link = (
        (
            '<p><a href="automatic/'
            + summary["automatic"]["revision"]
            + '/review.html">Automatic Qwen/event review</a></p>'
        )
        if (summary["automatic"]["status"] == "executed")
        else (
            "<p>Qwen roles/actions, transaction context and event/rule evaluation: "
            "not executed. No predictions or clean negative exist for these stages.</p>"
        )
    )
    page = """<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self';
media-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'">
<title>Local source and participant review</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}
.video{position:relative;width:100%}video,canvas{width:100%}canvas{position:absolute;inset:0;
pointer-events:none}pre{white-space:pre-wrap}a{color:#065f9b}</style>
<h1>Local source and participant review</h1><p>Watch the complete recording first.
Boxes and IDs are unreviewed model proposals, including any reflections. Displayed
boxes come from the nearest detection sample within half the 0.2s cadence; they are
not interpolated. Sparse samples never establish continuous visibility or absence.</p>
<div class="video"><video id="v" controls src="source.mp4"></video><canvas id="c"></canvas></div>
<p id="stamp"></p><p><a href="original.mov">Unchanged original MOV</a> ·
<a href="source-frames.json">All original PTS</a> ·
<a href="tracking/participants.json">Frozen participant proposals</a> ·
<a href="human-review-template.json">Separate review scopes and denominators</a></p>
<h2>Execution and coverage</h2><pre>SUMMARY</pre>FULL
<h2>Uniform source checks (not proposed events)</h2>CARDS
<script>const samples=OVERLAY;const v=document.getElementById('v'),c=document.getElementById('c');
function draw(){c.width=v.videoWidth||1;c.height=v.videoHeight||1;const x=c.getContext('2d');
const r=samples.reduce((a,b)=>Math.abs(b.t-v.currentTime)<Math.abs(a.t-v.currentTime)?b:a);
document.getElementById('stamp').textContent='Playback '+v.currentTime.toFixed(3)+
's; nearest sampled source '+r.t.toFixed(3)+'s';
if(Math.abs(r.t-v.currentTime)<=.101){x.strokeStyle='#ffdf00';x.fillStyle='#ffdf00';
x.lineWidth=2;x.font='18px sans-serif';for(const [id,b] of Object.entries(r.boxes)){
x.strokeRect(b[0]*c.width,b[1]*c.height,(b[2]-b[0])*c.width,(b[3]-b[1])*c.height);
x.fillText(id,b[0]*c.width,Math.max(18,b[1]*c.height));}}requestAnimationFrame(draw);}draw();</script>"""
    (case / "review.html").write_text(
        page.replace("SUMMARY", html.escape(json.dumps(summary, indent=2)))
        .replace("FULL", full_link)
        .replace("CARDS", cards)
        .replace("OVERLAY", json.dumps(overlay).replace("<", "\\u003c"))
    )
    return {
        "source_jpegs_independently_verified": checked,
        "source_frame_table_rows": count,
        "full_playback_frames_encoded": count,
        "playback_sha256": sha256(case / "source.mp4"),
        "packet_sha256": sha256(case / "review.html"),
    }


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--private-root", type=Path, required=True)
    prep.add_argument("--archive", type=Path, required=True)
    prep.add_argument("--extracted", type=Path, required=True)
    prep.add_argument("--reid-manifest", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("execute")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--model-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        execute(args)


if __name__ == "__main__":
    main()
