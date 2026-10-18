"""Synthetic trusted-gateway ownership checks; no real session or inference claims."""

import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_api_v2 import KEY, correction, uncertain
from test_video import make_mov

from forte.api import create_app
from forte.settings import Settings

TOKEN = "synthetic-dedicated-gateway-token-" + "a" * 32


def headers(principal="reviewer-a"):
    return {
        "X-API-Key": KEY,
        "X-Forte-Gateway-Token": TOKEN,
        "X-Forte-Principal": principal,
    }


def app(settings):
    return create_app(settings, runner=uncertain, ready=lambda: True)


def submit(client, source, principal="reviewer-a", version=2, trusted=True):
    auth = headers(principal) if trusted else {"X-API-Key": KEY}
    accepted = client.post(
        f"/api/v{version}/analyze", headers=auth, files={"file": ("synthetic.mov", source)}
    )
    assert accepted.status_code == 202, accepted.text
    for _ in range(100):
        response = client.get(accepted.headers["Location"], headers=auth)
        assert response.status_code == 200
        if response.json()["status"] != "processing":
            assert response.json()["status"] == ("done" if version == 2 else "failed"), (
                response.text
            )
            return response.json()
        time.sleep(0.01)
    pytest.fail("Synthetic fixture did not complete")


def test_security_capability_requires_both_secrets_and_principal(tmp_path):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    with TestClient(app(settings)) as client:
        for auth in [
            {},
            {"X-API-Key": KEY},
            {"X-API-Key": KEY, "X-Forte-Principal": "reviewer-a"},
            {"X-Forte-Gateway-Token": TOKEN, "X-Forte-Principal": "reviewer-a"},
        ]:
            denied = client.get("/api/internal/security", headers=auth)
            assert denied.status_code == 401
            assert denied.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]
            assert "principal_ownership" not in denied.text
        response = client.get("/api/internal/security", headers=headers())
        assert response.status_code == 200
        assert response.json() == {
            "schema_version": "forte.gateway-security/1",
            "trusted_gateway_required": True,
            "principal_ownership": True,
            "ownerless_jobs_denied": True,
        }
        assert response.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]
        assert "X-Forte-Ownership-Mode" not in client.get("/health/live").headers
        # Internal capability stays out of the preserved v1 and separate v2 contracts.
        assert "/api/internal/security" not in client.get("/openapi.json").json()["paths"]
        assert (
            "/api/internal/security"
            not in client.get("/api/v2/openapi.json", headers=headers()).json()["paths"]
        )


def test_legacy_mode_has_no_ownership_capability_or_marker(tmp_path):
    with TestClient(app(Settings(KEY, tmp_path / "jobs"))) as client:
        assert client.get("/api/internal/security").status_code == 401
        for path in ["/api/internal/security", "/api/v2/jobs/invalid", "/api/unknown"]:
            response = client.get(path, headers={"X-API-Key": KEY})
            assert response.status_code in {404, 422}
            assert "X-Forte-Ownership-Mode" not in response.headers


def test_trusted_marker_covers_errors_validation_contract_and_admission(tmp_path):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with TestClient(app(settings)) as client:
        for path in ["/api/unknown", "/api/v2/jobs/invalid", "/api/v2/openapi.json"]:
            response = client.get(path, headers=headers())
            assert response.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]
        accepted = client.post(
            "/api/v2/analyze", headers=headers(), files={"file": ("synthetic.mov", source)}
        )
        assert accepted.status_code == 202
        assert accepted.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]


def test_unhandled_trusted_api_errors_have_generic_marked_response(tmp_path):
    application = app(Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN))

    @application.get("/api/internal/synthetic-failure")
    async def synthetic_failure():
        raise RuntimeError("synthetic-private-detail-must-not-be-returned")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/internal/synthetic-failure", headers=headers())
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "synthetic-private-detail" not in response.text
        assert response.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]


