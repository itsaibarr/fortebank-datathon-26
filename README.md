# ForteBank Datathon 26

Local video review service under development. The approved design uses Qwen3-VL-8B, source-timed evidence and the case's asynchronous FastAPI contract. The frontend will use Next.js after backend mechanics work and the user chooses exact UI libraries.

## Current setup

The backend implements authenticated asynchronous MOV jobs, source-timed decoding, local VLM calls, candidate refinement, evidence verification and public-rule mapping. Its 49 local tests pass. Real development videos have traversed the offline GPU API, including source-verified JPEG evidence. Detection quality fails the acceptance gate: the second exploratory run tested 24 of 31 videos and returned 1 TP, 6 TN, 2 FP, 6 FN and 9 failed jobs. Two local event reviews rejected the reported explanations as unsupported; no grounded real positive is confirmed. The new actor check has not yet had a GPU/video rerun. There is no trained adapter or UI. See `docs/development-rehearsal.md`; keep private content outside this repository.

```bash
uv sync --frozen
uv run forte dataset-check --archive /Users/itsaibarr/Downloads/open.zip
uv run pytest -q
uv run ruff check .
uv run python -m build
```

The dataset command checks the expected original archive SHA256, ZIP integrity and file counts without extracting or modifying it. Use another absolute archive location on another machine. Do not change the expected hash to make an unrelated dataset pass.

## Read before implementation

- `SPEC.md` holds the approved requirements and remaining runtime checks. The user confirmed organizer permission for development footage on the dedicated Hyperstack VM in Canada.
- `contracts/api-contract.json` preserves the required jury API.
- `configs/baseline.json` holds the model and pipeline settings, with no adapter enabled.
- `tasks/plan.md` and `tasks/todo.md` are the Harness execution handoff.
- `docs/case-requirements.md` maps the supplied case to acceptance checks.
- `docs/gpu-runbook.md` and `.context/verify/gpu-setup.json` record the actual GPU check, reproducible commands, measurements and cleanup.
- `docs/backend.md` explains the implemented pipeline, startup and private API rehearsal.

Obsidian notes are in `/Users/itsaibarr/Documents/Obsidian Vault/Projects/ForteBank Datathon 26`:

- `GPU rental and access guide.md`
- `Training process and expected results.md`
- `Case requirements and implementation checks.md`
- `Computer vision stack and a 30 dollar GPU budget.md`

The GPU smoke scripts run on an already-authorized machine; they do not rent hardware or call a paid AI API. The first synthetic check used about $0.23. The separate development rehearsal, its billing receipt and remaining quality work are recorded in `docs/development-rehearsal.md`. User acceptance is a working end-to-end service with reviewed evidence, not the completion of training.
