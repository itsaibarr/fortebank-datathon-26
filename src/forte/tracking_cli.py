"""Local-only tracking preparation/review commands; stdout contains aggregates."""

import json
import os
import shutil
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from forte.annotations import Annotation
from forte.person_proposals import (
    LocalByteTrack,
    YoloxONNX,
    allowlisted_sources,
    prepare_clip,
    sha256,
    verify_manifest_source,
    verify_source,
    write_json,
)
from forte.track_review import apply_corrections, import_cvat
from forte.tracking import Correction, TrackManifest, training_targets, validate_pair


def add_commands(commands):
    packet = commands.add_parser("tracks-packet", help="Refresh local private review navigation")
    packet.add_argument("--directory", type=Path, required=True)
    index = commands.add_parser("tracks-index", help="Refresh private review status and aggregates")
    index.add_argument("--private-root", type=Path, required=True)
    index.add_argument("--directory", type=Path, required=True)
    index.add_argument("--revision", action="append", default=[], metavar="CLIP=PRIVATE_DIRECTORY")
    prepare = commands.add_parser("tracks-prepare", help="Create private local person proposals")
    prepare.add_argument("--private-root", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--weights", type=Path, required=True)
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--clip")
    prepare.add_argument("--pilot-only", action="store_true")
    prepare.add_argument("--resume", action="store_true")
    prepare.add_argument("--cadence-sec", type=float, default=0.2)
    for command in ("tracks-check", "tracks-review", "tracks-import-cvat", "tracks-export-targets"):
        parser = commands.add_parser(command, help="Private source-bound review operation")
        parser.add_argument("--directory", type=Path, required=True)
        parser.add_argument("--source", type=Path, required=True)
        if command in {"tracks-review", "tracks-import-cvat"}:
            parser.add_argument("--output", type=Path, required=True)
            parser.add_argument("--reviewer", required=True)
            parser.add_argument("--reason", required=True)
        if command == "tracks-review":
            parser.add_argument("--operations", type=Path, required=True)
        if command == "tracks-import-cvat":
            parser.add_argument("--xml", type=Path, required=True)
        if command == "tracks-export-targets":
            parser.add_argument("--output", type=Path, required=True)


def private_output(path):
    if any((ancestor / ".git").exists() for ancestor in [path.resolve(), *path.resolve().parents]):
        raise ValueError("Private output must be outside a Git checkout")
    os.umask(0o077)


def load_pair(directory, source):
    m = TrackManifest.model_validate_json((directory / "tracks.json").read_bytes())
    if sha256(source) != m.source_sha256:
        raise ValueError("Source hash mismatch")
    path = directory / m.annotation_file
    if path.resolve().parent != directory.resolve() or sha256(path) != m.annotation_sha256:
        raise ValueError("Annotation hash/path mismatch")
    a = Annotation.model_validate_json(path.read_bytes())
    verify_manifest_source(m, source)
    return validate_pair(m, a)


def aggregate(records, annotations=None):
    manifests = [m for _, m in records]
    annotations = annotations or []
    facts = [f for a in annotations for f in a.facts]
    return dict(
        recordings_processed=len(manifests),
        proposed_segments=sum(len(m.segments) for m in manifests),
        proposed_joins=sum(len(m.joins) for m in manifests),
        human_reviewed_segments=sum(
            s.review.status == "confirmed" for m in manifests for s in m.segments
        ),
        confirmed_roles=sum(f.kind == "role" and f.review_status == "confirmed" for f in facts),
        confirmed_actions=sum(f.kind == "action" and f.review_status == "confirmed" for f in facts),
        pending_roles=sum(f.kind == "role" and f.review_status == "draft" for f in facts),
        pending_actions=sum(f.kind == "action" and f.review_status == "draft" for f in facts),
        confirmed_abstentions=sum(
            f.target_kind == "abstention" and f.review_status == "confirmed" for f in facts
        ),
        people_reviewed=None,
        human_unreviewed_sec=sum(m.duration_sec for m in manifests),
        training_targets=0,
        source_frames=sum(len(m.frames) for m in manifests),
        detection_frames=sum(len(m.detection_frame_ids) for m in manifests),
        duration_sec=sum(m.duration_sec for m in manifests),
        runtime_sec=sum(m.provenance.get("runtime_sec", 0) for m in manifests),
        regression_recordings=sum(m.regression_only for m in manifests),
        undecodable_ranges=sum(len(m.provenance.get("undecodable_ranges", [])) for m in manifests),
        human_reviewed_recordings=0,
        observed_id_switches=None,
        observed_fragments=None,
        human_corrected_errors=0,
        compute_spend_usd=0,
        quality_gate="pending_local_human_review",
        split_frozen=False,
        note="Segments/joins are proposals; distinct people and tracking quality are unmeasured",
    )


def refresh_index(args):
    directory = args.directory.resolve()
    private_output(directory)
    eligible = {
        r["clip_id"]: r
        for r in allowlisted_sources(
            args.private_root / "batch-selection.json",
            args.private_root / "annotation-review/sources",
        )
    }
    old = json.loads((directory / "index.json").read_bytes())
    revisions = dict(value.split("=", 1) for value in args.revision)
    if not set(revisions) <= {r["clip_id"] for r in old["records"]}:
        raise ValueError("Revision must refer to an existing allowlisted record")
    records, annotations, rows = [], [], []
    for row in old["records"]:
        clip = row["clip_id"]
        record = eligible[clip]
        path = (
            Path(revisions[clip]) if clip in revisions else (directory / row["manifest"]).parent
        ).resolve()
        if not path.is_relative_to(args.private_root.resolve()):
            raise ValueError("Review revision escaped private root")
        m, a = load_pair(path, record["source"])
        if m.clip_id != clip or m.source_sha256 != record["recording_group"]:
            raise ValueError("Index/source binding mismatch")
        records.append((record, m))
        annotations.append(a)
        statuses = [s.review.status for s in m.segments] + [f.review_status for f in a.facts]
        row.update(
            manifest=str(path / "tracks.json"),
            status="confirmed"
            if statuses and all(x == "confirmed" for x in statuses)
            else "pending",
            confirmed=sum(x == "confirmed" for x in statuses),
            pending=sum(x == "draft" for x in statuses),
            rejected=sum(x == "rejected" for x in statuses),
            training_eligible=bool(training_targets(m, a)),
            excluded=m.exclusion_reasons,
        )
        rows.append(row)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    shutil.copyfile(directory / "index.json", directory / f"index-before-{stamp}.json")
    old["records"] = rows
    write_json(directory / "index.json", old)
    report = aggregate(records, annotations)
    report["training_targets"] = sum(
        len(training_targets(m, a)) for (_, m), a in zip(records, annotations, strict=True)
    )
    write_json(directory / "aggregate.json", report)
    from forte.review_packet import write_overview

    write_overview(directory)
    print(json.dumps(report))
    return 0


def review_receipts(review_path, reference):
    current = sha256(review_path)
    return dict(
        current_review_sha256=current,
        original_reference_review_sha256=reference["review_file_sha256"],
        reference_review_hash_matches_current=reference["review_file_sha256"] == current,
        binding_review_status="pending",
    )


def prepare_run(args):
    root = args.private_root.resolve()
    output = args.output.resolve()
    private_output(output)
    if not output.is_relative_to(root) or output == root:
        raise ValueError("Use a new versioned directory inside private root")
    records = allowlisted_sources(root / "batch-selection.json", root / "annotation-review/sources")
    if args.clip and args.clip not in {r["clip_id"] for r in records}:
        raise ValueError("Clip absent from development allowlist")
    index_path = root / "annotation-review/two-layer-review/index.json"
    old = json.loads(index_path.read_bytes())
    templates = {x["clip_id"]: x for x in old["records"]}
    review_path = root / "annotation-review/first-milestone-review.json"
    reference_path = root / "role-comparison-20261017/reference.json"
    reviews = json.loads(review_path.read_bytes())
    reference = json.loads(reference_path.read_bytes())
    by_source = {Path(r["source"]).resolve(): r["clip_id"] for r in records}
    pilot = [by_source[Path(x["source_path"]).resolve()] for x in reviews["items"]]
    if len(set(pilot)) != 3:
        raise ValueError("Three-case review must bind to three allowlisted recordings")
    regression = reference["recording_sha256"]
    # A stale narrative receipt must not approve a binding. Preserve both
    # versions/receipts and surface it; verified allowlisted media can still
    # receive geometry proposals without promoting the narrative to truth.
    receipts = review_receipts(review_path, reference)
    if args.clip:
        records = [r for r in records if r["clip_id"] == args.clip]
    elif args.pilot_only:
        records = [r for r in records if r["clip_id"] in pilot]
    records.sort(key=lambda r: (r["clip_id"] not in pilot, r["clip_id"]))
    for r in records:
        verify_source(r)
        t = templates[r["clip_id"]]
        if (
            t["recording_sha256"] != r["recording_group"]
            or Path(t["source"]).resolve() != r["source"].resolve()
        ):
            raise ValueError("Template index source mismatch")
    config = json.loads(args.config.read_bytes())
    detector = YoloxONNX(args.weights, config)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = output / "original-review-backups"
    backup.mkdir(exist_ok=True, mode=0o700)
    write_json(output / "review-receipts.json", receipts)
    for name, path in [
        ("first-milestone-review.json", review_path),
        ("role-reference.json", reference_path),
        ("two-layer-index.json", index_path),
    ]:
        target = backup / name
        if target.exists() and sha256(target) != sha256(path):
            raise ValueError("Preserved review changed; use a new run")
        if not target.exists():
            shutil.copyfile(path, target)
    result = []
    failures = []
    for record in records:
        dest = output / record["clip_id"]
        try:
            if args.resume and (dest / "complete.json").exists():
                m, _ = load_pair(dest, record["source"])
                complete = json.loads((dest / "complete.json").read_bytes())
                if (
                    sha256(dest / "tracks.json") != complete["manifest_sha256"]
                    or m.provenance["detector"] != config
                    or m.cadence_sec != args.cadence_sec
                ):
                    raise ValueError("Resume provenance changed")
            else:
                if args.resume and dest.exists():
                    failed = output / "failed-attempts"
                    failed.mkdir(exist_ok=True, mode=0o700)
                    shutil.move(
                        dest,
                        failed
                        / (record["clip_id"] + "-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")),
                    )
                extra = []
                if record["recording_group"] == regression:
                    extra = [f["frame_id"] for v in reference["variants"] for f in v["frames"]]
                template = index_path.parent / templates[record["clip_id"]]["annotation"]
                m = prepare_clip(
                    record,
                    template,
                    dest,
                    detector,
                    LocalByteTrack(args.cadence_sec),
                    cadence_sec=args.cadence_sec,
                    regression_only=record["recording_group"] == regression,
                    extra_frame_ids=extra,
                )
                if record["clip_id"] in pilot:
                    review = next(
                        x
                        for x in reviews["items"]
                        if Path(x["source_path"]).resolve() == record["source"].resolve()
                    )
                    # Original certainty and words are preserved, not converted
                    # to track facts or automatically assigned to a moving box.
                    write_json(dest / "legacy-review.json", review)
                    pending = dict(
                        status="pending_local_human_binding",
                        legacy_review_sha256=sha256(dest / "legacy-review.json"),
                        original_review_sha256=sha256(review_path),
                        track_candidates=[
                            dict(
                                segment_id=s.id,
                                person_id=s.person_id,
                                first_frame=s.boxes[0].frame_id,
                                last_frame=s.boxes[-1].frame_id,
                            )
                            for s in m.segments
                        ],
                        question="Which outlined segment matches the preserved correction? "
                        "Check service context before/during/after. "
                        "Departure alone cannot establish role.",
                        actual_reviewer=None,
                        confirmed_segment_ids=[],
                        review_receipts=receipts,
                    )
                    if m.regression_only:
                        pending["preserved_role_reference"] = reference
                        # Verify source associations independently of agreeing words.
                        frame_map = {f.frame_id: f for f in m.frames}
                        for variant in reference["variants"]:
                            for f in variant["frames"]:
                                actual = frame_map[f["frame_id"]]
                                if (
                                    actual.source_pts != f["source_pts"]
                                    or abs(actual.timestamp_sec - f["timestamp_sec"]) > 1e-6
                                ):
                                    raise ValueError("Regression source frame mismatch")
                    write_json(dest / "correction-binding-pending.json", pending)
                    intervals = []
                    for event in review.get("model_result", {}).get("events", []):
                        timestamp = event["timecode_sec"]
                        start, end = max(0, timestamp - 8), min(m.duration_sec, timestamp + 8)
                        intervals.append(
                            dict(
                                start_sec=start,
                                end_sec=end,
                                playback=f"review.mp4#t={start:.3f},{end:.3f}",
                                source_frame_ids=[
                                    f.frame_id for f in m.frames if start <= f.timestamp_sec <= end
                                ],
                                purpose="Context review only; reported event is unverified",
                            )
                        )
                    write_json(dest / "review-intervals.json", intervals)
            result.append((record, m))
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            detail = dict(
                clip_id=record["clip_id"],
                error_type=type(exc).__name__,
                trace=[
                    dict(file=Path(f.filename).name, line=f.lineno)
                    for f in traceback.extract_tb(exc.__traceback__)
                ],
            )
            if hasattr(exc, "errors"):
                detail["validation"] = [
                    dict(location=e["loc"], type=e["type"], message=e["msg"])
                    for e in exc.errors(include_input=False)
                ]
            else:
                detail["message"] = str(exc)
            write_json(dest / "failure-detail.json", detail)
            failures.append(dict(clip_id=record["clip_id"], error_type=type(exc).__name__))
        write_json(
            output / "index.json",
            dict(
                schema_version=1,
                records=[
                    dict(
                        clip_id=r["clip_id"],
                        recording_sha256=m.source_sha256,
                        manifest=f"{r['clip_id']}/tracks.json",
                        status="pending",
                        confirmed=0,
                        rejected=0,
                        training_eligible=False,
                        excluded=m.exclusion_reasons,
                        regression_only=m.regression_only,
                        pilot=r["clip_id"] in pilot,
                    )
                    for r, m in result
                ],
                failures=failures,
                holdout_recordings_included=0,
                jury_recordings_included=0,
                original_reviews_preserved=True,
            ),
        )
        write_json(output / "aggregate.json", aggregate(result))
        print(json.dumps(dict(completed=len(result), failed=len(failures))), flush=True)
    if failures:
        return 1
    from forte.review_packet import write_overview

    write_overview(output)
    return 0


