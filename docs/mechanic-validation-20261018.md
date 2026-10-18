# Practical mechanic validation — October 18, 2026

This is an exploratory development smoke test, not an accuracy benchmark. The
original archive was verified against the pinned SHA256 and ZIP CRCs. All 31
development groups and their 33 extracted aliases matched their existing hashes.
Reserved extracted recordings were not opened. Three distinct non-diagnostic
groups were selected: a supplied positive, a supplied normal case and a prior
tracking pilot. Supplied labels are sampling metadata, not independently verified
event, role or interval references. Session/camera grouping remains unfrozen.

The evaluation owns only the harness, synthetic checks and this report. It does
not change the detector, model, prompts, legal approvals, browser sessions,
installer or deployment acceptance. No training or public benchmark download ran.

## Reproduction

The harness is `python -m forte.mechanic_validation`. Preparation snapshots public
source, configuration, legal assets and contracts; verifies the archive and
extracted development aliases; copies only three neutral allowlisted sources;
and separates sampling/reference material from inference inputs. It refuses
nonempty output directories. The execution command refuses changed snapshots or
inputs and requires OS-enforced IPv4/IPv6 outbound denial.

```sh
PRIVATE_ROOT="$HOME/.local/share/forte26/development-rehearsal"
RUN="$HOME/.local/share/forte26/mechanic-validation/NEW-VERSION"
uv run python -m forte.mechanic_validation prepare \
  --private-root "$PRIVATE_ROOT" \
  --archive "$HOME/Downloads/open.zip" --extracted "$HOME/Downloads/open" \
  --reid-manifest "$HOME/.local/share/forte26/frozen-public/reid/manifest.json" \
  --output "$RUN"
env PYTHONPATH="$RUN/snapshot/src" \
  /usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' \
  "$PRIVATE_ROOT/person-tracking-v1/_runtime/.venv/bin/python" \
  -m forte.mechanic_validation execute --output "$RUN"
```

The Mac command makes honest automatic-run attempts and independently runs real
CPU YOLOX/ByteTrack/OSNet tracking. The pinned 27B BF16 model requires the separately
prepared CUDA environment. The Mac does not substitute another semantic backend.
Use a network-disabled Linux container for GPU inference, with public assets
downloaded before private media is mounted. Keep the existing frozen configuration
and full recordings. The normal API rehearsal client is:

```sh
python /app/rehearse_reasoning_api.py \
  --file /private/media/clipNNN.mov \
  --key-file /run/secrets/service-api.key \
  --allowlist /config/development-allowlist.json \
  --expected-sha256 SOURCE_SHA256 \
  --output /private/rehearsal/NEW-CASE-VERSION --timeout 300
```

Its allowlist contains only neutral names, development membership and hashes. It
has no supplied labels, expected roles, actions, events or timestamps. It measures
upload/poll/result/source/JPEG verification against loopback inside the isolated
container; it does not measure a remote browser workflow. Each case is backed up
locally and verified before the next case starts.

## Verified software boundaries

The local suite passed **384 tests, one optional skip, four existing warnings**
in 50.04 seconds. Six focused synthetic checks cover case selection, diagnostic
and reserved exclusions, reference-free inference projection, version dispatch,
supported positives surviving unrelated partial fragments, and incomplete coverage
remaining insufficient. Existing checks cover source PTS/JPEG integrity, strict
v1 serialization, omissions, actor consistency, draft interpretations, applicability
and legal evidence validation. These are software checks, not recognition scores.

Observed integration failures, reproduced without changing public cards:

1. Even with a reasoning configuration, v1 dispatches the legacy detector and
   v2 dispatches the new mechanic. V2 results cannot be read as v1 jobs. The exact
   required jury response therefore does not execute the new mechanic.
2. All twelve legal cards are drafts; zero are approved. All twelve default plans
   have unknown edition applicability and require metadata. The normal runner
   constructs the law service without reviewed applicability bindings and passes
   operation context without `metadata_evidence`. A context dictionary does not
   establish an authorized condition evidence item. These gates correctly remain
   closed; Qwen cannot approve them.
