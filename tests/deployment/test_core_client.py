"""Real core HTTP/multipart compatibility, with synthetic media and inference only.

No model is loaded, no private data is read, and the only listener is ephemeral
loopback. These are transport integration checks, not model or quality evidence.
"""

import asyncio
import hashlib
import json
import socket
import sys
import threading
import time
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from uuid import UUID

import av
import pytest
import uvicorn
from jsonschema import Draft202012Validator
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools/forte-admin")]

from forte_admin.client import APIClient, ClientError  # noqa: E402

import forte.api  # noqa: E402
from forte.api import create_app  # noqa: E402
from forte.contracts import DoneJob  # noqa: E402
from forte.contracts_v2 import ReasoningDoneJob  # noqa: E402
from forte.settings import Settings  # noqa: E402


@contextmanager
def core_http(app):
    """Run the actual ASGI application on a reserved ephemeral loopback socket."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            loop="asyncio",
            ws="none",
            log_level="critical",
            access_log=False,
            lifespan="on",
            timeout_graceful_shutdown=1,
        )
    )
    worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            worker.join(timeout=0.01)
        assert server.started, "Actual core HTTP server did not start."
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        worker.join(timeout=5)
        if worker.is_alive():
            server.force_exit = True
            worker.join(timeout=1)
        listener.close()
        assert not worker.is_alive(), "Isolated core HTTP server did not stop."


def synthetic_mov(path):
    """Make an actual, small MOV of solid colors; no case or recording content."""
    with av.open(str(path), "w", format="mov") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 96, 64, "yuv420p"
        stream.time_base = Fraction(1, 10)
        for index in range(4):
            frame = av.VideoFrame.from_image(Image.new("RGB", (96, 64), "blue"))
            frame.pts, frame.time_base = index, Fraction(1, 10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


@pytest.mark.parametrize("api_version", [1, 2])
def test_client_actual_core_routes_with_synthetic_inference(tmp_path, monkeypatch, api_version):
    # The environment also has an editable install for Agent A. Imports and the
    # real core's video-probe subprocess must use this stable release checkout.
    assert Path(forte.api.__file__).resolve() == REPO / "src/forte/api.py"
    monkeypatch.setenv("PYTHONPATH", str(REPO / "src"))
    source = synthetic_mov(tmp_path / "synthetic.mov")
    source_bytes = source.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    with av.open(str(source)) as container:
        video = container.streams.video[0]
        duration = float(video.duration * video.time_base)
    key = "synthetic-core-transport-key"
    key_file = tmp_path / "synthetic.key"
    key_file.write_text(key + "\n")
    key_file.chmod(0o600)
    ready = {"value": False}
    release = threading.Event()
    expected_result = {
        "schema_version": "forte.reasoning/1",
        "source_sha256": digest,
        "source": {"duration_sec": duration, "frame_table": "source-frames.json"},
        "artifacts": {"revision": "reasoning-" + "1" * 32},
        "assessment": "insufficient_evidence",
        "execution": {"status": "partial", "weights_frozen": True},
        "timeline": {"source_sha256": digest},
        "events": [],
        "uncertainty": ["Explicit synthetic fixture; no model inference occurred."],
        "provenance": {"model_name": "synthetic-test-runner-only"},
        "future_additive_field": {"preserved": True},
    }

    async def synthetic_runner(directory, job_id, deadline):
        assert (directory / "input.mov").read_bytes() == source_bytes
        while not release.is_set():
            await asyncio.sleep(0.005)
        if api_version == 2:
            return ReasoningDoneJob(job_id=job_id, result=expected_result)
        return DoneJob(job_id=job_id, verdict="no_violation", violations=[])

    settings = Settings(api_key=key, private_root=tmp_path / "synthetic-jobs")
    app = create_app(
        settings,
        ready=lambda: ready["value"],
        runner=synthetic_runner,
        reasoning_runner=synthetic_runner,
    )
    try:
        with core_http(app) as endpoint:
            client = APIClient(endpoint, key_file, api_version=api_version, timeout=5)
            with pytest.raises(ClientError) as error:
                client.health()
            assert error.value.status == 503
            ready["value"] = True
            assert client.health() == {"status": "ready"}
            accepted = client.upload(source)
            UUID(accepted["job_id"])
            assert client.job(accepted["job_id"])["status"] == "processing"
            release.set()
            result = client.wait(accepted["job_id"], timeout=5, poll_interval=0.005)
            assert result["status"] == "done"
            assert client.job(accepted["job_id"]) == result
            assert (settings.private_root / accepted["job_id"] / "input.mov").read_bytes() == (
                source_bytes
            )
            contract_name = (
                "reasoning-api-contract.json" if api_version == 2 else "api-contract.json"
            )
            contract = json.loads((REPO / "contracts" / contract_name).read_text())
            schema = contract["paths"][f"/api/v{api_version}/jobs/{{job_id}}"]["get"]["responses"][
                "200"
            ]["content"]["application/json"]["schema"]
            Draft202012Validator({**schema, "components": contract["components"]}).validate(result)
            if api_version == 2:
                assert result["result"] == expected_result
                assert "verdict" not in result and "error" not in result
                assert result["result"]["assessment"] == "insufficient_evidence"
                assert result["result"]["execution"]["status"] == "partial"
            else:
                assert result == {
                    "job_id": accepted["job_id"],
                    "status": "done",
                    "verdict": "no_violation",
                    "violations": [],
                }
    finally:
        release.set()
