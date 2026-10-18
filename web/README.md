# Local video review workspace

Next.js App Router, TypeScript and Tailwind use the user-selected shadcn preset
`b3d6mT4h6m`: Nova, zinc, sky, Manrope/Geist and Lucide. The sole backend
architecture is described in [report.md](../report.md): frozen 8B visual
facts, mandatory CPU Laya condition proposals and deterministic output adapters.

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
Saving a correction does not establish its use by later inference; automatic
reviewed-correction replay remains an open [task](../tasks/todo.md).

Browser verification uses only generated synthetic media and explicitly mocked
API replies in the test browser. Those fixtures are outside the build and are
not a production fallback. Upload/poll/authentication propagation, seek, overlays,
evidence, condition navigation and correction/history mechanics were exercised;
this does not establish recognition or legal accuracy on competition recordings.

The app header links the [jury documentation](https://datathon-f289adc4.mintlify.site/introduction). The Mintlify source is `../docs-site/`; it deploys separately from the application.
