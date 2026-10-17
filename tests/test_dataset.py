import hashlib
import json
from pathlib import Path
from zipfile import ZIP_STORED, BadZipFile, ZipFile

import pytest

from forte.cli import main
from forte.dataset import audit_archive


def archive_fixture(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "fixture.zip"
    with ZipFile(archive, "w", compression=ZIP_STORED) as contents:
        contents.writestr("open/", b"")
        contents.writestr("open/example.mov", b"synthetic-video-placeholder")
        contents.writestr("open/labels.xlsx", b"synthetic-annotation-placeholder")
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_inventory_excludes_directories_and_never_extracts(tmp_path: Path) -> None:
    archive, digest = archive_fixture(tmp_path)
    original = archive.read_bytes()
    result = audit_archive(archive, expected_sha256=digest)
    assert result["sha256"] == digest
    assert result["files"] == 2
    assert result["mov_files"] == 1
    assert result["annotation_files"] == 1
    assert result["other_files"] == 0
    assert result["zip_crc_valid"] is True
    assert archive.read_bytes() == original
    assert not (tmp_path / "open").exists()


def test_wrong_archive_is_rejected_before_it_can_be_used(tmp_path: Path) -> None:
    archive, _ = archive_fixture(tmp_path)
    with pytest.raises(ValueError, match="SHA256"):
        audit_archive(archive, expected_sha256="0" * 64)


def test_crc_corruption_is_rejected_even_when_the_hash_matches(tmp_path: Path) -> None:
    archive, _ = archive_fixture(tmp_path)
    data = archive.read_bytes().replace(
        b"synthetic-video-placeholder", b"synthetic-video-placeholdeX"
    )
    archive.write_bytes(data)
    with pytest.raises(BadZipFile, match="CRC"):
        audit_archive(archive, expected_sha256=hashlib.sha256(data).hexdigest())


def test_non_zip_and_missing_input_fail_explicitly(tmp_path: Path) -> None:
    missing = tmp_path / "missing.zip"
    with pytest.raises(FileNotFoundError):
        audit_archive(missing)
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"not an archive")
    with pytest.raises(BadZipFile):
        audit_archive(invalid, expected_sha256=hashlib.sha256(invalid.read_bytes()).hexdigest())


def test_cli_checks_the_expected_case_archive_and_outputs_json(tmp_path: Path, capsys) -> None:
    archive, digest = archive_fixture(tmp_path)
    assert main(["dataset-check", "--archive", str(archive), "--expected-sha256", digest]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mov_files"] == 1
    assert result["sha256"] == digest


def test_cli_returns_nonzero_for_a_different_dataset(tmp_path: Path, capsys) -> None:
    archive, _ = archive_fixture(tmp_path)
    assert main(["dataset-check", "--archive", str(archive)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SHA256" in captured.err
