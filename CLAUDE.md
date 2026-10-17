# ForteBank Datathon 26 orientation

## What this is
Local cash-operation video review service. Contracts, MOV decoding, loopback VLM adapter, temporal/evidence pipeline and authenticated asynchronous API are implemented. All 49 local tests pass. Real offline GPU API calls and source-JPEG provenance work, but exploratory detection quality fails acceptance. Two earlier reported-event reviews are complete and unsupported; full local annotation and normal-case review remain pending. The actor-grounding GPU rerun tested five of six selected clips before its failure stop: one supplied-negative alert and four insufficient-evidence failures. No human-confirmed positive control, trained adapter or UI exists. Read `docs/development-rehearsal.md` before further experiments.

## Workflow
- Primary system is `/Users/itsaibarr/harness`, commit `a22a10d9969d7a43f82ffe4f82a822fbb4b5091b`.
- Harness category 5 implementation after plan approval, bounded to local setup in this session. Use incremental implementation and meaningful behavior tests. Guides use category 7 research with Agent-Reach and concrete-answers.
- User approved setup and then explicitly delegated Hyperstack API provisioning/management within $30. Do not ask for the same approval again. Provision only after checking available credit and actual prices. The user handles the top-up; do not initiate payments or enable auto-top-up. Final training remains conditional on reviewed supervision and measured errors.
- Read `SPEC.md`, `tasks/plan.md`, `tasks/todo.md` and `docs/case-requirements.md` before extending the product.

## Stack and commands
- Python 3.12 and uv; dependencies isolated in `.venv` and pinned by `uv.lock`.
- `uv sync --frozen` installs the local foundation, without CUDA frameworks or model weights.
- `uv run forte dataset-check --archive /absolute/path/to/open.zip` verifies source provenance and ZIP integrity without extraction.
- `uv run pytest -q` runs setup behavior tests.
- `uv run ruff check .` and `uv run ruff format --check .` check Python.
- `uv run python -m build` checks package build.
- `uv run forte serve` starts the API with `FORTE_API_KEY_FILE` and `FORTE_PRIVATE_ROOT`; the resident local model must be healthy before POST acceptance. See `docs/backend.md`. There is no frontend yet. Do not present synthetic checks as task benchmarks.

## Load-bearing files
- `SPEC.md` defines scope, fixed API, privacy and runtime acceptance.
- `contracts/api-contract.json` is the approved exact jury contract.
- `configs/baseline.json` holds proposed model, video, job and optional training settings.
- `configs/provenance.json` records original case/archive fingerprints and verified audit counts.
- `src/forte/dataset.py` performs read-only archive checks.
- `src/forte/cli.py` exposes the dataset check.
- `src/forte/{api,jobs,worker}.py` own admission, atomic state, subprocess deadlines and sanitized failures.
- `src/forte/{video,inference,pipeline,rules}.py` own source PTS, loopback model calls, evidence verification and the provisional public-rule catalog.
- `tests/test_dataset.py` checks wrong inputs, integrity failures and CLI behavior.
- `tasks/todo.md` records actual completed tasks; do not mark future GPU/UI work done.
- `docs/case-requirements.md` maps the complete case to submission checks.
- `docs/development-rehearsal.md` records actual development runs, quality blockers and the private human-review procedure.

## Settled decisions
- The user requested a fresh domain/open-source/model review after rejecting the new report. See `docs/domain-research.md` and `.context/verify/domain-research-sources.json`. Proposed changes are a versioned scoped legal corpus/RAG, persistent actor grounding and an 8B-versus-Qwen3.8-27B comparison before optional SFT. These are research recommendations, not implemented or GPU-validated changes. The current catalog has only three provisional rules; do not describe it as full RK-law coverage. The user is not responsible for researching legislation to label visible facts.
- Qwen/Qwen3-VL-8B-Instruct BF16, exact revision in configuration; InternVL3_5-8B fallback. Main VLM remains at least 8B.
- Pretrained pipeline first; optional language-attention LoRA only after reviewed supervision and measured errors. No adapter is enabled now.
- PyAV/FFmpeg source timestamps, overlapping coarse/fine windows, source-frame evidence and local public-rule mapping.
- FastAPI public API with required file/header/field names, asynchronous jobs, one GPU host/container and atomic filesystem records.
- No cloud AI, audio analysis, identification, hidden-accounting claims or use of jury data for selection.
- Next.js App Router with TypeScript comes after working backend mechanics. Ask the user for exact UI libraries and screen/state brief before frontend work. No UI packages selected now.
- Primary GPU is Hyperstack A10080, `n3-A100x1` in CANADA-1 at the checked $1.35/hour compute rate. Actual setup used image 517, Ubuntu R570/CUDA12.8 with Docker. R595 image 1624 is B300-only. The pinned vLLM image worked with CUDA compatibility enabled. Stock/prices must be rechecked before another VM. $30 total cap; see `.context/verify/gpu-setup.json` for the completed synthetic check and billing snapshot.

## Data and access gotchas
- Original archive is `/Users/itsaibarr/Downloads/open.zip`; never change or commit it.
- 42 MOV files and one XLSX, 40 unique recordings. Exact duplicates must stay in one split.
- Duplicate positive `Х-4`/`Х-47` has 57/68-second points. No category/interval targets are supplied.
- Private footage, frames, annotations, descriptions, outputs and adapters stay outside Git and remote AI tooling. Use synthetic test fixtures in code.
- Local humans review private semantics. Keep holdout and jury footage out of tuning/training.
- User confirmed organizer permission for development footage on the dedicated Hyperstack VM in Canada. Private videos/results never enter Git or remote AI chat. Jury data remains excluded from training and model selection.
- Hyperstack credential and SSH private key live outside Git under `~/.config/forte26`; never print/copy their contents into logs, Obsidian or memory. API request headers must come from the private header file, not command arguments.
- Dedicated project environment and public keypair remain available. After the user funded the account, one VM passed the public/synthetic offline check and was deleted; the provider then reported zero VMs and volumes. Private provisioning state records its lifecycle and IDs outside Git. The later development rehearsal is also closed: zero VMs/volumes, $28.41 at that session's credit snapshot (settlement may lag). See `.context/verify/backend-gpu.json` and `docs/development-rehearsal.md` before another rental.
- HTTP-reflection and SSH source IPs differed on the old connection; the modem connection matched. Use a current `/32` SSH rule, the dedicated known-host file and a project control socket. Initial host trust used TOFU because provider console-log retrieval failed; do not claim independent console verification.
- Stopped Hyperstack VMs still bill. The user delegated lifecycle management; delete only this project's recorded resource IDs after preserving outputs or at its budget/time limit. Do not touch other account resources. Plan automatic cleanup and reserve before paid allocation.
- Latest role-check rehearsal is closed: zero VMs/volumes; $28.12 credit snapshot, with settlement possibly pending. Clean image source hashes matched the checkout and inference networking was disabled. Receipt: `.context/verify/role-regression-52b0497.json`. Further paid tuning needs new reviewed evidence; role guards alone did not pass quality.

## Where not to look
Ignore `.venv`, caches, generated `dist`, private runs, downloaded weights and future `web/out` for code orientation.

## Durable context
Use Octarin for relevant team decisions and write back durable setup facts, anchored to this product repo. Do not inherit unrelated `bank_mvp` implementation history.

## Doc index
See `.context/DOC-INDEX.md`. Regenerate with `bash /Users/itsaibarr/harness/agent/core/gen-doc-index.sh .`, then omit ignored `.venv`, cache and `dist` entries. The existing generator does not exclude Python environments; do not modify Harness to fix that here.
