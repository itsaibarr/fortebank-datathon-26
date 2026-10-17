"""Metadata-only release checks; no scene content reaches stdout."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from forte_visual import adapter
from forte_visual.io import canonical, digest, local, private_dir, read, write


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Clip(Strict):
    manifest: str
    annotation: str
    media: str
    # Original-oriented full-frame derivatives only. Crops are built by consumer.
    images: dict[str, str]
    track_mode: Literal["oracle", "automatic"] = "oracle"


class Release(Strict):
    schema_version: Literal["forte-visual-release/1"]
    producer_schema: Literal["forte-track/1"]
    producer_code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    export_complete: bool
    completed_by: str
    completed_at: datetime
    synthetic: bool = False
    files: dict[str, str]
    clips: list[Clip] = Field(min_length=1)


def verify(path: Path):
    before = digest(path)
    release = Release.model_validate(read(path))
    if not release.export_complete or not release.completed_by.strip():
        raise ValueError("Producer has not marked export complete")
    if not release.completed_at.tzinfo:
        raise ValueError("Completion time needs timezone")
    root = path.parent
    for name, expected in release.files.items():
        if len(expected) != 64 or digest(local(root, name)) != expected:
            raise ValueError("Missing/corrupt release artifact")
    pairs = []
    seen = set()
    for clip in release.clips:
        required = {clip.manifest, clip.annotation, clip.media, *clip.images.values()}
        if not required <= release.files.keys():
            raise ValueError("Referenced files absent from release inventory")
        m, a = adapter.load_pair(local(root, clip.manifest), local(root, clip.annotation))
        if m.clip_id in seen:
            raise ValueError("Duplicate clip ID")
        seen.add(m.clip_id)
        if m.source_sha256 != release.files[clip.media]:
            raise ValueError("Source hash mismatch")
        if m.annotation_sha256 != release.files[clip.annotation]:
            raise ValueError("Annotation hash mismatch")
        if local(root, str(Path(clip.manifest).parent / m.annotation_file)) != local(
            root, clip.annotation
        ):
            raise ValueError("Producer annotation path mismatch")
        frame_ids = {f.frame_id for f in m.frames}
        if not clip.images.keys() <= frame_ids:
            raise ValueError("Derivative has no source frame")
        recorded_commit = m.provenance.get("producer_code_commit")
        if recorded_commit and recorded_commit != release.producer_code_commit:
            raise ValueError("Producer code receipt mismatched")
        pairs.append((clip, m, a))
    # Check again after parsing all files: partial/changing exports are never accepted.
    if digest(path) != before or any(digest(local(root, n)) != h for n, h in release.files.items()):
        raise ValueError("Release changed during validation")
    check_splits(pairs)
    receipt = {
        "release_sha256": before,
        "producer_schema": release.producer_schema,
        "producer_code_commit": release.producer_code_commit,
        "mapping_version": adapter.MAPPING_VERSION,
        "mapping_sha256": adapter.mapping_hash(),
        "consumer_import_hashes": {
            name: digest(Path(module.__file__))
            for name, module in (
                ("annotations", __import__("forte.annotations", fromlist=["Annotation"])),
                ("tracking", __import__("forte.tracking", fromlist=["TrackManifest"])),
                ("video", __import__("forte.video", fromlist=["FrameRef"])),
            )
        },
        "files_digest": canonical(release.files),
        "file_count": len(release.files),
        "clips": len(pairs),
        "synthetic": release.synthetic,
        "compatibility": "synthetic-only" if release.synthetic else "structural-only",
        "reviewed_evaluation_targets": sum(
            len(adapter.reviewed_targets(m, a)) for _, m, a in pairs
        ),
        "eligible_training_targets": sum(
            len(adapter.reviewed_targets(m, a, training=True)) for _, m, a in pairs
        ),
    }
    prior = root / "consumer-receipt.json"
    if prior.exists() and read(prior) != receipt:
        raise ValueError("Consumer snapshot mapping/code/content changed; create a new snapshot")
    return release, pairs, receipt


def check_splits(pairs):
    groups = {}
    for _, m, _ in pairs:
        for key in [m.source_sha256, m.recording_group, m.session_group]:
            if key is None:
                continue
            if key in groups and groups[key] != m.split:
                raise ValueError("Recording/session/source split leakage")
            groups[key] = m.split
        if m.regression_only and m.training_eligible:
            raise ValueError("Regression footage cannot train")


def snapshot(path: Path, output: Path):
    release, _, receipt = verify(path)
    private_dir(output)
    for name in release.files:
        target = local(output, name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(local(path.parent, name), target)
        target.chmod(0o600)
    shutil.copyfile(path, output / "release.json")
    (output / "release.json").chmod(0o600)
    _, _, copied = verify(output / "release.json")
    if copied["release_sha256"] != receipt["release_sha256"]:
        raise ValueError("Snapshot source changed")
    verify(path)
    write(output / "consumer-receipt.json", receipt)
    return receipt


def gate(pairs, *, training=False):
    reasons = []
    groups = {
        m.session_group or m.recording_group for _, m, a in pairs if adapter.reviewed_targets(m, a)
    }
    if len(groups) < 2:
        reasons.append("Gate A needs multiple reviewed recording/session groups")
    if not any(m.regression_only and adapter.reviewed_targets(m, a) for _, m, a in pairs):
        reasons.append("Gate A missing reviewed regression packet")
    if training:
        coverage = {}
        for _, m, a in pairs:
            if m.split in {"train", "validation"} and (not m.split_frozen or not m.session_group):
                reasons.append("Gate B needs frozen session groups")
            for f in adapter.reviewed_targets(m, a, training=True):
                if (
                    f.kind == "action"
                    and f.value != "unclear"
                    and f.observation_state == "observed"
                ):
                    coverage.setdefault(f.value, {}).setdefault(m.split, set()).add(m.session_group)
        if not coverage:
            reasons.append("Gate B has no eligible positive action coverage")
        for splits in coverage.values():
            if len(splits.get("train", set())) < 3 or len(splits.get("validation", set())) < 2:
                reasons.append("Gate B action floor needs 3 train and 2 validation groups")
    return sorted(set(reasons))
