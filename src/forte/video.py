"""Video-only source PTS registry, bounded samples and source-frame evidence."""

import base64
import bisect
import hashlib
import io
import json
import math
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import av
from PIL import Image

from forte.contracts import EvidenceFrame


def open_video(path: Path):
    return av.open(str(path), options={"protocol_whitelist": "file", "enable_drefs": "0"})


def probe_video(path: Path) -> dict:
    if path.stat().st_size > 268435456:
        raise ValueError("Video exceeds upload limit")
    try:
        with open_video(path) as container:
            if "mov" not in container.format.name.split(",") or len(container.streams.video) != 1:
                raise ValueError("Expected a MOV container with one video stream")
            stream = container.streams.video[0]
            w, h = stream.codec_context.width, stream.codec_context.height
            if not (0 < w <= 4096 and 0 < h <= 4096 and w * h <= 8_400_000):
                raise ValueError("Video dimensions exceed limits")
            duration = float(stream.duration * stream.time_base) if stream.duration else None
            if duration is not None and not 0 < duration <= 180:
                raise ValueError("Video duration exceeds limits")
            rotation = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream_side_data=rotation",
                    "-of",
                    "json",
                    str(path.resolve()),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            side_data = (
                json.loads(rotation.stdout).get("streams", [{}])[0].get("side_data_list", [])
            )
            angle = next(
                (x["rotation"] for x in side_data if "rotation" in x),
                float(stream.metadata.get("rotate", 0)),
            )
            return {"width": w, "height": h, "duration": duration, "rotation": angle}
    except av.error.FFmpegError as exc:
        raise ValueError("Unsupported or corrupt video") from exc


@dataclass(frozen=True)
class FrameRef:
    frame_id: str
    ordinal: int
    source_pts: int
    timestamp_sec: float


def jpeg_bytes(image: Image.Image, max_pixels: int) -> bytes:
    if image.width * image.height > max_pixels:
        scale = math.sqrt(max_pixels / (image.width * image.height))
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def oriented(frame, stream, rotation=0):
    angle = frame.rotation or rotation or float(stream.metadata.get("rotate", 0))
    if angle % 90:
        raise ValueError("Unsupported non-right-angle display rotation")
    return frame.to_image().rotate(angle, expand=True) if angle else frame.to_image()


@dataclass
class VideoRegistry:
    path: Path
    duration: float
    frames: list[FrameRef]
    source_sha256: str
    rotation: float = 0
    cached: dict[str, Path] = field(default_factory=dict)

    def image_bytes(self, ref: FrameRef, max_pixels: int) -> bytes:
        with Image.open(self.cached[ref.frame_id]) as image:
            return jpeg_bytes(image, max_pixels)

    def evidence(self, ids: list[str]) -> list[EvidenceFrame]:
        wanted = set(ids)
        if not wanted <= {f.frame_id for f in self.frames}:
            raise ValueError("Unknown source frame")
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.source_sha256:
            raise ValueError("Source changed after decoding")
        selected = {f.ordinal: f for f in self.frames if f.frame_id in wanted}
        result = []
        with open_video(self.path) as container:
            stream = container.streams.video[0]
            stream.codec_context.thread_count = 1
            for i, frame in enumerate(container.decode(stream)):
                if i in selected:
                    ref = selected[i]
                    if frame.pts != ref.source_pts:
                        raise ValueError("Source frame association changed")
                    raw = jpeg_bytes(oriented(frame, stream, self.rotation), 4_194_304)
                    result.append(
                        EvidenceFrame(
                            timestamp_sec=ref.timestamp_sec,
                            image_base64=base64.b64encode(raw).decode(),
                        )
                    )
                if selected and i >= max(selected):
                    break
        if len(result) != len(wanted):
            raise ValueError("Could not re-extract evidence")
        return result


