# Proposal: train actor-bound facts, then scan the complete recording

Research checked on 17 October 2026 using direct GitHub CLI/API searches and
primary papers, repositories and documentation. Agent Reach was not used. This
document covers steps **3, training visual recognition**, and **4, scanning the
whole clip**, from the agreed six-step pipeline. It is a proposed experiment,
not an implemented or validated recognizer.

## Recommendation

After the [labeling/tracking handoff](handoffs/01-visual-labeling-and-person-tracking.md)
produces reviewed targets, run **supervised multimodal LoRA on the existing
Qwen3-VL-8B-Instruct**. Teach it to map chronological full-scene/person views to
short, actor-bound role/action records. Keep its visual encoder and projector
frozen for the first bounded experiment. Compare against the same untuned model
with identical tracks, frames and prompts. Training success means fewer incorrect
people/actions on separate recordings, not a lower text loss or better JSON.

Use **VideoPrism-B with a frozen backbone and trained classification head** as a
small, separate diagnostic baseline for reviewed role/action classes. It is not
another required production service. It tests whether a dedicated video encoder
already separates the actions more reliably than the VLM. Do not build a large
temporal network, train a text LLM from scratch or start GRPO as the first fix.

This is a design judgment: our immediate outputs include roles, two participants,
visibility and evidence references, and an 8B inference service already exists.
Qwen's official trainer supports multi-image/video supervision and language
attention LoRA. That makes a bounded SFT experiment practical; it does not prove
that frozen visual features contain every subtle cash-operation cue. If reviewed
errors persist because the objects/motion cannot be resolved, change acquisition,
sampling or the visual recognizer instead of rewarding longer explanations.
Sources: [Qwen training framework](https://github.com/QwenLM/Qwen3-VL/tree/96588727e44c78b25ba03ea03b8e12f7e64fd0da/qwen-vl-finetune),
[VideoPrism classification example](https://github.com/google-deepmind/videoprism/blob/c6eba0ece3dd49a24ffc44582966997a4a59f1d8/videoprism/colabs/videoprism_video_classification_demo.ipynb).

## What the open-source work actually solves

| Primary project | Relevant capability | Decision for this project |
| --- | --- | --- |
| [CVAT](https://github.com/cvat-ai/cvat), [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX), [trackers](https://github.com/roboflow/trackers), [SAM 2](https://github.com/facebookresearch/sam2) | Review tracks/attributes, detect person boxes, associate IDs, propagate prompted masks. | Use the local workflow in the updated handoff for steps 1–2. Semantic cashier/customer labels still require evidence and review. |
| [Qwen3-VL fine-tuning](https://github.com/QwenLM/Qwen3-VL/tree/96588727e44c78b25ba03ea03b8e12f7e64fd0da/qwen-vl-finetune) | Supervised conversations with images/video; LoRA targets attention projections. Apache-2.0 repository. | First bounded adaptation experiment on the existing 8B model. |
| [VideoPrism](https://github.com/google-deepmind/videoprism) | Frozen video embeddings; official example trains an attention pooler/projection with single-label CE or multilabel BCE. Base encoder is 114M parameters, with 16-frame 288×288 inputs. | Dedicated action baseline. Uses JAX/Flax; isolate it from the production Python environment. Code is Apache-2.0; repository distinguishes other materials as CC-BY-4.0, while the selected HF model card declares Apache-2.0. Preserve both notices. |
| [VideoMAEv2](https://github.com/OpenGVLab/VideoMAEv2), [ActionFormer](https://github.com/happyharrycn/actionformer_release) | Pretrained video representation; action classification plus start/end localization from temporal features. Both repositories declare MIT. | Useful next architecture if measured short-action/localization errors dominate. Their benchmark features/heads do not supply our roles or bank-specific targets. |
| [MS-TCN++](https://github.com/sj-li/MS-TCN2) | Supervised temporal action segmentation from feature sequences; MIT code. | Study temporal smoothing/segmentation. Its benchmark's single-label sequence convention needs adaptation for simultaneous actions and unknown ranges. |
| [MMAction2](https://github.com/open-mmlab/mmaction2) | Apache-2.0 toolbox for action recognition/detection. | Useful recipes/evaluation reference. Its current VideoMAEv2 integration documents testing only; do not promise fine-tuning through that config. |
| [Video-R1](https://github.com/tulerfeng/Video-R1), [TRL GRPO](https://huggingface.co/docs/trl/main/grpo_trainer) | Reinforcement learning for multimodal answers with computed rewards. | Research reference, deferred experiment. Generic VLM support does not establish exact Qwen3-VL-8B video compatibility. Video-R1's GitHub API reports no standard repository license; inspect its components/weights before reuse. |

The earlier [VideoMAE repository](https://github.com/MCG-NJU/VideoMAE) explicitly
uses CC-BY-NC-4.0 for most of the project. Do not confuse that with VideoMAEv2's MIT
code, or infer checkpoint/data permissions from a training framework's license.

[AVA](https://research.google.com/ava/) is a useful annotation precedent: actions
are attached to people in space/time and can overlap. It is not a cashier-role
dataset. In the repositories examined, I did not verify a ready-made checkpoint
that reliably labels our cashier/customer roles and RK cash-operation violations.
That is a bounded search result, not a claim that no such project exists.

### Closest retail-specific evidence

[RetailAction](https://huggingface.co/datasets/standard-cognition/RetailAction)
provides real retail interaction annotations for taking, putting and touching
products, including spatial locations and action intervals. Its multi-camera
customer/product task is a useful labeling/localization reference, but does not
supply bank cash counting, employment roles or RK compliance targets. Its card
declares a custom license; it is not a default training-data dependency here.

[People in Public / PIP-175k](https://visym.github.io/collector/pip_175k/) includes
object transfers and purchases involving a cashier and declares CC-BY-4.0. It is a
candidate source of generic interaction examples if our reviewed class coverage
is inadequate. A `person_purchases` target does not become a cashier employment
label or evidence of legally completed service; inspect exact actor definitions
before any mapping. No public dataset is downloaded in this research.

An apparently relevant [cashier-safety POC](https://github.com/nowshek28/guardian-vision)
uses predefined cashier/customer/table zones in its documented workflow and trains
a danger/no-danger hand-image classifier. That is not evidence that it learns
cashier/customer roles from service interactions. Do not replace our existing role
error with a fixed-position assumption and report the problem solved.

Earlier [IBM checkout-activity work](https://research.ibm.com/publications/detecting-human-activities-in-retail-surveillance-using-hierarchical-finite-state-machine)
uses primitive visual activities and a hierarchical finite-state model. It supports
the design pattern of recognizing observations before evaluating a transaction
sequence; it does not provide a validated open bank-compliance checkpoint. These
domain sources reinforce the need for our own reviewed interaction/role labels.

## 3. Exact supervised experiment

### Reviewed targets and split

There are 31 eligible development recording groups and nine reserved recordings.
The 31 annotation files currently contain templates, not a reviewed training set.
The existing model diagnostic uses one human-corrected recording across three
dependent context variants; both 8B and 27B still made a confident wrong role
assignment. Keep that recording regression-only while it evaluates the fix.
See [measured diagnostic](model-size-diagnostic.md).

Before exporting training examples:

1. Resolve duplicate/session continuity and freeze source hashes and group IDs.
   From eligible development groups, target approximately 60% train, 20% validation,
   20% internal test, assigning whole sessions together. Actual counts depend on
   resolved sessions and exclusions; do not promise an 18/6/6 independent split
   before that check. Keep the nine reserved recordings and all jury data untouched.
   The 31 development recordings have already been explored by earlier baselines;
   this new internal split is a development check, not a pristine unseen benchmark.
   The reserved set remains the later locked evaluation after all selections.
2. Require reviewed track continuity, roles, visible actions, intervals, source
   frames and review provenance. The exporter fails on drafts, unresolved ID joins
   or conflicting corrections. A separately reviewed, deliberately ambiguous view
   can teach `unclear`; an unreviewed disagreement cannot become that target.
3. Publish an aggregate class-by-group table. As a proposed pilot gate, each learned
   positive action needs examples from at least three independent training groups
   and two validation groups. This is an engineering floor, not a sample-size
   guarantee. Unsupported classes remain unvalidated; do not oversample a single
   recording and call it independent coverage.
4. Fully review some background intervals and role/action near misses. A clip's
   supplied negative verdict is not an exhaustive action annotation. Do not mark
   every unlabeled frame as background.

Initial visible vocabulary: `cashier/customer/unclear`; `hand_over_cash`,
`receive_cash`, `count_cash`, `hand_over_document`, `enter_area`, `leave_area`,
`other_visible_action`, and reviewed uncertainty/visibility states. Definitions
must specify observable start/end cues and actor/recipient conventions. Permit
overlap: a person can handle cash while moving. Cash direction is a relation
between known participants, not an automatic acceptance/payout classification.
Service-start/end cues are observations; actual service completion stays unknown
when the sequence cannot establish it. Do not train legal conclusions in this run.

### Model inputs and targets

Create three task types from the same reviewed manifest:

- **Role:** six chronological source times spanning relevant service interactions,
  each with a full-scene view and the target person's crop: 12 images. Include the
  target box, work-area geometry and anonymous ID as metadata. Use earlier/later
  context when the local movement alone does not establish the role.
- **Action:** four-second windows at two source times per second, with a full
  scene and target crop at each time: eight times, 16 images. Keep hands, exchanged
  objects and counterpart visible through a padded actor/pair crop; do not crop
  away the receiver. Longer actions use overlapping windows and boundary flags.
- **Interaction/phase:** ask which supplied tracks exchange an observable object,
  and which visible service cues occur. Use the same bounded image layouts and
  private longer-context packet where required. Train `unknown` when the transaction
  type or completion cannot be established visually.

Each image has a distinct view ID linked to an unchanged source frame ID and crop
transform. Coordinates and times come from the decoder/manifest. Model outputs
choose supplied frame IDs; application code resolves PTS. Randomize anonymous ID
names during training and permute input track ordering consistently, so `p01` does
not become a synonym for cashier. Do not include descriptive filenames, supplied
positive labels/points, law text or reference answers in input metadata.

For every task, the target is a short fact record: target track, role/action or
uncertainty, other participant if known, interval boundary frame IDs, clipped-edge
flags, visibility and supporting source frame IDs. Use concise labels, not a long
generated reasoning narrative. A synthetic shape example, unrelated to our footage:

```json
{
  "actor_id": "p07",
  "action": "hand_over_cash",
  "other_actor_id": "p12",
  "start_frame_id": "f0160",
  "end_frame_id": "f0168",
  "continues_before_window": false,
  "continues_after_window": false,
  "evidence_frame_ids": ["f0160", "f0164", "f0168"],
  "visibility": "observed"
}
```

Augment only from reviewed data: temporal offsets that retain all target evidence,
crop padding and ID permutations. Recompute interval clipping and references after
every transform. Wrong-actor examples should ask about a different actual track
with its reviewed answer. Do not fabricate a cashier label by swapping words, or
use reversed-video direction labels without checking their meaning. Keep all
derivatives in their original session split.

### Training mechanics and budget bound

Use the official Qwen trainer as the starting implementation, pinned to
`96588727e44c78b25ba03ea03b8e12f7e64fd0da`; inspect its processor and adapter-save
behavior before use. Its generic launch examples are not a tested command for this
project. Disable external reporting, Hub uploads and private completion logging;
all private training runs offline after dependencies/weights are staged.

Proposed first run:

| Setting | Value |
| --- | --- |
| Base weights | `Qwen/Qwen3-VL-8B-Instruct`, revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| Trainable weights | Language attention `q_proj/k_proj/v_proj/o_proj` LoRA only; rank 8, alpha 16, dropout 0.05 |
| Frozen | All base weights, visual encoder, visual merger/projector, embeddings and output head |
| Precision/optimizer | BF16, AdamW, learning rate 5e-5, weight decay 0.01, gradient norm cap 1 |
| Batch | One example, accumulate eight microbatches; gradient checkpointing, no packing initially |
| Sequence | At most 16 images, initially 196,608 pixels/image; total input/output at most 8,192 tokens, answer budget 768 |
| Loss | Mean next-token cross-entropy on reviewed assistant-answer tokens only; all input/image/padding labels masked to -100 |
| Duration | First pass: at most 30 optimizer updates and one dataset pass, whichever ends first; one measured extension up to 60 total updates/two passes only if validation improves |
| Checkpoints | Before training, then every ten updates and at end; select on validation, evaluate internal test once after selection |

These are proposed starting settings, not paper-derived optimums. Count actual
trainable tensors and assert no visual/base tensors receive updates. Verify loss
masks and image order on a synthetic batch, then compare frozen-weight hashes
before/after. Admit only examples that fit the measured token budget; resample or
reject an oversized example rather than truncating image tokens or evidence.
The [TRL SFT documentation](https://huggingface.co/docs/trl/main/sft_trainer)
explicitly identifies image-token truncation as a training hazard.

The previous 12-image inference check is not a 16-image backpropagation benchmark.
Future execution starts with one training step and one evaluation step on the
authorized A10080, with one resident model; measure peak memory, step time and
serialization/reload correctness. If it fails, stop the experiment and record the
failure instead of silently dropping to a smaller main model or renting more GPUs.
Use the existing total-project budget and cleanup runbook; no new allocation or
training is authorized by this research document.

### Dedicated video baseline

Use `google/videoprism-base-f16r288`, revision
`be719a406d563b66f0ac969e7c94bab8e997c81a`, with the official frozen-backbone
attention-pooler/projection example. For actions, sample 16 frames over two seconds
(8 FPS), starting a window every second; run full-scene and padded actor/pair views
as separate feature streams and join their pooled representations. For roles,
sample 16 frames over a longer reviewed service context instead of a departure-only
crop. This two-view/domain adaptation is our proposal, not a ready bank classifier.

Train a role softmax with cross-entropy and an action sigmoid head with binary
cross-entropy. Mask unknown/unreviewed class-time cells out of the loss; absence
targets require exhaustive review for that interval. Start head learning rate
1e-4, batch eight, at most 20 epochs, validation every epoch, stop after three
epochs without improved validation macro F1. Keep the backbone frozen and use the
same session split. No legal outputs and no RL reward are involved.

Initially compare role/action classification on reviewed windows. For an event
benchmark, choose class thresholds on validation, merge consecutive overlapping
positive windows only for the same actor/action, and report their coarse boundary
resolution. C uses denser, shorter input than A/B; include a matched-sampling
comparison before attributing its gains to the encoder rather than sampling.

Evaluate this as a benchmark competitor before proposing a second production
component. Its shorter, denser windows test motion that sparse VLM frames may miss;
its finite label head cannot discover an unseen action category. If it clearly wins
the action/latency comparison, propose routing action proposals through it and
retaining the ≥8B VLM for contextual roles/relations. Do not declare that switch in
advance of measurements.

## 4. Whole-clip inference with persistent actors

Initial Qwen scan proposal, with a coverage ledger for decoded, sampled, inspected
and unresolved ranges:

1. Decode the entire source with PTS and orientation preserved. Detect/track people
   at a proposed 10 FPS, recording skipped ranges and uncertain segment links.
   This cadence is a starting point to measure against reviewed tracking, not a
   guarantee that crossings or quick movements are captured.
2. Scan overlapping 16-second windows, stride 12 seconds, using 16 chronological
   full-scene frames at 1 FPS. Ask for ordinary actions, interactions and uncertainty
   on supplied tracks; no legal category is required to propose an event. Cover
   recording endpoints explicitly. A negative coarse window does not prove that
   no short action occurred between sampled frames.
3. Establish each role with the 12-image role task and store the predicted role,
   evidence interval and uncertainty against the track segment. Reuse it across
   windows; never transfer it over an uncertain join. New contradictory evidence
   triggers wider-context re-evaluation or uncertainty. A cached model prediction
   is not human confirmation, and repeated agreement is not independent evidence.
4. Propose closer review around visible exchanges, area crossings, track gaps,
   uncertain roles and coarse action candidates. Geometry can propose an area
   crossing even if the VLM misses it. Include a fixed, reproducible sample of
   otherwise quiet intervals to measure proposal misses. Score proposal recall on
   all reviewed events separately from final recognition accuracy.
5. Inspect an eight-second neighborhood at 2 FPS. To preserve both scene and actor
   views within a 16-image call, use three four-second subwindows with two-second
   overlaps, each containing eight source times × two views. This is up to three
   calls, not one 16-image call containing 32 images. If a handoff/counting cue is
   shorter, inspect a narrower two-second interval at 8 FPS, using separate bounded
   full-scene/crop passes where needed. Record the extra calls and remaining gaps.
6. Emit fact records, then merge only compatible events on the same supported
   tracks and action/participant relation. Keep clipped boundaries and conflicting
   facts unresolved until adjoining evidence supports a merge. Frame membership,
   track validity and ordered PTS are mandatory checks; they do not themselves
   verify that the label is visually correct.
7. Build the transaction timeline from these records. Acceptance/payout, service
   ongoing/finished and unknown context are separate fields, each with supporting
   observations. Do not infer service completion solely because a person leaves.
   Pass this timeline to later rule checks; steps 5–6 of the agreed pipeline remain
   separate from this recognizer.

This scan can miss actions between samples. Until proposal recall and dense-review
coverage pass, it cannot certify that counting or document delivery never happened.
An omission requires visibility of the full relevant opportunity, with adequate
temporal resolution; occlusion, uninspected intervals or truncation mean unknown.

For a duration D > 16 seconds, coarse calls are approximately
`ceil((D - 16) / 12) + 1`. A 120-second clip needs ten coarse calls, plus role calls,
three calls per fine neighborhood and any dense/context expansion. Measure actual
latency for each shape before setting a total call budget. Reserve time within the
existing five-minute job deadline; budget exhaustion records uncovered ranges and
an unresolved/failed analysis rather than silently producing a normal verdict.
Do not extend the public API contract in this research phase.

## Why reinforcement learning is deferred

In supervised training, the reviewed answer supplies the learning target directly.
In GRPO, the model generates several answers to each input; a reward function
scores them and training favors the better-scored answers. A reward still needs a
trustworthy way to determine which person/action/interval is correct.

[Video-R1](https://arxiv.org/html/2503.21776v4) demonstrates temporal reasoning RL,
using an initial 165k-example supervised stage and a 260k-example image/video RL
collection. Its rewards use reference answers; its temporal method compares
ordered and shuffled frames. That supports the method's plausibility, not a
claim that 31 bank recordings can reproduce its gains or costs. It does not repair
a mislabeled cashier/customer reference automatically.

If SFT later plateaus with enough independent reviewed targets, test a narrow
GRPO follow-up on structured facts. For one annotated event, a proposed reward is
zero for an invalid frame/track, incorrect actor/role or a false asserted action;
otherwise combine exact action correctness with temporal IoU and checked evidence
membership. Use separately annotated uncertainty and exhaustively reviewed empty
intervals to score abstention/background. Evaluate event recall and answer coverage
so predicting `unclear` everywhere cannot win. Evidence membership is only a
provenance signal; its semantic sufficiency still requires reviewed references.

Do not reward valid JSON, persuasive legal prose, longer reasoning or agreement
with the current model as substitutes for correct facts. GRPO requires multiple
completions per sample; T-GRPO also evaluates shuffled sequences, adding work.
Exact Qwen3-VL video support and memory fit require a smoke test; [TRL's supported
VLM list](https://huggingface.co/docs/trl/main/grpo_trainer#training-vision-language-models)
does not promise every model. No RL implementation is proposed for the next build.

## Evaluation and decision after the experiment

Compare **A: untuned 8B with reviewed-quality tracks/context**, **B: the same inputs
with supervised LoRA**, and **C: frozen VideoPrism plus trained heads**. Also run an
oracle-track versus automatic-track comparison: this separates recognition errors
from ID switches. Do not attribute a simultaneous tracker/input/model change to
training. The previous 27B result remains a diagnostic, not a promoted annotator.

Report per recording/session group and per class:

- Role confusion, including confident cashier/customer swaps; answered-role
  precision and coverage. Count abstentions and failed jobs separately.
- Action precision/recall and false events per video minute; actor and recipient
  must match for an event to count as correct. Match intervals one-to-one at
  temporal IoU 0.5, also report 0.75 and start/end error.
- Proposal recall before fine recognition, track ID switches/fragments on reviewed
  ranges, uncertainty propagation over gaps, and source-reference validity.
- Supported transaction type/phase accuracy and coverage, full-clip runtime,
  calls, peak VRAM and measured spend. Several crops/windows from one recording
  remain one dependent source group.

Proposed pilot acceptance: zero confident actor swaps on the reviewed regression
packet; zero invalid source/track references; at least 95% candidate recall on
reviewed events; and B must reduce wrong-actor events and improve actor-correct
event F1 on separate groups without worsening false-event rate or hiding errors
through extra abstention. These are targets, not current results. With few groups,
report counts and uncertainty; zero observed errors does not prove a low population
error rate. Reserve the internal test for the selected checkpoint; if it fails,
do not retune repeatedly against that test.

Also compare with a fixed-position/area baseline and report camera/session
coverage. If every recording shares one setup, neither a random window split nor
good internal scores establishes that the model works at another bank/camera.
Collect separately reviewed setups before making that claim.

If quality fails, classify the error before the next change: wrong reference,
ID switch, missing visual context, low object visibility, unseen action or model
confusion. Obtain the missing reviewed examples or improve the implicated visual
component. Model size or RL is not an automatic escalation path.

The next executable milestone remains the reviewed labeling/tracking pilot.
Then export the frozen split, measure A, run the bounded B/C comparison, and select
only on measured actor/action quality and runtime. No code, model, training dataset,
paid allocation or runtime behavior changed during this research.

## Evidence register

The project source register is extended in
`../.context/verify/domain-research-sources.json`, under
`pattern_learning_20261017`; it contains checked repository commits, license
metadata, source-file hashes, queries and claim assessments. Small claim clusters:

- **ev-pattern-01 — reusable tracking/review:** the verified CVAT/YOLOX/ByteTrack/
  trackers/SAM 2 sources support separate tools for geometry and review, not role
  truth. High confidence about features; bank-footage quality remains unmeasured.
- **ev-pattern-02 — feasible supervised adaptation:** Qwen's trainer selects the
  Qwen3-VL dense model class and adds attention LoRA; official data examples accept
  image lists/video. High confidence in source capability; exact local training
  environment and our quality gains remain unmeasured.
- **ev-pattern-03 — dedicated video learning:** VideoPrism's official classifier
  trains a small head with the backbone frozen; ActionFormer learns categories and
  boundaries from temporal features. High confidence about method; transfer to
  our participant-sensitive cash actions is an experiment.
- **ev-pattern-04 — RL requires valid supervision/reward:** Video-R1's paper uses
  reference-checked rewards and supervised initialization; TRL documents multimodal
  GRPO and model compatibility limits. High confidence about method; deferring RL
  is our data/budget judgment.
- **ev-pattern-05 — present readiness:** repository diagnostic receipts and the
  labeling handoff establish the missing reviewed targets and persistent tracks.
  High confidence about local state; no domain accuracy claim is inferred.
- **ev-pattern-06 — retail transfer limits:** RetailAction and PIP provide related
  interaction labels; the cashier-safety POC uses predefined zones; IBM provides
  an earlier primitive-action/sequence method. High confidence about these
  documented tasks; none validates our cashier-role or legal targets.
