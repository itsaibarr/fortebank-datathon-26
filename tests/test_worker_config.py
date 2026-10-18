"""Programmatic dictionary settings cross the worker boundary as private snapshots."""

import asyncio
import copy
import json
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from forte import jobs
from forte.settings import Settings


@pytest.mark.parametrize("replacement", ["pipe", "symlink"])
def test_configuration_replacement_at_open_is_rejected_without_blocking(tmp_path, replacement):
    script = r"""
import json, os, sys
from pathlib import Path
from forte import jobs
from forte.settings import Settings
root = Path(sys.argv[1])
configuration = root / "configuration.json"
configuration.write_text(json.dumps({"tracking": {}, "legal": {}}))
other = root / "other.json"
other.write_text(configuration.read_text())
original_open = os.open
replaced = []
def swap_at_open(path, flags, *args, **kwargs):
    if Path(path) == configuration and not replaced:
        configuration.unlink()
        if sys.argv[2] == "pipe":
            os.mkfifo(configuration)
        else:
            configuration.symlink_to(other)
        replaced.append(True)
    return original_open(path, flags, *args, **kwargs)
jobs.os.open = swap_at_open
try:
    jobs.reasoning_configuration(Settings("synthetic-service-key", root,
        reasoning_config=configuration))
except ValueError:
    assert replaced
else:
    raise AssertionError("Replaced configuration was accepted")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), replacement],
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert completed.returncode == 0, completed.stderr


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
    result = asyncio.run(jobs.run_worker(directory, job_id, time.monotonic() + 10, settings))
    frozen = directory / "immutable/request-config.json"
    assert result.job_id == job_id and len(calls) == 1
    assert frozen.stat().st_mode & 0o777 == 0o400
    assert json.loads(frozen.read_text())["bounds"]["max_calls"] == 32
    assert configuration == original
    before = frozen.read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(jobs.run_worker(directory, job_id, time.monotonic() + 10, settings))
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
    with pytest.raises(ValueError, match="Unknown"):
        asyncio.run(jobs.run_worker(tmp_path, uuid4(), time.monotonic() + 10, settings))
    assert not (tmp_path / "immutable").exists()


def test_path_configuration_is_frozen_before_worker_and_survives_operator_edits(
    tmp_path, monkeypatch
):
    job_id = uuid4()
    path = tmp_path / "existing-config.json"
    original = {"tracking": {"mode": "byte_track"}, "legal": {"release": "/synthetic"}}
    path.write_text(json.dumps(original))
    settings = Settings("synthetic-service-key", tmp_path, reasoning_config=path)

    async def synthetic_child(arguments, timeout):
        frozen = tmp_path / "immutable/request-config.json"
        assert arguments[arguments.index("--reasoning-config") + 1] == str(frozen)
        before = frozen.read_bytes()
        path.write_text(json.dumps({"training": {"enabled": True}}))
        assert frozen.read_bytes() == before
        assert json.loads(before)["tracking"] == original["tracking"]
        assert json.loads(before)["bounds"]["max_calls"] == 32
        assert frozen.stat().st_mode & 0o777 == 0o400
        jobs.atomic_json(
            tmp_path / "worker-result.json",
            jobs.failure(job_id, "synthetic").model_dump(mode="json"),
        )
        return b""

    monkeypatch.setattr(jobs, "child", synthetic_child)
    asyncio.run(jobs.run_worker(tmp_path, job_id, time.monotonic() + 10, settings))
    assert (tmp_path / "immutable/request-config.json").is_file()


def test_symlink_or_pipe_configuration_never_reaches_worker(tmp_path, monkeypatch):
    import os

    actual = tmp_path / "actual.json"
    actual.write_text(json.dumps({"tracking": {}, "legal": {}}))
    link = tmp_path / "link.json"
    link.symlink_to(actual)
    pipe = tmp_path / "pipe.json"
    os.mkfifo(pipe)

    async def forbidden_child(*args):
        pytest.fail("Unsafe configuration reached the subprocess boundary")

    monkeypatch.setattr(jobs, "child", forbidden_child)
    for supplied in (link, pipe):
        with pytest.raises(ValueError, match="regular"):
            asyncio.run(
                jobs.run_worker(
                    tmp_path,
                    uuid4(),
                    time.monotonic() + 10,
                    Settings("synthetic-service-key", tmp_path, reasoning_config=supplied),
                )
            )
    assert not (tmp_path / "immutable").exists()