@pytest.mark.parametrize(
    "gateway_headers",
    [
        [],
        [("X-Forte-Gateway-Token", "incorrect"), ("X-Forte-Principal", "reviewer-a")],
        [("X-Forte-Gateway-Token", TOKEN)],
        [("X-Forte-Gateway-Token", TOKEN), ("X-Forte-Principal", "invalid/principal")],
        [
            ("X-Forte-Gateway-Token", TOKEN),
            ("X-Forte-Principal", "reviewer-a"),
            ("X-Forte-Principal", "reviewer-b"),
        ],
        [
            ("X-Forte-Gateway-Token", TOKEN),
            ("X-Forte-Gateway-Token", TOKEN),
            ("X-Forte-Principal", "reviewer-a"),
        ],
    ],
)
def test_gateway_identity_is_authenticated_before_upload_or_disclosure(tmp_path, gateway_headers):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    consumed = []

    def body():
        consumed.append(True)
        yield b"synthetic-not-a-recording"

    auth = [("X-API-Key", KEY), *gateway_headers]
    with TestClient(app(settings)) as client:
        assert client.post("/api/v2/analyze", headers=auth, content=body()).status_code == 401
        assert not consumed
        for suffix in ["", "/source", "/evidence/frame", "/corrections"]:
            assert client.get("/api/v2/jobs/not-a-uuid" + suffix, headers=auth).status_code == 401
        assert client.get("/api/v1/jobs/not-a-uuid", headers=auth).status_code == 401
        assert client.get("/health/live").status_code == 200


def test_both_versions_persist_owner_and_cannot_be_read_by_another_principal(tmp_path):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with TestClient(app(settings)) as client:
        for version in [1, 2]:
            completed = submit(client, source, version=version)
            job_id = completed["job_id"]
            metadata = json.loads((settings.private_root / job_id / "request.json").read_text())
            assert metadata["api_version"] == version
            assert metadata["owner_principal"] == "reviewer-a"
            if version == 1:
                assert metadata["pipeline"] == "reasoning"
                assert metadata["projection"] == "forte.jury-v1/1"
            prefix = f"/api/v{version}/jobs/{job_id}"
            assert client.get(prefix, headers=headers()).status_code == 200
            denied = client.get(prefix, headers=headers("reviewer-b"))
            unknown = client.get(f"/api/v{version}/jobs/{uuid4()}", headers=headers("reviewer-b"))
            assert denied.status_code == unknown.status_code == 404
            assert denied.json() == unknown.json()
            assert denied.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]
            other = 1 if version == 2 else 2
            assert client.get(f"/api/v{other}/jobs/{job_id}", headers=headers()).status_code == 404
            if version == 1:
                assert completed == {
                    "job_id": job_id,
                    "status": "failed",
                    "error": {
                        "code": "insufficient_evidence",
                        "message": "The visible evidence was insufficient for a reliable result.",
                    },
                }


