"""Independent private experiment commands; no production API or allocator."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from forte_visual.benchmark import CANDIDATES, POLICY, MockExecutor, run_model, score, select
from forte_visual.evaluation import scan_metrics, track_metrics
from forte_visual.gates import data_gate, resource
from forte_visual.inputs import export, validate_pack
from forte_visual.io import canonical, digest, local, private_dir, read, write
from forte_visual.release import snapshot, verify
from forte_visual.scan import scan
from forte_visual.synthetic import create
from forte_visual.training import tiny_check


def add(parser, *names):
    for name in names:
        parser.add_argument("--" + name, type=Path, required=True)


def worker(job):
    from forte_visual.runtime import VLLMExecutor, train_offline

    if job["kind"] == "inference":
        executor = VLLMExecutor(
            Path(job["model_path"]),
            job["model"],
            Path(job["adapter_path"]) if job.get("adapter_path") else None,
        )
        run_model(
            Path(job["inputs"]), Path(job["output"]), job["model"], executor, seconds=job["seconds"]
        )
    else:
        train_offline(
            Path(job["model_path"]),
            job["model"],
            Path(job["inputs"]),
            Path(job["references"]),
            Path(job["output"]),
            max_updates=job["updates"],
            dataset_provenance=job["dataset_provenance"],
        )


def isolated_worker(job, output, python, seconds):
    path = output / "worker-job.json"
    write(path, job)
    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "WANDB_DISABLED": "true",
        "DO_NOT_TRACK": "1",
    }
    with (output / "worker.log").open("x") as stream:
        process = subprocess.Popen(
            [str(python), "-m", "forte_visual.cli", "_worker", "--job", str(path)],
            env=env,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
        try:
            if process.wait(timeout=seconds) != 0:
                raise subprocess.CalledProcessError(process.returncode, process.args)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Only this newly created session, including its vLLM workers. Never
            # touch another workstream's resident model or resource lifecycle.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            write(output / "failure.json", {"status": "incomplete_worker", "quality_result": None})
            raise ValueError(
                "Local worker failed/timed out; inspect private failure artifact"
            ) from None


def compare(args):
    release, _, receipt = verify(args.release)
    reasons = data_gate(args.release, args.pilot, args.inputs)
    validate_pack(args.release, args.inputs, args.references)
    private_dir(args.output)
    write(args.output / "policy.json", POLICY)
    write(
        args.output / "preflight.json",
        {"gates": reasons, "release": receipt, "dry_run": args.dry_run, "mock": args.mock},
    )
    if args.dry_run:
        return {"status": "dry_run", "pending_gates": len(reasons), "paid_resources_created": 0}
    if args.mock and not release.synthetic:
        raise ValueError("Mock execution accepts synthetic release only")
    if not args.mock and reasons:
        raise ValueError("Reviewed-data gate closed; see private preflight")
    for model in ("8b", "27b"):
        destination = args.output / model
        private_dir(destination)
        prediction = destination / "predictions.json"
        if args.mock:
            run_model(args.inputs, prediction, model, MockExecutor(), seconds=args.seconds)
        else:
            if args.models is None or args.runtime_python is None:
                raise ValueError("Explicit offline model inventory and runtime Python required")
            with resource(args.resource, seconds=args.seconds):
                isolated_worker(
                    {
                        "kind": "inference",
                        "model": model,
                        "model_path": read(args.models)[model],
                        "inputs": str(args.inputs.resolve()),
                        "output": str(prediction.resolve()),
                        "seconds": args.seconds,
                    },
                    destination,
                    args.runtime_python,
                    args.seconds,
                )
    scores = {}
    if args.references:
        for model in ("8b", "27b"):
            scores[model] = score(
                args.inputs, args.references, args.output / model / "predictions.json"
            )
            write(args.output / model / "metrics.json", scores[model])
    outcome = (
        select(scores["8b"], scores["27b"], synthetic=release.synthetic or args.mock)
        if scores
        else "inconclusive"
    )
    report = {
        "outcome": outcome,
        "input_sha256": digest(args.inputs),
        "release": receipt,
        "policy": POLICY,
        "mock": args.mock,
        "scores": scores,
        "candidate_generations_differ": True,
        "paid_resources_created": 0,
    }
    write(args.output / "comparison.json", report)
    return {"outcome": outcome, "mock": args.mock, "cases_scored": bool(scores)}


def train(args):
    if args.synthetic_check:
        return tiny_check(args.output)
    if not 1 <= args.updates <= 30:
        raise ValueError("Initial SFT bound is one pass / 30 updates")
    if not args.release or not args.inputs:
        raise ValueError("Training requires explicit release and frozen input pack")
    reasons = data_gate(args.release, args.pilot, args.inputs, training=True)
    if args.references:
        validate_pack(args.release, args.inputs, args.references, training=True)
    selection = read(args.selection) if args.selection else {}
    chosen = selection.get("outcome")
    if chosen not in {"8b", "27b"} or selection.get("mock"):
        reasons.append("No reviewed paired candidate selection")
    if args.pilot and args.selection:
        if read(args.pilot).get("selection_sha256") != digest(args.selection):
            reasons.append("Training pilot does not bind selected comparison")
    private_dir(args.output)
    write(
        args.output / "preflight.json",
        {"gates": reasons, "selected": chosen, "dry_run": args.dry_run},
    )
    if args.dry_run:
        return {"status": "dry_run", "pending_gates": len(reasons), "paid_resources_created": 0}
    if reasons:
        raise ValueError("Training data/selection gate closed; see private preflight")
    if args.updates > 1:
        compat = read(args.compatibility) if args.compatibility else {}
        if (
            not compat.get("multimodal_step_passed")
            or not compat.get("freeze_boundary_verified")
            or compat.get("candidate", {}).get("revision") != CANDIDATES[chosen]["revision"]
            or compat.get("input_sha256") != digest(args.inputs)
            or compat.get("runtime_code_sha256") != digest(Path(__file__).with_name("runtime.py"))
        ):
            raise ValueError(
                "Selected model exact SFT compatibility and one-step memory probe pending"
            )
    if not args.models or not args.references or not args.runtime_python:
        raise ValueError("Explicit offline models, references and runtime Python required")
    with resource(args.resource, seconds=args.seconds):
        _, pairs, receipt = verify(args.release)
        isolated_worker(
            {
                "kind": "training",
                "model": chosen,
                "model_path": read(args.models)[chosen],
                "inputs": str(args.inputs.resolve()),
                "references": str(args.references.resolve()),
                "output": str(args.output.resolve()),
                "updates": args.updates,
                "dataset_provenance": {
                    "release_sha256": receipt["release_sha256"],
                    "producer_code_commit": receipt["producer_code_commit"],
                    "selection_sha256": digest(args.selection),
                    "pilot_sha256": digest(args.pilot),
                    "split_sha256": canonical(
                        [
                            [m.source_sha256, m.session_group, m.split, m.split_frozen]
                            for _, m, _ in pairs
                        ]
                    ),
                },
            },
            args.output,
            args.runtime_python,
            args.seconds,
        )
    return {"status": "bounded_training_finished", "quality_result": "pending"}


def evaluate_adapter(args):
    reasons = data_gate(args.release, args.pilot, args.inputs)
    validate_pack(args.release, args.inputs, args.references)
    selection = read(args.selection)
    chosen = selection.get("outcome")
    if chosen not in {"8b", "27b"} or selection.get("mock"):
        reasons.append("Paired real model selection pending")
    private_dir(args.output)
    write(args.output / "preflight.json", {"gates": reasons, "dry_run": args.dry_run})
    if args.dry_run:
        return {"status": "dry_run", "pending_gates": len(reasons)}
    if reasons or not args.models or not args.runtime_python:
        raise ValueError("Adapter evaluation data/model/runtime gate closed")
    scores = {}
    for variant in ("base", "adapter"):
        destination = private_dir(args.output / variant)
        prediction = destination / "predictions.json"
        with resource(args.resource, seconds=args.seconds):
            isolated_worker(
                {
                    "kind": "inference",
                    "model": chosen,
                    "model_path": read(args.models)[chosen],
                    "adapter_path": str(args.adapter.resolve()) if variant == "adapter" else None,
                    "inputs": str(args.inputs.resolve()),
                    "output": str(prediction.resolve()),
                    "seconds": args.seconds,
                },
                destination,
                args.runtime_python,
                args.seconds,
            )
        scores[variant] = score(args.inputs, args.references, prediction)
        write(destination / "metrics.json", scores[variant])
    write(
        args.output / "adaptation.json",
        {
            "input_sha256": digest(args.inputs),
            "selected": chosen,
            "scores": scores,
            "promotion": "requires reviewed actor/action and complete-scan runtime gate",
        },
    )
    return {"status": "base_adapter_scored", "promoted": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("release-check")
    add(p, "release")
    p.add_argument("--snapshot", type=Path)
    p = commands.add_parser("synthetic")
    add(p, "output")
    p = commands.add_parser("export")
    add(p, "release", "output")
    p.add_argument("--training", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p = commands.add_parser("compare")
    add(p, "release", "inputs", "output")
    p.add_argument("--references", type=Path)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = commands.add_parser("train")
    add(p, "output")
    for name in ("release", "inputs", "references", "selection", "compatibility"):
        p.add_argument("--" + name, type=Path)
    p.add_argument("--synthetic-check", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--updates", type=int, default=1)
    p = commands.add_parser("evaluate-adapter")
    add(p, "release", "inputs", "references", "selection", "adapter", "output")
    p.add_argument("--dry-run", action="store_true")
    for name in ("compare", "train", "evaluate-adapter"):
        p = commands.choices[name]
        for flag in ("pilot", "resource", "models", "runtime-python"):
            p.add_argument("--" + flag, type=Path)
        p.add_argument("--seconds", type=float, default=270)
    p = commands.add_parser("scan")
    add(p, "release", "output")
    p.add_argument("--clip", required=True)
    p.add_argument("--mock", action="store_true", required=True)
    p = commands.add_parser("evaluate")
    add(p, "inputs", "references", "predictions", "output")
    p = commands.add_parser("evaluate-tracks")
    add(p, "oracle", "automatic", "output")
    p = commands.add_parser("evaluate-scan")
    add(p, "release", "timeline", "output")
    p = commands.add_parser("_worker", help=argparse.SUPPRESS)
    add(p, "job")
    args = parser.parse_args(argv)
    try:
        if args.command == "release-check":
            result = (
                snapshot(args.release, args.snapshot) if args.snapshot else verify(args.release)[2]
            )
        elif args.command == "synthetic":
            create(args.output)
            result = {"status": "synthetic_fixture_created"}
        elif args.command == "export":
            result = {
                "cases": export(args.release, args.output, training=args.training, seed=args.seed)
            }
        elif args.command == "compare":
            result = compare(args)
        elif args.command == "train":
            result = train(args)
        elif args.command == "evaluate-adapter":
            result = evaluate_adapter(args)
        elif args.command == "evaluate":
            result = score(args.inputs, args.references, args.predictions)
            write(args.output, result)
            result = {"status": "scored", "groups": len(result["groups"])}
        elif args.command == "evaluate-tracks":
            from forte.tracking import TrackManifest

            result = track_metrics(
                TrackManifest.model_validate(read(args.oracle)),
                TrackManifest.model_validate(read(args.automatic)),
            )
            write(args.output, result)
            result = {
                "status": "tracking_scored",
                "reviewed_boxes": result["reviewed_visible_boxes"],
            }
        elif args.command == "evaluate-scan":
            report = read(args.timeline)
            _, pairs, _ = verify(args.release)
            _, m, a = next(p for p in pairs if p[1].clip_id == report["clip_id"])
            write(args.output, scan_metrics(m, a, report))
            result = {"status": "scan_scored"}
        elif args.command == "scan":
            upload_started = time.monotonic()
            release, pairs, _ = verify(args.release)
            if not release.synthetic:
                raise ValueError(
                    "CLI mock scan requires synthetic inputs; "
                    "inject controlled executor for private use"
                )
            clip, m, _ = next(p for p in pairs if p[1].clip_id == args.clip)
            report = scan(
                m,
                local(args.release.parent, clip.media),
                args.output,
                upload_started=upload_started,
            )
            result = {"status": report["status"], "calls": report["calls"]}
        else:
            worker(read(args.job))
            result = {"status": "worker_finished"}
        print(json.dumps(result, default=str))
        return 0
    except (ValueError, OSError, KeyError, StopIteration):
        # No raw validation exception: it can contain private facts or filenames.
        print(
            json.dumps(
                {
                    "status": "blocked_or_failed",
                    "command": args.command,
                    "detail": "Inspect private preflight/receipts; no scene content logged",
                }
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
