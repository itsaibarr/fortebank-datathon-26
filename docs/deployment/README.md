# Deployment and installation

Reviewers use the same browser application in two environments: our hosted HTTPS
demonstration or a customer-controlled private installation. Administrators use
`forte-admin` to install, prepare, diagnose, start and stop that application. The
core `forte` CLI and API retain their analysis responsibilities; there is no
second analysis backend or dashboard.

The authoritative current [execution and readiness report](execution-20261018.md)
records the sequential integration of deployment source `19afab3` with core
`ae9f819c3d7063e8bcf0e51855e5b4773c1961df`, the verified administrator archive,
commands, test results and remaining acceptance checks. Core includes principal
ownership, local browser sessions and the existing review UI. The user assigned
VM evaluation to the parallel evaluation thread; this deployment run leaves
those services unchanged. Clean-host GPU installation and external HTTPS
reviewer access remain unverified; no jury URL is claimed. Earlier
[source handoffs](current-source-handoff.md) and receipts describe their dated
deliveries and do not replace the current execution record.

## Install the administrator artifact

Python 3.12+ runs the dependency-free administrator tools. Build the actual local
artifact, including a pinned public application source snapshot:

```sh
python3 tools/forte-admin/build.py \
  --core-commit ae9f819c3d7063e8bcf0e51855e5b4773c1961df \
  --output /tmp/forte-admin-0.2.0.tar.gz
mkdir -p "$HOME/.local/lib/forte-admin-release"
tar -xzf /tmp/forte-admin-0.2.0.tar.gz -C "$HOME/.local/lib/forte-admin-release"
export PATH="$HOME/.local/lib/forte-admin-release/forte-admin-0.2.0/tools/forte-admin:$PATH"
forte-admin --version
forte-admin install --help
```

Check the printed SHA256 through your approved distribution channel. `RELEASE.json`
records the publisher commit, exported core commit and per-file hashes. The
archive contains no recordings, credentials, model shards or built application
image. Small pinned public resources may be included explicitly; see
[resource preparation](resource-preparation.md). There is no assumed public
package or image registry release.

[Guided installation](guided-install.md) explains the one-command `install`
workflow, pure preview, explicit `--build-core`, public preparation and bounded
local qualification. Hardware qualification evaluates a compatible free CUDA
GPU and the actual pinned workload on a physical host or VM. An A100 product name
is not required, and enough system RAM alone does not implement CPU inference.

Use [the administrator guide](administrator.md) for configuration and accounts,
[the reviewer guide](reviewer.md) for browser use,
[the observed contracts](observed-contract.md) for API/session interfaces, and
[operations](operations.md) for ownership, persistence and rollback.

Configuration generation, source export/build, synthetic transport, local TLS,
actual GPU qualification, clean installation and external access are separate
evidence levels. The package preserves the configured processing destination and
never sends a private job to a hosted service after local failure.
