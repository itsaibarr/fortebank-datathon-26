# ForteBank Datathon 26 product specification

User approved local project setup on 17 October 2026 and subsequently provided a Hyperstack API credential with explicit permission to configure the GPU environment within $30. The user handles the top-up. The agent may provision and manage this project's resources after verifying credit, rates and cleanup controls, without asking again for the same authorization. It may not initiate payments, enable auto-top-up or publish private data. The supplied case, including all 35 FAQ answers, was reread and reconciled before setup.

The latest implementation scope is **pretrained local inference with frozen weights**. This supersedes earlier mandatory and optional training proposals for the current work. No fine-tuning, LoRA, QLoRA, adapter training, optimizer update or dataset-based weight adaptation is permitted. Prompt, participant-gallery, timeline and legal-index updates are inference state. Preserve the existing baseline and human corrections while implementing the integrated path; see `docs/frozen-inference.md` for its current verification boundary.

Historical checkpoint `131463f`: 320 Python tests passed, one optional Docker check was skipped and four existing warnings remained; frontend lint/types/static export and synthetic authenticated browser QA passed. The first real bounded API rehearsal returned done/partial/insufficient_evidence with source/PTS/returned-JPEG checks passing. Separate actual legal replay structurally accepted one of two unreviewed outputs; coverage remains incomplete. Final-image cold start passed at October 17 22:54:31 UTC, with model hashes, actual visual warmups, health and UI verified. The application-only bridge and unauthenticated-API rejection also passed. Two real API jobs completed as partial/insufficient in 257.43s and 258.04s, with a third request rejected with HTTP 429 and source/PTS/all-returned-JPEG/marker checks passing. All inference/application work stopped at 23:00:07 UTC. Base backup/restore and historical private integration artifacts are safe, but the final delta transfer failed and the complete final production delta was not preserved. Limited recovery from hash-verified compressed prefixes is not a complete restore. At 23:07:34 UTC the provider reported zero VMs/volumes, with an observed session credit reduction of about $2.62299 within the $3 cap, subject to settlement. Recognition/legal quality, complete coverage and full remote UI latency remain unestablished.

Observed hardware is A10080, 128GB-class RAM, 28 CPU cores, driver 570.195.03 and host IPC, with reported peak memory about 5.746 GB. Minimum RAM/disk requirements remain unvalidated. Public asset inventory is `contracts/frozen-assets-v1.json`; effective configuration/resource mappings are separate release artifacts.

The historical image and legacy key-only mode are **single-reviewer private only**.
The newer source applies principal ownership at `bdf3173` and integrates a separate
host-loopback browser-session gateway, local account administration and protected
cookie/CSRF UI. See `contracts/browser-session-contract-v1.json` and
`docs/browser-session-plan.md`. Every admission persists its principal; case, source,
evidence, corrections and fresh range requests check that owner, with generic 404
for another owner or ownerless history. The immutable historical runtime manifest
and image digest remain unchanged. New-image/external deployment and publication
acceptance remain separate; synthetic checks cannot approve them.

Installation must use capability-based compatible CUDA-host checks rather than a
named GPU or VM restriction. Allow an explicit local-only bounded qualification
operation with immutable source, image and resources before production acceptance.
It must check actual hashes and visual warmup while retaining network-disabled
private inference. Report measured and unmeasured limits separately. Qualification
must not set release, model-quality, session or publication acceptance flags.

## Inputs and outputs

Use the actual supplied `open.zip`, expected SHA256 `c01ee47563620f9cef14cc42fd23d81f4f58600e5d1eae39d97bb85b57961867`. It contains 42 MOV files and one XLSX; the prior full audit found 40 unique recordings. Keep originals unchanged and all private recordings, annotations, frames, descriptions and derived adapters outside Git. No audio analysis or face identification.

