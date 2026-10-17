# Agent B deployment handoff

## Ownership and checkpoints

- Branch: `codex/deployment-private-cli`.
- Worktree: `/Users/itsaibarr/conductor/repos/fortebank-deploy-b`.
- Original verified base: `7d9a1ca2ffda93f6c2dde4eaf8a5ca4c7d247eeb`.
- Consumed stable Agent A core: `111234c885f0a23d323fe72a81450dfca5aa7e60`, fast-forwarded only in B's worktree.
- Owned paths: `deploy/portable/`, `tools/forte-admin/`, `docs/deployment/`, `tests/deployment/`.
- Agent A acknowledged these boundaries at 22:50:26 UTC, single-reviewer-only access at 22:51:51, and no attach/cutover grant at 22:54:23 on October 17, 2026.
- Agent A's later asset/configuration/resource-envelope addenda were inspected read-only while uncommitted. They do not silently replace the stable release candidate. Consume their next stable commit through another isolated integration.

No root/shared manifest, lockfile, Dockerfile, core/API/model/UI source or existing checkout was edited by B. No VM restart, GPU workload, service attach, firewall/DNS/ingress change, additional allocation or payment was performed. A remains the designated integrator and runtime owner. A short health/static-only read window was later offered and closed; B did not use it to activate services or access cases.

## Delivered components and actual evidence level

`tools/forte-admin/` supplies the dependency-free `forte-admin` executable, nonmutating setup preview, owner-only repeatable setup, doctor, explicit pinned-image preparation, up/status/stop and sanitized support output. Existing data, service secrets and corrections survive setup and normal shutdown. Installation configuration is separate from connection profiles. First-administrator creation remains the core session layer's job; no administrator account is fabricated.

The client uses the existing v1/v2 multipart `file` and `X-API-Key` contract, streams uploads, polls `processing|done|failed`, preserves additive fields and uncertain results, refuses redirects/automatic POST retries/proxies/fallback, and binds private credentials to the chosen endpoint. Optional administrator-gateway credentials come from a separate private file. Destination appears before submission. Full results are written only when explicitly requested to a new private path outside Git; raw case output is not printed.

`deploy/portable/` supplies two rendered Compose profiles. Attach owns only its TLS ingress and never the existing bridge/core/GPU. Full private owns the canonical single offline core container, a fixed-app-port-only host bridge and supplied-certificate TLS ingress. The canonical host IPC mode is preserved. There is no duplicate model or production mock fallback. The helper `build_core.py` exports a verified Git commit and builds the existing UI/Dockerfile from that public snapshot; only its preview was exercised, not the heavyweight core rebuild. Apt resolution in the existing Dockerfile is not a hermetic OS snapshot; deploy its resulting immutable image ID.

The actual-core client tests run stable FastAPI/Uvicorn, actual generated MOV probing/storage and versioned schemas with a clearly synthetic inference runner. They establish transport compatibility, **not real model inference**. Local cached-Nginx checks establish configuration syntax, constrained container startup and HTTPS auth rejection. Separate synthetic checks cover 32 MiB binary/206 streaming, hostname verification, changed assets, ownership-safe shutdown and persistent setup. None is a clean GPU install, real-case ingress rehearsal or external browser acceptance.

Administrator/reviewer guides and API examples are in [README.md](README.md), [administrator.md](administrator.md), [reviewer.md](reviewer.md), [api-client.md](api-client.md), [operations.md](operations.md) and [observed-contract.md](observed-contract.md). The real admin archive is built by `python3 tools/forte-admin/build.py --output /outside/git/forte-admin-0.1.0.tar.gz`; it has no model, case data or credentials. Its `RELEASE.json` records its source commit and per-file hashes.

## Verified interfaces versus proposed integration

The source of truth is the stable canonical [core handoff](../../contracts/frozen-runtime-manifest-v1.json) and [observed interface record](observed-contract.md). V1 remains unchanged. V2 is separate, preserving `done` versus assessment uncertainty. Limits are 256 MiB for the complete multipart body, MOV, 180 seconds, a 30-second upload deadline, 270-second overall job target and two admitted jobs with one resident model sequence. UI/API use one origin. Original and evidence routes are authenticated and source-hash checked, but the shared key authorizes every case in the service root. There is no per-principal ownership or secure browser session.

