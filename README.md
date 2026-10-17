# ForteBank Datathon 26

Local video evidence review with a frozen 27B tracking, timeline and legal-retrieval
pipeline. The exact v1 asynchronous FastAPI contract and explicit 8B baseline remain
available. The review UI uses Next.js, TypeScript, Tailwind, shadcn preset
`b3d6mT4h6m` and Lucide.

## Current setup

The backend accepts MOV uploads, produces bounded timeline proposals and serves
source-timed original JPEGs with immutable correction history. Real offline GPU
runs completed with partial coverage and insufficient evidence. Recognition and
legal quality remain unaccepted; no model weights were trained or adapted. See
[the frozen execution record](docs/frozen-inference.md) for actual timings,
resource deletion and the incomplete final-backup limitation.

The current source adds protected browser sessions and per-principal authorization
for jobs, media, corrections and fresh range requests. Credentials remain on the
server; the browser shows destination, readiness, limits, manual retention and
no-training notices. [The browser/session contract](docs/browser-session-plan.md)
and [machine-readable interface](contracts/browser-session-contract-v1.json)
describe deployment integration. This source is newer than the historical verified
GPU image; a new image and external deployment still need qualification.

[Three official-law snapshots](legal/README.md), 272 main-clause records and twelve
draft operational cards support local retrieval. Interpretations, coverage and
human review remain independent. Private recordings, annotations and review files
stay outside Git and external inference services.

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

The GPU smoke scripts require an already-authorized compatible CUDA host; they do
not rent hardware or call a paid AI API. The previously observed A100 host is a
measurement, not a required GPU brand or VM. New-host qualification must verify
immutable resources and real bounded visual warmup, keeping measured limits
separate from unmeasured capacity. Local qualification does not approve publication
or detection quality. Deployment and guided installation are maintained in the
independent deployment lane; current release acceptance remains gated.
