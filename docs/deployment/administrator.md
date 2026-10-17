# Administrator installation guide

Initially the runtime targets **Ubuntu 24.04 x86_64 with one NVIDIA A100 80GB,
Docker Engine and Compose v2**. This is the core's observed hardware target;
a clean customer-host installation has not been executed. Full workload RAM,
disk reserve and packaged IPC requirements must be supplied in the accepted
release manifest. `doctor` rejects unsupported hosts or missing requirements.
Do not infer suitability from the model's parameter count.

## Prepare a pinned release

Keep installation state outside Git. Use the packaged
`deploy/portable/core-current.candidate.json` as an **unapproved candidate**.
It preserves provenance from Agent A's canonical handoff, frozen model identity,
contract hash and immutable local image ID. It intentionally contains no invented
resource inventory or successful deployment/security approvals.

For a later canonical handoff, create a new candidate:

```sh
python3 deploy/portable/import_handoff.py \
  --source /approved-release/frozen-runtime-manifest-v1.json \
  --core-commit FULL_VERIFIED_CORE_COMMIT \
  --inventory /approved-release/public-resource-inventory.json \
  --output /approved-release/install-manifest-v2.json
```

The inventory is a reviewed list of relative `path` and `sha256` pairs. Populate
it from the core release's public model/tracking/legal/configuration manifests,
not by treating arbitrary local bytes as approved. Match the exact effective
configuration and its mounted paths. Record the source image, core commit,
workload requirements and local acceptance receipt. Do not turn verification
flags on to bypass missing work. Full schema and profile mechanics are in
[`deploy/portable/README.md`](../../deploy/portable/README.md).

Resources belong under the selected `resources_root`, for example:

```text
resources/
  models/<pinned-model-revision>/  # complete model + processor + hash manifest
  models/yolox_s.onnx
  models/reid/                   # accepted ONNX and manifest
  legal/2026-10-17/              # official-source corpus and provenance
  legal/rule-cards.json
  config/frozen-inference.json   # exact accepted effective paths/configuration
  verification/acceptance.json
```

Online preparation downloads only public dependencies/resources. Cases must not
be present in that preparation stage. `prepare --images` pulls explicit registry
digests without starting services; Docker resumes existing layers. Immutable
local image IDs must instead be installed from the approved `docker save`
artifact using `docker load`, then inspected against the expected ID. The tool
does not independently select/download another model, quantization or tracker.
Missing resources are reported by hash verification. A complete disconnected
installation bundle is **not currently supplied**; prepared offline analysis is
a distinct goal.

## Full private installation

Provide your own trusted TLS certificate and private key, including an internal
CA certificate when public issuance is unsuitable. Install that CA in reviewer
trust stores. No ACME account, vendor login or certificate issuance is required.
Choose a proxy image by immutable repository digest, obtained through your
approved registry process. Examples deliberately do not invent a tested digest.

```sh
forte-admin setup --mode private --installation /srv/forte/install-1 \
  --manifest /approved-release/install-manifest-v2.json \
  --resources-root /srv/forte/resources \
  --origin https://review.example.internal:8443 --https-port 8443 \
  --proxy-image 'nginx@sha256:REPLACE_WITH_VERIFIED_DIGEST' \
  --tls-cert /srv/forte/tls/fullchain.pem --tls-key /srv/forte/tls/privkey.pem \
  --preview
```

Preview is also the default. Repeat the reviewed command with `--apply` to write
owner-only configuration and a new private service key if one does not already
exist. Invalid/incomplete configuration can be saved for preparation, but cannot
start services. Setup never creates an imaginary core administrator account.
The secure first-administrator bootstrap must be supplied by the core's session
layer before enabling browser access.

```sh
forte-admin doctor --installation /srv/forte/install-1 --json
forte-admin prepare --installation /srv/forte/install-1 --images
forte-admin up --installation /srv/forte/install-1
forte-admin status --installation /srv/forte/install-1
forte-admin stop --installation /srv/forte/install-1
```

