# Administrator installation guide

Run the administrator CLI on the machine that will process recordings. A physical
workstation, server or VM can host the same application. Reviewers then open its
HTTPS browser address; they do not install the CLI. A private installation keeps
processing and case storage on the customer-controlled host. Using our hosted
address processes uploads on our VM. A client command running on a laptop does
not change that destination.

`install` provides one resumable invocation for configuration, public preparation,
local account bootstrap, startup and readiness checks. Preview is the default;
`--apply` permits changes. The required host runtime and an accepted application
release must exist or be prepared through the explicit options below. The tool
does not install drivers, invoke `sudo`, rent a GPU or manufacture a successful
release/workload receipt. See [guided-install.md](guided-install.md) for phase and
failure behavior.

## Supported execution backend

The packaged model backend is NVIDIA CUDA on Linux x86_64. Ubuntu 24.04 was the
tested OS; other Linux configurations are candidates with an explicit unvalidated
notice. Docker Engine, Compose v2 and NVIDIA Container Toolkit must already work
for the administrator through a local Docker socket. Run the installer on the
GPU host rather than pointing its local probes at a remote Docker daemon.

There is no required GPU product name or VM provider. The host probe examines
available VRAM, the pinned model inventory, declared driver/compute requirements,
free storage and existing GPU allocations. It selects a free compatible device,
or accepts an explicit `--gpu-index`/`--gpu-uuid`. It does not stop another GPU
process to make room. This profile uses one GPU; combining several smaller GPUs,
CPU execution, Apple/AMD backends and CPU offloading are not implemented.

The selected frozen BF16 model has 18 weight shards totaling 55,563,006,776 bytes
(about 51.75 GiB). Those bytes are a lower bound, not a sufficient VRAM promise:
vision inputs, the 16,384-token context, KV cache and runtime overhead must also
fit. System RAM alone does not qualify this CUDA backend. Unknown RAM, disk,
driver or workload minima remain explicit notices. A bounded real model load and
visual warmup determine whether the actual workload runs on a candidate host;
they do not establish detection quality, legal accuracy or a latency guarantee.

## Obtain the administrator artifact and public resources

Use the complete `forte-admin-0.2.0.tar.gz` artifact from this project's release
handoff, extract it and preserve its directory structure. There is no assumed
public pip package. From its extracted root, invoke:

```sh
./tools/forte-admin/forte-admin --version
./tools/forte-admin/forte-admin install --help
```

The resource-inclusive administrator archive contains a small, hash-allowlisted
`public-resources/` bundle: the official legal snapshot and provenance, rule
cards, frozen configurations, model hash manifest, and approved ReID ONNX/export
manifest. The verified current selection has 21 files totaling 3,826,331 bytes.
It contains no 27B weight shards, recordings, credentials or core container image.
The publisher can create that variant from the repository with:

```sh
python3 tools/forte-admin/build.py \
  --with-public-resources --public-artifacts-root /approved/public-artifacts \
  --core-commit FULL_VERIFIED_CORE_COMMIT \
  --output /outside-git/forte-admin-0.2.0.tar.gz
```

The explicit public-artifact directory supplies `reid/osnet.onnx` and
`reid/manifest.json`; unrelated files are never scanned or copied. Without
`--with-public-resources`, the build produces the smaller tooling/metadata
archive and records `public_resources_included: false`. Do not describe that
variant as containing the legal/ReID resource bundle.
`--core-commit` independently includes public build inputs from the selected full
Git commit, under `core-source/`. Replace the placeholder with that verified
40-character commit. `RELEASE.json` records `core_source_included` and
`core_source_commit`; a tooling-only archive cannot build missing source.

With `install --online`, missing large public model files and the pinned detector
are downloaded individually and verified before use. Downloads are resumable.
Pinned public container images may also be prepared. All case processing remains
separate from this public acquisition stage. The installer preserves the frozen
model revision, tracker and legal snapshot; it does not choose alternatives.
See [resource-preparation.md](resource-preparation.md) for origins, hashes,
partial-file behavior and disconnected resource layout.

For disconnected preparation, supply `--resource-source /approved/public-bundle`
(repeatable) with paths matching the integration manifest. Supply an approved
`docker save` core artifact using `--image-artifact /approved/core-image.tar`;
its installed image ID must match the selected handoff. The proxy and any build
images must also be installed locally. A complete disconnected-install artifact
containing all weights, images and dependencies has not been delivered or tested.
Online preparation followed by offline case analysis is a separate capability.

## Select the application image or explicit source rebuild

Keep installation state, public resources, case storage and credentials outside
Git. The packaged `deploy/portable/core-current.candidate.json` preserves the
canonical core/model/corpus provenance and intentionally keeps its acceptance
flags false. It is an unapproved installation candidate, not a verified browser
release. Never turn flags on to bypass missing acceptance work.

An already-installed matching image or `--image-artifact` reproduces the exact
image identity in a compatible handoff. An alternative is explicit `--build-core`
public preparation. `--core-source` selects the extracted release directory
containing both `RELEASE.json` and `core-source/`; its default is the current
extracted administrator release. `--node-image` selects the pinned Node build
image. Source preparation uses only the approved source inputs
and public dependencies, without recordings, private credentials or GPU access.

