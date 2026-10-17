"""Synthetic behavior checks, never a private-data tracking benchmark."""

import errno
import json
import socket
import sys
from types import SimpleNamespace

import pytest
from PIL import Image
from test_video import make_mov

from forte.frozen_tracking import (
    DecodedFrame,
    LocalReIDONNX,
    TrackingConfig,
    analyze_participants,
    benchmark_continuity,
    continuity_metrics,
    normalized_embedding,
    reconcile_segments,
    require_outbound_blocked,
    source_transform,
)
from forte.video import FrameRef, decode_video

BOX = [0.1, 0.1, 0.5, 0.9]


def segment(name, times, embedding=(1, 0), box=BOX, zone=None, quality=0.9):
    observations = [
        {"frame_id": f"f{int(t * 100):06d}", "timestamp_sec": t, "box": box} for t in times
    ]
    return {
        "segment_id": name,
        "tracker_id": int(name[1:]),
        "participant_id": None,
        "observations": observations,
        "reflection_zone_id": zone,
        "conflicts": [],
        "gallery": [
            {
                "frame_id": observations[0]["frame_id"],
                "quality": quality,
                "embedding": normalized_embedding(embedding),
            }
        ]
        if embedding
        else [],
    }


def test_appearance_actually_changes_fragment_association_and_pair_benchmark():
    labels = {("f000000", "s1"): "actor-a", ("f000200", "s2"): "actor-a"}
    plain_segments = [segment("s1", [0]), segment("s2", [2])]
    plain, _, _ = reconcile_segments(plain_segments, TrackingConfig(mode="byte_track"))
    assert len(plain) == 2
    reid_segments = [segment("s1", [0]), segment("s2", [2])]
    reid, _, _ = reconcile_segments(reid_segments, TrackingConfig())
    assert len(reid) == 1
    evidence = reid[0]["association_evidence"][0]
    assert evidence["origin"] == "frozen_reid_and_motion" and evidence["similarity"] == 1
    assert evidence["review_status"] == "model_proposal"
    baseline_metrics = continuity_metrics({"segments": plain_segments}, labels)
    reid_metrics = continuity_metrics({"segments": reid_segments}, labels)
    assert baseline_metrics["false_split_pairs"] == 1
    assert reid_metrics["false_split_pairs"] == 0
    assert reid_metrics["false_merge_pairs"] == 0
    comparison = benchmark_continuity(
        {"source_sha256": "a" * 64, "segments": plain_segments},
        {"source_sha256": "a" * 64, "segments": reid_segments},
        labels,
        labels,
    )
    assert comparison["quality_measured"] is True  # Synthetic reviewed fixture only.
    with pytest.raises(ValueError, match="identical reviewed"):
        benchmark_continuity(
            {"source_sha256": "a" * 64, "segments": plain_segments},
            {"source_sha256": "a" * 64, "segments": reid_segments},
            labels,
            {("different-source-frame", "s1"): "actor-a", ("f000200", "s2"): "actor-a"},
        )
    # Same geometry/time but dissimilar appearance must remain separate.
    people, _, _ = reconcile_segments(
        [segment("s1", [0]), segment("s2", [2], (0, 1))], TrackingConfig()
    )
    assert len(people) == 2


@pytest.mark.parametrize(
    "other",
    [
        segment("s2", [0]),  # simultaneous people are never merged
        segment("s2", [20]),  # long absence
        segment("s2", [0.1], box=[0.7, 0.1, 0.9, 0.9]),  # impossible normalized speed
        segment("s2", [2], box=[0.1, 0.1, 0.2, 0.3]),  # incompatible body scale
        segment("s2", [2], embedding=None),  # visibility/quality yielded no embedding
    ],
)
def test_geometry_temporal_visibility_gates_prevent_forced_match(other):
    people, _, _ = reconcile_segments([segment("s1", [0]), other], TrackingConfig())
    assert len(people) == 2


