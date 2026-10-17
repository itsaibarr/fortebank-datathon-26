# Observed application contract

Initial observations on **2026-10-17, approximately 22:50–22:55 UTC** used read-only inspection
of Agent A's `/Users/itsaibarr/conductor/repos/fortebank-datathon-26` checkout.
Its branch was `codex/frozen-local-reasoning`, HEAD
`7d9a1ca2ffda93f6c2dde4eaf8a5ca4c7d247eeb`. The v2 implementation, model
configuration, frontend and Docker changes were **uncommitted at that time**.
That original HEAD alone does not contain the inspected application.

Agent A subsequently supplied stable checkpoint
**`111234c885f0a23d323fe72a81450dfca5aa7e60`**, incorporated into the deployment
worktree through an isolated fast-forward. Its authoritative
[`contracts/frozen-runtime-manifest-v1.json`](../../contracts/frozen-runtime-manifest-v1.json)
uses schema **`forte.integration/1`**, release
`frozen-local-reasoning-20261018-1`. This is a source/runtime handoff, not a
portable installation acceptance receipt. Its application image exists as local
ID `sha256:ee82962c4ee4d9026ef499a0854bcb485c94a18db97e07719800ca6dfe4276dd`;
no registry digest or publication was supplied. The handoff explicitly denies
runtime-attach authorization and grants no restart, ingress, GPU window or new
spending. Recheck image availability and acceptance prerequisites before activation.

The deployment branch is `codex/deployment-private-cli`, based on the same full
original commit. This document records observations and requested interfaces; it does not
modify the canonical schemas, core API, model settings or UI.

The stable handoff authorizes only `single_reviewer_private_only` operation,
reports shared-key holders can read all jobs in the service root, and prohibits
multi-user private uploads and public browser uploads. It reports no secure
session gateway or principal ownership implementation. Browser/private-install
and external end-to-end acceptance remain incomplete. Its reported 201 Python
tests, synthetic browser workflow, 161.95-second real **partial** API rehearsal,
and one validated but semantically unreviewed legal replay assessment establish
their named scopes only. Final image cold start and concurrent real jobs remain
pending in that manifest.

## Contract fingerprints

These hashes identify inspected bytes, not an approved release:

| File in Agent A's checkout | SHA256 |
| --- | --- |
| `contracts/api-contract.json` (v1, 1.0.0) | `2f07ca38a89320a97edc1f18cf1401462ce89f6912698245bac4f67bd3cacc05` |
| `contracts/reasoning-api-contract.json` (v2, 2.0.0) | `26ef3e7f80997e99be2c74c34a0637ce8ad249075b6034667eb3979ac602684c` |
| `configs/frozen-inference.json` | `c516e8c32a1fa05036f729cb6849cc86d2a570f9cf89632243887e03654d03e4` |
| `legal/2026-10-17/manifest.json` | `2d91e147f55c9bee54bae22e64126ed0fd00d35bbac3715aeda96075862400a1` |
| `legal/rule-cards.json` | `71e1d6aaa3d3bb77fac9fb5291fd66023cae24562c3d83628fff907c0e06e804` |

The inspected generated v2 OpenAPI has incomplete upload and response-media
schemas. In particular, its upload operation does not declare the multipart
request body. The implementation and v1 upload contract establish the actual
`file` field below. Do not generate an upload client from that incomplete
operation without Agent A supplying the missing schema.

## Routes, transport and result semantics

All `/api/` requests require exactly one `X-API-Key` header. The current middleware
compares it against one shared ASCII service secret of at least sixteen
characters. No per-user session or ownership enforcement was observed.

