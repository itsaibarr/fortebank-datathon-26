# ForteBank Datathon 26

Local video review service under development. The approved design uses Qwen3-VL-8B, source-timed evidence and the case's asynchronous FastAPI contract. The frontend will use Next.js after backend mechanics work and the user chooses exact UI libraries.

## Current setup

The backend implements authenticated asynchronous MOV jobs and source-timed JPEG evidence, with 69 local tests passing. Real offline GPU calls work, but detection quality fails acceptance and no grounded real positive is confirmed. The actor guard rerun was rejected on local review. A later controlled 8B/27B diagnostic still makes confident conflicting role assignments; neither model is promoted. There is no trained adapter or UI. See [development results](docs/development-rehearsal.md) and [the model diagnostic](docs/model-size-diagnostic.md).

The revised experimental preparation adds [three verified official-law snapshots](legal/README.md), 272 main-clause records, a coverage register, twelve draft operational cards, local lexical/dense/reranked retrieval and [separate visual/legal annotation validation](docs/legal-and-annotation.md). Retrieval quality and legal coverage remain incomplete, and these additions are not integrated into the legacy three-rule detector. Private review files and 31 development templates remain outside Git. All rented resources are deleted; latest credit is $27.55, with billing possibly still settling.

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
