# Frozen local participant, timeline and legal inference

The current scope is pretrained inference with frozen weights. It supersedes all
earlier mandatory or optional training work for this implementation: no LoRA,
QLoRA, adapter training, optimizer updates, or dataset-based weight adaptation.
Local participant galleries, prompts, timelines and legal indexes are inference
state. Historical training proposals remain historical documents, not executable
instructions for this scope.

The integration starts from main checkpoint `7d9a1ca` and the separate learning
checkout checkpoint `e7a5bbf`. Useful source-frame, whole-recording and evaluation
ideas were integrated through new modules with separate tests; the learning
branch and its training scaffolding were not merged. Its existing untracked
handoff remains in place. The original 8B detector is retained as a reproducible
comparison and rollback path.

## Component map and verification boundary

| Component | Existing behavior retained | Integrated change | Evidence and remaining work |
| --- | --- | --- | --- |
| Source media | PyAV MOV validation, rotation, normalized original PTS and source JPEG extraction | Full source-frame table, source-to-view transforms, explicit evidence envelopes and content hashes | Synthetic VFR/rotation/mutation tests pass; each real run must retain source receipts |
| Participants | YOLOX-s and ByteTrack proposals; separate immutable human review | Frozen pretrained OSNet features, bounded recording-local ReID, gallery updates, conflict/gap records and comparison interface | Public OSNet export and synthetic parity verified; private continuity gains and ID-switch metrics unmeasured |
| Visual reasoning | Loopback model adapter, structured responses, supplied frame IDs | Overview, overlapping full-duration windows, denser bounded reinspection and final reconciliation; source/participant allowlists and persisted observations | First real bounded rehearsal returned a valid partial result; its timeline budget was exhausted and quality remains unreviewed |
| Legal evidence | Three official acts, 272 main records, BM25 and optional local BGE experiments | Exact official context, recovered temporal notices, version limitations, explicit predicate polarity and four assessment states; reverse scoped-inventory checks | Actual eight-image replay made two 27B calls; one assessment passed structural validation, one was rejected. All findings remain unreviewed and scope incomplete |
| Orchestration | One API process, private atomic job records, two admitted jobs, deadlines | `forte scan` and versioned `/api/v2` execution, legal-call budgets, artifact manifests and source-bound correction lineage | 201 Python tests pass; real partial API rehearsal and source/JPEG integrity checks pass; full UI/concurrency timing remains unverified |
| Product UI | Next.js/TypeScript requirement | User-selected Tailwind, shadcn preset `b3d6mT4h6m` and Lucide under `web/` | Lint, types, static export and synthetic authenticated browser workflow pass; real deployment workflow remains unverified |

The main modules are `frozen_tracking.py`, `timeline.py`, `legal_reasoning.py`,
`reasoning_pipeline.py`, `model_profile.py` and `contracts_v2.py`. The existing
`pipeline.py`, `rules.py` and `contracts/api-contract.json` remain the legacy
comparison path. New modules do not approve existing tracking annotations or
replace human geometry, identity, role or legal review.

## Verified model and runtime checkpoint

