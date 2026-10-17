"""Synthetic versioned API checks; these do not benchmark recognition quality."""

import base64
import copy
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_video import make_mov

from forte.api import create_app
from forte.contracts import DoneJob
from forte.contracts_v2 import ReasoningDoneJob
from forte.settings import Settings
from forte.video import decode_video

KEY = "synthetic-version-two-key"
HEADERS = {"X-API-Key": KEY}


@pytest.fixture
def settings(tmp_path):
    return Settings(api_key=KEY, private_root=tmp_path / "jobs")


async def negative(directory, job_id, deadline):
    return DoneJob(job_id=job_id, verdict="no_violation", violations=[])


async def uncertain(directory, job_id, deadline):
    """Persist an actual synthetic source JPEG and its complete byte binding."""
    revision = directory / ("reasoning-" + "1" * 32)
    revision.mkdir(mode=0o700)
    registry = decode_video(directory / "input.mov", revision / "sampled-frames")
    first = registry.frames[0]
    original = registry.evidence([first.frame_id])[0]
    image = base64.b64decode(original.image_base64)
    image_path = revision / "evidence" / (first.frame_id + ".jpg")
    image_path.parent.mkdir(mode=0o700)
    image_path.write_bytes(image)
    source_hash = registry.source_sha256
    evidence = {
        "frame_id": first.frame_id,
        "file": "evidence/" + image_path.name,
        "source_sha256": source_hash,
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "jpeg_sha256": hashlib.sha256(image).hexdigest(),
        "source_pts": first.source_pts,
        "time_base": "1/10240",
        "timestamp_sec": first.timestamp_sec,
        "oriented_size": [96, 64],
        "rotation_degrees": 0,
        "kind": "decoded_source_jpeg_no_overlay_no_resize",
    }
    observation = {
        "observation_id": "obs-00000",
        "source_sha256": source_hash,
        "start_frame_id": first.frame_id,
        "end_frame_id": first.frame_id,
        "decisive_frame_id": first.frame_id,
        "start_sec": first.timestamp_sec,
        "end_sec": first.timestamp_sec,
        "decisive_sec": first.timestamp_sec,
        "kind": "context",
        "value": "Synthetic colored source-frame fixture.",
        "actor_ids": [],
        "recipient_ids": [],
        "evidence_frame_ids": [first.frame_id],
        "visibility": "visible_samples",
        "uncertainty": ["No real participant or transaction in this synthetic source."],
        "continues_before_window": False,
        "continues_after_window": False,
        "origin": "model",
        "review_status": "unreviewed",
    }
    event = {
        **observation,
        "event_id": "event-00000",
        "observation_ids": [observation["observation_id"]],
        "evidence": [evidence],
        "evidence_export_complete": True,
        "assessment": "insufficient_evidence",
        "legal_assessment_ids": [],
    }
    result = {
        "schema_version": "forte.reasoning/1",
        "source_sha256": source_hash,
        "source": {
            "duration_sec": registry.duration,
            "frame_count": len(registry.frames),
            "original_name": "input.mov",
            "frame_table": "source-frames.json",
        },
        "execution": {"status": "partial", "weights_frozen": True, "budget_exhausted": False},
        "assessment": "insufficient_evidence",
        "review_status": "unreviewed",
        "timeline": {
            "source_sha256": source_hash,
            "observations": [observation],
            "events": [event],
            "participants": [],
            "coverage": {"continuous_visibility_validated": False},
        },
        "participants": {"source_sha256": source_hash, "participants": []},
        "legal": {
            "source_sha256": source_hash,
            "assessments": [],
            "rule_coverage": [],
            "status": "incomplete",
        },
        "events": [event],
        "metrics": {},
        "provenance": {"model_name": "synthetic-only"},
        "artifacts": {
            "revision": revision.name,
            "result": "result.json",
            "review": "review.html",
            "source_frames": "source-frames.json",
        },
    }
    return ReasoningDoneJob(job_id=job_id, result=result)


def submit(client, source, *, version=2):
    response = client.post(
        f"/api/v{version}/analyze", headers=HEADERS, files={"file": ("synthetic.mov", source)}
    )
    assert response.status_code == 202, response.text
    assert response.headers["Location"] == f"/api/v{version}/jobs/" + response.json()["job_id"]
    for _ in range(100):
        completed = client.get(response.headers["Location"], headers=HEADERS)
        assert completed.status_code == 200
        if completed.json()["status"] != "processing":
            return completed.json()
        time.sleep(0.01)
    pytest.fail("Synthetic versioned job did not reach a terminal state")


