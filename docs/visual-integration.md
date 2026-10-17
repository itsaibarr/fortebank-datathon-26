# Live visual integration

This follow-up implements the application path in the isolated
`experiment/visual-learning` worktree. It merges producer `7d9a1ca` without
changing the producer checkout. Software checks and real model quality are
separate acceptance decisions. No tuned checkpoint or approved operational card
currently exists. A base-control rehearsal must never be described as tuned use.

## Application boundary

The application wheel owns `forte_visual`'s lightweight scanner, input/source
contracts, producer reader and release validation under `src/forte_visual/`.
Optional benchmark/training tools remain in `experiments/visual_learning/`, with
their own environment and SFT lock. The application wheel contains no Torch,
PEFT, NumPy training fixture, editable experiment dependency or absolute checkout
reference. Automatic tracking dependencies are an explicit installation extra:

```sh
uv sync --frozen --extra automatic-tracking
uv run forte-scan --config /private/config/visual.json \
  --source /private/new-upload.mov --private-output /private/new-scan
```

The real CLI calls the same pipeline as the API. Use a supervised container for
private inference; stage all public assets before private mounting. `--network
none` enforces the offline rehearsal boundary. The old `forte-visual scan --mock`
remains a synthetic test command, not the production scanner.

A configuration must explicitly select `mode: tuned` or `mode: base_control`.
There is no fallback between them. Example shape (replace every path/hash with
verified mounted assets; this is not an existing checkpoint):

```json
{
  "schema_version": 1,
  "candidate": "8b",
  "mode": "tuned",
  "base": "/models/base",
  "base_manifest_sha256": "<SHA256 of model-hashes.json>",
  "adapter": "/models/training/adapter",
  "training_receipt_sha256": "<SHA256 of training.json>",
  "detector_weights": "/models/yolox_s.onnx",
  "legal_release": "/legal/2026-10-17",
  "rule_cards": "/legal/rule-cards.json",
  "rule_policy": "/config/visual-rule-policy.json",
  "model_url": "http://127.0.0.1:8001"
}
```

A base control sets both adapter fields to null. It records that outcome. The
base manifest binds every staged model file and its pinned repository revision.
Tuned mode additionally requires a complete PEFT adapter inventory bound to the
same base and training receipt. Missing, changed or incompatible assets fail.
The static vLLM LoRA route is named from the training receipt hash; the base has
a different route. Readiness checks the engine's base/adapter roots and parent,
asset fingerprints, and a completed multimodal warm request on the exact route.
The API warms before accepting requests. Every job retains exact model file
hashes, route and warmup evidence in `model-provenance.json`.

`FORTE_VISUAL_CONFIG` is required by the normal environment-based API startup.
The old pipeline is available only through explicit `FORTE_PIPELINE=legacy` for
historical diagnostics. Production container startup always requires the visual
configuration; it does not select the legacy detector when model loading fails.

## Runtime processing and limits

The worker decodes the entire upload using the shared PTS/orientation registry.
It runs the producer's pinned YOLOX/ByteTrack implementations with no annotation,
reference role, binary label, supplied event time or development allowlist input.
The final upload path accepts valid new MOVs. Training/evaluation still require
the development allowlist and review gates.

Detector geometry, conservative segment continuity, gaps and proposed joins
remain automatic evidence. Roles never transfer through unconfirmed joins.
Source frame boxes include actual VLM sampling instants; interpolation cannot
supply evidence. Predictions and proposed work areas remain model-origin drafts.
Human-reviewed v2 view relationships collapse mirror views as views, not temporal
joins. Unknown-owner reflections are preserved and excluded from actor targets.
Automatic physical-person counting and reflection ownership are not established.

The scanner retains complete-duration 16-second/12-stride coarse scheduling,
source endpoints and the three overlapping fine windows in an eight-second
neighborhood. Fine scene/participant crops use at most sixteen images. The actual
resident multimodal processor's `/tokenize` count plus the 768-token output limit
must fit 8,192; no truncation is allowed. Every model call has a remaining-time
bound, measured tokens, sampled total-device memory and a private call receipt.
The API parent kills overdue worker process groups. The full upload deadline
remains 270 seconds, with at most two admitted jobs.

