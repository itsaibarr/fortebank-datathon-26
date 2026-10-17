# Offline official-law releases

`2026-10-17/` preserves three scoped seed acts from the official Adilet public API:

| Act | Subject | Main clause records |
|---|---|---:|
| V1900019680, NBK Resolution 231 | Cash operations and collection | 154 |
| V2000020075, NBK Resolution 14 | Security and premises | 24 |
| V1900018545, NBK Resolution 49 | Cash foreign-exchange operations | 94 |

272 records include six repealed provisions, which default retrieval excludes.
Annexes, forms, amendment notes and the enacting orders are preserved in full raw
HTML, but annex/form fields are not indexed as main provisions. This is a scoped
starting inventory, not a completeness claim for Kazakhstan law or video duties.

Each release contains the official metadata, version inventory, HTML response and
raw HTML, their SHA256 receipts, and an index reconstructed from that HTML. The
current-version flag and raw revision timestamp come from the official version
inventory. Metadata `end_date` is not treated as an expiry date. Historical
applicability to a recording date still requires explicit review; the recording
date is not established by the filename or by this release's date.

Search verifies all receipts and reconstructs the index without Internet access:

```sh
uv run forte legal-search --release legal/2026-10-17 \
  --act V1900019680 --query 'пункт 22' --limit 1
```

The first retrieval slice uses deterministic lexical BM25 and exact provision
lookup, retaining complete main clauses, parent headings and linked references.
It does not yet resolve cross-references, embed/rerank, or certify completeness.
An applicable rule and a visible fact must be established separately. Search
results are legal text, never a video finding. The legacy three-rule production
pipeline is not silently replaced by this experimental corpus.

Prepare another immutable release explicitly, outside inference:

```sh
uv run python scripts/collect_laws.py --output legal/YYYY-MM-DD
```

The collector uses the same unauthenticated by-NGR, content and versions endpoints
as the official public website. It refuses incomplete version inventories,
unresolved current status, content mismatches, shells and overwritten releases.
Hashes establish local integrity, not an independent government signature.