The selected checkpoint is **`Qwen/Qwen3.8-27B`**, revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`. Its actual configuration declares
`Qwen3_5ForConditionalGeneration` with a native vision configuration and BF16 text
weights. This identity is established from the pinned local assets rather than
from the informal model name. Eighteen safetensor shards and thirty manifest
entries were verified; the model-manifest SHA256 is
`d6cf043a326f8cb5b1f6e31ef37c4d650f6fda342b262029c30968174431459b`.
There is no quantization or trained adapter in this profile.

At the **22:03 UTC checkpoint on October 17, 2026** (03:03 October 18,
Asia/Almaty), the already-authorized Hyperstack A10080 in Canada was serving the
pinned vLLM 0.31.0 image and reported readiness with about 73,063 MiB of GPU memory
occupied. This was the existing VM, not a new allocation. HTTP readiness and model
loading do not establish a successful visual warmup or a completed private scan.
That initial readiness checkpoint was followed by the attempts below. It was not
itself a private inference or quality result.

The latest reported credit check was **22:19 UTC**, approximately **$25.9449**,
subject to provider settlement. The original overall authorization remains
**$30**. The same VM's bounded session started at 21:04 UTC; its cleanup deadline
was extended to **23:04 UTC**, with a **$3 session cap** inside the existing
authorization. This is a dated checkpoint, not a live account or resource-status
claim. The resource owner must preserve private results, enforce the earlier
time/spend limit and record actual deletion. Do not infer that a stopped VM stops
billing.

Subsequent runtime checks, still on that same VM, established the following:

- The first real development attempt under the 8,192-token profile failed with
  `visual_context_exceeded` after 33.7 seconds. The measured first prompt was
  14,691 tokens, including 11,619 text tokens. Metadata/context compaction reduced
  it to 9,692 total and 6,620 text tokens, still above 8,192.
- The frozen27b profile was explicitly increased to **16,384 context tokens**.
  The baseline8b profile remains **8,192**. The image budget remains sixteen per
  call; no model weights, quantization or semantic rule criteria were changed.
- Two sixteen-image synthetic visual checks were correct. The recorded input
  count was 3,062 tokens, with call times of 7.33 and 2.01 seconds and about
  73 GiB of reported GPU occupancy. These verify visual/request mechanics only.
- The first real 16K attempt failed with `ReadTimeout` after 85.55 seconds overall.
  Observed generation was about thirteen tokens per second. An intermediate
  640-token visual budget then failed with `model_output_truncated` after
  76.41 seconds overall; its first visual pass took 49.856 seconds, with a
  9,736-token prompt, 640 completion tokens and `finish_reason: length`.
- The current bounded profile permits **1,200 visual output tokens** and a
  **100-second local request timeout**, while retaining sixteen images, about 55%
  of remaining job time for timeline work and two legal calls. Legal requests
  end at the overall deadline minus ten seconds, reserving time for original
  source evidence and finalization. These bounds do not establish full coverage.
- `capacity_limited` explicitly records a pass that omits observations because
  of the output cap. Validated source-bound observations are persisted before a
  crossed stage deadline stops later work. A failed later pass retains earlier
  validated observations with an explicit partial/failed-pass status; its own
  unvalidated answer is excluded. A failure before any valid answer remains a
  failure. Incomplete scheduling and skipped rules never become negative findings.
- The first bounded real API rehearsal returned **`done`**, with execution
  **`partial`** and assessment **`insufficient_evidence`**. Its recorded analysis
  duration was **161.95 seconds**. The timeline budget was exhausted. Original
  source serving was hash-verified, and all returned event markers and JPEGs
  were checked against full original presentation timestamps and exact decoded
  source bytes. Counts, recording identifiers and case-bearing outputs stay in
  the private review package. This establishes partial execution/provenance,
  not semantic correctness, full coverage or full upload-to-UI latency.
- Both initial legal requests were rejected for context size **before model
  generation**. They remain unavailable coverage entries, not evaluated legal
  findings. The legal prompt now supplies only participants referenced by its
  selected observations and at most eight source images, preserving each chosen
  observation's complete supporting/decisive evidence set. Whole observations
  are excluded when their complete set cannot fit; their evidence is not trimmed.
  Exact primary clauses, required parent context and source validity notices
  remain intact. Output instructions require every condition, concise dependency
  reasons and a short explanation.
- The separate actual legal replay then completed **two real 27B calls**, each
  with eight images. The first used 8,819 prompt and 670 completion tokens,
  finished with `stop` in 53.35 seconds, and was rejected by strict application
  validation with `ValueError`. The second used 7,950 prompt and 612 completion
  tokens, finished with `stop` in 45.76 seconds, and produced **one structurally
  accepted, unreviewed assessment**. The legal report correctly remains
  incomplete. These are separate replay timings, not a new full upload-to-UI
  latency result. One valid assessment does not establish legal correctness,
  representative accuracy or complete rule coverage.

The first integrated Docker build failed while pip tried to uninstall the
Debian-managed `pyparsing` package. The Dockerfile now installs application
dependencies into `/opt/forte-app`, an isolated venv with `--system-site-packages`
to retain the bundled model engine. The v3 image build and application import,
static-asset and configuration checks subsequently passed. The latest final image
build has also completed. The final single-image cold-start/entrypoint check is
now running on the same GPU; startup success is not yet established. Production,
concurrency, final private backup and resource cleanup remain pending.
The existing SSH source address also changed during the session. Access was
restored through the existing bootstrap path, then restricted to the verified
current `/32`; the temporary broad ingress rule was removed. No new VM was rented.

The frozen appearance adapter is a real pretrained `osnet_x0_25` export, not a
placeholder embedding generator. Its public/synthetic verification receipt is
[frozen-tracking-public-20261018.json](../.context/verify/frozen-tracking-public-20261018.json).
It verifies loaded feature-body parameters, ONNX/PyTorch parity and execution in
an isolated runtime. It makes no private-data continuity or role-accuracy claim.

## Prepare assets and run locally

Download public code, model assets and official laws before opening private
media. Prepare a hash manifest for the exact model snapshot and the pretrained
ReID ONNX manifest. `forte model-check` verifies local bytes and the multimodal
architecture; it never downloads missing assets:

```sh
forte model-check \
  --root /models/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --profile frozen27b
