# ForteBank Datathon 26 execution checklist

Ordered task list following Harness's plan convention. Details, dependencies, file scope and verification are in [plan.md](plan.md). No product tasks are checked off by the architecture research.

## Local setup approved on 17 October 2026

- [x] Create the separate product Git repository and run the actual Harness bootstrap.
- [x] Fill orientation/specification, preserve the exact case API and carry forward the Next.js/user-library gate.
- [x] Create isolated Python 3.12 dependencies and a lockfile; no CUDA frameworks, model weights or UI packages installed.
- [x] Add a tested read-only dataset provenance/integrity command and run it on the actual `open.zip`.
- [x] Reread the complete attached case and write the Obsidian GPU, training and requirements guides.
- [ ] Model inference, complete API mechanics and final UI are still pending; setup success does not satisfy product acceptance.

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
- [x] Task 2 public/synthetic portion: pinned model, CUDA compatibility, structured output and both planned image sizes passed. The private-data hosting interpretation and full video/concurrency measurements remain open, so the parent task is not complete.
- [ ] Checkpoint: exact ≥8B model, licenses, local inference, token/memory bounds and dataset exclusions are explicit; no paid resource without authorization.

## Phase 1

- [x] Task 3: Implement exact public/internal contracts and semantic invariants; strict verdict, JPEG and supplied-frame/rule checks are covered by tests.
- [ ] Task 4: Decode MOV video only, retain PTS, implement coverage/fine windows and source evidence extraction.
- [ ] Task 5: Wrap resident local Qwen/vLLM with structured outputs and adapter slot.
- [ ] Task 6: Produce one real locally verified positive/negative result through the full temporal/rule/evidence pipeline.
- [ ] Task 7: Implement authenticated asynchronous POST/GET, admission, atomic state, deadlines and failures.
- [ ] Task 8: Verify upload/poll/result mechanics through the API and decode returned evidence locally. Do not build the UI yet.
- [ ] **First backend milestone:** real positive/negative development videos complete POST/GET with valid schema, source JPEGs, times, rule references and no manual inference.

## Phase 2

- [ ] Task 9: Evaluate all development recording groups with frozen run manifests and local semantic review.
- [ ] Task 10: Keep measured sampling/predicate/evidence improvements; add a real different-angle smoke set if available.
- [ ] Task 11: Either record why adapter training remains unjustified, or run only the budget follow-up's bounded LoRA experiment and promotion gate. No first-version QLoRA is required.
- [ ] Checkpoint: quality improvements do not add negative false positives or violate time/memory constraints; no jury/holdout tuning.

## Phase 3

- [ ] Task 12: Pass one/two-job timing, five-job rehearsal, offline operation and failure recovery; record actual costs and limits.
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
