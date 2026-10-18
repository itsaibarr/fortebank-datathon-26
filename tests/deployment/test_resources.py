"""Pinned public preparation checks; HTTP transport serves synthetic bytes only."""

import hashlib
import http.server
import io
import json
import subprocess
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/forte-admin"))
from forte_admin import resources  # noqa: E402

REVISION = "1" * 40
IMAGE = "sha256:" + "2" * 64
BODY = b"synthetic public model fixture\n" * 19
ASSET = f"models/snapshots/{REVISION}/tokenizer.json"
PUBLIC_URL = f"https://huggingface.co/Qwen/Qwen3.8-27B/resolve/{REVISION}/tokenizer.json"


def pinned(body=BODY, *, path=ASSET, url=PUBLIC_URL):
    digest = hashlib.sha256(body).hexdigest()
    entry = {
        "root": "models",
        "relative_path": REVISION + "/tokenizer.json",
        "container_path": "/" + path,
        "sha256": digest,
        "size_bytes": len(body),
        "source_url": url,
    }
    inventory = {
        "schema_version": "forte.public-assets/1",
        "model": {"repository": "Qwen/Qwen3.8-27B", "revision": REVISION},
        "files": [entry],
    }
    manifest = {
        "core": {"image": IMAGE},
        "assets": [{"path": path, "sha256": digest, "size_bytes": len(body)}],
    }
    return manifest, inventory


def docker_present(command, **kwargs):
    assert command[:3] == ["docker", "image", "inspect"]
    return SimpleNamespace(returncode=0, stdout=IMAGE + "\n")


def prepare(tmp_path, *, manifest=None, inventory=None, **kwargs):
    if manifest is None:
        manifest, inventory = pinned()
    return resources.prepare_resources(
        manifest,
        tmp_path / "resources",
        inventory=inventory,
        snapshot_root=tmp_path / "shipped",
        runner=kwargs.pop("runner", docker_present),
        **kwargs,
    )


def write_bundle(tmp_path, data=BODY):
    path = tmp_path / "bundle" / ASSET
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    return tmp_path / "bundle"


def test_preview_and_default_apply_never_use_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("implicit network access")

    monkeypatch.setattr(resources._PublicTransport, "open", forbidden)
    report = prepare(tmp_path, online=True)
    assert report["preview"] and report["ok"]
    assert report["items"][0]["status"] == "available"
    assert not (tmp_path / "resources").exists()
    report = prepare(tmp_path, apply=True)
    assert not report["ok"] and report["missing"] == 1
    assert not (tmp_path / "resources").exists()


def test_disconnected_import_repeatability_and_corruption_repair(tmp_path):
    bundle = write_bundle(tmp_path)
    report = prepare(tmp_path, source_dir=bundle, apply=True)
    destination = tmp_path / "resources" / ASSET
    assert report["ok"] and report["prepared"] == 1 and report["bytes"] == len(BODY)
    assert destination.read_bytes() == BODY
    stamp = destination.stat().st_mtime_ns
    report = prepare(tmp_path, source_dir=bundle, apply=True)
    assert report["ok"] and report["present"] == 1 and report["bytes"] == 0
    assert destination.stat().st_mtime_ns == stamp
    destination.write_bytes(b"corrupt")
    report = prepare(tmp_path, apply=True)
    assert not report["ok"] and report["corrupt"] == 1
    assert destination.read_bytes() == b"corrupt"
    report = prepare(tmp_path, source_dir=bundle, apply=True)
    assert report["ok"] and destination.read_bytes() == BODY


def test_corrupt_source_never_publishes_or_sends_case_content(tmp_path):
    bundle = write_bundle(tmp_path, b"PRIVATE_CONTENT_NOT_FOR_DIAGNOSTICS")
    report = prepare(tmp_path, source_dir=bundle, apply=True)
    assert not report["ok"] and report["corrupt"] == 1
    assert "PRIVATE_CONTENT" not in json.dumps(report)
    assert not (tmp_path / "resources" / ASSET).exists()


def test_only_exact_allowed_files_are_copied(tmp_path):
    bundle = write_bundle(tmp_path)
    (bundle / "case.mov").write_bytes(b"must never be copied")
    (bundle / "credentials.env").write_text("SECRET")
    assert prepare(tmp_path, source_dir=bundle, apply=True)["ok"]
    assert len(list((tmp_path / "resources").rglob("*.*"))) == 1
    assert not (tmp_path / "resources/case.mov").exists()


