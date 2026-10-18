"""Exact asynchronous jury API; one process, private files, no external inference."""

import asyncio
import hashlib
import hmac
import json
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.formparsers import MultiPartException, MultiPartParser

from forte.contracts import AcceptedJob, FailedJob, ProcessingJob
from forte.contracts_v2 import CorrectionRequest, ReasoningDoneJob
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
    def __init__(self, app, key, trusted_gateway_token=None):
        self.app, self.key = app, key.encode("ascii")
        self.trusted_gateway_token = (
            trusted_gateway_token.encode("ascii") if trusted_gateway_token is not None else None
        )

    async def __call__(self, scope, receive, send):
        trusted_api = (
            scope["type"] == "http"
            and scope["path"].startswith("/api/")
            and self.trusted_gateway_token is not None
        )
        response_started = False
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            if self.trusted_gateway_token is not None:
                downstream_send = send

                async def ownership_send(message):
                    nonlocal response_started
                    if message["type"] == "http.response.start":
                        response_started = True
                        message = dict(message)
                        message["headers"] = [
                            (key, value)
                            for key, value in message.get("headers", [])
                            if key.lower() != b"x-forte-ownership-mode"
                        ] + [(b"x-forte-ownership-mode", b"principal-v1")]
                    await downstream_send(message)

                send = ownership_send
            values = [v for k, v in scope["headers"] if k.lower() == b"x-api-key"]
            if len(values) != 1 or not hmac.compare_digest(values[0], self.key):
                response = error_response(401, "unauthorized", "Missing or invalid API key.")
                return await response(scope, receive, send)
            if self.trusted_gateway_token is not None:
                tokens = [v for k, v in scope["headers"] if k.lower() == b"x-forte-gateway-token"]
                principals = [v for k, v in scope["headers"] if k.lower() == b"x-forte-principal"]
                if (
                    len(tokens) != 1
                    or not hmac.compare_digest(tokens[0], self.trusted_gateway_token)
                    or len(principals) != 1
                    or re.fullmatch(rb"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}", principals[0]) is None
                ):
                    response = error_response(401, "unauthorized", "Trusted access is required.")
                    return await response(scope, receive, send)
                scope.setdefault("state", {})["forte_principal"] = principals[0].decode("ascii")
        try:
            await self.app(scope, receive, send)
        except Exception:
            if not trusted_api or response_started:
                raise
            response = error_response(500, "internal_error", "Unable to complete the request.")
            await response(scope, receive, send)


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


