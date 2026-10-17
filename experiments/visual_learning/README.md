# Actor-bound visual learning and complete-clip scanning

Experimental, private tools for steps 3–4. Production inference, API, rules,
annotations and decoding are unchanged by this workstream. Import the producer's
`forte26` package through the editable path dependency. No detector or tracker is
implemented here.

## Verified scope and current gates

The CPU command workflow runs on synthetic colored blocks. It verifies source
mapping, actor/participant invariants (including giver/receiver direction and separate
counterpart evidence), grouped scoring, budgets, masks and
serialization. It establishes no real visual accuracy or full-model memory fit.
Both pinned candidates remain eligible; the training model is **unselected**.

The producer committed TrackManifest v1 and annotation/review interfaces; those
are imported, not reimplemented. The consumer completed-export envelope below is
**provisional**: no completed reviewed release has been received. A live metadata
check found 31 completed proposal packets, zero reviewed segments/roles/actions
or training targets, and no release index. Proposal `complete.json` markers are
not reviewed evaluation/training releases. Never snapshot an actively edited
review directory or promote model agreement to independent review.

Gate A needs reviewed roles/actions, continuity and mappings across multiple
development sessions, the regression and near misses, with task semantics and
all evaluated assertions adjudicated. The protocol deliberately requires three
paired groups before it can select a winner. Gate B additionally requires a
frozen session split, eligible independent targets and at least three training
and two validation groups per positive learned action. No adjacent crops/windows
cross splits. Regression sources cannot train. Unreviewed background supplies no
negative target. Separately confirmed ambiguity can supply `unclear` targets.

Paid execution remains pending explicit resource ownership. No allocator exists
in these tools. The shared $30 project envelope is never replenished per run.
No live account/VM inspection was needed or attempted for this CPU preparation.

## Isolated environment and checks

Run commands from the product worktree root:

```sh
uv sync --project experiments/visual_learning --frozen
uv run --project experiments/visual_learning --frozen python -m pytest -q experiments/visual_learning/tests
uv run --project experiments/visual_learning --frozen ruff check experiments/visual_learning
uv run --project experiments/visual_learning --frozen ruff format --check experiments/visual_learning
uv build --project experiments/visual_learning --out-dir experiments/visual_learning/dist
```

The environment is `experiments/visual_learning/.venv`; the root lockfile is not
resolved or edited by these commands. The CPU profile installs NumPy and the
lightweight producer dependencies; no Torch, JAX or vLLM. On this machine the
pinned packages were installed from the existing uv cache after initial public
wheel downloads timed out. `uv sync ... --frozen --offline` reproduces that path
when the same wheel cache is present.

The integration snapshot merges producer commit `aeeb158`; its later working
changes are neither copied nor tested here. Check its committed tests in this
worktree using the isolated environment:

```sh
uv run --project experiments/visual_learning --frozen python -m pytest -q tests experiments/visual_learning/tests
uv run --project experiments/visual_learning --frozen ruff check .
uv run --project experiments/visual_learning --frozen ruff format --check .
uv run --project experiments/visual_learning --frozen python -m build --outdir experiments/visual_learning/dist/product
```

## One CPU-only end-to-end command

Use a new, absolute private directory. Every write refuses existing files and
Git checkouts. Never commit outputs, frames, predictions or adapters.

```sh
uv run --project experiments/visual_learning --frozen python \
  experiments/visual_learning/scripts/synthetic_e2e.py \
  --output /Users/itsaibarr/.local/share/forte26/development-rehearsal/visual-learning/cpu-synthetic-NEW
```

This executes all six required commands plus tracking/scan scoring and dry runs.
Its mock independently returns uncertainty for both candidates, without reference
access. `aggregate.json` reports grouped denominators and explicitly synthetic
results. The tiny adapter is a NumPy matrix fixture, not a Qwen/PEFT adapter.

Equivalent individual commands (set `RUN` to a new private run parent):

