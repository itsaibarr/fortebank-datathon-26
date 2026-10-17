# Private person tracking and visual review

The steps 1–2 workflow is implemented. A CPU run processed all 31 allowlisted
development recordings offline and prepared local review packets. **No complete
person/role/action pilot is approved, and no training targets are released.**
The three original review cases are priority items. Human responses now supply
role/view mappings for all three pilot recordings and one explicit same-person join; full
interval and geometry review remains open. Their narrative corrections
are preserved, with explicit pending bindings to outlined segments/source frames.
A local human must finish those bindings and review the tracks, areas and actions.

The public jury API and production detector are unchanged. This workflow does
not train anything, infer employment from a detector, or assign legal labels.
Steps 3–4 in `role-action-training-research.md` remain a later proposal.

## Reproduce proposals

Run from this repository. Public setup and private inference are separate:

```sh
PRIVATE_ROOT=/Users/itsaibarr/.local/share/forte26/development-rehearsal
bash scripts/person_tracking.sh setup "$PRIVATE_ROOT"
bash scripts/person_tracking.sh propose "$PRIVATE_ROOT" \
  "$PRIVATE_ROOT/person-tracking-v1/new-run" --pilot-only
# After local pilot review, or to prepare explicitly unreviewed drafts:
bash scripts/person_tracking.sh propose "$PRIVATE_ROOT" \
  "$PRIVATE_ROOT/person-tracking-v1/new-run" --resume
```

Add `--clip clipNNN` to process one allowlisted recording. The command rejects
reserved/unknown IDs, hash mismatches and private output inside Git. It reads
only neutral filename, recording hash and development split for eligibility;
supplied labels, points and original filenames do not guide detection or labeling.
The prior template index is checked against each source and copied explicitly.

Dependencies are isolated under `person-tracking-v1/_runtime/.venv`, using the
`tracking` dependency group and `uv.lock`. Normal `uv sync --frozen` keeps the
lightweight API environment. Public weights are downloaded first and SHA256
checked. The Mac wrapper enforces `sandbox-exec` network denial for Python and
its children. A direct unsandboxed CLI invocation is not the private inference
runbook. On Linux use an independently verified network-disabled container;
the Mac wrapper fails rather than pretending to provide Linux isolation.

The Mac runtime emitted duplicate PyAV/OpenCV AVFoundation class warnings; the
31-recording run completed without a crash. This is not a Linux portability test.

