import pytest
from test_legal import HTML, snapshot

from forte.cli import main
from forte.legal import Corpus, extract_clauses
from forte.retrieval import DenseIndex, corpus_digest, hybrid_search, rerank_hits


def fixture():
    s = snapshot()
    corpus = Corpus(sources=[s], clauses=extract_clauses(s, HTML))
    index = DenseIndex(
        corpus_sha256=corpus_digest(corpus),
        clause_ids=[c.id for c in corpus.clauses],
        vectors=[[1, 0], [1, 0], [0, 1]],
    )
    return corpus, index


def test_semantic_candidate_can_recover_a_paraphrase_without_a_word_match():
    corpus, index = fixture()
    assert corpus.search("synthetic paraphrase") == []
    hits = hybrid_search(corpus, index, "synthetic paraphrase", [0, 1])
    assert hits[0]["clause"]["provision"] == "22"
    assert "До завершения" in hits[0]["clause"]["text"]
    assert hits[0]["dense_similarity"] == 1
    assert hybrid_search(corpus, index, "пункт 20", [0, 1])[0]["clause"]["provision"] == "20"


def test_changed_corpus_missing_clauses_or_invalid_vectors_are_rejected():
    corpus, index = fixture()
    index.corpus_sha256 = "0" * 64
    with pytest.raises(ValueError, match="corpus"):
        hybrid_search(corpus, index, "query", [0, 1])
    _, index = fixture()
    index.clause_ids.pop()
    with pytest.raises(ValueError):
        hybrid_search(corpus, index, "query", [0, 1])
    with pytest.raises(ValueError):
        DenseIndex(corpus_sha256="0" * 64, clause_ids=["x"], vectors=[[float("nan"), 0]])


def test_dense_cli_requires_a_local_model_and_matching_index(tmp_path, capsys):
    assert (
        main(
            [
                "legal-search",
                "--release",
                str(tmp_path),
                "--query",
                "synthetic",
                "--embedding-model",
                str(tmp_path),
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert not output.out and "invalid" in output.err


def test_reranker_reorders_relevant_candidates_and_can_reject_all_candidates():
    corpus, index = fixture()
    hits = hybrid_search(corpus, index, "synthetic paraphrase", [1, 0])
    ranked = rerank_hits("synthetic paraphrase", hits, lambda q, texts: [-5, 3])
    assert len(ranked) == 1 and ranked[0]["clause"] == hits[1]["clause"]
    assert rerank_hits("unrelated", hits, lambda q, texts: [-5, -3]) == []
    with pytest.raises(ValueError, match="scores"):
        rerank_hits("query", hits, lambda q, texts: [float("nan"), 1])
