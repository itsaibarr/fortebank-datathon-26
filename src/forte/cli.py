"""Application, source-provenance and private development-evaluation commands."""

import argparse
import json
import sys
from pathlib import Path
from zipfile import BadZipFile

from forte.dataset import EXPECTED_ARCHIVE_SHA256, audit_archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forte")
    commands = parser.add_subparsers(dest="command", required=True)
    dataset = commands.add_parser(
        "dataset-check", help="Verify the original archive without extraction"
    )
    dataset.add_argument("--archive", type=Path, required=True)
    dataset.add_argument(
        "--expected-sha256",
        default=EXPECTED_ARCHIVE_SHA256,
        help="Expected fingerprint; override only for explicit synthetic fixtures",
    )
    server = commands.add_parser("serve", help="Run the single-process private video API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    evaluation = commands.add_parser("evaluate", help="Aggregate completed development API results")
    evaluation.add_argument("--manifest", type=Path, required=True)
    evaluation.add_argument("--results", type=Path, required=True)
    scan = commands.add_parser("scan", help="Run actual frozen local timeline/legal inference")
    scan.add_argument("--source", type=Path, required=True)
    scan.add_argument("--config", type=Path, required=True)
    scan.add_argument("--private-output", type=Path, required=True)
    scan.add_argument("--model-url", default="http://127.0.0.1:8001")
    scan.add_argument("--model-name", default="forte-vlm")
    scan.add_argument("--deadline-seconds", type=float, default=270)
    snapshot = commands.add_parser("model-check", help="Verify frozen local model asset hashes")
    snapshot.add_argument("--root", type=Path, required=True)
    legal = commands.add_parser("legal-search", help="Verify and search an offline law release")
    legal.add_argument("--release", type=Path, required=True)
    legal.add_argument("--query", required=True)
    legal.add_argument("--act")
    legal.add_argument("--limit", type=int, default=5)
    annotation = commands.add_parser(
        "annotations-check", help="Validate private visual/legal annotation structure"
    )
    annotation.add_argument("--release", type=Path, required=True)
    annotation.add_argument("--cards", type=Path, required=True)
    annotation.add_argument("--file", type=Path, required=True)
    from forte.tracking_cli import add_commands, run_command

    add_commands(commands)
    args = parser.parse_args(argv)
    if args.command == "model-check":
        from forte.model_profile import verify_snapshot

        try:
            report = verify_snapshot(args.root)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"model-check: verification failed ({type(exc).__name__})", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return 0
    if args.command == "scan":
        from forte.pipeline import analyze_reasoning
        from forte.settings import Settings

        try:
            config = json.loads(args.config.read_text())
            if not 1 <= args.deadline_seconds <= 270:
                raise ValueError("Scan deadline must be within the service budget")
            settings = Settings(
                "unused-local-scan-key",
                args.private_output,
                args.model_url,
                args.model_name,
                job_timeout=args.deadline_seconds,
                model_revision=config["model"]["revision"],
                max_context_tokens=config["model"].get("max_context_tokens", 8192),
                reasoning_config=args.config,
            )
            result = analyze_reasoning(args.source, args.private_output, settings)
        except Exception as exc:
            print(f"scan: local analysis failed ({type(exc).__name__})", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "execution": result["execution"]["status"],
                    "assessment": result["assessment"],
                    "events": len(result["events"]),
                    "weights_frozen": True,
                },
                allow_nan=False,
            )
        )
        return 0
    if args.command.startswith("tracks-"):
        return run_command(args)
    if args.command == "annotations-check":
        from forte.annotations import Annotation, RuleCard, validate_annotation
        from forte.legal import load_release

        try:
            cards = [RuleCard.model_validate(c) for c in json.loads(args.cards.read_text())]
            result = validate_annotation(
                Annotation.model_validate_json(args.file.read_bytes()),
                cards,
                load_release(args.release),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"annotations-check: invalid annotation ({type(exc).__name__})", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "structurally_valid": True,
                    "facts": len(result.facts),
                    "claims": len(result.claims),
                    "independent_semantic_adjudication": False,
                }
            )
        )
        return 0
    if args.command == "legal-search":
        from forte.legal import load_release

        try:
            corpus = load_release(args.release)
            hits = corpus.search(args.query, act_id=args.act, limit=args.limit)
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            print(f"legal-search: invalid release or query ({type(exc).__name__})", file=sys.stderr)
            return 1
        print(json.dumps(hits, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if args.command == "serve":
        import uvicorn

        from forte.api import create_default_app

        uvicorn.run(create_default_app(), host=args.host, port=args.port, workers=1)
        return 0
    if args.command == "evaluate":
        from forte.evaluation import evaluate

        try:
            report = evaluate(json.loads(args.manifest.read_text()), args.results)
        except (OSError, ValueError, KeyError) as exc:
            print(f"evaluate: invalid or incomplete run ({type(exc).__name__})", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0
    try:
        result = audit_archive(args.archive, expected_sha256=args.expected_sha256)
    except (OSError, ValueError, BadZipFile, RuntimeError) as error:
        print(f"dataset-check: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
