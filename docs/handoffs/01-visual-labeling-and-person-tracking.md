# Handoff prompt: correct visual labels and person tracking

You are taking over implementation of the first two stages of the ForteBank
Datathon video pipeline. Execute the work below; deliver a working annotation and
tracking workflow with reviewed reference cases. Do not stop at another proposal.

The immediate problem is incorrect cashier/customer assignment. Earlier reports
attached a cashier obligation to the wrong person. Both tested VLMs still make
confident role errors. We need trustworthy visual labels and person continuity
before training or legal detection can improve.

**Scope: implement these two stages only.**

1. Label visible people, their roles, work areas, actions and intervals correctly.
2. Follow the same people through a clip, preserving IDs when continuity is
   supported and recording uncertainty when it is not.

Do not train a model, issue violation labels, change the public jury API, replace
the production detector, expand legal retrieval or build the product frontend.
The resulting labels must be usable for later role/action training and evaluation.
The subsequent steps 3–4 proposal is in `docs/role-action-training-research.md`;
read its target requirements, but do not execute training under this handoff.

**Workspace and existing work**

- Product repository: `/Users/itsaibarr/conductor/repos/fortebank-datathon-26`.
  Handoff base is `cdbe640`; inspect the current branch and changes before editing.
  Preserve any newer work. Do not reset to that commit.
- Read `AGENTS.md`, `CLAUDE.md`, `SPEC.md`, `tasks/todo.md`,
  `docs/legal-and-annotation.md` and `docs/model-size-diagnostic.md` first.
- Reuse `src/forte/video.py` for source timestamps, orientation and frame IDs.
  Inspect `src/forte/annotations.py` and `tests/test_annotations.py` before extending
  the annotation format. Keep the existing visual/legal separation.
- At this checkpoint, 69 tests pass. The legal corpus and review contracts exist,
  but the 31 development annotation files are empty templates. No reviewed
  training dataset, persistent person tracker or confirmed legal-positive control
  exists.
- In the one-recording diagnostic, across three dependent context variants, 8B
  agreed with the existing correction in 0/3 and 27B in 1/3. Each made one confident
  conflicting assignment. Neither model is a trusted annotator or reviewer.

Private working root:
`/Users/itsaibarr/.local/share/forte26/development-rehearsal`

Use these existing private inputs; do not print their scene contents:

- `batch-selection.json`: the 31 eligible development recording groups and neutral
  source names. Use group/hash/split fields for eligibility. Supplied binary labels,
  original descriptive filenames and supplied points must not guide visual labeling.
- `annotation-review/sources/clipNNN.mov`: neutral source copies. Verify each hash
  against its recording group before deriving annotations.
- `annotation-review/first-milestone-review.json`: the three-case review packet,
  original user corrections and claim-specific adjudication. Preserve it.
- `annotation-review/two-layer-review/index.json` and adjacent JSON files:
  source-bound draft templates. Reuse or migrate them explicitly, with backups.
- `role-comparison-20261017/reference.json`: existing role-correction reference and
  source/frame provenance. Preserve this diagnostic recording as regression-only,
  excluded from future training while it is used to evaluate the fix.

The archive has 40 unique recordings: 31 development and nine reserved recordings.
Use only the development allowlist. Do not open the reserved recordings or jury
footage for this task. Keep duplicates and continuous recording sessions together
in any later split. Do not infer session boundaries or independence from filenames.

**Find and reuse GitHub projects directly**

Use GitHub CLI and primary repositories. The user explicitly excludes Agent Reach
for this work; that instruction overrides older research defaults in project docs.
Search before implementing an annotation tool or tracker from scratch:

