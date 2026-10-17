# ForteBank Datathon 26

Local video review service under development. The approved design uses Qwen3-VL-8B, source-timed evidence and the case's asynchronous FastAPI contract. The frontend will use Next.js after backend mechanics work and the user chooses exact UI libraries.

## Current setup

The backend implements authenticated asynchronous MOV jobs, source-timed decoding, local VLM calls, candidate refinement, evidence verification and public-rule mapping. Its 26 local tests pass. The first GPU check proved the pinned model on synthetic images; complete development-video API verification is still pending. There is no trained adapter or UI. Keep model weights and competition files outside this repository.

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

The GPU smoke scripts run on an already-authorized machine; they do not rent hardware or call a paid AI API. The observed account-credit reduction for the completed check was about $0.23, leaving about $29.77 at the post-deletion snapshot. Full-video quality and latency still need evaluation. User acceptance is a working end-to-end service, not the completion of training.
