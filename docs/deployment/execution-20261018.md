# Deployment execution and readiness — 18 October 2026

This is the authoritative plan, progress record and consolidated report for T3
thread `1316f01a-0b03-42b4-8a84-02bfdfdaa12f`. One agent executes each stage in
order. Earlier delivery reports are attributed historical evidence, not current
acceptance. Detailed local logs and the initial-change backup are outside Git at
`~/.local/share/forte26/deployment-readiness/20261018-0344/`.

## Scope and immutable starting point

- Initial core: `ae9f819c3d7063e8bcf0e51855e5b4773c1961df`, branch
  `codex/frozen-inference-completion`.
- Pre-existing modifications: `CLAUDE.md`, `README.md`, `SPEC.md`, `tasks/todo.md`;
  untracked `docs/frozen-integration-20261018.md`. Preserve their bytes. Their
  hashes, copies and tracked patch are in the private initial-state backup.
- Reusable deployment source: `19afab3a8c7867aa9c88333a2a3edb79027397c3`
  (`codex/deployment-delivery-b-20261018`). Its differences from the initial core
  are confined to `deploy/portable/`, `tools/forte-admin/`, `docs/deployment/`
  and `tests/deployment/`. Core, UI, contracts, model configuration and lockfiles
  are byte-identical. Inspect and import this complete dependency closure rather
  than reconstructing an installer or applying an obsolete ownership patch.
- Allowed implementation scope: those four deployment directories. Do not change
  core inference, model selection, frontend libraries, source timestamps,
  evidence semantics or the canonical contracts.
