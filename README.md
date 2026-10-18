# ForteBank Datathon 26

Local source-timed cash-operation video review. The sole architecture and current
verification status are in [report.md](report.md).

Frozen Qwen3-VL-8B produces actor-bound visual facts; mandatory local CPU Laya
multilingual proposes three-state conditions. Code evaluates official local rules,
source evidence, uncertainty and verdicts and renders template explanations.
One pipeline serves exact jury v1 and richer v2/UI adapters.

## Local software checks

```sh
uv sync --frozen --extra inference-tracking
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python -m build
cd web
npm ci
npm test
npm run lint
npx tsc --noEmit
npm run build
```

These install software, not weights. Synthetic tests do not establish model quality.
The selected Laya upstream runtime is pinned by Git commit in `pyproject.toml`;
its local checkpoint and CPU warmup are mandatory for readiness.

## Guides

- [Runtime/API](docs/backend.md), [specification](SPEC.md), [tasks](tasks/todo.md)
- [Legal conditions](docs/legal-reasoning.md), [tracking/review](docs/person-tracking.md)
- [Source timeline](docs/timeline-inference.md), [appearance proposals](docs/frozen-tracking.md)
- [Browser security](docs/browser-session-plan.md), [offline bridge](docs/offline-api-bridge.md)
- [Review format](docs/review-packet-format.md), [cleanup inventory](docs/cleanup-inventory.md)
- [Exact jury contract](contracts/api-contract.json), [UI contract](contracts/reasoning-api-contract.json)

Private media, labels, descriptions, results, corrections and credentials stay
outside Git and external AI. Private inference requires explicit authorization and
OS-enforced egress denial. No paid work, weights download, live service changes,
deployment, submission or publication is authorized by local source consolidation.
Historical receipts in `.context/verify` retain their original meaning and are not
verification of the current implementation.