| Operation | Observed interface |
| --- | --- |
| Legacy upload | `POST /api/v1/analyze`, multipart field `file`; 202 `{ "job_id": "<uuid>" }` and `Location` |
| Legacy poll/result | `GET /api/v1/jobs/{job_id}`; `processing`, `done` or `failed` |
| Reasoning upload used by UI | `POST /api/v2/analyze`; same file/admission rules; 202 and versioned `Location` |
| Reasoning poll/result | `GET /api/v2/jobs/{job_id}`; same execution statuses; `done` includes `api_version: 2` and `result` |
| Original MOV | `GET /api/v2/jobs/{job_id}/source`; only after a completed v2 result; source hash checked; `video/quicktime`, `Cache-Control: no-store` |
| Source evidence JPEG | `GET /api/v2/jobs/{job_id}/evidence/{frame_id}`; completed result allowlist, safe path and image hash checked; `image/jpeg`, `no-store` |
| Correction history | `GET /api/v2/jobs/{job_id}/corrections`; immutable revision list |
| Append correction | `POST /api/v2/jobs/{job_id}/corrections`; 201; source digest, parent revision, scope, target, reviewer and change; conflicts 409 |
| Reasoning schema | Authenticated `GET /api/v2/openapi.json` |
| Liveness | Unauthenticated `GET /health/live`; 200 `{ "status": "ok" }` when API is running |
| Model readiness | Unauthenticated `GET /health/ready`; 200 `{ "status": "ready" }` or 503 `model_not_ready` |
| Static product | `/`, through `FORTE_FRONTEND_ROOT`; exported Next.js assets served by FastAPI on the same origin |

UUID job namespaces are version-separated. A v2 result cannot be read through v1
and converted into a binary verdict. POST is not idempotent: never automatically
retry a submission whose response was lost. Polling is safe to repeat.

V1 keeps `no_violation|violation` and the original evidence schema. V2 preserves
`supported_violation`, `no_violation_observed`, `insufficient_evidence` and
`not_applicable` under `result.assessment`. A `done` job can have
`result.execution.status: partial`. Clients must retain unfamiliar additive
fields and expose uncertainty; a failed, partial or unfamiliar assessment is
never a clean negative. Core semantics and legal interpretation belong to
Agent A.

Upload is one `.mov` filename with actual bytes/container validation, no extra
multipart fields, duration `(0, 180]` seconds, dimensions at most 4,096 on either
axis and 8.4 million pixels. The **entire multipart body** is capped at
268,435,456 bytes; file bytes must leave room for multipart framing. Upload body
time is thirty seconds. The accepted job deadline is 270 seconds from upload
start; two admitted jobs maximum, no unbounded queue. A slow external connection
can exceed the upload deadline even for a valid file. No measured public-upload
capacity or under-300-second whole-workflow guarantee is established.

Observed errors include 401 authentication, 408 upload timeout, 413 body size,
415 invalid format/container, 422 fields/video bounds, 429 capacity with
`Retry-After: 5`, 503 unavailable model/configuration, 404 unknown/version-mismatch
job, and 409 unavailable result, integrity or correction conflict. Failed jobs
carry an error and no fabricated verdict. Admission checks model health before
consuming the uploaded recording.

## Runtime and resources

The candidate application container owns the VLM and one API process. Internal
ports are `127.0.0.1:8001` for vLLM and `8000` for FastAPI. An API worker is a
bounded subprocess, not a separate queue service. There is no required Redis,
database or hosted inference service. Exactly one API process may own a job root;
its filesystem lock rejects a duplicate owner. On restart, previously processing
jobs become failed/interrupted; completed results and correction files persist.

The inspected entrypoint verifies local model assets, starts the model, runs a
synthetic multimodal warmup, then starts `forte serve --host 0.0.0.0 --port 8000`.
`LocalVLM.ready()` itself checks engine health, served model name/revision and
the 27B profile's local snapshot metadata; it does **not** execute that warmup or
validate every retrieval/tracking resource. Starting `forte serve` directly
bypasses the entrypoint warmup. Readiness therefore needs both an immutable
entrypoint/warmup receipt and HTTP checks, plus a bounded actual workload receipt
for release acceptance.

| Candidate frozen27b setting | Observed value |
| --- | --- |
| Model | `Qwen/Qwen3.8-27B` |
| Revision | `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` |
| Architecture | `Qwen3_5ForConditionalGeneration`, native vision configuration |
| Precision/training | BF16, no quantization, no adapters, frozen weights |
| Model-manifest SHA256 reported by A | `d6cf043a326f8cb5b1f6e31ef37c4d650f6fda342b262029c30968174431459b` |
| Base engine image | `vllm/vllm-openai@sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b` |
| Serving bounds | 16,384 context tokens, one active model sequence, sixteen images/call, processor max 196,608 pixels, GPU allocation 0.90, eager mode |
| API admission | Two accepted jobs; this is not a two-job latency measurement |
| Tracking | Pinned YOLOX-s ONNX, ByteTrack and frozen OSNet export; actual detector/ReID files and manifest required |
| Legal resources | Local `legal/2026-10-17`, official-source-only snapshots and local rule cards; no online legal lookup during a case |

