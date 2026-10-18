# Deployment operations

This runbook covers `codex/guided-private-install`, based on
`131463f21286c03d12a77f5e73306b7024fa6ee6`, with stable core source
`e55c0773ea74e2745ea33512d19bfaa38b32d7fb`. See [the handoff](handoff.md) for
integration status and [the contracts](observed-contract.md) for API/session
behavior. Source includes principal ownership, local account/session services
and the corresponding browser UI. Runtime acceptance remains a separate gate.
No current VM, activated HTTPS URL or fresh GPU installation is claimed.

## Service ownership

A full private profile owns its one offline core container, application-only
host bridge, local session gateway and TLS ingress. An attach profile owns its
session gateway and ingress only. The handed-off core, existing bridge, GPU,
storage and jobs stay with their designated owner. Attach must never start a
second model or configure the existing core's trusted token without the owner's
handoff. Separate worktrees do not isolate ports, GPU memory or volumes.

Owned containers are checked against project/service labels, immutable image,
network mode, selected GPU and mounts before resume or shutdown. The session
helper records private PID/start-time/script/configuration/token identity; the
application bridge verifies its own private process/token state. Identity
mismatches block signals to an unrelated process. Private state and secrets
stay outside Git. Do not edit daemon state to bypass an identity failure; inspect
it locally and coordinate recovery with the owner.

Routine commands are profile-scoped and preserve data:

```sh
forte-admin doctor --installation /srv/forte-installation
forte-admin status --installation /srv/forte-installation
forte-admin stop --installation /srv/forte-installation
forte-admin up --installation /srv/forte-installation
```

`up` requires the real release/resource/security receipts. Repeated guided
`install` preserves account state, secrets, cases and corrections. `stop` stops
only owned services and never deletes volumes. `logs` exposes sanitized
operational facts rather than raw model prompts, case output or credentials.
Never use global Docker pruning, shared cache cleanup or `down -v` for recovery.

## Hardware and preparation

The current backend uses one compatible NVIDIA CUDA GPU on a Linux host, a local
Docker Engine, Compose v2 and NVIDIA Container Toolkit. Ubuntu 24.04 x86-64 is the
historically tested host configuration; other supported architectures or Linux
configurations must satisfy the pinned runtime and their reported qualification
notices. A physical workstation, server or VM is equally eligible. The installer
does not require the A100 product name, install drivers or implement CPU/offload
inference merely because host RAM is large.

Capability checks inspect free VRAM, runtime/driver compatibility, active device
allocations, available system RAM and storage. Model weight bytes are only a
lower bound. Unknown workload minima remain warnings and require bounded actual
loading and visual warmup; they do not silently become successful qualification
or an invented minimum. `--gpu-index`/`--gpu-uuid` select one eligible device.

[Guided installation](guided-install.md) covers one-command setup and
[resource preparation](resource-preparation.md) describes image/model/legal
acquisition. Public software preparation is explicit and separate from case
processing. `--build-core` uses the exported full commit and pinned Node/base
images to create a new immutable local image and separate unapproved manifest.
It does not overwrite the historical `111234c` candidate or reuse its acceptance.
No heavyweight image build has been verified in this revision.

For an authorized free device, explicit `install --qualification --apply` checks
hash-pinned resources and the image's actual bounded visual warmup in an offline
scratch core. It has no ingress, browser account setup or private case mounts.
It stops its owned scratch container before reporting success, returns no
application URL and leaves acceptance flags unchanged. A qualification receipt
is not a browser deployment, full case, accuracy result or clean installation.

The previous paid VM was deleted. Historical host observations and real partial
analysis receipts remain in [frozen inference](../frozen-inference.md) and the
canonical runtime manifest. They do not verify the new source/access stack or
provide a fresh spending allocation. No further paid machine is provisioned by
this installer.

## Sessions, network and HTTPS

The local account tool stores password hashes and revocable sessions in a
private SQLite database. The gateway verifies the core's trusted ownership
capability on the same connection used for forwarding. Its service key and
separate gateway token remain server-side; untrusted identity headers are
removed. The core must be configured with the matching
`FORTE_TRUSTED_GATEWAY_TOKEN_FILE`. It persists the authenticated principal at
admission and denies ownerless/cross-owner jobs, media, corrections and fresh
ranges. Legacy key-only mode remains for explicit administrative compatibility;
it is not the multi-user browser mode.