```sh
RUN=/absolute/private/visual-learning/run-NEW
uv run --project experiments/visual_learning forte-visual synthetic --output "$RUN/fixture"
uv run --project experiments/visual_learning forte-visual release-check \
  --release "$RUN/fixture/release.json" --snapshot "$RUN/snapshot"
uv run --project experiments/visual_learning forte-visual export \
  --release "$RUN/snapshot/release.json" --output "$RUN/export" --seed 0
uv run --project experiments/visual_learning forte-visual compare \
  --release "$RUN/snapshot/release.json" --inputs "$RUN/export/inference/inputs.json" \
  --references "$RUN/export/reference/answers.json" --mock --output "$RUN/comparison"
uv run --project experiments/visual_learning forte-visual train \
  --synthetic-check --output "$RUN/tiny-training"
uv run --project experiments/visual_learning forte-visual scan \
  --release "$RUN/snapshot/release.json" --clip clip000 --mock --output "$RUN/scan"
uv run --project experiments/visual_learning forte-visual evaluate \
  --inputs "$RUN/export/inference/inputs.json" --references "$RUN/export/reference/answers.json" \
  --predictions "$RUN/comparison/8b/predictions.json" --output "$RUN/metrics.json"
uv run --project experiments/visual_learning forte-visual evaluate-scan \
  --release "$RUN/snapshot/release.json" --timeline "$RUN/scan/timeline.json" \
  --output "$RUN/scan-metrics.json"
uv run --project experiments/visual_learning forte-visual evaluate-tracks \
  --oracle "$RUN/snapshot/clip000/tracks.json" --automatic "$RUN/snapshot/clip000/tracks.json" \
  --output "$RUN/track-metrics.json"
```

`--mock` accepts only synthetic releases. The library scanner accepts an injected
controlled executor `(case, image_root, remaining_seconds) -> response`; its
response has `facts`, source-bound `proposals`, token counts and measured memory.
Run real executors inside a supervised process with the supplied timeout. The
CLI currently exposes the mock scan, so it cannot accidentally start private
inference. `runtime.py` supplies a real single-fact benchmark executor; a live
multi-fact scan executor and its quality/latency validation remain gated work.

## Completed release exchange and missing inputs

`release-check` is metadata-only: hashes, versions, eligibility and counts; no
frames or scene text. `export` is the explicit source-decoding operation. It
reuses `decode_video`, `VideoRegistry.evidence`, source PTS and orientation.

The provisional consumer envelope has these fields (generate a full synthetic
example with `synthetic`; do not invent producer completion or reviewer names):

- `schema_version: forte-visual-release/1`, `producer_schema: forte-track/1`;
- exact `producer_code_commit`, `export_complete`, actual `completed_by` and
  timezone-aware `completed_at`;
- `development_allowlist`: inventory-bound original `batch-selection.json` for
  real releases. The adapter reuses the producer's neutral/hash/split projection;
  reserved/jury/unallowlisted sources are rejected;
- `files`: release-relative path to SHA256 for every media, annotation, track,
  derivative and provenance artifact;
- `clips`: `manifest`, `annotation`, `media`, `images` (source-frame-ID → oriented
  full-scene derivative path), `track_mode` (`oracle` or `automatic`).

All referenced paths must remain inside the release, without symlinks/traversal.
Correction artifacts and prior revisions must be included in the inventory; an
explicit `artifact_mapping` maps original producer paths to snapshot-relative
paths without rewriting the producer manifest.
Track v1 validates PTS, orientation, boxes, facts, participants, reviews and joins.
The reader checks inventory hashes before and after parsing/copying. A snapshot's
consumer receipt additionally binds mapping source hash and imported producer
module hashes; changed mappings/code/content require a new snapshot. Snapshotting
never alters producer reviews or creates competing corrections.

The producer can supply its existing completed export instead of this envelope.
Adapt only `adapter.py` and version/hash the mapping; do not demand a schema
rewrite. Current missing inputs are a producer-declared completed export, reviewed
Gate A targets/near misses/continuity, frozen Gate B grouping/coverage, an automatic
track-to-reviewed-actor correspondence for the tracker ablation, and coordinated
resource ownership. Until then no real compatibility receipt is claimed.

Exports contain `inference/inputs.json` and opaque scene/crop JPEGs, physically
separate from `reference/answers.json`. Targets and exclusions stay private.
Role examples have six chronological times × two views; actions/context use
four seconds at 2 FPS × two views. Missing source boxes/evidence reject an
example rather than silently truncating it. Crop source rectangles and affine
transforms are explicit. Anonymous names and ordering vary by source hash and
seed, remaining consistent across the same recording. Input messages contain
only supplied IDs, geometry, views and task semantics, never original filenames,
binary labels, points, law, reviewer narratives or reference values.

Internal-test sources are excluded from default exports and live selection/
validation commands. Freeze a checkpoint before a separate once-only internal
test execution is enabled. All internal test recordings remain development
material; the nine reserved recordings and jury data remain excluded entirely.

## Pinned model/runtime profiles and selection

`configs/public-sources.json` records eleven primary metadata/code hashes.
Recheck public metadata with `scripts/check_public_sources.py`; it never reads
competition data. Both pinned model cards declare Apache-2.0. Preserve final
model/dependency notices when staging runtime assets.

- 8B: `Qwen/Qwen3-VL-8B-Instruct` at
  `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`;
  `Qwen3VLForConditionalGeneration`.
- 27B: `Qwen/Qwen3.8-27B` at
  `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`;
  `Qwen3_5ForConditionalGeneration` (hybrid linear/full attention).

