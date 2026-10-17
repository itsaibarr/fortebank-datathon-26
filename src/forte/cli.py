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
    legal = commands.add_parser("legal-search", help="Verify and search an offline law release")
    legal.add_argument("--release", type=Path, required=True)
    legal.add_argument("--query", required=True)
    legal.add_argument("--act")
    legal.add_argument("--limit", type=int, default=5)
    legal.add_argument("--dense-index", type=Path)
    legal.add_argument("--embedding-model", type=Path)
    legal.add_argument("--embedding-device", default="cpu", choices=["cpu", "cuda"])
    annotation = commands.add_parser(
        "annotations-check", help="Validate private visual/legal annotation structure"
    )
    annotation.add_argument("--release", type=Path, required=True)
    annotation.add_argument("--cards", type=Path, required=True)
    annotation.add_argument("--file", type=Path, required=True)
    args = parser.parse_args(argv)
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
            if bool(args.dense_index) != bool(args.embedding_model):
                raise ValueError("Dense retrieval requires both local index and model")
            corpus = load_release(args.release)
            if args.dense_index:
                from forte.retrieval import DenseIndex, LocalBGE, hybrid_search

                index = DenseIndex.model_validate_json(args.dense_index.read_bytes())
                encoder = LocalBGE(args.embedding_model, args.embedding_device)
                hits = hybrid_search(
                    corpus,
                    index,
                    args.query,
                    encoder.encode([args.query])[0],
                    act_id=args.act,
                    limit=args.limit,
                )
            else:
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