def test_default_release_bundle_and_multiple_operator_sources(tmp_path):
    shipped_bundle = tmp_path / "shipped/public-resources"
    destination = shipped_bundle / ASSET
    destination.parent.mkdir(parents=True)
    destination.write_bytes(BODY)
    assert prepare(tmp_path, apply=True)["ok"]
    destination.unlink()
    (tmp_path / "resources" / ASSET).unlink()
    bundle = write_bundle(tmp_path)
    report = prepare(tmp_path, source_dir=[tmp_path / "absent", bundle], apply=True)
    assert report["ok"] and report["prepared"] == 1


def test_symlinked_source_or_destination_is_rejected(tmp_path):
    bundle = write_bundle(tmp_path)
    source = bundle / ASSET
    source.unlink()
    other = tmp_path / "private"
    other.write_bytes(BODY)
    source.symlink_to(other)
    report = prepare(tmp_path, source_dir=bundle, apply=True)
    assert not report["ok"] and report["corrupt"] == 1
    destination = tmp_path / "resources/models"
    destination.parent.mkdir()
    destination.symlink_to(bundle / "models")
    assert not prepare(tmp_path, source_dir=bundle, apply=True)["ok"]
    assert other.read_bytes() == BODY


@pytest.mark.parametrize(
    "path", ["../case.mov", "/case.mov", "models/../../secret", "models/x\nkey"]
)
def test_unsafe_manifest_paths_rejected(tmp_path, path):
    manifest, inventory = pinned()
    manifest["assets"][0]["path"] = path
    report = prepare(tmp_path, manifest=manifest, inventory=inventory, apply=True)
    assert not report["ok"] and not (tmp_path / "resources").exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.invalid/model",
        "http://huggingface.co/model",
        PUBLIC_URL.replace(REVISION, "main"),
        PUBLIC_URL + "?token=secret",
    ],
)
def test_unpinned_or_unapproved_download_urls_rejected(tmp_path, url):
    manifest, inventory = pinned(url=url)
    report = prepare(tmp_path, manifest=manifest, inventory=inventory, online=True, apply=True)
    assert not report["ok"]
    assert "token=secret" not in json.dumps(report)


def test_inventory_hash_or_size_disagreement_rejected(tmp_path):
    manifest, inventory = pinned()
    manifest["assets"][0]["sha256"] = "f" * 64
    report = prepare(tmp_path, manifest=manifest, inventory=inventory)
    assert not report["ok"] and "differs" in report["unresolved_prerequisites"][0]


@pytest.mark.parametrize("mutation", ["model", "files", "container", "relative"])
def test_malformed_inventory_returns_safe_structured_error(tmp_path, mutation):
    manifest, inventory = pinned()
    if mutation == "model":
        inventory["model"] = ["SECRET"]
    elif mutation == "files":
        inventory["files"] = {"SECRET": "not-an-array"}
    elif mutation == "container":
        inventory["files"][0]["container_path"] = None
    else:
        inventory["files"][0].pop("relative_path")
    report = prepare(tmp_path, manifest=manifest, inventory=inventory, apply=True)
    assert not report["ok"] and report["unresolved_prerequisites"]
    assert "SECRET" not in json.dumps(report)
    assert not (tmp_path / "resources").exists()


def test_derived_onnx_requires_local_approved_artifact(tmp_path):
    manifest, inventory = pinned(path="models/public/reid/osnet.onnx", url=None)
    report = prepare(tmp_path, manifest=manifest, inventory=inventory, online=True)
    assert not report["ok"] and report["missing"] == 1


def test_legal_snapshot_uses_shipped_bytes_and_never_refetches_provenance_url(
    tmp_path, monkeypatch
):
    manifest, inventory = pinned(
        path="legal/2026-10-17/content.json", url="https://adilet.zan.kz/rus/docs/V1"
    )
    entry = inventory["files"][0]
    entry.update(root="legal", relative_path="2026-10-17/content.json")
    shipped = tmp_path / "shipped/legal/2026-10-17/content.json"
    shipped.parent.mkdir(parents=True)
    shipped.write_bytes(BODY)
    monkeypatch.setattr(resources._PublicTransport, "open", lambda *a: pytest.fail("legal refetch"))
    report = prepare(tmp_path, manifest=manifest, inventory=inventory, online=True, apply=True)
    assert report["ok"] and report["prepared"] == 1
    assert (tmp_path / "resources/legal/2026-10-17/content.json").read_bytes() == BODY


