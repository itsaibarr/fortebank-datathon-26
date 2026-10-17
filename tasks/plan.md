# Implementation plan for ForteBank Datathon 26

## Funded GPU setup completed on 17 October 2026

The user subsequently delegated Hyperstack API management within $30 and confirmed funding. One A10080 passed the pinned BF16 model's offline, structured, 16-image synthetic check and was then deleted. The account snapshot showed approximately $0.23 used and $29.77 remaining. See `docs/gpu-runbook.md` and `.context/verify/gpu-setup.json`. This supersedes earlier statements below that the user must manually provision the instance or that GPU compatibility has never been checked. No competition data was transferred and no training ran. The user has since confirmed organizer permission for development footage on the dedicated Hyperstack VM in Canada. Backend contracts, decoding, inference adapter, temporal pipeline and asynchronous API now pass 26 local tests. Actual development-video GPU evaluation and UI remain pending.

## Approved setup slice on 17 October 2026

The user approved starting local setup. This product repository is now the implementation workspace and its `tasks/todo.md` is the task-status source. Original research remains in `/Users/itsaibarr/conductor/repos/aibar/research/fortebank-datathon-26`. `SPEC.md` and `docs/case-requirements.md` include the reread case and take precedence over older prose where the frontend sequence, mixed-visibility handling or optional training budget changed.

The first bounded slice initializes Harness orientation, a local Python 3.12/uv environment and lockfile, the exact API contract, model/provenance configurations and a tested read-only supplied-archive verification command. It does not implement the full API or inference service. The user will provision the GPU following the Obsidian guide and supply SSH details; do not start paid work on the strength of setup approval alone.

This is the execution handoff for the selected architecture in [architecture.md](/Users/itsaibarr/conductor/repos/aibar/research/fortebank-datathon-26/architecture.md). It describes future implementation; no commands below are represented as having run. Read the dataset audit, API schema and ADRs before coding. The user's frontend instruction supersedes the original plain HTML proposal: use Next.js, start the UI after the processing mechanics work, and ask the user for the exact UI libraries before building it. Estimated effort: first backend draft roughly 6–10 focused person-hours once private GPU/hosting prerequisites are available. Quality work and the UI need separate estimates after baseline measurements and the UI library decision. These are scheduling estimates, not guarantees.

## Work in a separate product checkout and keep Harness in control

Use `/Users/itsaibarr/conductor/repos/fortebank-datathon-26` as the proposed product root if it is free; if it already exists, inspect its Git status and orientation before using it. Do not build the product in the Harness installation or mix it into this research package. Keep this package as the decision source. Use Harness's existing project bootstrap and doc-index conventions in the new checkout, without changing global configuration or overwriting existing project instructions. Read the actual bootstrap script before executing it.

Review this concrete plan before implementation. The research task did not authorize implementation, GPU rental or paid infrastructure. A subsequent implementation instruction can authorize coding; spending still requires an explicit instruction and a stated ceiling. Do not repeatedly ask about settled model/API/topology decisions.

The architecture has internal modules, not separate services:

| Module | Owns | Depends on |
| --- | --- | --- |
| `contracts` | Public and internal schemas, result invariants | — |
| `video` | Validation, decoding, PTS frame registry, sampling, evidence JPEGs | contracts |
| `inference` | Resident local backend, preprocessors, constrained observations | contracts, video |
| `rules` | Verified static public rules, predicates, explanation templates | contracts |
| `pipeline` | Coverage, candidates, fine pass, verification and serialization | video, inference, rules |
| `jobs-api` | Authentication, admission, state, deadlines, endpoints | contracts, pipeline |
| `ui` | Upload, polling and evidence cards | jobs-api |
| `evaluation` | Frozen splits, metrics, latency, local human review rubric | contracts, pipeline |

Dependency order: contracts → video/backend/rules → one real pipeline → jobs/API → measured quality and backend hardening → user UI-library decision → Next.js UI → final browser verification and deployment. Keep a thin API skeleton available early, but do not spend a day building isolated layers without a real video result. Prepare backend code, fixtures and manifests on the Mac before starting the paid GPU clock.

## Selected implementation stack and structure

