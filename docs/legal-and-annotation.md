# Local law retrieval and two-layer review

The first implementation preserves three official acts, 272 main-clause records,
their full raw texts and version inventories. Six repealed records are excluded
from default retrieval. See [the corpus guide](../legal/README.md) and the complete
[coverage register](../legal/coverage-2026-10-17.json). Every collected clause has
an entry; most remain unreviewed for video observability. This is not an exhaustive
inventory of applicable Kazakhstan law. Annexes and cross-referenced acts remain
explicit coverage gaps.

[Twelve operational cards](../legal/rule-cards.json) reference thirteen collected
clauses. They separate acceptance, payout, cash processing, collection handoffs,
exchange offices and premises construction. All are agent-prepared drafts. No
legal reviewer has approved them, and they are not supervised violation labels.

Several distinctions prevent predictable false reports:

- Resolution 231 point 22 sits in cash acceptance. Establish that phase, the
  cashier role, continuity and unfinished service before relating a departure to
  it. A customer departure cannot satisfy the cashier predicate.
- Point 32 permits packaging/label-based payout methods in specified conditions.
  That qualification does not waive point 31's client-presence requirement.
- Point 42 expressly excepts client cash acceptance and payout from its
  controlling-employee condition.
- Resolution 14 point 16 requires a lockable cash-room door. An open door does not
  establish that it is not lockable or that the cited point requires it always shut.
- Document issuance, authenticity checks, authorization and internal procedures
  may need context that a camera cannot establish.

`forte legal-search` verifies the raw-file receipts and reconstructs the index
before offline lexical retrieval. Optional pinned BGE-M3 embeddings and a local
BGE reranker can be enabled explicitly. All modes return full clauses, parent
headings, references, official anchors, snapshot identifiers and revision metadata.
Legal matching does not establish a visual fact. Automatic cross-reference
expansion, as-of-date legal resolution and broad independent retrieval evaluation
remain open.

The small agent-prepared public-law pilot has fourteen relevant queries and one
unrelated query. Lexical retrieval finds the expected clause first in 8/14 and in
the top three in 10/14. Dense fusion reaches 8/14 and 11/14 but fails the unrelated
query. Adding reranking reaches 10/14 first, 10/14 top three and rejects the
unrelated query. The fixed rejection floor also removes a relevant departure
paraphrase. These results are a baseline with precision/recall tradeoffs, not a
production acceptance result. Expected clause labels themselves need independent
review, particularly ambiguous transaction-context queries. Never interpret an
empty search as `no_violation` or as proof that no public duty exists.

The local dense index covers the 266 non-repealed collected clauses. The index is
hash-bound to the verified corpus, saved outside Git and rebuildable from the
preparation script. Both text models ran offline in the pinned GPU image. No text
model weights or CUDA dependencies were installed into the lightweight Mac uv
environment. See the [experiment receipt](../.context/verify/legal-hybrid-experiments-20261017.json).

`forte.annotations.Annotation` separates source-bound visual facts from legal
claims. Facts have anonymous actor IDs, roles/actions/context, intervals, source
frame IDs, continuity and individual review states. Legal claims assess every
rule-card prerequisite and exception, including unknowns. They can remain
unresolved even when a visible action is confirmed. Resolved claims require an
approved card, named reviewer, confirmed supporting facts and the correct actor
role. An unknown prerequisite cannot become a supported violation.

```sh
uv run forte annotations-check --release legal/2026-10-17 \
  --cards legal/rule-cards.json --file /private/path/annotation.json
```

The command emits counts and structural validity only. Structural validation
does not prove that a reviewer field is authentic, that the model saw the action
correctly, or that a legal interpretation is correct. Human review remains a
separate process. Private facts, descriptions, frames and model outputs stay
outside the repository. The changing legal corpus remains outside model weights.

The legacy production pipeline still uses its old three provisional rules. These
new contracts and corpus are experimental preparation, not a promoted detector.
Promote a revised pipeline only after reference facts, applicability and measured
quality justify it. No training is enabled by creating these files.
