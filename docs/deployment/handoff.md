# Agent B deployment handoff

## Checkpoint and ownership

- Branch: `codex/guided-private-install`.
- Worktree: `/Users/itsaibarr/conductor/repos/fortebank-install-v2`.
- Verified base: `131463f21286c03d12a77f5e73306b7024fa6ee6`.
- Stable Agent A source consumed: `e55c0773ea74e2745ea33512d19bfaa38b32d7fb`,
  including `bdf3173` ownership, `5be7d78` session gateway and `7fa153f` UI work.
- Owned paths: `deploy/portable/`, `tools/forte-admin/`, `docs/deployment/` and
  focused `tests/deployment/`. Core schemas, model/serving parameters, legal
  semantics, UI and final live cutover remain Agent A's ownership.

The final publisher commit and file hashes are recorded in the administrator
archive's `RELEASE.json`. Stable source integration does not approve an image or
activate a runtime. No VM/GPU process, driver, firewall, DNS or live ingress was
changed by this lane. No additional paid machine, GPU workload or heavyweight
image build was run. Agent A remains the default release integrator.

## Implemented independent deliverables

`forte-admin install` orchestrates capability checks, repeatable configuration,
pinned public preparation, explicit source-image build/import, local account
bootstrap, TLS, owned startup and bounded readiness in one invocation. Preview is
nonmutating. Resumption preserves cases, corrections, account state and existing
secrets. Installation state is separate from endpoint-bound client profiles.
The API client streams the existing multipart `file`, polls the existing
statuses, preserves uncertainty/additive fields and reports the destination
before submission. It has no remote inference fallback.

Public source export uses a verified full Git commit and the existing build
allowlist. `SOURCE.json` binds every exported file. The customer-side builder
verifies the extracted bundle, uses pinned Node/base images, builds in an
isolated public copy and records the resulting immutable local image ID. It
mounts no cases and uses no GPU. Explicit online preparation may acquire public
dependencies; offline build denies outbound network. Existing apt resolution is
not a hermetic OS snapshot. Public-resource preparation verifies pinned model,
tracking, configuration and official-law assets without case mounts.

The source now includes the real local account tool, session gateway and UI
contract from Agent A. Service key and dedicated gateway token stay server-side.
The gateway authenticates an opaque principal; the core persists it at admission
and checks every existing job/source/evidence/correction route and fresh range
request. Ownerless/cross-owner jobs return generic 404 in trusted mode. Browser
uploads require explicit activation plus a same-connection security capability
and model readiness. See [the session contract](../../contracts/browser-session-contract-v1.json).

Private profiles own the offline core, fixed application-port bridge, local
session gateway and TLS ingress. Attach profiles own their gateway and ingress;
the existing core, bridge, GPU and storage remain with the runtime owner. Host
helpers verify private process identity/state. Container resume/stop checks
verify project/service labels, immutable image, GPU allocation, network and
mount ownership before acting. No shared cache or Docker resources are pruned.

## Historical image versus new source build

[`core-current.candidate.json`](../../deploy/portable/core-current.candidate.json)
and the canonical frozen runtime manifest describe historical core `111234c`
and local image
`sha256:ee82962c4ee4d9026ef499a0854bcb485c94a18db97e07719800ca6dfe4276dd`.
The VM that held that image was deleted. No registry image was published; the
old candidate remains historical and unapproved, with all five installer
acceptance flags false. It must not be described as the new session-aware image.

A release archive can export core `e55c0773ea74e2745ea33512d19bfaa38b32d7fb`.
`install --build-core` builds that snapshot and derives a separate local manifest
with its new image ID, source/contract fingerprints and preserved ancestry.
Release, model-workload, offline-analysis, browser-session and ownership
acceptance flags remain false. Neither JSON validation nor source-build success
can approve those checks.

Explicit `install --qualification` verifies pinned assets and performs a bounded
local-only model/visual warmup on an authorized free compatible CUDA GPU. It
uses separate scratch storage, exposes no browser ingress and stops its owned
core before reporting completion. It returns no application URL and does not
promote release, security or quality acceptance. A physical host or VM is valid;
the GPU product name alone is neither a requirement nor proof of suitability.

## Checks completed and limits

Focused checks cover zero-mutation preview; repeated setup and credential/case
preservation; capability-based GPU selection; public asset/source integrity and
resumption; fake-runner source builds; actual pinned Git export; lifecycle,
process/container ownership and shutdown boundaries; local TLS; session/account
integration; endpoint-bound API transport; bootstrap-error redaction; and
qualification cleanup. Some transport tests run the real FastAPI/session
components with synthetic inference and synthetic MOV inputs. They establish
software mechanics, not actual model analysis or legal/detection accuracy.

The root integrator records the final suite totals and receipt in
[verification.json](verification.json). No fresh clean-host GPU installation,
new heavy image build, actual case through this ingress, externally reachable
HTTPS URL or complete disconnected installation bundle has been verified. The
historical real core rehearsals and incomplete final-backup preservation are
recorded in [frozen inference](../frozen-inference.md); they are not receipts for
this new source image or access stack.

## Exact remaining integration actions

1. On an existing authorized customer/VM host, assign one runtime owner and a
   bounded GPU window. Inspect available capacity, disk, active jobs and budget
   before changing any runtime. No current GPU host or live hosted URL is
   available in this handoff, and the old allocation is not a fresh budget.
2. Build/import the new pinned core image and public resources. Run the local
   qualification on the actual selected device, retain the new immutable image
   and model/corpus/configuration fingerprints, and review the host-specific
   workload requirements. Do not infer compatibility or speed from parameter
   count or total RAM alone.
3. Verify and accept the new release/security handoff before enabling browser
   uploads. Exercise actual accounts, cross-user denial for every existing job,
   source, evidence and correction route and subsequent ranges. Recheck any new
   preview/clip/export route before release; it is not automatically covered by
   the current route inventory. Ownerless historical jobs remain denied rather
   than automatically assigned.
4. Supply the intended hostname, matching certificate/key or trusted internal
   CA, listen scope and approved core/bridge handoff. Private installation owns
   its core; attach changes only the owned access layer and requires the core
   owner to configure the matching trusted token. Do not restart Agent A's
   services or change DNS/firewalls without that coordinated cutover.
5. Complete an authorized development MOV upload through real inference and the
   browser. Check original interval/PTS, participant/evidence/provision links,
   offline IPv4/IPv6 denial, persistence/restart, large uploads, queue limits and
   unavailable-model states. Private frames remain human-reviewed locally;
   reserved and jury media are excluded from rehearsals.
6. For hosted jury access, complete the same workflow from an authorized browser
   outside the VM's local network over the actual HTTPS origin. Record the URL
   only after this passes. Rollback stops only owned services, preserves data and
   restores a compatible pinned release; core migration compatibility remains
   Agent A's responsibility.

Administrator instructions are in [guided installation](guided-install.md),
[administrator](administrator.md), [resource preparation](resource-preparation.md)
and [operations](operations.md). Reviewers use [the browser quick start](reviewer.md).
Private data never enters Git, source/image build contexts, external inference
or diagnostic output. Uploads are not training data; pretrained weights and
official-source-only local retrieval remain unchanged.
