# Run the backend and verify a private result

The API and temporal pipeline are implemented. Local tests use synthetic MOV files and injected observations. A synthetic GPU check verified the exact Qwen checkpoint. Full development-video accuracy and latency still require a real API rehearsal.

## A job follows one path

1. Check `X-API-Key`, admission capacity and resident-model readiness before reading the body.
2. Accept exactly one multipart field named `file`, with a `.mov` filename. Limit the entire body to 256 MiB and upload to 30 seconds. Probe one video stream, at most 180 seconds and 8.4 million pixels. Audio is ignored.
3. Save the source privately and return HTTP 202 with `job_id`. GET `/api/v1/jobs/{job_id}` reads its atomic state.
4. A separate worker decodes the clip and records each source presentation timestamp. It samples overlapping 16-second windows with a 12-second stride at roughly one frame per second, up to 16 images per call.
5. The loopback Qwen3-VL-8B model returns candidate events as supplied frame IDs. An 8-second window around each candidate is inspected at two frames per second. A separate model call checks the proposed evidence and every public-rule prerequisite.
6. Unsupported candidates are discarded. Unresolved visibility cannot silently become a clean negative. A supported event uses 1–3 JPEGs re-extracted from the unchanged original source, with actual normalized source timestamps.
7. The application adds the exact catalog citation and cautious wording. It validates the final JSON and atomically changes the state to `done` or `failed`. The deadline is 270 seconds from upload start; terminal states cannot be overwritten.

Two requests can be admitted at once. Additional requests receive HTTP 429 with `Retry-After: 5`. A service restart fails interrupted jobs. There is one API process, one resident model and filesystem state. There is no database or separate queue service.

## Start the pinned GPU image

Build `Dockerfile` on the authorized x86_64 GPU host. Its base image pins vLLM 0.31.0 by digest. Download `Qwen/Qwen3-VL-8B-Instruct` revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` into a private host cache first. Keep the model cache read-only during inference.

Set `FORTE_MODEL_PATH` to that snapshot inside the container, `FORTE_API_KEY_FILE` to a mounted private service key and `FORTE_PRIVATE_ROOT` to a private writable job directory. The service key is separate from the Hyperstack credential. Never mount the provider credential into the application.

The entrypoint runs the model on `127.0.0.1:8001` and the API on port 8000. It enables BF16, 8,192 tokens, two active sequences, at most 16 images and eager execution. Public downloads require networking. The rehearsal container uses `--network none` after those downloads, and its HTTP client runs with `docker exec` inside the same network namespace. This is an offline verification deployment, not the final public HTTPS deployment.

For local API development with an already running loopback model:

```bash
FORTE_API_KEY_FILE=/absolute/private/service-api.key \
FORTE_PRIVATE_ROOT=/absolute/private/jobs \
uv run forte serve --host 127.0.0.1 --port 8000
```

`GET /health/live` checks the process. `GET /health/ready` checks model health and the pinned snapshot identity. POST returns 503 until the model is ready. The API never downloads or cold-loads weights during a job.

## Rehearse without exposing private content

Run the included client against loopback or a controlled SSH tunnel:

```bash
uv run python scripts/check_api.py \
  --key-file /absolute/private/service-api.key \
  --file /absolute/private/development.mov \
  --output /absolute/private/rehearsal
```

The client checks unauthenticated rejection, POST, polling, the result schema, completion time and exact source-JPEG provenance. It saves sensitive JSON and evidence locally. Its terminal output contains only status, verdict, event count, elapsed time and failure code. A correct schema does not prove the model's visible-action interpretation; a local human must review the saved evidence and descriptions.

Each job's private `metrics.json` stores call timing, token usage, frame counts and sanitized error classes. Do not paste `result.json`, scene descriptions, evidence or model error logs into external AI tools. Keep original footage, annotations, outputs and adapters out of Git.

## Known limits before quality evaluation

The provisional catalog contains three conservative predicates under National Bank resolution 231, points 20 and 22. It cannot claim complete coverage of every cash-discipline event. No categories or intervals were supplied by the dataset, and no local semantic annotation review has been completed. The proposed development/holdout split still needs session-continuity review. No adapter is enabled. Cross-camera accuracy, full-length and concurrent-job latency remain unmeasured.
