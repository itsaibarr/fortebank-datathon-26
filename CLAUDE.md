# ForteBank Datathon 26 orientation

## What this is
Local cash-operation video review service. The integration connects frozen participant tracking/ReID, visual observations, local official-law retrieval, explicit condition evaluation, original-source evidence and a versioned asynchronous API. 201 Python tests pass with four existing warnings; frontend lint/types/static export and synthetic authenticated browser QA pass. The first real bounded API rehearsal returned done/partial/insufficient_evidence with recorded analysis duration 161.95s and verified source/PTS/returned JPEGs. Its timeline budget was exhausted. A separate smaller-prompt legal replay made two actual 27B calls: one structurally accepted unreviewed assessment, one rejected output; coverage remains incomplete and quality unestablished. The final image is built and cold startup is running; production, concurrency, final backup and cleanup remain pending. The original 8B detector and exact v1 contract remain available. See `docs/frozen-inference.md` for scope and limits.

The latest user scope is **pretrained inference with frozen weights**. It supersedes earlier mandatory and optional training proposals for this implementation. Do not perform LoRA, QLoRA, adapter training, optimizer updates or dataset-based weight adaptation. Missing reviewed labels limit quality measurement; they do not block a first frozen development inference.

## Workflow
- Primary system is `/Users/itsaibarr/harness`, commit `a22a10d9969d7a43f82ffe4f82a822fbb4b5091b`.
- Harness category 5 implementation after plan approval, bounded to local setup in this session. Use incremental implementation and meaningful behavior tests. Guides use category 7 research with Agent-Reach and concrete-answers.
- User approved setup and then explicitly delegated Hyperstack API provisioning/management within $30. Do not ask for the same approval again. Provision only after checking available credit and actual prices. The user handles the top-up; do not initiate payments or enable auto-top-up. Current work reuses the existing authorized VM under its recorded session deadline/spend cap; no training is authorized in the current scope.
- Read `SPEC.md`, `tasks/plan.md`, `tasks/todo.md` and `docs/case-requirements.md` before extending the product.

## Stack and commands
- Python 3.12 and uv; dependencies isolated in `.venv` and pinned by `uv.lock`.
- `uv sync --frozen` installs the local foundation, without CUDA frameworks or model weights.
- `uv run forte dataset-check --archive /absolute/path/to/open.zip` verifies source provenance and ZIP integrity without extraction.
- `uv run pytest -q` runs setup behavior tests.
- `uv run ruff check .` and `uv run ruff format --check .` check Python.
- `uv run python -m build` checks package build.
- `uv run forte serve` starts the API with `FORTE_API_KEY_FILE` and `FORTE_PRIVATE_ROOT`; the resident local model must be healthy before POST acceptance. `FORTE_REASONING_CONFIG` selects the new v2 path. See `docs/frozen-inference.md`; `docs/backend.md` describes the legacy detector.
- `forte model-check --root /models/<pinned-revision> --profile frozen27b` verifies local multimodal assets without downloads. `forte scan --source /private/development/clipNNN.mov --config /private/config/frozen-inference.json --private-output /private/runs/scan` makes actual local calls with OS-enforced outbound denial. See the frozen guide for mounts and required public assets.
- `web/` implements the approved Next.js/TypeScript, Tailwind, shadcn preset `b3d6mT4h6m` and Lucide interface. Lint, types, static export and synthetic authenticated upload/poll/media/seek/overlay/correction/mobile checks pass; receipt `.context/verify/frozen-timeline-ui-synthetic.json`. Real full-workflow verification remains open. Do not present synthetic checks as task benchmarks.