def run_command(args):
    try:
        if args.command == "tracks-packet":
            private_output(args.directory)
            from forte.review_packet import write_overview

            write_overview(args.directory)
            print(json.dumps(dict(private_review_packet_refreshed=True)))
            return 0
        if args.command == "tracks-prepare":
            return prepare_run(args)
        if args.command == "tracks-index":
            return refresh_index(args)
        m, a = load_pair(args.directory, args.source)
        if args.command == "tracks-check":
            print(
                json.dumps(
                    dict(
                        structurally_valid=True,
                        segments=len(m.segments),
                        facts=len(a.facts),
                        training_targets=len(training_targets(m, a)),
                        independent_semantic_adjudication=False,
                    )
                )
            )
            return 0
        private_output(args.output)
        if args.command == "tracks-export-targets":
            targets = training_targets(m, a)
            if not targets:
                raise ValueError("No independently reviewed eligible training targets")
            if args.output.exists():
                raise FileExistsError("Export exists")
            write_json(
                args.output,
                dict(
                    schema_version=1,
                    source_sha256=m.source_sha256,
                    manifest_sha256=sha256(args.directory / "tracks.json"),
                    annotation_sha256=m.annotation_sha256,
                    facts=[f.model_dump(mode="json") for f in targets],
                    frames=[f.model_dump() for f in m.frames],
                    segments=[s.model_dump(mode="json") for s in m.segments],
                    work_areas=[area.model_dump(mode="json") for area in m.work_areas],
                ),
            )
            print(json.dumps(dict(exported_targets=len(targets))))
            return 0
        if args.output.exists():
            raise FileExistsError("Use a new immutable review revision directory")
        if args.command == "tracks-review":
            operations = json.loads(args.operations.read_bytes())
            revised, annotation = apply_corrections(
                m,
                a,
                operations,
                reviewer=args.reviewer,
                reason=args.reason,
                artifact="review-operations.json",
            )
        else:
            revised = import_cvat(m, args.xml, args.directory / "cvat-source-map.json")
            annotation = a
            revised.corrections.append(
                Correction(
                    operation="cvat_import",
                    reviewer=args.reviewer,
                    reviewed_at=datetime.now(UTC),
                    before_sha256=sha256(args.directory / "tracks.json"),
                    affected_ids=[s.id for s in revised.segments],
                    reason=args.reason,
                    artifact="cvat-edits.xml",
                )
            )
            validate_pair(revised, annotation)
        shutil.copytree(args.directory, args.output)
        if args.command == "tracks-review":
            shutil.copyfile(args.operations, args.output / "review-operations.json")
        else:
            shutil.copyfile(args.xml, args.output / "cvat-edits.xml")
        shutil.copyfile(args.directory / "tracks.json", args.output / "tracks-before.json")
        shutil.copyfile(
            args.directory / "annotation.json", args.output / "annotation-before-revision.json"
        )
        write_json(args.output / "annotation.json", annotation.model_dump(mode="json"))
        revised.annotation_sha256 = sha256(args.output / "annotation.json")
        # Rebuild derivatives so review geometry/IDs do not lag the revision.
        from forte.person_proposals import build_packet

        shutil.rmtree(args.output / "frames")
        build_packet(args.source, args.output, revised)
        revised.provenance["review_media"] = {
            name: sha256(args.output / name)
            for name in (
                "review.mp4",
                "oriented-source.mp4",
                "review-assets.json",
                "cvat.xml",
                "cvat-source-map.json",
            )
        }
        write_json(args.output / "tracks.json", revised.model_dump(mode="json"))
        write_json(
            args.output / "complete.json",
            dict(
                source_sha256=revised.source_sha256,
                manifest_sha256=sha256(args.output / "tracks.json"),
                revision=True,
            ),
        )
        write_json(
            args.output / "revision.json",
            dict(
                parent=str(args.directory),
                parent_manifest_sha256=sha256(args.directory / "tracks.json"),
                manifest_sha256=sha256(args.output / "tracks.json"),
            ),
        )
        print(json.dumps(dict(revision_created=True, training_eligible=False)))
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        ImportError,
        StopIteration,
    ) as exc:
        print(
            f"tracks: operation failed ({type(exc).__name__}); inspect private inputs locally",
            file=sys.stderr,
        )
        return 1
