# PRODUCT_W1 implementation and delivery record

Updated 18 October 2026. The bounded delivery is case investigation, immutable
review reporting and source-context navigation. Vendor research did not replace
the tracker, inference engine, legal evaluator, schema or v1 jury detector.

## Source and ownership

The contributor checkout is
`/Users/itsaibarr/conductor/repos/fortebank-product-w1`, branch
`codex/product-w1`, verified base `e4814e23d3ef827f9831414e272cca16673f8b7b`.

- `7d34fae3ac774c032e4410df54d4e674f95754b2`: investigation controls,
  source-complete JSON report, locked correction snapshot, tests.
- `1098dc24c8a9b424f9260ba367b30077cc58a41e`: preserve the selected event/draft
  when filtering; block case switches during outstanding actions; improve errors.
- `22c991fc05149c7ced111a4a9e27e39c7374c17d`: per-case/request history cancellation,
  stale-response rejection, overlapping-reload exclusion and save-field locking.

The designated source integrator remains A, thread
`2c5cea8b-735f-4560-a2d5-ba1f6ffa98fe`. Its authoritative checkout is
`/Users/itsaibarr/.t3/worktrees/fortebank-datathon-26/t3-ca5de3e3`, branch
`t3/review-agent-b-integration`. The common coordination surface is
`/Users/itsaibarr/conductor/repos/fortebank-datathon-26/.git/forte-coordination/`.
All status/handoff writes use its existing `coordination.lock` with `fcntl`
exclusive locking and atomic replacement. A, B, CORE_W2 and PRODUCT acknowledged
the same shared filesystem. PRODUCT updates only its own records/handoffs.

Main evaluation files and B's deployment directories were not edited. TEST owned
the single frozen GPU runtime and preservation timers throughout product work.
PRODUCT performed no VM provisioning, SSH, model request, service restart,
ingress mutation, paid allocation or budget extension.

## Delivered behavior

**AD-01 — Investigate an owned recording.** Combine local word matching with exact
actor/recipient ID, inclusive source-time overlap, assessment and saved-correction
presence. Search covers existing event/linked observation text, identifiers,
uncertainty, notes and linked rule explanations. This is lexical candidate
retrieval, not semantic search. Source IDs, original ordering and adjacent events
remain separate. No-match and invalid-range states cannot clear a recording.
Filters remain in component memory; case text never enters a URL, localStorage,
analytics or external search. A filtered-out event loses selection rather than
inheriting another event's draft.

**AD-02 — Export and reopen.** Download a complete recording report, retaining the
unchanged original result and full correction ancestry even when the screen is
filtered. Reopen an owned persisted job by its UUID without rerunning analysis or
storing a case list in the browser. Ownership remains server-enforced.

**AD-03 — Review in source context.** Seek directly to unexamined/unclear intervals,
retain independent partial/skipped coverage, and inspect all recording targets
or one event's correction history. Show target, parent, source hash, original-result
hash, origin and structured change. Initial/manual history requests share an
abort/generation guard, and only the current case/request may commit a response
or clear loading. Save/reload fields and case-switching actions are locked while
their operations are pending. Corrections preserve the proposal; they do not
approve another scope, revise legal conclusions or retrain/condition the model.

## Interfaces and persistence

`GET /api/v2/jobs/{job_id}/report` adds schema
`forte.investigation-report/1`. It returns `job_id`, export time, complete-case
scope, `base_result_sha256`, unchanged `result`, ancestry-ordered `corrections`,
`corrections_match_current_result`, `review_head`, authenticated case-relative links
and limitations. It references media rather than embedding video/JPEGs. The route
uses `completed_reasoning()` / `read_job()` principal and API-version checks before
history access; another owner or ownerless job receives generic 404. It returns
`Cache-Control: no-store` and an attachment filename based only on the UUID.

