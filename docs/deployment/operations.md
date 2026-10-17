# Deployment operations and verification record

This runbook covers the deployment lane based on
`7d9a1ca2ffda93f6c2dde4eaf8a5ca4c7d247eeb`, branch
`codex/deployment-private-cli`. See [observed-contract.md](observed-contract.md)
for inspected application interfaces and pending core changes. Commands and
configuration for the implementation live in this directory and
`deploy/portable/`.

The deployment worktree now includes Agent A's stable core checkpoint
`111234c885f0a23d323fe72a81450dfca5aa7e60`, following an isolated integration.
The [authoritative core handoff](../../contracts/frozen-runtime-manifest-v1.json)
identifies release `frozen-local-reasoning-20261018-1`, schema
`forte.integration/1` and the same local image ID as the dated inventory below.
It does **not** provide a published registry image, runtime-attach permission or
a deployment test window. The portable manifest example is a separate installer
input, deliberately unreleased; importing source metadata must not mark its
security/workload/installation acceptance flags approved.

The handoff's allowed product scope is **single-reviewer private only**. It
explicitly disallows multi-user private uploads and public browser uploads;
secure browser sessions and principal ownership are absent. Nothing in the
source handoff establishes a clean private installation, full browser end-to-end
completion or an externally reachable hosted service. Agent B has not activated
the shared runtime or performed additional GPU work.

The standalone administrator command is `forte-admin`, avoiding a collision with
the core application's `forte` command. From a checkout, use
`tools/forte-admin/forte-admin`; follow [README.md](README.md) to build/install
the real distributable. No public package name or registry availability is
assumed. Routine commands preserve persistent data:

```sh
forte-admin doctor --installation /srv/forte-installation
forte-admin status --installation /srv/forte-installation
forte-admin stop --installation /srv/forte-installation
forte-admin up --installation /srv/forte-installation
```

`up` must refuse missing release/runtime/session prerequisites; generation of
configuration is not evidence that the browser product is ready. `stop` is
profile-scoped and does not delete volumes. `logs` is a bounded operational
diagnostic, not permission to expose raw upstream model/case logs.

## Service ownership and permitted operations

Agent A owns existing VM/model/API/UI processes, the shared GPU, canonical
serving settings and final integration. The current session's recorded owner is
`visual-learning-integration`. Agent B prepares isolated deployment tooling and
read-only diagnostics. An attach profile owns only its explicitly created
access/relay components; stopping it must not stop the attached application,
model, GPU job, existing bridge, data or cache.

A full private profile is for a fresh, supported customer-controlled host and
owns the one core application container it creates, plus its access components.
Use a separate container/project name, configuration directory, private storage
and available loopback ports. Existing VM ports, namespaces and caches are not
available merely because another Git worktree was created.

Never run a second model to test an attach profile. Do not change drivers,
serving flags, ingress/DNS/firewalls or another profile's volumes; do not prune
Docker resources. A runtime handoff identifies an explicit service owner, test
window, bounded workload and rollback command before GPU tests or live cutover.

## Supported hardware and observed evidence

The initial candidate target is **Linux x86-64 Ubuntu 24.04, one NVIDIA A100
PCIe 80 GB, NVIDIA 570.195.03, Docker with working NVIDIA Container Toolkit**.
Existing host receipts report 28 vCPUs, approximately 120 GB RAM, a 100 GB root
disk and a 750 GB ephemeral data disk. CUDA compatibility is enabled by the
core's pinned vLLM image. Other GPUs, operating systems, driver versions and
lower memory hosts require their own actual multimodal workload validation.
An integer parameter count is not a hardware qualification.

Historical public/synthetic records in `.context/verify/gpu-setup.json` exercised
the original 8B profile. A's `docs/frozen-inference.md` reports the current 27B
candidate's 16-image synthetic checks, roughly 73 GiB occupancy, and a real
partial API execution. The historical sequential 8B/27B diagnostic sampled
73,307 MiB peak GPU memory. These records have different workloads and are not
minimum VRAM, final release certification or clean-installer verification.

At the direct inspection below, the prepared host already had public assets,
dependencies and an application image. No clean host installation, new model
download, additional GPU allocation or private inference was performed by this
deployment lane. Free storage must account for the exact pinned images and model
snapshot, detector/ReID, legal resources, upgrade overlap, retained originals,
derived artifacts and backups; the currently populated 69 GB cache is not a
complete storage sizing guarantee.

## Direct read-only operational receipt

At **2026-10-17T22:51:07Z**, Agent B used the existing project SSH wrapper with
the dedicated known-host file/key/control socket. The commands queried UTC time,
kernel, GPU counters, memory, filesystem capacity, container names/images/status,
listening socket addresses and process executable names. No process arguments,
secret values, model output, case files, private images or logs were printed.