Loopback binding is the default. Set `--bind-address 0.0.0.0` only in a reviewed
installation change with the designated integrator's ingress authorization.
This installer does not change DNS/firewall rules. It returns the configured
origin and actual live/ready state; it does not call a configured URL reachable
or externally verified merely because it exists in configuration.

The full profile owns its Compose project, offline model/API/UI container,
app-port-only host bridge and TLS ingress. The core has no network interface.
The bridge cannot target the model port. Persistent bind mounts keep recordings,
results and corrections across normal stop/start. Secrets are not included in
the browser bundle. No raw case logs are exported by `logs`.

## Attach to an existing authorized installation

`--mode attach --attach-upstream http://127.0.0.1:18000` owns **only TLS ingress**.
It assumes the designated core owner already runs the application-only bridge.
It never starts, restarts, stops or changes the existing model/API/UI container,
bridge, database or GPU allocation. Use another free HTTPS port/project name for
a rehearsal. Current VM permission is read-only; this profile has not been
activated there. Do not treat generating an attach profile as a cutover grant.

## Administrative API access

Connection profiles are separate from installation configuration and bind a
private key file to one endpoint. Never place a key in a URL or command argument.
A remote endpoint means hosted processing, even when the command runs locally.

```sh
forte-admin connect --endpoint https://YOUR_AUTHORIZED_ORIGIN:8443 \
  --key-file /private/credentials/service.key --profile /private/connections/demo.json
forte-admin analyze --profile /private/connections/demo.json \
  --file /authorized/development/synthetic-or-allowlisted.mov --submit --wait \
  --output /private/results/new-result.json
```

Use the direct core endpoint only in its authorized private trust boundary. The
optional `gateway-single-admin` mode is an administrative transport with supplied
htpasswd and server-side key injection; it does not make the current UI a
session-based product or establish user isolation. Browser-session mode remains
gated until core ownership and secure sessions pass verification.

Destination is printed before submission. Uploads stream through the real
versioned API; no mock, redirect, retry or hosted failover is used. An unfamiliar
assessment remains unchanged in a saved result. The terminal prints only safe job
metadata. Result output must be a new file outside Git. Failed jobs exit 5;
configuration failures exit 2, transport/protocol failures 3 and timeouts 4.
`setup` exits 0 when it successfully writes/previews configuration, even if the
reported prerequisites still block `up`; `doctor` reports those blockers with 2.

## Retention, upgrades and support

Current core retention is manual: originals, derived evidence, corrections,
temporary application files and backups persist until explicitly removed by the
administrator under the event/customer policy. No automatic TTL is claimed.
Normal shutdown preserves all volumes. No upload is used for training.

Repeated setup preserves existing secrets/data/corrections. Changing mode or
storage roots requires a new installation and an explicit migration. Upgrade and
rollback must use consistent immutable image/config/corpus snapshots plus a
private backup; compatibility or migrations remain the core owner's decision.
See [operations.md](operations.md). `logs` deliberately supplies a redacted status
explanation rather than model prompts or case-bearing raw service output.

## Rebuild the existing application from source

`deploy/portable/build_core.py` exports only tracked build inputs from the chosen
full commit using `git archive`. It never builds Agent A's changing checkout.
Provide an approved immutable Node build image already installed locally:

```sh
python3 deploy/portable/build_core.py --repository /approved/source/forte26 \
  --core-commit 111234c885f0a23d323fe72a81450dfca5aa7e60 \
  --node-image 'node@sha256:YOUR_VERIFIED_BUILD_IMAGE_DIGEST' \
  --tag forte26-install-1:release-1 \
  --output /approved-release/build-receipt.json --preview
```

Remove `--preview` only during the online **public preparation** stage. This
builds the existing locked Next.js interface and existing core Dockerfile in an
isolated exported snapshot, then records the image ID and source hash. It does
not mount cases, keys or private outputs, start a model, publish an image or
change live services. The real heavyweight build has not been run by Agent B.
Core lockfiles and the base image are pinned; the existing Dockerfile's apt
packages are not a fully hermetic OS snapshot. Deploy the resulting immutable
image ID and revalidate its workload; do not claim bit-identical rebuilds.
