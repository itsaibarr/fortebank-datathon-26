# Agent B deployment handoff

The current isolated integration is documented in
[current-source-handoff.md](current-source-handoff.md). It uses core `ae9f819`
and the complete deployment closure from `11d3e48`, without changing core files
or activating the separately owned VM. The receipts below remain historical;
they must not be treated as current image, external-access or installation
acceptance.

## Checkpoint and ownership

- Branch: `codex/guided-private-install`.
- Worktree: `/Users/itsaibarr/conductor/repos/fortebank-install-v2`.
- Verified base: `131463f21286c03d12a77f5e73306b7024fa6ee6`.
- Stable Agent A source consumed: `e55c0773ea74e2745ea33512d19bfaa38b32d7fb`,
  including `bdf3173` ownership, `5be7d78` session gateway and `7fa153f` UI work.
- Owned paths: `deploy/portable/`, `tools/forte-admin/`, `docs/deployment/` and
  focused `tests/deployment/`. Core schemas, model/serving parameters, legal
  semantics, UI and final live cutover remain Agent A's ownership.
- The operational documentation chain starts at `8d3c0d2`; the current B head
  and standalone receipts are recorded in the shared ledger's B reservation.
  Agent A's isolated integration checkout is
  `/Users/itsaibarr/.t3/worktrees/fortebank-datathon-26/t3-ca5de3e3`, branch
  `t3/review-agent-b-integration`. Its final application snapshot is
  `ebb3d82e8728dec21289d34e9b9fb81b95f5d0f3`.
- Shared source reservations are now recorded in
  `/Users/itsaibarr/conductor/repos/fortebank-datathon-26/.git/forte-coordination/ledger.json`,
  with integrator identity in `owner.json`. Updates use `fcntl.flock` on the
  adjacent `coordination.lock`, preserve peer entries and replace JSON atomically.
  This source lock is separate from the GPU lifecycle lock.

The final publisher commit and file hashes are recorded in the administrator
archive's `RELEASE.json`. Stable source integration does not approve an image or
activate a runtime. No core/API/model process, driver, firewall, DNS or live ingress was
changed by this lane. No additional paid machine, GPU workload or heavyweight
image build was run. Agent A remains the default release integrator.

## Final operational state

The evaluation lifecycle is closed. TEST's public receipt
`.context/verify/mechanic-validation-lifecycle-20261018.json`, integrated at
`2fd219175fe61ebb389568a11e74615a4acdb692`, reports zero provider VMs and volumes
at **2026-10-18 01:03:11 UTC**. All three baseline archives and 436 file hashes,
plus the final runtime archive's three checks, were restored locally. Observed
shared spend was $1.379332437 against the $3 cap, subject to billing settlement.
No deadline was extended. There is no active deployment VM or verified live
hosted URL. Agent B has no further VM, model, build or service operation queued.

The final application-source GPU/API test was not executed: the separate-process
proposal missed the agreed 01:00 start cutoff. Earlier real baseline inference
and B's unchanged-core transport checks do not validate the final application.
Session, private-installer, public HTTPS/browser and quality acceptance remain
unestablished.

The new source/admin archive exports exact application commit `ebb3d82` from a
separate clean detached publisher at that same full commit. Its filename is
`forte-admin-0.2.0-integrated-ebb3d82e8728.tar.gz`, SHA256
`5a22ba3def3af670c4862d64edf26257a476e51be3598f51fd153aacb324a7b9`,
1,901,392 bytes. Two local builds are byte-identical. The original `e55c077`
archive, SHA256 `7fdd77bfd6e8485254395a7c0a7fa9338ed993430037ae5ea35e830ce79f2b41`,
is unchanged. Lifecycle closure is documented separately; the completed archive
is not overwritten or relabeled to a later documentation commit.
The [release and closure receipt](release-ebb3d82-verification.json) records all
192 release hashes, the complete 128-file immutable Git source export, 21 public
assets, extracted CLI/import/preview checks and two identical builds. Matching
`.verification.json` and `.checks.json` sidecars sit beside the archive. All five
installer acceptance flags remain false; no image build or final-source model
execution is implied.

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

At the 18 October 2026 00:49 UTC coordination checkpoint, a different authorized
VM, `1108722`, is owned by `mechanic-validation-20261018-01` for three frozen
baseline cases and verified local backups. Its key-only, network-disabled
evaluation runtime is not a session-enabled deployment. The owner reported the
first case's complete local restore with all 100 file hashes verified; cases two
and three and their preservation were still pending. Agent B has no runtime
activation handoff. The useful-work cutoff remains 01:08 UTC and the deletion
deadline remains 01:28:30 UTC, within the existing $3 session cap, $30 project cap
and $1.50 reserve. These are coordinated bounds, not a fresh credit reading.

The owner subsequently confirmed that the current entrypoint's `wait -n` and
EXIT cleanup couple the API to the resident model: restarting the API also stops
the model. The only accepted post-preservation access plan is a separate bridge
to unchanged container port 8000 and bounded health/client checks. Follow the
[source-only procedure](unchanged-core-attach.md); it grants no execution window,
core overlay, session transition or public ingress permission.

The later explicit owner handoff permitted fixed-script bridge port 18000 and
local SSH forward 8040 through 01:03 UTC, after all three backups and 436 restored
file hashes were acknowledged. Agent B completed real-core health, static UI,
unauthenticated 401 and authenticated v2-contract client checks at 00:58:57 UTC.
The exact forward was canceled, bridge and relay children exited, both listeners
closed and the unchanged core remained running. No private case/output reads,
uploads, model generation or core changes occurred. See the
[sanitized transport receipt](vm1108722-transport-verification.json). This
completed window was released; it does not establish new-image, session,
private-installer or public HTTPS/browser acceptance.

The fixed public archive was transferred to Agent B's separate VM staging area;
a small read-only inspection verified all 187 release hashes after SSH recovery.
The public CPU build was skipped because too little time remained before its
00:45 UTC deadline. No new application image was built, and that expired window
does not authorize another build or activation. The original local operational
helper's path and cleanup findings were corrected in separate v2 files with 21
fake-executor regressions passing; neither helper was executed on the VM.

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
[verification.json](verification.json) and
[integration-review-20261018.json](integration-review-20261018.json). The fixed
integration checkpoint passed 706 tests with no skips and four existing warnings;
its lint and formatting checks passed. No fresh clean-host GPU installation,
new heavy image build, actual case through this ingress, externally reachable
HTTPS URL or complete disconnected installation bundle has been verified. The
historical real core rehearsals and incomplete final-backup preservation are
recorded in [frozen inference](../frozen-inference.md); they are not receipts for
this new source image or access stack.

## Exact remaining integration actions

1. On an existing authorized customer/VM host, assign one runtime owner and a
   bounded GPU window. Inspect available capacity, disk, active jobs and budget
   before changing any runtime. VM `1108722` has been deleted after complete
   preservation; no active deployment target or live hosted URL remains. No new
   rental is authorized by this handoff. Further real-installation or external
   access checks require a separately assigned existing authorized environment
   and bounded runtime handoff; source packaging does not create that resource.
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
