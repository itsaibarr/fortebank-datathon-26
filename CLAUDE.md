# ForteBank orientation

`report.md` is the sole current architecture. `SPEC.md` defines acceptance;
`tasks/todo.md` tracks actual remaining work. No historical receipt approves the
new architecture or authorizes live resources.

## Product

One authenticated asynchronous FastAPI service, one application container, local
8B vLLM process and resident CPU Laya process; atomic filesystem jobs.
`src/forte/pipeline.py` is the only inference implementation. Both API output
adapters reach it through `worker.py`. `timeline.py` extracts source-bound facts;
`legal_reasoning.py` owns official rules and deterministic conditions;
`laya.py`/`laya_service.py` own the mandatory text-only choice boundary.
`video.py`, tracking/review modules and the session gateway preserve provenance
and independent review/security scopes. Corrections persist immutably; automatic
correction replay into later inference is not implemented.

## Commands

- `uv sync --frozen --extra inference-tracking` installs declared software only.
- `uv run pytest -q`
- `uv run ruff check .` and `uv run ruff format --check .`
- `uv run python -m build`
- `cd web && npm test && npm run lint && npx tsc --noEmit && npm run build`
- `uv run forte --help` lists source audit, scan, law and tracking commands.
- `forte model-check --root /models/<pinned-8B-revision>` verifies staged assets.
- `forte serve` requires private key/root/config and both local models healthy.
  See `docs/backend.md`; run only with separately authorized runtime assets.

## Boundaries

Private media/results/descriptions/corrections never enter Git or external AI.
Private inference requires explicit authorization and OS-enforced denied egress.
No weights download, training, paid resources, live service changes, deployment or
publication under source-cleanup authorization. Jury data never enters selection.
Do not restart another session or alter its hosts, caches, credentials or worktrees.
Preserve original PTS/JPEGs, actor/recipient binding, unknowns, reflection ownership,
independent human review and immutable correction history. No draft self-approval.

Next.js/TypeScript with Tailwind/shadcn/Lucide is approved. Browser sessions use
same-origin cookies and CSRF, never service keys in browser source.

## Verification limits

See `report.md` for actual local check results. Both real-model runtime compatibility,
CPU latency/memory, complete private-video quality/coverage and deployment remain
unverified for this architecture. Old `.context/verify` receipts are historical
and unchanged. Do not reuse their image identities or test counts as current.
