# Observed application and session contracts

The current deployment worktree consumes stable Agent A source
`e55c0773ea74e2745ea33512d19bfaa38b32d7fb`. It includes `bdf3173` principal
ownership, `5be7d78` local browser sessions and `7fa153f` session-aware UI.
The historical frozen runtime manifest and `core-current.candidate.json` still
identify core `111234c` and its deleted VM's local image. They do not describe a
newly built session-aware image or authorize its runtime acceptance.

Authoritative source contracts are
[legacy v1](../../contracts/api-contract.json),
[reasoning v2](../../contracts/reasoning-api-contract.json),
[browser sessions](../../contracts/browser-session-contract-v1.json),
[public assets](../../contracts/frozen-assets-v1.json) and
[effective configuration](../../contracts/frozen-effective-config-v1.json).
The new source-build receipt records the exported commit, per-file hashes,
contract hash and resulting local image. The integrator must accept that exact
release; importing metadata does not approve it.

## Browser access and ownership

The local gateway is launched with
`python3 tools/forte-session/session_gateway.py --config <private-json>` and
listens on configured loopback, default port 18002, behind supplied-certificate
HTTPS ingress. Its credential-free origin is exact. The upstream must be a
literal loopback application endpoint; model port 8001 is rejected.

Local account administration is
`python3 tools/forte-session/session_store.py --db <private-db> add <username>`;
passwords are prompted, not command-line arguments. Disable and password-reset
commands revoke sessions. The account database directory/file modes are 0700 and
0600. There is no default account; the installer invokes this real account
component and preserves existing enabled accounts.

The browser uses `GET /auth/session`, `POST /auth/login` with username/password,
and `POST /auth/logout`. Its opaque cookie is Secure, HttpOnly, SameSite=Strict,
Path=/ with no Domain. Mutations require the exact configured Origin and session
CSRF token; login requires Origin. Session responses provide the principal,
CSRF token and expiry. `GET /deployment.json` supplies `forte.deployment/1`
metadata: private/hosted mode, actual destination, browser upload activation,
readiness, limits, manual retention and training disabled. Service key and
gateway token stay server-side, outside browser code.

Trusted core mode is selected with `FORTE_TRUSTED_GATEWAY_TOKEN_FILE`. Alongside
the service key, the gateway supplies its dedicated token and opaque principal.
The core advertises authenticated `/api/internal/security` capability and
`X-Forte-Ownership-Mode: principal-v1`. The gateway validates this capability on
the same connection used for forwarding and strips client identity credentials.
Browser uploads remain disabled unless explicitly enabled and both capability
and model readiness pass.

The core persists ownership at v1/v2 admission, checks every existing poll,
source, evidence, correction and fresh range request, and attributes corrections
to the trusted principal. Cross-owner and ownerless requests return generic 404.
Legacy shared-key behavior remains unchanged only when no trusted gateway token
is configured; that is an administrative compatibility mode, not browser user
isolation. The earlier optional patch in `patches/` is historical proposal
material, superseded by Agent A's accepted source work.

## Analysis API and transport

The public analysis endpoints remain:

- `POST /api/v1/analyze` and `POST /api/v2/analyze`, multipart field `file`, return
  202 with `job_id` and the versioned polling `Location`.
- `GET /api/v1/jobs/{job_id}` and `GET /api/v2/jobs/{job_id}` return
  `processing|done|failed`. A done v2 response includes `api_version: 2` and
  `result`. Job namespaces are version-separated.
- `GET /api/v2/jobs/{job_id}/source` serves the completed result's original MOV
  with source-hash verification and `video/quicktime`.
- `GET /api/v2/jobs/{job_id}/evidence/{frame_id}` serves only an allowed,
  hash-verified source JPEG. Source/evidence responses are `no-store`.
- `GET` and `POST /api/v2/jobs/{job_id}/corrections` read immutable revisions or
  append a source-bound correction; parent/scope conflicts return 409.