The browser uses one HTTPS origin for UI, sessions, uploads and evidence. Gateway
metadata supplies hosted/private mode, destination, readiness, limits, manual
retention and training disabled. Upload admission additionally requires explicit
operator activation and real core readiness/security capability. Keep uploads
disabled until the exact new release and access stack pass acceptance.

Use a supplied certificate/key or an internal-CA certificate trusted by reviewer
browsers. Public ACME issuance is not required for an internal/offline deployment.
Explicit loopback-only self-signed setup requires local certificate trust import
and does not establish public access. Keep application upstreams loopback and the
model port private. No service credentials belong in JavaScript, URLs or logs.

The private core uses OS/container-denied outbound networking. Offline flags
alone do not enforce that boundary. The bridge relays only the fixed application
port; it does not expose model port 8001. The session gateway permits only the
explicit handed-off loopback application endpoint. Missing resources or a failed
local model must preserve the selected processing destination; there is no
hosted inference fallback, external case storage or case-bearing telemetry.
A complete disconnected-install bundle remains unverified.

## Retention, upgrades and rollback

Normal stop/restart and repeated setup preserve originals, derivatives,
timelines, immutable correction revisions and account/secret state. Retention is
manual, including temporary application artifacts; backups have their own
administrator policy. Session expiry does not delete upstream cases. New cleanup
or migration behavior requires the core storage owner's contract and checks.

Prepare a release from a verified source snapshot, not a changing checkout.
Keep the previous image ID, manifest, configuration and compatible private
backups on customer-controlled storage. The integrator must:

1. Close admission using the agreed access/core mechanism and wait for active
   work. Record previous configuration and take an authorized private backup.
2. Stop only profile-owned services. An attach core cutover belongs to its runtime
   owner. Preserve cases, correction history and secrets.
3. Stage the new immutable image/resources and reviewed manifest. Verify hash,
   storage compatibility, sessions, ownership, readiness and a bounded workload
   before reopening uploads.
4. If verification fails, stop the new owned services and restore the previous
   compatible image/manifest/configuration. Use `up` after compatibility is
   established. Restore private data only through an explicit migration/rollback
   procedure; do not overwrite newer corrections with an old backup.

No general backward-storage compatibility or migration guarantee is claimed.
Selecting another manifest is not a data migration. Preserve both snapshots and
keep admission closed if compatibility is unresolved. Interrupted processing
remains an explicit failure rather than a clean negative.

## Activation checks still required

Bind each receipt to one exact source/image/model/corpus/configuration selection:

- Fresh host preparation/build or approved image import, actual bounded GPU
  qualification and repeatable startup on the selected compatible hardware.
- Real authorized development upload, asynchronous inference and human browser
  review of source interval/PTS, participant, evidence and official provision.
- Two-account denial for all existing job/media/correction routes and subsequent
  range requests through the deployed gateway/HTTPS stack; future routes require
  their own enforcement and tests.
- Real private case processing with IPv4/IPv6 outbound denied after preparation,
  persistence/restart, large MOV, queue-full and unavailable-model behavior.
- Hosted workflow from an authorized external browser using the actual hostname,
  certificate, upload path, playback and evidence routes.

Synthetic checks and local TLS do not establish these outcomes. Use isolated
failure simulation instead of stopping another owner's model. Use only footage
authorized for the selected environment; reserved/jury recordings are excluded.
Never inspect private frames through remote browser/image tools. Operational
smoke tests are not legal/detection-quality acceptance.

## Cached proxy test on macOS and Colima

The optional native proxy check mounts pytest's generated configuration into a
cached local container. An active Colima VM may not share macOS's default
`/private/var/folders/...` temporary directory. In that environment Docker can
return 125 with `bind source path does not exist` before the check starts. Use a
new test directory inside an existing Colima-shared `/Users/...` location:

```text
FORTE_TEST_DOCKER_PROXY=1 PYTHONPATH=src <python-environment>/bin/pytest -q \
  --basetemp <unique-shared-Users-directory> \
  tests/deployment/test_runtime.py::test_cached_nginx_starts_with_readonly_root_and_no_capabilities
```

At integrated Python source `53ebe49`, the normal suite passed 749 tests with one
optional Docker skip and four existing warnings. The same unmodified optional
check then passed separately in 1.05 seconds from a unique shared directory,
using the cached image without a network pull. These are 750 distinct checks
across separate runs, not one 750-test suite run. The first environment failure
remains recorded in the CORE verification handoff; no installer or test change
was required.
