# Handoff prompt: visual learning and complete-clip scanning

You own steps **3, learning actor-bound visual facts**, and **4, scanning the
complete recording**, of the ForteBank Datathon pipeline. The
[steps 1–2 labeling/tracking work](01-visual-labeling-and-person-tracking.md)
is already running separately. Build the independent software now; consume its
reviewed artifacts when they are ready. Deliver executable tools and verified
results, not another research-only plan.

The immediate failure is a confident cashier/customer substitution. A recognizer
must establish which tracked person performs an action, preserve that association
across windows, and return uncertainty when the video cannot support the answer.
Correct JSON, persistent boxes and plausible prose do not establish actor truth.

**Latest model-selection decision:** 8B is the existing baseline. **The final
training model is not selected.** Compare pinned 8B and 27B on the same reviewed
tracked inputs before choosing what to fine-tune. Do not exclude 27B because the
older research document contains an 8B training recipe. Do not select either
model from the existing one-recording diagnostic.

## Read first and preserve current work

Product repository: `/Users/itsaibarr/conductor/repos/fortebank-datathon-26`.
Start from the commit containing this handoff, with `3e155bf` as the preceding
research checkpoint. Inspect current commits, worktrees and changes; never reset
the running labeling agent's checkout or assume it is clean.

Read `AGENTS.md`, `CLAUDE.md`, `SPEC.md`, `tasks/todo.md`,
[the research proposal](../role-action-training-research.md),
[the measured diagnostic](../model-size-diagnostic.md),
[annotation contracts](../legal-and-annotation.md), and
[the GPU runbook](../gpu-runbook.md). Use the existing Harness workflow at
`/Users/itsaibarr/harness`. Research exact model/framework compatibility through
direct `gh` CLI/API and primary docs; the user excludes Agent Reach for this work.

Inspect `src/forte/video.py`, `src/forte/annotations.py`,
`src/forte/role_benchmark.py`, `scripts/role_benchmark.py`,
`configs/baseline.json` and their tests. Reuse source timing, orientation, hashes
and evidence validation rather than creating another decoder or truth format.
The old role benchmark has a 12-image, six-case limit and no persistent track
interface; do not mistake it for the complete new evaluation harness.

At the research checkpoint, 69 tests passed; no adapter or reviewed training set
existed. Steps 1–2 may have advanced since then. Recheck actual state and consume
their completed artifacts rather than repeating the labeling/tracking work.

## Parallel ownership

Use a separate branch/worktree. When launched through T3, explicitly create/select
the worktree in T3's workspace configuration; changing a shell directory does not
isolate the thread. Do not start a second agent or top-level thread yourself unless
the user or the task owner explicitly requests it.

Keep initial implementation under **`experiments/visual_learning/`**, including
its package, tests, configuration, runbook, `pyproject.toml` and lockfile. Use a
separate virtual environment; do not install Torch/JAX/vLLM into the production
environment or change the root dependency lockfile while steps 1–2 are running.
Use an editable/path dependency on the checked-out `forte26` package when needed.
Resolve separate model-runtime profiles if 8B, 27B and VideoPrism need incompatible
dependencies; record the exact lock/container digest for each.

The other workstream owns annotation/tracking production, shared schema changes,
source decoding and its private review files. Treat these as read-only:

- `src/forte/annotations.py`, `src/forte/video.py`, tracking modules, `src/forte/cli.py`
  and their tests, including any newly appearing `tests/test_tracking.py`.
- Root `pyproject.toml` / `uv.lock`, `configs/baseline.json`, public API/contracts,
  and the existing inference/pipeline/rules implementation.
- Shared orientation/checklist files while the other workstream edits them.
  Keep this workstream's progress/runbook inside its owned directory; reconcile
  shared docs once at integration.
- Producer-owned media, track manifests, annotations and review histories.

Import existing interfaces behind a small consumer adapter. If a schema changes,
adapt that reader and version the mapping; do not silently edit the producer's
schema or copy its business logic. Shared-file integration happens after the
producer commit is available, with one owner per file. Preserve unrelated changes;
never use broad staging or destructive cleanup in a shared checkout.

## Work that starts immediately

Complete these using public metadata and synthetic fixtures, without waiting for
private labels or allocating a GPU:

1. A versioned release reader/validator and training-example exporter, with the
   producer mapping isolated behind an adapter. If the producer schema is not yet
   published, mark the fixture interface provisional rather than claiming real
   compatibility.