Both pinned metadata files specify `Qwen3VLProcessor`; their model architectures
and generations differ. The official Qwen3-VL trainer is not a Qwen3.8 trainer.
Our optional direct HF/PEFT trainer chooses the actual multimodal architecture
and asserts full language-attention LoRA tensor names; the 27B hybrid linear
attention remains frozen in this initial proposed boundary. An actual selected-
27B one-step probe must validate that decision and memory before a longer run.

Inference uses the already measured project image, not a new Docker tag:

```text
vllm/vllm-openai@sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b
```

That prior image is vLLM 0.31.0 / Torch 2.13.0+cu130 / Transformers 5.17.0.
Its historical 12-image diagnostic does not establish this scanner's 16-image
quality, full-duration timing or training fit. The new executor's full-model path
has not run here.

SFT is separately resolved in `runtime/sft/uv.lock` for Linux x86_64/Python 3.12:
Torch 2.13.0, Torchvision 0.28.0, Transformers 5.17.0, PEFT 0.21.2,
Accelerate 1.15.0. Resolve/install
only in that profile on the coordinated GPU host, before disabling networking:

```sh
uv sync --project experiments/visual_learning/runtime/sft --frozen
```

The lock was resolved on CPU; this is not a CUDA installation/fit check. Optional
VideoPrism remains deferred and uninstalled; it must use its own JAX profile if
later justified. It does not delay these tools.

`compare` writes `policy.json` before running either candidate. It freezes the
same cases/pixels/IDs/task/schema, seed 0, non-thinking deterministic generation,
768 output tokens and 8,192 total tokens. Each official processor measures input
admission before generation and logs actual grids/token details privately. No
truncation. One model per supervised subprocess; timeouts stop its process group.
Device memory is sampled every 200 ms with nvidia-smi, including vLLM workers.

Selection prioritizes fewer wrong-actor/recipient assertions and role swaps at
comparable per-group role/action answer coverage, then actor-correct event F1
without worse false-event rates. Minimum consistent group wins and a non-tiny
F1 difference are predeclared. Ties, insufficient groups, contract/source errors,
failures or coverage drops are inconclusive. Runtime/memory/cost remain explicit
feasibility gates; a quality winner is not production promotion. Never describe
this as a controlled parameter-count ablation or select from the old recording.

Metrics include session/track-mode counts, actor-and-recipient event P/R/F1 at
IoU .5/.75, known-boundary errors (clipped unknown edges excluded), false events
per evaluated opportunity minute, role/context precision and coverage, swaps,
abstention, invalid references, failures, tokens, runtime and memory. Several
windows remain dependent observations. `evaluate-tracks` scores only independently
reviewed oracle geometry. `evaluate-scan` reports proposal recall and coverage;
unmatched scan assertions await adjudication, so it does not invent an FP rate
from incomplete background labels.

## Data/resource gates and real commands (pending execution)

The pilot receipt is private, completed by the actual reviewer, and binds the
release SHA256, frozen input SHA256, reviewer, `independent_review`,
`regression_reviewed`, `near_misses_reviewed`, `source_mapping_reviewed`,
`continuity_reviewed`, `selection_frozen`, `task_semantics_reviewed`,
`all_assertions_adjudicated` and development/validation split. Training additionally
binds `training_input_sha256` and `selection_sha256`. These fields record actual
review; they cannot create it. Structural checks do not authenticate a human.

The coordinating GPU owner supplies an existing private resource receipt with
`owner: visual-learning`, `project: forte26`, exact `project_resource_id`,
`live_state_sha256`, `live_checked_at` less than five minutes old, `expires_at`
beyond the run deadline, `cleanup_armed: true`, `network_mode: none`,
`remaining_project_usd`, `reserve_usd`, live `hourly_total_usd`, an explicit
`reserved_usd` covering the deadline at that rate, and `total_project_ceiling_usd: 30`.
An advisory exclusive lock prevents concurrent consumers using that same receipt.
No receipt mechanism was established by this workstream on behalf of steps 1–2.
A file claiming ownership does not allocate resources. Follow the existing GPU
runbook, confirm the explicit ownership handoff, live billing/rates/resources and
cleanup before making such a receipt. Never touch the producer's VM/firewall.
The runtime also rejects non-loopback network interfaces; offline environment
flags alone are not treated as network isolation.

`models.json` maps `8b`/`27b` to staged local snapshot directories. Each directory
needs `model-hashes.json` with exact `model`, `revision`, and `files` (all files
except this receipt → SHA256). Hash staged public assets before private mounting.
The runtime verifies every base file and the architecture. It never downloads.

