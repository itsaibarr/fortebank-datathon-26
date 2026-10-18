# Core completion slices, 18 October 2026

These changes continue the frozen v2 reasoning pipeline. They do not change the
v1 detector, weights, legal corpus, approval gates, thresholds or runtime budgets.
The original evaluation runtime remains a separate build until the integration
owner records and verifies an explicit deployment transition.

## Trusted legal configuration

The existing reasoning configuration accepts two optional fields under `legal`:

- `applicability`: a list of existing `VersionApplicability` records, with exact
  act/version, effective interval, official authority provision IDs and reviewer.
- `metadata_evidence`: a list of existing `EvidenceItem` records with unique IDs,
  `kind: metadata`, `origin: human` or `authorized_metadata`, and the actual
  recording SHA256 as `source_id`. Participant references remain source-local.

Both default to empty. They are supplied by the trusted operator configuration,
never by the visual model, public upload fields or a filename heuristic. The
pipeline forwards supplied applicability to `LegalEvidenceService` and supplied
metadata to `evaluate_timeline`. Unknown legal configuration fields reject rather
than silently ignoring a misspelled evidence field. A foreign source binding
fails before tracking or private visual requests. Effective configuration bytes,
including these records, remain in the private run and its existing config hash.

Structural validation does not authenticate a reviewer, establish a recording's
calendar date, approve an interpretation, or prove that metadata is true. The
default cards are still drafts and undated recordings still have unknown edition
applicability. No source review or legal conclusion is manufactured by wiring.

## Failure and identity handling

A legal evidence-preparation deadline now records the unavailable stage and
preserves prior validated timeline/condition records. Invalid source ownership,
source mutation, metadata and other preparation validation failures still fail
closed. Receipts distinguish `inference_attempted` from preparation attempts;
`metrics.calls` counts real backend attempts and `metrics.attempts` counts rule
attempts. Missing evaluations remain explicit and cannot clear a recording.

Negative keys emitted by the ByteTrack adapter identify unassociated detector
observations. Their geometry, confidence and source PTS remain in singleton
segments, with `association_status: unassociated_detection`, no appearance
gallery, no canonical participant and a null `tracker_id_origin`. Confirmed
nonnegative tracker proposals, including ID zero, keep their existing behavior.
An unknown-owner reflection remains a view observation. This change introduces
neither geometry approval nor temporal/person joins.

Full scenes and source crops now reach the actual visual-request serializer in
source timestamp order, with a scene before its same-source crops. View IDs,
image bytes, affine transforms, source rectangles and evidence hashes remain
paired. Unclear detailed-window coverage or pending refinement keeps the final
execution partial, even when the sampling schedule itself has run to completion.

## Verification and remaining boundary

Focused synthetic regressions are in `test_reasoning_configuration.py`,
`test_legal_preparation_failures.py`, `test_unmatched_tracking.py`,
`test_timeline_ordering.py` and `test_reasoning_coverage.py`. The ordering check
examines both tokenization and completion HTTP payloads, JPEG hashes and rotated
source/view transforms. Negative-key behavior was additionally exercised with
the installed public trackers 2.6.1 / supervision 0.31.0 adapter and synthetic
detections, preserving valid ID zero. Baseline failures were reproduced before
the corresponding corrections. See the final integration manifest for final
combined commands, counts and actually served build identity.

These checks establish software behavior. They do not establish recognition,
participant continuity, legal accuracy, full recording coverage or final remote
upload-to-UI latency. The existing TEST owner retains the unchanged private
baseline evidence. New source requires a new runtime identity and affected
acceptance checks; an earlier baseline pass cannot verify these changes.
