# ForteBank Datathon 26 execution checklist

## Revised approach authorized after domain research

- [x] Collect three official Adilet full-text snapshots and current-version inventories; verify offline reconstruction of 272 main-clause records, with annexes preserved raw.
- [x] Add a complete register of collected clauses and twelve source-bound draft cards covering thirteen clauses. This does not establish exhaustive applicable-law coverage or approved interpretations.
- [x] Implement offline lexical retrieval and opt-in pinned BGE-M3 dense retrieval/reranking; keep measured development query results and avoid production promotion without broader validation.
- [x] Separate source-bound visible facts from legal prerequisites/exceptions and explicit review states; 69 local tests, lint/format and package build pass.
- [x] Prepare 31 private development annotation templates. They are drafts, with zero reviewed training targets; holdout/jury recordings are excluded.
- [x] Compare pinned 8B/27B models on the same three context variants of one user-corrected role error. 27B fits but neither reliably agrees with the correction; no promotion or training.
- [x] Update the steps 1–2 handoff with direct GitHub search commands and verified local annotation/tracking projects, excluding Agent Reach at the user's request.
- [x] Research steps 3–4 and document the proposed supervised role/action experiment, video-classifier baseline, scan cadence and evaluation gates in `docs/role-action-training-research.md`. Research only: no training, installation or GPU rental.
- [ ] Finish the reviewed person/role/action and tracking pilot from `docs/handoffs/01-visual-labeling-and-person-tracking.md`; prepare reviewed targets and a session-bound split before the training experiment.
- [ ] Establish genuine reviewed positive controls, recording-date applicability and approved operational cards; complete visible-fact review and resolve split continuity.
- [ ] Implement and evaluate persistent actor correspondence, transaction phase and production RAG integration against reviewed reference cases.
- [ ] Reopen optional supervised training only after independent reviewed targets and the existing evaluation gates are satisfied.

Ordered task list following Harness's plan convention. Details, dependencies, file scope and verification are in [plan.md](plan.md). No product tasks are checked off by the architecture research.

## Steps 1–2 implementation checkpoint

- [x] Pin local YOLOX-s ONNX and ByteTrack release/artifact hashes after direct GitHub inspection; separate public setup from network-disabled CPU inference.
- [x] Add versioned source-bound tracks linked to the existing visual/legal annotations, independent geometry/identity/role review, explicit uncertainty and immutable correction revisions.
- [x] Run the three priority proposal cases, then prepare drafts/local packets for all 31 development groups; preserve original reviews, templates and the regression exclusion. No holdout/jury media included.
- [x] Re-decode all 29,546 source frames and verify both playback derivatives (59,092 frames); privately re-extract/check 122 source images and 286 crops. These are provenance checks, not semantic approval.
- [x] Test CVAT XML person boxes/area polygons, mutable roles, occlusion/outside/keyframe flags, actual source bindings, crossing/gap uncertainty and rejection of unreviewed training targets. 101 tests, lint, format and build pass.
- [x] Record human role/view responses for all three pilot recordings in immutable v2 revisions: fourteen mappings, six local identity groups, seven reflection relationships and one explicit same-person join; retain one explicitly unclear review item and independent interval, geometry and training gates.
- [x] Record stable identity for two complete proposed segment ranges in one pilot, without approving boxes, joins or role/action intervals. Preserve prior correction inputs across nested review revisions; synthetic regression and package checks pass.
- [ ] Finish native CVAT Community startup and a synthetic server round trip. Docker Hub TLS timeouts/stalled downloads prevented startup; no project containers were created.
- [ ] Finish actual human bindings for the three cases, check people/segments, work areas and role/action intervals, and measure ID switches/fragments. All three have initial human role/view responses; one item remains unclear, complete interval/geometry review is pending and no training target is released.
- [ ] Resolve the role-reference/current-review receipt mismatch and freeze reviewed recording/session groups before later training. Do not infer sessions from filenames.

Runbook: [person-tracking.md](../docs/person-tracking.md). Aggregate receipt:
[person-tracking-20261017.json](../.context/verify/person-tracking-20261017.json).
Successful per-clip CPU runtime totals 548.77 seconds; new paid compute spend is $0.
No training, legal classification, production detector change or product frontend.

## Local setup approved on 17 October 2026

- [x] Create the separate product Git repository and run the actual Harness bootstrap.
- [x] Fill orientation/specification, preserve the exact case API and carry forward the Next.js/user-library gate.
- [x] Create isolated Python 3.12 dependencies and a lockfile; no CUDA frameworks, model weights or UI packages installed.
- [x] Add a tested read-only dataset provenance/integrity command and run it on the actual `open.zip`.
- [x] Reread the complete attached case and write the Obsidian GPU, training and requirements guides.
- [ ] Backend mechanics pass local tests and actual offline GPU API calls; semantic acceptance, task quality and final UI remain pending. Setup success does not satisfy product acceptance.

## Hyperstack delegation

- [x] User authorized API provisioning and resource management within $30; user handles the top-up. Do not request that authorization again.
- [x] Validate the supplied credential with read-only API calls, check account credit, stock, actual GPU price and offered image.
- [x] Create the dedicated project environment and import the public half of a dedicated local SSH key. No paid VM or storage created while credit is zero.
- [x] Recheck funding and price, establish cleanup/time controls, then provision one A10080 and verify SSH/driver/Docker using public or synthetic inputs.
- [x] Run the exact BF16 model on two 16-image synthetic sequences with container networking disabled; preserve artifacts locally and delete the VM. Provider inventory and dashboard reported zero VMs/volumes afterward. Receipt: `.context/verify/gpu-setup.json`.
- [x] Organizer hosting clarification: user confirmed development videos from open.zip may run on our dedicated Hyperstack VM in Canada. Training still requires reviewed supervision and measured errors; jury exclusions remain.

