"""Build and measure a public-law dense index inside the offline model runtime."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from forte.legal import load_release
from forte.retrieval import DenseIndex, LocalBGE, corpus_digest, hybrid_search, live_clauses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new index directory")
    corpus = load_release(args.release)
    start = time.perf_counter()
    encoder = LocalBGE(args.model, args.device)
    clauses = live_clauses(corpus)
    index = DenseIndex(
        corpus_sha256=corpus_digest(corpus),
        clause_ids=[c.id for c in clauses],
        vectors=encoder.encode(["\n".join(c.headings) + "\n" + c.text for c in clauses]),
    )
    build_seconds = time.perf_counter() - start
    cases = json.loads(args.cases.read_text())["cases"]
    vectors = encoder.encode([c["query"] for c in cases])
    rows = []
    for case, vector in zip(cases, vectors, strict=True):
        hits = hybrid_search(corpus, index, case["query"], vector, act_id=case["act_id"], limit=3)
        provisions = [h["clause"]["provision"] for h in hits]
        expected = case["expected_provision"]
        rows.append(
            {
                "case_id": case["id"],
                "retrieved": provisions,
                "rank": provisions.index(expected) + 1 if expected in provisions else None,
                "no_match_correct": not hits if expected is None else None,
            }
        )
    report = {
        "model": index.model,
        "revision": index.revision,
        "pooling": index.pooling,
        "dimensions": len(index.vectors[0]),
        "indexed_clauses": len(clauses),
        "build_seconds": build_seconds,
        "device": args.device,
        "positive_queries": sum(c["expected_provision"] is not None for c in cases),
        "top1_hits": sum(r["rank"] == 1 for r in rows),
        "top3_hits": sum(r["rank"] is not None for r in rows),
        "negative_queries": sum(c["expected_provision"] is None for c in cases),
        "negative_passes": sum(r["no_match_correct"] is True for r in rows),
        "torch": encoder.torch.__version__,
        "results": rows,
        "limitations": [
            "Small agent-prepared development query set, not independent QA.",
            "Fixed uncalibrated dense floor 0.35; similarity is not applicability.",
            "No reranker, automatic cross-reference expansion or legal adjudication.",
        ],
    }
    args.output.mkdir(parents=True)
    raw = (index.model_dump_json() + "\n").encode()
    (args.output / "index.json").write_bytes(raw)
    report["index_sha256"] = hashlib.sha256(raw).hexdigest()
    (args.output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"results", "limitations"}}))


if __name__ == "__main__":
    main()