```sh
# Reversible metadata preflight, no resource allocation, inference or training:
uv run --project experiments/visual_learning forte-visual compare \
  --release /private/release/release.json --inputs /private/eval/inference/inputs.json \
  --pilot /private/pilot.json --dry-run --output /private/visual-learning/preflight-NEW

# Run inside the pinned, staged network-none inference container, after Gate A:
python -m forte_visual.cli compare \
  --release /private/release/release.json --inputs /private/eval/inference/inputs.json \
  --references /private/eval/reference/answers.json --pilot /private/pilot.json \
  --resource /private/resource-owner.json --models /private/models.json \
  --runtime-python /usr/bin/python3 --seconds 900 --output /private/visual-learning/paired-NEW

# Export only eligible training/validation targets, after Gate B:
uv run --project experiments/visual_learning forte-visual export --training \
  --release /private/training-release/release.json --output /private/visual-learning/training-pack-NEW

# One training/evaluation/save-reload smoke, using the selected candidate only:
python -m forte_visual.cli train --release /private/training-release/release.json \
  --inputs /private/training-pack/inference/inputs.json --references /private/training-pack/reference/answers.json \
  --selection /private/paired/comparison.json --pilot /private/training-pilot.json \
  --resource /private/resource-owner.json --models /private/models.json \
  --runtime-python /private/sft-venv/bin/python --updates 1 --seconds 1800 \
  --output /private/visual-learning/train-probe-NEW

# Identical-input untuned-base versus saved adapter, validation only:
python -m forte_visual.cli evaluate-adapter --release /private/release/release.json \
  --inputs /private/validation/inference/inputs.json --references /private/validation/reference/answers.json \
  --selection /private/paired/comparison.json --adapter /private/train-run/adapter \
  --pilot /private/validation-pilot.json --resource /private/resource-owner.json \
  --models /private/models.json --runtime-python /usr/bin/python3 --seconds 900 \
  --output /private/visual-learning/adapter-validation-NEW
```

Use the actual interpreter path in the staged container/profile, not an assumed
host installation. Mount only experiment code and needed private inputs read-only,
with a new writable private output directory. Do not mount provider credentials.
Set HF/Transformers offline, telemetry off and hosted logging disabled. The local
worker log can contain sensitive generated errors and stays private.

The initial SFT recipe is BF16 language full-attention LoRA, rank 8/alpha 16,
dropout .05, AdamW 5e-5, weight decay .01, batch one/accumulate eight,
gradient checkpointing and grad norm 1. Assistant-answer CE only; prompt,
image, vision delimiters and padding labels are -100. Prefix matching is verified
against the actual processor; unstable boundaries fail. All vision, projector,
base, embedding and output-head weights remain frozen. Actual trainable names,
full frozen-tensor hash, base/adapter file hashes, checkpoint 0/every 10/final,
validation smoke loss, time/memory and reload logits are recorded.

At most one pass / 30 updates is exposed; default is a one-update probe. A run above
one update requires the selected model’s successful `training.json` via
`--compatibility`, tied to the same model revision, inputs and trainer source.
Do not assume the 8B recipe transfers. A measured extension toward the authorized
60-update/two-pass ceiling is intentionally not automatic. It requires validation
quality improvement and a separately bounded resumed-run implementation. No
training loss or valid JSON promotes an adapter.

## Scanner behavior and remaining validation

The mock scanner schedules 16-second coarse windows at 12-second stride, at most
16 source frames at 1 FPS, including short clips and the last source frame. Source
processing counts from the supplied upload start. Roles cache model origin,
evidence interval and supported segment component; repeated agreement stays
unreviewed, conflicts become unclear, and no unsupported join carries a role.
Proposals include ordinary/unfamiliar model actions, geometric area crossings,
track gaps, role uncertainty and reproducible quiet samples.

Each eight-second neighborhood becomes three overlapping four-second calls at
two-second stride: eight times × scene/crop = 16 images **per call**. Facts must
cite supplied frames with actor/counterpart membership and ordered intervals.
Only matching people/participants/actions with overlapping supported intervals
merge. Clipped edges, contradictions and unknown phases persist; departure never
implies service completion.

The coverage ledger distinguishes decoded ranges, sampling instants/gaps, fine
inspection, occlusion, tracking/decoding gaps and unresolved ranges. Fine coverage
is a sampled envelope, not proof of continuous visibility or object resolution.
Omission eligibility is always false in this unvalidated experiment. Call/token/
memory bounds and the 270-second upload-origin deadline preserve partial records
with incomplete status; executor failures cannot become clean negatives. The
CLI mock is bounded; custom live executors must honor the remaining timeout and
run under the supervised-process boundary. Dense brief-motion passes, a live
multi-fact scan runtime and full source-to-client <300-second measurements remain
conditional validation, not claimed features or quality results.

No legal retrieval/predicates, public verdict, API change or deployment is included.
