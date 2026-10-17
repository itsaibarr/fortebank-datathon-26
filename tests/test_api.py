import asyncio
import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_video import make_mov

from forte.api import create_app
from forte.contracts import DoneJob
from forte.settings import Settings

KEY = "synthetic-test-key-only"


@pytest.fixture
def settings(tmp_path):
    return Settings(api_key=KEY, private_root=tmp_path / "jobs")


async def negative(directory, job_id, deadline):
    return DoneJob(job_id=job_id, verdict="no_violation", violations=[])


def test_auth_precedes_body_and_job_existence(settings):
    consumed = []

    def body():
        consumed.append(True)
        yield b"not even multipart"

    with TestClient(create_app(settings, runner=negative, ready=lambda: True)) as client:
        assert client.post("/api/v1/analyze", content=body()).status_code == 401
        assert not consumed
        assert client.get("/api/v1/jobs/not-a-uuid").status_code == 401
        assert client.get("/api/v1/jobs/not-a-uuid", headers={"X-API-Key": KEY}).status_code == 422


def test_required_post_and_get_contract(settings, tmp_path):
    source = make_mov(tmp_path / "s.mov").read_bytes()
    with TestClient(create_app(settings, runner=negative, ready=lambda: True)) as client:
        headers = {"X-API-Key": KEY}
        response = client.post(
            "/api/v1/analyze", files={"file": ("s.mov", source)}, headers=headers
        )
        assert response.status_code == 202
        id = response.json()["job_id"]
        UUID(id)
        import time

        for _ in range(100):
            r = client.get("/api/v1/jobs/" + id, headers=headers)
            if r.json()["status"] != "processing":
                break
            time.sleep(0.01)
        assert r.json() == {
            "job_id": id,
            "status": "done",
            "verdict": "no_violation",
            "violations": [],
        }
        assert client.get(response.headers["Location"], headers=headers).json() == r.json()
        schema = json.loads(open("contracts/api-contract.json").read())
        from jsonschema import Draft202012Validator

        Draft202012Validator(
            {"$ref": "#/components/schemas/JobResponse", "components": schema["components"]}
        ).validate(r.json())


def test_capacity_is_checked_before_body_and_timeout_is_terminal(settings, tmp_path):
    async def slow(directory, job_id, deadline):
        await asyncio.sleep(10)
        return await negative(directory, job_id, deadline)

    settings.job_timeout = 2
    source = make_mov(tmp_path / "s.mov").read_bytes()
    with TestClient(create_app(settings, runner=slow, ready=lambda: True)) as client:
        h = {"X-API-Key": KEY}
        a = client.post("/api/v1/analyze", files={"file": ("s.mov", source)}, headers=h)
        b = client.post("/api/v1/analyze", files={"file": ("s.mov", source)}, headers=h)
        assert a.status_code == b.status_code == 202
        consumed = []

        def body():
            consumed.append(True)
            yield b"x"

        assert client.post("/api/v1/analyze", content=body(), headers=h).status_code == 429
        assert not consumed
        import time

        time.sleep(2.1)
        for response in [a, b]:
            result = client.get("/api/v1/jobs/" + response.json()["job_id"], headers=h).json()
            assert result["status"] == "failed"
            assert result["error"]["code"] == "processing_timeout"


def test_errors_and_not_ready_are_explicit(settings, tmp_path):
    h = {"X-API-Key": KEY}
    with TestClient(create_app(settings, runner=negative, ready=lambda: False)) as client:
        assert client.post("/api/v1/analyze", content=b"x", headers=h).status_code == 503
    with TestClient(create_app(settings, runner=negative, ready=lambda: True)) as client:
        assert (
            client.post("/api/v1/analyze", files={"file": ("bad.txt", b"x")}, headers=h).status_code
            == 415
        )
        assert (
            client.post(
                "/api/v1/analyze", files={"file": ("bad.mov", b"corrupt")}, headers=h
            ).status_code
            == 415
        )
        assert (
            client.post("/api/v1/analyze", files={"wrong": ("s.mov", b"x")}, headers=h).status_code
            == 422
        )
        settings.upload_max_bytes = 8
        assert client.post("/api/v1/analyze", content=b"x" * 20, headers=h).status_code == 413


def test_restart_fails_inflight_and_terminal_state_cannot_be_overwritten(settings):
    from uuid import uuid4

    from forte.jobs import JobStore

    id = uuid4()
    store = JobStore(settings.private_root)
    store.create(id)
    store.close()
    store = JobStore(settings.private_root)
    assert store.read(id).status == "failed"
    assert store.read(id).error.code == "interrupted"
    assert not store.finish(DoneJob(job_id=id, verdict="no_violation", violations=[]))
    store.close()


def test_upload_timeout_is_enforced_before_a_job_is_created(settings):
    settings.upload_timeout = 0.02
    app = create_app(settings, runner=negative, ready=lambda: True)
    messages = []

    async def exercise():
        async with app.router.lifespan_context(app):

            async def receive():
                await asyncio.sleep(1)
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/analyze",
                "raw_path": b"/api/v1/analyze",
                "query_string": b"",
                "server": ("localhost", 80),
                "client": ("127.0.0.1", 1),
                "headers": [
                    (b"x-api-key", KEY.encode()),
                    (b"content-type", b"multipart/form-data; boundary=test"),
                ],
            }
            await app(scope, receive, send)

    asyncio.run(exercise())
    assert next(m["status"] for m in messages if m["type"] == "http.response.start") == 408
    assert not list(settings.private_root.glob("*/state.json"))


def test_openapi_preserves_the_approved_external_contract(settings):
    with TestClient(create_app(settings, runner=negative, ready=lambda: True)) as client:
        expected = json.loads(open("contracts/api-contract.json").read())
        assert client.get("/openapi.json").json() == expected