- Host: Linux x86-64, kernel `6.14.0-37-generic`.
- GPU: NVIDIA A100 80 GB PCIe, driver `570.195.03`, total 81,920 MiB, used
  **0 MiB**, utilization 0% at that instant. This snapshot is not permission to
  consume the GPU; the owner's application was starting.
- RAM: 120,841 MiB total, 116,378 MiB available; no swap.
- Root filesystem: approximately 96 GB capacity, 49 GB used, 48 GB available.
- Container `forte26-frozen-production`, tag `forte26-frozen:verified`, was up
  approximately thirty-six seconds and had no published ports.
- Host listeners showed SSH on IPv4/IPv6 and loopback system DNS. No HTTP/HTTPS
  application listener was observed. No host ingress or outside-browser workflow
  was tested.

At **2026-10-17T22:52:08Z**, a second read-only query recorded:

- The same container was running, started
  `2026-10-17T22:50:30.930995461Z`, with Docker network mode `none`.
- Local image ID and local RepoDigest:
  `sha256:ee82962c4ee4d9026ef499a0854bcb485c94a18db97e07719800ca6dfe4276dd`;
  reported image size 9,275,095,203 bytes. Its local tag/digest is evidence of
  present bytes, not proof of a published, reproducible or accepted release.
- Read-only mount targets were `/models/public`, `/media`, `/legal`,
  `/service-api.key` and the pinned model's `/models/snapshots/<revision>`.
  `/jobs` was writable. Host source paths and secret contents were not copied.
- Existing `/ephemeral/forte26` occupied approximately 69 GB; the source checkout
  on the VM occupied approximately 4.9 MB.
- Standard-library HTTP requests inside the existing container found both
  `127.0.0.1:8000/health/live` and `/health/ready` unreachable at that instant.
  The container's cold start was in progress. No inference request or readiness
  assertion followed, and no restart was attempted.

A bounded read-only provider credit GET at approximately **22:52 UTC**, with
credentials supplied from the existing private header file, returned
**USD 25.2439411593**. Recorded session-start credit was USD 27.5503658903;
the observed reduction was about USD 2.3064 and provider settlement may lag.
The existing session cap was **USD 3**, inside the original **USD 30** total
authorization. Recorded compute and IP rates were USD 1.35/hour and
USD 0.00672043/hour. The existing deletion deadline was
**2026-10-17T23:04:26.333971Z**. This is dated evidence, not a current credit
balance or permission to rent another host. Agent A must enforce the earlier
spend/time limit, preserve private outputs and record actual resource deletion.
Stopping a provider VM does not prove billing stopped.

## Access and reviewer onboarding

The intended hosted path is one supplied HTTPS origin serving Agent A's static
web application and same-origin API/media routes. Private installation uses the
customer's configured origin. The browser must display that deployment label
and actual processing location before upload; no local failure switches to our
VM. Public dependency/model/legal preparation occurs separately from offline
case processing. Existing read-only legal snapshots retain their versions.

For browser activation, require Agent A's verified server-side session and
ownership integration. The observed UI currently asks for the shared upstream
service key and retains it in component memory. It does not yet satisfy the
ordinary-reviewer session contract; do not distribute that key as a substitute
for isolation. The explicit single-administrator gateway mode supports CLI
transport while browser/private multi-user upload remains gated. An entry-point
password alone does not make job/media ownership safe.

Once the browser gate is satisfied, the reviewer quick start is:

1. Open the actual HTTPS address provided by the administrator and authenticate.
   Confirm **Hosted demonstration** or **Private installation** and the named
   processing environment. The address must be externally tested before it is
   described as a public hosted URL.
2. Confirm service readiness and the actual retention policy. Upload one
   authorized MOV within 180 seconds and the body-size/time limits documented in
   [observed-contract.md](observed-contract.md). A prepared example must be
   authorized for that environment and clearly labeled as previously analyzed.
3. Wait for the asynchronous job, then inspect the execution completeness,
   assessment, original interval, participant proposal, source evidence and
   official provision. `partial`, `insufficient_evidence` and failures remain
   visible. Operational checks do not establish legal or detection accuracy.
4. Save only authorized scoped corrections; they preserve independent review
   scopes and currently do not automatically retrain or update model inference.

No externally verified HTTPS application URL was supplied at the stable handoff
or available at the inspection checkpoint. Missing hostname/certificate, browser
session, per-user ownership and final cutover are explicit integration dependencies.

## Offline and TLS operation