def correction(result, **updates):
    return {
        "source_sha256": result["source_sha256"],
        "parent_revision": None,
        "scope": "visual",
        "target_id": "obs-00000",
        "reviewer": "synthetic-reviewer",
        "change": {"visibility": "synthetic correction"},
        **updates,
    }


def test_v2_uncertainty_is_success_and_v1_contract_and_job_namespaces_remain_separate(
    settings, tmp_path
):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    app = create_app(settings, runner=negative, reasoning_runner=uncertain, ready=lambda: True)
    with TestClient(app) as client:
        v2 = submit(client, source)
        assert v2["status"] == "done" and v2["api_version"] == 2
        assert v2["result"]["assessment"] == "insufficient_evidence"
        assert v2["result"]["execution"]["status"] == "partial"
        assert "error" not in v2 and "verdict" not in v2
        assert client.get("/api/v1/jobs/" + v2["job_id"], headers=HEADERS).status_code == 404
        v1 = submit(client, source, version=1)
        assert v1 == {
            "job_id": v1["job_id"],
            "status": "done",
            "verdict": "no_violation",
            "violations": [],
        }
        assert client.get("/api/v2/jobs/" + v1["job_id"], headers=HEADERS).status_code == 404
        assert client.get("/openapi.json").json() == json.loads(
            Path("contracts/api-contract.json").read_text()
        )


def test_all_private_v2_resources_require_auth_before_validation_or_disclosure(settings):
    app = create_app(settings, reasoning_runner=uncertain, ready=lambda: True)
    with TestClient(app) as client:
        for suffix in ["", "/source", "/evidence/f000000", "/corrections"]:
            assert client.get("/api/v2/jobs/not-a-uuid" + suffix).status_code == 401
        assert client.post("/api/v2/jobs/not-a-uuid/corrections", json={}).status_code == 401
        assert client.get("/api/v2/jobs/not-a-uuid/source", headers=HEADERS).status_code == 422
        assert client.get(f"/api/v2/jobs/{uuid4()}/source", headers=HEADERS).status_code == 404


def test_authenticated_source_and_source_evidence_match_their_recorded_hashes(settings, tmp_path):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    with TestClient(create_app(settings, reasoning_runner=uncertain, ready=lambda: True)) as client:
        completed = submit(client, source)
        prefix = "/api/v2/jobs/" + completed["job_id"]
        result = completed["result"]
        served = client.get(prefix + "/source", headers=HEADERS)
        assert served.status_code == 200 and served.content == source
        assert served.headers["cache-control"] == "no-store"
        assert hashlib.sha256(served.content).hexdigest() == result["source_sha256"]
        item = result["events"][0]["evidence"][0]
        frame = client.get(prefix + "/evidence/" + item["frame_id"], headers=HEADERS)
        assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg"
        assert frame.headers["cache-control"] == "no-store"
        assert hashlib.sha256(frame.content).hexdigest() == item["image_sha256"]
        assert frame.content.startswith(b"\xff\xd8")
        assert client.get(prefix + "/evidence/invented-frame", headers=HEADERS).status_code == 404
        path = settings.private_root / completed["job_id"] / result["artifacts"]["revision"]
        (path / item["file"]).write_bytes(b"changed synthetic evidence")
        assert (
            client.get(prefix + "/evidence/" + item["frame_id"], headers=HEADERS).status_code == 409
        )


def test_evidence_symlink_cannot_escape_its_private_revision(settings, tmp_path):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    with TestClient(create_app(settings, reasoning_runner=uncertain, ready=lambda: True)) as client:
        completed = submit(client, source)
        result = completed["result"]
        item = result["events"][0]["evidence"][0]
        revision = settings.private_root / completed["job_id"] / result["artifacts"]["revision"]
        outside = tmp_path / "outside-synthetic.jpg"
        outside.write_bytes((revision / item["file"]).read_bytes())
        (revision / item["file"]).unlink()
        (revision / item["file"]).symlink_to(outside)
        response = client.get(
            f"/api/v2/jobs/{completed['job_id']}/evidence/{item['frame_id']}", headers=HEADERS
        )
        assert response.status_code == 404 and outside.read_bytes() not in response.content


def test_changed_original_media_is_never_served_as_the_analyzed_recording(settings, tmp_path):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    with TestClient(create_app(settings, reasoning_runner=uncertain, ready=lambda: True)) as client:
        completed = submit(client, source)
        original = settings.private_root / completed["job_id"] / "input.mov"
        original.chmod(0o600)
        original.write_bytes(b"changed synthetic source")
        response = client.get(f"/api/v2/jobs/{completed['job_id']}/source", headers=HEADERS)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "source_changed"
        assert b"changed synthetic source" not in response.content