def nearest(frames: list[FrameRef], target: float) -> FrameRef:
    index = bisect.bisect_left([f.timestamp_sec for f in frames], target)
    choices = frames[max(0, index - 1) : min(len(frames), index + 1)]
    return min(choices, key=lambda f: abs(f.timestamp_sec - target))


def decode_video(path: Path, cache: Path, deadline: float | None = None) -> VideoRegistry:
    metadata = probe_video(path)
    deadline = deadline or time.monotonic() + 270
    frames = []
    last_span = 0.0
    try:
        with open_video(path) as container:
            stream = container.streams.video[0]
            stream.codec_context.thread_count = 1
            origin = None
            for i, frame in enumerate(container.decode(stream)):
                if time.monotonic() > deadline or i >= 60000:
                    raise ValueError("Decode resource limit exceeded")
                if frame.pts is None or frame.is_corrupt:
                    raise ValueError("Untrustworthy source timestamps or corrupt frame")
                source_time = float(frame.pts * frame.time_base)
                if origin is None:
                    origin = source_time
                timestamp = source_time - origin
                if timestamp > 180 or (frames and timestamp <= frames[-1].timestamp_sec):
                    raise ValueError("Invalid source duration or presentation order")
                last_span = float(frame.duration * frame.time_base) if frame.duration else 0
                frames.append(FrameRef(f"f{i:06d}", i, frame.pts, timestamp))
            if not frames:
                raise ValueError("No decoded video frames")
            if last_span <= 0:
                last_span = 1 / float(stream.average_rate) if stream.average_rate else 0.04
        duration = frames[-1].timestamp_sec + last_span
        if not 0 < duration <= 180:
            raise ValueError("Video duration exceeds limits")
        if metadata["duration"] and metadata["duration"] - duration > max(0.5, 2 * last_span):
            raise ValueError("Incomplete video decode")
        registry = VideoRegistry(
            path,
            duration,
            frames,
            hashlib.sha256(path.read_bytes()).hexdigest(),
            rotation=metadata["rotation"],
        )
        targets = [i / 2 for i in range(math.ceil(duration * 2))]
        selected = {nearest(frames, t).ordinal for t in targets} | {frames[-1].ordinal}
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open_video(path) as container:
            stream = container.streams.video[0]
            stream.codec_context.thread_count = 1
            for i, frame in enumerate(container.decode(stream)):
                if time.monotonic() > deadline:
                    raise ValueError("Decode resource limit exceeded")
                if i in selected:
                    ref = frames[i]
                    target = cache / (ref.frame_id + ".jpg")
                    target.write_bytes(
                        jpeg_bytes(oriented(frame, stream, registry.rotation), 393216)
                    )
                    registry.cached[ref.frame_id] = target
        if len(registry.cached) != len(selected):
            raise ValueError("Incomplete sampling pass")
        return registry
    except av.error.FFmpegError as exc:
        raise ValueError("Corrupt video decode") from exc


def make_windows(duration: float, size: float, stride: float) -> list[tuple[float, float]]:
    if not 0 < stride <= size or duration <= 0:
        raise ValueError("Invalid coverage schedule")
    windows = []
    start = 0.0
    while start < duration:
        end = min(duration, start + size)
        windows.append((start, end))
        if end == duration:
            break
        start += stride
    return windows


def sample_window(registry: VideoRegistry, start: float, end: float, fps: float):
    candidates = [
        f
        for f in registry.frames
        if f.frame_id in registry.cached and start <= f.timestamp_sec < end
    ]
    if not candidates:
        raise ValueError("No frames for requested window")
    count = min(16, max(1, math.ceil((end - start) * fps)))
    selected = {nearest(candidates, start + i / fps).frame_id for i in range(count)}
    if end >= registry.duration:
        if len(selected) == 16:
            selected.remove(
                max(
                    (f for f in candidates if f.frame_id in selected), key=lambda f: f.timestamp_sec
                ).frame_id
            )
        selected.add(candidates[-1].frame_id)
    return [f for f in candidates if f.frame_id in selected]
