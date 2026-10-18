# Agent B source delivery and runtime handoff

This is a source-only deployment delivery. It does not activate a GPU model,
browser uploads, jury ingress or any acceptance flag.

## Ownership and immutable inputs

- Branch: `codex/deploy-delivery-20261018`.
- Worktree: `/Users/itsaibarr/.t3/worktrees/fortebank-datathon-26/codex-deploy-delivery-20261018`.
- Verified base: `6c7bbe05a714172d0f38c2de2b4f907ce8db7522`.
- Deployment fix: `4030bf272f413dfbc603d7eb21dc4bbd5399a537`.
- Reserved scope: `deploy/portable/`, `tools/forte-admin/`,
  `docs/deployment/`, `tests/deployment/`. No core/API/model/UI, root manifest,
  lockfile or peer checkout was edited.
- No other T3 thread or delegated agent was launched or triggered.

The earlier deployment, client, guided installer, account integration and
profiles were already committed at the base. This continuation reuses them.
The separately attached Agent A implementation prompt was not available;
canonical contracts, implementation and stable handoffs supplied the interfaces.

## Delivered artifact

The current source archive is:

```text
/Users/itsaibarr/.cache/forte-deploy-b/delivery-20261018/forte-admin-0.2.0-4030bf2-core-ae9f819.tar.gz
SHA256 a1ec585d641c5dc5ae75c20761482ccc469838cbfa621a82f8450655d1dabf62
```

It binds administrator publisher `4030bf2` to the runtime owner's frozen
application source `ae9f819c3d7063e8bcf0e51855e5b4773c1961df`.
Two builds are byte-identical. All 197 release entries and 130 public application
source files pass their hashes; 21 small pinned public assets are included.
It contains no built application image, model shards, credentials or cases.
The earlier archive exporting `6c7bbe0` is preserved separately.

The two core exports have identical public build-file inventories and hashes.
At 03:14:31 UTC all 130 files also matched `/opt/forte26/app` on VM 1108896.
This verifies the public source bytes, not an application image or model run.
See [the archive check](artifact-ae9f819-verification.json) and
[the staged-source check](staged-source-check.json).

Install the actual archive using Python 3.12+; no public package is assumed:

```sh
mkdir -p "$HOME/.local/lib/forte-admin-delivery"
tar -xzf /approved/path/forte-admin-0.2.0-4030bf2-core-ae9f819.tar.gz \
  -C "$HOME/.local/lib/forte-admin-delivery"
export PATH="$HOME/.local/lib/forte-admin-delivery/forte-admin-0.2.0/tools/forte-admin:$PATH"
forte-admin --version
forte-admin install --help
forte-admin install --mode private --build-core --qualification --preview
```

The extracted CLI and source-build previews passed without creating installation
state or calling a build runner. On this unsupported local macOS host, install
preview correctly exits 2 and supplies no application URL. This is not a clean
GPU installation. Follow the packaged administrator/guided-install/resource
preparation guides for a supported Linux x86_64 NVIDIA CUDA host. Minimum RAM,
disk and workload acceptance remain unvalidated; a GPU product name is not a
qualification result.

## Changes and validation

Normal startup previously accepted true verification booleans plus any existing
receipt file. A regression reproduced acceptance of `{"synthetic":true}`.
Startup now calls the existing exact-release evidence validator before Docker
or GPU operations, verifies the configured ingress image, and requires the
appropriate browser or single-administrator evidence policy. Status cannot
report verified browser access from flags alone. Bounded qualification stays
separate; shutdown still checks ownership and preserves storage.

The synthetic runtime fixtures now bind their evidence to the actual helper
closure. The session rendering fixture supplies the raw HTTP request line that
the strengthened gateway validates. Administrator documentation explains the
receipt format and older-manifest compatibility boundary.

- Deployment suite: **697 passed**, no skips, one existing warning.
- Whole local suite: **1082 passed, one deselected**, four existing warnings.
- Scoped Ruff and formatting: all 38 deployment Python files pass.
- Archive rebuild, extraction, hashes and nonmutating previews: pass.