2. Role/action/context input builders, full-scene/crop source mappings, answer
   schema, token-budget admission, assistant-loss masking, and split-leak checks.
3. A common benchmark driver for both pinned models, separate reference scoring,
   aggregate metrics and comparison reports. An injectable mock executor lets
   this run without model weights.
4. A complete-clip scan planner and timeline assembler with track continuity,
   uncertainty, coverage accounting, bounded fine inspection and deadlines.
5. Offline supervised-training entry points, adapter save/reload checks and
   evaluation commands. Validate wiring/masks with small synthetic tensors; do
   not claim this establishes full-model memory fit or learning quality.

Do not wait idle for annotations. Deliver the independently runnable preparation
even if reviewed-data or compute ownership gates remain pending.

## Input exchange with steps 1–2

Private root:
`/Users/itsaibarr/.local/share/forte26/development-rehearsal`.

The producer's authoritative starting artifacts are
`annotation-review/two-layer-review/`, `annotation-review/first-milestone-review.json`,
the neutral sources and its new track manifest. Do not train directly from a
directory it is still editing. Accept a completed, versioned producer release or
create an immutable consumer snapshot only after the producer marks that export
complete. Verify hashes before and after copying; a partially written index is
not a release. Do not demand a new producer format if its existing export supplies
the required information.

The release/snapshot must bind:

- Schema version, producer code commit, manifest hash and hashes of referenced
  annotation/media/derivative files; exact revision of the consumer mapping.
- Neutral clip ID, source hash, recording/session group, duration, oriented source
  dimensions, normalized frame time and original PTS.
- Track/segment IDs, source-frame boxes/crop transforms, visibility, gaps and
  proposed versus verified joins. No unsupported role inheritance across a gap.
- Roles, actions, participants, intervals, clipping/visibility limits and evidence
  frames, with actual review status, reviewer and correction provenance.
- Training eligibility/exclusions and a frozen group split when training is ready.

Store this workstream's examples, predictions, checkpoints and reports under a new
private `visual-learning/<run-id>/` directory. Reference the producer release;
never rewrite its reviews or maintain a competing corrected annotation set. Keep
reference answers physically separate from inference inputs. A metadata-only
preflight checks hashes, completeness and eligibility without printing scenes.

**Gate A — reviewed evaluation pilot:** checked role/action facts, person continuity
and source mappings on multiple development recordings, including near misses and
the known role regression. A single corrected scene is insufficient to choose a
model. Run the frozen 8B/27B comparison only after this gate; clearly scope its
conclusions if the pilot lacks class/session diversity.

**Gate B — training-ready release:** independently reviewed eligible targets,
resolved recording/session grouping, a frozen train/validation/internal-test split
and class coverage. The proposed pilot floor is three independent training groups
and two validation groups per learned positive action; it is not a statistical
accuracy guarantee. Never split adjacent windows/crops of a session across sets.
The 31 development recordings have already been explored; internal testing is a
development check. Keep the nine reserved recordings and all jury data untouched.

Known regression footage remains excluded from training while used to evaluate
the fix. Drafts, unresolved ID joins, conflicting corrections and unlabeled
background are ineligible. Deliberately ambiguous views can teach `unclear` only
when separately reviewed as such. Do not request RK-law labels from the user.

## Compare 8B and 27B before training

Candidates:

- `Qwen/Qwen3-VL-8B-Instruct`, revision
  `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`.