`GET .../corrections` keeps its response shape and now reads under the writer's
existing `.revision.lock`. It verifies source, immutable-base identity, ancestry
and independent-scope fields. Unsafe symlinks/FIFOs, malformed/mixed-source/forked
records or unreasonable history sizes fail with sanitized 409. Old-result
sidecars survive reruns and remain explicitly mismatched to the new base; they
are never replayed or silently overwritten. The digest serialization exactly
matches `timeline.append_correction`.

No schema migration, new dependency, browser secret, gateway source edit or new
service is required. The existing gateway forwards authenticated v2 routes and
attachment headers. A owns the shared authenticated OpenAPI artifact and adds the
new report module to application fingerprints. Exact v1 and reasoning-result
formats are preserved. The new mechanic's dispatch through the fixed v1 jury
endpoint remains a separate unresolved integration concern.

## Verification evidence

- PRODUCT root independently ran 39 report/API/v2/actual local HTTPS integration
  checks, passing with one existing warning. A child ran 51 report/API/v2/gateway
  checks, passing. These suites overlap and are not 90 unique tests.
- Final contributor frontend: 17 tests pass, including controlled late-case and
  superseded-request cases; ESLint, TypeScript and production static export pass.
  Independent UI source review found and drove the draft/history race fixes.
- Report checks retain original result equality, adjacent actors, zero PTS,
  unknown/null values, skipped rules, correction ancestors and old-base mismatch.
  They cover principal/version denial, corrupt history, symlinks, FIFO rejection
  and exclusion of partially written sidecars under the existing lock.
- The earlier combined source `53ebe49d26a102e026e4e8ce9149c80995e64db0`
  passed 749 Python tests, one optional skip and four existing warnings, as reported
  by A/CORE. Its Python changes include OpenAPI, real HTTPS report ownership and
  the twentieth application fingerprint. That receipt predates `22c991f`'s UI fix.
- Earlier product/integrated synthetic browser runs exercised sign-in, generated
  H264 MOV upload, actual API result, original playback, event/filter selection,
  correction persistence, full report download, source seeking and UUID reopening.
  Those runs are baseline evidence until the final UI artifact is retested.

The latest contributor static build manifest is
`3f9950e5a1643bbb071b0cfe3d1978c551ab96ae51859fc33b23181a97a81f2d`
(44 files). Its source is `22c991f`; build files contain no case data. Final browser
verification will use a read-only snapshot of that artifact and record server
source identity separately.

T3 preview failed twice on the generated local QA certificate with
`ERR_CERT_AUTHORITY_INVALID`. BrowserOS's own tab accepted the local test-certificate
interstitial. This is a synthetic loopback test exception, not external HTTPS or
production certificate acceptance. Native file-chooser operation is separate;
browser automation populated the actual file input with generated media.

## Research and evidence

[RESEARCH_REPORT.md](RESEARCH_REPORT.md) covers both vendors across nine dimensions.
[FINDINGS.json](FINDINGS.json) preserves 58 classified findings, 49 source records
and 48 distinct URLs with selected/deferred mappings. The
[REA record](docs/product-research/REA.md) and
[evidence manifest](docs/product-research/evidence-manifest.json) identify two
executed public-page launch scenarios. No vendor analytics or authenticated
workflow/model/API/network-body behavior was observed. Vendor legal/compliance
claims never enter the official Kazakhstan corpus.

The authoritative 40-group split manifest's 31 development hashes exactly match
the current neutral/hash projection; nine reserved groups were excluded. A
network-denied hash-only audit verified the 31 development source files without
viewing frames. Full membership and audit receipt remain outside Git at
`/Users/itsaibarr/.local/share/forte26/product-adaptation-20261018-v1/`.
Session grouping still requires review. The requested
`fortebank_rea_visual_detail_prompt.txt` was not found by bounded filename searches
of the repository, conductor workspaces and Downloads; no contents were invented.

## Rollback and remaining limits

Revert the three product commits through A in reverse order, keeping dependent
UI/API changes together. Existing result/correction formats remain compatible;
retain originals, sidecars and backups. No private data migration is necessary.

