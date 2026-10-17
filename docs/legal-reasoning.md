# Local official-law evidence and condition evaluation

`forte.legal_reasoning.LegalEvidenceService` connects the preserved official-law
release to the frozen local visual reasoning path. It verifies the existing
receipts and reconstructs the corpus before use. Inference performs no network
requests, law refresh, model download, optimizer step or weight update.

The legacy detector and its three preliminary rules remain available. The new
path produces a separate, versioned assessment record; it does not silently map
missing context or skipped rules to the legacy binary clean result.

## Corpus audit

The pinned `legal/2026-10-17` release contains these scoped official acts:

| Official act | Pinned edition ID | Main records |
| --- | --- | ---: |
| [NBRK Resolution 231, V1900019680](https://adilet.zan.kz/rus/docs/V1900019680) | `c4cd4052-63e3-475b-ba9e-93f23de13fdb` | 154 |
| [NBRK Resolution 14, V2000020075](https://adilet.zan.kz/rus/docs/V2000020075) | `4bd1c354-b40c-4b38-ab7d-53aaa7b4f39c` | 24 |
| [NBRK Resolution 49, V1900018545](https://adilet.zan.kz/rus/docs/V1900018545) | `0d776d3e-1c76-40f2-90ea-64f6de7868dc` | 94 |

There are 272 main records, 266 after excluding repealed records. The twelve
derived operational cards remain drafts; zero are approved. These counts do not
establish 272 implemented detectors, full Kazakhstan-law coverage, or legal-match
accuracy. Annexes and forms remain in hashed raw HTML rather than the numbered
main-provision index. Other referenced acts remain explicit retrieval gaps.

The audit checks enacted-act metadata in addition to the official HTTPS origin.
Only `adilet.zan.kz` and `nationalbank.kz` are accepted authority origins; news,
drafts and commentary are rejected even on those hosts. Redirects through other
origins and unverified subdomains are rejected by `require_official_act`.
`load_release` currently ingests the existing Adilet receipt format only. The
National Bank origin policy does not claim a new National Bank collector exists.

An October 18 public-text check found temporal suspension/replacement notices for
Resolution 14 clauses 11, 13(3), 14 and 16 through January 1, 2027. They already
exist in the preserved source HTML, but the legacy main-clause extractor omits
their `<font>` blocks. The new exact-source tool restores them separately as
`source_effect_notices`; it preserves the original release and its fingerprints.
It returns linked but unavailable amending text explicitly. The ordinary public
page for Resolution 231 returned an empty navigation shell during this check;
that response was not accepted as a refreshed source. Resolution 49's public text
was readable. None of these checks replaced the pinned release or independently
certified present-day applicability.

Imported `adoption_date` fields differ from dates written in the official act
names. Both are preserved in `audit()`. Do not resolve that discrepancy by
treating `revision_date_raw`, `end_date`, retrieval time or source PTS as an
effective-date boundary. The source's current flag describes collection-time
publisher metadata, not the edition applicable to an undated recording.

## Local evidence tools

```python
from pathlib import Path
from forte.legal_reasoning import LegalEvidenceService

law = LegalEvidenceService(Path("legal/2026-10-17"), Path("legal/rule-cards.json"))
hits = law.retrieve_applicable_rules("пункт 22", {"act_ids": ["V1900019680"]}, event_date=None)
source = law.get_source_provision("V1900019680", "c4cd4052-63e3-475b-ba9e-93f23de13fdb", "22")
```

Retrieval retains deterministic BM25 and exact provision selectors. Existing
optional local BGE-M3/reranker experiments remain documented in
[the retrieval guide](legal-and-annotation.md); this service does not claim a
new semantic-retrieval quality improvement. Scores rank candidates, not violation
probabilities. Empty retrieval is an unavailable match, not evidence of legality.

Exact lookup requires an available act, edition and provision. Context includes
parent headings, complete neighboring provisions, collected definitions,
available exact referenced clauses, temporal notices and unresolved reference
URLs. An unavailable reference is never filled with model recollection.
`snapshot_sha256` binds the reconstructed corpus; the separate
`rule_cards_sha256` identifies the interpretation inventory. Each condition plan
also has its own fingerprint.

An event date requires an explicit reliable source: recording metadata,
authorized operation metadata, or human review. Date filtering remains unknown
unless the caller separately supplies reviewed `VersionApplicability` bindings
with effective intervals, a reviewer and available official authority IDs.
These are application configuration, never VLM output. Structural validation does
not authenticate a reviewer or prove that their interpretation is correct.

## Explicit condition logic

`prepare_card` creates an application-owned plan. Each condition states a
proposition, category, and `violation_when` polarity. A proposition that the
required action occurred defeats an omission claim when its polarity requires
`contradicted`. Legacy card prerequisites are already worded as violation
conditions; exceptions must be contradicted. Scope, role, sequence, edition,
nonvisual prerequisites and complete-opportunity requirements remain separate.

The model may propose only supplied participant, frame, observation and official
provision IDs. It cannot return an approval field or choose a final assessment.
`evaluate_candidate` rejects invented IDs, mixed source ownership, inconsistent
duty-holders, incomplete/duplicate condition tables, rejected evidence and
unsupported known states. Role claims require repeated source-frame support.
Contradictory evidence and unresolved dependencies force the affected condition
to unknown. Missing-step findings additionally require application-established
complete visibility; ordinary sparse timeline samples do not supply it.
Authorization and other nonvisual conditions require explicit authorized
metadata, which can be passed as `metadata_evidence`.

The application computes:

- `supported_violation`: every decisive condition has the required polarity and
  the separately reviewed interpretation and edition permit the inference.
- `no_violation_observed`: within the assessed rule and evidence scope, the
  known conditions defeat the hypothesized violation.
- `insufficient_evidence`: a decisive condition, date, edition or interpretation
  remains unresolved.
- `not_applicable`: supported scope, role, exception or edition evidence defeats
  applicability.

All machine assessments retain `review_status: unreviewed` and
`validated_legal_conclusion: false`. A draft interpretation can retain a
`candidate_assessment: supported_violation` for review, but its exported
`assessment` remains `insufficient_evidence`. A valid JSON object never approves
its own facts, person continuity, geometry or legal interpretation.

## Integrated inference and persistence

`law.evaluate_timeline(timeline, registry, backend, output, deadline, ...)` makes
actual local `backend.request` calls with original source-frame references and
JPEGs. It prioritizes observation-triggered provisions, then checks untriggered
cards from the scoped inventory in the reverse direction. Every card receives
an evaluated, unavailable or skipped coverage entry. The default six-call budget
does not cover all twelve cards; exhaustion is explicit. Participant embeddings
and appearance galleries are excluded from the legal prompt.

The private output contains model replies, call receipts, the legal snapshot and
plan fingerprints, complete condition records, participant associations,
contrary evidence, original frame IDs, source-derived evidence envelopes,
official URLs and unresolved limitations. Evidence envelopes are not asserted
action-onset/offset precision. Paths inside this Git checkout are rejected by the
private artifact helper. Case-bearing outputs must remain in the authorized
environment with outbound networking blocked.

Verification:

```sh
uv run pytest -q tests/test_legal_reasoning.py tests/test_legal.py tests/test_retrieval.py
uv run ruff check src/forte/legal_reasoning.py tests/test_legal_reasoning.py
```

These tests verify official-source policy, raw-notice recovery, date limitations,
predicate polarity, contradiction handling, role consistency, provenance gates,
and the real image/request interface with a synthetic response. They do not
measure private-video recognition, legal precision/recall or representative 27B
quality. Frozen real-development inference and independent review remain the
evidence required for those claims.