- User steering at 03:47 UTC: read the parallel evaluation thread; its VM work
  may cover this need. Read
  [ForteBank Approach Evaluation Pipeline](t3-thread://v1/f3826967-a68c-468c-b030-79d8c77202ed)
  without messaging or starting agents. Leave VM/model operations to that work;
  no further VM mutation, GPU test, provisioning, ingress or lifecycle change is
  part of this execution. Reuse only applicable, explicitly identified evidence.

**Scope update at 04:00 UTC:** the user explicitly instructed this thread to
deploy one additional VM and complete the deployment checks requiring it. This
supersedes the earlier no-new-VM boundary for one additional active owned VM.
Do not touch the parallel evaluation's VM 1108896. The previously observed
1108917 has since been deleted by its original guard; current inventory has one
VM and zero volumes. Use a separate owner namespace and lifecycle state, not
the shared provisioning-state file. No additional agent/thread is authorized.

Verified new-resource preflight at 04:01:59 UTC: $22.078260155944104 credit,
CANADA-1 `n3-A100x1` stock available, compatible image 517 (Ubuntu 24.04 R570 /
CUDA 12.8 / Docker), compute $1.35/hour and IP $0.00672043/hour. Plan at most
$3 of this run's bounded account debit, within the existing $30 project ceiling
and $1.50 reserve. Separate local and VM-side exact-resource cleanup guards
must be armed and acknowledged before useful work. Useful stop 05:45 UTC,
deletion 06:00 UTC, cleanup retries until 06:15 UTC; credit/rate caps may trigger
earlier cleanup. Existing-owner spend is shared account debit, not attributed
as this VM's measured invoice. No automatic top-up, volume or extra VM.

**Provisioning recovery:** VM 1108949 was created once at 04:06 UTC but the reused
guard treated a single provider GET failure as fatal and deleted it before any
installation/data upload. Positive inventory absence was observed at 04:09 UTC.
Added bounded retries for GET only (three attempts); retained fixed budgets,
exact-resource identity, no POST retry and cleanup verification. All 120 existing
fake-provider checks plus targeted retry checks pass. Replacement 1108954 is the
sole new active deployment VM; the failed attempt's shared debit is deducted
from the original $3 bound. Its remaining cap is $2.886939964166661, useful stop
05:25 UTC, deletion 05:40 UTC, cleanup target 05:55 UTC. Caps may trigger earlier.
The original VM 1108896 remains untouched. Separate private state is
`~/.config/forte26/deployment-readiness-20261018-05/`; the initial failed state
under `...-04/` is preserved, closed and never reused.

## Verified architecture and contract

| Area | Existing implementation and deployment implication |
| --- | --- |
| Tracking/ReID | `person_proposals.py`, `frozen_tracking.py`: YOLOX, ByteTrack, frozen OSNet; recording-local identity proposals and geometry retain independent provenance. Package their pinned public assets; no replacement tracker. |
| Participants/roles/timeline | `timeline.py`, `reasoning_pipeline.py`: source-PTS ledger, chronological windows, role history, bounded reinspection, partial coverage and immutable corrections. No training or automatic correction replay is claimed. |
| Reasoning | One resident local vLLM model. Selected frozen candidate is Qwen/Qwen3.8-27B, revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, BF16, no adapters; 16,384 context tokens, sixteen images, one model sequence. Preserve explicit legacy baseline and opt-in v1 reasoning projection. |
| Legal retrieval | Pinned local three-act/272-main-record corpus, BM25/exact lookup and twelve draft cards. Corpus hash `856f66bc541f92a7c3b0316d43ce9e2664cef321e6db63fc83396007ee561462`. Scope and historical applicability remain limited. |
| Dataset | `dataset.py` checks immutable archives; private neutral/hash development allowlist remains separate. No reserved/jury recordings, private frames or descriptions enter Git, images or remote review tools. |
| API | FastAPI `api.py`, canonical v1 and separate v2 contracts. `POST /api/v{1,2}/analyze`: exactly one multipart field `file`, MOV; 202 with `job_id`. Poll `GET /api/v{1,2}/jobs/{job_id}`: `processing`, `done`, `failed`. Service clients use `X-API-Key`. |
| Limits/errors | 256 MiB complete multipart body, maximum 180 seconds, 30-second upload deadline, 270-second job budget, two admitted jobs, one API process per filesystem root. 401/404 auth, 413 size, 415 format, 422 request/video, 429 capacity and 503 model/config readiness remain explicit. |
| Results/media | V2 source, evidence, corrections and report routes are beneath `/api/v2/jobs/{job_id}`. Original MOV uses `FileResponse` and integrity checks. Every fresh range checks ownership. No separate preview, supporting-clip or export routes were found; do not invent them. V1 uncertainty fails instead of becoming a clean negative. V2 execution and assessment remain independent. |
| Authorization | Core trusted-gateway mode persists opaque principals and denies other owners/ownerless history. Existing stdlib session gateway and SQLite/scrypt account tool provide secure cookies, exact HTTPS Origin, CSRF and revocation. Legacy shared-key mode is a single trust domain. |
| Storage/workers | Atomic private filesystem jobs and subprocess workers; persistent cases/corrections plus separate private account SQLite. No Redis, Celery, external database or remote case store. Retention is manual, including backups; uploads are not training data. |
| Browser | Existing Next.js/TypeScript static export served by core. Same-origin session/API calls, upload/poll/review, authenticated source/evidence, intervals, participant and legal references. Reuse it; no second dashboard. |
| Serving | Existing Dockerfile pins vLLM base digest `a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b`; runtime requirements, uv/npm locks are present. Container entrypoint verifies model hashes and visual warmup before API. Internal API 8000; model 8001 loopback only. |
| Packaging | Existing `forte-admin` is separate from core `forte`. Newer committed tooling adds guided/resumable installation, public preparation, immutable source/image build, qualification, session bootstrap and exact-release receipt validation. Private owns offline core/access; attach owns access only. |

Contract byte hashes at discovery:

| Resource | SHA256 |
| --- | --- |
| v1 API | `2f07ca38a89320a97edc1f18cf1401462ce89f6912698245bac4f67bd3cacc05` |
| v2 API | `85cd54cf12bf2923a64666524ed3a1879c07f2fa12a0ff5b6979b03a4b84fa83` |
| browser session | `3cc3f16715bdf82d2ad1ac4cb541af76832bf16a326d154aba70113f090c066e` |
| public asset inventory | `2f858a24955c95f9655d91cc9e70badfc2ba9cc51e05af4058f16dfe19b84cf0` |
| frozen config | `c516e8c32a1fa05036f729cb6849cc86d2a570f9cf89632243887e03654d03e4` |

## Existing deployment capabilities and gaps

The starting checkout has the earlier 0.1 installer and historical single-user
candidate. The newer committed 0.2 delivery already implements most requested
mechanics but is not integrated here. Reuse it after source comparison and run
its behavior tests against this actual core. Historical patch proposals and
historical image acceptance cannot approve this new source/release.

Missing acceptance evidence: current exact built image and reviewed runtime
manifest; measured supported-host minimums; clean customer GPU installation;
real-model upload through the final access profile; offline packaged analysis;
real-case/browser persistence; trusted externally reachable HTTPS origin and a
complete outside-network reviewer workflow. No source-only check fills these
gaps. The parallel evaluation thread owns model/VM evaluation, not automatically
these access and installation acceptance checks.

## Prerequisites, resources and rollback

Supported initial recipe: Linux x86_64, compatible NVIDIA CUDA GPU, usable Docker
Engine/Compose and NVIDIA Container Toolkit. Check GPU capability/free capacity
against actual pinned workload, not a GPU product name. Customer supplies local
storage, trusted certificate/key or internal CA, intended origin/listener,
approved release/image, prepared public weights/legal assets and local account.
The installer must report unsupported macOS/CPU-only environments clearly.

Discovery observation on VM 1108896 at 03:46:22 UTC: Ubuntu 24.04.3, 28 CPUs,
120,841 MiB RAM/112,748 MiB available, A10080 driver 570.195.03 with 73,531 MiB
allocated/7,623 MiB free, 648 GiB available on `/ephemeral`, one resident vLLM
engine and the existing core container. Host loopback 8445/18003 are occupied;
container model/API have no host publication. Deletion timer remains 07:00 UTC.
No database service was visible in process/container/port inventory; private
job counts and case records were deliberately not opened. This is a read-only
observation, not a deployment or workload qualification by this run.

Provider at discovery: two active project VMs (1108896 and 1108917), zero volumes;
credit $22.50788829211078, subject to billing settlement and other work. Existing
1108896 record has a $7 session ceiling, original $30 project ceiling, $1.50
reserve, useful stop 06:30 UTC and deletion 07:00 UTC. No fresh budget or
allocation is assumed. This execution adds no paid infrastructure or GPU load.

Local verification uses the existing Python 3.12 virtualenv and cached container
resources where available; no global dependency changes. Allow several GiB for
public source/build/test artifacts. Actual log/archive sizes will be recorded.
Weights/images can consume tens of GiB on a target; RAM/disk minimums and full
build/download costs remain unvalidated. No heavyweight model download or image
build is required for the source/tooling verification here.

Rollback: retain the original HEAD and initial private backup; revert only this
run's deployment files using the recorded initial hashes/committed source in a
reviewed edit. Never reset/restore the complete checkout. Temporary local tests
must stop only their own services. Normal `forte-admin stop` preserves cases,
credentials, accounts and volumes. Upgrade/rollback requires compatible pinned
images and a private verified backup, preserving account principal IDs.

## Sequential execution plan and progress

Each stage inspects, prepares, executes, verifies and records its outcome here
before the next stage. A blocked runtime check does not prevent independent
local packaging work after its blocker is recorded.

| Stage | Work and verification | Status |
| --- | --- | --- |
| 01 Discovery | Instructions/history, actual contracts/architecture, existing deployment attempts, nonmutating provider/VM observation, read parallel thread | PASS; runtime follow-up delegated by user steering to existing evaluation work |
| 02 Planning | Record source snapshot, safe scope, dependencies, prerequisites/resources, ordered tests, acceptance and rollback | PASS; this plan recorded before implementation |
| 03 Deployment preparation | Import complete committed deployment closure; preserve existing changes; inspect source/asset/image/session dependencies and validate packaging configuration | PASS — 63 files imported; 169 checks pass, one optional Docker check deferred to Stage 05 |
| 04 CLI and installation | Validate guided preview/setup/resume/credentials, hardware diagnostics, preparation, source build and API-client semantics; build/extract/check real administrator archive | PASS at tooling/artifact scope — 327 tests; real extracted CLI checks pass; clean GPU installation unverified |
| 05 Hosted integration | Validate attach isolation, same-origin/TLS/session proxy mechanics locally; record runtime/external prerequisites without touching VMs | PARTIAL — 114 local TLS/gateway checks pass; live hosted integration/external URL unverified |
| 06 Private installation | Validate generated offline core/access topology, asset checks, qualification cleanup, persistence and unsupported-host behavior; distinguish clean-install gap | PARTIAL — 93 lifecycle checks pass; 21 real public resources imported/reused offline; clean GPU install and offline analysis unverified |
| 07 Security and access | Exercise real core/session ownership with generated media; range/report/CSRF/revocation failures; inspect redaction and private network topology | PASS at source/synthetic scope — 58 core security checks pass; exact deployed boundary still requires testing |
| VM-01 Authorized additional VM | Validate cost/stock/owner/guards, create one additional active VM, inspect clean host without changing existing VM | PASS after documented replacement — 1108954 clean/SSH reachable; local and remote guards acknowledged; 1108949 absent |
| VM-02 Clean runtime preparation | Transfer exact public artifact, run guided preparation/qualification and verify pinned image/model/corpus on the new host | PENDING |
| 08 Sequential verification | Record Tests 1–8 individually with current versus reused evidence, real versus synthetic behavior, blockers and logs | PENDING |
| 09 Final validation | Lint/format/diff/source-preservation/archive checks; reconcile documentation and all unresolved checks | PENDING |
| 10 Final report | Consolidated deliverables, evidence, limits, required inputs and four readiness decisions | PENDING |

Success for this execution means a reproducible, reviewable administrator and
deployment delivery with observed source/tool behavior and honest remaining
gates. Hosted jury demonstration, private customer installation, offline
operation and external evaluation may be marked ready only when their actual
runtime/access checks pass on the exact release.

## Stage Report — 01 Discovery

### Stage
01 — Discovery.

### Objective
Identify the current application and deployment implementation without changing
services, private cases or existing source work.

### Initial State
Initial HEAD and five pre-existing files are recorded above. The active branch
contains older deployment source; newer complete committed delivery is available.

### Actions Performed
Read repository instructions, specification, plan/checklist and case matrix;
inspect Git history/branches, manifests/locks, API/jobs/worker/startup, contracts,
model/legal and deployment guides; recall relevant Octarin decisions. Read-only
provider inventory/credit and SSH inspection established the observations above.
Read the parallel evaluation thread after the user's steering. No further VM
work is planned here.

### Files Modified
No application or deployment code. Private initial-state backup and this report.

### Commands Executed
`git status --short --branch`; `git rev-parse HEAD`; `git log -8 --oneline`;
`git branch -avv`; `git diff --name-status ae9f819 19afab3`; scoped `rg`, `cat`,
`sed` and `git show` reads; SHA256 comparison; read-only provider GETs using a
private header file; strict-known-host SSH with `free`, `df`, `nvidia-smi`,
`ps` (command names only), `ss`, Docker version/Compose/ps and timer inventory.
T3 `t3_thread_list` and `t3_thread_read` only; no messages or child agents.

### Verification
System TLS client authenticated provider requests successfully. Strict SSH
connection succeeded. Core/source/contract/lock differences between initial core
and reusable deployment source are absent. Initial unrelated edits are backed up
with hashes and patch outside Git.

### Results
PASS for discovery; subsequent VM execution is outside this lane after steering.

### Issues
Default Python 3.14 urllib lacks the local issuer CA. System curl succeeded with
certificate verification enabled. Historical zero-VM/shared-key-only documents
are stale for current infrastructure/source; they remain historical evidence.

### Resource Usage
Read-only provider/SSH observations; no new compute, model loading, GPU work,
firewall/DNS change, service restart or expenditure.

### Rollback
No runtime changes. Preserve private backup; no cleanup of shared resources.

### Conclusion
Existing application and committed deployment closure can be reused. Actual
GPU/access/clean-install acceptance is not established by discovery.

### Next Stage
02 — Planning, recorded below; then 03 — Deployment preparation.

## Stage Report — 02 Planning

### Stage
02 — Planning.

### Objective
Define a sequential, evidence-driven implementation and verification path.

### Initial State
Discovery complete; user directs this lane to read parallel VM evaluation and
avoid overlapping VM work.

### Actions Performed
Defined the scoped source import, existing interfaces, resource/prerequisite
checks, ten stages, explicit evidence levels and rollback. Eight requested
integration tests remain separate acceptance cases even when their runtime
prerequisites are unavailable here.

### Files Modified
`docs/deployment/execution-20261018.md` (this authoritative record).

### Commands Executed
Private initial-state backup and hash collection; creation of this plan.

### Verification
Reusable source is committed and affects only the four deployment directories.
It has identical core/UI/contracts/configuration/locks to the starting snapshot.
No additional agent, workflow, VM or GPU operation has been launched.

### Results
PASS.

### Issues
Runtime handoff, exact image acceptance, external HTTPS trust and clean-host
installation evidence remain prerequisites, not invented defaults.

### Resource Usage
Local small text artifacts; no paid resource changes.

### Rollback
Remove only this newly added report if abandoning the task; preserve initial
files and private backup. No runtime rollback is needed.

### Conclusion
Implementation can start with the complete existing deployment closure. Each
later stage records its result before the following stage starts.

### Next Stage
03 — Deployment preparation.

## Stage Report — 03 Deployment preparation

### Stage
03 — Deployment preparation.

### Objective
Integrate the complete existing deployment dependency closure with the current
application, preserving unrelated work and canonical behavior.

### Initial State
Initial core `ae9f819`; scoped deployment paths have no pre-existing changes.
Committed delivery `19afab3` includes the guided installer, hardware/resource
checks, source/image preparation, principal session integration, lifecycle
ownership checks and exact-release acceptance validator.

### Actions Performed
Saved the initial scoped Git archive outside Git. Imported exactly the 63 changed
files from `19afab3` (47 new) after checking that no imported path was dirty or
symlinked. Existing paths outside that closure were not copied or replaced.
Imported bytes total 680,329. Reviewed runtime/session rendering, account
bootstrap, archive selection and current API/limits documentation. Kept every
unapproved candidate acceptance flag false.

### Files Modified
The 63 exact files and their before/after hashes are in private
`source-import.json`; they are confined to `deploy/portable/`,
`tools/forte-admin/`, `docs/deployment/` and `tests/deployment/`.
This report is the sole additional progress file. No shared configuration,
dependency lock, core, model or frontend file changed.

### Commands Executed
Verified `git archive`/`git diff` source import from full commit `19afab3`;
`.venv/bin/python -m pytest -q tests/deployment/test_acceptance_receipt.py
tests/deployment/test_runtime.py tests/deployment/test_profile_sessions.py
--junitxml=<evidence>/stage03.xml`; SHA256 preservation comparison.

### Verification
169 passed, one optional cached-Nginx test skipped, in 4.96 seconds. Tests cover
offline profile rendering, streaming/ranges, exact-release receipt identity,
fail-closed unapproved uploads, server-side secrets, actual session-store
bootstrap/preservation, private/hosted metadata and refusal to signal unrelated
processes. Generated media and synthetic workload evidence only. The Docker
check is scheduled explicitly for Stage 05. All five pre-existing file hashes
still match; imported closure matches `19afab3`; core/UI/contracts/dependencies
are unchanged.

### Results
PASS for source/configuration integration. No runtime acceptance is promoted.

### Issues
The historical runtime candidate still identifies `111234c`; building a new
current-core image must produce its own candidate and exact evidence. Source
tests cannot approve a real GPU/browser deployment.

### Resource Usage
Local CPU tests, generated fixtures and small public files. Cached Nginx exists
locally; no GPU, public download, model load, VM change or paid allocation.

### Rollback
Use the saved initial scoped archive and per-file hashes to revert only these
63 paths after review; remove only this import's new files. Preserve unrelated
edits, private backup and all application data. No live service rollback.

### Conclusion
The current checkout now contains the full reusable deployment tooling. Its
configuration/session/release checks work with this core at synthetic scope.

### Next Stage
04 — CLI, guided installation and immutable administrator artifact verification.

## Stage Report — 04 CLI and installation

### Stage
04 — CLI and installation.

### Objective
Ship a real independently runnable administrator artifact and verify its
installer/client behavior before any application API exists.

### Initial State
Imported dependency-free `forte-admin 0.2.0`; local Python 3.12 virtualenv,
macOS arm64 host and cached Docker. Local host is unsupported for CUDA execution.

### Actions Performed
Inspected actual CLI help/options and installer/hardware/preparation/account/
source-image paths. Executed focused behavior tests. Created one detached local
build snapshot at committed publisher `19afab3` (no new agent, branch or parallel
workflow), verified clean status before/after, and built the administrator archive
twice from that immutable snapshot with full core `ae9f819` export. Reused only
two explicitly named pinned public ReID artifacts from the prior hash-verified
public archive; bundling independently checked canonical sizes/hashes.

Extracted the actual archive, checked every release hash, ran its CLI version,
nonmutating guided-install preview, configuration-only setup twice, doctor and
privacy-safe logs. Verified retained service/gateway credentials and a generated
synthetic preservation file. Verified the actual exported source through the
source-build preview with zero build-runner calls or state creation.

### Files Modified
Imported tooling/tests/guides listed in Stage 03; this report. New build snapshot,
archive, extraction, generated configuration and logs are outside Git.

### Commands Executed
`tools/forte-admin/forte-admin --help`; `install --help`; focused pytest on
`test_installer`, `test_install_flow`, `test_hardware`, `test_preparation`,
`test_resources`, `test_source_image`, `test_public_bundle`, `test_client` and
`test_core_client`, with `--junitxml=<evidence>/stage04.xml`.
`git clone --shared --no-checkout --no-hardlinks <local-repo> <build-snapshot>`;
`git checkout --detach 19afab3a8c7867aa9c88333a2a3edb79027397c3` in that snapshot;
`python tools/forte-admin/build.py --output <archive> --with-public-resources
--public-artifacts-root <pinned-public-artifacts> --core-commit
ae9f819c3d7063e8bcf0e51855e5b4773c1961df` twice. Extracted CLI commands and
source-preview details are in `stage04-*.json` and `stage04-artifact-build.log`.

### Verification
327 tests pass in 13.89 seconds: setup/preview/resume, secure credential/account
handling, occupied ports, capability-based hardware diagnostics, public resource
hashes, offline source-build command isolation and canonical v1/v2 streaming
client behavior against actual FastAPI with generated MOV/synthetic inference.
No automatic retry, remote fallback or uncertain-result conversion is introduced.

Archive is byte-identical across two builds, 1,945,950 bytes, with 200 verified
release file hashes, 130 exact public core-source files and 21 small pinned public
resources. No core image, weight shards, secrets or cases are included.

Artifact: `~/.local/share/forte26/deployment-readiness/20261018-0344/forte-admin-0.2.0-core-ae9f819.tar.gz`.
SHA256: `992b2fd042880d32325f402b90b5ec1bf204aad70e2770cd120e4081612f2715`.

Extracted CLI reports version 0.2.0. Guided preview returns exit 2 for the
unsupported host, creates no installation and returns no application URL. Both
configuration-only setups exit 0, start no services and preserve credentials and
the synthetic file. Doctor exits 2 honestly. Support output excludes credentials
and synthetic case content. Source-build preview passes without a build or GPU.

### Results
PASS for implemented tooling, reproducible artifact and extracted-CLI mechanics.
Clean supported-host installation and real application readiness remain unverified.

### Issues
The first verification helper attempted to import a nonexistent constant for the
Node image. Product CLI checks had already passed. Corrected only that helper to
read the actual CLI parser default and completed source preview; no product fix
or acceptance change was needed. The archive is an administrator/public-source
delivery, not a complete disconnected GPU installation bundle.

### Resource Usage
Local CPU and generated data; archive about 1.86 MiB. No dependency upgrade,
large public download, image build, model load, GPU request or new expenditure.

### Rollback
No services were started. Keep or archive the new private configuration and
verification artifacts. Source rollback remains scoped to Stage 03's receipt;
do not delete unrelated cases, Docker resources or existing accounts.

### Conclusion
Administrators have a real installable artifact and working local bootstrap/
diagnostic/client commands. Reviewers still require an accepted deployment and
browser URL; configuration-only success does not supply either.

### Next Stage
05 — Hosted access-profile integration using only isolated local transport/TLS
checks; VM and external activation remain with existing runtime work/prerequisites.

## Stage Report — 05 Hosted access integration

### Stage
05 — Hosted access-profile integration.

### Objective
Verify access-layer compatibility, TLS and same-origin authorization without
changing the parallel evaluation's running model or services.

### Initial State
Attach profile and actual current core/session source are present. Existing VM
and ports remain separately owned. Local pinned Nginx image is cached. All media
and account fixtures in this stage are generated/synthetic.

### Actions Performed
Ran sequential local tests of actual FastAPI/Uvicorn, local session gateway,
generated TLS trust, v1 jury transport and cached constrained Nginx startup.
The jury-key transport remains an explicitly separate optional source component;
it is not automatically activated as browser access. No DNS, firewall, live
ingress, production account or VM service was changed.

### Files Modified
This report and deployment README's pointer to the current execution record.
Local generated TLS/media/test artifacts and logs remain outside Git.

### Commands Executed
`FORTE_TEST_DOCKER_PROXY=1 .venv/bin/python -m pytest -q
tests/deployment/test_jury_gateway.py tests/test_browser_session_integration.py
tests/deployment/test_runtime.py::test_cached_nginx_starts_with_readonly_root_and_no_capabilities
--basetemp <owned-shared-cache>/stage05 --junitxml=<evidence>/stage05-retry.xml`.

### Verification
114 checks pass in 22.63 seconds, with one existing Starlette deprecation warning.
Actual local TLS/session/core tests cover authenticated upload/poll, principal
separation, media/ranges, CSRF/revocation, readiness independent of activation,
key rotation, early admission rejection and absolute request deadlines.
Nginx configuration/startup/challenge passes with network disabled, read-only
root, no capabilities and bounded tmpfs; its temporary owned container is stopped
in test cleanup. That internal challenge probe uses a generated untrusted test
certificate; separate session/TLS tests use normal verification against their
generated trust root. Neither supplies public certificate trust.

### Results
PARTIAL for hosted integration: local transport/configuration compatibility
passes. A live assigned hosted profile, real-model browser run and outside-network
HTTPS address are unverified and were not activated here.

### Issues
Initial attempt produced 114 fixture setup errors because this run's new pytest
`--basetemp` parent did not exist. No test body ran. Following the `investigate`
workflow, the traceback and missing parent confirmed the cause. Created only
that owned parent, changed no product code, and reran the same selection
successfully. Preserve both attempts (`stage05-result.json` and
`stage05-retry-result.json`); do not count the fixture errors as application bugs.

### Resource Usage
Local CPU/loopback services and one short-lived cached Nginx test container.
No image pull, GPU workload, VM operation or additional infrastructure cost.

### Rollback
Test fixtures close owned listeners and stop their owned temporary container.
No existing application, annotation, database or cached Docker resource is
stopped or deleted. No live infrastructure rollback is needed.

### Conclusion
Hosted access components are compatible at isolated synthetic transport scope.
Attach starts no duplicate model/API/worker and does not claim an external URL.

### Next Stage
06 — Private profile, bounded qualification and offline preparation checks.

## Stage Report — 06 Private installation

### Stage
06 — Private installation profile and preparation.

### Objective
Verify isolated private topology, repeatable offline public preparation and safe
bounded qualification without using the evaluation VMs.

### Initial State
Pinned core source and 21 public resources are extracted. Large weights,
detector and exact built image are not locally supplied. Local macOS arm64 host
does not implement the selected Linux/NVIDIA CUDA execution target.

### Actions Performed
Reviewed private rendering and qualification paths: one canonical core/model/API
container with network `none`, host IPC, read-only public mounts and configured
private storage; host bridge reaches application 8000 only; model 8001 is never
exposed; session gateway and supplied-certificate ingress provide browser access.
Qualification uses its own scratch core, no ingress and ownership-verified cleanup.

Ran lifecycle/ownership/qualification tests sequentially. Used the actual extracted
resource preparer with `apply=True, online=False` to copy the shipped public bundle
into a new outside-Git directory, then repeated it and compared all file hashes.
This is public resource preparation, not case inference.

### Files Modified
This report; generated public preparation receipts/resources outside Git. No
application data, model cache, shared Docker resource or host configuration changed.

### Commands Executed
`.venv/bin/python -m pytest -q tests/deployment/test_qualification.py
tests/deployment/test_runtime_ownership.py --junitxml=<evidence>/stage06.xml`;
actual `forte_admin.resources.prepare_resources` twice with the canonical
candidate/inventory, extracted public source and `online=False`.

### Verification
93 tests pass in 0.40 seconds. Synthetic driver tests cover exact image/resource/
hardware checks, selected-device capacity, local-only qualification, readiness
timeout/interruption, retained acceptance flags, cleanup ownership, preserved
storage and refusal to stop a foreign or changed runtime. No GPU is emulated as
an accepted real workload.

Actual public preparation copies 21 files/3,826,331 bytes. Repeat reuses all 21,
copies zero bytes and preserves every hash. No corruption is found. The 31
remaining public assets and missing exact application image leave preparation
incomplete; the tool reports not ready. No model download or external resource
acquisition is attempted.

### Results
PARTIAL. Private profile/tooling/public preparation mechanics pass; a clean
supported GPU installation, actual model load, private case processing and full
offline job are unverified.

### Issues
No clean supported customer test host is available in this execution. Running
configuration checks on the prepared Mac or reading historical A100 receipts
cannot satisfy clean-install acceptance. Minimum RAM/disk/workload requirements
remain unvalidated. A completely disconnected installation bundle is not supplied.

### Resource Usage
Local CPU tests and 3.65 MiB copied public data. Zero model/GPU load, paid resource
change or case-data transfer. Existing credentials/cases are not involved.

### Rollback
Retain or archive this run's public preparation directory and receipts. Future
normal stop preserves persistent data; qualification cleanup may remove only its
verified owned scratch service. Never prune shared containers/volumes/caches.

### Conclusion
The private recipe preserves local processing boundaries and reports missing
resources honestly. Offline preparation and synthetic lifecycle tests establish
their own scopes; they do not prove offline real inference or a customer install.

### Next Stage
07 — Core/session authorization, privacy and failure-boundary verification.

## Stage Report — 07 Security and access

### Stage
07 — Source-level security and access.

### Objective
Verify the actual core/session trust boundary before enabling any new access.

### Initial State
Current core trusted-principal implementation and imported access profile;
generated-media local TLS checks passed in Stage 05. No public activation.

### Actions Performed
Executed remaining gateway ownership, session gateway/store and absolute-body-
deadline tests sequentially. Kept credentials server-side and release gates
unchanged. Read the user's new VM instruction after this selection completed.

### Files Modified
This report only; generated accounts and fixtures/logs outside Git.

### Commands Executed
`.venv/bin/python -m pytest -q tests/test_gateway_ownership.py
tests/test_session_gateway.py tests/test_session_store.py
tests/test_session_body_deadlines.py --junitxml=<evidence>/stage07.xml`.

### Verification
58 tests pass in 48.27 seconds, one existing Starlette deprecation warning.
Together with Stage 05, source tests exercise principal ownership, ownerless
history denial, media/ranges/reports/corrections, same-connection capabilities,
protected sessions, login/logout/reset/disable expiry, CSRF and bounded framing.
Generated media/synthetic inference only. Existing source has no independent
preview/clip/export routes; any future route needs its own authorization check.

### Results
PASS for source/synthetic security mechanics. Deployed-image security acceptance
remains unverified until tested on the newly authorized VM.

### Issues
Legacy shared-key mode remains one trust domain and must not expose multi-user
browser uploads. Shared host IPC and host-network ingress require the documented
dedicated controlled host. Draft legal interpretation and recognition quality
remain separate from security/operations acceptance.

### Resource Usage
Local CPU and isolated generated fixtures; no GPU or VM operations.

### Rollback
Fixtures close owned services and retain no production accounts. No live access
or persistent customer data changed.

### Conclusion
Source security checks pass; no schema/boolean is treated as proof of a deployed
security boundary. The user now authorizes one separate VM for remaining checks.

### Next Stage
VM-01 — New-resource lifecycle controls, provisioning and clean-host inspection,
then VM-02 preparation and the eight sequential integration tests.

## Stage Report — VM-01 Additional VM and clean-host discovery

### Stage
VM-01 — Authorized additional VM, lifecycle and access.

### Objective
Provide an isolated GPU installation host while preserving the parallel
evaluation's VM and keeping the complete attempt group within $3.

### Initial State
User explicitly authorized one additional VM. Live provider inventory showed
only 1108896, zero volumes and sufficient existing credit. Verified stock,
compute/IP price and image 517 compatibility; no new funding is assumed.

### Actions Performed
Prepared owner-private isolated lifecycle state and tested exact-ID/name/
environment/nonce guards before creating resources. Initial adaptation exposed
the guard's distinct recovery-authority invariant; retained that invariant and
reran all 120 fake-provider checks successfully. A state-lock collision occurred
before any initial POST; added bounded control retries without retrying POST.

First VM 1108949 was automatically deleted after one provider request failure.
Verified positive absence and preserved its closed state. Corrected GET retry
policy (maximum three attempts, DELETE unchanged, POST unsupported by guard),
reran 120 checks plus targeted transient/exhaustion/DELETE checks, then created
one replacement 1108954 with the failed attempt's debit deducted from the same
$3 group. No two deployment-owned VMs overlapped.

Initial SSH restricted to the HTTP-reflected source timed out. On the new empty
VM only, opened a bounded temporary key-only SSH rule, established a dedicated
TOFU known-host/control connection, read its actual source, pinned that `/32`
and removed the temporary broad rule in `finally`. No password/root login or
other VM rule changed. Bootstrapped an independent VM-side cleanup systemd
service before useful work. Matched its actual ACK, fixed VM ID, intent hash,
code hash and deadline against the live local guard. Read-only host inventory
then confirmed no application containers, images or GPU compute processes.

### Files Modified
This report; private operator scripts/state/logs under owner namespaces `...-04/`
and `...-05/`. No shared provisioning state, peer files, existing VM or drivers.

### Commands Executed
Read-only provider pricebook/flavor/image/credit/inventory GETs; 120 fake-provider
tests plus bounded retry tests; one POST per recorded resource attempt;
strict ownership-checked provider security-rule operations for the new VM only;
SSH/SCP guard bootstrap; `sudo systemd-run --uid=ubuntu --gid=ubuntu` for
`forte26-readiness-1108954-cleanup`; read-only OS/RAM/disk/GPU/ports/Docker/
Python/systemd inventory. Exact private requests/responses and logs are retained.

### Verification
New VM 1108954: Ubuntu 24.04.3 x86_64, Python 3.12.3, 28 CPUs, 120,841 MiB RAM
(119,444 available), 700 GiB free ephemeral disk, 83 GiB root free, A100 80GB
PCIe, compute capability 8.0, driver 570.195.03, zero GPU processes and 81,154
MiB free VRAM. Docker 29.1.3/Compose 5.0.1 and NVIDIA runtime are present.
No pre-existing containers/images or application listeners; SSH/DNS only.
Remote cleanup service is active (PID 1910); acknowledged guard hash
`68bb197204a8603065f3afdbae48865b12a94703922aebf08fdb8a226ee90de4`
matches the local source. Fixed deletion deadline is 05:40 UTC.

### Results
PASS after recovery. VM 1108954 is a clean application-installation target;
no model/application workload has yet run. First attempt is FAIL/closed, not
counted as installation verification.

### Issues
Provider GETs can fail transiently; immediate cleanup on one such failure wasted
the first boot. Bounded retries now tolerate that case without extending the
deadline. HTTP and SSH source addresses differ; the observed SSH source is used.
TOFU was recorded; no independent provider-console host-key attestation exists.

### Resource Usage
One additional active A10080, $1.35672043/hour combined checked rate. No volume,
cache deletion or additional funding. Remaining group bound and earlier debit
are recorded above; account debit includes the parallel evaluation's activity.

### Rollback
Request cleanup through the exact owned guard and verify complete provider
inventory absence. Preserve output locally before cleanup; never stop/delete
1108896 or its volumes/services. Both local and independent remote guards retain
the fixed deadline and same budget, with no rolling extension.

### Conclusion
The new clean host is reachable and protected by acknowledged cleanup controls.
Existing VM/model operations are preserved. Installation can now begin serially.

### Next Stage
VM-02 — Transfer the verified public artifact and execute guided preparation and
bounded real workload qualification on 1108954.

### VM-02 preparation checkpoint — actual clean-install issue

The full archive and all 200 release entries verified after transfer. Guided
installation began at 04:18:52 UTC on the clean host and completed its first
attempt at 04:22:36 UTC (223.369 seconds, exit 2). Capabilities/configuration pass;
the existing source Dockerfile and Next.js export built a 33.2 GB application
image from `ae9f819`. No GPU/model or case operation started. The remaining
preparation blocked on nineteen pinned files (eighteen shards and tokenizer):
`Public resource redirect targets an unapproved origin.` Both operation logs and
result were captured locally before any retry; no other installation runs.

Read-only HEAD requests to the canonical pinned Hugging Face weight and tokenizer
URLs both returned HTTP 302 to the exact HTTPS origin
`https://us.aws.cdn.hf.co`. Signed query strings were not logged. The transport
had older Hugging Face/Xet origins but omitted this one. Added one exact origin;
kept size/hash, scheme, port, credentials, proxy and other-origin restrictions.
The new regression failed before the fix and then passed with 121 related
resource/preparation/source/archive checks (7.15 seconds). Scoped lint/format and
diff checks pass. The archive publisher also includes this execution record so
its README's report link is present in the extracted artifact. No model, core,
contract, frontend or dependency setting changed. The next attempt will resume
the same installation with the corrected pinned publisher, reuse its built
image/verified files and retain credentials/data; acceptance flags remain false.