```

Use [configs/frozen-inference.json](../configs/frozen-inference.json) as the
explicit configuration. Its `/models` and `/legal` paths are container paths;
mount the matching public assets or write a private configuration with the
actual paths. Keep the event calendar date null unless reliable recording or
authorized operation metadata establishes it. The selected bounded configuration
sets `legal_max_calls` to two, leaving most of the twelve scoped cards unevaluated;
the result records those skips. It does not claim complete legal coverage.

After building `web/out` and successfully completing the application image build
on the authorized host, this is an offline rehearsal layout. The image build is
complete, while its final cold-start check is in progress. Replace host paths with existing
authorized mounts. The service key is separate from the provider credential;
never mount the Hyperstack credential into the application.

```sh
docker run --rm --gpus all --network none --ipc=host \
  --name forte-frozen \
  -v /absolute/public/model-assets:/models:ro \
  -v /absolute/checkout/legal:/legal:ro \
  -v /absolute/private/config:/config:ro \
  -v /absolute/private/service-api.key:/run/secrets/forte-api.key:ro \
  -v /absolute/private/development:/private/development:ro \
  -v /absolute/private/jobs:/private/jobs \
  -e FORTE_MODEL_PROFILE=frozen27b \
  -e FORTE_MODEL_PATH=/models/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  -e FORTE_REASONING_CONFIG=/config/frozen-inference.json \
  -e FORTE_API_KEY_FILE=/run/secrets/forte-api.key \
  -e FORTE_PRIVATE_ROOT=/private/jobs \
  -e FORTE_MAX_CONTEXT_TOKENS=16384 \
  forte26:frozen
```

The entrypoint verifies model hashes, sets the served revision from that receipt,
starts the loopback VLM, and runs the synthetic visual warmup before starting the
API. The frozen27b profile uses BF16, one active model sequence, 16,384 tokens and
at most sixteen images per call. The API still admits at most two jobs; one active
GPU sequence is not a two-job latency guarantee. Tokenization is checked before
each call, and context overflow is explicit.

Each persisted run fingerprints nineteen shipped application modules, including
the temporal, legal, media, tracking and API paths. This identifies code bytes;
it does not assert that every optional module ran. Public model assets, legal
snapshots and the effective run configuration have separate fingerprints.

An isolated container has no published external API port. Exercise its loopback
API with a client inside the same container/network namespace, or run the scan
command against its already-warm resident model:

```sh
docker exec forte-frozen forte scan \
  --source /private/development/clipNNN.mov \
  --config /config/frozen-inference.json \
  --private-output /private/jobs/offline-development-scan \
  --model-url http://127.0.0.1:8001 \
  --deadline-seconds 270
