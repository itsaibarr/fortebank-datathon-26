# Runtime and API

See [report.md](../report.md) for architecture. `pipeline.py` is the only production
inference implementation. API v1 projects its rich result through source/condition
replay; v2 returns that result directly. Insufficient v1 evidence is failed.

Set private `FORTE_API_KEY_FILE`, `FORTE_PRIVATE_ROOT`, `FORTE_REASONING_CONFIG`
(from `configs/frozen-inference.json`), `FORTE_MODEL_PATH` and `FORTE_LAYA_PATH`.
The latter paths end with their pinned revisions. Both snapshots require local
`model-hashes.json` with model ID, revision and complete SHA256 file map. The Laya
map includes tokenizer/, encoder/config.json, rl_agent_config.json and weights.
No startup code downloads weights. Laya source/runtime is pinned in pyproject.

`Dockerfile` retains the pinned vLLM base; `scripts/container-entrypoint.sh` verifies
8B assets, starts one-sequence loopback vLLM, warms its actual visual processor,
starts a CPU FP32 Laya process and starts one FastAPI process. Readiness/admission
require both exact local identities. Laya advertises ready only after a synthetic
forward. A missing/unhealthy CPU service does not select another pipeline.
The modified image and Laya/vLLM dependency compatibility have not been built or
run on a real host under this cleanup; do not claim runtime acceptance.

Build the approved UI with `cd web && npm run build` before an authorized container
build. Mount immutable public assets and private job/key/config paths; enforce
outbound denial at the OS/container boundary, expose only the application port,
keep model ports 8001/8002 internal and allow one visual sequence at a time.
The offline bridge and session gateway retain existing security boundaries;
see [browser-session-plan.md](browser-session-plan.md) and
[offline-api-bridge.md](offline-api-bridge.md). No live service is changed here.

Initial bounds: two admitted jobs, 256 MiB, 180 seconds decoded video, 30-second
upload and 270-second absolute deadline. Failed/interrupted jobs persist atomically;
one process owns the job root. A worker receives immutable per-request config.

Local commands: `forte serve`, `forte scan --source /private/clip.mov --config
/private/config.json --private-output /private/new-run`, `forte model-check --root
/models/<8B-revision>`. Private execution needs separate authorization and enforced
egress denial; these examples are instructions, not execution receipts.
