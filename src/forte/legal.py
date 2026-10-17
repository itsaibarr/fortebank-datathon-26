"""Versioned official legal text; retrieval never establishes a video fact."""

import hashlib
import json
import math
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    act_id: str
    version_id: str
    official_url: str
    retrieved_at: str
    revision_date_raw: str
    is_current: bool
    title: str
    sha256: str

    @field_validator("official_url")
    @classmethod
    def official_source(cls, value):
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.hostname not in {"adilet.zan.kz", "www.adilet.zan.kz", "nationalbank.kz"}
            or url.username
            or url.password
            or url.port not in {None, 443}
        ):
            raise ValueError("An official HTTPS legal source is required")
        return value


class Clause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    act_id: str
    version_id: str
    provision: str
    url: str
    headings: list[str]
    text: str
    references: list[str]
    source_sha256: str
    repealed: bool = False

    @property
    def id(self):
        return f"{self.act_id}:{self.version_id}:{self.provision}"


class Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.parts, self.links = [], [], []
        self.tag = self.anchor = None

    def flush(self):
        if self.tag:
            text = re.sub(r"\s+", " ", "".join(self.parts)).strip()
            self.blocks.append((self.tag, text, self.anchor, self.links))
        self.tag, self.anchor, self.parts, self.links = None, None, [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"p", "h1", "h2", "h3", "h4", "td"}:
            self.flush()
            self.tag, self.anchor = tag, attrs.get("id")
        elif tag == "a":
            self.anchor = self.anchor or attrs.get("name")
            if attrs.get("href"):
                self.links.append(attrs["href"])
        elif tag == "br":
            if self.tag == "note":
                self.flush()
            else:
                self.parts.append(" ")
        elif tag == "span" and attrs.get("class") == "note" and not self.tag:
            self.tag = "note"

    def handle_endtag(self, tag):
        if tag == self.tag:
            self.flush()

    def handle_data(self, data):
        if self.tag:
            self.parts.append(data)


def extract_clauses(source: Snapshot, html: str) -> list[Clause]:
    if hashlib.sha256(html.encode()).hexdigest() != source.sha256:
        raise ValueError("Legal snapshot SHA256 mismatch")
    parser = Blocks()
    parser.feed(html)
    parser.flush()
    clauses, headings, seen = [], [], set()
    active = False
    for tag, text, anchor, links in parser.blocks:
        if tag.startswith("h") and re.match(r"Глава\s+1\.", text):
            active = True
        if not active:
            continue
        if re.match(r"Приложение\s+\d", text):
            break  # Annexes remain in the hashed raw source; never confuse form numbering.
        if tag.startswith("h"):
            if text.startswith("Глава"):
                headings = [text]
            elif text.startswith("Параграф"):
                headings = headings[:1] + [text]
            continue
        match = re.match(r"(\d+(?:-\d+)?)\.\s+", text)
        if match:
            provision = match[1]
            if provision in seen:
                raise ValueError("Duplicate main legal provision")
            seen.add(provision)
            clauses.append(
                Clause(
                    act_id=source.act_id,
                    version_id=source.version_id,
                    provision=provision,
                    url=source.official_url + ("#" + anchor if anchor else ""),
                    headings=headings.copy(),
                    text=text,
                    references=[],
                    source_sha256=source.sha256,
                    repealed=bool(re.match(r"\d+(?:-\d+)?\.\s+Исключен", text)),
                )
            )
        elif clauses:
            clauses[-1].text += "\n" + text
        if clauses:
            clauses[-1].references.extend(urljoin(source.official_url, link) for link in links)
    if not clauses:
        raise ValueError("Snapshot contains no main legal clauses; refuse shells or partial pages")
    return clauses


def tokens(text):
    return re.findall(r"[\w-]+", text.casefold().replace("ё", "е"))