The fixed baseline is [official YOLOX-s ONNX](https://github.com/Megvii-BaseDetection/YOLOX/releases/tag/0.1.1rc0)
→ [roboflow/trackers ByteTrack](https://github.com/roboflow/trackers/tree/3666546420b0fd564c8e63157a6621efffdfa01a).
Code, artifact hashes, COCO person class 0, thresholds and license basis are in
`configs/person-tracking.json`; discovery receipts are in
`.context/verify/person-tracking-upstream-20261017.json`. The selected tracker is
the 2.6.1 wheel, pinned to its release commit and wheel/source hashes. The initial
HEAD search was discovery, not the installed revision. No hosted inference SDK,
appearance ReID, SAM, BoxMOT or semantic role model is used.

Each recording is decoded completely with `forte.video`, including original PTS,
time base, source ordinal, display rotation and normalized timestamp. Detection
runs nominally every 0.2 seconds and includes first/last source frames. Every
sampled-out frame is identifiable from the complete frame ledger and detection
ID list. Undecodable recordings fail; they do not become clean negatives.
ByteTrack receives actual timestamps and retains state across all windows.
Its unassociated detections receive separate draft segments. Gaps, unsupported
jumps and overlapping-person transitions start new segments and proposed joins.
This conservative guard intentionally produces many fragments and candidate
links. Those are hypotheses for review, not measured distinct people or ID errors.

## Private artifacts and migration

The completed preparation run is `person-tracking-v1/run-001` beneath the private
root. Open its `review.html`, then the three priority `human-check.html` pages.
There is full-scene playback, draft ID playback, chronological source JPEGs and
separate person crops from the same exact source frame. Priority pages retain
surrounding playback and the original human correction; they do not ask a human
to guess a role from an isolated departure. Files are local and fetch no external
resources. The coding agent must never use screenshot/image/browser tools to
inspect these private views.

Per-recording artifacts:

- `tracks.json`: version 1 proposal sidecar, linked by path/hash to `annotation.json`.
  A human view/role review explicitly migrates its copied revision to version 2;
  old version 1 files remain readable and unchanged.
  Source dimensions/rotation, normalized full-frame XYXY boxes, original PTS,
  track/person/segment IDs, gaps, proposed joins, independent geometry/identity
  reviews, work-area outlines, origins, scores and correction history are explicit.
- `annotation.json`: existing visual/legal schema with backward-compatible
  optional track bindings, counterpart evidence, observation state, review time,
  visible basis, visibility limits and playback interval. Canonical role/action
  facts live here; the sidecar does not duplicate them as a competing label set.
- `annotation-before.json` and run-level `original-review-backups/`: unchanged
  original templates, three-case review, role reference and original index.
  Existing review files/media are never overwritten. Empty-template rounded
  durations migrate to the exact decoded end, with old duration/hash retained.
- `review-assets.json`: full-scene/crop hashes and pixel crop transforms. JPEGs
  and H.264 playback are oriented derivatives; original MOV bytes are untouched.
  Interpolated overlay boxes are display proposals, separate from detector boxes.
- `cvat.xml` plus `cvat-source-map.json`: CVAT frame ordinals are explicitly bound
  to the full source PTS ledger and recording hash. Keep both files together.
- `correction-binding-pending.json`, `human-review-request.json`, `legacy-review.json`
  and `review-intervals.json`: original certainty, exact frame/segment choices and
  unresolved local questions. A narrative correction is not automatically a box
  or a complete role interval.
- `index.json`, `aggregate.json`, `source-verification.json` and
  `run-provenance.json`: statuses, exclusions, mechanical receipts and loaded-code
  snapshots. `failed-attempts/` retains incomplete drafts, never training truth.

One provenance issue remains unresolved: the role reference's recorded review-file
hash differs from the currently supplied review packet. Both original artifacts
and both receipts are preserved. All reference-frame PTS associations verify
against the development source. This does not repair or authenticate the older
narrative receipt, so the binding still requires local review. The known diagnostic
recording remains regression-only regardless of later annotation approval.

## CVAT Community review

[CVAT Community](https://github.com/cvat-ai/cvat/tree/9176834830e2e931a8d3a6857dcf43c6cc0ee927)
is the selected annotation tool. The setup script derives a reduced isolated
Compose configuration from that exact upstream revision and pins server/UI image
digests. It publishes only `127.0.0.1:18080`, uses an internal Docker network,
disables analytics and keeps this project's containers/volumes separately named.
It does not touch other Docker projects or delete retained review volumes.

```sh
RUNTIME="$PRIVATE_ROOT/person-tracking-v1/_runtime"
"$RUNTIME/.venv/bin/python" scripts/cvat_community.py prepare --directory "$RUNTIME/cvat"
COMPOSE_PARALLEL_LIMIT=1 "$RUNTIME/.venv/bin/python" scripts/cvat_community.py pull \
  --directory "$RUNTIME/cvat"
"$RUNTIME/.venv/bin/python" scripts/cvat_community.py start --directory "$RUNTIME/cvat"
"$RUNTIME/.venv/bin/python" scripts/cvat_community.py create-user --directory "$RUNTIME/cvat"
```

Credentials are generated into that private directory; do not print or commit
that file. After startup, use the local Community instance only. Create a video
tracking task from `oriented-source.mp4`, all source frames, with `person`
(rectangle) and `work_area` (polygon) labels as declared in `cvat.xml`. Person
attributes are immutable `segment_id`/`person_id` text and mutable `role`
(`unclear`, `cashier`, `customer`). Work-area attributes are `area_id` text and
`boundary_uncertain` checkbox. Import `cvat.xml`, correct boxes/tracks/outlines,
and export **CVAT for video 1.1**. Do not change source frame range, step or scale.
Verify task frame count against the source sidecar before reviewing.

The local server pilot has **not** started: Docker Hub repeatedly returned
`net/http: TLS handshake timeout`; a final sequential pull also stalled and was
stopped. No project containers were created, no footage was uploaded, and native
server round-trip acceptance remains pending. The adapter's synthetic XML
round trip passes for occlusion, outside/keyframe flags, mutable roles and area
polygons. That is not a claim of successful import/export through a running CVAT
server. Complete the native synthetic round trip before importing private pilot
media after the image-download problem is resolved.

Integrated SAM 2 tracking is documented for Online/Enterprise, not Community.
Do not upload to Online or promise a free integrated SAM 2 tracker. External
local correction proposals could be imported separately if later justified.
No fallback annotation service was deployed.

## Apply an actual review

CVAT attribute edits are drafts. They never overwrite a human role fact or approve
geometry merely because a role word agrees. `outside` ends a proposal's validity;
it is not automatically an observed exit from a physical area.

```sh
uv run forte tracks-import-cvat --directory /private/run/clipNNN \
  --source /private/neutral/clipNNN.mov --xml /private/edited.xml \
  --output /private/run/revisions/clipNNN-v1 --reviewer 'actual local reviewer' \
  --reason 'description of actual review scope'
uv run forte tracks-review --directory /private/run/revisions/clipNNN-v1 \
  --source /private/neutral/clipNNN.mov --operations /private/review-operations.json \
  --output /private/run/revisions/clipNNN-v2 --reviewer 'actual local reviewer' \
  --reason 'description of actual correction'
```

Operations are a JSON list. Supported operations are `split` (segment/frame),
`join` (from/to segments), `box` (segment plus full Box record), `review` (segment,
explicit status, optional `resolve_identity: true` and `approve_boxes: true`), `area` (full WorkArea record)
and `fact` (full VisualFact record with explicit review status). Version 2 also
accepts `role_binding` (human segment/role mapping with candidate versus actually
reviewed source frames) and `view_relation` (direct/reflected views sharing a
recording-local canonical person ID). These mappings are review constraints, not
complete role-interval facts or training targets. Mirror relationships do not
create temporal joins or approve boxes. Reflected views cannot silently acquire
a different role from their reviewed canonical person. `view_observation` records
just the human-reported view kind when the reflection owner or role is unknown.
A reflected `role_binding` may have a null `canonical_person_id` only alongside
a reviewed reflection observation; this preserves the reported role without
inventing an owner. A view-only response does not become a reviewed `unclear`
role or abstention target. Repeated cashier assignments on separate segments do
not establish that they depict the same person. The aggregate reports canonical
role-mapping groups and unresolved identities separately; those groups are not
a count of verified distinct physical people. See the synthetic
examples in `tests/test_track_review.py` and `tests/test_tracking.py`. A split
keeps the old person before the cut and creates a fresh person after it. Facts
are not moved automatically; a split that invalidates old facts requires explicit
fact correction in the same operation list. Joins remain recorded history;
confirmed human joins supersede matching proposals without erasing them.

Every review creates a new directory, preserves the previous manifest/annotation
and exact operation/XML input, appends reviewer/time/reason/history, and rebuilds
matching playback/assets/receipts. Roles need a work area, temporally separated
source frames and service context. Link identifiable giver/receiver segments and
evidence; otherwise leave the counterpart unknown. Cash handling, clothes, side,
posture or departure alone do not establish a role. Label unreadable documents
as unreadable documents, with no invented contents or amounts. Record visible
service-end cues separately; service completion defaults to uncertain.

Use `observation_state` to distinguish `not_reviewed`, `not_visible`,
`not_observed_in_reviewed_interval` and `observed`. Unknown/occluded/unsampled
cells are not absence targets. A deliberately reviewed unresolvable view can
be a confirmed `target_kind: abstention`; an unresolved disagreement cannot.
Do not add legal decisions, rule IDs or statutory intent to visual targets.

Refresh the private index after a revision:

```sh
uv run forte tracks-index --private-root "$PRIVATE_ROOT" \
  --directory "$PRIVATE_ROOT/person-tracking-v1/run-001" \
  --revision clipNNN=/private/run/revisions/clipNNN-v2
uv run forte tracks-check --directory /private/run/revisions/clipNNN-v2 \
  --source /private/neutral/clipNNN.mov
```

The original index is backed up before refreshing. No draft is approved by valid
JSON, a model, or this software checker. Reviewers are real humans; synthetic
reviewer names occur only in synthetic tests. Record actual reviewed ranges and
tracking errors privately before reporting tracking accuracy.

## Training gate and verification

Draft/rejected facts, unresolved identities, unreviewed boxes, proposed joins and
unfrozen session splits are excluded from target export. The regression recording
is always excluded. Role approval does not approve every box or join. Before any
later training, a human must determine session continuity and freeze a split that
keeps exact duplicates and continuous sessions together. No sessions are inferred
from filenames, and the current split is deliberately unfrozen.

`tracks-export-targets` refuses an empty/unreviewed release and emits source-bound
facts, frame/geometry provenance and canonical artifact hashes only when all gates
are met. Nothing from the present run is training-ready.

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python -m build
# Run both private/synthetic runtime checks with the same network sandbox:
# scripts/check_tracking_runtime.py
# scripts/verify_tracking_run.py --private-root "$PRIVATE_ROOT" --directory /private/run
```

The real provenance check re-decodes every allowed source and both complete
playback derivatives; it re-extracts before/middle/after source JPEGs/crops plus
all retained diagnostic reference views. It checks pixels and transforms locally,
without displaying media to the remote coding agent. It proves source association,
not actor correctness. Aggregate measurements and remaining gates are in
`.context/verify/person-tracking-20261017.json`.

## Human view-mapping follow-up

Responses for all three pilot recordings are preserved privately with verbatim
wording, reviewer source and receipt time. Fourteen named view/role mappings are
associated with six recording-local identity groups, with seven reviewed reflection
relationships and one independently confirmed same-person join. The groups are
not a verified count of all physical people. Full segments, geometry, work areas,
actions and role intervals remain unapproved, and no role/action training target
is released. The historical regression exclusion remains. Original review packets
and baseline proposals are intact; the private index points to immutable reviewed
revisions. One additional human response remains explicitly unclear, with its
role, view kind and identity unresolved; it supplies no abstention training target.
The aggregate separates proposed, confirmed and rejected joins.

Review regeneration now retains all previously cited source-frame images,
including diagnostic reference views, before adding new candidate views. The
packet displays recorded mappings beside pending interval/geometry gates rather
than treating mirror detections as additional physical people.

The current aggregate receipt is
`.context/verify/person-pilot-role-review-20261017.json`; the earlier
`person-view-review` receipts remain historical checkpoints.

These pilots check source binding and annotation errors. Recording-local IDs
are annotation references, not employment classes or features to memorize.
Generalization to other cameras remains untested. Before any later training,
review camera/view and session groups without using filenames as evidence, keep
related recordings and reflected views together, and evaluate on unseen camera
views when the available development data supports that split. Compare against
the unchanged model and the position/area baseline required by the steps 3–4
proposal. If camera diversity is unavailable, report that limit explicitly;
several windows from one recording do not supply independent evidence.
