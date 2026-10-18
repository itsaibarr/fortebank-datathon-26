# Accepted architecture: frozen 8B vision with Laya decisions

Decision date: 18 October 2026.

**Target approved by the user: keep the pretrained 8B visual model, put Laya multilingual above its observations, and use deterministic code for rule evaluation, evidence and output. Remove the other architectures from the active codebase.**

This is the sole architecture reference. The local consolidation implements this path; the verification section below distinguishes synthetic software checks from real runtime acceptance. No model weights, private inference, live service changes or deployment were performed during cleanup.

File-level changes are recorded in [docs/cleanup-inventory.md](docs/cleanup-inventory.md).

## 1. The single processing path

1. Accept and validate the video through the existing authenticated asynchronous API.
2. Decode original source timestamps and prepare chronological windows.
3. Retain the existing person detector, tracking and frozen appearance correspondence.
4. Run **Qwen3-VL-8B-Instruct** on each normal window to extract compact visual facts.
5. Retrieve applicable local rule cards and prepare a small fact packet for each condition.
6. Run **Laya multilingual** to propose `satisfied`, `contradicted` or `unknown` for that condition.
7. Apply application-owned evidence checks, temporal predicates, prerequisites and exceptions.
8. Reinspect an ambiguous visual interval with the **same 8B model** when the job budget permits.
9. Export original JPEG evidence and construct the API result and explanation in code.

There is one visual model, one text decision model and one pipeline. There is no 27B fallback, competing model router, training stage or second legal-generation model.

## 2. Model selection

### Visual model

- Model: `Qwen/Qwen3-VL-8B-Instruct`.
- Revision retained from the existing baseline: `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`.
- Architecture: `Qwen3VLForConditionalGeneration`, including its visual encoder.
- Initial precision: frozen BF16, without adapters or weight updates.
- Initial serving engine: the existing pinned local vLLM runtime. Do not change inference frameworks merely for cleanup.
- Input: ordered source images, optional source-bound participant crops, timestamps and bounded participant history.
- Output: visual observations and uncertainty, not final violation claims or legal prose.
- Public weight-file total observed during research: approximately 17.534 decimal GB. This is not the runtime VRAM requirement.

Use the existing pretrained checkpoint. No task-specific tuned 8B checkpoint has been established. Pretraining and previously successful model startup do not establish task accuracy.

### Decision model

- Model: `convaiinnovations/laya-multilingual` by Convai Innovations.
- Public revision observed during research: `1720e3e3357cfe1e281542e223f8273b0890ca34`.
- Architecture: mmBERT-base encoder plus typed decision heads, approximately 322 million parameters.
- Published FP16 weight file: approximately 0.644 decimal GB.
- Deployment target: upstream Laya in a local CPU process, using a pinned compatible runtime. CPU execution precision must be explicit; FP32 execution increases resident tensor memory over the FP16 file size.
- Initial input limit: the checkpoint's shipped 1,024-token decision context, including instructions and options.
- Output: probabilities over three explicitly defined condition states. Application code builds the result schema.

The upstream runtime is pinned to Git commit `d74e8be46ef5241e4ba2b16cd25e896f24f71373` (its source declares version 0.4.11). Actual local checkpoint loading and compatibility remain unverified. The recorded revision is a research metadata observation, not a local installation or compatibility receipt.

Laya accepts text and serialized structured state. It does not accept images or understand arbitrary visual embeddings. Use `choice` with three states; do not turn a binary probability into an invented third-state interpretation.

The `laya-mlx` project is an Apple Silicon runtime port. It is not the selected NVIDIA/Linux deployment runtime. Jev, other VLMs, VideoPrism, cloud models and model-comparison frameworks are outside this target architecture.

Both selected model cards declare Apache-2.0. Preserve applicable notices and the selected runtime/dependency licenses.

## 3. Video and person mechanics

Keep the original MOV unchanged and bind every artifact to its source hash. Decode with PyAV/FFmpeg, preserving source PTS, timebase, orientation and original frame identity. A model chooses supplied IDs; application code resolves their timestamps.

Keep the existing YOLOX-s person detector, ByteTrack and frozen OSNet correspondence code where it serves this path. Existing detector and ReID adapters use CPU ONNX execution. Their outputs are proposals, not approved person identities or roles.

The initial sampling schedule reuses existing baseline settings:

