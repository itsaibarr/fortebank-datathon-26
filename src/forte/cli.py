"""Local setup commands. This module does not run model inference."""

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
    args = parser.parse_args(argv)
    if args.command == "serve":
        import uvicorn

        from forte.api import create_default_app

        uvicorn.run(create_default_app(), host=args.host, port=args.port, workers=1)
        return 0
    try:
        result = audit_archive(args.archive, expected_sha256=args.expected_sha256)
    except (OSError, ValueError, BadZipFile, RuntimeError) as error:
        print(f"dataset-check: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