3. The default legal budget is two calls for twelve cards. It cannot complete the
   scoped inventory even with perfect recognition. Skipped rules stay explicit.
   The visual schedule and source evidence export also share the 270-second
   analysis deadline. A completed sample schedule does not establish continuous
   visibility or the full opportunity needed for an omission.

Sources: `src/forte/{api,worker,reasoning_pipeline,legal_reasoning,timeline}.py`,
`configs/frozen-inference.json`, `legal/rule-cards.json` and the frozen snapshots
recorded privately. No gate was relaxed to manufacture a positive or normal result.

## Local component execution

All three full recordings completed frozen CPU tracking with outbound networking
denied. The source ledger contains **3,186 frames over 106.367 seconds**; tracking
examined **642 detection samples**. These are proposed observations, not counts of
physical people or verified continuous visibility. All participants start without
assigned roles; the tracking run created no role hypotheses.

| Stage | Executed / planned | Time across three recordings | Acceptance |
| --- | ---: | ---: | --- |
| Complete source decode and PTS ledger | 3 / 3 | 8.468 s | Mechanical pass |
| Frozen YOLOX + ByteTrack + OSNet | 3 / 3 | 47.037 s | Execution pass; accuracy not evaluable |
| Local playback and source checks | 3 / 3 | 9.546 s | 9 / 9 JPEGs match independent source re-extraction |
| Total component execution | 3 / 3 | 65.057 s | Separate from API latency |
| Automatic Mac inference | 0 / 3 executed; 3 blocked | Recorded privately | No resident pinned Qwen service |
| Independent human review | 0 / 3 | Not measured | Geometry/identity/view and semantic accuracy not evaluable |

Private immutable artifacts are under
`~/.local/share/forte26/mechanic-validation/20261018-01/`. The saved predictions,
source tables, complete oriented playback, nearest-sample overlays, independent
JPEG checks and separate scoped review templates precede human review. This
report contains no scene descriptions, original filenames, recording hashes,
person IDs, timestamps of suspected events or model narratives.

## Run identities

The initial snapshot was made at Git HEAD
`252fc37e25abeb41863ecabbece2a8ef2378318d`, with core source matching
`e55c0773ea74e2745ea33512d19bfaa38b32d7fb`, plus the new evaluation harness.
Its complete file inventory, working-tree state,
effective configuration and reference-free input hashes are recorded privately.
The snapshot digest is
`d2c0a6187e840b8be351d4f9a03ce7f37f42668bbcaa1608a0d1bcff1e0d5105`.
The harness and focused tests were subsequently committed at `dc38664`.

Model: `Qwen/Qwen3.8-27B`, revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, BF16, no adapters. Its expected manifest
is `contracts/frozen-model-hashes-v1.json`. The actual CUDA runtime verified all
30 assets, including all 18 weight shards; separate runtime and visual warmup
receipts are preserved locally. YOLOX, ByteTrack and OSNet identities are pinned by
`configs/person-tracking.json` and the private public-asset manifest. Public law
corpus digest:
`d48d9db466d7fc5be7eb630a3424bab6818da11b11ca614eda1f9ac2a999584c`;
card digest: `367befb0818bc4cf7b69eaac6d3533eb665505f7a2b5221fde28331df4171ce4`.

The previous VM was absent from live provider inventory. A replacement evaluation
VM uses the existing project authorization, a $3 session cap and a 90-minute
deadline. Local and acknowledged VM-side deletion guards are active. Historical
GPU reports remain evidence of their own versions; this run does not inherit their
quality or timing claims. Actual CUDA execution and bounded runtime handoff are recorded below. Final VM deletion is a separate lifecycle receipt; it is not claimed here.


## CUDA environment identity

The actual image is
`sha256:c8c5e458011e3bf882f44bd45df99aae3980a5de13db1564ef381346968642f7`,
built over pinned vLLM base
`sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b`.
All nineteen shipped application fingerprints matched the frozen source snapshot.
Runtime: vLLM 0.31.0, Torch 2.13.0+cu130, Transformers 5.17.0, ONNX Runtime
1.31.0, trackers 2.6.1, Supervision 0.31.0, PyAV 17.1.0 and Pillow 12.3.0.
The host has one A10080 PCIe and driver 570.195.03. These are observed run
identities rather than general minimum hardware requirements.