Coverage separately records dense decoding, sparse samples, fine inspection,
model visibility assessments, occlusion, source/tracking gaps and unresolved
ranges. A model's visible sampled range is not validated continuous visibility.
No absence/opportunity validator is promoted: `adequate_for_omission` remains
false. Empty predictions, partial execution, model failures and missing legal
preconditions fail as `insufficient_evidence` or another allowed failure; they
cannot become `no_violation`. Normal-case semantic acceptance therefore remains
unfinished. A supported positive can retain limitations about unresolved footage.

## Rule scope

The staged corpus still contains three official acts and twelve draft cards.
The official text hashes were rechecked on 18 October local time and match the
saved snapshots; see `.context/verify/visual-legal-recheck-20261018.json`.

The first executable operational category is cash-acceptance cashier departure
under [resolution 231, point 22](https://adilet.zan.kz/rus/docs/V1900019680).
It requires the same supported actor, cashier role, acceptance phase, continuing
service, visible work-area crossing, unclipped source boundaries and independently
established institutional/date applicability. Different context dimensions may
coexist; conflicting operation phases or roles remain unresolved. Source dates
are not guessed from filenames or the current legal edition.

Other visible actions remain in the timeline and receive local retrieval
candidates, with unresolved legal status. There is no exhaustive law-coverage
claim. Draft cards cannot be enabled by adding a reviewer string: an actual
independent review artifact must bind card bytes, source snapshots and legal
release. The current policy supplies none. Merely validating that artifact's JSON
cannot authenticate its human origin; independent review remains indispensable.

Reportable events use one to three original-source JPEGs and source-registry
PTS-derived times. Descriptions include the document, provision, URL, edition
and material visual limits. They do not infer intent, hidden accounting,
document contents or employment from movement alone.

## Real API rehearsal command

Run inside the warmed network-disabled application container, with private input,
job and output mounts. It uploads the whole source without known times/roles,
polls the existing authenticated API, validates the exact public contract,
collects private timeline/provenance, checks the selected model identity and
verifies every returned JPEG against source re-extraction:

```sh
python3 /app/scripts/rehearse_visual_api.py \
  --key-file /service-api.key --file /media/development.mov \
  --jobs-root /jobs --config /config/visual.json \
  --output /jobs/rehearsal-NEW
```

The container image deliberately copies this script to `/app/scripts/`; it
contains no private data. A failed result and its timing remain failed evidence.
Zero reportable events do not establish normality or verified source JPEGs.
No predictions are edited between upload and response.

## Review exchange and resumption

A live metadata check accepted all 31 current pairs (28 v1, three v2), retaining
six confirmed identity ranges and twelve accepted boxes. There are zero approved
role/action intervals, training targets, training-eligible recordings and frozen
splits. No completed real export or real adapter/training receipt was found.
These are live structural counts, not an immutable release compatibility receipt.
No actively edited packet was copied into a release.

The separate local packet is
`~/.local/share/forte26/development-rehearsal/visual-learning/integration-20261018-01/review.html`.
It proposes six source-bound segment intervals and preserves prior certainty;
it creates no approvals. Ask only for visible decisions relevant to an event.
The producer still needs a completed immutable export, reviewed opportunities
and continuity across independent groups. Gate A/B and the predeclared model
selection/promotion policies remain unchanged. A valid selection precedes the
exact architecture's one-update probe and bounded supervised experiment. The
trainer now performs the saved-adapter reload in a fresh interpreter, without
opening reference answers in that child; this code has not passed a full-model
probe yet. See the experiment README for the existing gated commands.

The producer's positive-action-without-actor export bypass is rejected at both
the consumer pair and release boundaries. The owning workstream's reproduction
is documented in `producer-consumer-findings.md`; its annotation files and shared
producer schemas were not modified.
