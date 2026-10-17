# Browser session continuation

This source-only continuation starts from `131463f` on
`codex/browser-session-ownership`. The previous verified image/core and its
frozen runtime manifest remain historical evidence. No GPU allocation,
publication, live attach or model-quality acceptance is authorized by this plan.

## Trust boundary

Apply the reviewed principal patch to the API. Legacy key-only v1/v2 behavior
remains when trusted-gateway mode is absent. When enabled, every API request
requires the separate server-only gateway token and an opaque principal, in
addition to the service key. Admission persists that principal; every case,
original, evidence, correction and later range checks it. Ownerless cases deny.

Add an internal authenticated `GET /api/internal/security` capability response
in trusted mode only. Its exact fields are `schema_version:
forte.gateway-security/1`, `trusted_gateway_required: true`,
`principal_ownership: true`, `ownerless_jobs_denied: true`. Every trusted-mode
API response also carries `X-Forte-Ownership-Mode: principal-v1`.

A host-loopback stdlib session gateway keeps all service/gateway secrets outside
the browser and outside the offline model container. Users have persistent
opaque IDs; passwords are salted scrypt hashes in a private SQLite database.
Session IDs are random, stored hashed, rotated on login and revoked on logout,
password reset or user disable. Use an eight-hour absolute and thirty-minute
idle expiry. The cookie is `__Host-forte_session`, Secure, HttpOnly, SameSite
Strict, Path=/, without Domain. No default/real account is created by source
setup; account administration is an explicit local CLI action.

Mutations require exact configured HTTPS Origin and a per-session CSRF token.
Login requires exact Origin and a small JSON body. No CORS, forwarded identity,
client API key, gateway token or reviewer field establishes identity. Strip all
incoming internal auth headers and inject secrets plus the authenticated user ID
on the private app hop. Never log credentials, cookies, case bodies or paths.

Before each API forward, verify the core capability on the same persistent
upstream HTTP connection used for that request; refuse a closed/replaced
connection. Also require the ownership response marker before returning API
bytes. Do not retry a mutation or redirect an authenticated upstream request.
Legacy/incorrect upstreams must never silently become a session backend.

Use bounded streaming for uploads and binary/range responses. Reject ambiguous
framing, unsupported transfer encoding, duplicate sensitive headers and oversized
login bodies before consuming them. Core upload/time/admission limits stay in
force. `/api/internal/` is not proxied to browsers.

## Browser endpoints

- `GET /deployment.json`: public no-store metadata from the gateway.
- `GET /auth/session`: 200 with `authenticated: false`, or an authenticated
  principal (`id`, `username`), `csrf_token` and `expires_at`.
- `POST /auth/login`: JSON `username`/`password`, exact Origin; returns the
  authenticated session and sets the protected cookie. Generic errors.
- `POST /auth/logout`: Origin plus `X-CSRF-Token`; revoke, expire cookie, 204.
- Existing `/api/v1/` and `/api/v2/`: session-authenticated gateway forwarding;
  CSRF plus Origin for mutations; generic cross-owner 404 from the core.

Deployment metadata uses `schema_version: forte.deployment/1`, `mode: private|hosted`,
`auth_mode: browser_session`, `destination` (configured HTTPS origin),
`browser_uploads_enabled`, `ready`, `retention: manual`, `training_enabled:
false`, and `limits` with `upload_max_bytes`, `max_video_seconds`,
`upload_timeout_seconds`, `job_timeout_seconds`. Uploads require explicit
operator configuration, successful ownership handshake and readiness.
The optional gateway `deployment_mode` selects that label and defaults to `private`.
It describes where processing is offered, independently from the installer's
`private|attach` ownership profile. `hosted` does not activate a host, enable
uploads, change authorization or approve publication.

The UI uses same-origin credentials and CSRF; no service-key field or browser
storage. Preserve the approved shadcn preset and review workflow. Clear private
state and revoke object URLs on logout, expiry or principal change. Recheck on
focus/pageshow and notify other tabs of auth changes without storing secrets.
Metadata missing, mismatched origin or unavailable security fails closed.

## Deployment and evidence

Keep current admin-only profiles as the default. Add an explicit browser-session
profile which runs the host gateway behind the supplied-certificate TLS ingress,
mounts the separate gateway token into the offline core, and never publishes the
core/model ports. Setup/up/stop must own only their profile resources and preserve
private DB, configuration, originals, corrections and credentials.

The CLI may support session credentials from a protected private file; legacy
operator-key profiles remain explicit. Session profiles never send the service
key. Administrator archives include public source/metadata only.

## Source integration interface

The independent deployment lane owns `deploy/portable/`, `tools/forte-admin/`,
`docs/deployment/` and `tests/deployment/`. Session implementation lives separately
under `tools/forte-session/`. The deployment lane integrates its stable checkpoint;
session code does not rewrite the deployment lane's active files.

Run `python tools/forte-session/session_gateway.py --config <private-json>`.
`create_server(config, store=None)` returns a stdlib HTTP server, bound only to
`127.0.0.1`. Configuration keys are `listen_host`, `listen_port` (default 18002),
`origin` (exact HTTPS origin), `upstream` (literal loopback HTTP origin),
`service_key_file`, `gateway_token_file`, `session_db`,
`deployment_mode` (private or hosted, default private), `browser_uploads_enabled`
(default false), and the four `limits` above. TLS belongs
to the supplied-certificate ingress in front of this host listener. Secret values
must never enter installation JSON, frontend assets or the public manifest.

Provision the first account explicitly with
`python tools/forte-session/session_store.py --db <private-path> add <username>`;
passwords are prompted privately, never supplied in arguments. The same CLI offers
`disable`, `reset-password` and `list`. Setup creates no default account or password.
`expires_at` is a numeric Unix timestamp in seconds. Gateway/store source and their
synthetic tests are distinct from a built GPU image and deployment acceptance.

Verify actual modified FastAPI plus gateway over local HTTPS using synthetic MOV
and model responses: two users, v1/v2, all resources, independent ranges, CSRF,
forgery/duplicate headers, expiry/logout/disable/restart and legacy-core refusal.
Browser QA must use synthetic data only. Keep new runtime/image, real GPU,
external URL, session activation and quality acceptance separate and unapproved.