The final service accepts a new video, analyzes visually observable actions and provides a cautious assistance verdict, event types, source timestamps, one to three real JPEGs per event and a visible-action explanation with a relevant public Kazakhstan rule. Never infer hidden accounting facts, intent, identities or unavailable internal rules.

## Fixed public contract

`POST /api/v1/analyze` requires `X-API-Key` and a multipart MOV field named `file`, and returns HTTP 202 with `job_id`. `GET /api/v1/jobs/{job_id}` requires the same header and returns `processing`, `done` or `failed`. Completed results use only `no_violation` or `violation` and the case's fields `job_id`, `status`, `verdict`, `violations`, `type`, `timecode_sec`, `description`, `evidence_frames`, `timestamp_sec`, `image_base64`. Legal document/provision/URL go in `description`.

The normative OpenAPI contract is `contracts/api-contract.json`, copied without schema changes from the approved research. Accept approximately 29 MB case videos within the specified 256 MiB upload and 180-second duration bounds. The case supplies clips of 10 to 145 seconds. Validate actual format, dimensions and duration; an extension alone is insufficient.

The new `/api/v2/analyze` and `/api/v2/jobs/{job_id}` path is separate from that fixed legacy contract. It preserves execution state (`processing`, `done`, `failed`) independently from assessment (`supported_violation`, `no_violation_observed`, `insufficient_evidence`, `not_applicable`). An executed analysis with insufficient evidence is a successful `done` job, not a clean binary negative or an execution failure. Keep source/evidence and correction routes authenticated, source-bound and private. V2 jobs must not be exposed as v1 binary results.

The v2 contract is `contracts/reasoning-api-contract.json`, available at authenticated `/api/v2/openapi.json`. Preserve immutable correction history across runs. Automatic replay of those corrections into later model inference remains an explicit implementation gap; storing a correction does not establish its use as model context.

Target 270 seconds from upload start and verify client completion under 300 seconds. Warm models before admission. Admit at most two jobs and reject overflow; keep polling responsive. Corrupt/unprocessable/timeout jobs fail explicitly. Return verified positive events with a stated visibility limitation if another fragment is unclear. Never treat a skipped or undecoded clip as a clean negative.

## Selected processing architecture

The frozen integration candidate is `Qwen/Qwen3.8-27B` revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, verified locally as `Qwen3_5ForConditionalGeneration` with native vision configuration and BF16 weights. Pin and hash-check complete model, tokenizer, processor and weight-shard assets before serving. No quantization or trained adapter is selected. Retain the reproducible `baseline8b` profile, `Qwen/Qwen3-VL-8B-Instruct` revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, and the original detector for matched comparison and rollback. The earlier `OpenGVLab/InternVL3_5-8B` fallback remains historical contingency, not a promoted current model. Model-specific preprocessing stays behind the local window/request interface.

Use PyAV/FFmpeg for source PTS and rotation. Retain the original coarse/fine baseline. The integrated path adds a recording overview, overlapping 16-second windows at 12-second stride, bounded denser reinspection and final chronological reconciliation. Every supplied image has an ID linked to original PTS; crops retain reversible source/view transforms. Check actual processor counts before each call: frozen27b uses 16,384 context tokens after measured 8K overflow; baseline8b remains 8,192. Retain at most sixteen images. The current bounded profile uses 1,200 visual output tokens, a 100-second local request timeout, approximately 55% of remaining time for timeline work and two legal calls ending at the overall deadline minus ten seconds. Record `capacity_limited` explicitly. Save validated source-bound observations before stopping a crossed stage budget; retain them if a later pass fails, excluding the failed reply. Report incomplete coverage rather than a negative. Model output selects supplied frame and participant IDs; application code derives timestamps and evidence envelopes. Sparse sampling does not establish exact action boundaries or a missing step.

Scan the complete duration, inspect candidates, verify evidence with a separate prompt, merge reports of the same action, and preserve distinct events. Use a reviewed local rule catalog. An omission needs visible transaction context and the full opportunity to perform the required action, with a source-frame boundary timestamp. No fixed-camera-only crop rule or closed set of training labels may silently suppress unseen event types.

