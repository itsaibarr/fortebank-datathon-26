# Portable deployment profiles

These profiles package the existing Forte application. The canonical API, model,
tracking and official local legal corpus remain Agent A's implementation. Start
with [the administrator guide](../../docs/deployment/administrator.md).

## Supported runtime and ownership

The packaged inference backend is Linux x86_64, local Docker Engine with Compose
v2, and compatible NVIDIA CUDA hardware/container runtime. A physical workstation,
server or VM is eligible. No particular GPU product name is required. Diagnostics
check backend support, free memory, driver/container compatibility and existing
allocations. Weight bytes are a lower bound; actual multimodal warmup is needed
for host qualification. CPU, Apple/AMD and offloading backends are not implemented.
Unknown resource minimums remain explicit notices rather than fabricated limits.

`private` owns one offline core container (API, worker, model and exported UI),
one loopback application bridge, one host session gateway and one TLS ingress.
The canonical `network_mode: none` and `ipc: host` remain unchanged. Only the
selected GPU UUID is exposed. The bridge streams to container application port
8000; model port 8001 is never exposed. Public resources are mounted read-only;
case storage is separate and persistent.

`attach` owns only its session gateway and ingress. It uses the runtime owner's
existing loopback application bridge, service key and matching trusted-gateway
token. It never starts a model or takes ownership of upstream processes/storage.
Activate it only after the shared runtime owner supplies a coordinated window.

The default origin is `https://localhost:8443`, bound to loopback. Session/bridge
ports are separate loopback listeners. Nonlocal access needs an explicit origin,
bind scope and trusted supplied certificate. Ports must be unprivileged; standard
public port 443 needs coordinated outer ingress. Packaging never changes DNS,
firewalls, drivers or cloud allocations.

## Preparation, access and acceptance

`forte-admin install` combines bootstrap and startup after host prerequisites.
Preview is nonmutating. Public resource acquisition and source-image building
require explicit selection; no model is downloaded during case processing.
The archive can contain a verified Git source snapshot and small hash-pinned
public resources. Large weights are prepared separately and verified by hash.
The existing Dockerfile and locks are used; apt resolution is not a hermetic OS
snapshot. A local image ID needs its saved artifact or a new explicit source build.

The historical candidate records core `111234c` and a deleted VM's local image.
New session-aware source is a separate checkpoint. A source build derives a new
local image/candidate while keeping all five acceptance flags false. Production
`up` requires reviewed release/workload/offline/session/ownership receipts; a
validator or successful build cannot approve itself. `install --qualification`
provides a separate bounded first load/visual warmup with scratch case storage,
no session/ingress or public listener, no acceptance promotion and owned shutdown.

Browser reviewers use Agent A's same-origin session UI. Service keys and gateway
tokens remain server-side; the gateway propagates an authenticated principal and
checks the core security capability. The core enforces job/media/correction/range
ownership. The optional single-admin Basic gateway is API transport only, with
one trust domain and no multi-user claim. It does not implement browser sessions.
TLS may use a supplied public certificate or internal CA. Explicit local
self-signed setup gives a trust notice and never changes system trust.

## Lifecycle, privacy and evidence

Repeated setup preserves secrets, accounts, cases and corrections. Repeated `up`
verifies installation labels, immutable image, GPU UUID, network and mounts,
reuses an owned running model and resumes access helpers. It refuses foreign
identities. `stop` inspects exact owned containers and private helper identities;
it never prunes Docker, removes volumes or signals an unverified process.
For a release/configuration change, stop this installation first, back it up,
then install the compatible pinned release. Core schema migration compatibility
remains Agent A's decision.

Status probes fixed loopback health paths and the actual TLS listener using the
configured hostname, metadata and session endpoint. It distinguishes loading,
core readiness and browser access, and always leaves `externally_verified` false.
A successful local listener check does not establish an outside-browser workflow.
Diagnostics omit credentials, raw logs and case content. No hosted fallback exists.
Originals, derivatives, corrections, temporary files, account state and backups
persist under manual retention until administrator/application cleanup. Uploads
are never training data in this phase. See [operations](../../docs/deployment/operations.md).

Synthetic transport, repeatability, source/export, resource/hash, ownership and
failure-path tests pass. Cached local Nginx startup/TLS rejection is separately
tested. See [verification.json](../../docs/deployment/verification.json) for exact
receipts. No clean GPU installation, new session-aware heavyweight image, real
packaged offline job or external HTTPS jury workflow is claimed. There is no
currently activated hosted URL.