def test_actual_candidate_preview_uses_immutable_legal_snapshot_without_model_download(tmp_path):
    manifest = json.loads((ROOT / "deploy/portable/core-current.candidate.json").read_text())
    report = resources.prepare_resources(manifest, tmp_path / "resources", runner=docker_present)
    assert not report["ok"] and report["preview"]
    legal = [item for item in report["items"] if item["path"].startswith("legal/")]
    assert legal and all(item["status"] == "available" for item in legal)
    assert not (tmp_path / "resources").exists()


@pytest.fixture
def synthetic_http():
    state = SimpleNamespace(mode="normal", requests=[])

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            state.requests.append(dict(self.headers))
            requested = self.headers.get("Range")
            start = int(requested.removeprefix("bytes=").removesuffix("-")) if requested else 0
            body, status, etag = BODY[start:], 206 if requested else 200, '"synthetic-v1"'
            if state.mode == "restart":
                body, status, start, etag = BODY, 200, 0, '"synthetic-v2"'
            if state.mode == "bad_etag":
                etag = '"unrelated-v2"'
            if state.mode == "interrupt_weak":
                etag = 'W/"weak-validator"'
            self.send_response(status)
            self.send_header("ETag", etag)
            if status == 206:
                range_start = start + 1 if state.mode == "bad_range" else start
                total = len(BODY) + 1 if state.mode == "bad_total" else len(BODY)
                self.send_header("Content-Range", f"bytes {range_start}-{len(BODY) - 1}/{total}")
            if state.mode == "too_large":
                body += b"unexpected bytes"
            else:
                length = len(body) - 1 if state.mode == "bad_length" else len(body)
                self.send_header("Content-Length", str(length))
            self.end_headers()
            if state.mode in {"interrupt", "interrupt_weak"}:
                body = body[: len(body) // 2]
            self.wfile.write(body)
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class SyntheticTransport:
        """Test-only replacement transport; there is no installer flag for this."""

        def open(self, url, headers):
            assert url == PUBLIC_URL
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/fixture", headers=headers
            )
            return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=3
            )

    state.transport = SyntheticTransport()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def spec():
    manifest, inventory = pinned()
    return resources._specifications(manifest, inventory)[0]


def interrupt(tmp_path, synthetic_http):
    destination = tmp_path / "public.bin"
    synthetic_http.mode = "interrupt"
    with pytest.raises(resources.ResourceError, match="incomplete|failed"):
        resources._download(spec(), destination, _transport=synthetic_http.transport)
    assert not destination.exists()
    partial = destination.with_name(destination.name + ".part")
    assert 0 < partial.stat().st_size < len(BODY)
    return destination, partial


def test_streamed_download_hash_and_atomic_publication(tmp_path, synthetic_http):
    destination = tmp_path / "public.bin"
    assert resources._download(spec(), destination, _transport=synthetic_http.transport) == len(
        BODY
    )
    assert destination.read_bytes() == BODY
    assert not destination.with_name("public.bin.part").exists()
    assert not destination.with_name("public.bin.part.json").exists()
    assert synthetic_http.requests[0]["Accept-Encoding"] == "identity"
    assert not any(key.lower() in {"authorization", "cookie"} for key in synthetic_http.requests[0])


def test_interrupted_download_resumes_with_exact_range_and_etag(tmp_path, synthetic_http):
    destination, partial = interrupt(tmp_path, synthetic_http)
    length = partial.stat().st_size
    synthetic_http.mode = "normal"
    assert (
        resources._download(spec(), destination, _transport=synthetic_http.transport)
        == len(BODY) - length
    )
    assert destination.read_bytes() == BODY
    assert synthetic_http.requests[-1]["Range"] == f"bytes={length}-"
    assert synthetic_http.requests[-1]["If-Range"] == '"synthetic-v1"'


@pytest.mark.parametrize("mode", ["bad_etag", "bad_range", "bad_total"])
def test_invalid_resume_keeps_existing_partial_and_never_publishes(tmp_path, synthetic_http, mode):
    destination, partial = interrupt(tmp_path, synthetic_http)
    previous = partial.read_bytes()
    synthetic_http.mode = mode
    with pytest.raises(resources.ResourceError, match="range or ETag"):
        resources._download(spec(), destination, _transport=synthetic_http.transport)
    assert not destination.exists() and partial.read_bytes() == previous