Calibrated queue/dwell/zones, live VMS ingestion, cross-camera identity, appearance
embeddings, enterprise administration/connectors and semantic chat are deferred
pending reviewed inputs/interfaces/resources. Five-second time-only event merging
is rejected for actor-sensitive bank review. No model/checkpoint, legal corpus,
training target, coverage claim or semantic-quality claim is promoted by these
product tests. Final authoritative runtime and real-inference/latency/quality
acceptance remain distinct from local synthetic UI verification.

## Final delivery status

All three product commits are integrated in frozen application
`ebb3d82e8728dec21289d34e9b9fb81b95f5d0f3`; `22c991f` maps to integration commit
`4055598`. A independently checked the exact web tree
`c978bfbb970df43b32ede6956aeb5fece6e485a3` and unchanged Python/contracts from
the 749-test source. Later documentation-only HEAD changes do not change this
application identity.

[The final verification manifest](docs/product-research/final-verification.json)
records actual local execution of that application plus the immutable 44-file
UI artifact: generated H264 MOV upload, API completion/partial state, original
playback, zero-time/actor filters, filtered draft safety, 1,000 ms delayed
reload/save locking, two visual/role corrections on distinct events, full report
download, ancestry/PTS/time-base/coverage/unknown-rule preservation, source seek,
logout clearing, cross-owner generic 404, and owner UUID reopen with two retained
revisions and a fresh 32-byte HTTP 206 source read. Report equality and its
canonical digest were independently checked after download. Desktop width 1,256
and mobile width 390 had no horizontal overflow and were visually inspected.

The final synthetic server's actual boot HEAD was `ebb3d82`, empty dirty diff,
with twenty application-module fingerprints. All 45 tracked web files matched
contributor `22c991f`. Its served snapshot was read-only and independent of future
builds. A's durable artifact is
`/Users/itsaibarr/.local/share/forte26/source-candidates/ebb3d82e8728dec21289d34e9b9fb81b95f5d0f3/web-out`.
Its compact JSON file-map digest is
`6c6071796163d7a88880b17c64771b8da735cd9d68dc2f8d2223d70345fe17ab`;
the producer's differently serialized file-map digest is `3f9950e5…81f2d` above.
Both describe the same independently checked per-file bytes.

The final QA process, both earlier QA processes, synthetic sessions and owned
browser tabs were closed. Durable generated-input, boot/stop, reproduction and
download evidence is outside Git under
`/Users/itsaibarr/.local/share/forte26/product-adaptation-20261018-v1/`.
No service credential, test private key or session database was copied into the
public receipt or Git.

The selected product scope is complete and verified at the source/local synthetic
boundary. Combined production completion remains **unverified**: TEST rejected a
late candidate GPU/API start after the 01:00 UTC cutoff, retained all baseline
evidence and deleted its VM. PRODUCT requested no extension or replacement.
There is no fresh candidate GPU result, new qualified image, public HTTPS site,
clean CUDA-host installation or new recognition/legal quality approval. Actual
model/processor/serving configuration and official corpus were not exercised by
the explicit synthetic runner; the manifest records source configuration hashes
as source identity only. Fixed-v1 dispatch to the new mechanic is still separate.

A retains release/runtime authority. Documentation and any future acceptance work
transfer explicitly to A and consolidation thread
`741ce35c-f3ab-47e4-939f-13f093d0f042`; nothing requires a sleeping-user research
review or routine approval. Source and synthetic verification must never be
relabeled as the missing real deployment acceptance.

The later readable role/action projection request is tracked as AD-04 in
FINDINGS.json. TEST is preparing its offline renderer/contract in an isolated
checkout; A and consolidation coordinate any new web/API delivery. It is not
silently added to the frozen application or reported as implemented. Its generic
requirements preserve multiple participant hypotheses, temporal action support,
uncertainty and abstention; summary/people/actions/evidence/coverage precede raw
technical details. No role is assigned from clothing, position or a fixed global
cashier/client assumption. No private examples or case descriptions are required.
