"""Verify published examples against the real API using generated fixtures only.

This is a documentation check, not a production server or model-quality benchmark.
All temporary credentials, media and cases stay outside the checkout.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]


def main():
    site = ROOT / "docs-site"
    config = json.loads((site / "docs.json").read_text())
    pages = []

    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "pages":
                    pages.extend(item for item in child if isinstance(item, str))
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(config["navigation"])
    all_pages = {str(path.relative_to(site).with_suffix("")) for path in site.rglob("*.mdx")}
    assert set(pages) == all_pages, "Every Mintlify page must be in navigation"
    checks = ["all pages reachable through Mintlify navigation"]
    for name in pages:
        text = (site / (name + ".mdx")).read_text()
        front = yaml.safe_load(text.split("---", 2)[1])
        assert front["title"] and front["description"]
        for fence in re.findall(r"```json\n(.*?)\n```", text, re.S):
            json.loads(fence)
        for link in re.findall(r'(?:\]\(|href=")(/[^\s\)"#]+)', text):
            target = site / link.lstrip("/")
            assert target.is_file() or target.with_suffix(".mdx").is_file(), link
    for source, copied in [
        ("api-contract.json", "v1.json"),
        ("reasoning-api-contract.json", "v2.json"),
    ]:
        assert (ROOT / "contracts" / source).read_bytes() == (
            site / "openapi" / copied
        ).read_bytes()
    checks += [
        "MDX frontmatter and JSON examples",
        "internal Mintlify links",
        "exact OpenAPI copies",
    ]
    for source in [ROOT / "README.md", ROOT / "web/README.md", ROOT / "docs/README.md"]:
        for link in re.findall(r"\]\(([^\s)]+)\)", source.read_text()):
            if "://" not in link and not link.startswith("#"):
                assert (source.parent / link.split("#")[0]).exists(), link
    checks.append("README and engineering index file links")

    from test_api_v2 import uncertain
    from test_browser_session_integration import core_http
    from test_video import make_mov

    from forte.api import create_app
    from forte.contracts_v2 import CorrectionRequest, ReasoningDoneJob
    from forte.settings import Settings

    generated_example = json.loads((site / "examples/v2-result.json").read_text())
    ReasoningDoneJob.model_validate(generated_example)
    assert generated_example["result"]["provenance"]["model_name"] == "synthetic-only"
    v2_doc = (site / "api/v2.mdx").read_text()
    correction_example = json.loads(re.findall(r"```json\n(.*?)\n```", v2_doc, re.S)[0])
    CorrectionRequest.model_validate(correction_example)
    assert correction_example["source_sha256"] == generated_example["result"]["source_sha256"]
    checks.append("generated complete v2 response and correction request schemas")

    with tempfile.TemporaryDirectory(prefix="forte-docs-") as temporary:
        private = Path(temporary)
        env = dict(os.environ, FORTE_EXAMPLE_ROOT=str(private / "client"))
        auth_doc = (site / "api/authentication.mdx").read_text()
        key_command = re.findall(r"```bash\n(.*?)\n```", auth_doc, re.S)[0]
        # Replace only the example directory: execute the actual documented key recipe.
        key_command = key_command.replace(
            'export FORTE_EXAMPLE_ROOT="$HOME/.local/share/forte26/api-example"',
            'export FORTE_EXAMPLE_ROOT="' + str(private / "client") + '"',
        )
        completed = subprocess.run(
            ["bash", "-c", key_command], cwd=ROOT, env=env, capture_output=True, text=True
        )
        assert completed.returncode == 0, "Documented private-key recipe failed"
        assert not completed.stdout.strip(), "Private-key recipe must not print its secret"
        client_root = private / "client"
        key_path = client_root / "service-api.key"
        header_path = client_root / "request.headers"
        assert key_path.stat().st_mode & 0o777 == 0o600
        assert header_path.stat().st_mode & 0o777 == 0o600
        key = key_path.read_text().strip()
        assert header_path.read_text() == "X-API-Key: " + key + "\n"
        checks.append("documented key generation, private permissions and zero secret output")

        sample = make_mov(private / "generated.mov")
        settings = Settings(key, private / "cases")
        app = create_app(settings, runner=uncertain, ready=lambda: True)
        with core_http(app) as origin:
            env.update(BASE_URL=origin, SAMPLE_FILE=str(sample))
            v1_doc = (site / "api/v1.mdx").read_text()
            commands = re.findall(r"```bash\n(.*?)\n```", v1_doc, re.S)
            submit = commands[0].replace(
                'export BASE_URL="http://127.0.0.1:8000"', 'export BASE_URL="' + origin + '"'
            )
            submit = submit.replace(
                'export SAMPLE_FILE="/absolute/path/to/authorized-sample.mov"',
                'export SAMPLE_FILE="' + str(sample) + '"',
            )
            run = subprocess.run(["bash", "-c", submit], cwd=ROOT, env=env, capture_output=True)
            assert run.returncode == 0, "Documented curl submission failed"
            for _ in range(100):
                run = subprocess.run(
                    ["bash", "-c", commands[1]], cwd=ROOT, env=env, capture_output=True
                )
                assert run.returncode == 0, "Documented curl polling failed"
                result = json.loads((client_root / "result.json").read_text())
                if result["status"] != "processing":
                    break
                time.sleep(0.02)
            assert (
                result["status"] == "failed" and result["error"]["code"] == "insufficient_evidence"
            )
            schema = json.loads((ROOT / "contracts/api-contract.json").read_text())
            validator = Draft202012Validator(
                {"$ref": "#/components/schemas/JobResponse", "components": schema["components"]}
            )
            validator.validate(result)
            for example in re.findall(r"```json\n(.*?)\n```", v1_doc, re.S):
                data = json.loads(example)
                if "status" in data:
                    validator.validate(data)
            checks += [
                "actual documented curl POST202 and GET terminal workflow",
                "v1 response examples match exact jury schema",
            ]
            with httpx.Client(base_url=origin, timeout=15, trust_env=False) as client:
                assert client.get("/health/live").json() == {"status": "ok"}
                assert client.get("/health/ready").status_code == 200
                missing = "/api/v1/jobs/00000000-0000-4000-8000-000000000000"
                assert client.get(missing).status_code == 401
                headers = {"X-API-Key": key}
                assert client.get(missing, headers=headers).status_code == 404
                assert (
                    client.post(
                        "/api/v1/analyze",
                        headers=headers,
                        files={"wrong": ("generated.mov", sample.read_bytes())},
                    ).status_code
                    == 422
                )
                assert (
                    client.post(
                        "/api/v1/analyze",
                        headers=headers,
                        files={"file": ("generated.txt", b"invalid")},
                    ).status_code
                    == 415
                )
                accepted = client.post(
                    "/api/v2/analyze",
                    headers=headers,
                    files={"file": ("generated.mov", sample.read_bytes())},
                )
                assert accepted.status_code == 202
                path = "/api/v2/jobs/" + accepted.json()["job_id"]
                for _ in range(100):
                    data = client.get(path, headers=headers).json()
                    if data["status"] != "processing":
                        break
                    time.sleep(0.02)
                assert data["status"] == "done"
                assert data["result"]["assessment"] == "insufficient_evidence"
                (client_root / "result.json").write_text(json.dumps(data))
                v2_commands = re.findall(r"```bash\n(.*?)\n```", v2_doc, re.S)
                run = subprocess.run(
                    ["bash", "-c", v2_commands[0]], cwd=ROOT, env=env, capture_output=True
                )
                assert run.returncode == 0, "Documented v2 original-media curl failed"
                assert (
                    hashlib.sha256((client_root / "original.mov").read_bytes()).hexdigest()
                    == data["result"]["source_sha256"]
                )
                assert (
                    hashlib.sha256(
                        client.get(path + "/source", headers=headers).content
                    ).hexdigest()
                    == data["result"]["source_sha256"]
                )
                frame = data["result"]["events"][0]["evidence"][0]
                jpeg = client.get(path + "/evidence/" + frame["frame_id"], headers=headers)
                assert hashlib.sha256(jpeg.content).hexdigest() == frame["jpeg_sha256"]
                assert client.get(path + "/corrections", headers=headers).json() == {
                    "revisions": []
                }
                correction = dict(correction_example, source_sha256=data["result"]["source_sha256"])
                (client_root / "correction.json").write_text(json.dumps(correction))
                run = subprocess.run(
                    ["bash", "-c", v2_commands[1]], cwd=ROOT, env=env, capture_output=True
                )
                assert run.returncode == 0, "Documented v2 correction curl failed"
                appended = json.loads((client_root / "correction-response.json").read_text())
                assert appended["correction"]["origin"] == "human"
                assert appended["correction"]["other_scopes_approved"] is False
                assert (
                    client.post(path + "/corrections", headers=headers, json=correction).status_code
                    == 409
                )
                assert client.get(path, headers=headers).json() == data
                assert client.get(path + "/report", headers=headers).status_code == 200
            checks += [
                "real health and 401/404/415/422 response boundaries",
                "documented v2 curl original download and source hash",
                "documented v2 curl immutable correction, scope boundary and stale-parent conflict",
                "v2 successful abstention, original source/JPEG and report routes",
            ]

        # Verify the documented aggregate command with fully synthetic completed v1 artifacts.
        group = {
            "recording_id": "a" * 64,
            "neutral_file": "clip000.mov",
            "split": "development",
            "positive": False,
        }
        results = private / "evaluation"
        (results / "clip000").mkdir(parents=True)
        (results / "clip000/result.json").write_text(
            json.dumps(
                {
                    "job_id": result["job_id"],
                    "status": "done",
                    "verdict": "no_violation",
                    "violations": [],
                }
            )
        )
        (results / "clip000/summary.json").write_text(
            json.dumps({"source_sha256": group["recording_id"], "seconds": 1.0})
        )
        manifest = private / "development.json"
        manifest.write_text(json.dumps({"split_status": "synthetic", "groups": [group]}))
        run = subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "forte",
                "evaluate",
                "--manifest",
                str(manifest),
                "--results",
                str(results),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, "Documented evaluator CLI failed"
        metrics = json.loads(run.stdout)
        assert metrics["counts"]["tn"] == 1 and metrics["accuracy_including_failed"] == 1.0
        assert metrics["effective_recall"] is None
        checks.append("documented v1 evaluator CLI and zero-positive denominator")

    print(
        json.dumps(
            {
                "documentation_checks": "passed",
                "pages": len(pages),
                "checks": checks,
                "fixtures": "generated only",
                "model_inference": False,
                "private_credentials_printed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
