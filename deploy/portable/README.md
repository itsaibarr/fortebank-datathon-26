# Portable deployment profiles

This directory packages the existing application. It does not implement an analysis backend, select a model, approve legal interpretations or claim detection accuracy. Use the administrator CLI described in `docs/deployment/administrator.md`; this module is its runtime implementation.

The initial runtime target is Ubuntu 24.04 x86_64 with Docker Engine, Compose v2 and the NVIDIA Container Toolkit. Private startup accepts exactly one otherwise idle NVIDIA A100 80 GB, the reviewed driver family and the RAM/free-disk requirements from the release manifest. Other hardware is unsupported until a separate workload receipt exists. Rendering and synthetic transport tests also work on macOS; this is not clean GPU installation verification.

## Ownership

`attach` starts and stops only this installation's `ingress` Compose service. It connects to the existing application bridge at `http://127.0.0.1:18000`. It never starts a model, stops the upstream application, mounts its writable case directory, changes its flags or owns its existing bridge. An approved runtime attach window is required before activating this profile on the shared VM. A separate worktree does not provide a runtime window.

`private` owns one `core` Compose service containing Agent A's API, worker, local model and exported UI; one ingress service; and one host stdlib bridge daemon. The core uses `network_mode: none` and the canonical tested `ipc: host`; this is for the selected dedicated host, not an unreviewed shared customer runtime. The daemon connects with bounded `docker exec -i` streams to **application port 8000 only**, from host loopback port 18001 by default. Model port 8001 is never exposed. The bridge limits concurrent connections to 16, preserves binary bytes and TCP half-closes, and never records headers or payloads. It requires host Docker access; install it as a controlled administrator service, not as a browser feature.

Ingress uses host networking to reach the loopback application bridge and listens only on `127.0.0.1:8443` by default. Publishing on all interfaces requires explicit `bind_address: "0.0.0.0"`, an approved access window and an origin matching the supplied certificate. No DNS, firewall, certificate issuance, driver installation or cloud allocation is performed. The fixed HTTPS port must be unprivileged (1024–65535); standard public port 443 needs a separately coordinated host ingress configuration.

## Inputs and release gate

`installation.json` is installation configuration, distinct from API-client endpoint profiles. Supply absolute paths for `resources_root`, `data_root`, `secrets_root`, `integration_manifest`, `tls_cert` and `tls_key`. `origin` must be the actual HTTPS origin with the configured port. Do not place these directories inside Git or a Docker build context.

Both image identifiers must be immutable: `repository@sha256:<64 hex>` or a local `sha256:<64 hex>` image ID. The runtime uses locally prepared images with `--pull never`. A local image ID is portable only with its explicitly supplied `docker save` artifact, whose transfer checksum is verified before `docker load`. The deployment module does not build from another agent's changing checkout, pull a mutable tag or download weights during a case.

The local integration manifest uses schema version 1:

- `core`: stable `commit`, immutable `image`, canonical `contract_sha256`.
- `model`: `identity`, exact `revision`, explicit `profile`, `frozen: true`.
- `corpus`: official local corpus `version`; additional provenance fields are preserved.
- `runtime.environment`: nonsecret `FORTE_*` settings from the core integrator. The image retains its canonical entrypoint and serving flags. Offline settings, the private root and key path are set by packaging. Remote model URLs are rejected.
- `runtime.mounts`: optional resource-relative `source` and unique `/models` or `/legal` `target`. Both are read-only. `resources_root` is also always mounted read-only as `/resources`; put the reviewed effective configuration at `/resources/config/frozen-inference.json`.
- `runtime.requirements`: reviewed `min_host_ram_gib`, `min_free_disk_gib` and exact tested NVIDIA `driver_major`. Missing values block private startup. They describe the actual model/image/multimodal workload, not a guess from parameter count.
- `assets`: `{ "path": "resource-relative-file", "sha256": "..." }` entries covering the actual model, detector, ReID, legal and configuration inventory. Symlink escape or a changed hash blocks startup. This inventory is a release integrator responsibility; one synthetic asset is never a production inventory.
- `verification`: `release`, `model_workload`, `offline_analysis`, `browser_session`, `ownership`, plus resource-relative local `receipt`. Missing release, workload, offline receipt or manifest hash blocks `up`.

Pin the manifest's byte hash as `manifest_sha256` in installation configuration. Booleans are reviewed handoff declarations, not facts manufactured by the schema validator. Inspect the underlying receipts. Readiness means a usable resident model; it does not establish quality, browser authentication, legal accuracy or complete disconnected-install support.

The authoritative core handoff `contracts/frozen-runtime-manifest-v1.json` has its own schema (`forte.integration/1`). Use the packaged standalone `import_handoff.py` script to create a candidate local manifest. The adapter preserves missing gates; importing a handoff does not approve it. The initial stable `111234c` handoff records a pending cold start, no per-principal ownership and no secure browser sessions. Accordingly, public browser activation remains blocked.

## Access and secrets

`access_mode: "browser-session"` is the default. Startup requires verified same-origin browser sessions **and** job/media ownership. Without that declaration, rendering returns 503 for `/api/` and `up` refuses activation. The deployment lane does not implement application authorization or turn a shared API key into user isolation. Agent A must check ownership for every job, original, evidence image, clip, correction, range request and export before multi-user uploads can be enabled.