def create_app(settings: Settings, runner=None, ready=None, reasoning_runner=None):
    backend = LocalVLM(
        settings.model_url,
        settings.model_name,
        expected_revision=settings.model_revision,
        max_context_tokens=settings.max_context_tokens,
    )
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
    app.add_middleware(
        KeyAuth, key=settings.api_key, trusted_gateway_token=settings.trusted_gateway_token
    )

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

    if settings.trusted_gateway_token is not None:

        @app.get("/api/internal/security", include_in_schema=False)
        async def security_capability():
            return {
                "schema_version": "forte.gateway-security/1",
                "trusted_gateway_required": True,
                "principal_ownership": True,
                "ownerless_jobs_denied": True,
            }

    async def process(id, deadline, version=1):
        nonlocal admitted
        try:
            remaining = max(0.001, deadline - time.monotonic())
            selected_runner = reasoning_runner if version == 2 else runner
            operation = (
                selected_runner(store.directory(id), id, deadline)
                if selected_runner
                else run_worker(store.directory(id), id, deadline, settings, reasoning=version == 2)
            )
            result = await asyncio.wait_for(operation, remaining)
            if time.monotonic() > deadline:
                store.finish(failure(id, "processing_timeout"))
                return
            if result.job_id != id:
                raise ValueError("Job ID mismatch")
            if (version == 2) != isinstance(result, ReasoningDoneJob) and result.status == "done":
                raise ValueError("Wrong API result version")
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
    async def get_job(job_id: UUID, request: Request):
        return read_job(job_id, 1, request).model_dump(mode="json", exclude_none=True)

    def read_job(job_id, version, request):
        try:
            marker = store.directory(job_id) / "request.json"
            try:
                metadata = json.loads(marker.read_text()) if marker.exists() else {"api_version": 1}
            except (OSError, ValueError) as exc:
                if settings.trusted_gateway_token is None:
                    raise
                raise FileNotFoundError from exc
            if settings.trusted_gateway_token is not None:
                principal = getattr(request.state, "forte_principal", None)
                if (
                    not principal
                    or not isinstance(metadata, dict)
                    or metadata.get("owner_principal") != principal
                    or metadata.get("api_version") != version
                ):
                    raise FileNotFoundError
            if metadata["api_version"] != version:
                raise FileNotFoundError
            return store.read(job_id)
        except FileNotFoundError as exc:
            raise Problem(404, "job_not_found", "Unknown or expired job.") from exc

    @app.post("/api/v1/analyze", status_code=202)
    async def analyze(request: Request):
        return await accept_upload(request, 1)

    @app.post("/api/v2/analyze", status_code=202)
    async def analyze_reasoning(request: Request):
        if settings.reasoning_config is None and reasoning_runner is None:
            raise Problem(
                503, "reasoning_not_configured", "The local reasoning pipeline is not configured."
            )
        return await accept_upload(request, 2)

    @app.get(
        "/api/v2/jobs/{job_id}",
        response_model=ProcessingJob | ReasoningDoneJob | FailedJob,
        response_model_exclude_none=True,
    )
    async def get_reasoning_job(job_id: UUID, request: Request):
        return read_job(job_id, 2, request).model_dump(mode="json", exclude_none=True)

    def completed_reasoning(job_id, request):
        result = read_job(job_id, 2, request)
        if not isinstance(result, ReasoningDoneJob):
            raise Problem(409, "result_not_available", "Analysis has not completed.")
        return result.result

    @app.get("/api/v2/jobs/{job_id}/source")
    async def source(job_id: UUID, request: Request):
        from forte.model_profile import hash_file

        result = completed_reasoning(job_id, request)
        root = store.directory(job_id).resolve()
        path = (root / "input.mov").resolve()
        try:
            matches = (
                path.is_relative_to(root)
                and await asyncio.to_thread(hash_file, path) == result["source_sha256"]
            )
        except OSError as exc:
            raise Problem(404, "source_not_found", "Original media is unavailable.") from exc
        if not matches:
            raise Problem(409, "source_changed", "Original media failed integrity verification.")
        return FileResponse(
            path,
            media_type="video/quicktime",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/v2/jobs/{job_id}/evidence/{frame_id}")
    async def evidence(job_id: UUID, frame_id: str, request: Request):
        result = completed_reasoning(job_id, request)
        for event in result.get("events", []):
            for item in event.get("evidence", []):
                if item.get("frame_id") != frame_id:
                    continue
                root = store.directory(job_id).resolve()
                revision = root / result["artifacts"]["revision"]
                path = (revision / item["file"]).resolve()
                if not path.is_relative_to(revision.resolve()) or not path.is_relative_to(root):
                    raise Problem(404, "evidence_not_found", "Unknown source evidence.")
                try:
                    raw = path.read_bytes()
                except OSError as exc:
                    raise Problem(404, "evidence_not_found", "Unknown source evidence.") from exc
                expected = item.get("image_sha256", item.get("sha256"))
                if not expected or hashlib.sha256(raw).hexdigest() != expected:
                    raise Problem(
                        409, "evidence_changed", "Source evidence failed integrity verification."
                    )
                return Response(raw, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
        raise Problem(404, "evidence_not_found", "Unknown source evidence.")

    async def reviewed_snapshot(job_id, result):
        from forte.investigation_report import InvalidCorrectionHistory, correction_snapshot

        try:
            return await asyncio.to_thread(
                correction_snapshot, store.directory(job_id) / "corrections", result
            )
        except InvalidCorrectionHistory as exc:
            raise Problem(
                409, "correction_history_unavailable", "Correction history could not be verified."
            ) from exc

    @app.get("/api/v2/jobs/{job_id}/corrections")
    async def get_corrections(job_id: UUID, request: Request):
        result = completed_reasoning(job_id, request)
        return JSONResponse(
            {"revisions": await reviewed_snapshot(job_id, result)},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/v2/jobs/{job_id}/report")
    async def investigation_report(job_id: UUID, request: Request):
        from forte.investigation_report import build_investigation_report

        result = completed_reasoning(job_id, request)
        revisions = await reviewed_snapshot(job_id, result)
        report = build_investigation_report(job_id, result, revisions)
        return JSONResponse(
            report,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="forte-case-{job_id}.json"',
            },
        )

    @app.post("/api/v2/jobs/{job_id}/corrections", status_code=201)
    async def correct(job_id: UUID, correction: CorrectionRequest, request: Request):
        from forte.timeline import append_correction

        result = completed_reasoning(job_id, request)
        submitted = correction.model_dump(mode="json")
        if settings.trusted_gateway_token is not None:
            submitted["reviewer"] = request.state.forte_principal
        try:
            path = await asyncio.to_thread(
                append_correction,
                store.directory(job_id) / "corrections",
                result,
                submitted,
            )
            return {"revision": path.name, "correction": json.loads(path.read_text())}
        except (ValueError, FileExistsError) as exc:
            raise Problem(
                409, "correction_conflict", "Correction source, target or parent revision changed."
            ) from exc

    async def accept_upload(request: Request, version):
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
            from forte.jobs import atomic_json

            metadata = {"api_version": version}
            if settings.trusted_gateway_token is not None:
                metadata["owner_principal"] = request.state.forte_principal
            atomic_json(directory / "request.json", metadata)
            task = asyncio.create_task(process(id, started + settings.job_timeout, version))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            queued = True
            return JSONResponse(
                AcceptedJob(job_id=id).model_dump(mode="json"),
                status_code=202,
                headers={"Location": f"/api/v{version}/jobs/{id}"},
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

    @app.get("/api/v2/openapi.json", include_in_schema=False)
    async def reasoning_contract():
        schema = get_openapi(
            title="ForteBank versioned reasoning API",
            version="2.0.0",
            routes=[r for r in app.routes if getattr(r, "path", "").startswith("/api/v2/")],
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKey"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
        schema["security"] = [{"ApiKey": []}]
        return schema

    contract = Path(__file__).resolve().parents[2] / "contracts/api-contract.json"
    if contract.exists():
        app.openapi = lambda: json.loads(contract.read_text())
    else:
        from importlib.resources import files

        app.openapi = lambda: json.loads(
            files("forte").joinpath("data/api-contract.json").read_text()
        )
    if settings.frontend_root:
        app.mount("/", StaticFiles(directory=settings.frontend_root, html=True), name="frontend")
    return app


def create_default_app():
    return create_app(Settings.from_env())