| Setting | Initial value |
| --- | --- |
| Normal window | 16 seconds |
| Window stride | 12 seconds |
| Normal visual sampling | Approximately 1 FPS, at most 16 images |
| Normal image area cap | 196,608 pixels |
| Targeted reinspection | Up to 8 seconds, approximately 2 FPS, at most 16 images |
| Reinspection image area cap | 393,216 pixels |
| Visual model context | 8,192 total prompt and output tokens |
| Starting observation output budget | 768 tokens; a proposed initial setting, not a measured acceptance result |

Actual processor token counts govern admission to each call. Do not copy the old 27B participant dumps, raw-law prompts or 16K assumptions into the 8B path. Include only participants and facts relevant to the current window. Record an overflow rather than silently truncating decisive context.

Inspect the full scheduled duration. One normal visual pass per window is the default. Merge chronology and overlapping observations in code. Do not retain unconditional model overview, fine-verification, legal and reconciliation passes from the old paths.

Allow at most one targeted reinspection per distinct unresolved interval, with a job-wide bound and the original absolute deadline. Deduplicate requests. It may inspect denser source frames, earlier role evidence and relevant crops, without another model.

Complete scheduling means sampled coverage, not continuously verified visibility. Unsampled or occluded actions remain unknown. Output-cap exhaustion, an uncovered window or an unfinished reinspection must remain explicit.

### Roles, continuity and reflections

- Keep anonymous participant IDs recording-local. Do not perform face or personal identification.
- Keep detector boxes, tracker associations, appearance joins, model role hypotheses and human corrections as separate origins.
- Bind a role to a participant and supported interval. Clothing, a fixed image side or proximity cannot establish cashier/customer status.
- Preserve identity gaps, conflicting role assignments, proposed joins and counterevidence.
- A reflection is a view of a person, not an additional physical person. Unknown ownership stays null.
- A reviewed reflection observation does not approve its owner, operational role or track geometry.
- Preserve immutable human revisions and previously cited source frames. Conflicting repeated role words do not approve a join.
- Apply a reviewed correction only within its recorded scope, with explicit provenance. Persisting a correction alone does not prove later inference consumed it.

## 4. Observation interface

Each 8B observation must contain, or explicitly reference:

| Field | Meaning |
| --- | --- |
| Observation ID and source hash | Stable association with this recording and run |
| Actor and recipient IDs | Supplied participant references; empty/null when unresolved |
| Fact kind and value | Concise visible object, action, interaction, role or operational-context observation |
| Start, end and decisive frame IDs | References into the source ledger, not generated timestamps |
| Supporting and contradictory frame IDs | Supplied source evidence for the observation |
| Visibility and unresolved dependencies | Gaps, occlusion, ambiguous ownership or missing context |
| Origin and review state | Model proposal versus separately reviewed fact |

Use concise Russian observation text consistently with the existing task. A structured predicate vocabulary may accompany the text, but it must not silently exclude unfamiliar actions. Preserve an unknown/unclassified concern channel.

Validate all references, bounds and actor associations before accepting a packet. A schema-valid observation remains a model proposal; it does not become human-approved truth or a training target.

Sampled start/end references describe an evidence envelope, not verified exact action onset and offset. Preserve that distinction in storage, the API and the UI.

Do not use a single whole-video caption as the sole observation interface. Retain the event/participant relationships, chronology and counterevidence needed for downstream decisions.

## 5. Local rules and the Laya interface

Keep the verified official-law corpus, source hashes, exact provisions, parent context and version notices. Use local BM25 and exact provision lookup; the current scoped corpus does not require BGE embeddings, a reranker or a vector database.

Rule cards define the applicable operation, duty-holder, factual predicates, polarity, exceptions, metadata dependencies and evidence requirements. Application code owns the card IDs and citation mapping.

For each event/actor/condition combination:

1. Select the relevant rule card using observations and authorized operation metadata.
2. Build a bounded packet of relevant facts, temporal relationships, visibility limits and contradictory evidence.
3. Ask Laya one short three-option question about the condition's positive proposition.
4. Read the proposed condition state and probability distribution; the application adapter attaches the input fact IDs.
5. Associate source evidence through the existing fact records. Do not ask Laya to invent a frame ID or citation.

Definitions are fixed:

- `satisfied`: supplied evidence establishes the proposition.
- `contradicted`: supplied counterevidence establishes that the proposition is false.
- `unknown`: evidence is missing, insufficient, inconsistent or outside the observable scope.

Tokenize with Laya's own tokenizer before prediction. Include options and instructions in the 1,024-token limit. Never permit silent state truncation. If required supporting/counterevidence context cannot fit, return unknown instead of dropping it.

Batch independent condition questions within an explicit memory limit. Do not serialize the entire recording or law corpus into every question. Do not assume multiple questions share a single reusable encoder computation.