## Load-bearing files
- `SPEC.md` defines scope, fixed API, privacy and runtime acceptance.
- `contracts/api-contract.json` is the approved exact jury contract.
- `contracts/reasoning-api-contract.json` defines the separate v2 result/resources and authenticated `/api/v2/openapi.json`; the original v1 OpenAPI is unchanged.
- `configs/baseline.json` preserves the earlier 8B baseline settings; its historical optional training settings do not authorize training. `configs/frozen-inference.json` declares the current frozen model/tracking/legal path.
- `configs/provenance.json` records original case/archive fingerprints and verified audit counts.
- `src/forte/dataset.py` performs read-only archive checks.
- `src/forte/cli.py` exposes the dataset check.
- `src/forte/{api,jobs,worker}.py` own admission, atomic state, subprocess deadlines and sanitized failures.
- `src/forte/{video,inference,pipeline,rules}.py` own source PTS, loopback model calls, evidence verification and the provisional public-rule catalog.
- `src/forte/{model_profile,frozen_tracking,timeline,legal_reasoning,reasoning_pipeline,contracts_v2}.py` own pinned frozen assets, local participants, complete-duration observation scheduling, official-law condition checks, rich execution results and correction provenance.
- `docs/offline-api-bridge.md` describes fixed application-port-only loopback access to the existing offline container. It grants no model-port access or container egress. Private footage is reviewed by the human, never through remote browser/screenshot tools.
- `src/forte/{legal,retrieval,annotations}.py`, `legal/` and their preparation scripts own verified experimental law retrieval and separate review layers; these are not integrated into the legacy detector.
- `src/forte/{tracking,person_proposals,track_review,tracking_cli,review_packet}.py` implement private source-bound person proposals and independent human-review gates. `scripts/person_tracking.sh` separates public setup from network-disabled private inference; see `docs/person-tracking.md`.
- `tests/test_dataset.py` checks wrong inputs, integrity failures and CLI behavior.
- `tasks/todo.md` records actual completed tasks; do not mark model readiness as private inference success, synthetic tests as quality acceptance, or pending GPU/UI measurements as complete.
- `docs/case-requirements.md` maps the complete case to submission checks.
- `docs/development-rehearsal.md` records actual development runs, quality blockers and the private human-review procedure.