- `GET /api/v2/openapi.json` requires application authorization. The core serves
  the exported Next.js application through `FORTE_FRONTEND_ROOT` on the same
  application origin.

Core `/health/live` returns `{"status":"ok"}`; `/health/ready` returns ready or
503 while the model is unusable. Gateway `/health/live` returns
`{"status":"alive"}`; its readiness additionally requires trusted ownership
capability and core readiness. The installer distinguishes core, access and
external readiness. A live process or local health response alone does not
verify model warmup, all resources, browser isolation or external reachability.

Uploads accept one `.mov` with actual container/content validation, duration
`(0,180]` seconds, maximum dimension 4096 and maximum 8.4 million pixels. The
entire multipart body is limited to 268435456 bytes; the file must leave framing
space. Upload time is bounded to 30 seconds. Two jobs may be admitted; there is
no unbounded queue. The overall job deadline is 270 seconds from upload start.
Observed software states include 408 timeout, 413 body limit, 415 invalid format,
422 bounds/fields, 429 capacity, 503 unavailable model, 404 denied/unknown job and
409 result/integrity/correction conflicts. POST is not idempotent; a lost response
must not trigger an automatic resubmission.

V1 retains its fixed original verdict schema. V2 distinguishes execution from
assessment: `done` may have partial execution, and assessment may be
`supported_violation`, `no_violation_observed`, `insufficient_evidence` or
`not_applicable`. Clients preserve additive fields and uncertainty. Failure,
partial coverage and unfamiliar assessments are never translated into a clean
negative. Model semantics and legal interpretation remain Agent A's domain.

## Runtime and resources

The canonical application image contains one resident VLM and FastAPI process;
its internal model port is 8001 and application port is 8000. Bounded job workers
are subprocesses and job/correction state is filesystem-backed; there is no
external queue service. The local session gateway separately uses its private
SQLite account/session store. Only one API process may own a job root. Restart
marks interrupted processing explicitly; completed cases and corrections persist.

The image entrypoint verifies local assets, starts the pinned model, executes an
actual synthetic visual warmup, then serves the API/UI. Starting the API directly
bypasses that warmup. Qualification checks the actual image and fixed readiness
endpoint within a bounded offline scratch run; it exposes no ingress, stops its
owned core and returns no browser URL. Its success does not promote acceptance.

The selected model remains frozen `Qwen/Qwen3.8-27B`, revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, native
`Qwen3_5ForConditionalGeneration`, BF16 without adapters or weight updates. The
profile retains 16384 context tokens, one active sequence and sixteen images per
call. Tracking uses pinned YOLOX-s/ByteTrack and frozen OSNet resources; retrieval
uses the prepared official local law snapshot and cards. Packaging does not
select a different quantization, tracker or legal interpretation.

The explicit pinned 8B baseline remains available through its own configuration;
it is never a second model started by attach or an automatic fallback. Hardware
checks use the selected CUDA runtime and available device capacity on either a
physical host or VM. The historical A100 observation is not an exact-device
requirement. Weight size alone does not include vision/context/cache overhead;
unknown host minima require measured bounded qualification.

Public resources are mounted read-only. Case media, evidence, timelines,
corrections and job state stay in configured private storage with outbound
networking denied during processing. Retention is manual, including temporary
application data and independently managed backups. Uploads are not training
data. Corpus scope, draft rule cards, recording-date applicability and human
participant/geometry/legal review remain independent of deployment readiness.

## Remaining verification

Source integration and synthetic transport/session tests establish their named
software scopes. A newly built GPU image, clean customer installation, real
case through the new HTTPS/session stack and external hosted workflow are still
required. The deployed stack must recheck two-account denial and later range
requests, source-PTS/evidence links, large upload/capacity/unavailable-model
behavior, offline analysis and persistence. Any future preview/clip/export route
requires its own ownership enforcement and verification. Use only authorized
development footage, with private frames reviewed locally by a human; never use
reserved/jury data or describe operational smoke tests as accuracy results.
