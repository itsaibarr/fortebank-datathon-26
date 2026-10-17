# Development rehearsal: mechanics work, detection quality does not pass

The real Qwen3-VL-8B BF16 model runs inside our controlled Hyperstack A10080 container with Docker networking disabled. Actual MOV uploads complete the required authenticated POST/GET flow. Returned JPEGs were decoded and checked against re-extraction from the unchanged uploaded source. This establishes transport and provenance, not semantic correctness.

Only the 31 proposed development recordings were transferred, under neutral names with verified SHA256s. Labels and supplied points stayed on the Mac and never entered prompts. The nine reserved recordings and jury videos were not used. The development/holdout split still needs local recording-session continuity review, so these are exploratory runs, not independent validation.

## Results against supplied binary labels

Both broad runs stopped after three consecutive failed jobs. They cover different partial subsets, so their headline rates are not a controlled comparison.

| Run/code | Tested/planned | TP | TN | FP | FN | Failed positive | Failed negative | Client p95 | Max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `1a56beb` | 28/31 | 0 | 8 | 0 | 9 | 6 | 5 | 29.52 s | 30.02 s |
| `cce5a1d` | 24/31 | 1 | 6 | 2 | 6 | 5 | 4 | 59.11 s | 66.72 s |

Failed jobs count against effective recall and overall accuracy. The second run has 1/12 effective positive recall and 2/12 supplied-negative false positives. One detected positive was 2.5 seconds from a supplied point; a nearby point does not prove the same action was detected. Categories and true intervals are not annotated.

Receipts are `.context/verify/baseline-1a56beb.json` and `.context/verify/baseline-cce5a1d.json`. Private predictions, JPEGs, full metrics and neutral-name mappings remain under `~/.local/share/forte26/development-rehearsal/`, outside Git and external AI tools.

## What the diagnostics established

- Output limits of 256/384 tokens caused actual truncated structured answers. Coarse/fine limits were increased to 512/768; verification remains 192.
- Coarse proposals must be separated from final rule confirmation. Unproven context can survive candidate refinement, but every required condition must pass final verification.
- Model-selected start/end frames can be reversed or exclude the selected decisive frame. They are now normalized into a source-frame envelope; the public timestamp still uses a supplied decisive source frame.
- Supported narrow evidence must also survive a wider-context check. This is implemented at `be6249e`; the six-case selected regression returned two normal results and four failed jobs, including the earlier detected positive. It does not pass quality acceptance or establish population accuracy. Receipt: `.context/verify/regression-be6249e.json`.

Do not keep adjusting prompts indefinitely or begin training on the model's own drafts. The failure mix needs local human diagnosis: missed observable categories, incorrect context, rule coverage, false alarms and actual annotation disagreements.

## Smallest human review

Open `~/.local/share/forte26/development-rehearsal/annotation-review/REVIEW.txt` locally. It links to three cases: a reported positive, a flagged supplied negative, and a normal result. Read each explanation under `model_result` in the JSON; watch videos and evidence in local applications.

Fill `first-milestone-review.json` beside it: `result_correct`, visible-explanation/source-moment/rule checks, reviewer and `checked`. Use `null` for uncertainty. For the flagged negative, record `false_alarm`, `plausible_visible_concern` or `unclear`; preserve the supplied label. Keep all scene details in that private JSON. No new UI or code is needed. Allow roughly 10–20 minutes.

These three checks close a semantic debugging loop; they do not supply enough reviewed training or validation data. The separate `review-tasks.json` contains 31 unreviewed development tasks. Any model drafts remain explicitly unreviewed and separate from human event fields.

## Remaining gates

1. Review the three cases, then freeze recording groups and review the missed-positive/category coverage. Do not mark pipeline acceptance complete from schema success alone.
2. Review legal scope. Points 20 and 22 are within the cash-acceptance section of resolution 231; verify transaction context and applicability before releasing the provisional catalog. Existence of a citation alone is insufficient.
3. Re-evaluate the fixed development set after justified changes. Preserve a no-new-false-positive promotion gate, source evidence and time limits. A high failure rate is not a useful detector.
4. Training remains off. Optional BF16 language-attention LoRA requires reviewed targets, separate recording-group validation and repeated errors the adapter could address. Stop the inference container before training on the same GPU.
5. Finish workload, concurrency, restart and final immutable-container checks. Independent-angle accuracy, full category/interval accuracy and minimum VRAM remain unmeasured.
6. Ask the user for exact UI libraries before the Next.js/TypeScript frontend. Final HTTPS, jury-hosting interpretation, submission deadline and final distribution notices still need closure.

The app image was built from `467fc2a` and selected public Python modules were patched for these experiments. Record exact hashes, then rebuild and rehearse a clean final image before deployment. No adapter, public UI or production service is claimed.

## Concurrency measurement

At `be6249e`, two selected normal development clips were admitted together with HTTP 202 and both reached `done` in approximately 12.275 seconds from submission. A third upload received HTTP 429 while both slots were occupied. Container networking remained disabled. This is a two-job mechanics check, not a busiest-clip or population latency guarantee. Receipt: `.context/verify/concurrency-be6249e.json`.

Actual API/inference source hashes and versions are in `.context/verify/backend-runtime-metadata.json`. The runtime CLI predates the new local evaluation command; API/inference source modules match the local code. A container-side NVML query failed once while the host GPU query and inference remained operational; do not claim complete per-run peak-memory coverage from it.

## Rental closed

The private results archive was copied to the Mac and its SHA256 verified before deletion. Hyperstack then reported zero VMs and zero volumes. The latest balance snapshot is $28.41 from the $30 top-up, about $1.59 consumed across both sessions; billing settlement may lag. The development-session snapshot reduction was $1.36. Non-billed project environment and public keypair remain for a future authorized session. Receipt: `.context/verify/backend-gpu.json`. Do not start another paid session while waiting for human annotations.

## Review and actor verification follow-up

The user locally reviewed the two evidence-bearing entries in the three-case packet. Neither reported event is supported well enough to accept its explanation. The review retains uncertainty; the normal-case result, full-video categories and exact event intervals were not inferred from that response. Private review details and corrections are only in the local annotation files.

The earlier TP/TN/FP/FN counts remain comparisons with supplied binary video labels. A video-level TP does not establish that the reported action, category or point is correct. No genuine positive event has yet passed human semantic acceptance. The three-case review does not open the training gate.

At `52b0497`, departure verification first establishes actor role from frames without receiving the proposed story or legal hypothesis. It requires earlier role-supporting source frames and continuity, checks wider context, and abstains on conflicting assignments. Successful departure evidence includes the earlier role frame and decisive moment. There is no fixed camera-side rule, identity recognition or new tracking framework.

Two initial regression tests reproduced missing-role acceptance and narrative exposure before the change. Two further tests reproduced inconsistent-role handling. All 49 tests now pass, with Ruff and package build. This is code-level validation only: no GPU/video rerun of this version occurred and no quality improvement is claimed. Receipt: `.context/verify/actor-grounding.json`. A subsequent bounded rehearsal must include reviewed true-event controls as well as unsupported-event cases, report failures separately and retain the source-evidence/time limits. No new paid VM was created for this change.