Observation-first retrieval prioritizes work, but cannot certify that untriggered duties were checked. Keep a scoped rule inventory with evaluated, inapplicable, unknown and skipped entries. An empty search is not a clean negative or proof that no duty exists.

The existing three-act inventory and twelve draft interpretations are starting material. Their draft state remains draft until properly reviewed. The new model cannot approve a rule card, invent an institution fact, or infer the recording's calendar date from PTS or filenames.

## 6. Deterministic decisions

Laya proposes factual condition states. Code computes the assessment and applies the hard evidence and applicability guards.

- A supported event requires every applicable prerequisite in its required state, all relevant exceptions resolved, a consistent duty-holder and source-bound evidence.
- Known scope or exception facts may establish non-applicability according to the approved rule plan.
- Missing decisive facts, conflicting actors, unavailable metadata, an unapproved interpretation or unknown edition applicability prevent a supported legal conclusion.
- A missing-action claim requires a verified complete visible opportunity. Failure to observe an action in sparse samples does not satisfy this requirement.
- A clean recording-level negative requires adequate evaluated scope and coverage. No candidates, no detections or high Laya negative confidence are insufficient by themselves.
- Keep a separately supported positive when unrelated work is incomplete, with its limitation stated.

Use explicit internal assessments: `supported_violation`, `no_violation_observed`, `insufficient_evidence` and `not_applicable`. Keep execution status separate from assessment and review status.

Laya probabilities are not guaranteed probabilities of correctness. Start with structural unknown/conflict guards. Add only thresholds supported by independent development calibration; do not invent a universal confidence threshold or fit weights. Calibration/threshold changes are selection decisions and must never use jury data.

Reinspection is triggered by a specific missing visual dependency. If the dependency remains unresolved after the bounded 8B recheck, preserve unknown. Missing nonvisual metadata cannot be recovered by another image call.

## 7. Evidence, explanations and API

Export one to three real JPEGs per reported event from the unchanged original source. Preserve the decisive frame and necessary earlier role/context evidence within that budget. If the required evidence cannot fit or be validated, do not fabricate a complete supported result.

Construct explanations with deterministic templates using validated observation fields, explicit limitations and the exact rule-card citation. Do not request another LLM call to write prose. Source origin, semantic relevance and legal applicability are separate checks.

Preserve [contracts/api-contract.json](contracts/api-contract.json):

- `POST /api/v1/analyze`, `X-API-Key`, multipart MOV field `file`, HTTP 202 and `job_id`.
- `GET /api/v1/jobs/{job_id}` with `processing`, `done` or `failed`.
- Completed binary verdicts remain `violation` or `no_violation` with the existing fields.
- Insufficient evidence must not be converted into a successful binary negative.

The current UI consumes richer review resources. Retain required v2/source/evidence/correction routes as adapters over the same pipeline. Multiple output contracts do not require multiple inference implementations.

Keep the approved Next.js/TypeScript interface and Tailwind/shadcn/Lucide stack. Preserve upload, polling, source playback, event markers, evidence, correction provenance and errors. Do not redesign the UI or re-open the library choice during cleanup.

Preserve authentication, existing principal ownership and cookie/CSRF protections wherever the UI uses them. Simplifying deployment must not expose another user's media or reintroduce service keys into browser code.

## 8. Runtime and performance policy

Use one controlled host, one deployable application container, FastAPI, the local 8B vLLM process, a resident CPU Laya process and atomic filesystem job records. No database, queue service, model platform or cloud inference endpoint is required.

Warm and verify both selected models before admitting jobs. Missing or unhealthy Laya is a readiness failure, not permission to silently use the old pipeline or fabricated decisions. One visual inference queue bounds GPU work; two admitted jobs do not imply two simultaneous GPU calls.

Retain initial limits of two admitted jobs, 256 MiB uploads, 180-second validated video duration, a 30-second upload bound and a 270-second absolute job target from upload start. Reserve time for evidence/finalization and verify client completion below 300 seconds when real workload testing is separately authorized.

Private inference requires OS-enforced outbound denial after public assets have been staged. Keep model assets local and immutable. Do not rely only on a prompt, environment variable or HTTP-client setting for isolation.

The intended savings come from removing 27B residency, repeated visual interpretation, generated legal-condition prose and redundant pipeline/framework code. The 8B visual model remains the main GPU component. The decision-layer weight budget is approximately 0.644 GB; the entire system is not a 1–2 GB model or memory system.

No end-to-end speedup, minimum VRAM, CPU Laya latency or accuracy improvement has been measured for this architecture. Published short-text Laya timings on other hardware are not video-processing targets.