def test_corrections_preserve_immutable_result_and_reject_wrong_source_target_and_stale_parent(
    settings, tmp_path
):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    with TestClient(create_app(settings, reasoning_runner=uncertain, ready=lambda: True)) as client:
        completed = submit(client, source)
        prefix = "/api/v2/jobs/" + completed["job_id"]
        result = completed["result"]
        first = client.post(prefix + "/corrections", headers=HEADERS, json=correction(result))
        assert first.status_code == 201, first.text
        first_revision = first.json()["revision"]
        stored = first.json()["correction"]
        assert stored["scope"] == "visual" and stored["target_id"] == "obs-00000"
        assert stored["origin"] == "human" and stored["other_scopes_approved"] is False
        assert (
            stored["base_result_sha256"]
            == hashlib.sha256(
                json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
            ).hexdigest()
        )
        assert client.get(prefix, headers=HEADERS).json() == completed
        assert (
            client.post(
                prefix + "/corrections", headers=HEADERS, json=correction(result)
            ).status_code
            == 409
        )
        second = client.post(
            prefix + "/corrections",
            headers=HEADERS,
            json=correction(result, parent_revision=first_revision),
        )
        assert second.status_code == 201
        assert (
            client.post(
                prefix + "/corrections",
                headers=HEADERS,
                json=correction(result, parent_revision=first_revision),
            ).status_code
            == 409
        )
        current = second.json()["revision"]
        for updates in [{"source_sha256": "0" * 64}, {"target_id": "invented-observation"}]:
            assert (
                client.post(
                    prefix + "/corrections",
                    headers=HEADERS,
                    json=correction(result, parent_revision=current, **updates),
                ).status_code
                == 409
            )
        assert (
            client.post(
                prefix + "/corrections",
                headers=HEADERS,
                json=correction(result, parent_revision="../outside.json"),
            ).status_code
            == 422
        )
        revisions = client.get(prefix + "/corrections", headers=HEADERS).json()["revisions"]
        assert len(revisions) == 2
        assert {r["parent_revision"] for r in revisions} == {None, first_revision}


def test_v2_runner_cannot_finish_with_a_v1_binary_result(settings, tmp_path):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    with TestClient(create_app(settings, reasoning_runner=negative, ready=lambda: True)) as client:
        completed = submit(client, source)
        assert completed["status"] == "failed"
        assert completed["error"]["code"] == "analysis_failed"


def test_correction_parent_cannot_be_reused_after_immutable_base_result_changes(settings, tmp_path):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    with TestClient(create_app(settings, reasoning_runner=uncertain, ready=lambda: True)) as client:
        completed = submit(client, source)
        prefix = "/api/v2/jobs/" + completed["job_id"]
        first = client.post(
            prefix + "/corrections", headers=HEADERS, json=correction(completed["result"])
        )
        assert first.status_code == 201
        state_path = settings.private_root / completed["job_id"] / "state.json"
        altered = copy.deepcopy(completed)
        altered["result"]["metrics"]["synthetic_tampering"] = True
        state_path.write_text(json.dumps(altered))
        response = client.post(
            prefix + "/corrections",
            headers=HEADERS,
            json=correction(completed["result"], parent_revision=first.json()["revision"]),
        )
        assert response.status_code == 409
        assert len(client.get(prefix + "/corrections", headers=HEADERS).json()["revisions"]) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", "../outside"),
        ("file", "../../outside.jpg"),
        ("source_sha256", "0" * 64),
        ("timestamp_sec", 181),
    ],
)
def test_v2_contract_rejects_artifact_traversal_mixed_sources_and_outside_source_times(
    settings, tmp_path, field, value
):
    source = make_mov(tmp_path / "source.mov").read_bytes()
    with TestClient(create_app(settings, reasoning_runner=uncertain, ready=lambda: True)) as client:
        completed = submit(client, source)
    result = completed["result"]
    if field == "revision":
        result["artifacts"][field] = value
    else:
        result["events"][0]["evidence"][0][field] = value
    with pytest.raises(ValueError):
        ReasoningDoneJob(job_id=uuid4(), result=result)


def test_version_two_schema_rejects_absent_source_binding():
    for result in [
        {},
        {"schema_version": "forte.reasoning/1", "assessment": "insufficient_evidence"},
    ]:
        with pytest.raises(ValueError):
            ReasoningDoneJob(job_id=uuid4(), result=result)