- `Qwen/Qwen3.8-27B`, revision
  `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.

These are different model generations, not a controlled parameter-count ablation.
Compare actual candidates without attributing any gain solely to size. Verify
each model's official processor, runtime, license and training support; the
Qwen3-VL trainer is not automatically a Qwen3.8 trainer.

Freeze the same reviewed selection cases, source timestamps, target tracks,
scene/crop pixels, task semantics, output contract, seed, output budget and
visibility scoring. Store per-model token/resize details: processors may differ.
Run one model at a time. Start with deterministic, non-thinking generation for
the matched comparison; any thinking-mode follow-up is a separately named,
time-bounded experiment, not a hidden change to one candidate.

Measure actor/role confusion, actor-and-recipient-correct events, temporal
localization, false events per minute, abstention/answer coverage, invalid source
references, failed jobs, warm/cold timing, actual tokens and peak memory. Compare
oracle reviewed tracks with automatic tracks to separate recognition from tracker
errors. Several windows of one recording remain dependent observations.

Predeclare selection before seeing results: prioritize fewer wrong-actor
assertions at comparable answer coverage, then actor-correct event F1 without a
worse false-event rate, then runtime/memory/cost. Report paired per-group counts.
A tie, inconsistent tiny gain or inadequate coverage is **inconclusive**; it is
not permission to call 8B the quality winner. A 27B quality advantage must remain
eligible if runtime and the existing budget permit it. Neither model is promoted
merely by emitting valid answers or fitting the GPU.

Use validation/development selection cases for these decisions. Select a checkpoint
before evaluating the internal test once; do not tune repeatedly against it.

## Supervised learning after selection

The first method is supervised multimodal adaptation on reviewed visual facts.
Do not train legal citations/conclusions, invented reasoning narratives, face
identity or a text-only model from scratch. RL/GRPO remains deferred.

- Role examples: six chronological times spanning supported service interactions,
  each with full scene and target crop, giving 12 images.
- Action examples: four-second windows at 2 FPS, eight source times × scene and
  padded actor/pair crop, giving 16 images. Preserve counterpart/hands/objects.
- Context examples: visible interactions/service cues and supported transaction
  context, with explicit unknowns when type/completion cannot be established.

Return anonymous actor, role/action, known counterpart, source boundary frame IDs,
clipped-edge flags, evidence IDs and visibility. Application code resolves PTS;
the model does not invent timestamps. Randomize anonymous ID names/track ordering
consistently. Exclude supplied binary labels/points, descriptive source names and
reference facts from inference input. Negative action targets require exhaustive
review of the relevant interval/class.

Loss is assistant-answer token cross-entropy; mask input/image/padding tokens to
`-100`. Train only language-attention LoRA initially, freeze the visual encoder,
projector and all base weights, and assert the actual trainable tensor names.
Use the researched **8B reference recipe if 8B is selected**: BF16, rank 8/alpha 16,
dropout 0.05, AdamW at 5e-5, batch one/accumulate eight, gradient checkpointing,
at most 30 updates/one pass initially. At most 60 updates/two passes in total only
after measured validation improvement. Preserve adapter/base hashes and verify
save/reload equivalence.

If 27B is selected, verify the exact framework supports its multimodal architecture
and these freeze/LoRA boundaries, derive a pinned compatible config, and measure
one training/evaluation step before committing to the run. Do not assume the 8B
command or memory figures transfer. If it fails fit/budget, report that result;
do not silently switch to 8B training and present it as the selected experiment.

Admit only examples whose measured input plus output fits the bounded sequence
budget, initially 8,192 tokens and at most 16 images. Never truncate away image
tokens, target frames or answers. Treat 196,608 pixels/image as an initial cap,
not proof that small objects are resolvable. Inference fit is not backpropagation
fit. Evaluate the selected untuned base and its adapter on identical inputs.

The frozen VideoPrism-B/head baseline in the research report is optional after the
matched 8B/27B comparison, if needed to diagnose motion/action failures and if
resources remain. It is not a required third production service. Keep its
dependencies separate and use matched-sampling checks before attributing gains
to architecture. Do not let this optional branch delay the core deliverables.

## Complete-clip scan, built in parallel with a mock executor

Consume tracks from steps 1–2; do not implement another detector/tracker.

1. Schedule the complete duration, including short clips and endpoints, in
   16-second coarse windows with 12-second stride and up to 16 frames at 1 FPS.
   Use source PTS/orientation from the shared decoder. Record decoding/sampling
   gaps; sparse sampling does not establish continuous visibility.
2. Establish and cache predicted roles against supported track segments with
   their evidence intervals and origin. Conflicting later evidence triggers
   wider context or uncertainty. Never turn repeated model agreement into human
   confirmation or carry a role across an unsupported join.
3. Propose fine inspection from ordinary actions, area crossings, exchanges,
   track gaps and role uncertainty, plus a reproducible sample of quiet ranges.
   An event need not match a legal rule or known action class to be proposed.
4. Inspect an eight-second neighborhood at 2 FPS as three overlapping four-second
   windows at two-second stride. Each contains eight times × scene/crop: 16 images
   per call. Sixteen times × two views would be 32 images, not one 16-image call.
   Narrow/denser bounded passes may be required for brief motion.
5. Validate source/track membership, ordered intervals and participant relations;
   assemble compatible facts into a timeline without merging different people or
   inventing boundaries. Keep clipped events, contradictions and uncertain phases
   explicit. Do not infer service completion solely from a departure.
6. Maintain a coverage ledger distinguishing decoded, sampled, closely inspected,
   occluded and unresolved ranges. Omission checks require the full relevant
   opportunity to be visible at adequate resolution. Unseen is not absent.
7. Enforce call/time/token/memory bounds. Existing configuration targets 270 seconds
   from upload start and under 300 seconds client completion; include source
   processing and output work. On exhausted budget, preserve partial observations
   and report incomplete analysis through the experiment's internal status.
   Never convert an unfinished scan to a clean negative.

Return an internal visual timeline only. Legal retrieval/predicate integration,
public verdict generation, API changes and deployment belong to subsequent work.
Do not replace the production pipeline under this handoff.

## Compute and confidentiality

Preparation is CPU/synthetic work. Existing $30 total-project Hyperstack lifecycle
authorization persists; it is not a fresh $30 grant per agent. The last research
snapshot was $27.55 with zero VMs/volumes, subject to billing settlement. Recheck
live state before future compute, and follow the existing runbook and cleanup.

Only one coordinated owner may allocate/use the project's GPU and spend envelope
at a time. Steps 1–2 retain any active resource ownership until an explicit handoff.
Do not allocate a parallel VM, stop/delete their VM, change firewall/runtime state
or exhaust their budget. Use the existing resource-owner/reservation mechanism;
if none is established, finish preparation and mark paid execution pending resource
ownership. This is coordination of already-authorized spending, not a new request
for the same user permission. Preserve source/results before project-scoped cleanup.

Credentials remain outside Git under `~/.config/forte26`; never print them. Private
media, crops, captions, annotations, predictions and competition-derived adapters
stay outside Git/chat/shared memory/external AI inference. Do not inspect private
frames through remote image tools. Local humans or approved controlled inference
perform semantic review. Block outbound networking after staging public assets;
disable telemetry, hosted logging and Hub uploads. No audio or face identification.

## Commands, checks and acceptance

Implement and document a separate command namespace, for example:

```text
uv run --project experiments/visual_learning forte-visual release-check ...
uv run --project experiments/visual_learning forte-visual export ...
uv run --project experiments/visual_learning forte-visual compare ...
uv run --project experiments/visual_learning forte-visual train ...
uv run --project experiments/visual_learning forte-visual scan ...
uv run --project experiments/visual_learning forte-visual evaluate ...
```

These commands are required new deliverables, not existing working commands.
Provide exact arguments/examples and a CPU-only synthetic end-to-end invocation.
Private inputs/results are explicit paths; outputs use new run directories.
`compare`/`train` must check their data and resource gates before allocation or
inference. A dry run creates no paid resources and starts no training.

Add meaningful behavior tests for: draft/conflict rejection; missing/corrupt or
changing releases; unsupported schema mapping; path/hash/frame provenance; crop
transforms; split leakage; no answer leakage; ID permutations; uncertain joins;
token admission/loss masks; clipped/overlapping event merging; endpoint coverage;
deadline exhaustion; mock-model failure; paired metrics and abstention counting.
Use synthetic fixtures only. Run isolated tests/lint/build, then the existing
project checks after integration. Do not modify or claim passing the other agent's
in-progress tests. Schema tests do not establish real visual accuracy.

Deliver:

1. A tested, isolated exporter, benchmark/training setup and mock-driven complete-
   clip scanner, with a reproducible runbook and separate commits.
2. A producer-release compatibility receipt tied to exact schema/code/content
   hashes when available; otherwise a clearly provisional adapter and missing-input
   list, not a fabricated successful integration.
3. After Gate A/resource ownership: a paired 8B/27B report and explicit selected
   model or inconclusive outcome. After Gate B: a bounded training/quality report
   only if selection, compatibility, memory and budget checks pass.
4. Aggregate actor-correct precision/recall/F1, false-event rate, temporal IoU
   0.5/0.75 and boundary errors, role precision/coverage, proposal recall, track
   errors, source validity, scan coverage, runtime, memory and spend. Keep exact
   scene outputs private and denominators grouped by recording/session.
5. A final handoff listing completed software, real compatibility, reviewed-data
   readiness, model-selection outcome, actual experiments and pending gates
   separately. No model is promoted unless measured actor/action quality improves
   without hiding errors through extra abstention and meets runtime constraints.

If the producer release is unavailable, complete the independent deliverables and
state the dependency precisely. Do not invent labels or wait for all 31 clips
before building the tools. Integration can start on a completed reviewed pilot;
training waits for its own reviewed split/coverage gate.
