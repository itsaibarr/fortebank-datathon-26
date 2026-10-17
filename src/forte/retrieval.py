"""Local BGE-M3 dense retrieval fused with the verified lexical index."""

import hashlib
import math
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from forte.legal import Corpus

BGE_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"


def corpus_digest(corpus):
    return hashlib.sha256(corpus.model_dump_json().encode()).hexdigest()


def live_clauses(corpus):
    current = {(s.act_id, s.version_id) for s in corpus.sources if s.is_current}
    return [c for c in corpus.clauses if not c.repealed and (c.act_id, c.version_id) in current]


class DenseIndex(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    model: Literal["BAAI/bge-m3"] = "BAAI/bge-m3"
    revision: Literal["5617a9f61b028005a4858fdac845db406aefb181"] = BGE_REVISION
    pooling: Literal["normalized_cls"] = "normalized_cls"
    corpus_sha256: str
    clause_ids: list[str]
    vectors: list[list[float]]

    @model_validator(mode="after")
    def shape_and_norms(self):
        if not self.vectors or len(self.clause_ids) != len(self.vectors):
            raise ValueError("Dense index rows and clause IDs must match")
        if len(set(self.clause_ids)) != len(self.clause_ids):
            raise ValueError("Duplicate dense clause ID")
        size = len(self.vectors[0])
        for row in self.vectors:
            if len(row) != size or size < 2 or abs(sum(x * x for x in row) - 1) > 0.001:
                raise ValueError("Dense vectors must have consistent size and unit norm")
        return self


def hybrid_search(corpus: Corpus, index: DenseIndex, query, vector, *, act_id=None, limit=5):
    index = DenseIndex.model_validate(index.model_dump())
    clauses = live_clauses(corpus)
    if index.corpus_sha256 != corpus_digest(corpus) or set(index.clause_ids) != {
        c.id for c in clauses
    }:
        raise ValueError("Dense index does not match verified corpus")
    if not 1 <= limit <= 20 or not query.strip():
        raise ValueError("Use a nonempty query and limit 1–20")
    # Provision numbers are authoritative selectors; semantic similarity cannot override them.
    if re.search(r"(?:пункт(?:а|у|ом)?|п\.|§)\s*\d", query, re.I):
        return corpus.search(query, act_id=act_id, limit=limit)
    if len(vector) != len(index.vectors[0]) or not all(math.isfinite(x) for x in vector):
        raise ValueError("Invalid query embedding")
    norm = math.sqrt(sum(x * x for x in vector))
    if not norm:
        raise ValueError("Empty query embedding")
    vector = [x / norm for x in vector]
    by_id = {c.id: c for c in clauses if not act_id or c.act_id == act_id}
    dense = sorted(
        [
            (id, sum(x * y for x, y in zip(row, vector, strict=True)))
            for id, row in zip(index.clause_ids, index.vectors, strict=True)
            if id in by_id
        ],
        key=lambda row: (-row[1], row[0]),
    )
    # A fixed development floor, not a calibrated relevance or compliance probability.
    dense = [(id, similarity) for id, similarity in dense[:20] if similarity >= 0.35]
    lexical = corpus.search(query, act_id=act_id, limit=20)
    lexical_ids = [
        f"{h['clause']['act_id']}:{h['clause']['version_id']}:{h['clause']['provision']}"
        for h in lexical
    ]
    scores = {}
    for ranking in [lexical_ids, [id for id, _ in dense]]:
        for rank, id in enumerate(ranking, start=1):
            scores[id] = scores.get(id, 0) + 1 / (60 + rank)
    sources = {(s.act_id, s.version_id): s for s in corpus.sources}
    similarities = dict(dense)
    return [
        {
            "score": scores[id],
            "clause": by_id[id].model_dump(),
            "source": sources[(by_id[id].act_id, by_id[id].version_id)].model_dump(),
            "dense_similarity": similarities.get(id),
            "retrieval": "BM25+dense RRF",
            "interpretation": "retrieved legal text, not a video finding",
        }
        for id in sorted(scores, key=lambda id: (-scores[id], id))[:limit]
    ]


class LocalBGE:
    """Use the existing GPU runtime's Torch/Transformers, never a remote inference API."""

    def __init__(self, path: Path, device="cpu"):
        if path.name != BGE_REVISION or not path.is_dir():
            raise ValueError("Mount the pinned BGE-M3 snapshot directory")
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch, self.device = torch, device
        self.tokenizer = AutoTokenizer.from_pretrained(
            path, local_files_only=True, trust_remote_code=False
        )
        self.model = (
            AutoModel.from_pretrained(
                path,
                local_files_only=True,
                trust_remote_code=False,
                weights_only=True,
            )
            .to(device)
            .eval()
        )

    def encode(self, texts):
        result = []
        for text in texts:
            inputs = self.tokenizer(text, return_tensors="pt", truncation=False)
            if inputs["input_ids"].shape[1] > 8192:
                raise ValueError("Clause exceeds embedding context; hierarchical split required")
            with self.torch.inference_mode():
                output = self.model(**{k: v.to(self.device) for k, v in inputs.items()})
                vector = self.torch.nn.functional.normalize(
                    output.last_hidden_state[:, 0], p=2, dim=1
                )
            result.append(vector[0].float().cpu().tolist())
        return result


def rerank_hits(query, hits, scorer, *, limit=5):
    if not 1 <= limit <= 20:
        raise ValueError("Use a limit 1–20")
    if not hits or re.search(r"(?:пункт(?:а|у|ом)?|п\.|§)\s*\d", query, re.I):
        return hits[:limit]
    scores = scorer(
        query, ["\n".join(h["clause"]["headings"]) + "\n" + h["clause"]["text"] for h in hits]
    )
    if len(scores) != len(hits) or not all(math.isfinite(s) for s in scores):
        raise ValueError("Invalid reranker scores")
    # Raw logit zero is a fixed development floor, not a calibrated legal probability.
    ranked = [
        dict(hit, reranker_logit=score)
        for hit, score in zip(hits, scores, strict=True)
        if score >= 0
    ]
    return sorted(ranked, key=lambda h: (-h["reranker_logit"], h["clause"]["url"]))[:limit]


class LocalReranker:
    def __init__(self, path: Path, device="cpu"):
        if path.name != RERANKER_REVISION or not path.is_dir():
            raise ValueError("Mount the pinned BGE reranker snapshot directory")
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch, self.device = torch, device
        self.tokenizer = AutoTokenizer.from_pretrained(
            path, local_files_only=True, trust_remote_code=False
        )
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(
                path,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
            )
            .to(device)
            .eval()
        )

    def score(self, query, passages):
        scores = []
        for passage in passages:
            inputs = self.tokenizer(query, passage, return_tensors="pt", truncation=False)
            if inputs["input_ids"].shape[1] > 8192:
                raise ValueError("Clause exceeds reranker context; hierarchical split required")
            with self.torch.inference_mode():
                result = self.model(**{k: v.to(self.device) for k, v in inputs.items()})
            scores.append(float(result.logits.float().reshape(-1)[0]))
        return scores