```bash
gh search repos --topic multi-object-tracking --sort stars --limit 20 \
  --json fullName,url,updatedAt
gh search repos annotation --topic video-annotation --sort stars --limit 20 \
  --json fullName,url,updatedAt
gh search repos '"action recognition"' --match name,description --sort stars \
  --limit 20 --json fullName,url,updatedAt
gh repo view cvat-ai/cvat --json nameWithOwner,url,licenseInfo,isArchived
gh repo view roboflow/trackers --json nameWithOwner,url,licenseInfo,isArchived
gh api repos/roboflow/trackers/commits/HEAD --jq .sha
gh api repos/roboflow/trackers/readme -H 'Accept: application/vnd.github.raw+json'
```

Treat search ranking as discovery, then inspect code, current docs, releases,
checkpoint terms and the relevant feature's availability. Record exact revisions
and artifact hashes. These projects were checked on 17 October 2026:

| Project | Use here | Boundary |
| --- | --- | --- |
| [CVAT Community](https://github.com/cvat-ai/cvat) | Self-hosted video review, box tracks, interpolation and attributes; MIT core. | Humans correct IDs, roles and actions. Preserve PTS in our sidecar; CVAT frame numbers alone are insufficient. |
| [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) | Local person-box detector; Apache-2.0 code. | Separately pin/check checkpoint terms and class mapping. It detects people, not cashier employment. |
| [roboflow/trackers](https://github.com/roboflow/trackers) | Apache-2.0 implementation of ByteTrack and other motion/association trackers with a common interface. | Feed local detector results. Its example's hosted inference path is unnecessary. Appearance/ReID branches are not included in these implementations. |
| [ByteTrack reference](https://github.com/FoundationVision/ByteTrack) | MIT reference implementation/paper for association and baseline comparison. | Tracking IDs can switch; no cashier/customer classifier is supplied. |
| [SAM 2](https://github.com/facebookresearch/sam2) | Apache-2.0 code/checkpoints for prompted video segmentation and local correction proposals. | Propagation can drift; masks/boxes and joins still need review. Run separately and import proposals. |
| [Label Studio](https://github.com/HumanSignal/label-studio) | Apache-2.0 alternative for custom annotation tasks. | Keep as fallback if the pilot exposes a specific CVAT limitation; do not deploy both by default. |

Recommended baseline: **local YOLOX person boxes → ByteTrack through
`roboflow/trackers` → self-hosted CVAT Community review → existing private
annotation schema**. Use standalone SAM 2 only where correction propagation helps.
This recommendation has not been installed or benchmarked on our clips.

CVAT's current [integrated SAM 2 tracker documentation](https://github.com/cvat-ai/cvat/blob/develop/site/content/en/docs/annotation/auto-annotation/segment-anything-2-tracker.md)
limits that feature to Online/Enterprise. Do not promise a free Community
integration or upload private footage to CVAT Online. Community can review imported
proposals without that feature. Keep the [CVAT track export](https://github.com/cvat-ai/cvat/blob/develop/site/content/en/docs/dataset_management/formats/format-cvat.md)
and source-PTS sidecar together, and verify a round trip including occlusion,
outside/keyframe flags and mutable role attributes.

[BoxMOT](https://github.com/mikel-brostrom/boxmot) is useful for comparing richer
tracking/ReID approaches, but its code declares AGPL-3.0. [SAM 3](https://github.com/facebookresearch/sam3)
uses the custom SAM License and gated checkpoints. Do not substitute either
silently for the baseline. Detector, tracker, annotation tool and semantic role
classifier solve different tasks; a stable track is not a verified role label.

**1. Build correct visual reference labels**

Start with the existing three-case packet. Prepare source frames and short local
playback intervals that let a reviewer identify each person before, during and
after the relevant movement. Include full-scene context and person crops linked
to the same source frame. Do not show an isolated departure and ask the reviewer
to guess the role from that image.

For each reviewed interval, record:

- Anonymous person/track IDs and source-frame bounding boxes.
- Visible work-area boundaries, attached to the recording and source frames.
  Mark uncertain boundaries explicitly. A work-area outline is visual context,
  not a legal conclusion about what constitutes a workplace.
- Role: `cashier`, `customer` or `unclear`, with the interval where that assignment
  is supported, source-frame IDs and a private explanation of the visible basis.
- Observable actions: receiving or handing over cash, counting cash, handing over
  an unreadable document, entering/leaving a marked area and other visible actions.
  Link the giver and receiver when both are identifiable; otherwise leave the
  other participant unknown. Keep additional actions possible.
- Start/end timestamps, visibility limits and review status for every action.
  Label a visible service-end cue as an observation; mark service completion
  uncertain if the available sequence does not establish it.

Apply these labeling rules:

- Establish roles from the sequence of service interactions and scene context.
  Cash handling alone is insufficient because both parties can handle money.
  Screen side, clothes, standing, sitting or departure alone cannot establish a role.
- Do not force a unique cashier or customer for the entire clip. Link each role
  to a person, work area and supported interval. A new analysis window must not
  silently change that person's role.
- Require temporally separated supporting frames for a definite role and retain
  the surrounding playback interval. A cited frame does not automatically prove
  the label; the reviewer must check it.
- Distinguish `not_reviewed`, `not_visible` and `not_observed_in_reviewed_interval`.
  An occluded or unsampled action is unknown. A document is not a receipt unless
  the evidence establishes that. Do not invent document contents or amounts.
- Carry existing human corrections forward with their original certainty. A
  narrative correction is not yet a complete track annotation: bind it to the
  correct person and source frames. Do not manufacture boxes or certainty from it.
- Local model suggestions remain drafts. They cannot approve themselves or
  overwrite a human correction. Surface conflicts for specific local review.
- Do not label `violation`, `no_violation`, rule IDs or statutory intent here.
  The user must not be asked which RK law a clip violates or to supply its timestamp.

Prepare the review packet yourself. If human input is needed, ask a narrow visible
question using exact local frame/track choices, such as which outlined person is
performing cashier service or whether an ID switches between two people. Continue
independent preparation while that review is pending. Never invent a reviewer name
or mark a draft `confirmed` because a model returned valid JSON.

**2. Detect and follow people across the complete clip**

Implement one reproducible person-detection/tracking baseline. A detector locates
people; the tracking code matches their boxes across nearby frames using movement
and overlap. Start from the already researched ByteTrack approach with a
license-cleared person detector/checkpoint. Pin both code and weight revisions and
check their terms before downloading. Tracking does not assign employment roles.

- Process the complete recording, not just a reported timestamp or selected frames.
  Record the detection cadence and any skipped/undecodable ranges. Review dense
  source playback near crossings, handoffs, entrances and exits.
- Use recording-local anonymous IDs. Preserve them across analysis windows.
  Do not identify faces or link people's identities across recordings.
- Handle partial occlusion, people crossing, exits/re-entry and missed detections.
  An unsupported match must end a track segment or create an uncertain link;
  do not silently transfer the previous person's role to a new detection.
- Store proposed segment joins separately until continuity is verified. Record
  human splits/joins as corrections with provenance, rather than deleting history.
- Include full-scene review playback with IDs and optional separate crop sequences.
  Analysis overlays must be separate derivatives; keep original source frames
  unchanged and retain the exact source mapping.
- Treat automated boxes, interpolation and role suggestions as different origins.
  Human acceptance of a role does not automatically approve every box or track join.
- Run the baseline on the three-case packet first, correct it against reviewed
  tracks, then prepare tracking/annotation drafts for all 31 development groups.
  Do not build an unreviewed 31-clip training set and call it completed labeling.

**Artifact contract**

Use a versioned private track manifest linked to the existing annotation files,
or extend their schema with an explicit migration. Avoid incompatible duplicate
formats. At minimum preserve:

- Recording hash, neutral clip ID, duration, orientation and source dimensions.
- Frame ID, original PTS, normalized timestamp, box coordinates and coordinate
  convention. Prefer normalized `[x1, y1, x2, y2]` on the oriented full frame;
  record any scaling/crop transforms. Reject out-of-bounds or inverted boxes.
- Track/segment IDs, visibility, uncertain gaps, proposed/confirmed joins and origin.
- Role/action facts linked to those IDs, intervals and source frames.
- `draft`, `confirmed` or `rejected` status; actual reviewer, review time,
  correction history and private notes. Keep automatic scores separate from review.
- Explicit training eligibility and exclusion reasons. Drafts and unresolved
  role/identity intervals are ineligible; the known regression recording is held out
  of training. Freeze a recording/session-group split before any later training.
  Separately reviewed views that intentionally cannot establish a role/action may
  supply explicit abstention targets. Keep those distinct from unresolved review
  disagreements or uncertain identity joins.

Keep private derivatives under a new versioned directory inside the private root;
do not overwrite original reviews or media. Store all scene descriptions and
semantic corrections in the private review/annotation files. Only code, synthetic
fixtures, general instructions and aggregate measurements may enter Git or chat.

**Privacy, runtime and implementation constraints**

- Never send private videos, images, crops, captions or descriptions to an external
  AI service, hosted vision tool or shared memory. The remote coding agent must
  not inspect private frames through its own image/screenshot tools. Private visual
  inspection is by a local human or approved inference on our controlled machine.
  Model outputs remain drafts until independently reviewed.
- Development hosting on the dedicated Hyperstack VM in Canada and a $30 total
  project budget were already authorized. Do not request that permission again
  or treat the handoff as a fresh $30 budget. The last credit snapshot was $27.55;
  all VMs/volumes were deleted. Recheck live state, credit and rates if compute is
  needed, follow `docs/gpu-runbook.md`, arm bounded cleanup before allocation and
  delete only this project's recorded resources after preserving results.
- Credentials are outside Git under `~/.config/forte26`; never print them.
  Complete private inference with outbound networking disabled after public
  dependencies/weights are downloaded.
- Use the repository's Harness workflow and isolated dependencies. Follow relevant
  skill instructions, add meaningful failing tests before changing behavior and
  implement in small verified commits. Preserve unrelated work.
- Reuse a self-hosted annotation tool from the shortlist where it reduces review
  work. This permits a private local CVAT Community pilot, not product frontend
  development. Product UI-library selection remains outside this handoff.
  Do not install a hosted annotation service or send footage to public demos.

**Required deliverables and acceptance**

1. A reproducible command that creates private track proposals and a local review
   packet from an allowlisted recording, with hashes and complete source mapping.
2. A reviewed pilot using the existing three-case packet: checked person IDs, role
   evidence, visible action intervals and explicit unresolved items. The existing
   role correction must be attached to the correct track without reintroducing the
   cashier/customer substitution. Do not report success merely from agreeing words.
3. Track/annotation drafts for all 31 development groups, plus a private index of
   what is confirmed, pending, rejected or excluded. No holdout/jury data included.
4. Tests for source binding, box transforms, cross-window ID preservation, crossing
   people, occlusion, uncertain re-entry, role inheritance after an uncertain join,
   interval bounds and rejection of unreviewed training targets. Use synthetic
   media/fixtures in Git; keep real-content checks private.
5. Aggregate results: recordings processed, actual people/segments reviewed,
   confirmed versus uncertain roles/actions, observed ID switches and fragments,
   corrected errors, uncovered ranges, runtime and compute spend. Separate software
   checks, human annotation quality and tracking quality. Several windows from one
   recording are not independent evaluation cases.
6. Updated project instructions/checklist, a short reproducible runbook and a final
   handoff stating exactly what is usable for training and what remains unresolved.

Run the checks appropriate to changed code: `uv run pytest -q`,
`uv run ruff check .`, `uv run ruff format --check .` and package build when affected.
Verify real source associations locally; passing schema tests does not establish
that a person was labeled correctly.

If human review is unavailable, finish the runnable workflow, private proposals
and precise review packets. Report the reviewed-label gate as pending. Do not claim
that correct labeling, tracking quality or training readiness is achieved without
that evidence. Stop before model training and legal-violation classification.
