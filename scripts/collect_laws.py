"""Collect a new immutable official-text release; never run during video inference."""

import argparse
import datetime as dt
import hashlib
import json
import re
import tempfile
from pathlib import Path

import httpx

from forte.legal import Corpus, Snapshot, extract_clauses

BASE = "https://adilet.zan.kz/api/documents"
ACTS = ["V1900019680", "V2000020075", "V1900018545"]


def collect(acts, output, client):
    if output.exists() or len(set(acts)) != len(acts) or not 1 <= len(acts) <= 10:
        raise ValueError("Use a new release directory and 1–10 distinct act IDs")
    if any(not re.fullmatch(r"V\d{10}", act) for act in acts):
        raise ValueError("Invalid act ID")
    output.parent.mkdir(parents=True, exist_ok=True)
    sources, clauses, receipts = [], [], []

    def fetch(url):
        response = client.get(url)
        response.raise_for_status()
        if len(response.content) > 5 * 1024**2:
            raise ValueError("Official response exceeds the collection limit")
        return response, response.json()

    with tempfile.TemporaryDirectory(prefix="law-release-", dir=output.parent) as temporary:
        root = Path(temporary)
        for act in acts:
            meta_response, meta = fetch(f"{BASE}/by-ngr/{act}?language=rus")
            meta = meta.get("document", meta)
            id = meta["id"]
            if not re.fullmatch(r"[0-9a-f-]{36}", id) or meta["group_number"] != act:
                raise ValueError("Official response does not match requested act")
            versions_response, versions = fetch(f"{BASE}/{id}/versions?page=1&page_size=500")
            if versions["total_count"] != len(versions["versions"]):
                raise ValueError("Incomplete version inventory")
            current = [v for v in versions["versions"] if v.get("is_current")]
            if (
                len(current) != 1
                or current[0]["document_id"] != id
                or meta.get("is_actual") is not True
                or meta.get("status") not in {"new", "upd"}
            ):
                raise ValueError("Current official version is unresolved")
            content_response, content = fetch(f"{BASE}/{id}/content")
            html = content["text_content"]
            if content["document_id"] != id or meta.get("text_content", html) != html:
                raise ValueError("Content does not match official metadata/version")
            source = Snapshot(
                act_id=act,
                version_id=id,
                title=meta["title_ru"],
                official_url=f"https://adilet.zan.kz/rus/docs/{act}",
                retrieved_at=dt.datetime.now(dt.UTC).isoformat(),
                revision_date_raw=current[0]["revision_date"],
                is_current=True,
                sha256=hashlib.sha256(html.encode()).hexdigest(),
            )
            extracted = extract_clauses(source, html)
            if len(extracted) < 10:
                raise ValueError("Unexpectedly incomplete legal text")
            directory = root / act / id
            directory.mkdir(parents=True)
            (directory / "source.html").write_text(html)
            responses = {
                "metadata": meta_response,
                "versions": versions_response,
                "content": content_response,
            }
            hashes = {}
            for name, response in responses.items():
                (directory / f"{name}.json").write_bytes(response.content)
                hashes[f"{name}.json"] = hashlib.sha256(response.content).hexdigest()
            hashes["source.html"] = source.sha256
            receipts.append(
                {
                    "snapshot": source.model_dump(),
                    "sha256": hashes,
                    "main_clause_records": len(extracted),
                    "annexes": "preserved in raw source, not main-clause records",
                }
            )
            sources.append(source)
            clauses.extend(extracted)
        corpus = Corpus(sources=sources, clauses=clauses)
        raw = (corpus.model_dump_json(indent=2) + "\n").encode()
        (root / "corpus.json").write_bytes(raw)
        manifest = {
            "schema_version": 1,
            "corpus_sha256": hashlib.sha256(raw).hexdigest(),
            "sources": receipts,
            "coverage": "three scoped seed acts, not all RK law",
            "date_semantics": "revision_date_raw is publisher metadata; end_date is not "
            "interpreted as an effective-until date",
            "rule_cards_reviewed": False,
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        Path(temporary).rename(output)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--act", action="append")
    args = parser.parse_args()
    with httpx.Client(timeout=35, follow_redirects=False, trust_env=False) as client:
        result = collect(args.act or ACTS, args.output, client)
    print(
        json.dumps(
            {
                "acts": len(result["sources"]),
                "clauses": sum(s["main_clause_records"] for s in result["sources"]),
                "output": str(args.output),
            }
        )
    )
