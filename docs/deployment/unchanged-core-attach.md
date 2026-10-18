# Bounded checks against the unchanged evaluation API

Status: **source-only procedure, not an execution receipt**. The runtime owner
must first hand off the exact permitted operations after all three baseline
backups are restored and verified. The accepted target is the existing API on
container port 8000. This procedure neither upgrades that API nor enables
browser sessions or public ingress.

## Supervisor boundary

The reviewed source `scripts/container-entrypoint.sh` launches the resident
model and API, waits for either child with `wait -n`, and runs an EXIT cleanup
that kills both. The runtime owner independently reported this behavior in
`/app/container-entrypoint.sh`. Killing or restarting the API therefore stops
the resident model. Do not signal either child, replace source in the container,
change its environment or mounts, or run a core/private-profile lifecycle
command. Any different candidate process requires a separate concrete procedure
reviewed by the integrator and runtime owner.

## Required owner receipt

Record only nonsecret operational identities, without case names or contents:

- Full running container ID and immutable image ID; effective source, contract,
  model, corpus and configuration identities supplied by the owner.
- Unchanged network-none runtime, application port 8000 and private model port
  8001; active-job count zero and completion of the three verified local backups.
- Available approved host loopback port, proposed `127.0.0.1:18011`; separately
  approved local tunnel port if a tunnel is needed. Never reclaim an occupied
  port or existing bridge.
- Actual remaining time, resource allowance and session cap. The useful-work
  stop remains 2026-10-18 01:08 UTC; deletion remains 01:28:30 UTC. The expired
  00:45 public-build window supplies no permission for these operations.
- An explicitly approved method to use the existing API-key file in memory on
  the VM, or an owner-prepared separate B credential file. Never print the key,
  put it in argv, transfer it implicitly or modify the owner's credentials.

Before launch, recheck only the approved inventory fields. Do not dump Docker
environment, inspect private mounts, read model/case logs, or enumerate case
directories. Compare the exact container/image identities and abort on drift.
Use the canonical existing SSH master and strict host-key verification, with no
direct-SSH fallback or changes to the master, firewall or timer.

## Bridge-only launch

Use the already verified public release under B's separate staging directory.
Verify the release inventory and the bridge source hash before launch. Do not
extract another archive or rebuild the application for this check.

The sole service command has this shape; placeholders must come from the owner
handoff and B's private launch receipt:

```text
python3 <verified-release>/deploy/portable/bridge.py \
  --container <full-verified-container-ID> --port <approved-loopback-port> \
  --token <fresh-32-hex-process-ownership-marker> \
  --state <B-owned-private-directory>/bridge.json
```

The marker identifies B's process; it is not an application credential. Keep the
state and launch receipt private. Record the exact source SHA, argv, executable,
PID, process start time, full container ID, port and state-file identity. Verify
the bridge is listening only on the agreed loopback address before proceeding.

This bridge starts a short-lived `docker exec` relay per connection. Its literal
destination is container `127.0.0.1:8000`; it does not expose 8001, attach Docker
networking or manage the entrypoint's API/model processes. Avoid the historical
`scripts/offline_api_bridge.py` for this plan: it is fixed to port 18000 and lacks
the portable bridge's ownership state. Do not invoke `forte up`, qualification,
session/ingress startup or private core shutdown to obtain a bridge.

## Bounded health and client checks

Complete connections serially with short timeouts and `Connection: close`:

1. Request `/health/live` and `/health/ready` through the new loopback bridge.
   Record HTTP status and the bounded status/error code only. Readiness checks
   resident-model availability; they do not generate a qualification workload or
   establish successful case inference.
2. Request the owner-confirmed `/api/v2/openapi.json` without credentials and
   expect 401. This route contains public API metadata, not case data.
3. If the owner grants authenticated client use, load the released stdlib
   `APIClient` with the explicit loopback origin and approved key-file path.
   Its nonmutating constructor and GET transport may request that same API
   contract; compare canonical JSON hashes against the source-matched contract
   using the same serialization, separately from its original file hash.
   Log only the endpoint, status and comparison result. Do not print response
   bodies or credentials. If the existing credential has a different endpoint
   binding, stop and report that prerequisite; never silently rebind it.

`forte connect` writes a credential-origin sidecar. It must not be run against
the owner's original credential file. A saved CLI connection profile is optional
for these checks; library-only construction does not create one. Do not submit
an upload, poll a baseline job, read media/corrections/results, create a synthetic
job or request model generation under this health/client-only scope.

If an SSH tunnel is explicitly included in the handoff, create only its exact
approved loopback forward over the canonical master. Record whether creation
succeeded and the exact forward specification. A failed creation grants no
ownership of a pre-existing forward. No browser or screenshot check of private
case data is part of this procedure.

## Rollback and receipts

Finish all requests and close any B-created forward before stopping the bridge.
Cancel only the exact forward whose successful creation B recorded; never close
or restart the shared SSH master. Before SIGTERM, compare the bridge PID,
process start time, executable, exact argv/ownership marker, state file, target
container ID and port with the private launch receipt. Any mismatch means no
signal and an explicit unresolved-cleanup report. Never use name-pattern kills,
process-group kills or Docker stop/restart/rm on the core.

Confirm the owned bridge exited, its listener closed and no B-owned relay child
remains. Both bridge implementations use daemon handler threads, so state-file
disappearance alone does not prove relay cleanup. Do not stop the bridge while
requests remain active. If cleanup is ambiguous, report it without touching
peer processes. Finally recheck the owner's approved core identities and running
state without reading private logs or generating inference.

Record bridge/client transport results separately from inference, deployment and
external browser acceptance. Keep release, model-workload, offline-analysis,
browser-session and ownership acceptance flags false. Preserve persistent data,
all owner services, the shared timer and the original fixed archive. The current
key-only runtime cannot establish multi-user isolation or hosted jury access.
