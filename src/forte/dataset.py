"""Read-only provenance checks for the supplied competition archive."""

import hashlib
from pathlib import Path
from zipfile import BadZipFile, ZipFile

EXPECTED_ARCHIVE_SHA256 = "c01ee47563620f9cef14cc42fd23d81f4f58600e5d1eae39d97bb85b57961867"


def audit_archive(
    archive: Path, *, expected_sha256: str = EXPECTED_ARCHIVE_SHA256
) -> dict[str, str | int | bool]:
    """Verify bytes and CRCs, then inventory entries without extracting anything."""
    archive = archive.expanduser().resolve()
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != expected_sha256.lower():
        raise ValueError(f"SHA256 mismatch: expected {expected_sha256}, got {digest}")
    with ZipFile(archive) as contents:
        bad_entry = contents.testzip()
        if bad_entry is not None:
            raise BadZipFile(f"CRC check failed for {bad_entry}")
        files = [entry for entry in contents.infolist() if not entry.is_dir()]
        videos = sum(entry.filename.lower().endswith(".mov") for entry in files)
        annotations = sum(entry.filename.lower().endswith(".xlsx") for entry in files)
        return {
            "archive": str(archive),
            "sha256": digest,
            "archive_bytes": archive.stat().st_size,
            "uncompressed_bytes": sum(entry.file_size for entry in files),
            "files": len(files),
            "mov_files": videos,
            "annotation_files": annotations,
            "other_files": len(files) - videos - annotations,
            "zip_crc_valid": True,
        }
