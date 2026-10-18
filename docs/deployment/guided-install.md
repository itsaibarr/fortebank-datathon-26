# Guided local installation

An administrator runs `forte-admin` on the machine that will process recordings.
Reviewers open that machine's browser address. The machine can be a physical
workstation, server or VM: the installer evaluates its runtime, available GPU
memory and pinned workload rather than requiring a particular GPU product name.
The selected CUDA backend still requires a compatible NVIDIA GPU; ordinary
system RAM alone does not provide CPU execution or offloading support.

The administrator archive is built from this repository with
`python3 tools/forte-admin/build.py --output /outside-git/forte-admin-0.2.0.tar.gz --core-commit e55c0773ea74e2745ea33512d19bfaa38b32d7fb`.
Extract the complete archive, keep its directory structure, and invoke
`./tools/forte-admin/forte-admin`. There is no assumed public package or registry
image. The archive includes tooling, public metadata and a verified public
core-source snapshot. The core image, model weights and other large public assets
are prepared from those pinned inputs on the selected host.

## What one invocation does

`forte-admin install --mode private` is the administrator's one-command entry
point after host prerequisites are installed. Preview is the nonmutating default;
`--apply` explicitly permits local configuration, public preparation and startup.
The same invocation can be repeated after a missing prerequisite is resolved. It
checks host capabilities, preserves or generates the service secret, prepares
hash-pinned public assets, configures TLS, delegates the first administrator
account to the actual core account tool, renders the private profile, starts only
installation-owned services, and waits for real model and browser-access
readiness. It returns the configured browser address only when those checks pass.

This automation does not install host drivers, run `sudo` or change global Docker
configuration. Docker Engine with Compose v2 and NVIDIA Container Toolkit must
already be usable. Missing host prerequisites produce actionable blockers before
resource downloads or service startup. The tool never rents a GPU or changes a
shared model process to make a check pass.

Sufficient free GPU memory makes a compatible device a candidate for a bounded
load and visual warmup. Weight bytes provide only a lower bound: vision inputs,
KV cache, context and runtime overhead must also fit. Unmeasured RAM, disk and
workload limits remain notices rather than invented minimums. An actual warmup
establishes the tested workload on that host, not detection quality, legal
accuracy or an unmeasured latency guarantee. The historical A100 measurement is
an observation, not a hardware product-name requirement.

## Private browser installation

Prepare nonsecret installation configuration using the examples in
[administrator.md](administrator.md). It selects the pinned core integration
manifest and image, resource/data directories, application HTTPS origin, listener
and supplied certificate/key. A customer-controlled DNS name or IP and
certificate trust must be configured for reviewers on other computers.

Review an installation plan without changing the machine:

```sh
./tools/forte-admin/forte-admin install \
  --installation "$HOME/.local/share/forte-admin/installations/private" \
  --mode private --config /outside-git/private-install.json --preview
```

The fresh-host options can instead be supplied in one invocation:

```sh
./tools/forte-admin/forte-admin install \
  --installation "$HOME/.local/share/forte-admin/installations/private" \
  --mode private --build-core --online \
  --resource-source /outside-git/prepared-public-resources \
  --origin https://review.customer.example:8443 --bind-address 0.0.0.0 \
  --tls-cert /outside-git/tls/fullchain.pem --tls-key /outside-git/tls/privkey.pem \
  --administrator admin --readiness-timeout 360 --apply
```

The hostname, certificate and resource paths above are administrator inputs, not
supplied services. A successful browser installation additionally requires the
accepted release/security handoff below. Replace `--apply` with `--preview` to
inspect this selection without creating state, pulling images, building software
or creating an account.

`--online` permits pinned public resource and image acquisition; without it,
preparation stays offline and reports missing assets. `--resource-source` imports
approved public files from an existing resource layout and can be repeated for
additional directories. `--image-artifact` imports an approved `docker-save` image
instead of building it. The old verified image ID was local to the deleted VM;
it is not a downloadable registry release. A fresh host needs that approved image
artifact or explicit `--build-core` preparation.

`--build-core` uses the publisher-exported commit and per-file hashes, then runs
the actual frontend and Dockerfile builds in an isolated public source copy. It
records the newly built immutable image ID in a separate local installation
manifest. The old image's provenance and acceptance flags are preserved. The
default Node build image is pinned by repository digest; `--node-image` accepts an
explicit immutable digest override. `--core-source` can select another exported
source bundle that verifies against the same expected full core commit. Online
builds may acquire public npm/apt
dependencies. Offline builds deny networking and need already prepared
dependencies; a complete disconnected build bundle is not claimed. Pinned source
and lockfiles do not make apt repositories a hermetic OS snapshot.

The administrator password is prompted securely on the installation machine.
For unattended bootstrap, `--admin-password-file` accepts an owner-only private
file; passwords are not command-line arguments. Repeated installation preserves
existing enabled accounts. `--gpu-index` or `--gpu-uuid` can select a device;
otherwise capability checks select an eligible free GPU and retain that choice.
Public preparation never changes the selected model revision or corpus snapshot.

