from fractions import Fraction
from pathlib import Path

import av
import pytest
from PIL import Image

from forte.video import decode_video, make_windows, probe_video, sample_window


def make_mov(path: Path, pts=(100, 104, 111, 120, 130), rotation=0):
    with av.open(str(path), "w", format="mov") as out:
        stream = out.add_stream("mpeg4", rate=10)
        stream.width, stream.height = 96, 64
        stream.pix_fmt = "yuv420p"
        stream.set_display_rotation(rotation)
        stream.time_base = Fraction(1, 10)
        for i, p in enumerate(pts):
            f = av.VideoFrame.from_image(Image.new("RGB", (96, 64), "red" if i == 2 else "blue"))
            f.pts, f.time_base = p, Fraction(1, 10)
            for packet in stream.encode(f):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path


def test_variable_source_pts_not_frame_index_and_real_evidence(tmp_path):
    path = make_mov(tmp_path / "source.mov")
    info = probe_video(path)
    assert info["width"] == 96
    registry = decode_video(path, tmp_path / "frames")
    times = [f.timestamp_sec for f in registry.frames]
    assert times == pytest.approx([0, 0.4, 1.1, 2, 3])
    red = registry.frames[2]
    jpeg = registry.evidence([red.frame_id])[0]
    import base64
    import io

    pixel = Image.open(io.BytesIO(base64.b64decode(jpeg.image_base64))).getpixel((40, 30))
    assert pixel[0] > pixel[2] + 100
    assert jpeg.timestamp_sec == pytest.approx(1.1)
    with pytest.raises(ValueError):
        registry.evidence(["invented"])


def test_window_coverage_and_limits_include_last_source_frame(tmp_path):
    registry = decode_video(make_mov(tmp_path / "short.mov"), tmp_path / "cache")
    windows = make_windows(registry.duration, 16, 12)
    assert windows[0][0] == 0 and windows[-1][1] == registry.duration
    frames = sample_window(registry, *windows[-1], fps=1)
    assert 1 <= len(frames) <= 16
    assert frames[-1].frame_id == registry.frames[-1].frame_id
    windows = make_windows(145, 16, 12)
    assert all(b[0] <= a[1] for a, b in zip(windows, windows[1:], strict=False))
    assert windows[-1][1] == 145


def test_bad_formats_and_actual_duration_are_rejected(tmp_path):
    invalid = tmp_path / "bad.mov"
    invalid.write_bytes(b"not a movie")
    with pytest.raises(ValueError):
        probe_video(invalid)
    long = make_mov(tmp_path / "long.mov", (0, 1900))
    with pytest.raises(ValueError):
        decode_video(long, tmp_path / "long-cache")


def test_evidence_refuses_a_changed_source(tmp_path):
    path = make_mov(tmp_path / "original.mov")
    registry = decode_video(path, tmp_path / "cache")
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="changed"):
        registry.evidence([registry.frames[0].frame_id])


def test_display_rotation_is_applied_to_samples_and_evidence(tmp_path):
    rotated = make_mov(tmp_path / "rotated.mov", rotation=90)
    registry = decode_video(rotated, tmp_path / "cache")
    assert registry.rotation == 90
    with Image.open(next(iter(registry.cached.values()))) as image:
        assert image.size == (64, 96)
