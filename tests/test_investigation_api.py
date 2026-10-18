"""Synthetic case-report API ownership, lineage and privacy regression checks."""

import asyncio
import copy
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from test_api_v2 import KEY, correction, uncertain
from test_gateway_ownership import TOKEN, headers, submit
from test_video import make_mov

from forte.api import create_app
from forte.investigation_report import result_digest
from forte.settings import Settings


async def partial(directory, job_id, deadline):
    job = await uncertain(directory, job_id, deadline)
    result = job.result
    result["timeline"]["coverage"].update(
        {
            "unexamined_intervals": [[0.5, 1]],
            "unclear_intervals": [],
            "pending_reinspections": 1,
            "output_capacity_limited_intervals": [[0, 0.5]],
        }
    )
    result["legal"]["rule_coverage"] = [
        {"rule_id": "synthetic-rule", "status": "skipped", "reason": None}
    ]
    result["participants"]["unresolved_matches"] = [{"owner": None}]
    adjacent = copy.deepcopy(result["events"][0])
    adjacent["event_id"] = "event-adjacent"
    result["events"].append(adjacent)
    return job


def test_report_preserves_result_history_and_attachment_without_new_inference(tmp_path):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    application = create_app(settings, runner=partial, ready=lambda: True)
    with TestClient(application) as client:
        job = submit(client, source)
        prefix = "/api/v2/jobs/" + job["job_id"]
        saved = client.post(
            prefix + "/corrections", headers=headers(), json=correction(job["result"])
        )
        assert saved.status_code == 201
        response = client.get(prefix + "/report", headers=headers())
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["schema_version"] == "forte.investigation-report/1"
        assert report["result"] == job["result"]
        assert report["base_result_sha256"] == result_digest(job["result"])
        assert report["corrections"] == [saved.json()["correction"]]
        assert report["review_head"] == saved.json()["revision"]
        assert report["corrections_match_current_result"] is True
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Content-Type"].startswith("application/json")
        assert (
            response.headers["Content-Disposition"]
            == f'attachment; filename="forte-case-{job["job_id"]}.json"'
        )
        assert str(tmp_path) not in json.dumps(report["links"])
        assert client.get(prefix, headers=headers()).json() == job


def test_report_checks_owner_and_auth_before_private_history_access(tmp_path):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    application = create_app(settings, runner=partial, ready=lambda: True)
    with TestClient(application) as client:
        job = submit(client, source)
        prefix = "/api/v2/jobs/" + job["job_id"]
        unknown = client.get(f"/api/v2/jobs/{uuid4()}/report", headers=headers("reviewer-b"))
        assert (
            client.get(prefix + "/report", headers=headers("reviewer-b")).json() == unknown.json()
        )
        assert unknown.status_code == 404
        for auth in [{}, {"X-API-Key": KEY}]:
            assert client.get("/api/v2/jobs/not-a-uuid/report", headers=auth).status_code == 401
        request_path = settings.private_root / job["job_id"] / "request.json"
        request_path.write_text(json.dumps({"api_version": 2}))
        assert client.get(prefix + "/report", headers=headers()).status_code == 404
        legacy = submit(client, source, version=1)
        assert (
            client.get(f"/api/v2/jobs/{legacy['job_id']}/report", headers=headers()).status_code
            == 404
        )


def test_corruption_returns_sanitized_conflict_for_history_and_report(tmp_path):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with TestClient(create_app(settings, runner=partial, ready=lambda: True)) as client:
        job = submit(client, source)
        prefix = "/api/v2/jobs/" + job["job_id"]
        directory = settings.private_root / job["job_id"] / "corrections"
        directory.mkdir()
        (directory / ("f" * 32 + ".json")).write_text("private-synthetic-canary: invalid")
        for suffix in ["/corrections", "/report"]:
            response = client.get(prefix + suffix, headers=headers())
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "correction_history_unavailable"
            assert "private-synthetic-canary" not in response.text
            assert str(tmp_path) not in response.text


def test_processing_and_failed_reports_are_unavailable(tmp_path):
    async def blocked(directory, job_id, deadline):
        await asyncio.sleep(10)

    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with TestClient(create_app(settings, runner=blocked, ready=lambda: True)) as client:
        accepted = client.post(
            "/api/v2/analyze", headers=headers(), files={"file": ("synthetic.mov", source)}
        )
        assert accepted.status_code == 202
        prefix = accepted.headers["Location"]
        assert client.get(prefix + "/report", headers=headers()).status_code == 409
    with TestClient(create_app(settings, runner=partial, ready=lambda: True)) as client:
        assert client.get(prefix + "/report", headers=headers()).status_code == 409