A rebuilt image has its own image identity and receipt. A successful build is
**not a verified application release**: the new image still needs actual model
loading, offline inference, session/ownership and browser acceptance. The source
build must not inherit those approvals from an older image. Existing pinned
lockfiles/base inputs also do not make the Dockerfile's apt packages a completely
hermetic OS snapshot.

## One-command local qualification

The current candidate can be inspected and, on an authorized compatible host,
explicitly qualified without opening reviewer ingress:

```sh
./tools/forte-admin/forte-admin install \
  --installation "$HOME/.local/share/forte-admin/installations/qualification" \
  --mode private --online --build-core --qualification --preview
```

After reviewing the plan, replace `--preview` with `--apply` and retain the other
options. For an already-prepared image, omit `--build-core`; if required, provide
its matching `--image-artifact`. For offline operation, omit `--online` and supply
the missing resources/images locally. Keep the default loopback origin for this
qualification. It runs a bounded model load/visual warmup in owned scratch state,
then stops its temporary services. It does not expose HTTPS, admit reviewer
uploads, bootstrap browser users, or promote production acceptance flags.

Preview creates no configuration, downloads nothing, builds no image and starts
no service. An unresolved prerequisite or failed warmup remains a blocker, with
the selected processing location preserved. The tool never retries the analysis
on our VM or an external inference provider.

## Private reviewer browser installation

This path requires an accepted image/manifest plus verified browser sessions and
per-user job/media ownership. Supply a certificate/key trusted by the reviewers,
including an internal-CA certificate when public issuance is unsuitable. No ACME
account or external identity provider is required. Configure the customer-hosted
DNS/IP address and network access separately.

```sh
./tools/forte-admin/forte-admin install \
  --installation /srv/forte/install-1 --mode private \
  --manifest /approved-release/install-manifest.json \
  --resources-root /srv/forte/resources --online \
  --origin https://review.example.internal:8443 --https-port 8443 \
  --tls-cert /srv/forte/tls/fullchain.pem --tls-key /srv/forte/tls/privkey.pem \
  --administrator reviewer-admin --preview
```

Replace `--preview` with `--apply` for the reviewed installation. An interactive
password prompt creates the first local account through the real session store.
For unattended setup, use an owner-only `--admin-password-file`; do not put the
password or service key in command arguments. Repeated installation preserves
existing accounts and secrets. Incomplete release or browser acceptance prevents
activation even if configuration/resource generation succeeded.

Loopback binding is the default. To serve other computers, explicitly select
`--bind-address 0.0.0.0` as part of the designated integrator's ingress change;
the installer does not change DNS or firewall rules. For a local browser only,
`--tls-mode local-self-signed` creates a persistent loopback certificate. Import
it into the reviewer's trust store; it is not a public HTTPS certificate.

```sh
./tools/forte-admin/forte-admin doctor --installation /srv/forte/install-1 --json
./tools/forte-admin/forte-admin status --installation /srv/forte/install-1
./tools/forte-admin/forte-admin stop --installation /srv/forte/install-1
./tools/forte-admin/forte-admin up --installation /srv/forte/install-1
```

The installer returns a working application URL only after actual model and
browser-access readiness pass. A configured origin or local probe alone is not
an externally verified address. Public/multi-user activation remains blocked
until ownership is enforced for jobs and every original, derivative, frame,
clip, correction, export and subsequent range request.

## Attach hosted access to an existing runtime

Use `--mode attach --attach-upstream http://127.0.0.1:18000` only after the runtime
owner hands off that exact application-only endpoint. Attach owns its access
services; it does not prepare weights, load another model or manage the existing
core/API/worker/GPU. Supply the release/security handoff, trusted TLS and actual
reviewer-facing origin. The designated integrator controls live ingress and
cutover. Jury members then open the hosted browser address and install nothing.

No hosted address is currently claimed as activated. The historical experimental
VM was deleted; deployment generation does not recreate it or authorize another
paid machine. An outside-network browser must complete the hosted workflow before
external access is reported verified.

## Operations, privacy and verification limits

The model/API processing container has outbound networking denied after resource
preparation. Case originals and derivatives stay in the selected environment;
uploads are not training data. The CLI's endpoint-bound `connect`, `analyze` and
`job` commands use the same application API; see [api-client.md](api-client.md).
They do not create a separate local inference backend.

Repeated setup/install and normal stop/start preserve cases, corrections,
credentials and persistent volumes. Retention is manual: originals, derivatives,
temporary application files and backups require administrator/application cleanup
under the customer's policy. No automatic TTL is claimed. Use consistent image,
configuration and corpus snapshots with private backups for upgrade/rollback;
schema compatibility remains a core release requirement. `logs` returns redacted
operational status rather than raw case-bearing output. See
[operations.md](operations.md).

Current evidence includes focused synthetic installer/client/transport checks,
actual local certificate generation, and exact hash verification of the bundled
small public resources. Historical core GPU receipts apply to their original
image/host. They do not establish a clean installation or real inference for a
newly rebuilt image. The current installation work has not established a clean
customer GPU installation, end-to-end private upload/review, new-image offline
analysis, secure external multi-user workflow or externally reachable hosted URL.