The earlier `baseline8b` is an explicitly selected comparison profile with its
own pinned snapshot, 8,192-token context and two model sequences. It is not an
automatic failure fallback and must not be loaded alongside Agent A's active
27B service by an attach deployment. Do not substitute model names, quantization,
trackers or legal rules in packaging.

Required configuration is `FORTE_API_KEY_FILE`, `FORTE_PRIVATE_ROOT`,
`FORTE_MODEL_PATH`, `FORTE_MODEL_PROFILE`, `FORTE_MODEL_NAME`,
`FORTE_MODEL_REVISION`, `FORTE_MAX_CONTEXT_TOKENS`, `FORTE_REASONING_CONFIG`,
`FORTE_MODEL_URL` and optional `FORTE_FRONTEND_ROOT`, according to whether the
entrypoint or existing owned API supplies each value. The VLM adapter accepts
only a plain HTTP loopback origin, without credentials/query/fragment. Serving
commands and flags stay in the core image; the deployment layer consumes them.

Public assets are read-only mounts. Case media, derivatives, timelines,
corrections and job state live in the private job root. No cleanup/TTL, backup
expiry, per-user quota or first-administrator account mechanism was observed.
Accordingly, current retention is **until the administrator explicitly removes
the installation's private data and any backups**. Do not display an invented
automatic deletion period. Uploads are not used for training in this phase.

The legal corpus manifest identifies `corpus_sha256`
`856f66bc541f92a7c3b0316d43ce9e2664cef321e6db63fc83396007ee561462`, three
scoped acts and 272 main-clause records. Twelve cards are drafts; this is neither
all Kazakhstan law nor confirmation of recording-date applicability.

## Required integration changes: pending Agent A ownership

1. The stable committed core above is supplied. Still required: a distributable
   immutable application image, completed v2
   contract including upload/error/media/range behavior, actual effective resource
   configuration and hash-pinned resource inventory. Bind the deployment
   verification receipt to those exact bytes and the supported hardware.
2. Supply a server-side browser session/bootstrap contract. Keep the upstream
   service key server-side; do not compile it into static JavaScript or require
   reviewers to share it. A reverse proxy's administrator password is not a
   product account system. Until connected, the gateway's explicit single-admin
   mode is CLI transport only; browser sessions and private multi-user upload
   remain disabled.
3. Propagate a trusted principal from the authenticated session, persist ownership
   at job creation and enforce it **before existence/media disclosure** for every
   poll/result, original, evidence frame, correction, future preview/clip/export,
   and every fresh byte-range request. Strip client-supplied principal headers at
   the trusted boundary; never trust a raw external user header. Assign correction
   attribution from the trusted principal. Define migration behavior for existing
   ownerless jobs; default is administrator-only, not globally readable.
   A concrete optional gateway/ownership proposal against the stable core is in
   [patches/README.md](patches/README.md), with base hashes, a ready-to-review
   unified diff and 31 passing isolated synthetic checks. It has not been applied
   or accepted and does not implement browser sessions.
4. Expose non-case deployment information for the UI: hosted/private label, actual
   processing origin/environment, limits, measured readiness/capacity, real
   retention for originals/derivatives/temp/backups, and no-training policy.
   Required endpoint/schema is a proposal to agree with A, not an invented route
   that this installer calls.
5. Verify authenticated MOV playback and byte ranges with the packaged framework.
   `FileResponse` was observed, but code inspection is not a range/playback test.
   The current UI fetches the complete authenticated MOV to a blob before playback;
   it does not demonstrate authenticated streamed seeking. Preserve source PTS
   and evidence semantics in A's pipeline.

These are scoped core requests and an unapplied patch proposal, not accepted
ownership transfers. This workstream does not edit Agent A's checkout. The shared API key
currently protects service access but any holder can request another known job
ID; obscure UUIDs do not create user isolation.