One Linux/CUDA container, Python 3.12 if compatible with the selected vLLM image, FastAPI/Uvicorn/Pydantic and PyAV/FFmpeg, with one loopback vLLM instance. The frontend is Next.js App Router with TypeScript, built only in the polishing phase. Plan a static export served by FastAPI on the same origin; browser requests call the required FastAPI endpoints. [Next.js documents this export mode](https://nextjs.org/docs/app/guides/static-exports). User-specific job data is fetched at runtime in the browser, never during the frontend build. Keep evidence images local and use no external image optimizer. Component, styling, icon, motion and video-viewer libraries remain undecided until the required user discussion. Start inference from vLLM v0.31.0 and pin the actual working image digest. Use a separate optional training environment.

```text
CLAUDE.md                         Harness project orientation, <=150 lines
SPEC.md                           Approved requirements and package references
pyproject.toml + uv.lock           Frozen application dependencies
Dockerfile                        One reproducible deployable image
configs/baseline.yaml              Model and sampling limits; adapter_path=null
data/rules/                       Public legal snapshots and reviewed catalog
src/forte/contracts.py             Public/internal Pydantic schemas
src/forte/video/                   Decode, frame registry and sampling
src/forte/inference/               Qwen and fallback adapters
src/forte/pipeline.py              Analyze/localize/verify/serialize
src/forte/jobs.py                  Admission, state, deadlines and cleanup
src/forte/api.py                   Exact public endpoints, health/readiness
web/                              Next.js App Router and TypeScript, polishing phase
web/out/                          Exported frontend assets, generated during build
src/forte/eval.py                  Local evaluation CLI
tests/contract/                   Strict API and serialization invariants
tests/video/                      PTS and evidence provenance
tests/jobs/                       Deadline/admission/restart behavior
tests/integration/                Offline and local-GPU end-to-end checks
runs/                             Local private diagnostics, ignored by Git
```

Private datasets, labels, frames, job results, real scene descriptions and competition-derived adapters stay outside Git and remote AI tools. Repository diagnostics can contain aggregated metrics/configuration hashes. The coding agent must not paste private frames or model-generated scene narratives into a remote chat to debug them. A local human reviews semantic facts in the local service; the coding agent can work from aggregate error categories and non-sensitive synthetic fixtures.

## Phase 0 makes the first model call safe and informative

### Task 0 — Reconcile the supplied decisions and case

**Dependency:** none. **Scope:** small, 1–2 orientation/spec files. **Estimate:** 15–30 minutes.

- Acceptance: product orientation points to this package and the exact case schema; ≥8B, no audio/identity/cloud AI, five-minute deadline and jury-data exclusion are explicit.
- Acceptance: current checkout state is recorded; no unrelated work or Harness files are changed.
- Verification: manually reconcile API schema fields and case section 10; regenerate Harness doc index.

### Task 1 — Freeze private recording groups and initial rules

**Dependency:** Task 0. **Scope:** medium, private annotation/split artifacts and public rule configuration. **Estimate:** 1–2 person-hours of local review, which can overlap non-dependent coding.

- Acceptance: exact duplicates grouped; 57/68-second ambiguity adjudicated or excluded from strict temporal supervision; near-duplicate continuity candidates reviewed locally; final groups/split hashes frozen before tuning.
- Acceptance: local reviewer checks all development positive anchors with context and all development negative recordings for misleading patterns; categories remain observable and map to verified catalog provisions. No face recognition or identity labels. A separate curator may inspect reserved content solely for duplicate/session grouping before the split freezes, without sharing category/action findings with prompt or model developers.
- Verification: compare private manifest to 40 recording groups, count any pre-experiment group merges, confirm no group crosses splits; verify rule text/version/exceptions against official public snapshots. The nine-recording holdout remains unused for semantic tuning.

**Required human involvement:** a local reviewer can inspect private content without sending it to remote AI. If review is unavailable, proceed with the baseline's conservative verified rules and explicitly mark class/interval evaluation provisional; do not invent annotations. This does not reopen model or API choices.

### Task 2 — Resolve hosting and run a bounded model smoke test

**Dependency:** Task 0; rented-processor interpretation and spending instruction before any paid/private-hosting action. **Scope:** medium, container/config/smoke script. **Estimate:** 1 hour primary setup allowance.

- Acceptance: exact Qwen checkpoint loads locally in BF16; bounded multi-image input produces frame-ID JSON; no external media fetch or inference call. Freeze model revision, image digest and dependencies.
- Acceptance: record load/download/warm-up times, processor token counts, peak VRAM and host RAM; model readiness prevents analyze before warm-up. One positive/negative local sample is reviewed locally, with sensitive output excluded from remote logs.
- Verification: synthetic two-image smoke first, then permitted development media; one-hour unsuccessful-setup stop condition. A Transformers-only diagnostic or named fallback is allowed within that cap. Do not train.

**Procurement brief, when authorized:** follow [the $30 budget revision](/Users/itsaibarr/conductor/repos/aibar/research/fortebank-datathon-26/budget-followup.md). Primary is Hyperstack on-demand `n3-A100x1`, one A100 PCIe 80 GB, 28 CPUs/120 GB host RAM, 100 GB root/750 GB ephemeral disk, advertised $1.35/hour. Fallback is Runpod Secure A100 PCIe 80 GB at $1.79/hour. Check stock, total checkout/payment, driver/image compatibility, direct TLS/public endpoint and permitted data handling before private uploads. No live allocation or five-minute latency is established. Do not restore the original H100 budget by default.

## Phase 1 delivers a real POST to GET result without UI work

### Task 3 — Define and validate all boundary contracts

**Dependency:** Task 0. **Scope:** small, `contracts.py`, schema fixture and contract tests. **Estimate:** 30–45 minutes.

- Acceptance: exact POST field/header and processing/done/failed response variants match [api-contract.json](../contracts/api-contract.json); no extra public verdict or confidence/legal field.
- Acceptance: internal frame/window/candidate/evidence-check types decouple checkpoints; verdict/list consistency and source-frame references are explicit validators.
- Verification: focused contract tests reject invalid verdicts, empty positive evidence, >3 JPEGs/event, NaN/out-of-range time, invented rule IDs and extra successful-result keys.

### Task 4 — Decode a source video with a trustworthy frame registry

**Dependency:** Task 3. **Scope:** medium, decoder/sampler/evidence modules and video tests. **Estimate:** 1–1.5 hours.

- Acceptance: `.mov` probe/decode is video-only with bounded resources; actual source PTS preserved, rotation handled, frame IDs map to source content; uniform coverage schedule is explicit.
- Acceptance: coarse 16-second/12-stride/1 FPS windows and fine 8-second/2 FPS windows obey frame/token limits; evidence JPEGs re-extract source frames and are never generated.
- Verification: variable-frame-rate and nonzero-start synthetic fixtures prove correct time normalization; first/last coverage, short clips, corrupt input, exact-frame association and 1–3 JPEG serialization are tested. Run the local archive decode manifest as a read-only smoke if permitted.

### Task 5 — Wrap the resident Qwen backend

**Dependency:** Tasks 2, 3, 4. **Scope:** medium, backend interface/Qwen adapter/config and integration smoke. **Estimate:** 1–1.5 hours.

- Acceptance: analyze and verify accept only supplied local frames and fixed schemas; Qwen-specific preprocessing stays behind the interface; no default remote demo URL, label point, filename cue or arbitrary path enters the prompt.
- Acceptance: temperature/seed/output limits recorded; vLLM supports two bounded sequences, frame IDs returned only from the current call; adapter path is null.
- Verification: local GPU smoke tests schema decoding, visual token accounting and repeated calls without reloading. Use current `structured_outputs`, not removed `guided_json` fields. Do not blindly upgrade image-bundled Transformers.

### Task 6 — Produce one grounded local result

**Dependency:** Tasks 1, 4, 5, with provisional conservative rules allowed as described in Task 1. **Scope:** medium, pipeline/rules/serializer and tests. **Estimate:** 1–2 hours.

- Acceptance: full-duration coverage → candidate merge → fine inspection → evidence verification → approved-rule mapping; multiple events retained. Resolve candidates as supported or unsupported from available evidence. A verified positive remains reportable when another fragment is unclear, with the relevant limitation in its description; do not silently return a clean negative for incomplete coverage. Global decode/processing failures remain explicit failures.
- Acceptance: omission events require a visible transaction opportunity and justified boundary time; do not treat an unsampled action as absent. Preserve a cautious path for unseen event types with applicable public rules rather than forcing closed training categories.
- Acceptance: descriptions consist of visible facts, cautious rule relation and uncertainty; actual points and 1–3 source JPEGs pass deterministic validation; unusable/incomplete analysis cannot become a negative verdict.
- Verification: run one development negative and one development positive locally. A local reviewer confirms evidence and explanation; the aggregate result and timings are recorded. Use synthetic fixtures to exercise multi-event and invalid-citation rejection even if the provided annotations are sparse.

### Task 7 — Expose the asynchronous authenticated API

**Dependency:** Tasks 3 and 6. **Scope:** medium, API/jobs/state code and tests. **Estimate:** 1–1.5 hours.

- Acceptance: key and capacity checked before multipart buffering; streamed bounded upload; atomic processing state; 202 job ID; GET reaches done/failed without blocking polls or re-inference.
- Acceptance: two admission slots, no unbounded queue, 270-second total deadline, upload timeout, terminal-state immutability, restart-to-failed and cleanup behavior work.
- Verification: ASGI tests for auth, bounds, corruption, 429/503, timeout and restart; a real multipart curl through the running service completes GET with schema-valid output. No fake cached jury/training-video results.

### Task 8 — Close the backend milestone through the required API

**Dependency:** Task 7. **Scope:** small, local API verification script and recorded acceptance results. **Estimate:** 30–60 minutes.

- Acceptance: real multipart POST with the API key returns a job ID; polling reaches a schema-valid terminal result. A development positive supplies source-timed evidence and a cautious explanation; a negative can return an empty violation list. A local reviewer checks semantic correctness and evidence on permitted local tooling.
- Acceptance: the verification script saves source JPEGs locally from the API's base64 fields and checks timestamps, legal references, authentication failures and processing errors. No frontend implementation or UI library selection in this task.
- Verification: positive and negative development videos traverse POST → GET → decoded evidence without manual inference or cached answers. Record actual upload-to-result duration.

**Milestone 1:** the required API mechanics work with the real selected local model, including timestamps and source-frame evidence. The competition UI remains mandatory and is implemented in Phase 3. Record actual time-to-first-result, remaining errors and a working image/config digest. Neither training nor UI work holds this milestone open.

## Phase 2 improves measured errors

### Task 9 — Run the frozen development evaluation

**Dependency:** Tasks 1 and 8. **Scope:** medium, local evaluation CLI/metrics/rubric/report. **Estimate:** 1–2 hours including inference.

- Acceptance: all 31 initial development groups, or the corrected frozen count, evaluated once for the baseline; TP/FP/FN/TN, coverage, point errors, grounding rubric, timings and memory recorded. Duplicate/ambiguous anchor treatment follows the audit.
- Acceptance: errors are grouped into sampling, visibility, action semantics, transaction context, rule applicability, verification and infrastructure causes. No holdout or jury selection.
- Verification: manually check metric arithmetic on small synthetic cases, then local reviewer adjudicates semantic errors without exposing private content externally. Keep aggregate reports and versioned run manifests.

### Task 10 — Improve sampling, predicates and evidence by ablation

**Dependency:** Task 9. **Scope:** small/medium configuration and prompts, no topology change. **Estimate:** 1–2 hours.

- Acceptance: each change addresses an observed failure, compares the same development groups, and preserves zero-new-negative-FP intent; no blanket “phone/open door/money visible” accusation rule.
- Acceptance: short-event misses motivate denser coverage; unclear action sequences motivate context; evidence selection and rule applicability remain separate from language style.
- Verification: compare one change at a time; retain only measured improvements under time/memory bounds. If using new angle footage, split by its recording source and keep it out of training during a robustness check.

### Task 11 — Run the optional adapter experiment only if its gate opens

**Dependency:** Tasks 1, 8, 9 and repeated semantic errors after Task 10; explicit remaining compute budget. **Scope:** medium, separate training config and evaluation artifacts. **Estimate:** 2–6 GPU-hours plus 1–2 comparison/debugging hours, conditional.

- Acceptance: the [budget follow-up's](/Users/itsaibarr/conductor/repos/aibar/research/fortebank-datathon-26/budget-followup.md) reviewed-label, BF16 language-only LoRA, freeze, save/reload, fixed grouped development validation and spending gates are met. QLoRA is a 48 GB fallback experiment, not the default. No jury or locked-holdout use; actual trainable modules logged.
- Acceptance: the promoted adapter improves the task gate with no false-positive, grounding, angle or latency regression; otherwise discard the experiment and retain the pretrained baseline.
- Verification: short finite-gradient smoke before any full trial; four development block folds only if meaningful; hard time caps stop unsuccessful work. Do not tune on training loss or change API contracts.

If Task 11 is skipped, mark it “not justified by observed errors/budget” and continue. Skipping it is the intended first-version path.

## Phase 3 hardens the mechanics, then builds the agreed Next.js UI

### Task 12 — Prove timing, offline operation and failure handling

**Dependency:** Task 8 and selected quality configuration. **Scope:** medium, integration tests/config and operational runbook. **Estimate:** 1–2 hours.

- Acceptance: warm single-job p95 target ≤150 seconds, two simultaneous admitted jobs each ≤270 seconds and client wall time <300 seconds; cold-start reported separately. No omitted candidates or invalid successful results under load.
- Acceptance: runtime succeeds with outbound Internet blocked and local weights/dependencies/rules; crashes, full disk, GPU OOM, timeout, malformed generated output and interrupted uploads fail safely.
- Verification: five non-jury rehearsal jobs, including longest/busiest permitted clips and two-job concurrency; offline ASGI/CLI smoke inside an isolated container; record allocated/reserved VRAM, CPU, RAM, disk and spend. If capacity fails, profile bounded work or use the documented GPU fallback, not an unbounded queue.

### Task 13 — Freeze the configuration and touch the holdout once

**Dependency:** Tasks 9, 10, optional 11, and 12. **Scope:** small, configuration/run manifest/report. **Estimate:** 30–60 minutes including inference.

- Acceptance: checkpoint/adapter, prompts, rules, thresholds, sampling, software image and split hashes frozen before reading holdout predictions.
- Acceptance: one locked-holdout run reports raw counts, point errors, evidence/class limitations and failures. If it fails a target, report failure honestly; do not keep calling the same nine clips an untouched holdout after retuning.
- Verification: reproduce one run from manifest and reconcile all eligible groups. A revised product can use development evidence, but any reused holdout becomes development and needs a new independent final set.

### Task 14 — Agree the UI libraries, then build the Next.js frontend

**Dependency:** Tasks 8–12 and a stable selected backend configuration. **Scope:** frontend brief, Next.js application, export integration and browser verification. **Estimate:** give a concrete estimate after the user selects the UI libraries.

- Required user discussion before UI implementation: ask for the exact component/styling libraries and any preferred icon, animation and video-viewer packages. Offer a short compatible recommendation set and settle the screen layout and visual reference together. Do not install a default design system or build throwaway UI beforehand.
- Acceptance: record the agreed libraries and versions plus one screen/state specification before coding. Cover API-key entry, MOV upload, processing, final verdict, event timestamps, source JPEGs, cautious descriptions, rule links and failures. Include responsive and keyboard behavior, not only a success screenshot.
- Acceptance: use Next.js App Router and TypeScript. Export client UI assets into the same controlled service; browser calls use the existing FastAPI contract. Keep API keys in page memory, evidence local and build inputs free of private job data.
- Verification: positive and negative development clips traverse browser → POST → GET → visible results. Seek the selected local video to event times; check upload/auth/timeout/failure states and one narrow viewport. Perform private semantic/visual review locally, without sending screenshots to remote AI. Fix against the agreed screen/state specification rather than redesigning repeatedly.

### Task 15 — Publish the controlled service and hand it to the jury

**Dependency:** Tasks 12–14; organizer interpretation resolved before rented hosting of jury data. **Scope:** medium, deployment/runbook/final browser acceptance. **Estimate:** 1–2 hours plus standby.

- Acceptance: stable full HTTPS UI/API URL and port, warmed model, private API key handoff, key on both routes, explicit supported categories/limitations and start/restart instructions; no third-party inference path.
- Acceptance: scratch access, cleanup/retention, TLS, image/license notices, local logs and monitoring reviewed; public proxy intermediaries are not silently introduced.
- Verification: non-jury external upload/poll smoke plus offline check, then leave the exact working instance/config running through the judging window. No package upgrades, Pod resets, training or model swaps during judging.

## Commands the implementation must provide

These commands are intended product interfaces to implement and document; they do not exist in this research package:

```bash
uv sync --frozen
uv run ruff check .
uv run pytest -q tests/contract tests/video tests/jobs
uv run pytest -q tests/integration -m local_gpu
uv run python -m forte.eval --split development --config configs/baseline.yaml --output runs/baseline
docker build -t forte26:local .
```

Document a container entry point that launches/watches the local engine and API together, and a CLI/ASGI smoke that runs in `docker run --network none --gpus all` with local read-only model/media mounts. Do not start a public service with a dummy key or omit TLS from the external submission.

## Final review reconciles artifacts with the actual behavior

Before declaring the implementation ready, reconcile every item in [todo.md](todo.md), all case fields, actual measured capacity/deadlines, citations and offline data flow. Keep fundamental ADRs unchanged unless new measured evidence defeats their acceptance conditions. Update the product orientation with durable decisions and use Octarin if available. The current research package's validation record is a research review, not a claim that the future implementation passed tests.
