#!/usr/bin/env python3
"""Convert the canonical core handoff into an UNAPPROVED installation candidate.

This does not fabricate resource inventories, operating requirements, successful
verification or browser ownership. Review and local acceptance remain required.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path


def convert(source, core_commit, inventory=None, effective_config=None):
    raw = Path(source).read_bytes()
    canonical = json.loads(raw)
    if canonical.get("schema_version") != "forte.integration/1":
        raise ValueError("Expected canonical forte.integration/1 handoff")
    if not re.fullmatch(r"[0-9a-f]{40}", core_commit):
        raise ValueError("Select the full verified stable core commit")
    model = canonical["model"]
    if model.get("adapters") or model.get("quantization") is not None:
        raise ValueError("This frozen BF16 profile does not accept changed model weights")
    image = (
        canonical["container"].get("registry_digest") or canonical["container"]["local_image_id"]
    )
    assets = json.loads(Path(inventory).read_text()) if inventory else []
    if isinstance(assets, dict):
        if assets.get("schema_version") != "forte.public-assets/1":
            raise ValueError("Unsupported public resource inventory schema")
        mapped = []
        for item in assets.get("files", []):
            destination = item.get("container_path", "")
            if destination.startswith(("/models/", "/legal/")):
                path = destination.lstrip("/")
            elif item.get("root") == "repository":
                path = "repository/" + item["relative_path"]
            else:
                raise ValueError("Resource has no supported explicit container mapping")
            if ".." in Path(path).parts or not re.fullmatch(
                r"[0-9a-f]{64}", item.get("sha256", "")
            ):
                raise ValueError("Invalid resource path or hash")
            mapped.append(
                {"path": path, "sha256": item["sha256"], "size_bytes": item.get("size_bytes")}
            )
        assets = mapped
    if not isinstance(assets, list):
        raise ValueError("Resource inventory must be a list or canonical public inventory")
    if effective_config:
        config_hash = hashlib.sha256(Path(effective_config).read_bytes()).hexdigest()
        if config_hash != canonical["configuration"]["verified_effective_config_sha256"]:
            raise ValueError("Effective configuration differs from the canonical core receipt")
        assets.append({"path": "config/frozen-inference.json", "sha256": config_hash})
    model_path = canonical.get("serving_environment", {}).get(
        "FORTE_MODEL_PATH", "/models/" + model["revision"]
    )

    return {
        "schema_version": 1,
        "core": {
            "commit": core_commit,
            "image": image,
            "contract_sha256": canonical["implementation"]["v2_contract_sha256"],
        },
        "model": {
            "identity": model["checkpoint"],
            "revision": model["revision"],
            "profile": "frozen27b",
            "frozen": True,
        },
        "corpus": {
            "version": "2026-10-17",
            "manifest_sha256": canonical["configuration"]["legal_manifest_sha256"],
        },
        "runtime": {
            "ipc": canonical["container"]["ipc"],
            "environment": {
                "FORTE_MODEL_PATH": model_path,
                "FORTE_MODEL_PROFILE": "frozen27b",
                "FORTE_REASONING_CONFIG": "/resources/config/frozen-inference.json",
            },
            "mounts": [
                {"source": "models", "target": "/models"},
                {"source": "legal", "target": "/legal"},
            ],
            "requirements": {
                "min_host_ram_gib": None,
                "min_free_disk_gib": None,
                "driver_major": None,
            },
        },
        "assets": assets,
        "verification": {
            "release": False,
            "model_workload": False,
            "offline_analysis": False,
            "browser_session": False,
            "ownership": False,
            "receipt": "verification/acceptance.json",
        },
        "provenance": {
            "source_schema": canonical["schema_version"],
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_release": canonical["release"],
            "canonical_verification": canonical["verification"],
            "canonical_security_boundary": canonical["security_and_product"],
            "derived_status": (
                "Unapproved installation candidate; no verification is promoted automatically."
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--core-commit", required=True)
    parser.add_argument("--inventory", help="Reviewed public resource path/SHA256 list")
    parser.add_argument(
        "--effective-config", help="Exact public effective configuration from the core handoff"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = convert(args.source, args.core_commit, args.inventory, args.effective_config)
        output = Path(args.output)
        if output.exists():
            raise ValueError("Output already exists; choose a new versioned candidate")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps({"candidate_created": True, "approved": False}))
    except (OSError, KeyError, ValueError, TypeError):
        print(
            json.dumps(
                {
                    "error": (
                        "Invalid handoff or unavailable destination; no verification was approved."
                    )
                }
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