Mac effective configuration SHA256:
`fc87552f1bd89d94b94e6b275c6a201b43b3414606427c001d51eb161ba4bcb8`.
CUDA effective configuration SHA256:
`f8fcdde58b7b6eb0d550e63fbb7556dcf1bdad87693f89f552f989726845dec0`.
Their runtime asset paths differ. The CUDA service keeps a 16,384-token context,
one active model sequence, at most sixteen images, 1,200 visual output tokens,
a 100-second per-request limit, a 270-second analysis deadline and two legal
calls. No budget, prompt, weights or legal interpretation changed between cases.

The frozen detector SHA256 is
`c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`.
OSNet-x0.25 exported embedding weight SHA256 is
`b20223157278fbe918b945f3bb0b76c09e6fc1bf7b133a9ecdb9450443f46978`;
its public provenance manifest SHA256 is
`94e4ff696380d3c9f881864f19e80bdb2402a40c211321111e5cd415c233953b`.
The model asset manifest SHA256 is
`d6cf043a326f8cb5b1f6e31ef37c4d650f6fda342b262029c30968174431459b`.

The container runs with `--network none`, read-only public weights and no host
port publication. Both IPv4 and IPv6 outbound probes failed under the OS network
boundary. The app and resident model communicate only inside that namespace.
The normal authenticated v2 client uploads the complete source; no reference
annotations or supplied labels are present on the CUDA host. Two public synthetic
sixteen-image warmups passed before private jobs. No paid host beyond this one
was created for deployment or model comparison.


## Actual automatic smoke result

**The automatic mechanic is not established as working on this smoke set.** Its
components executed, source evidence is verifiable, and all three local API
clients finished within 300 seconds. All three results are **partial and
insufficient**, with no supported violation or whole-recording clean negative.
Integration and temporal capacity block final acceptance. Recognition accuracy
remains not evaluable without complete independent human judgments.

| Stage or boundary | Observed denominator | Result |
| --- | ---: | --- |
| Full-source CUDA decode and tracking | 3 / 3 recordings; 642 detection samples | Execution pass |
| Sparse accepted geometry anchors | 8 / 8 match at prespecified IoU ≥ 0.5; mean IoU 0.9961 | Scoped pass; biased, non-exhaustive prior proposals |
| Stable-segment anchor pairs | 0 false splits / 4 pairs | Scoped pass; no full switch/continuity metric |
| Missed/spurious people, reflections, occlusion/reappearance | 0 complete current-case references / 3 | Not evaluable |
| Qwen visual calls | 5 valid responses / 8 calls; 3 read timeouts | Partial; 8 action and 2 context observations |
| Operational-role outputs | 0 role observations / 10 observations | Role correctness and justified abstention not evaluable |
| Actor/recipient and action correctness | 10 observations cite proposed actors; 0 complete human references | Not evaluable |
| Detailed temporal windows | 2 completed / 9 scheduled | Fail coverage acceptance; all 3 timelines exhaust budget |
| Legal rule-case inventory | 2 evaluated, 4 unavailable, 30 skipped / 36 | Fail scope coverage; both returned assessments insufficient |
| Legal model calls | 2 accepted / 6 calls; 3 read timeouts; 1 actor-grounding rejection | Partial; no supported legal finding |
| API event candidates and evidence | 9 / 9 have complete export and 2–3 real JPEGs | Mechanical pass; candidate correctness not evaluable |
| Original source/JPEG/marker integrity | 3 / 3 sources, 20 / 20 distinct JPEGs, 9 / 9 markers | Pass independent hash, PTS and source re-extraction |
| Exact required v1 using new mechanic | 0 / 1 route integration boundary | Fail: v1 still dispatches legacy |
| Complete independent human correctness review | 0 / 3 | Not evaluable; 1 partial qualitative response |

The eight geometry anchors belong to only two recordings and were previously
accepted detector proposals, so they cannot estimate detector recall, false-positive
rate, full identity switches, reflection handling or physical-person counts. The
four identity comparisons stay within previously confirmed stable segments;
identity between unrelated segments is not assumed. All references were compared
only after all three predictions had been saved and locally preserved.