Keep anonymous participants recording-local. YOLOX/ByteTrack and frozen pretrained appearance features may propose correspondence, but tracker IDs, reflections, inferred roles, geometry and human facts remain separate origins. Preserve gaps, conflicts, uncertainty and immutable corrections. A person gallery is private inference state, not identity recognition or approved continuity truth.

Use only enacted official RK acts from `adilet.zan.kz` and `nationalbank.kz` as normative authority. Verify source type as well as origin. Local retrieval must retain exact clauses, versions, parent context, temporal notices, exceptions and unavailable cross-references. The three-act, 272-record inventory and twelve draft cards are scoped coverage, not all RK law or approved detectors. Recording-date and effective-edition uncertainty remain explicit; PTS, filenames and current-at-collection flags cannot establish calendar applicability.

Keep each legal prompt bounded to participants referenced by its supplied observations and at most eight images. Select complete observation evidence sets, preserving decisive/support frames; exclude an observation wholesale if its complete evidence cannot fit. Retain exact primary clauses, required parent context and validity notices. Require every condition once, including unknowns, with concise explanations. A pre-generation context rejection is unavailable legal evaluation, not a finding.

Evaluate each candidate through an explicit condition table with `satisfied`, `contradicted` or `unknown`, predicate polarity, support/counterevidence IDs and unresolved dependencies. Application code validates supplied IDs and computes the outcome; model JSON cannot approve itself. Keep interpretation status and human review separate. A draft interpretation may retain a reviewable candidate, but cannot become a validated legal conclusion. Unknown decisive context or incomplete coverage must not become a clean result.

Use one controlled GPU host and one deployable application container with FastAPI and a local vLLM process. Start from vLLM v0.31.0, then verify the pinned image and driver on the actual host. Store atomic filesystem job records; no database, Redis, Celery or vector store. No external AI endpoint receives video, frames, captions or sensitive descriptions. After downloading public weights/dependencies/rules, a complete job must work with outbound Internet blocked.

Persist fingerprints for the nineteen shipped application modules alongside separate public model, law-snapshot and effective-configuration fingerprints. This establishes source-byte provenance, not execution or correctness of every optional path.

## Approved frontend scope

Frontend is Next.js App Router with TypeScript. The user selected Tailwind, shadcn preset `b3d6mT4h6m` and Lucide, satisfying the earlier library-selection gate. Use static export served through FastAPI on the same origin. Browser code calls the existing authenticated API; no private job data is fetched during frontend build. UI implementation is allowed; actual browser/API behavior, accessibility, error states and full workflow timing still require verification.

Final UI requires video upload, processing, explicit execution/assessment state, event intervals and participants, timestamped original evidence, cautious descriptions, condition findings, public-rule links, human correction provenance and useful error states. Preserve legacy binary verdicts only where that contract applies. Accounts, history, batch upload and report export are not case requirements.

## Frozen inference and evaluation

Preserve recording groups and exact duplicate pairs. Resolve or flag the supplied point-annotation conflict in the private duplicate manifest; recording identifiers and exact points do not belong in public status documents. Freeze groups before tuning. Proposed initial development/holdout counts are 31/9, subject to local session-continuity review. Jury videos never enter training or model selection; touch the locked holdout once after freezing choices.

No training or adapter updates are in the current scope. Preserve earlier research and learning-worktree files without executing their training scaffolding. Establish zero-shot frozen predictions first. Any later authorized in-context examples must use development material, represent contrasting cases, and be reported as few-shot inference. Missing human-reviewed positive legal controls, complete actor/action labels or confirmed recording dates limit the metrics and legal conclusions available; they do not prevent implementing or running the frozen development pipeline.