Keep model/API case processing in the verified egress-denied core boundary.
`HF_HUB_OFFLINE` and telemetry flags alone are not network denial. The observed
core can run `--network none`; access can relay only its application port from
an explicitly owned host component while model port 8001 remains private.
An attach deployment must confirm that boundary and target the existing
application, never silently start a replacement model.

Terminate HTTPS with an administrator-supplied certificate and private key, or
a certificate issued by the customer's internal CA and trusted by reviewer
browsers. Use the certificate's actual DNS name. Do not require public ACME,
vendor login or Internet connectivity for internal/offline processing. Restrict
upstream API/model ports to loopback/internal access and limit forwarding to the
intended application. Configure streaming uploads with whole-body/time bounds
compatible with the core; verify authenticated range headers and responses
through every access layer. Never put API keys in URLs, static assets or logs.

Online preparation followed by disconnected **analysis** is the target. A full
disconnected installation bundle requires an inventory of image archives,
weights, detector/ReID manifests, legal snapshot/cards, configuration and
licenses, with hashes verified on the destination; no complete bundle or clean
offline install has been verified here. Missing local assets must stop startup
with a specific prerequisite and preserve the selected processing destination.

## Persistence, retention, upgrade and rollback

Normal profile-scoped stop/start must preserve private cases, existing secrets,
configuration and corrections. Setup must not rotate secrets or clear storage
on repetition. No automatic core cleanup was observed: originals, evidence,
timelines, corrections and temporary artifacts persist until the administrator
performs explicit retention work. Backup retention is separately administered.
Do not promise that a gateway TTL deletes upstream case files. New retention
behavior requires Agent A's storage contract and tests.

Prepare upgrades from an immutable source snapshot and application digest, never
from Agent A's changing checkout. Retain the previous integration manifest,
configuration and image digest. The recommended sequence, after ownership
handoff, is:

1. Stop admission using the agreed core/access mechanism and wait for active
   jobs; do not invent a maintenance endpoint. Capture the exact previous
   manifest and take an administrator-controlled private backup of the job root,
   corrections and configuration on encrypted customer storage. Keep credentials
   and case data out of build contexts/support bundles.
2. Stop only the services owned by this profile. Do not use `docker compose down
   -v`, global cleanup or commands against Agent A's container. The integrator
   performs any separate core cutover for an attach installation.
3. Stage the new digest, pinned resources and manifest. Validate their hashes,
   trusted session/ownership contract, capacity and storage schema compatibility.
   Start the same profile and inspect liveness, readiness and a bounded authorized
   workload before reopening access.
4. If verification fails, stop the newly owned services, restore the previous
   manifest/image and compatible configuration, then start that profile again.
   Restore a storage backup only through an explicit migration/rollback procedure
   owned by Agent A. Never assume an older image can read newer job/correction
   formats or overwrite corrections created after the backup.

The profile-scoped stop/start commands for either a staged upgrade or a rollback
are the same commands above. Select the intended immutable manifest with the
documented setup preview, inspect the generated changes, and use the explicit
apply action only after the integrator certifies compatibility. Existing data
and secrets are preserved; the manifest selection alone is not a database or
correction migration.

No schema migration or backwards-compatibility guarantee was supplied at this
checkpoint. Rollback therefore needs Agent A to certify the selected data
formats; otherwise preserve both snapshots and keep admission closed. A stopped
or restarting analysis fails explicitly and is not relabeled as a clean result.

## Integration acceptance still required

Record these as separate evidence levels against one exact release, rather than
checking them off from configuration generation or a synthetic transport test:

- Immutable core/image/resource fingerprints and clean installer repeatability on
  the supported target; an already prepared VM is insufficient.
- Entrypoint startup, synthetic multimodal warmup, liveness and actual full
  model/tracking/legal readiness with effective model/corpus configuration.
- Authorized real development POST/poll/result and human browser review; source
  marker/participant/provision checks remain Agent A's semantic scope.
- Cross-user denial of jobs, originals, every evidence route and each subsequent
  range request, plus corrections and any future clip/export/preview routes.
- A private job with IPv4/IPv6 Internet access blocked after preparation; no
  external inference/storage or case-bearing telemetry.
- Repeated setup/restart preserving cases/secrets/corrections; large MOV,
  capacity-full and unavailable-model states through the real access layer.
- Hosted workflow from an authorized browser outside the VM's local network,
  real certificate/name, upload timing, authenticated playback and evidence.

Use synthetic configurations to simulate failures rather than stopping Agent
A's model. Do not open private recordings through automated remote browser or
image tools. Reserved and jury media are excluded from deployment rehearsals.
