# ForteBank Datathon 26

Local video review service under development. The approved design uses Qwen3-VL-8B, source-timed evidence and the case's asynchronous FastAPI contract. The frontend will use Next.js after backend mechanics work and the user chooses exact UI libraries.

## Current setup

This repository is initialized through `/Users/itsaibarr/harness/bootstrap.sh`. Local Python dependencies and a read-only dataset verification command are in place. A funded Hyperstack A10080 ran the pinned Qwen3-VL-8B model successfully on synthetic frames with networking disabled, then was deleted. There is no full video-analysis server, trained adapter or UI yet. No model weights or competition files belong in this repository.

```bash
uv sync --frozen
uv run forte dataset-check --archive /Users/itsaibarr/Downloads/open.zip
uv run pytest -q
uv run ruff check .
uv run python -m build
```

The dataset command checks the expected original archive SHA256, ZIP integrity and file counts without extracting or modifying it. Use another absolute archive location on another machine. Do not change the expected hash to make an unrelated dataset pass.

## Read before implementation

- `SPEC.md` holds the approved requirements and explicit unresolved hosting/runtime gates.
- `contracts/api-contract.json` preserves the required jury API.
- `configs/baseline.json` holds the model and pipeline settings, with no adapter enabled.
- `tasks/plan.md` and `tasks/todo.md` are the Harness execution handoff.
- `docs/case-requirements.md` maps the supplied case to acceptance checks.
- `docs/gpu-runbook.md` and `.context/verify/gpu-setup.json` record the actual GPU check, reproducible commands, measurements and cleanup.

Obsidian notes are in `/Users/itsaibarr/Documents/Obsidian Vault/Projects/ForteBank Datathon 26`:

- `GPU rental and access guide.md`
- `Training process and expected results.md`
- `Case requirements and implementation checks.md`
- `Computer vision stack and a 30 dollar GPU budget.md`

The GPU smoke scripts run on an already-authorized machine; they do not rent hardware or call a paid AI API. The observed account-credit reduction for the completed check was about $0.23, leaving about $29.77 at the post-deletion snapshot. Full-video quality and latency still need evaluation. User acceptance is a working end-to-end service, not the completion of training.