## Settled decisions
- The current local reasoning path integrates the scoped official corpus and twelve draft cards; reviewed continuity, correct historical legal applicability and representative quality acceptance remain open. The legacy detector still has only three provisional rules; neither it nor the three-act corpus constitutes full RK-law coverage. The earlier one-recording role diagnostic failed reliable agreement for both models. The user is not responsible for researching legislation to label visible facts.
- Current integration candidate: `Qwen/Qwen3.8-27B`, revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, actual `Qwen3_5ForConditionalGeneration` native vision configuration, unquantized BF16 and no adapters. Retain explicit `baseline8b` with Qwen3-VL-8B-Instruct revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`. A deployment has one selected resident model; v1 does not automatically load another 8B model.
- Frozen27b explicitly uses 16,384 context tokens after measured prompts could not fit 8,192 even with metadata compaction; baseline8b remains 8,192. The current profile keeps sixteen images, 1,200 visual output tokens, a 100-second local request timeout, about 55% of remaining time for timeline work and two legal calls ending at the overall deadline minus ten seconds. `capacity_limited` and partial schedules remain explicit. Validated observations survive a crossed stage deadline or failed later pass; unvalidated replies are excluded. These are execution bounds, not evidence of complete coverage or accuracy.
- Each persisted run records fingerprints for nineteen shipped application modules, separately from public model, legal-snapshot and effective-configuration hashes. These identify source bytes, not execution of every optional path.
- Legal calls now supply only participants referenced by selected observations and at most eight images, retaining complete decisive/support sets and exact primary legal text, parent context and validity notices. Oversized observation sets are skipped whole. All conditions remain required, with concise dependency/explanation output. After initial pre-generation context rejections, actual replay completed two 27B calls: one output passed application validation, one was rejected. This establishes one unreviewed assessment, not legal accuracy or complete coverage.
- Correction sidecars and immutable histories survive reruns, but automatic replay of reviewed corrections into later inference is not implemented. Do not claim model correction uptake from storage alone.
- Frozen pretrained inference only for the current scope. Participant galleries, legal indexes, prompts and timelines may change as private inference state; model weights may not.
- Steps 1–2 have an execution handoff in `docs/handoffs/01-visual-labeling-and-person-tracking.md`: direct GitHub CLI search, local YOLOX/ByteTrack proposals and self-hosted CVAT review, with standalone SAM 2 corrections. The user explicitly excludes Agent Reach for this work, overriding older research defaults. YOLOX-s ONNX and roboflow/trackers ByteTrack now run in an isolated private CPU environment. All 31 development groups have drafts and local review packets; human pilot approval and the session split remain pending. Local CVAT Community 2.79.0 now runs on loopback, with annotation backends on an internal network. Native synthetic video import/export passes; full human annotation remains pending. See `docs/person-tracking.md`.
- Historical steps 3–4 training research remains in `docs/role-action-training-research.md`; its training proposals are superseded by the current frozen-only instruction. Useful whole-recording and evaluation ideas were integrated from learning checkpoint `e7a5bbf` into new modules without merging training scaffolding or altering its existing handoff.
- PyAV/FFmpeg source timestamps, overlapping coarse/fine windows, source-frame evidence and local public-rule mapping.
- FastAPI public API with required file/header/field names, asynchronous jobs, one GPU host/container and atomic filesystem records.
- No cloud AI, audio analysis, identification, hidden-accounting claims or use of jury data for selection.
- The user selected Next.js App Router/TypeScript, Tailwind, shadcn preset `b3d6mT4h6m` and Lucide. That library gate is satisfied; do not ask for it again. The product workflow still needs actual browser/API verification.
- Primary GPU is Hyperstack A10080, `n3-A100x1` in CANADA-1 at the checked $1.35/hour compute rate. Actual setup used image 517, Ubuntu R570/CUDA12.8 with Docker. R595 image 1624 is B300-only. The pinned vLLM image worked with CUDA compatibility enabled. Stock/prices must be rechecked before another VM. $30 total cap; see `.context/verify/gpu-setup.json` for the completed synthetic check and billing snapshot.

## Data and access gotchas
- Original archive is `/Users/itsaibarr/Downloads/open.zip`; never change or commit it.
- 42 MOV files and one XLSX, 40 unique recordings. Exact duplicates must stay in one split.
- A duplicated recording has conflicting supplied point annotations; its identifiers and exact points stay in the private manifest. No complete category/interval targets are supplied.
- Private footage, frames, annotations, descriptions, outputs and adapters stay outside Git and remote AI tooling. Use synthetic test fixtures in code.
- Local humans review private semantics. Keep holdout and jury footage out of tuning/training.
- User confirmed organizer permission for development footage on the dedicated Hyperstack VM in Canada. Private videos/results never enter Git or remote AI chat. Jury data remains excluded from training and model selection.
- Hyperstack credential and SSH private key live outside Git under `~/.config/forte26`; never print/copy their contents into logs, Obsidian or memory. API request headers must come from the private header file, not command arguments.
- Dedicated project environment and public keypair remain available. After the user funded the account, one VM passed the public/synthetic offline check and was deleted; the provider then reported zero VMs and volumes. Private provisioning state records its lifecycle and IDs outside Git. The later development rehearsal is also closed: zero VMs/volumes, $28.41 at that session's credit snapshot (settlement may lag). See `.context/verify/backend-gpu.json` and `docs/development-rehearsal.md` before another rental.
- HTTP-reflection and SSH source IPs differed on the old connection; the modem connection matched. Use a current `/32` SSH rule, the dedicated known-host file and a project control socket. Initial host trust used TOFU because provider console-log retrieval failed; do not claim independent console verification.
- Stopped Hyperstack VMs still bill. The user delegated lifecycle management; delete only this project's recorded resource IDs after preserving outputs or at its budget/time limit. Do not touch other account resources. Plan automatic cleanup and reserve before paid allocation.
- Latest role-check rehearsal is closed: zero VMs/volumes; $28.12 credit snapshot, with settlement possibly pending. Clean image source hashes matched the checkout and inference networking was disabled. Receipt: `.context/verify/role-regression-52b0497.json`. Further paid tuning needs new reviewed evidence; role guards alone did not pass quality.

- The authorized corpus/model diagnostic session is closed: zero VMs/volumes, $27.55 latest credit with settlement possibly pending. Its observed credit reduction was about $0.57. See `.context/verify/model-size-diagnostic-20261017.json`. Generated scene content remains private; no model or retrieval candidate was promoted and no training occurred.

- Current frozen-integration session is distinct from those closed historical receipts. Initial readiness was October 17 22:03 UTC; later bounded execution produced a source-verified partial result and separate actual legal replay accepted one of two outputs structurally. Latest reported credit at 22:19 UTC was about $25.9449, subject to settlement. The same VM's session began 21:04 UTC, with cleanup by 23:04 UTC and a $3 session cap within the original $30 authorization; no extra VM was rented. SSH ingress is restricted to the verified current `/32`. The final image build passes; cold startup is running, with final backup and resource cleanup pending. See `docs/frozen-inference.md`; dated status does not establish live lifecycle or cleanup.

## Where not to look
Ignore `.venv`, caches, generated `dist`, private runs, downloaded weights and future `web/out` for code orientation.

## Durable context
Use Octarin for relevant team decisions and write back durable setup facts, anchored to this product repo. Do not inherit unrelated `bank_mvp` implementation history.

## Doc index
See `.context/DOC-INDEX.md`. Regenerate with `bash /Users/itsaibarr/harness/agent/core/gen-doc-index.sh .`, then omit ignored `.venv`, cache and `dist` entries. The existing generator does not exclude Python environments; do not modify Harness to fix that here.

- Human role/view/geometry follow-up is preserved in immutable private sidecars.
  Identity, reflections, geometry and role intervals have independent approval
  scopes. Keep case-specific counts, bindings, unresolved items, cited frames and
  correction content private; public orientation must not reconstruct them.