Record stage wall times, call counts, image and token counts, queue time, coverage, reinspection reasons, sampled device memory, process RSS, failures and useful completed results. Use a single concise run manifest with model/source/config/law identities. Remove hardcoded assumptions that a release must contain exactly the old nineteen modules.

## 9. What stays and what is removed

Retain capabilities needed for this single path: media provenance, detection/tracking, frozen appearance correspondence, visual facts, Laya, lexical/exact rule retrieval, deterministic conditions, evidence, required API/UI, privacy/security, correction history and meaningful verification.

Remove from the active working tree, after dependency reconciliation and preservation of unique uncommitted work:

- 27B profiles, configuration, startup paths, GPU legal calls and larger-model fallback logic.
- Parallel legacy/integrated inference implementations, mode selectors and duplicate CLIs. Reuse their required mechanics in one implementation.
- Alternative-model adapters, comparison orchestrators and obsolete candidate routing.
- LoRA/QLoRA/SFT/optimizer code and dormant training configuration.
- BGE dense retrieval and reranking paths not needed by the selected local rule engine.
- Duplicate installers, deployment frameworks, account/provisioning experiments and per-run tooling without a role in the retained product.
- Tests solely for deleted behavior, superseded architecture documents, obsolete handoffs, per-run root control files and generated artifacts.

Do not keep alternative architectures in an `old/`, `legacy/`, backup source directory or disabled feature flag. Git history provides source rollback. Preserve unique uncommitted artifacts outside the active tree before removing them; never present removal as proof the old experiment passed.

Private media, human reviews, corrections, credentials, shared model caches, external worktrees and live resources are outside the repository-cleanup deletion scope. A required review/import capability may be consolidated, but its records and independent review semantics must survive.

## 10. Documentation reconciliation

Make this report the architecture reference. Update active `README.md`, `AGENTS.md`, `CLAUDE.md`, `SPEC.md`, task lists, backend/tracking/legal/deployment guides, configuration examples, API/UI descriptions, packaging metadata and relevant scoped project memory to agree with the implemented target.

Keep startup instructions short: one current path, actual commands and current blockers. Remove historical session diaries and competing plans from automatically loaded instructions. Keep detailed historical evidence in Git or the existing private archive rather than copying it into every document.

Inspect the current dependency graph and consumers before deleting any file. Reconcile imports, CLI entry points, model readiness, health, Docker copies/mounts, package data, environment settings, resource manifests, UI clients and tests together. A string replacement from `27B` to `8B` is not a migration.

Preserve historical receipts unchanged if retained; they describe their original source and model. Do not rewrite them as results of this target. Replace obsolete active release manifests with a newly identified manifest when an actual new artifact exists.

## 11. Validation and completion

Source cleanup can be verified without private inference or downloaded weights. Use existing synthetic fixtures and injected model boundaries only in tests.

Required checks cover:

1. Full-duration scheduling, bounded reinspection, chronological facts and explicit incomplete coverage.
2. Source/actor/frame allowlists, identity uncertainty, role conflicts, reflection ownership and immutable corrections.
3. Laya token-budget refusal, all three condition states, malformed outputs, readiness and no silent model fallback.
4. Rule polarity, exceptions, draft interpretations, missing metadata and missing-opportunity guards.
5. Required API schemas, ownership, admission, deadline behavior, original JPEGs and frontend integration.
6. A single production inference entry path, with removed imports/flags/assets/dependencies absent.
7. Python checks/package build and the existing frontend tests, lint, types and build where affected.

Real acceptance is a separate authorized activity. Compare reviewed positives, hard negatives, multiple actors and ambiguous cases on development recording groups. Report precision, recall, F1, missed/abstained positives, useful answer coverage, localization, evidence relevance, rule correctness, latency and memory. A video-level TP does not independently establish the event, actor, evidence or rule was correct.

Preserve exact duplicates in the same split, resolve session grouping, exclude diagnostic training targets and never use reserved/jury recordings for selection. Do not claim generalization from approximately fifty correlated examples.

Do not close real-model or deployment tasks from synthetic tests. If either model, annotations or runtime authorization is unavailable, complete the source work and state exactly which real checks remain unverified.

## 12. Evidence and references

The model identities and metadata below were inspected during the preceding read-only research. They are reference sources, not proof of installed assets or ForteBank accuracy:

- [Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct).
- [Laya multilingual](https://huggingface.co/convaiinnovations/laya-multilingual).
- [Upstream Laya code and typed decision API](https://github.com/NandhaKishorM/laya).
- [Laya benchmark methods and limitations](https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md).
- [Independent Laya calibration and escalation study](https://arxiv.org/abs/2609.33843).
- [Original fixed jury API contract](contracts/api-contract.json).

Architecture approval establishes the selected direction. Implementation, real inference, semantic accuracy and deployment acceptance remain separate facts.


## 13. Implemented source and verification (18 October 2026)

`src/forte/pipeline.py` is the sole production inference implementation. `worker.py`
always returns its rich result; v2 exposes it and v1 applies deterministic provenance,
condition and JPEG replay. The API has one injectable runner for synthetic tests,
no production mode selector. The exact jury contract file is unchanged.

`timeline.py` performs normal overlapping windows plus specific globally bounded,
interval-deduplicated rechecks. `laya.py` and `laya_service.py` implement the mandatory
loopback CPU choice boundary with full sequence-budget preflight and at most four
encoder rows per batch. Unknown/refused packets, source conflicts and incomplete
coverage remain explicit. Official sources and draft cards remain unchanged.

The retained deployment mechanism is the existing pinned Docker base/entrypoint,
application-only offline bridge and ownership/session gateway. Redundant installers,
provisioning/release frameworks, competing profiles/pipelines, image/legal-generation
prompts, dense/reranker code, comparison tools, dormant training configuration and
target-export CLI are removed. Review eligibility guards and historical private
review-layout adapters remain because they preserve independent human provenance.

Recovery checkpoint: `/Users/itsaibarr/conductor/repos/forte-cleanup-recovery-20261018-095015`.
It holds original dirty/untracked bytes, the tracked binary diff and starting HEAD.
No ignored media/cache/credential store was removed or included in a published artifact.
Tracked rollback remains in Git; nothing was pushed or deployed. Historical receipts
under `.context/verify/` and `web/qa/` remain unchanged and explicitly historical.

Counts include all newly added files, exclude ignored build/cache/private outputs,
and use source `.py`/`.sh` files under `src`, `scripts`, `deploy` and `tools`.

| Surface | Before | After |
| --- | ---: | ---: |
| Executable source files / lines | 73 / 21,690 | 46 / 12,809 |
| Python package files / lines | 33 / 11,479 | 31 / 10,447 |
| Markdown files / lines | 67 / 9,019 | 24 / 1,851 |
| Python test files / lines | 61 / 15,682 | 43 / 8,021 |
| All nonignored files | 348 | 221 |
| Direct dependencies | 7 | 9 |
| Optional dependency declarations | 5 | 5 |
| Development/other group declarations | 10 | 5 |
| Locked package records | 61 | 84 |

Dependencies did **not** decrease overall: mandatory Laya and an explicit CPU-only
Torch source add runtime requirements. Five duplicated tracking-group declarations
were removed; the shared tracking extra remains. The lock and exported runtime
requirements agree; no second CUDA runtime is added for CPU decisions.

Verified locally: 364 Python tests pass with four existing warnings; focused boundary
checks also pass. Ruff lint/format, sdist and wheel builds, wheel-resource/import checks,
lock consistency, shell syntax, unchanged v1 contract and current Markdown-link checks
pass. Frontend: 17 tests, ESLint, TypeScript and Next.js static build pass. Python checks
use the existing environment with `--no-sync`; the new Laya boundary is injected in tests,
not silently substituted in production. No installed Laya/checkpoint compatibility is claimed.

Unverified: actual pinned Laya CPU load/tokenizer/FP32 compatibility and latency/RSS;
selected 8B/container/GPU compatibility under the new dependency set; private-video
semantics, evidence relevance, legal applicability, full coverage, quality, workload
latency and VRAM; real human-local browser flow; exact new image, deployment and jury
acceptance. Per-request GPU queue time remains explicitly null when absent from vLLM
responses; round-trip time, source coverage and process/whole-device memory samples
are separate measurements. Automatic reviewed-correction replay is still unimplemented.
These remain open in `tasks/todo.md`; no speed, memory or accuracy improvement is asserted.


### Documentation release review

The user separately authorized updating the existing Mintlify documentation site.
Remote `main` introduced independently maintained `docs-site/` pages and demo links;
these are preserved and reconciled with this architecture. The reduction counts
above describe consolidation checkpoint `af25644`, before that documentation merge.
This documentation publication does not establish application runtime deployment.

Source review identified two open conservative assessment limitations: actor-wide
condition packets may let unrelated ambiguity suppress an independently supported
event or exceed its evidence budget; v1 clearance replay still assumes one
assessment per rule and abstains on otherwise complete multi-actor results. They
remain explicit follow-ups in `tasks/todo.md`, not accepted semantic behavior.