Only 30.733 of 106.367 source seconds lie in completed detailed-window envelopes;
75.633 seconds remain outside those envelopes. Overview calls also produced
observations, but do not complete the detailed schedule. None of the three cases
establishes continuous visibility. Eight pending reinspections and five unresolved
questions remain. No omission opportunity is certified from this sampling.

The registry contains 457 proposed entries over 465 segments; these are **not
physical-person counts**. Of the segments, 433 originate from fresh negative
unmatched tracker IDs, 436 contain a single detection sample and 429 lack an
appearance gallery. The adapter assigns a new negative ID to every unmatched
detection, and reconciliation can instantiate a participant from it. That is an
observed origin/association problem requiring investigation, even though the
limited accepted anchors matched. Geometry must remain separate from identity;
neither deleting low-confidence boxes nor inventing joins is an acceptable repair.
The independent Mac component run proposed 472 entries/481 segments on the same
642 samples; the environments are not asserted to be numerically identical.

The one rejected legal reply was valid JSON/schema, then failed the frozen
validator with the public static reason **“Actor-sensitive condition requires a
participant.”** A CPU-only replay of its saved unmodified reply, exact plan and
reconstructed evidence ownership reproduced that rejection with zero new model
calls. It is an actor/condition validation failure rather than a JSON-format
failure. Both accepted legal assessments contain only unknown conditions: twelve
unknown condition states in total. False alarms, missed events, wrong-event
reports, duplicate-versus-distinct correctness, unsupported intent/accounting
claims, and exact action onset/offset errors remain **not evaluable**.

Fourteen calls have recorded prompt counts, with a maximum of 11,207 tokens
against the 16,384-token context. No recorded call failed for context overflow.
None of the eight returned visual/legal responses ended at the output-token
limit. Six timed-out calls produced no complete validated response; they are
retained as failures, not counted as successful parsing or recognition.

## Timings and initial requirements

| Automatic case | Analysis time | Local upload/poll/result/source/evidence verification | Outcome |
| --- | ---: | ---: | --- |
| 1 | 254.546 s | 257.793 s | Partial / insufficient |
| 2 | 256.754 s | 263.827 s | Partial / insufficient |
| 3 | 254.906 s | 258.349 s | Partial / insufficient |

Across all three automatic runs: decode **15.047 s**, tracking **126.552 s**,
Qwen timeline **358.012 s**, legal evaluation **261.817 s**, total analysis
**766.206 s**. Tracking alone takes 15.397–91.433 seconds per recording.
The remaining time includes evidence export and orchestration. All three jobs
reached `done`, zero jobs failed or disappeared, but zero completed the full
inspection/legal scope. The 1 Hz GPU sampler recorded a peak of 73,531 MiB during
the preserved first-run interval; this is an observed peak, not a minimum-memory
qualification.

The 300-second metric uses a warmed API on the CUDA host and includes its actual
loopback upload plus verification. It excludes model download/cold start, WAN
file transfer and an external browser. Full remote upload-to-browser-result
latency has not been measured.

| Initial smoke requirement | Separate acceptance |
| --- | --- |
| Correctly grounded positive | Not demonstrated: 0 supported findings; independent event truth unavailable |
| Correctly handled normal | Safe uncertainty retained; correct clean-normal recognition not established |
| Reliable physical actor attribution | Not evaluable; proposed IDs and sparse anchor agreement are insufficient |
| Verifiable original source evidence | Pass: 3 sources, 20 JPEGs and 9 markers verified |
| Completion within 300 seconds | Pass 3 / 3 for local terminal API results; full-scope completion fails 0 / 3 |
| Exact required jury response from this mechanic | Fail: required v1 path does not execute it |

These cases are not successful negatives. No recognition confusion matrix or
accuracy percentage is reported. A user inspected some saved evidence and gave
favorable feedback on targeted reinspection/evidence follow-up. That is recorded
as partial qualitative feedback without promoting any geometry, identity, role,
action, event or legal scope to approved.

## Preservation and failure ownership