def test_appearance_tie_preserves_unresolved_candidates_and_role_unknown():
    people, _, unresolved = reconcile_segments(
        [segment("s1", [0]), segment("s2", [0]), segment("s3", [2])], TrackingConfig()
    )
    assert len(people) == 3
    assert unresolved[0]["candidate_participant_ids"] == ["p0001", "p0002"]
    assert all(p["role_hypotheses"] == [] for p in people)


def test_reflection_similarity_does_not_create_person_or_invent_owner():
    people, views, _ = reconcile_segments(
        [segment("s1", [0]), segment("s2", [0], zone="mirror")], TrackingConfig()
    )
    assert len(people) == len(views) == 1
    assert views[0]["canonical_person_id"] is None and views[0]["ownership"] == "unknown"


class Detector:
    provenance = {"synthetic": True}

    def detect(self, image):
        return [(BOX, 0.9)]


class Tracker:
    def __init__(self, ids):
        self.ids = iter(ids)

    def update(self, boxes, timestamp):
        return [(next(self.ids), b, s) for b, s in boxes]


class SyntheticEmbedder:
    provenance = {"synthetic": True, "pretrained": False}

    def embed(self, image):
        pixel = image.getpixel((0, 0))
        return [1, 0] if pixel[0] > pixel[2] else [0, 1]


def frames(times=(0, 0.2, 2), colors=None):
    colors = colors or ["red"] * len(times)
    return [
        DecodedFrame(
            FrameRef(f"f{i:06d}", i, 1000 + int(t * 100), t),
            Image.new("RGB", (100, 100), color),
            "1/100",
            100,
            100,
        )
        for i, (t, color) in enumerate(zip(times, colors, strict=True))
    ]


@pytest.fixture
def offline(monkeypatch):
    # Synthetic fixtures only. Production code has no environment bypass.
    monkeypatch.setattr(
        "forte.frozen_tracking.require_outbound_blocked", lambda: {"synthetic": True}
    )


def test_callable_registry_bounds_gallery_preserves_pts_and_never_overwrites(tmp_path, offline):
    output = tmp_path / "new-run"
    registry = analyze_participants(
        frames(),
        output,
        {"source_sha256": "a" * 64, "gallery_size": 1},
        detector=Detector(),
        tracker=Tracker([1, 1, 9]),
        embedder=SyntheticEmbedder(),
    )
    assert len(registry["participants"]) == 1
    assert len(registry["participants"][0]["appearance_gallery"]) == 1
    assert registry["source_frames"][-1]["source_pts"] == 1200
    assert registry["sampled_source_frames"][-1]["time_base"] == "1/100"
    assert registry["frame_boxes"]["f000002"] == {"p0001": BOX}
    assert registry["provenance"]["human_approval_created"] is False
    original = (output / "participants.json").read_bytes()
    with pytest.raises(FileExistsError):
        analyze_participants(frames(), output, TrackingConfig(source_sha256="a" * 64))
    assert (output / "participants.json").read_bytes() == original


def test_tracker_id_switch_splits_conflicting_appearance(tmp_path, offline):
    registry = analyze_participants(
        frames((0, 0.2), ["red", "blue"]),
        tmp_path / "run",
        TrackingConfig(source_sha256="a" * 64),
        detector=Detector(),
        tracker=Tracker([1, 1]),
        embedder=SyntheticEmbedder(),
    )
    assert len(registry["participants"]) == 2
    assert (
        registry["participants"][1]["conflicts"][0]["reason"]
        == "appearance_conflicts_with_tracker_id"
    )


def test_low_quality_truncated_crops_cannot_supply_reid(tmp_path, offline):
    class TruncatedDetector(Detector):
        def detect(self, image):
            return [([0, 0.1, 0.5, 0.9], 0.9)]

    registry = analyze_participants(
        frames((0, 2)),
        tmp_path / "run",
        TrackingConfig(source_sha256="a" * 64),
        detector=TruncatedDetector(),
        tracker=Tracker([1, 9]),
        embedder=SyntheticEmbedder(),
    )
    assert len(registry["participants"]) == 2
    assert all(p["appearance_gallery"] == [] for p in registry["participants"])