class Corpus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[Snapshot]
    clauses: list[Clause]

    @model_validator(mode="after")
    def bound_sources(self):
        sources = {(s.act_id, s.version_id): s for s in self.sources}
        if len(sources) != len(self.sources) or len({c.id for c in self.clauses}) != len(
            self.clauses
        ):
            raise ValueError("Duplicate corpus source or clause ID")
        for clause in self.clauses:
            source = sources.get((clause.act_id, clause.version_id))
            if (
                not source
                or source.sha256 != clause.source_sha256
                or clause.url.split("#")[0] != source.official_url
            ):
                raise ValueError("Clause does not match its official source")
        return self

    def search(self, query, *, act_id=None, limit=5, include_historical=False):
        if not 1 <= limit <= 20 or not query.strip():
            raise ValueError("Use a nonempty query and a limit between 1 and 20")
        current = {(s.act_id, s.version_id) for s in self.sources if s.is_current}
        requested = re.search(r"(?:пункт(?:а|у|ом)?|п\.|§)\s*(\d+(?:-\d+)?)\b", query, re.I)
        candidates = [
            c
            for c in self.clauses
            if not c.repealed
            and (not act_id or c.act_id == act_id)
            and (include_historical or (c.act_id, c.version_id) in current)
            and (not requested or c.provision == requested[1])
        ]
        if not candidates:
            return []
        documents = [tokens(c.text + " " + " ".join(c.headings)) for c in candidates]
        frequencies = [Counter(d) for d in documents]
        average = sum(map(len, documents)) / len(documents)
        query_terms = set(tokens(query)) - {"пункт", "пункта", "п", "§"}
        scored = []
        sources = {(s.act_id, s.version_id): s for s in self.sources}
        for clause, terms, counts in zip(candidates, documents, frequencies, strict=True):
            score = 1.0 if requested else 0.0
            for term in query_terms:
                frequency = counts[term]
                if not frequency:
                    continue
                df = sum(term in counts for counts in frequencies)
                idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
                score += (
                    idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(terms) / average))
                )
            if score:
                scored.append(
                    {
                        "score": score,
                        "clause": clause.model_dump(),
                        "source": sources[(clause.act_id, clause.version_id)].model_dump(),
                        "interpretation": "retrieved legal text, not a video finding",
                    }
                )
        return sorted(scored, key=lambda hit: (-hit["score"], hit["clause"]["url"]))[:limit]


def load_release(root: Path) -> Corpus:
    """Check receipts and reconstruct the index from its preserved official text, offline."""
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported legal release")

    def verified(path, expected):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Unsafe legal release path")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Legal release SHA256 mismatch")
        return raw

    corpus = Corpus.model_validate_json(verified(root / "corpus.json", manifest["corpus_sha256"]))
    sources, clauses = [], []
    for receipt in manifest["sources"]:
        source = Snapshot.model_validate(receipt["snapshot"])
        if not re.fullmatch(r"V\d{10}", source.act_id) or not re.fullmatch(
            r"[0-9a-f-]{36}", source.version_id
        ):
            raise ValueError("Unsafe legal source ID")
        directory = root / source.act_id / source.version_id
        hashes = receipt["sha256"]
        if set(hashes) != {"source.html", "metadata.json", "versions.json", "content.json"}:
            raise ValueError("Incomplete legal source receipt")
        raw = {name: verified(directory / name, digest) for name, digest in hashes.items()}
        html = raw["source.html"].decode()
        meta = json.loads(raw["metadata.json"])
        meta = meta.get("document", meta)
        content, versions = json.loads(raw["content.json"]), json.loads(raw["versions.json"])
        current = [v for v in versions["versions"] if v.get("is_current")]
        if (
            meta["id"] != source.version_id
            or meta["group_number"] != source.act_id
            or meta["title_ru"] != source.title
            or meta["is_actual"] is not True
            or meta["status"] not in {"new", "upd"}
            or not source.is_current
            or source.official_url != f"https://adilet.zan.kz/rus/docs/{source.act_id}"
            or content["document_id"] != source.version_id
            or content["text_content"] != html
            or meta.get("text_content", html) != html
            or versions["total_count"] != len(versions["versions"])
            or len(current) != 1
            or current[0]["document_id"] != source.version_id
            or current[0]["revision_date"] != source.revision_date_raw
        ):
            raise ValueError("Legal release metadata/version mismatch")
        extracted = extract_clauses(source, html)
        if receipt["main_clause_records"] != len(extracted):
            raise ValueError("Legal release clause count mismatch")
        sources.append(source)
        clauses.extend(extracted)
    if corpus != Corpus(sources=sources, clauses=clauses):
        raise ValueError("Legal index does not reconstruct from official snapshots")
    return corpus
