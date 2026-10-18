# Deployment and installation

Reviewers use the same browser application in two environments: our hosted HTTPS
demonstration or a customer-controlled private installation. Administrators use
`forte-admin` to install, prepare, diagnose, start and stop that application. The
core `forte` CLI and API retain their analysis responsibilities; there is no
second analysis backend or dashboard.

The deployment branch `codex/guided-private-install` consumes Agent A's stable
source checkpoint `e55c0773ea74e2745ea33512d19bfaa38b32d7fb`, including principal
ownership, local browser sessions and session-aware UI. These mechanisms are
implemented in source. A newly built GPU image, clean-host installation and
external HTTPS reviewer workflow remain unverified. No live VM or jury URL is
available. [The handoff](handoff.md) records the exact remaining activation work.

## Install the administrator artifact

Python 3.12+ runs the dependency-free administrator tools. Build the actual local
artifact, including a pinned public application source snapshot:

```sh
python3 tools/forte-admin/build.py \
  --core-commit e55c0773ea74e2745ea33512d19bfaa38b32d7fb \
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
