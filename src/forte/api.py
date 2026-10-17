"""Exact asynchronous jury API; one process, private files, no external inference."""

import asyncio
import hmac
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartException, MultiPartParser

from forte.contracts import AcceptedJob
from forte.inference import LocalVLM
from forte.jobs import JobStore, failure, probe, run_worker
from forte.settings import Settings


class Problem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def error_response(status, code, message):
    headers = {"Retry-After": "5"} if status in {429, 503} else None
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status, headers=headers
    )


class KeyAuth:
    def __init__(self, app, key):
        self.app, self.key = app, key.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            values = [v for k, v in scope["headers"] if k.lower() == b"x-api-key"]
            if len(values) != 1 or not hmac.compare_digest(values[0], self.key):
                response = error_response(401, "unauthorized", "Missing or invalid API key.")
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


class UploadLimit(MultiPartException):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


async def upload_stream(request, settings):
    deadline = time.monotonic() + settings.upload_timeout
    size = 0
    iterator = request.stream().__aiter__()
    while True:
        try:
            data = await asyncio.wait_for(anext(iterator), max(0.001, deadline - time.monotonic()))
        except StopAsyncIteration:
            return
        except TimeoutError as exc:
            raise UploadLimit(408, "upload_timeout", "Upload exceeded the time limit.") from exc
        size += len(data)
        if size > settings.upload_max_bytes:
            raise UploadLimit(413, "upload_too_large", "Upload exceeds the size limit.")
        yield data


def create_app(settings: Settings, runner=None, ready=None):
    backend = LocalVLM(settings.model_url, settings.model_name)
    ready = ready or backend.ready
    tasks = set()
    admitted = 0
    lock = asyncio.Lock()
    store = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal store
        store = JobStore(settings.private_root)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            store.close()
            backend.client.close()

    app = FastAPI(title="ForteBank video review", lifespan=lifespan)
    app.add_middleware(KeyAuth, key=settings.api_key)

    @app.exception_handler(Problem)
    async def problem(request, exc):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        return error_response(422, "invalid_request", "Invalid request fields or job ID.")

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness():
        if not await asyncio.to_thread(ready):
            raise Problem(503, "model_not_ready", "The local model is not ready.")
        return {"status": "ready"}

    async def process(id, deadline):
        nonlocal admitted
        try:
            remaining = max(0.001, deadline - time.monotonic())
            operation = (
                runner(store.directory(id), id, deadline)
                if runner
                else run_worker(store.directory(id), id, deadline, settings)
            )
            result = await asyncio.wait_for(operation, remaining)
            if time.monotonic() > deadline:
                store.finish(failure(id, "processing_timeout"))
                return
            if result.job_id != id:
                raise ValueError("Job ID mismatch")
            store.finish(result)
        except TimeoutError:
            store.finish(failure(id, "processing_timeout"))
        except asyncio.CancelledError:
            store.finish(failure(id, "interrupted"))
            raise
        except Exception:
            store.finish(failure(id, "analysis_failed"))
        finally:
            async with lock:
                admitted -= 1

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: UUID):
        try:
            return store.read(job_id).model_dump(mode="json", exclude_none=True)
        except FileNotFoundError as exc:
            raise Problem(404, "job_not_found", "Unknown or expired job.") from exc

    @app.post("/api/v1/analyze", status_code=202)
    async def analyze(request: Request):
        nonlocal admitted
        started = time.monotonic()
        async with lock:
            if admitted >= settings.max_admitted:
                raise Problem(429, "capacity_full", "Two jobs are already admitted.")
            admitted += 1
        queued, form = False, None
        id = uuid4()
        directory = store.directory(id)
        try:
            if not await asyncio.to_thread(ready):
                raise Problem(503, "model_not_ready", "The local model is not ready.")
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError as exc:
                raise Problem(422, "invalid_request", "Invalid content length.") from exc
            if length < 0 or length > settings.upload_max_bytes:
                raise Problem(413, "upload_too_large", "Upload exceeds the size limit.")
            parser = MultiPartParser(
                request.headers,
                upload_stream(request, settings),
                max_files=1,
                max_fields=0,
                max_part_size=65536,
            )
            try:
                form = await parser.parse()
            except BaseException:
                for temporary in parser._files_to_close_on_error:
                    temporary.close()
                raise
            from starlette.datastructures import UploadFile

            items = list(form.multi_items())
            if len(items) != 1 or items[0][0] != "file" or not isinstance(items[0][1], UploadFile):
                raise Problem(422, "invalid_file_field", "Exactly one file field is required.")
            file = items[0][1]
            if not file.filename or Path(file.filename).suffix.lower() != ".mov":
                raise Problem(415, "unsupported_format", "Upload a MOV video.")
            directory.mkdir(mode=0o700)
            target = directory / "input.mov"
            target.touch(mode=0o600)
            with target.open("wb") as out:
                while data := await file.read(1024 * 1024):
                    await asyncio.to_thread(out.write, data)
            target.chmod(0o400)
            try:
                info = await probe(target)
                if "error" in info:
                    raise Problem(
                        info["error"]["status"],
                        "invalid_video",
                        "Video format or constraints are invalid.",
                    )
            except (ValueError, TimeoutError) as exc:
                raise Problem(415, "invalid_video", "Unsupported or corrupt video.") from exc
            store.create(id)
            task = asyncio.create_task(process(id, started + settings.job_timeout))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            queued = True
            return JSONResponse(
                AcceptedJob(job_id=id).model_dump(mode="json"),
                status_code=202,
                headers={"Location": f"/api/v1/jobs/{id}"},
            )
        except UploadLimit as exc:
            raise Problem(exc.status, exc.code, exc.message) from exc
        except MultiPartException as exc:
            raise Problem(
                422, "invalid_multipart", "One multipart file field is required."
            ) from exc
        finally:
            if form is not None:
                await form.close()
            if not queued:
                if directory.exists():
                    (directory / "input.mov").unlink(missing_ok=True)
                    directory.rmdir()
                async with lock:
                    admitted -= 1

    contract = Path(__file__).resolve().parents[2] / "contracts/api-contract.json"
    if contract.exists():
        app.openapi = lambda: json.loads(contract.read_text())
    else:
        from importlib.resources import files

        app.openapi = lambda: json.loads(
            files("forte").joinpath("data/api-contract.json").read_text()
        )
    return app


def create_default_app():
    return create_app(Settings.from_env())
