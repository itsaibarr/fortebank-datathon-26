import hashlib

import pytest

from forte.legal import Corpus, Snapshot, extract_clauses

HTML = """<article>
<p id="order1">1. Утвердить Правила.</p>
<h3 id="rules">Правила синтетических операций</h3>
<h3 id="chapter1">Глава 1. Общие положения</h3>
<p id="p1">1. Термины: клиент получает услугу.</p>
<h3>Глава 2. Кассовые операции</h3>
<h3>Параграф 2. Прием наличных денег</h3>
<p id="p20">20. Деньги пересчитываются в присутствии клиента.</p>
<p>Исключение: применяется дополнительное условие.</p>
<p class="note">Сноска. Пункт изменен.</p>
<p id="p22">22. Кассовому работнику запрещено покидать рабочее место.</p>
<p>До завершения обслуживания клиента.</p>
<table><tr><td>Приложение 1<br>к Правилам</td></tr></table>
<p>1. Поле формы, а не пункт основных Правил.</p>
</article>"""


def snapshot(html=HTML, url="https://adilet.zan.kz/rus/docs/V1900019680"):
    return Snapshot(
        act_id="V1900019680",
        version_id="synthetic-version",
        official_url=url,
        retrieved_at="2026-10-17T12:00:00Z",
        revision_date_raw="2026-07-11T18:00:00Z",
        is_current=True,
        title="Synthetic legal fixture",
        sha256=hashlib.sha256(html.encode()).hexdigest(),
    )


def test_clauses_retain_scope_exceptions_and_source_anchors():
    clauses = extract_clauses(snapshot(), HTML)
    assert [c.provision for c in clauses] == ["1", "20", "22"]
    clause = clauses[1]
    assert clause.url.endswith("#p20")
    assert clause.headings[-1] == "Параграф 2. Прием наличных денег"
    assert "Исключение" in clause.text
    assert "Сноска" in clause.text
    assert "Поле формы" not in clauses[-1].text


def test_source_hash_or_misleading_domain_cannot_be_accepted():
    with pytest.raises(ValueError, match="SHA256"):
        extract_clauses(snapshot(), HTML + "changed")
    with pytest.raises(ValueError, match="official"):
        snapshot(url="https://adilet.zan.kz.evil.example/rus/docs/V1900019680")
    with pytest.raises(ValueError, match="official"):
        snapshot(url="https://adilet.kz/rus/docs/V1900019680")


def test_welcome_shell_and_duplicate_main_provisions_are_rejected():
    shell = '<html><script src="app.js"></script><div id="root"></div></html>'
    with pytest.raises(ValueError, match="legal clauses"):
        extract_clauses(snapshot(shell), shell)
    duplicate = HTML.replace('<p id="p22">22.', '<p id="p22">20.')
    with pytest.raises(ValueError, match="Duplicate"):
        extract_clauses(snapshot(duplicate), duplicate)


def test_retrieval_returns_whole_scope_and_exact_provision_without_inventing_a_match():
    source = snapshot()
    corpus = Corpus(sources=[source], clauses=extract_clauses(source, HTML))
    hits = corpus.search("кассовому работнику покидать рабочее место", limit=2)
    assert hits[0]["clause"]["provision"] == "22"
    assert "До завершения" in hits[0]["clause"]["text"]
    assert "Прием" in hits[0]["clause"]["headings"][-1]
    assert corpus.search("пункт 20", act_id=source.act_id)[0]["clause"]["provision"] == "20"
    assert corpus.search("unrelatedtermwithnomatch") == []


def test_old_versions_and_tampered_corpus_cannot_enter_default_retrieval():
    source = snapshot().model_copy(update={"is_current": False})
    corpus = Corpus(sources=[source], clauses=extract_clauses(source, HTML))
    assert corpus.search("пункт 22") == []
    assert corpus.search("пункт 22", include_historical=True)
    clauses = extract_clauses(snapshot(), HTML)
    clauses[0].source_sha256 = "0" * 64
    with pytest.raises(ValueError, match="source"):
        Corpus(sources=[snapshot()], clauses=clauses)


def test_corrupt_clause_ids_and_repealed_text_are_excluded():
    html = HTML.replace("22. Кассовому", "22. Исключен. Кассовому")
    corpus = Corpus(sources=[snapshot(html)], clauses=extract_clauses(snapshot(html), html))
    assert corpus.search("пункт 22") == []
    clauses = extract_clauses(snapshot(), HTML)
    with pytest.raises(ValueError, match="Duplicate"):
        Corpus(sources=[snapshot()], clauses=clauses + [clauses[0]])


def test_unwrapped_repeal_notes_are_retained_without_becoming_live_rules():
    html = HTML.replace(
        '<p id="p22">',
        '<span class="note"><a name="p21"></a>21. Исключен постановлением.</span><br><p id="p22">',
    )
    clauses = extract_clauses(snapshot(html), html)
    assert next(c for c in clauses if c.provision == "21").repealed
    corpus = Corpus(sources=[snapshot(html)], clauses=clauses)
    assert corpus.search("пункт 21") == []
