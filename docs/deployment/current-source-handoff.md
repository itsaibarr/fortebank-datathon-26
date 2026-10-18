# Current deployment source handoff

This delivery integrates the existing application and complete administrator
tooling in an isolated source checkout. It supplies no active jury URL and makes
no clean GPU installation, real-model browser or external-access claim.

## Source and ownership

- Branch: `codex/deployment-delivery-b-20261018`.
- Worktree: `/Users/itsaibarr/conductor/repos/fortebank-deployment-delivery-b`.
- Verified base/core: `ae9f819c3d7063e8bcf0e51855e5b4773c1961df`.
- Reused deployment source: `11d3e48` from `codex/deploy-delivery-20261018`,
  including the `4030bf2` startup evidence fix and its full dependency closure.
- Owned paths: `deploy/portable/`, `tools/forte-admin/`, `docs/deployment/`,
  `tests/deployment/`. No core, UI, model, shared manifest, lockfile or other
  checkout is changed. No merge into Agent A's checkout is performed.

The startup ownership notice was sent before the user's later instruction to
stop agent messaging. This continuation sends no further messages, launches no
agents or T3 threads, and assumes no acknowledgement or runtime handoff. The
actual accessible path above and the final local commits are the handoff mechanism.

## Delivered functionality

The dependency-free `forte-admin` CLI provides `setup`, guided `install`,
`doctor`, `prepare`, bounded `qualify`, `up`, `status`, privacy-safe `logs`,
`stop`, and separately bound `connect`/`analyze`/`job` client profiles.
Installation begins locally before the API exists. Preview creates no state or
services; explicit preparation acquires only pinned public resources. Setup and
restart preserve secrets, cases and immutable corrections. Normal stop preserves
persistent storage. Local account bootstrap calls the existing session-store
tool and never puts passwords in arguments or service keys in browser code.

Private mode owns the pinned single offline application/model container, its
application-only bridge, browser session gateway and TLS ingress. Attach owns
only its access components and never starts or stops the existing model/API or
worker. The separate deployment label reports hosted versus private processing.
Supplied certificates/internal CA work without public certificate issuance;
loopback self-signed setup is explicit and still needs browser trust.

Public source export comes from a full Git commit, not a changing checkout.
Online public acquisition is separate from case processing. Private inference
uses a network-disabled container. The tool has no hosted fallback, training
path, telemetry sink or invented model substitution. Small public resources may
ship with the admin archive; weights and the built core image do not. A fully
disconnected installation bundle has not been verified.

One Linux x86_64 NVIDIA CUDA deployment recipe is implemented. Hardware checks
evaluate free GPU capacity and the actual frozen multimodal configuration.
Minimum host RAM/disk and a clean customer hardware qualification remain
unvalidated. The historical A100 measurement is not a minimum specification.
Normal startup requires exact-release operational and security evidence;
bounded qualification cannot manufacture those acceptance flags.

## Verified interfaces and integration

See [observed-contract.md](observed-contract.md) and the canonical contracts at
the pinned core. Multipart field `file`, `X-API-Key`, v1/v2 analyze and poll
routes, and `processing|done|failed` are unchanged. The client streams uploads,
preserves additive result fields and uncertainty, and does not retry POST,
follow redirects or turn failures into clean negatives. The destination is
displayed before submission. Connection profiles are distinct from installations.

The source session gateway and core enforce principal ownership for jobs,
originals, evidence, corrections, reports and subsequent ranges. Tests use real
FastAPI/session components with generated media and synthetic inference. That
establishes source mechanics, not a deployed or real-model security acceptance.
The separate jury v1 transport is tested source only and is not automatically
activated by either deployment profile. No new route, dashboard or analysis
backend was created here. No shared core patch is required for this source
integration. Earlier proposed core patches remain historical and must not be
applied to `ae9f819`.

The existing UI already reports processing destination, hosted/private label,
input limits, readiness, manual retention and no training use. Current configured
limits remain a 256 MiB multipart body, MOV, 180 seconds, 30-second upload
deadline and 270-second job budget with two admitted jobs and one model sequence.
Retention of originals, derivatives, temporary files and backups remains manual;
the installer does not promise automatic application cleanup.

## Read-only VM inventory and boundaries

At approximately 03:24 UTC on October 18, 2026, read-only SSH found VM 1108896's
existing `forte26-frozen-integrated` container running. Its A100 80GB had
73,531 MiB allocated; about 113,069 MiB host RAM and 648 GiB `/ephemeral` were
available. Loopback ports 8445 and 18003 were occupied. The observed deletion
timer remained 07:00 UTC. No private job directory or model response was read.
Provider credit was $23.20886051427745, an observed cumulative debit of about
$6.79114 from the original $30, subject to settlement. This is not a new budget.

The recorded runtime owner remains `integration-completion-20261018-01`, with
a $7 session ceiling, $30 project ceiling, $1.50 reserve, useful stop 06:30 UTC
and deletion 07:00 UTC. The host and its ports, GPU, storage, ingress and lifecycle
were not handed over. This lane performed no runtime restart, image load, GPU
request, staging, firewall/DNS change or paid allocation. Do not activate from
these instructions against that shared runtime.

## Installation and remaining activation steps

Use [README.md](README.md) to build/install the real administrator archive,
[guided-install.md](guided-install.md) for preview and explicit preparation,
[administrator.md](administrator.md) for TLS/accounts/configuration,
[reviewer.md](reviewer.md) for browser use and
[api-client.md](api-client.md) for the administrative API client.
The current archive and exact checks are recorded in
[current-source-verification.json](current-source-verification.json).

The designated integrator must supply an exact new image/model/corpus/runtime
manifest and accepted workload evidence, an assigned runtime test window and
ports/storage, matching trusted-principal credentials, and a hostname/certificate
trust choice. Then perform one bounded authorized development upload through
the real session stack; verify actual inference, original-PTS marker/evidence
and provision routing, two-user denial including fresh ranges/reports, offline
analysis, setup/restart persistence, large MOV/capacity/model-failure states, and
an authorized browser workflow outside the VM network. Reserved and jury footage
must not be used for these rehearsals.

Only that reviewed evidence can promote exact-release acceptance. A local
certificate, source archive, configuration preview, cached example or synthetic
test cannot supply an external URL or clean-install result. Upgrade/rollback must
use compatible pinned images and preserve the account principal database and
case/correction storage; core migration compatibility remains the core owner's
decision. Rollback stops only the newly owned profile, never shared services.