@pytest.mark.parametrize("mode", ["bad_length", "too_large"])
def test_wrong_response_length_cannot_publish(tmp_path, synthetic_http, mode):
    synthetic_http.mode = mode
    destination = tmp_path / "public.bin"
    with pytest.raises(resources.ResourceError, match="pinned"):
        resources._download(spec(), destination, _transport=synthetic_http.transport)
    assert not destination.exists()


def test_weak_validator_restarts_partial_without_range(tmp_path, synthetic_http):
    destination = tmp_path / "public.bin"
    synthetic_http.mode = "interrupt_weak"
    with pytest.raises(resources.ResourceError):
        resources._download(spec(), destination, _transport=synthetic_http.transport)
    synthetic_http.mode = "normal"
    resources._download(spec(), destination, _transport=synthetic_http.transport)
    assert destination.read_bytes() == BODY
    assert "Range" not in synthetic_http.requests[-1]


def test_complete_hash_verified_partial_publishes_without_network(tmp_path, synthetic_http):
    destination = tmp_path / "public.bin"
    (tmp_path / "public.bin.part").write_bytes(BODY)
    assert resources._download(spec(), destination, _transport=synthetic_http.transport) == 0
    assert destination.read_bytes() == BODY and not synthetic_http.requests


def test_if_range_ignored_restarts_instead_of_appending(tmp_path, synthetic_http):
    destination, _ = interrupt(tmp_path, synthetic_http)
    synthetic_http.mode = "restart"
    resources._download(spec(), destination, _transport=synthetic_http.transport)
    assert destination.read_bytes() == BODY


def test_hash_mismatch_cannot_replace_existing_destination(tmp_path, synthetic_http):
    destination = tmp_path / "public.bin"
    destination.write_bytes(b"previous preserved")
    expected = spec() | {"sha256": "e" * 64}
    with pytest.raises(resources.ResourceError, match="SHA256"):
        resources._download(expected, destination, _transport=synthetic_http.transport)
    assert destination.read_bytes() == b"previous preserved"


def test_unvalidated_or_oversized_partial_rejected(tmp_path, synthetic_http):
    destination = tmp_path / "public.bin"
    partial = tmp_path / "public.bin.part"
    partial.write_bytes(b"x" * (len(BODY) + 1))
    with pytest.raises(resources.ResourceError, match="exceeds"):
        resources._download(spec(), destination, _transport=synthetic_http.transport)
    partial.write_bytes(b"untrusted partial")
    with pytest.raises(resources.ResourceError, match="metadata"):
        resources._download(spec(), destination, _transport=synthetic_http.transport)
    assert not synthetic_http.requests


def test_production_transport_and_redirects_block_unapproved_origins():
    transport = resources._PublicTransport(resources.HF_ORIGINS)
    for url in (
        "http://127.0.0.1:9999/fixture",
        "https://evil.invalid/",
        "https://user:pass@huggingface.co/",
    ):
        with pytest.raises(resources.ResourceError):
            transport.open(url, {})
    guard = resources._RedirectGuard(resources.HF_ORIGINS)
    with pytest.raises(resources.ResourceError, match="unapproved"):
        guard.redirect_request(
            urllib.request.Request(PUBLIC_URL), None, 302, "", {}, "https://evil.invalid/leak"
        )
    assert guard.redirect_request(
        urllib.request.Request(PUBLIC_URL),
        None,
        302,
        "",
        {},
        "https://cas-bridge.xethub.hf.co/public?signature=public",
    )


def test_production_transport_does_not_use_environment_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@evil.invalid")
    captured = []

    def opener(*handlers):
        captured.extend(handlers)
        return SimpleNamespace()

    monkeypatch.setattr(urllib.request, "build_opener", opener)
    resources._PublicTransport(resources.HF_ORIGINS)
    assert isinstance(captured[0], urllib.request.ProxyHandler)
    assert captured[0].proxies == {}