The browser installer requires the reviewed core local account tool and secure
session integration. It does not generate an imaginary account, place a service
key in browser code or treat an API-key gateway as reviewer ownership. Missing
session/ownership acceptance blocks public or multi-user browser installation.
Existing cases, corrections and credentials remain available for the next run.
The supplied installation candidate keeps its acceptance flags false. A locally
built image remains an unaccepted candidate until the actual operational,
session and ownership checks have been reviewed. Configuration and image-build
success do not override that gate.

For an explicitly loopback-only demonstration, `--tls-mode local-self-signed`
can generate and preserve an installation-local certificate with the correct
localhost/IP subject alternative name. The reviewer must import that certificate
into a local trust store before using the browser. Certificate verification stays
enabled; a self-signed loopback address does not establish public HTTPS. A supplied
internal-CA certificate is appropriate for an internal network. An offline
installation does not depend on public certificate issuance.

## Bounded local qualification

When an accepted full browser release is unavailable, explicit local
qualification can test the selected frozen runtime without enabling ingress:

```sh
./tools/forte-admin/forte-admin install \
  --installation "$HOME/.local/share/forte-admin/installations/qualification" \
  --mode private --build-core --online \
  --resource-source /outside-git/prepared-public-resources \
  --qualification --readiness-timeout 360 --preview
```

The default origin is loopback. Replace `--preview` with `--apply` to request the
bounded check on an authorized free GPU. `--qualification` requires the private
profile and loopback scope; it does not enable browser uploads. This path still
requires pinned image/resource hashes and actual visual warmup. It uses isolated
scratch storage, starts only the temporary owned core, and requires its owned
services to stop before reporting qualification complete. It does not bootstrap
browser users, expose HTTPS or launch another hosted service.

Success reports `qualification_complete: true`, `ready: false` and no
`application_url`. Release, ownership, offline-analysis and quality acceptance
remain unchanged. No GPU qualification was run as part of this revision's local
orchestration tests.

## Attaching our hosted access layer

`install --mode attach` configures access to a separately owned, explicitly
handed-off application on the same host. It never prepares weights or launches a
second model, API or worker. The designated runtime owner supplies the exact
loopback application endpoint and reviewed release/security handoff. It still
needs supplied TLS, real browser sessions, ownership enforcement and the intended
reviewer-facing address. Jury members use the browser; they do not run the CLI.
Uploads to that address are processed on the hosted VM.

The operator supplies `--attach-upstream http://127.0.0.1:<handed-off-port>`,
`--origin`, `--bind-address`, `--tls-cert` and `--tls-key`, plus the reviewed
`--manifest`. `--build-core` and `--qualification` are private-host operations;
the attach profile never assumes ownership of the handed-off core service.

A successful local HTTPS readiness probe does not establish outside-network
access. `externally_verified` remains false until an authorized external browser
actually completes the workflow. A missing hostname, VM or external environment
is a deployment prerequisite rather than permission to substitute an endpoint.

## Repeatability, privacy and failure behavior

Installation state belongs outside Git in an owner-only directory. The installer
rejects an unrelated nonempty directory and rejects changing an existing
profile's data/secret ownership through a repeat invocation. A directory lock
prevents concurrent installers from creating duplicate work. The private
`install-journal.json` records phase names, fixed states, an attempt number and a
configuration fingerprint. It excludes passwords, API keys, account names, case
identifiers and subprocess output. Repeating the command rechecks prerequisites
and resumes preparation rather than trusting a previous completion marker.

Normal stop preserves persistent volumes. Setup, resume and bounded readiness
failure preserve originals, derivatives, immutable corrections and secrets. The
current retention policy is manual deletion; temporary files and backups require
the application's/administered cleanup policy described in
[operations.md](operations.md). Installation itself never deletes cases or
relabels uploaded recordings as training data.

Private case processing runs with outbound networking denied after public asset
preparation. Resource acquisition is a separate phase, without private recording
mounts or case-bearing telemetry. A missing model, failed warmup, unavailable
service or incomplete result is reported accurately. The installer does not
retry against our VM or any remote inference provider. A verified completely
disconnected-install bundle has not been established merely by shipping the
administrator archive.

A readiness timeout returns exit code 2, records the blocked phase, preserves the
configured destination and provides no working application URL. Interruption
returns 130 with a resumable journal; inspect `status` and rerun the same command.
The browser installation does not stop an owned deployment automatically when
warmup is slow. Local qualification has its own mandatory cleanup boundary.

## Verification boundary

Focused tests use synthetic public assets, local temporary directories, actual
OpenSSL certificate generation and substituted owned lifecycle helpers. They
verify zero-mutation preview, first setup, credential/correction/certificate
preservation, interruption/resume, missing resources and account integration,
readiness timeout, attach isolation, no hosted failover, bounded qualification
and redacted failure reports. The real portable prerequisite checker and actual
pinned Git export are also exercised read-only. Source-build command tests use a
substitute runner; they do not perform a real image build.

The one-command flow is implemented and tested at that mechanics level. This
revision still requires a fresh authorized GPU-host qualification, reviewed
browser installation acceptance, and an external HTTPS reviewer workflow before
either the private-install or hosted offering can be called fully verified. The
checks above do not establish a clean customer installation, actual model
loading, case analysis, secure multi-user access or an external hosted URL.
