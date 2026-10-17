# Deployment and installation

Agent B's deployment tooling packages the existing application. The CLI is
`forte-admin`; the model/application CLI remains `forte`. Reviewers use the web
application. No second analysis backend or results dashboard is introduced.

The release candidate consumes core commit
`111234c885f0a23d323fe72a81450dfca5aa7e60`. Its canonical handoff is
[`contracts/frozen-runtime-manifest-v1.json`](../../contracts/frozen-runtime-manifest-v1.json).
The existing image has an immutable local image ID, not a published registry
reference. [`handoff.md`](handoff.md) records exact evidence and remaining work.

**Current access boundary:** the core uses one shared API key and has no browser
sessions or per-user ownership. Agent A acknowledged single-reviewer private
administrative use only. Both deployment profiles gate browser uploads. There is
no activated or externally verified jury URL. A supplied hostname/certificate,
accepted runtime handoff, and the core security work are still required.

## Install the actual administrator artifact

Python 3.12+ runs these dependency-free tools. This is a local artifact, not an
advertised public package. From this checked-out branch:

```sh
python3 tools/forte-admin/build.py --output /tmp/forte-admin-0.1.0.tar.gz
mkdir -p "$HOME/.local/lib/forte-admin-release"
tar -xzf /tmp/forte-admin-0.1.0.tar.gz -C "$HOME/.local/lib/forte-admin-release"
export PATH="$HOME/.local/lib/forte-admin-release/forte-admin-0.1.0/tools/forte-admin:$PATH"
forte-admin --version
forte-admin --help
```

The archive contains only administrator/deployment source, public configuration
examples, source-file hashes and its source commit. It contains no recordings,
keys, model weights, application image or browser build. Build twice to obtain
the same bytes from unchanged inputs. Check the printed SHA256 when transferring
it through your approved software-distribution channel.

Read [the administrator guide](administrator.md),
[reviewer quick start](reviewer.md), [observed API](observed-contract.md), and
[operations/upgrade/rollback](operations.md).

## Evidence levels

Configuration generation, synthetic transport tests, local TLS checks, real
single-container inference, clean-host installation and external-browser access
are separate checks. This lane does not claim that one establishes another.
The package never switches a private job to hosted processing after a failure.
