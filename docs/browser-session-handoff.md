# Browser session source handoff

The source chain starts at `131463f`: core ownership is `bdf3173`, the standalone
gateway/store is `5be7d78`, and the session UI is `7fa153f`. The hosted-label
checkpoint `e55c077` adds an explicit deployment label; it does not activate a host.
The deployment lane integrates these commits into `codex/guided-private-install`.
No deployment-lane file was changed by the core/session/UI lane.

The exact interface is [browser-session-contract-v1.json](../contracts/browser-session-contract-v1.json).
The [architecture and threat boundary](browser-session-plan.md) explains the
same-connection capability check and the separation from the historical GPU image.

## Launch and first account

Run the host gateway behind the supplied-certificate TLS ingress:

```sh
python3 tools/forte-session/session_gateway.py --config /srv/forte/session-gateway.json
python3 tools/forte-session/session_store.py --db /srv/forte/auth/users.sqlite3 add reviewer
```

The second command prompts twice for a password. No default account/password is
created, and passwords are not accepted in command arguments. The account CLI also
supports `list`, `disable <username>` and `reset-password <username>`. Reset and
disable revoke existing sessions. Preserve the database and its opaque principal
IDs across upgrades; do not assign ownerless historical cases to a new user.

Example configuration contains paths, not secret values:

```json
{
  "listen_host": "127.0.0.1",
  "listen_port": 18002,
  "origin": "https://review.example.invalid:8443",
  "upstream": "http://127.0.0.1:18001",
  "service_key_file": "/srv/forte/secrets/core-api.key",
  "gateway_token_file": "/srv/forte/secrets/gateway-token",
  "session_db": "/srv/forte/auth/users.sqlite3",
  "deployment_mode": "private",
  "browser_uploads_enabled": false,
  "limits": {
    "upload_max_bytes": 268435456,
    "max_video_seconds": 180,
    "upload_timeout_seconds": 30,
    "job_timeout_seconds": 270
  }
}
```

Use the canonical HTTPS origin shown by the browser, without a trailing slash.
Credential files and the database are owner-private; their directories remain
outside Git. Mount the same gateway token read-only into the core and set
`FORTE_TRUSTED_GATEWAY_TOKEN_FILE` to its container path. The service key and
gateway token must differ. The gateway rejects a legacy or incompatible core.

`deployment_mode` is `private` or `hosted`, defaulting to `private`. It selects the
honest UI label and always reports the configured destination. The installer's
`private|attach` mode controls service ownership independently. Neither a label
nor a successful metadata request authorizes public uploads.

## Probes and routing

Route nginx `/`, `/auth/`, `/api/`, `/deployment.json` and health paths through the
session gateway; preserve the configured origin's authority as `Host`. Direct
loopback probes must set that Host too. `/health/live` returns 200 with
`{"status":"alive"}`. `/health/ready` returns 200/`ready` only when the trusted
core capability and model readiness pass; otherwise it returns 503/`not_ready`.
These responses expose no account or case details.

`/deployment.json` is no-store and reports mode, exact destination, readiness,
effective upload flag, four limits, manual retention and no training. Effective
uploads require explicit operator activation plus live ownership and readiness.
`/auth/session`, `/auth/login` and `/auth/logout` manage the protected cookie and
per-session CSRF token. Do not forward client identity or service-key headers to
the core. The gateway injects its own authenticated principal and secrets.

## Verification boundary

Checkpoint `e55c077` passed 378 Python tests, one optional Docker skip and four
existing warnings. Six actual local HTTPS tests used modified FastAPI,
gateway, SQLite sessions, generated MOV and an explicit fake inference runner.
They cover v1/v2 ownership, cross-user generic 404, forgery, source/JPEG/fresh
ranges, corrections, CSRF, revocation, readiness and legacy-core refusal. Gateway
tests cover framing, connection closure, missing markers, redirects, secret-header
stripping and encoded-route rejection. Frontend lint, types, eight contract/body
tests and static export passed; delayed and buffered bodies cannot outlive their
session generation.

The aggregate [source verification receipt](../.context/verify/browser-session-source-20261018.json)
pins checkpoint `e55c077`, the tested source bytes and unchanged historical
manifests. Hosted/private frontend checks have a separate versioned receipt;
the original session receipt remains bound to `7fa153f`.

Interactive browser QA is separate. T3 and gstack rejected the local synthetic
certificate with `ERR_CERT_AUTHORITY_INVALID`. After the human accepted the native
browser exception, actual sign-in and deployment notices were verified. The native
file chooser then hit a ScreenCaptureKit `-3812` automation error; upload/result
browser interaction remains incomplete pending the human's file selection. The
source QA receipts preserve their earlier observation times. No private media was
opened by browser/screenshot tools.

The historical frozen GPU image/manifests remain unchanged. This source has no
new qualified image, external HTTPS check, production activation or detection/legal
quality approval. A compatible CUDA host may perform an explicit bounded offline
qualification with pinned source/image/resources; record measurements without
changing production or quality acceptance flags. No new machine, paid resource
or public hostname has been activated in this continuation.
