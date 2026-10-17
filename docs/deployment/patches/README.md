# Proposed trusted gateway ownership patch

**Prepared for Agent A; not applied to the application checkout.** Base:
`111234c885f0a23d323fe72a81450dfca5aa7e60`. Exact source-file hashes are in
[base-files.json](base-files.json). [trusted-principal.patch](trusted-principal.patch)
changes only `src/forte/api.py`, `src/forte/settings.py` and a new synthetic test
module. Canonical result schemas, legal reasoning, original PTS, evidence,
correction scopes and model configuration are unchanged.

The missing behavior is authorization of a case to a particular trusted
principal. A shared upstream API key currently grants access to every known job
in its service root. This patch proposes an **optional internal gateway mode**:

- Configure `FORTE_TRUSTED_GATEWAY_TOKEN_FILE` to a separately generated,
  server-only secret of 32–256 printable ASCII characters. It must differ from
  the upstream service API key. The token file must be readable only by the
  service administrator and mounted read-only into the application. No secret
  value goes into this packet, the runtime manifest or browser JavaScript.
- When enabled, every `/api/` request needs the existing `X-API-Key`, exactly one
  `X-Forte-Gateway-Token` matching that separate secret, and exactly one
  `X-Forte-Principal`. Principals are opaque, stable, case-sensitive IDs matching
  `[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}`. Missing, forged, duplicate or malformed
  internal identity headers fail with 401 before request-body consumption or
  route validation. The API does not derive a principal from a client field.
- Both v1 and v2 admissions persist `owner_principal` atomically in private
  request metadata before launching the worker. Both poll/result routes and all
  existing v2 original/evidence/correction routes check that owner through the
  common reader before accessing result/media/correction content. A different
  principal and an unknown job receive the same generic 404. Every new range
  request traverses that check. Existing ownerless jobs fail closed; no owner is
  guessed or silently migrated.
- In trusted mode, saved correction attribution uses the authenticated principal
  rather than the client-supplied `reviewer`. Independent correction approval
  scopes and immutable lineage remain unchanged.
- Without the new setting, the current API-key-only behavior and exact legacy
  v1 shapes remain available. That default mode **does not provide user
  isolation**. Liveness, readiness and static assets are unchanged.

This is not a browser session implementation. The trusted gateway is a
privileged component: it must authenticate the browser, enforce session/CSRF
rules, strip incoming principal/token headers, obtain the principal from that
authenticated session, and inject both secrets server-side on the private
application hop. Untrusted clients must not reach an alternate application
listener that supplies these headers. A user-controlled `reviewer`, forwarded
header or front-door shared password does not establish that session.

The current portable gateway strips principal headers and has no such session
layer. Enabling this core setting without the agreed gateway intentionally
causes API requests to fail authentication. The patch therefore does not enable
browser uploads, set installer ownership/session verification flags or establish
external access. Keep those gates closed pending Agent A's acceptance and full
gateway integration. Future private previews, clips, exports or media routes
must call the same ownership-aware reader before serving content.

## Verification and owner integration

`git apply --check docs/deployment/patches/trusted-principal.patch` passes against
the deployment worktree's unchanged core source at the base above. The patch was
also applied only inside a disposable `git archive` snapshot of that commit.
There, **31 targeted tests passed**:

```sh
python -m pytest -q tests/test_gateway_ownership.py tests/test_api.py tests/test_api_v2.py
```

The new synthetic checks cover missing/forged/duplicate internal identity,
authentication before upload consumption, both API versions, owner metadata,
cross-version isolation, every existing private route, correction writes and
trusted attribution, a valid owner byte-range followed by another principal's
denied range, restart persistence, ownerless legacy jobs, optional secret-file
configuration and unchanged default v1 behavior. The existing v1/v2 tests pass
alongside them. The run emitted one existing Starlette/httpx deprecation warning.
Receipt: [verification.json](verification.json). No GPU, VM, real case media,
remote browser or private inference was used, and source hashes in the actual
worktree remained unchanged.

After Agent A accepts the patch, the designated integrator must apply it to the
correct base, rerun the full core suite, build a new immutable image and refresh
source/runtime/contract receipts. Then verify the real session boundary and
cross-user denial over HTTPS, including independent later range requests,
corrections and every private route. Establish migration/administrative access
for ownerless cases explicitly; do not weaken the default denial to make an old
demo accessible. Only after these checks may the corresponding installer
verification flags change. Synthetic patch tests are not that approval.
