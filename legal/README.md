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

Default retrieval uses deterministic lexical BM25 and exact provision lookup,
retaining complete main clauses, parent headings and linked references. Opt-in
local BGE-M3 dense fusion and BGE reranking are implemented and measured, with
quality gaps described in [the review guide](../docs/legal-and-annotation.md).
Automatic cross-reference expansion and completeness certification remain open.
An applicable rule and a visible fact must be established separately. Search
results are legal text, never a video finding; empty retrieval is abstention. The
legacy three-rule production pipeline is not replaced by this experimental corpus.

Build the 266-clause dense index inside the existing pinned model runtime, with
networking disabled and public model snapshots downloaded beforehand:

```sh
python scripts/prepare_legal_index.py --release legal/2026-10-17 \
  --model /models/5617a9f61b028005a4858fdac845db406aefb181 \
  --reranker /models/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e \
  --cases legal/retrieval-cases.json --output /output/law-index --device cuda
```

The corresponding `forte legal-search` flags are `--dense-index`,
`--embedding-model`, `--reranker-model` and `--embedding-device cpu|cuda`. Both
models load local files only, with remote code disabled. This optional path needs
the model runtime's Torch/Transformers; default lexical search works in the
lightweight uv environment. The tested runtime is vLLM 0.31.0 / Torch 2.13.0+cu130 /
Transformers 5.17.0 in the image pinned by `Dockerfile`. Encoder model
`BAAI/bge-m3` is MIT; reranker `BAAI/bge-reranker-v2-m3` is Apache-2.0. The dense
floor 0.35 and reranker raw-logit floor zero are development settings, not
calibrated applicability probabilities.

Prepare another immutable release explicitly, outside inference:

```sh
uv run python scripts/collect_laws.py --output legal/YYYY-MM-DD
```

The collector uses the same unauthenticated by-NGR, content and versions endpoints
as the official public website. It refuses incomplete version inventories,
unresolved current status, content mismatches, shells and overwritten releases.
Hashes establish local integrity, not an independent government signature.
