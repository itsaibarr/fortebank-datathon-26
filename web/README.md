# Local video review workspace

Next.js App Router, TypeScript and Tailwind use the user-selected shadcn preset
`b3d6mT4h6m`: Nova, zinc, sky, Manrope/Geist and Lucide. The previous setup-only
note is preserved in [the archived setup note](../docs/archive/frontend-setup-20261017.md); the explicit library approval
supersedes its unselected-library state.

Run from this directory:

```sh
npm ci
npm run dev -- --port 3102
npm run typecheck
npm run lint
npm test
npm run build
```

`npm run build` produces the static `out/` directory. Set
`FORTE_FRONTEND_ROOT=/absolute/path/to/web/out` on the FastAPI service to serve
it behind the approved browser-session gateway, on the same HTTPS origin as
`/auth/`, `/deployment.json` and `/api/v2`. The development server alone does not
supply these services. Direct key-only API access does not enable this browser UI.

The UI signs in through the same-origin session gateway. The HttpOnly cookie is
managed by the server; only the session CSRF token is held in page memory. No
service key, gateway token or browser storage is used. Mutations carry CSRF,
while original video and JPEG evidence are fetched with same-origin credentials
before local blob URLs are created. Logout, expiry, 401, principal changes and
cross-tab auth changes clear private state, cancel requests and revoke these URLs.
Focus and restored-page events recheck the session. Failed metadata or an origin
mismatch disables uploads, while an authenticated review can remain open during
a readiness outage. The page displays verified destination, limits, manual
retention and no-training policy. Verified metadata selects the exact “Private
installation” or “Hosted service” label. Both modes require the same session,
exact HTTPS origin, readiness and explicit upload activation checks.

No key, job, recording, evidence or reviewer content is fetched during the static
build. Fonts are downloaded during the public build and served from local build
assets at runtime.

Sign in with your administrator-provided account, then upload and analyze a MOV.
Completed and partial execution
remain separate from assessment certainty. Select an event to seek the original
video, inspect original frames and participant proposal overlays, check exact
local provisions and condition findings, or append a scoped correction. The
condition tab also exposes every recording-wide legal finding and skipped rule.
The correction history preserves prior revisions and independent review scopes.

Browser verification uses only generated synthetic media and explicitly mocked
API replies in the test browser. Those fixtures are outside the build and are
not a production fallback. Upload/poll/authentication propagation, seek, overlays,
evidence, condition navigation and correction/history mechanics were exercised;
this does not establish recognition or legal accuracy on competition recordings.