The deselected core-owned test used an obsolete empty configuration and worker
signature. A separate [test-only patch](patches/mechanic-dispatch-fixture.patch)
passes all six tests in a disposable copy and applies against its recorded base.
It was never applied to this checkout. Runtime source `ae9f819` independently
contains a stronger correction, so that historical proposal must not be applied
to it. See [base and scope](patches/base.json).

Full evidence levels and exact commands are in [verification.json](verification.json).
These are source, synthetic transport and local cached-Nginx checks. They do not
establish detection/legal quality, GPU inference, complete offline analysis,
clean installation or externally reachable HTTPS.

## Runtime owner notice supersedes the earlier empty inventory

The initial live provider check found zero VMs/volumes. A later preflight found
new VM **1108896**, created by `integration-completion-20261018-01`.
User authorization to create/use a VM was received here; B did not create a
duplicate, acquire the lifecycle lock or alter the other owner's provisioning.

The explicit current owner is thread
`98fef0e2-ae91-41d5-aa8c-42a9a97e61f6`, source **ae9f819** on
`codex/frozen-inference-completion`, coordinated under **741**.
It owns downloads, source/static build, full hash/warmup qualification, bounded
integration smoke, runtime transport/UI preparation and lifecycle. It plans a
separate key-only loopback **8002** and job root for status thread **3b38** after
qualification, for serial legacy-v1/reasoning-v2 comparison.

The owner explicitly prohibits B staging, restart, ingress/lifecycle changes or
another VM. No deployment test window has been handed to B. A source delivery
does not change that ownership. The old coordination ledger contains stale
preflight-only records; it must not override this newer explicit notice.

At 03:11 UTC read-only inspection found A100 80GB PCIe, driver 570.195.03,
120841 MiB total RAM, 118913 MiB available, and about 700 GiB free on
`/ephemeral`. At 03:14 UTC the visible container was a public vLLM base image
`sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b`
on bridge networking with no GPU request or FORTE model configuration. This was
public preparation, not a qualified application/model service. No private job
root, case content or model output was opened.

Useful work stops **06:30 UTC**. Deletion is acknowledged for **07:00 UTC**;
the remote `forte26-budget-delete.timer` was directly observed with that deadline,
and the recorded local cleanup process was alive. Session cap is **$7** within
the **$30** project cap, with **$1.50** reserve. At 03:12:45 UTC provider credit
was $23.457592593110796; observed cumulative debit from the original $30 was
$6.542407406889204, subject to settlement. This lane's unused $3 guard rehearsal
never created an intent, state, ACK, active guard or resource and controls nothing.

## Interfaces, remaining work and activation boundary

The same-origin browser uses the existing session gateway; service secrets stay
server-side. The client retains multipart `file`, `X-API-Key`, versioned analyze
and polling routes, and `processing|done|failed`, including uncertainty and
additive fields. Source, evidence, corrections and report remain core-owned.
The installer keeps private/attach ownership separate from the private/hosted
processing label. Attach launches no model or worker. Private owns the packaged
offline core plus its own bridge/session/ingress. Retention remains manual;
uploads are not training data and local failure never triggers hosted fallback.

Before any B activation, the runtime owner must finish its current qualification
and serial comparison, then provide an exact image/model/corpus/configuration
manifest, assigned ports/storage, compatible trusted principal/session boundary,
and a bounded deployment window. The key-only comparison service on 8002 is not
a browser/multi-user handoff. A real hostname or IP certificate/trust choice and
external reviewer access check remain outstanding. No jury HTTPS URL is claimed.

Then verify a real authorized development upload and actual inference, source
interval/evidence/rule routing, two-account denial including later ranges and
reports, offline analysis, persistence/restart, large MOV, capacity and model
failure states, followed by an authorized external browser workflow. The
application's exact-image acceptance evidence must be reviewed before flags are
promoted. Rollback stops only the newly owned access profile and preserves cases,
corrections, credentials and the existing runtime.

The archive is a separate full deployment closure. The runtime branch has older
deployment files: do not cherry-pick `4030bf2` alone there or overlay this changing
checkout. Integrate the complete reviewed deployment artifact/source closure in
isolation. No core inference, UI, model, quantization, corpus or role semantics
were changed by this lane. Axxon-inspired adaptation remains PRODUCT/741 work;
this packet grants it no GPU reservation or deployment acceptance.
