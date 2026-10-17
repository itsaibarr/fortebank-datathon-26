# Local video review workspace

Next.js App Router, TypeScript and Tailwind use the user-selected shadcn preset
`b3d6mT4h6m`: Nova, zinc, sky, Manrope/Geist and Lucide. The previous setup-only
note is preserved in `README.setup-history.md`; the explicit library approval
supersedes its unselected-library state.

Run from this directory:

```sh
npm ci
npm run dev -- --port 3102
npm run typecheck
npm run lint
npm run build
```

`npm run build` produces the static `out/` directory. Set
`FORTE_FRONTEND_ROOT=/absolute/path/to/web/out` on the FastAPI service to serve
it on the same origin as `/api/v2`. The development server alone does not supply
the API; use the built static site with the service for a real analysis.

The UI calls the explicit versioned reasoning route, retains the service key
only in component memory, and fetches source video and JPEG evidence with the
authentication header before creating local blob URLs. No key, job, recording,
evidence or reviewer content is fetched during the static build. Fonts are
downloaded during the public build and served from local build assets at runtime.

Upload a MOV, enter the service key, and analyze. Completed and partial execution
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