```

For human browser access while keeping container outbound networking denied, use
the fixed application-only host loopback bridge in
[offline-api-bridge.md](offline-api-bridge.md). It relays only application port
8000 through the existing authorized container and SSH connection; it does not
expose model port 8001 or grant container egress. Private browser/media review is
for the human; remote browser/screenshot tooling remains prohibited for it.

Only a recording on the development hash/neutral-name allowlist may be used.
Keep the source path and result directory private. The CLI prints only execution
state, assessment, event count and the frozen-weight flag. Detailed predictions,
frames, crops, embeddings, replies and review packets stay under the private
output directory. OS-enforced IPv4 and IPv6 outbound denial is checked before
private inference; an environment variable or an offline model-cache flag does
not substitute for that boundary.

For an API process attached to an already-warm, isolated model, the corresponding
settings are `FORTE_API_KEY_FILE`, `FORTE_PRIVATE_ROOT`, `FORTE_MODEL_URL`,
`FORTE_MODEL_NAME`, `FORTE_MODEL_REVISION`, `FORTE_MAX_CONTEXT_TOKENS`,
`FORTE_REASONING_CONFIG`, and optionally `FORTE_FRONTEND_ROOT`. The model revision
must match the selected frozen configuration. `uv run forte serve` is suitable
for the lightweight host environment only when its model/tracking dependencies
and network isolation are separately satisfied.

## API, review and baseline behavior

`POST /api/v2/analyze` accepts the same authenticated multipart MOV upload as v1.
`GET /api/v2/jobs/{job_id}` keeps execution state (`processing`, `done`, `failed`)
separate from assessment (`supported_violation`, `no_violation_observed`,
`insufficient_evidence`, `not_applicable`). Successful analysis with unresolved
facts is a `done` job with an explicit uncertain assessment. A corrupt source,
unavailable model or failed execution remains an execution error.

The new normative reasoning contract is
[`contracts/reasoning-api-contract.json`](../contracts/reasoning-api-contract.json),
served from authenticated `/api/v2/openapi.json`. The original v1 contract and
its original OpenAPI endpoint remain unchanged.

Authenticated v2 source/evidence routes verify original-media or JPEG hashes
before serving. Correction routes append source-bound, immutable human sidecars
with a current parent revision and the unchanged base-result digest. A correction
in one scope does not approve other scopes. Raw model observations remain
unreviewed. Correction sidecars are preserved across runs, but are **not yet
automatically replayed into subsequent model inference**. Storage/lineage support
does not establish that the model consumed a correction. See
[legal-reasoning.md](legal-reasoning.md) for source policy,
condition polarity and draft-interpretation gates.

The exact v1 OpenAPI schema and legacy detector remain available. Job namespaces
are isolated: a v2 job is not exposed as a v1 binary verdict. There is one selected
resident model per deployment. To reproduce the original **8B model plus legacy
detector**, explicitly select `baseline8b` and its pinned snapshot
`0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`; a frozen27b deployment does not
automatically load a second 8B model when v1 is called.

## Implemented and unresolved

Source-bound participant proposals, whole-recording local model calls, exact law
retrieval, explicit condition evaluation, original evidence export, private
artifact persistence, v2 uncertainty and correction handling are implemented.
Synthetic tests verify enforcement, including v1 regression, authenticated
resources, source mutation, evidence escape attempts and stale correction
parents. The latest reported Python suite has **201 passing tests**, with four
existing warnings. Frontend
lint, TypeScript and static export pass. Synthetic browser QA exercised upload,
polling, authenticated source/JPEG blobs, in-memory-only key handling, event
seeking, participant overlays, correction chains and a failed same-file retry.
The 390-pixel viewport had no horizontal overflow or console errors. Receipt:
[frozen-timeline-ui-synthetic.json](../.context/verify/frozen-timeline-ui-synthetic.json).
These checks do not measure recognition or legal accuracy.

The private inventory accounts for forty canonical recordings: thirty-one
development and nine reserved. Session, recording-date and camera-continuity
metadata remain unconfirmed; filenames and PTS do not supply them. Reserved and
jury media remain excluded, and no reserved media was opened in this work.
Missing human role/geometry/action review, approved legal interpretations and
recording-date applicability limit quality conclusions; they do not prevent the
software's first frozen development inference.

Before quality or submission claims, complete the final cold-start deployment
check and broader legal validation, review original evidence locally, compare
matched 8B/tracking variants, measure
the full upload-to-UI workflow and one/two-job concurrency, and record failures,
coverage gaps, actual memory/spend and resource cleanup. No precision/recall,
participant-continuity improvement, legal-match percentage, or under-300-second
workflow claim follows from the integration tests alone.
