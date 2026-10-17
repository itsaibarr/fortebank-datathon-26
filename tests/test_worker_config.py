"""Programmatic dictionary settings cross the worker boundary as private snapshots."""

import asyncio
import copy
import json
import time
from uuid import uuid4

import pytest

from forte import jobs
from forte.settings import Settings


def test_dictionary_is_validated_frozen_and_passed_as_path_without_model_launch(
    tmp_path, monkeypatch
):
    job_id = uuid4()
    directory = tmp_path / str(job_id)
    directory.mkdir(mode=0o700)
    configuration = {"tracking": {"mode": "byte_track"}, "legal": {"release": "/synthetic"}}
    original = copy.deepcopy(configuration)
    settings = Settings("synthetic-service-key", tmp_path, reasoning_config=configuration)
    calls = []

    async def synthetic_child(arguments, timeout):
        calls.append(arguments)
        path = arguments[arguments.index("--reasoning-config") + 1]
        assert path == str(directory / "immutable/request-config.json")
        assert (
            json.loads((directory / "immutable/request-config.json").read_text())["tracking"]
            == configuration["tracking"]
        )
        jobs.atomic_json(
            directory / "worker-result.json",
            jobs.failure(job_id, "synthetic").model_dump(mode="json"),
        )
        return b""

    monkeypatch.setattr(jobs, "child", synthetic_child)
    result = asyncio.run(
        jobs.run_worker(directory, job_id, time.monotonic() + 10, settings, reasoning=True)
    )
    frozen = directory / "immutable/request-config.json"
    assert result.job_id == job_id and len(calls) == 1
    assert frozen.stat().st_mode & 0o777 == 0o400
    assert json.loads(frozen.read_text())["bounds"]["max_calls"] == 32
    assert configuration == original
    before = frozen.read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(
            jobs.run_worker(directory, job_id, time.monotonic() + 10, settings, reasoning=True)
        )
    assert frozen.read_bytes() == before and len(calls) == 1


def test_invalid_dictionary_never_reaches_worker_or_creates_snapshot(tmp_path, monkeypatch):
    settings = Settings(
        "synthetic-service-key",
        tmp_path,
        reasoning_config={"tracking": {}, "legal": {}, "training": {"enabled": True}},
    )

    async def forbidden_child(*args):
        pytest.fail("Invalid configuration reached the subprocess boundary")

    monkeypatch.setattr(jobs, "child", forbidden_child)
    with pytest.raises(ValueError, match="training"):
        asyncio.run(
            jobs.run_worker(tmp_path, uuid4(), time.monotonic() + 10, settings, reasoning=True)
        )
    assert not (tmp_path / "immutable").exists()


def test_path_configuration_is_forwarded_unchanged(tmp_path, monkeypatch):
    job_id = uuid4()
    path = tmp_path / "existing-config.json"
    settings = Settings("synthetic-service-key", tmp_path, reasoning_config=path)

    async def synthetic_child(arguments, timeout):
        assert arguments[arguments.index("--reasoning-config") + 1] == str(path)
        jobs.atomic_json(
            tmp_path / "worker-result.json",
            jobs.failure(job_id, "synthetic").model_dump(mode="json"),
        )
        return b""

    monkeypatch.setattr(jobs, "child", synthetic_child)
    asyncio.run(jobs.run_worker(tmp_path, job_id, time.monotonic() + 10, settings, reasoning=True))
    assert not (tmp_path / "immutable").exists()