## Phase 0

- [x] Task 0: Orient the clean product checkout and preserve unrelated changes.
- [ ] Task 1: Review private recordings locally, resolve/flag duplicate time conflict, freeze recording groups/split and approved observable rules.
- [ ] Task 2: Resolve rented-processor permission and spending separately, then run the one-hour bounded local model compatibility check.
- [x] Task 2 public/synthetic portion: pinned model, CUDA compatibility, structured output and both planned image sizes passed. Organizer permission for development hosting is confirmed. Full video/concurrency measurements remain open, so the parent task is not complete.
- [ ] Checkpoint: exact ≥8B model, licenses, local inference, token/memory bounds and dataset exclusions are explicit; no paid resource without authorization.

## Phase 1

- [x] Task 3: Implement exact public/internal contracts and semantic invariants; strict verdict, JPEG and supplied-frame/rule checks are covered by tests.
- [x] Task 4: Decode MOV video only, retain normalized source PTS, implement bounded coverage/fine samples and source JPEG re-extraction; VFR, rotation, source mutation and corrupt/duration checks pass.
- [x] Task 5: Wrap resident local Qwen/vLLM with structured outputs, pinned readiness and model-independent observation boundaries. Actual offline development API calls work; no adapter is enabled.
- [ ] Task 6: Produce one real locally verified positive/negative result through the full temporal/rule/evidence pipeline.
- [x] Task 7: Implement authenticated asynchronous POST/GET, two-slot admission, atomic private records, process deadlines/restart failures and bounded upload. Local contract/failure tests and real GPU calls pass mechanically; human review follows in Task 8.
- [ ] Task 8: Verify upload/poll/result mechanics through the API and decode returned evidence locally. Do not build the UI yet.
- [x] Task 8 mechanical portion: real POST/GET, two verdict shapes, source-timed JPEG decoding and exact source re-extraction exercised offline. This does not complete local semantic review.
- [x] Partial local review: two earlier reported-event explanations reviewed and unsupported; uncertainty preserved privately. Normal-case and full-event annotation review remain open. Actor-grounding enforcement passes local tests; the real GPU rerun failed quality (five tested: one supplied-negative alert, four insufficient-evidence failures). The user subsequently reviewed and rejected the new alert too; the correction is private.
- [x] Follow-up domain research: audited the actual three-rule legal coverage, reviewed official sources and pinned open-source/model references, and wrote `docs/domain-research.md`. Proposed corpus/RAG, persistent actor grounding and 8B/27B comparison remain unimplemented. Prepare legal mappings separately from observable-fact annotations; the user is not required to research legislation.
- [x] Bounded actor-check rehearsal: clean image, matching runtime source hashes, offline inference, source-verified JPEGs and local backup verified; VM deleted. Zero VMs/volumes and $28.12 latest credit snapshot. Receipt `.context/verify/role-regression-52b0497.json`. This does not complete semantic acceptance.
- [ ] **First backend milestone:** real positive/negative development videos complete POST/GET with valid schema, source JPEGs, times, rule references and no manual inference.

## Phase 2

- [ ] Task 9: Evaluate all development recording groups with frozen run manifests and local semantic review. First exploratory baseline tested 28/31 before its three-failure stop: 0 TP, 8 TN, 9 FN, 11 failed. The second tested 24/31: 1 TP, 6 TN, 2 FP, 6 FN and 9 failed. Both quality gates failed; receipts `.context/verify/baseline-1a56beb.json` and `.context/verify/baseline-cce5a1d.json`.
- [ ] Task 10: Keep measured sampling/predicate/evidence improvements; add a real different-angle smoke set if available.
- [ ] Task 11: Either record why adapter training remains unjustified, or run only the budget follow-up's bounded LoRA experiment and promotion gate. No first-version QLoRA is required.
- [ ] Checkpoint: quality improvements do not add negative false positives or violate time/memory constraints; no jury/holdout tuning.

## Phase 3

- [ ] Task 12: Pass one/two-job timing, five-job rehearsal, offline operation and failure recovery; record actual costs and limits. Offline real API calls and a two-job check passed (both done in about 12.3 s, third HTTP 429); full workload and final image checks remain open.
- [ ] Task 13: Freeze all selections, run the locked holdout once, report every error/limitation honestly.
- [ ] Task 14: Ask the user for exact UI libraries once backend mechanics work; agree libraries and screen/state specification before building the Next.js App Router/TypeScript frontend. Verify the complete browser workflow.
- [ ] Task 15: Deploy the exact working container, verify HTTPS/public port, privately hand off the jury key and document usage/categories/limitations.
- [ ] Final checkpoint: all exact case API fields, 1–3 real JPEGs/event, evidence provenance, cautious explanations and valid public rules; no external AI, audio, identity recognition or jury training.
- [ ] Retention checkpoint: keep all private media/outputs/competition-derived adapters out of Git and remove them under the competition's end-of-event requirement.

## Decisions that do not need reopening

- [ ] Keep Qwen3-VL-8B-Instruct primary, InternVL3_5-8B fallback, BF16 first.
- [ ] Keep the public contract, one-container topology and local filesystem job records.
- [ ] Keep deterministic rule mapping and original-frame evidence outside generated prose.
- [ ] Use Next.js for the frontend. Defer UI implementation until the backend works, then ask the user about exact UI libraries before selecting or installing them.
- [ ] Use configuration changes and measured errors before proposing another model/framework/infrastructure layer.
