"""The exact jury API can opt into one frozen reasoning run without leaking v2."""

import hashlib
import json
import shutil
import sys
import time
import types

import pytest
from fastapi.testclient import TestClient
from test_api_v2 import uncertain
from test_jury_projection import _fixture
from test_video import make_mov

from forte.api import create_app
from forte.contracts_v2 import ReasoningDoneJob
from forte.settings import Settings

KEY = "synthetic-jury-dispatch-key"
TOKEN = "synthetic-jury-gateway-token-" + "a" * 32


def auth(principal="jury-a"):
    return {
        "X-API-Key": KEY,
        "X-Forte-Gateway-Token": TOKEN,
        "X-Forte-Principal": principal,
    }


def configuration():
    return {"tracking": {"mode": "byte_track"}, "legal": {"release": "/synthetic"}}


def poll(client, location, headers):
    for _ in range(150):
        response = client.get(location, headers=headers)
        assert response.status_code == 200
        if response.json()["status"] != "processing":
            return response.json()
        time.sleep(0.01)
    pytest.fail("Synthetic jury job did not complete")


def test_opt_in_executes_reasoning_once_and_keeps_v1_owner_and_version(tmp_path, monkeypatch):
    cfg = tmp_path / "configuration.json"
    cfg.write_text(json.dumps(configuration()))
    settings = Settings(KEY, tmp_path / "jobs", reasoning_config=cfg, trusted_gateway_token=TOKEN)
    calls = []
    projected = []

    async def reasoning(directory, job_id, deadline):
        calls.append("reasoning")
        return await uncertain(directory, job_id, deadline)

    def project(job_id, report, directory, snapshot, *, deadline):
        frozen = directory / "immutable/request-config.json"
        assert snapshot.reasoning_config == frozen
        assert frozen.stat().st_mode & 0o777 == 0o400
        value = json.loads(frozen.read_bytes())
        assert value["tracking"] == configuration()["tracking"]
        assert value["bounds"]["max_calls"] == 32
        projected.append(report["source_sha256"])
        # The synthetic runner remains uncertain; the binary API must fail.
        raise ValueError("insufficient_evidence")

    module = types.ModuleType("forte.jury_projection")
    module.project_reasoning_to_v1 = project
    monkeypatch.setitem(sys.modules, module.__name__, module)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with TestClient(create_app(settings, runner=reasoning, ready=lambda: True)) as client:
        accepted = client.post(
            "/api/v1/analyze", headers=auth(), files={"file": ("synthetic.mov", source)}
        )
        assert accepted.status_code == 202
        location = accepted.headers["Location"]
        result = poll(client, location, auth())
        assert calls == ["reasoning"]
        assert projected == []  # already-insufficient results abstain before artifact replay
        assert result["status"] == "failed"
        assert result["error"]["code"] == "insufficient_evidence"
        assert "api_version" not in result and "result" not in result and "verdict" not in result
        assert client.get(location, headers=auth("jury-b")).status_code == 404
        assert client.get(location.replace("/v1/", "/v2/"), headers=auth()).status_code == 404
        metadata = json.loads(
            (settings.private_root / result["job_id"] / "request.json").read_bytes()
        )
        assert metadata["api_version"] == 1 and metadata["pipeline"] == "reasoning"
        assert metadata["projection"] == "forte.jury-v1/1"
        frozen = settings.private_root / result["job_id"] / "immutable/request-config.json"
        assert (
            metadata["reasoning_config_sha256"] == hashlib.sha256(frozen.read_bytes()).hexdigest()
        )
        assert client.get("/openapi.json").json() == json.loads(
            __import__("pathlib").Path("contracts/api-contract.json").read_bytes()
        )


def test_invalid_opt_in_configuration_rejects_before_reading_upload(tmp_path):
    settings = Settings(
        KEY,
        tmp_path / "jobs",
        reasoning_config={"tracking": {}, "legal": {}, "training": {"enabled": True}},
    )
    consumed = []

    def body():
        consumed.append(True)
        yield b"must-not-be-read"

    with TestClient(create_app(settings, ready=lambda: True)) as client:
        response = client.post("/api/v1/analyze", headers={"X-API-Key": KEY}, content=body())
    assert (
        response.status_code == 503
        and response.json()["error"]["code"] == "reasoning_config_invalid"
    )
    assert not consumed
    assert not list(settings.private_root.glob("*/input.mov"))


def test_v1_has_no_alternate_pipeline_selector(tmp_path, monkeypatch):
    monkeypatch.setenv("FORTE_API_KEY", KEY)
    monkeypatch.setenv("FORTE_PRIVATE_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("FORTE_V1_PIPELINE", "legacy")
    assert not hasattr(Settings.from_env(), "v1_pipeline")


@pytest.mark.parametrize("draft", [False, True])
def test_real_projection_through_admission_and_persistence(tmp_path, draft):
    fixture = _fixture(tmp_path, cards=2, max_calls=1, draft=draft)
    settings = Settings(
        KEY,
        tmp_path / "api-jobs",
        reasoning_config=fixture.settings.reasoning_config,
        trusted_gateway_token=TOKEN,
    )
    calls = []

    async def reasoning(directory, job_id, deadline):
        calls.append(job_id)
        assert (directory / "input.mov").read_bytes() == (
            fixture.directory / "input.mov"
        ).read_bytes()
        assert (directory / "immutable/request-config.json").read_bytes() == (
            fixture.directory / "immutable/request-config.json"
        ).read_bytes()
        shutil.copytree(fixture.revision, directory / fixture.revision.name)
        return ReasoningDoneJob(job_id=job_id, result=fixture.report)

    with TestClient(create_app(settings, runner=reasoning, ready=lambda: True)) as client:
        accepted = client.post(
            "/api/v1/analyze",
            headers=auth(),
            files={"file": ("generated.mov", (fixture.directory / "input.mov").read_bytes())},
        )
        assert accepted.status_code == 202
        location = accepted.headers["Location"]
        result = poll(client, location, auth())
        assert len(calls) == 1
        if draft:
            assert result["status"] == "failed"
            assert result["error"]["code"] == "insufficient_evidence"
        else:
            assert result["status"] == "done" and result["verdict"] == "violation"
            assert len(result["violations"]) == 1
            assert 1 <= len(result["violations"][0]["evidence_frames"]) <= 3
            assert "Other work is incomplete" in result["violations"][0]["description"]
        assert "result" not in result and "api_version" not in result
        assert client.get(location, headers=auth("jury-b")).status_code == 404
        assert client.get(location.replace("/v1/", "/v2/"), headers=auth()).status_code == 404
        receipt = settings.private_root / result["job_id"] / "jury-v1-projection.json"
        assert receipt.is_file()