An explicit `gateway-single-admin` mode accepts one administrator password file (`htpasswd_file`) and injects the service key server-side from `secrets_root/core-api.key`. It is for authenticated API-client transport only. The current UI's key-entry design is not integrated with this mode; it must not be advertised as working reviewer browser access. Multiple password entries do not create case isolation. `multi_user_uploads: true` is rejected in this mode.

Supply a generated URL-safe service key of 32–256 characters, separately from provider or SSH credentials. The installer preserves it across setup. Nginx receives a mode-0600 server-only key include in the installer directory. It never delivers this include to the browser. Caller-supplied service keys, Basic credentials and spoofable principal/user headers are removed before proxying in single-administrator mode. Session mode preserves application cookies and Authorization while stripping untrusted principal headers and service keys.

Ingress uses supplied matching certificate/key files, including internal-CA deployments. Certificate trust, hostname, expiry and external routing must be verified by the administrator; parsing the pair locally is insufficient. No mandatory vendor login, external AI, case telemetry or external case storage is introduced. Online public resource preparation is separate from offline analysis. No automatic hosted fallback exists.

Ingress has request/access logging disabled, buffering disabled for uploads and responses, a 256 MiB whole-body limit and forwarding of Range/If-Range headers. Its workers retain the container's root identity to read mode-0600 bind secrets; **all Linux capabilities are dropped**, the root filesystem is read-only, temporary directories are bounded tmpfs and no application case volume is mounted. The proxy has host-network access; the inference service remains network-none. Nginx runs only the fixed proxy configuration, not case processing.

## Lifecycle and persistence

The callable interface is:

```python
from pathlib import Path
from deploy.portable.runtime import render, validate, prerequisites, lifecycle

errors = validate(config)  # Pure structure validation, no resource reads.
missing = prerequisites(config)  # Read-only hashes, secrets, TLS and release checks.
files = render(config, Path(target))  # Writes only the installer directory.
report = lifecycle(config, Path(target), "up")
report = lifecycle(config, Path(target), "status")
report = lifecycle(config, Path(target), "stop")
```

`host_prerequisites` adds bounded OS/Docker/GPU/RAM/disk/listener checks. `compose_command` produces explicit project/file-scoped arguments and gates `up` on release prerequisites. `lifecycle` also gates runtime host checks, verifies offline core-container labels and starts the owned private bridge. It returns sanitized facts; external process output, model logs and case content are withheld. `logs` explains this policy instead of dumping case-bearing logs.

`status` reads fixed loopback core health routes, disables environment HTTP proxies and redirects, and bounds response sizes. It separately performs a real TLS handshake to the installer listener on loopback, verifies the configured origin hostname against the supplied certificate, and checks a ready response (session mode) or the Basic-auth challenge (single-administrator mode). It reports `live`, `core_ready`, `access_ready`, combined `ready`, and separately declared browser verification. HTTPS unavailability makes `ok` false even if the core is healthy. The unauthenticated challenge does not prove authenticated transport. This is a local listener check; `externally_verified` remains false. Startup reports pending warmup or HTTPS failure honestly. No readiness timeout restarts the shared model. Repeated `up` refuses occupied ports/already running projects without replacing them; use `status`, then a coordinated `stop` and `up` for an intended release change.

`stop` verifies rendered profile identity, stops only its Compose services and signals only its verified bridge PID/token/container identity on Linux. It never uses `down -v`, deletes cases, clears caches or changes upstream services. Repeated setup/render preserves case files, corrections and external secrets. A separate installer directory is required for another project or profile.

Cases and corrections remain in the externally mounted `data_root`. Core model logs and temporary artifacts may also remain there. Retention is **manual** until Agent A supplies application cleanup: originals, derivatives, corrections, temporary artifacts and backups have no automatic deletion deadline. No uploaded footage is added to training. Normal stop preserves everything. Administrators must execute the event/customer-approved cleanup separately and account for backups.

For upgrade or rollback, stop the owned installation, retain a protected copy of `installation.json`, its pinned integration manifest and immutable images, then render/start the selected compatible release. Back up cases with the application stopped. Do not roll back across an incompatible record/schema migration until Agent A supplies migration/compatibility instructions. A partially failed `up` can leave the newly owned core running; `status` then `stop` is the bounded rollback. No broad resource cleanup is performed.

## Verification performed

Synthetic tests cover fail-closed auth/release gates, attach-only ownership, immutable image/config checks, changed resource hashes, repeated render/persistence, refusal to signal a foreign PID, secret handling and a 32 MiB binary stream with an HTTP 206 response. Optional cached-Docker testing validates generated Nginx syntax and real startup with a read-only root, all capabilities removed, supplied synthetic TLS and unauthenticated HTTPS rejection.

```bash
python3 -m pytest tests/deployment/test_runtime.py -q
FORTE_TEST_DOCKER_PROXY=1 python3 -m pytest tests/deployment/test_runtime.py -q \
  --basetemp /Users/itsaibarr/.cache/forte-runtime-synthetic
```

The second command was run on local Colima using pre-existing `nginx@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de`; 22 tests passed. It does not pull images, start a model, open a public port or use case footage. The explicit base directory must be shared with the local Docker daemon. Do not run the Docker test against the shared VM's Docker context.

Still unverified: clean customer GPU installation; cold start of the complete private profile; real retained case/restart; real large MOV through this ingress; authenticated source ranges/evidence; offline real inference of the packaged release; per-user isolation; jury browser workflow; and external HTTPS. Those require stable core resources, approved service ownership and an actual test window. Synthetic validation does not complete these gates.
