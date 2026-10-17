"""Pinned public rules and deterministic cautious explanation construction."""

import hashlib
import json
import re
from importlib.resources import files


def load_rules():
    root = files("forte").joinpath("data")
    catalog = json.loads(root.joinpath("rules.json").read_text())
    digest = hashlib.sha256(root.joinpath("resolution231-source.txt").read_bytes()).hexdigest()
    if digest != catalog["source_sha256"]:
        raise ValueError("Public rule source fingerprint mismatch")
    return catalog["rules"]


def description(event, rule, partial=False):
    facts = event.visible_facts.strip()
    if re.search(
        r"https?://|adilet|недостач|украл|мошеннич|винов|\btheft\b|\bfraud\b", facts, re.IGNORECASE
    ):
        raise ValueError("Unsupported legal, accounting or intent claim")
    text = f"Видимые действия: {facts} Возможное основание для проверки: {rule['citation']} "
    text += rule["limitation"]
    if partial:
        text += (
            " В другом фрагменте видимость была недостаточной; вывод относится к указанным кадрам."
        )
    return text
