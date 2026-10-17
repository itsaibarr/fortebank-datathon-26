import hashlib
import json
import shutil
from pathlib import Path

import pytest

from forte.cli import main
from forte.legal import load_release

RELEASE = Path(__file__).resolve().parents[1] / "legal/2026-10-17"


def test_offline_release_verifies_and_cli_retrieves_a_cited_clause(capsys):
    corpus = load_release(RELEASE)
    assert len(corpus.sources) == 3
    assert len(corpus.clauses) == 272
    assert (
        main(
            [
                "legal-search",
                "--release",
                str(RELEASE),
                "--act",
                "V1900019680",
                "--query",
                "пункт 22",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    hit = json.loads(capsys.readouterr().out)[0]
    assert hit["clause"]["provision"] == "22"
    assert hit["clause"]["url"].startswith("https://adilet.zan.kz/rus/docs/V1900019680#")
    assert hit["source"]["sha256"] == hit["clause"]["source_sha256"]


def test_changed_raw_text_or_recompiled_invention_is_rejected(tmp_path):
    release = tmp_path / "release"
    shutil.copytree(RELEASE, release)
    source = next(release.glob("*/*/source.html"))
    original = source.read_bytes()
    source.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="SHA256"):
        load_release(release)
    source.write_bytes(original)
    corpus_path = release / "corpus.json"
    corpus = json.loads(corpus_path.read_text())
    corpus["clauses"][0]["text"] = "Invented duty"
    corpus_path.write_text(json.dumps(corpus, ensure_ascii=False))
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["corpus_sha256"] = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="reconstruct"):
        load_release(release)


def test_missing_or_unsafe_release_fails_cli_without_printing_content(tmp_path, capsys):
    assert main(["legal-search", "--release", str(tmp_path), "--query", "пункт 22"]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert "invalid" in output.err
