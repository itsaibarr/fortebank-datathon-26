"""Private, non-overwriting artifacts and content integrity."""

import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def local(root: Path, relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("Artifact path escapes release")
    result = root / p
    if result.is_symlink() or any(x.is_symlink() for x in result.parents if x != root.parent):
        raise ValueError("Artifact symlink forbidden")
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes release")
    return result


def private_dir(path: Path):
    assert_private(path)
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    return path


def write(path: Path, value):
    assert_private(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    path.chmod(0o600)


def read(path: Path):
    return json.loads(path.read_bytes())


def assert_private(path):
    if any((parent / ".git").exists() for parent in (path.resolve(), *path.resolve().parents)):
        raise ValueError("Experiment artifacts must remain outside Git checkouts")