def test_explicit_image_import_checks_identity_and_never_logs_loader_output(tmp_path):
    artifact = tmp_path / "approved-image.tar"
    artifact.write_bytes(b"synthetic archive handled by fake docker only")
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        installed = any(cmd[:2] == ["docker", "load"] for cmd in commands)
        return SimpleNamespace(
            returncode=0 if installed else 1, stdout=IMAGE if installed else "SECRET diagnostic"
        )

    report = prepare(tmp_path, image_artifact=artifact, runner=runner)
    assert report["image"]["status"] == "available"
    assert all(cmd[:3] == ["docker", "image", "inspect"] for cmd in commands)
    commands.clear()
    report = prepare(tmp_path, image_artifact=artifact, runner=runner, apply=True)
    assert report["image"]["status"] == "prepared"
    assert any(cmd[:2] == ["docker", "load"] for cmd in commands)
    assert "SECRET" not in json.dumps(report)


def test_wrong_image_id_stays_blocked(tmp_path):
    artifact = tmp_path / "wrong.tar"
    artifact.write_bytes(b"synthetic")

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="sha256:" + "9" * 64)

    report = prepare(tmp_path, image_artifact=artifact, runner=runner, apply=True)
    assert report["image"]["status"] == "missing"
    assert not report["ok"]


def test_docker_errors_are_safe_and_actionable(tmp_path):
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired("SECRET command", 30, output="CASE diagnostic")

    report = prepare(tmp_path, runner=runner)
    assert report["image"]["status"] == "missing"
    assert not report["ok"]
    assert "SECRET" not in json.dumps(report) and "CASE" not in json.dumps(report)


def test_shared_resource_preparations_cannot_change_the_verified_partial_before_publication(
    tmp_path, monkeypatch
):
    destination = tmp_path / "resources" / ASSET
    partial = destination.with_name(destination.name + ".part")
    lock = destination.with_name(destination.name + ".prepare.lock")
    verified, publish = threading.Event(), threading.Event()
    opened = []

    class PublicBytes(io.BytesIO):
        status = 200
        headers = {"Content-Length": str(len(BODY)), "ETag": '"synthetic-public-v1"'}

    def transport(_self, url, headers):
        opened.append(url)
        return PublicBytes(BODY)

    original = resources._verified

    def pause_after_hash(path, spec):
        result = original(path, spec)
        if path == partial and result:
            verified.set()
            assert publish.wait(5), "Synthetic publication barrier timed out"
        return result

    monkeypatch.setattr(resources._PublicTransport, "open", transport)
    monkeypatch.setattr(resources, "_verified", pause_after_hash)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(prepare, tmp_path, apply=True, online=True)
        try:
            assert verified.wait(5), "First synthetic preparation did not reach verification"
            inode = lock.stat().st_ino
            assert lock.stat().st_mode & 0o777 == 0o600
            assert partial.read_bytes() == BODY and not destination.exists()
            second = prepare(tmp_path, apply=True, online=True)
            assert not second["ok"] and second["missing"] == 1 and second["corrupt"] == 0
            assert "Another preparation owns" in second["items"][0]["reason"]
            assert len(opened) == 1 and partial.read_bytes() == BODY
        finally:
            publish.set()
        assert first.result(timeout=5)["ok"]
    assert destination.read_bytes() == BODY and not partial.exists()
    assert lock.exists() and lock.stat().st_ino == inode
    # The inode remains stable across the next repair, rather than unlinking a
    # held lock and allowing another process to lock a different replacement.
    destination.write_bytes(b"synthetic corruption")
    assert prepare(tmp_path, apply=True, online=True)["ok"]
    assert destination.read_bytes() == BODY and lock.stat().st_ino == inode


@pytest.mark.parametrize("kind", ["symlink", "directory", "broad"])
def test_resource_lock_rejects_unsafe_files_before_transport(tmp_path, monkeypatch, kind):
    destination = tmp_path / "resources" / ASSET
    destination.parent.mkdir(parents=True, mode=0o700)
    lock = destination.with_name(destination.name + ".prepare.lock")
    preserved = tmp_path / "synthetic-preserved.txt"
    preserved.write_bytes(b"synthetic bytes must not be changed")
    if kind == "symlink":
        lock.symlink_to(preserved)
    elif kind == "directory":
        lock.mkdir()
    else:
        lock.write_bytes(b"")
        lock.chmod(0o644)

    def forbidden(*args):
        pytest.fail("Unsafe lock must reject before any public transport")

    monkeypatch.setattr(resources._PublicTransport, "open", forbidden)
    report = prepare(tmp_path, apply=True, online=True)
    assert not report["ok"] and report["corrupt"] == 1
    assert not destination.exists()
    assert preserved.read_bytes() == b"synthetic bytes must not be changed"