All three complete artifact sets were restored locally and checked against their
per-file manifests: **100, 216 and 120 checks; 436 total**. The immutable originals,
raw returned model answers, call receipts, private cache/evidence, source PTS,
configuration and histories survive outside Git. Redundant uploaded `input.mov`
bytes were reconstructed from the existing immutable local copy only after its
SHA256 matched the saved source; every restored file hash then matched.
The first unverified interrupted transfer prefix is retained separately and is
never called a complete archive. Hotspot transfers for the remaining complete
archives took approximately 11.9 and 3.0 seconds. No failed baseline was replaced.

The final local human packet index is
`~/.local/share/forte26/mechanic-validation/20261018-01/gpu-review-v4/index.html`.
It links full source playback with actual sampled tracking overlays, Qwen's
observations and cited frames, event JPEGs/source timestamps, complete rule
conditions/citations/limitations, examined/skipped coverage and separate review
scopes. Earlier packet revisions and partial feedback are retained. All 3,186
playback frames exactly preserve source-normalized PTS. Local link checks are
recorded separately; no private browser/image/screenshot tool inspected them.

Failure assignment:

- **Detection/association:** unmatched detector-origin observations become fresh
  participant proposals; complete missed/spurious/continuity quality is unknown.
- **Qwen role/actor/action interpretation:** no role observations returned;
  physical actor and action correctness await independent review.
- **Temporal/runtime capacity:** all timelines exhaust budget; six total model
  read timeouts, seven detailed windows unfinished, eight reinspections pending.
- **Legal integration:** draft plans, unknown applicability, absent authorized
  metadata evidence, insufficient call budget and one rejected actor-sensitive
  condition prevent supported scope completion.
- **Evidence/API:** v2 original evidence mechanics pass; v1 integration fails.

## Highest-impact fixes and next experiment

1. **Connect the new mechanic to the required v1 jury boundary.** Preserve exact
   serialization, original JPEGs and timestamps. Map incomplete/insufficient
   inspection to an honest terminal failure rather than `no_violation`; a
   separately supported event must survive uncertainty elsewhere.
2. **Complete legal evidence and applicability integration.** Wire real authorized
   metadata items and separately reviewed applicability/interpretation records
   into the actual evaluator. Preserve unknown when those prerequisites are
   absent. Do not approve draft cards or manufacture a recording date to make
   these three cases pass.
3. **Make the inspection plan fit measured stage costs.** Account for tracking
   cost and request latency before allocating detailed windows, reinspections
   and the scoped legal inventory. Record capacity failure explicitly when the
   270-second analysis budget cannot cover it. Investigate unmatched-detection
   identity promotion with synthetic fixtures and profile its cost; causation
   between registry size and latency has not yet been established.

Each repair needs a new source/configuration identity and a matched comparison
on the same allowed development recordings. Other lanes' subsequent source
patches are not part of this baseline and inherit none of its execution evidence.
No more development recordings were added after the repeated failures appeared.

**Next experiment:** have a second local reviewer watch each of the same three
complete source recordings first, recording scoped geometry, physical continuity,
role/action intervals, actor/recipient facts and candidate event boundaries before
revealing these saved predictions. Then compare the frozen outputs and supplied
source evidence against those judgments. Use the packet's prepared rule
conditions/exceptions/explanations; no reviewer must research legislation. This
resolves the largest remaining uncertainty—recognition correctness—without new
model calls, altered prompts, weights, labels in inference or reserved footage.

## Runtime ownership

At 00:54:11 UTC the VM was running with zero active jobs, all three backups
acknowledged, and its OS network boundary unchanged. Observed shared session
credit reduction was **$1.1758**, leaving approximately **$1.8242** of the $3 cap
before settlement. B received an explicit fixed-app-port loopback bridge and
health/public-client window ending 01:03 UTC, with rollback limited to its own
bridge/tunnel. Key material remains server-side and never enters logs/chat.
API/model restart is prohibited because the current `wait -n` supervisor would
stop both processes. No session/publication acceptance is claimed.
Useful-work stop remains **01:08 UTC**; acknowledged deletion guards remain
scheduled for **01:28:30 UTC**. A source-final candidate requires a separately
reviewed process/run identity; its status does not change this frozen baseline.
The VM is not claimed deleted in this report.
