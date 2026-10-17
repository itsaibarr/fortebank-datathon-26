# Frozen participant tracking

`forte.frozen_tracking.analyze_participants(source, work_dir, config, deadline=...)`
adds recording-local participant proposals to the frozen reasoning runtime. It
accepts an original MOV path, the existing `VideoRegistry`, or an iterable of
`DecodedFrame` objects carrying original PTS, time base, orientation and pixels.
It does not change the public API, legacy detector, annotation schema or immutable
human review sidecars. It never grants an identity, geometry, role or training
approval.

The detector remains the hash-pinned official YOLOX-s COCO person model. Its
`LocalByteTrack` adapter passes `supervision.Detections` to the retained
`trackers.ByteTrackTracker` with actual source timestamps. Detector support here
is **person class 0 only**; this module supplies no hand, banknote or document
recognizer. Objects too small or unresolved require separately grounded local
visual analysis and remain unknown until supported.

## Frozen appearance model

`scripts/export_osnet.py --output /public/reid` is a public preparation step. Run
it in a staging container without private media or job mounts, before blocking
outbound inference networking. The script fetches the author's MSMT17-combineall
OSNet-x0.25 checkpoint from
[`kaiyangzhou/osnet`](https://huggingface.co/kaiyangzhou/osnet/tree/a5c5cc037c24235cda3b21085b93ad77c9616224)
and the standalone
[`osnet.py`](https://github.com/KaiyangZhou/deep-person-reid/blob/f8cd150fdf77e8d9e1ed143b7f308c2c609ded50/torchreid/models/osnet.py)
implementation. Repository revisions are explicit in the script. Preserve the
upstream MIT license beside the exported model. Staging needs torch, numpy,
onnxruntime and ONNX; the runtime needs only the pinned tracking dependencies.

Checkpoint loading uses `torch.load(weights_only=True)`. Every feature-extractor
parameter must match; only the unused identity classifier is excluded. The
model is placed in evaluation mode with gradients disabled. Export produces
fixed RGB `[1,3,256,128]` input and `[1,512]` feature output, with no optimizer,
adapter or training step. A deterministic synthetic tensor checks exported CPU
ONNX features against PyTorch features before writing `manifest.json`.

The manifest retains checkpoint/code/export hashes, source revisions, preprocessing,
output semantics, dependency versions and numerical export agreement. The local
runtime checks the ONNX hash, local path containment, tensor dimensions and
declared feature output before use. A manifest is provenance, not human approval
or evidence of tracking quality. Missing actual ReID weights fail explicitly;
`mode="byte_track"` is the explicit comparison mode, never a silent fallback.

The authorized public-only VM export on 18 October 2026 loaded all pretrained
feature parameters and produced ONNX SHA256
`b20223157278fbe918b945f3bb0b76c09e6fc1bf7b133a9ecdb9450443f46978`.
The synthetic PyTorch/ONNX maximum absolute feature difference was `4.768e-05`.
This establishes an executable pretrained feature path, not continuity accuracy
on competition footage. Exported weights remain outside Git.

## Association and unknowns

Each detector/ByteTrack observation keeps its source-frame ID, original PTS,
normalized timestamp, oriented normalized XYXY geometry and detector/tracker
origin. No display interpolation is inserted into the evidence table. Detection
runs at the configured source-time cadence, includes first/last source frames,
and includes every frame already cached for the multimodal scanner. A new
refinement frame decoded later has no guessed actor assignment.

Accepted crop embeddings require a minimum pixel area, confidence and truncation
quality. They are L2-normalized and stored in a bounded private appearance
gallery. A strong appearance conflict on a retained tracker ID starts a new
fragment and records the conflict. Separate fragments can share a canonical
recording-local participant proposal only when all of these gates pass:

- Nonoverlapping source-time intervals and a bounded gap.
- Plausible normalized center speed and body-area ratio.
- Adequate real crop embeddings and sufficient cosine similarity.
- A sufficient similarity margin over other eligible people.

An ambiguous match creates a separate participant and an unresolved candidate
record. Low-quality or missing appearance leaves separate fragments. A proposed
association stores both segment IDs, source-frame evidence, cosine similarity,
gap and geometry gates. Galleries and fragment associations are inference
state; weights remain frozen.

Canonical IDs (`p0001`, etc.) are scoped to one source recording, not employment
identities or verified physical-person counts. The participant registry contains
track segments, association evidence, bounded gallery, conflicts, visibility
gaps and separate initially empty `role_hypotheses`. Supported role hypotheses
must later retain their evidence and valid intervals. Clothing, a zone or an
identity link supplies no role by itself.

Camera zones are separate configuration with normalized polygons. A configured
reflection region marks view observations with unknown canonical ownership;
appearance similarity never identifies its owner. Such views are excluded from
the physical participant pool and ordinary `frame_boxes`, preserving their
separate evidence without increasing the participant count. This module does
not detect mirrors automatically. Unconfigured reflection regions remain a
documented camera-calibration limit. Existing human view/role corrections stay
in their immutable review revisions and must be reconciled separately with
source-frame provenance; a new model run never overwrites them.

## Invocation and privacy

```python
from forte.frozen_tracking import TrackingConfig, analyze_participants

participants = analyze_participants(
    registry,
    private_run / "tracking",
    TrackingConfig(
        detector_weights=public_root / "yolox_s.onnx",
        reid_manifest=public_root / "reid/manifest.json",
        mode="reid",
    ),
    deadline=deadline,
)
```

Before touching pixels the callable checks that the OS denies outbound IPv4 and
IPv6 routes or sockets. UDP route selection sends no packet. An environment variable cannot
bypass this gate. The gate verifies a conservative prerequisite; the caller must
provide actual OS isolation: macOS `sandbox-exec` denying networking or a Linux
container started with `--network none`. Loopback model calls can run inside the
same network-disabled Linux container. Public downloads happen separately.

Outputs must be outside every Git checkout. `participants.json` is created once
with private permissions; an existing run is rejected. Use a new versioned
directory for every run and preserve human correction revisions. Embeddings,
private model outputs, frames and case-bearing logs stay in the authorized
environment. Do not inspect private pictures through remote tools.

The return dictionary exposes `participants`, `segments`, `frame_boxes`,
`box_coordinate_space="oriented_normalized_xyxy"`, the complete source-frame
ledger, sampled PTS/time-base/affine transforms, view observations, unresolved
matches and sampling coverage. Sparse samples never establish continuous
visibility or an omitted action. Source hashing and a complete re-decode catch
changed or incomplete source associations.

## Verification and continuity comparison

`tests/test_frozen_tracking.py` uses only synthetic images and synthetic MOVs.
It verifies actual appearance influence, temporal/motion/size/quality gates,
ambiguity, ID-switch conflicts, unknown mirror ownership, bounded galleries,
VFR PTS binding, immutable outputs, failed isolation and missing weights.
Synthetic embeddings are explicitly labeled as synthetic and are not represented
as pretrained inference or a tracking-quality measurement.

For an offline development comparison, run `mode="byte_track"` and `mode="reid"`
on the same hash-pinned source and configuration. Match the same human-reviewed
source detections to each run's segments locally. Supply those explicit
`(source_frame_id, segment_id) -> anonymous reviewed person` assignments to
`benchmark_continuity`. It reports false split/merge pairs and unmatched reviewed
observations for both runs, and refuses different source hashes or reviewed
actor populations. Missing labels are not generated from model predictions.
An empty or incompletely matched reviewed population is marked unmeasured.

This comparison measures continuity among matched reviewed detections. It does
not measure detector recall, complete physical-person count, role accuracy or
legal detection. No continuity gain on real recordings is claimed without a
suitable reviewed comparison; the twelve historically accepted boxes alone do
not establish a representative continuity benchmark.

## Recording manifest and reviewed event evaluation

`forte.manifest.prepare_manifest` performs a metadata-only upgrade of existing
recording groups. It preserves original alias, coarse label, approximate point,
conflict and split metadata verbatim while leaving session, camera and calendar
date unknown. `locked_holdout` maps to reserved eligibility while its original
value remains in provenance. Reserved inventory records need no media alias;
development allowlists expose only neutral basename, source hash and split.

Explicit `record_group_review` operations preserve grouping lineage.
`freeze_manifest` requires reviewed session membership for every recording and
rejects sessions spanning development and reserved splits or unadjudicated
reserved development exposure. Neither a filename nor an old split-status word
freezes session groups. A frozen manifest does not authorize training.

The private canonical metadata revision prepared on 18 October 2026 contains all
40 original recording groups, including 31 development and nine reserved
metadata-only records. It combines the preserved development selection with the
historical full split inventory, retaining both source hashes and original
records in private lineage. No reserved media was opened. Session/camera/date
groups remain unknown and the split remains provisional.

`evaluate_events` uses explicit source-boundary tolerance and maximum-cardinality
one-to-one event matching. Known reviewed actor/recipient, role and provision
version must agree when their respective checks are enabled. Unreviewed targets
are excluded. Model abstentions remain visible and still miss a confirmed event;
reviewed abstention-target coverage is reported separately. False-positive counts
and precision require an explicitly complete reviewed evaluation population;
sparse positive examples alone cannot establish them. Metrics cover only the
supplied reviewed population, never an implicit full-video or competition claim.