The installer schema is deliberately separate from `forte.integration/1`. `import_handoff.py` preserves the canonical provenance in an **unapproved** candidate. It can map the later canonical `forte.public-assets/1` inventory by explicit container paths and verify the exact effective-config hash. All release/workload/offline/browser/ownership acceptance flags remain false. A validator or valid JSON cannot approve itself.

The prepared [trusted-principal patch](patches/README.md) is an explicit proposal against `111234c`, not an applied change. Its SHA256 and base-file hashes are recorded. It adds an optional dedicated trusted gateway token and persisted opaque case owner across both API versions, all media/correction routes and later byte ranges; default legacy behavior remains unchanged. It passed `git apply --check` and 31 targeted tests only in a disposable patched snapshot. It does not implement browser sessions. Current ingress strips identity/token headers and therefore cannot enable that mode by itself. Agent A must review/apply it, provide the secure session boundary, update the UI and rebuild a new core image before security acceptance.

Required UI onboarding contract: hosted/private label; actual destination; real readiness and input limits; manual retention for originals, derivatives, temporary files and backups; training disabled; honest cached-example labeling and no hosted fallback. These changes remain Agent A's ownership. No second dashboard was created.

## VM/resources and exact activation actions

See the dated [read-only VM receipt](operations.md). At 22:52 UTC the existing host had one A10080, driver 570.195.03, no published container ports and a new production image starting offline. Credit was about $25.24394 versus $27.55036 at session start; settlement can lag. This is not a fresh budget. A later reported that its two real jobs completed as partial/insufficient-evidence results and that services were stopped for backup/cleanup. B has not independently rerun or extended them. Historical observed host capacity is not an approved minimum. Core release, workload, RAM/disk minimum and security acceptance remain unset, as directed by A.

The immutable local image ID is `sha256:ee82962c4ee4d9026ef499a0854bcb485c94a18db97e07719800ca6dfe4276dd`; it is not a published registry address. Import an approved saved-image artifact or build from the pinned source snapshot, then verify the resulting ID. The initial installer candidate intentionally has no invented complete asset inventory or resource requirements.

The next integrator must:

1. Commit/accept the canonical public inventory, exact effective configuration and measured resource envelope. Map public resources into the candidate's explicit `/models`, `/legal` and `/resources/config` layout, preserving source hashes and canonical model/serving parameters. Approve target-specific host requirements from actual tests; do not infer minimums from 27B or a container-RAM sample.
2. Review the proposed ownership patch and implement the agreed secure browser session/UI integration. Verify both principals across every job, original/evidence/correction/export/preview/clip route and independent subsequent ranges. Until then, browser multi-user/private uploads stay disabled; an explicit administrative transport is one trust domain only.
3. Supply the real hostname, matching certificate/private key (public or internal CA), immutable ingress image, intended bind scope and an authorized runtime test window with a single service owner. Do not assume the prior paid VM remains available after cleanup.
4. Build/import the exact image and install prepared public assets. Run doctor, profile-scoped startup/readiness, one bounded authorized development upload and actual inference, evidence/marker/provision check, offline analysis, persistence/restart, large MOV and queue/unavailable-model behavior. Use only development media allowlisted for that environment, never reserved or jury footage.
5. Verify an authorized browser outside the VM's local network over the actual HTTPS origin. Record the reachable URL only after this passes. Rollback is profile-scoped `stop`; preserve data/config/secrets and restore a compatible pinned release. Application migration or rollback compatibility remains A's decision.

No external hosted URL is activated or verified. No clean private GPU installation, complete disconnected bundle, real-case run through this ingress, browser session isolation or final jury workflow is claimed. These precise dependencies do not prevent use/review of the independently completed tooling.

## Verification receipts

[verification.json](verification.json) records the deployment checks, actual-core synthetic transport, local TLS check, archive verification and explicit missing evidence. [patches/verification.json](patches/verification.json) records the separate 31-test proposed-core check. Operational tests are not legal/detection accuracy.
