# Readable saved-prediction review

`mechanic_review.py` is retained only as a source-preserving adapter for existing
historical private review layouts. It performs no inference, selects no model and
never changes original predictions or cited evidence. Current API review uses the
single pipeline's immutable result plus `investigation_report.py`, following
[report.md](../report.md). The historical layout and receipts below retain their
original source/model identity and do not validate the current 8B/Laya runtime.


This standalone tool creates a new human-local presentation of already saved v2
results. It makes no model calls and changes no API, model, prompt, law, source,
prediction, correction or approval. The exact original result remains available
as a separate byte-preserved download. Its historical checks are separate from
current pipeline, real-model and deployment acceptance.

## Human review layout

The page starts with the saved outcome, incomplete inspection and unresolved
questions. It then shows complete source playback, independent participant
proposals and operational roles, actions with actor/recipient links, event
candidates, source evidence, temporal/rule coverage, and rule conditions. Files
and technical provenance follow these sections. Large raw JSON and appearance
embeddings are not embedded in the reading flow.

Each source-time button seeks the full recording. Sampled boxes preserve the
recording-local IDs and are drawn only near an actual detection sample, with no
interpolation or new association. Unmatched-origin legacy proposals are retained
in a separate expandable table; they are not silently deleted or merged.
Reflections, unknown reflection ownership, unassociated geometry and unresolved
identity remain separate records. A model proposal count is never a physical
person count.

Multiple people can share the same role. A person can have distinct, uncertain or
conflicting role hypotheses at different times. Every saved role hypothesis keeps
its observation ID, origin, review state, interval, supporting frame IDs and any
uncertainty supplied by the original result. Missing values remain missing/null.
Only compatible references to the *same observation ID* are enriched; conflicting
records survive separately. No role interval grows to fill visibility gaps.

An unresolved role is displayed as unresolved. The tool does not assign a
cashier/customer pair, use clothing, gender, image side or coordinates to choose
roles, or infer permanent employment. Saved geometry approval, a reflection fact
and a role hypothesis never approve one another. Presentation checks do not
establish improved multi-person tracking or role/action recognition.

## Additive JSON contract

`review.json` uses `schema_version: "forte.review-packet/1"`. It is a local review
projection, not a new public/jury API contract and not a replacement v2 response.

| Field | Meaning |
| --- | --- |
| `original_prediction` | Exact original JSON file and its SHA256 |
| `source` | Saved source fingerprint, duration and frame count |
| `processing` | Original job/execution/assessment/review/error; separate presentation state |
| `summary` | Proposal/observation counts; physical-person count stays null |
| `people[]` | Original participant ID, identity state, sampled envelope, source frame/segment IDs, tracking basis, role hypotheses, conflicts and gaps |
| `people[].role_hypotheses[]` | `claim` with saved observation fields plus `record_sources` indicating registry/timeline locations |
| `views`, `geometry_only`, `unresolved_identity`, `role_conflicts` | Independent view, geometry, identity and conflicting-role scopes |
| `observations[]` | Original role/action/interaction/context records, source fingerprint, transaction phase/localization, time bounds, actors, recipients, evidence and uncertainty |
| `findings[]` | Original event candidates, original assessments, observation/legal links and evidence metadata |
| `evidence_frames` | Frame-ID lookup of local image path/hash, original PTS/timebase/timestamp and image origin label; populated by packet generation |
| `coverage` | Saved timeline state, scheduled/examined/unexamined/unclear intervals and every rule coverage state |
| `legal[]` | Saved condition plans/results, interpretation/review state, official citations, exceptions, prerequisites and limitations |
| `unresolved_questions`, `limitations`, `legal_limitations` | Original unresolved facts and constraints |
| `metrics`, `provenance`, `projection_limits` | Processing/source identities and explicit limits of the projection |

`processing.assessment` always retains the original value. A separate
`presentation_state: "incomplete_inspection"` and prominent warning prevent an
unfinished result from being presented as whole-recording clearance. Failed or
processing jobs receive no invented assessment. A saved supported event remains
visible alongside unrelated incomplete inspection. Unexamined, unclear or
output-limited intervals trigger the warning even if an execution label says
completed. Event support links navigate to the original observation and rule
assessment IDs; unavailable references stay visible without broken anchors.

`original-result.json` contains the exact input bytes. `manifest.json` records its
fingerprint, the renderer source hash, the previous review hash, every linked
asset's SHA256, and zero new model calls. An image supplied through the API must
match its original evidence hash. A persisted resized scene view must match the
archived run inventory and is labelled separately from an original API JPEG.
Image metadata keeps the original frame ID, source PTS, time base and timestamp.

## Local reproduction

Use the preserved mechanic-validation run layout, containing `inference-inputs`,
the three restored case archives and the original `gpu-review-v4` source packet.
Only saved neutral/hash development members are accepted, before source bytes
are opened. The generator verifies source hashes, frame-table source binding,
original-result archival hashes and cited image hashes. Existing output
directories are refused, including partially generated ones. Keep every review
revision, including intermediate drafts.

```sh
RUN="$HOME/.local/share/forte26/mechanic-validation/20261018-01"
env PYTHONPATH=src /usr/bin/sandbox-exec \
  -p '(version 1)(allow default)(deny network*)' \
  /path/to/existing/python -m forte.mechanic_review \
  --run-root "$RUN" --output "$RUN/gpu-review-NEW-VERSION"
```

No dependency installation, GPU host or resident service is needed. All input,
output and linked private media must remain outside Git. Each case keeps full
playback/original-source links, every earlier cited JPEG, the immutable original
JSON, a copy of the previous human-review template and the original baseline
packet link. Existing human judgments are never relabelled or fed into inference.
Only the human opens the local packet; no remote browser, screenshot or multimodal
tool may inspect private footage or descriptions.

## REA adaptation boundary

The earlier external PRODUCT/REA research recorded Axxon/Mikshi public evidence
separately from recommendations and unknown internals. Those historical research
documents are not active architecture guides in this checkout. Their findings informed scoped
timeline navigation, independent human assessment, source/derived-media separation
and explicit track/configuration dependencies. They do not establish either
vendor's staff/customer role classifier, model, training or identity accuracy.

This tool adopts the readable evidence and investigation organization. Role/action
inference follows the selected frozen pipeline; semantic acceptance requires a
newly identified runtime evaluation and independent local human judgments.
No vendor architecture or recognition capability is inferred
from screenshots, marketing or this renderer.

## Validation scope

Generated fixtures verify independent people, shared/null/conflicting time-scoped
roles, actor/recipient/source links, reflection ownership, partial/failed states,
escaped text, JavaScript-safe serialization, multiple overlay IDs and source
seeking. File-level fixtures verify byte preservation, prior images, local links,
fresh directories, reserved exclusions and corrupted-result/evidence rejection.
These are presentation/provenance checks, not detection or role accuracy metrics.