Compare the retained 8B pipeline, frozen 27B integration and selected tracking/ReID variant on matched development inputs and a frozen protocol. Measure recording-level outcomes only to the extent supported by coarse labels; actor/action, localization, category and legal-match metrics require appropriate independent review. Record abstentions, skipped rules, unavailable context, evidence relevance, explanation grounding, applicability, cross-angle limitations, full upload-to-UI time, peak VRAM and spend. Model readiness, valid JSON and synthetic tests do not establish recognition quality. Retain the original baseline until measured evidence justifies a new quality claim.

## Hosting and submission gates

Preferred rental is Hyperstack `n3-A100x1`, one A100 PCIe 80 GB. On 17 October 2026 the funded API check verified $1.35/hour compute and $0.006720430/hour public IP. One VM used the compatible Ubuntu R570/CUDA12.8 Docker image 517; the R595 image initially considered is hard-restricted to B300 flavors. The pinned vLLM 0.31.0 container passed BF16 Qwen3-VL-8B offline synthetic checks with CUDA compatibility enabled, then the VM was deleted. The observed account-credit reduction was about $0.23, leaving $29.77 at the post-deletion snapshot. See `.context/verify/gpu-setup.json` for actual limits and receipts. Recheck rates/stock before another allocation. Include additional storage charges if introduced, retain a reserve, establish cleanup before allocation and manage only recorded project resource IDs. Fallback Runpod Secure A100 PCIe 80 GB is advertised at $1.79/hour, but the supplied key authorizes Hyperstack access only. Actual development-video API calls and source-JPEG checks have run; exploratory detection quality fails acceptance. See `docs/development-rehearsal.md` for timings, run scope and remaining checks. No training has run. Existing older H100 budgets are superseded.

The user confirmed on 17 October 2026 that organizers allow development videos from open.zip on our dedicated Hyperstack VM in Canada. Inference executes inside our controlled service, never a third-party AI API. Keep recordings and sensitive outputs private and out of Git/chat. Jury and reserved recordings remain excluded from tuning and model selection; no weight updates are permitted in the current scope. Only the development neutral/hash allowlist may be opened.

The frozen integration reused the already-authorized A10080 without another allocation and is now closed. Runtime, observed spend and verified resource deletion are recorded in `docs/frozen-inference.md`; older deletion/credit receipts above refer to earlier sessions. Complete final production-delta preservation failed despite the verified base backup. Do not treat limited recovered files as a complete production archive.

The original remote deletion timer fired October 17 at 23:04:26 UTC after a backup-only extension attempt was not acknowledged because SSH timed out. Provider state was DELETING at 23:04:40, no VM at 23:05:47, and zero VMs/volumes at 23:07:34. Final credit was $24.92737 versus $27.55036 before this session, an observed reduction of about $2.62299 within the $3 session cap/original $30 authorization, subject to settlement. The public preservation receipt is `.context/verify/frozen-backup-preservation-20261018.json`; local validation found no completed production result record. Future human access may use the application-port-only loopback bridge in `docs/offline-api-bridge.md`; it must not grant container egress or expose model port 8001. Do not inspect private footage through remote browser or screenshot tools.

Before submission provide public HTTPS UI/API addresses and jury key, startup/usage instructions, architecture and model list, rule catalog, supported categories, limitations and known errors. Check commercial-use licenses for final weights and dependencies. Use libraries and pretrained models, never a ready-made complete competition solution. Keep data use within the hackathon and document end-of-event cleanup. The case says 12:00 but supplies no date/timezone; confirm the actual organizer deadline.

## Source records

Case SHA256 is `f73a951c87aca9d540076aacc5b4fd8a688810a4ec827b1a382512c770d278a0`. Full research, dataset/decode audit, source ledger and original ADRs are in `/Users/itsaibarr/conductor/repos/aibar/research/fortebank-datathon-26`. The latest Obsidian case matrix and guides are linked from `README.md`. The user approved setup; runtime requirement compliance remains to be demonstrated.
