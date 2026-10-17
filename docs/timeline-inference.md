# Frozen whole-recording reasoning

The versioned reasoning route supplements the unchanged original detector. It
uses the configured resident loopback model with frozen weights and actual JPEG
inputs; production has no mock scan executor. `src/forte/timeline.py` reuses source
decoding and evidence from `forte.video`. The separate learning checkout was
inspected without changing it. Its bounded scan scheduling, conservative
overlap consolidation and explicit coverage inspired this isolated integration;
its training/runtime package is not imported.

`analyze_reasoning(source, work_dir, settings, deadline=...)` runs source decoding,
participant proposals, whole-recording observations, official local provisions,
condition evaluation and original evidence export. `settings.reasoning_config`
must explicitly supply tracking and legal settings. Model checkpoint/revision
verification is owned by the serving adapter. Failure to verify readiness stops
the job. There is no silent model or tracker fallback.

Example configuration, with public artifacts downloaded before offline execution:

```json
{
  "tracking": {
    "detector_weights": "/private/weights/yolox_s.onnx",
    "mode": "reid",
    "reid_manifest": "/private/weights/reid-manifest.json"
  },
  "legal": {
    "release": "/application/legal/2026-10-17",
    "cards": "/application/legal/rule-cards.json",
    "event_date": null,
    "operation_context": {}
  },
  "bounds": {
    "max_calls": 32,
    "max_tokens": 80000,
    "max_reinspections": 4,
    "legal_max_calls": 6
  }
}
```

The process must have OS-enforced outbound network denial, retaining loopback
access to the resident model. The runtime checks denial before opening media;
an environment flag does not authorize network access. Use only authorized
development allowlist sources. Reserved and jury recordings remain excluded
from configuration and model selection. Artifacts must be outside Git.

Each run creates a fresh `reasoning-<revision>/` directory. It preserves:

- `source-frames.json`: every source frame's original PTS, actual time base,
  normalized timestamp, source/oriented dimensions and rotation. Frame-rate
  multiplication is never used to reconstruct source time.
- `participants.json`: recording-local identities, association proposals and
  independent role hypotheses; appearance galleries remain private inference
  state and are excluded from visual prompts.
- `scan/reply-*.json`, observations, timeline and call receipts: actual local model
  responses, source IDs, image counts, token usage, latency and phase.
- `scan/view-transforms.json`: full-scene and participant-crop source rectangles,
  crop rounding, display orientation, resize/translation mapping and image hashes.
- Legal condition records, exact source references and skipped-rule coverage.
- `evidence/` and `evidence-association.json`: re-decoded source JPEGs without
  overlays or resize, original PTS/time bases and content hashes.
- `result.json` and `review.html`: provisional reviewable output. The HTML has no
  external dependencies or remote requests; open it locally for a human reviewer.

The bounded hierarchy uses at most 16 overview images, all overlapping 16-second
windows at a 12-second stride, up to four targeted inspections, then a visual
chronology/reconciliation pass. Every window records its actual supplied frame
IDs. Evidence tools also record the largest actual sample gap: a requested
cadence may be reduced by the image cap. Targeted inspection uses up to eight
source images and bounded crops, retaining the full scene. There is no motion
filter that suppresses static or slow scenes. These defaults require measurement
on the authorized GPU before making a latency or quality claim.

Observations may reference only frames and participants supplied in the current
request. Actor claims additionally require that participant to occur in a cited
frame's source-bound boxes. The application derives intervals from source IDs;
the model cannot invent timestamps. An interval is a sampled evidence envelope,
not an exact onset/offset claim. Crop IDs cannot masquerade as original frame IDs.
Overlap consolidation additionally requires the same actors/action, temporal
overlap and shared source evidence. Distinct occurrences stay separate.

Coverage records completed overlapping windows, unexamined and unclear ranges,
pending refinement and budget exhaustion. Sparse samples never establish
continuous visibility or a missing step. Empty predictions, incomplete processing
and unknown legal conditions cannot become a clean negative. The rich contract
keeps execution (`completed`/`partial`) separate from `supported_violation`,
`no_violation_observed`, `insufficient_evidence` and `not_applicable`.

`append_correction` writes a new exclusive immutable sidecar with reviewer,
independent review scope, original result hash, source hash, target ID and parent
revision. It never edits a prior review or promotes geometry, identity, roles,
legal interpretation or any training target by association. Consumer tools must
show the correction lineage together with the original model proposal.

Synthetic tests exercise VFR source provenance, rotated crops, real image
serialization through the loopback HTTP adapter, invented-reference rejection,
partial coverage, conservative event merging and correction lineage. They do
not measure participant accuracy, event precision/recall, legal correctness,
27B quality or the under-300-second user workflow. Those require executed runs
and suitable independent human reference labels.