def test_real_variable_pts_decode_and_redecode_source_binding(tmp_path, offline):
    source = tmp_path / "synthetic.mov"
    make_mov(source, pts=(100, 101, 102, 120, 130))
    decoded = decode_video(source, tmp_path / "cache")
    registry = analyze_participants(
        decoded,
        tmp_path / "tracking",
        TrackingConfig(mode="byte_track"),
        detector=Detector(),
        tracker=Tracker([1] * 100),
    )
    assert registry["source_frames"] == [
        {
            "frame_id": f.frame_id,
            "ordinal": f.ordinal,
            "source_pts": f.source_pts,
            "timestamp_sec": f.timestamp_sec,
        }
        for f in decoded.frames
    ]
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        analyze_participants(
            decoded,
            tmp_path / "changed",
            TrackingConfig(mode="byte_track"),
            detector=Detector(),
            tracker=Tracker([1]),
        )


def test_malformed_pts_and_image_transform_are_rejected(tmp_path, offline):
    sequence = frames()
    sequence[1].ref = FrameRef("f000001", 1, 9999, 0.2)
    with pytest.raises(ValueError, match="PTS"):
        analyze_participants(
            sequence,
            tmp_path / "bad",
            TrackingConfig(source_sha256="a" * 64),
            detector=Detector(),
            tracker=Tracker([1] * 3),
            embedder=SyntheticEmbedder(),
        )
    assert source_transform(100, 60, 90) == [0, 1, 0, -1, 0, 100]


def test_unsandboxed_execution_and_env_only_claim_are_rejected(monkeypatch):
    monkeypatch.setenv("FORTE_TRACKING_NETWORK_ISOLATION", "trust-me")

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def connect(self, address):
            assert address == ("192.0.2.1", 9)

    monkeypatch.setattr(socket, "socket", lambda *a: Socket())
    with pytest.raises(RuntimeError, match="OS-enforced"):
        require_outbound_blocked()
    monkeypatch.setattr(
        socket, "socket", lambda *a: (_ for _ in ()).throw(PermissionError(errno.EPERM, "denied"))
    )
    assert require_outbound_blocked()["outbound_probe"] == "os_denied"


def test_reid_manifest_refuses_missing_provenance_or_weight_mismatch(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"architecture": "osnet_x0_25"}))
    with pytest.raises(ValueError, match="documented"):
        LocalReIDONNX(manifest)
    (tmp_path / "features.onnx").write_bytes(b"synthetic-not-a-model")
    manifest.write_text(
        json.dumps(
            {
                "architecture": "osnet_x0_25",
                "weights": "features.onnx",
                "weights_sha256": "a" * 64,
                "input_size": [256, 128],
                "pretrained": {
                    "source": "official-public-test",
                    "revision": "test",
                    "checkpoint_sha256": "b" * 64,
                },
            }
        )
    )
    with pytest.raises(ValueError, match="hash/path"):
        LocalReIDONNX(manifest)


def test_ipv4_denial_is_insufficient_when_ipv6_has_outbound_route(monkeypatch):
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def connect(self, address):
            assert address == ("2001:db8::1", 9)

    def create(family, kind):
        if family == socket.AF_INET:
            raise PermissionError(errno.EPERM, "IPv4 denied")
        return Socket()

    monkeypatch.setattr(socket, "socket", create)
    with pytest.raises(RuntimeError, match="OS-enforced"):
        require_outbound_blocked()


def test_missing_real_reid_asset_fails_instead_of_byte_track_fallback(tmp_path, offline):
    with pytest.raises(ValueError, match="real local pretrained"):
        analyze_participants(frames(), tmp_path / "missing", TrackingConfig(source_sha256="a" * 64))


def test_outputs_inside_repository_are_rejected(offline):
    from pathlib import Path

    with pytest.raises(ValueError, match="outside Git"):
        analyze_participants(
            frames(), Path(__file__).resolve().parents[1] / "private", TrackingConfig()
        )
