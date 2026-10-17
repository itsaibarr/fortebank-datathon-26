"""One service process, two admitted jobs, atomic private filesystem records."""

import asyncio
import copy
import fcntl
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter

from forte.contracts import DoneJob, ErrorDetail, FailedJob, ProcessingJob
from forte.contracts_v2 import ReasoningDoneJob

RESPONSE = TypeAdapter(ProcessingJob | DoneJob | ReasoningDoneJob | FailedJob)


def atomic_json(path: Path, data):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(data, out, ensure_ascii=False, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def failure(id, code):
    messages = {
        "processing_timeout": "Analysis exceeded the processing limit.",
        "interrupted": "Analysis was interrupted by a service restart.",
        "insufficient_evidence": "The visible evidence was insufficient for a reliable result.",
    }
    return FailedJob(
        job_id=id,
        error=ErrorDetail(
            code=code, message=messages.get(code, "Analysis could not complete reliably.")
        ),
    )


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        self.lock = (root / "server.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock.close()
            raise RuntimeError("Use exactly one API process for this job root") from exc
        for p in root.glob("*/state.json"):
            try:
                id = UUID(p.parent.name)
            except ValueError:
                continue
            if self.read(id).status == "processing":
                self.finish(failure(id, "interrupted"))

    def directory(self, id: UUID):
        return self.root / str(id)

    def read(self, id: UUID):
        return RESPONSE.validate_json((self.directory(id) / "state.json").read_text())

    def create(self, id: UUID):
        self.directory(id).mkdir(mode=0o700, exist_ok=True)
        atomic_json(
            self.directory(id) / "state.json", ProcessingJob(job_id=id).model_dump(mode="json")
        )

    def finish(self, result):
        if self.read(result.job_id).status != "processing":
            return False
        atomic_json(
            self.directory(result.job_id) / "state.json",
            result.model_dump(mode="json", exclude_none=True),
        )
        return True

    def close(self):
        self.lock.close()


async def child(args, timeout):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "forte.worker",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await process.wait()
        raise
    if process.returncode:
        raise ValueError("Worker failed")
    return stdout


async def probe(path: Path):
    return json.loads(await child(["--probe", str(path)], 10))


async def run_worker(directory, id, deadline, settings, *, reasoning=False):
    extra = [
        "--model-revision",
        settings.model_revision,
        "--max-context-tokens",
        str(settings.max_context_tokens),
    ]
    if reasoning:
        configuration = settings.reasoning_config
        if isinstance(configuration, dict):
            from forte.reasoning_pipeline import load_reasoning_config

            # Validation supplies defaults; do not mutate the caller's dictionary
            # while freezing the exact worker request into this private job.
            snapshot_settings = copy.copy(settings)
            snapshot_settings.reasoning_config = copy.deepcopy(configuration)
            validated = load_reasoning_config(snapshot_settings)
            immutable = directory / "immutable"
            immutable.mkdir(mode=0o700)
            configuration = immutable / "request-config.json"
            atomic_json(configuration, validated)
            configuration.chmod(0o400)
        if not isinstance(configuration, Path):
            raise ValueError("A persisted reasoning configuration is required")
        extra += ["--reasoning-config", str(configuration)]
    await child(
        [
            "--job",
            str(directory),
            "--job-id",
            str(id),
            "--deadline",
            str(deadline),
            "--model-url",
            settings.model_url,
            "--model",
            settings.model_name,
            *extra,
        ],
        max(0.001, deadline - time.monotonic()),
    )
    return RESPONSE.validate_json((directory / "worker-result.json").read_text())