def test_every_v2_media_correction_and_subsequent_range_rechecks_owner(tmp_path):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with TestClient(app(settings)) as client:
        completed = submit(client, source)
        prefix = "/api/v2/jobs/" + completed["job_id"]
        result = completed["result"]
        frame_id = result["events"][0]["evidence"][0]["frame_id"]
        media = ["/source", "/evidence/" + frame_id]
        for suffix in ["", *media, "/corrections"]:
            assert client.get(prefix + suffix, headers=headers()).status_code == 200
            response = client.get(prefix + suffix, headers=headers("reviewer-b"))
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "job_not_found"
        own_range = client.get(prefix + "/source", headers=headers() | {"Range": "bytes=0-15"})
        assert own_range.status_code == 206 and own_range.content == source[:16]
        assert own_range.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]
        for suffix in media:
            denied = client.get(
                prefix + suffix, headers=headers("reviewer-b") | {"Range": "bytes=16-31"}
            )
            assert denied.status_code == 404
        for auth in [headers("reviewer-b"), {"X-API-Key": KEY, "X-Forte-Principal": "reviewer-a"}]:
            response = client.post(prefix + "/corrections", headers=auth, json=correction(result))
            assert response.status_code in {401, 404}
        assert client.get(prefix + "/corrections", headers=headers()).json() == {"revisions": []}
        saved = client.post(
            prefix + "/corrections",
            headers=headers(),
            json=correction(result, reviewer="spoofed-reviewer"),
        )
        assert saved.status_code == 201, saved.text
        assert saved.headers.get_list("X-Forte-Ownership-Mode") == ["principal-v1"]
        assert saved.json()["correction"]["reviewer"] == "reviewer-a"
        assert saved.json()["correction"]["other_scopes_approved"] is False
    with TestClient(app(settings)) as restarted:
        assert restarted.get(prefix, headers=headers()).json() == completed
        assert restarted.get(prefix + "/source", headers=headers("reviewer-b")).status_code == 404
        history = restarted.get(prefix + "/corrections", headers=headers()).json()["revisions"]
        assert len(history) == 1 and history[0]["reviewer"] == "reviewer-a"


@pytest.mark.parametrize("version", [1, 2])
def test_ownerless_jobs_are_not_assigned_on_enabling_gateway_mode(tmp_path, version):
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    settings = Settings(KEY, tmp_path / "jobs")
    with TestClient(app(settings)) as legacy:
        completed = submit(legacy, source, version=version, trusted=False)
    path = settings.private_root / completed["job_id"] / "request.json"
    original = path.read_bytes()
    settings.trusted_gateway_token = TOKEN
    with TestClient(app(settings)) as secured:
        prefix = f"/api/v{version}/jobs/" + completed["job_id"]
        assert secured.get(prefix, headers=headers()).status_code == 404
        assert path.read_bytes() == original
        if version == 2:
            for suffix in ["/source", "/corrections"]:
                assert secured.get(prefix + suffix, headers=headers()).status_code == 404


@pytest.mark.parametrize("metadata", ["invalid-json", "[]", '{"owner_principal":"reviewer-a"}'])
def test_unverifiable_ownership_metadata_denies_all_resources_generically(tmp_path, metadata):
    settings = Settings(KEY, tmp_path / "jobs", trusted_gateway_token=TOKEN)
    source = make_mov(tmp_path / "synthetic.mov").read_bytes()
    with TestClient(app(settings)) as client:
        completed = submit(client, source)
        prefix = "/api/v2/jobs/" + completed["job_id"]
        (settings.private_root / completed["job_id"] / "request.json").write_text(metadata)
        unknown = client.get("/api/v2/jobs/" + str(uuid4()), headers=headers())
        for suffix in ["", "/source", "/evidence/frame", "/corrections"]:
            response = client.get(prefix + suffix, headers=headers())
            assert response.status_code == 404
            assert response.json() == unknown.json()


def test_optional_gateway_file_is_fail_closed_and_distinct(tmp_path, monkeypatch):
    monkeypatch.setenv("FORTE_API_KEY", KEY)
    monkeypatch.setenv("FORTE_PRIVATE_ROOT", str(tmp_path / "jobs"))
    monkeypatch.delenv("FORTE_TRUSTED_GATEWAY_TOKEN_FILE", raising=False)
    assert Settings.from_env().trusted_gateway_token is None
    token_file = tmp_path / "gateway-token"
    token_file.write_text(TOKEN)
    monkeypatch.setenv("FORTE_TRUSTED_GATEWAY_TOKEN_FILE", str(token_file))
    assert Settings.from_env().trusted_gateway_token == TOKEN
    token_file.write_text("")
    with pytest.raises(ValueError, match="Trusted gateway mode"):
        Settings.from_env()
    with pytest.raises(ValueError, match="differ"):
        Settings(api_key=TOKEN, private_root=tmp_path / "other", trusted_gateway_token=TOKEN)
