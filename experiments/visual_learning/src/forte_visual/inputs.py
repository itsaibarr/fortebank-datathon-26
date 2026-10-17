"""Actor-bound scene/crop packs. References never enter inference metadata."""

import io
import math
import random
from pathlib import Path
from typing import Literal

from forte.video import decode_video, jpeg_bytes, nearest
from PIL import Image
from pydantic import Field

from forte_visual import adapter
from forte_visual.io import canonical, digest, private_dir, write
from forte_visual.release import Strict, local, verify


class View(Strict):
    view_id: str
    frame_id: str
    path: str
    sha256: str
    kind: Literal["scene", "crop"]
    # Source-oriented pixel rectangle and affine x'=sx*x+tx, y'=sy*y+ty.
    source_rect: tuple[int, int, int, int]
    source_to_view: tuple[float, float, float, float]
    width: int
    height: int


class InputCase(Strict):
    case_id: str
    group_id: str
    clip_id: str
    task: Literal["role", "action", "context", "coarse"]
    track_mode: Literal["oracle", "automatic"]
    actor_id: str
    # Alias -> supplied supported segment IDs, without semantic attributes.
    actors: dict[str, list[str]]
    track_boxes: dict[str, dict[str, list[tuple[float, float, float, float]]]]
    frames: dict[str, float]
    source_pts: dict[str, int]
    views: list[View] = Field(min_length=1, max_length=16)
    window: tuple[float, float]
    source_sha256: str
    mapping_sha256: str


class Answer(Strict):
    actor_id: str
    kind: Literal["role", "action", "context"]
    value: str = Field(min_length=1, max_length=80)
    other_actor_id: str | None = None
    start_frame_id: str
    end_frame_id: str
    continues_before_window: bool
    continues_after_window: bool
    evidence_frame_ids: list[str] = Field(min_length=1, max_length=16)
    visibility: Literal["observed", "unclear", "not_visible", "reviewed_absent"]


def validate_answer(case: InputCase, answer: Answer):
    if answer.actor_id != case.actor_id or answer.kind != case.task:
        raise ValueError("Answer substitutes target actor/task")
    if answer.other_actor_id is not None and (
        answer.other_actor_id not in case.actors or answer.other_actor_id == answer.actor_id
    ):
        raise ValueError("Unsupported participant relation")
    ids = [answer.start_frame_id, answer.end_frame_id, *answer.evidence_frame_ids]
    if not set(ids) <= case.frames.keys():
        raise ValueError("Invalid source reference")
    start, end = case.frames[answer.start_frame_id], case.frames[answer.end_frame_id]
    if start > end or any(not start <= case.frames[f] <= end for f in answer.evidence_frame_ids):
        raise ValueError("Unordered answer interval/evidence")
    if answer.visibility != "observed" and answer.value != "unclear":
        if answer.visibility != "reviewed_absent":
            raise ValueError("Unsupported visible assertion")
    if case.task == "role" and answer.value not in {"cashier", "customer", "unclear"}:
        raise ValueError("Unknown role")


def aliases(manifest, seed):
    # Do not collapse producer person IDs across unverified joins. Segment identity
    # components include only independently confirmed joins.
    components = {s.id: {s.id} for s in manifest.segments}
    for j in manifest.joins:
        if j.review.status == "confirmed":
            merged = components[j.from_segment] | components[j.to_segment]
            for s in merged:
                components[s] = merged
    unique = sorted({tuple(sorted(v)) for v in components.values()})
    rng = random.Random(seed)
    names = rng.sample(range(1, 9999), len(unique))
    items = [(f"p{n:04d}", list(c)) for n, c in zip(names, unique, strict=True)]
    rng.shuffle(items)
    return dict(items)


def crop_rect(boxes, width, height, padding=0.15):
    if not boxes:
        raise ValueError("No supported actor crop")
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    right, bottom = max(b[2] for b in boxes), max(b[3] for b in boxes)
    dx, dy = (right - left) * padding, (bottom - top) * padding
    return (
        max(0, math.floor((left - dx) * width)),
        max(0, math.floor((top - dy) * height)),
        min(width, math.ceil((right + dx) * width)),
        min(height, math.ceil((bottom + dy) * height)),
    )


def make_case(
    m,
    registry,
    directory,
    *,
    case_id,
    task,
    start,
    end,
    segments,
    counterpart=None,
    seed=0,
    track_mode="oracle",
):
    people = aliases(m, seed)
    actor = next((p for p, ss in people.items() if set(segments) <= set(ss)), None)
    if actor is None:
        raise ValueError("Target crosses unsupported identity join")
    frame_by_id = {f.frame_id: f for f in registry.frames}
    available = [
        f
        for f in registry.frames
        if f.frame_id in registry.cached and start <= f.timestamp_sec < end
    ]
    if not available:
        raise ValueError("No frames in window")
    count = 6 if task == "role" else 8
    times = (
        [
            available[0].timestamp_sec
            + i * (available[-1].timestamp_sec - available[0].timestamp_sec) / 5
            for i in range(6)
        ]
        if task == "role"
        else [start + i / 2 for i in range(8)]
    )
    selected = [nearest(available, t) for t in times if t < end]
    if len({f.frame_id for f in selected}) != count:
        raise ValueError("Insufficient distinct source times for prescribed task shape")
    segs = {s.id: s for s in m.segments}
    if any(segs[s].identity_uncertain for s in segments):
        raise ValueError("Uncertain target identity")
    other = next(
        (
            p
            for p, ss in people.items()
            if counterpart and any(segs[s].person_id == counterpart for s in ss)
        ),
        None,
    )
    if counterpart and other is None:
        raise ValueError("Counterpart identity unavailable")
    import base64

    extracted = {
        f.frame_id: e
        for f, e in zip(selected, registry.evidence([f.frame_id for f in selected]), strict=True)
    }
    views = []
    for f in selected:
        # Re-extract through shared source verification, never trust released JPEG
        # pixels as a substitute for source mapping.
        raw = base64.b64decode(extracted[f.frame_id].image_base64)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        if image.size != (m.oriented_width, m.oriented_height):
            raise ValueError("Source-oriented dimensions mismatch")
        wanted = set(segments) | (set(people[other]) if other else set())
        boxes = [
            b.xyxy
            for s in wanted
            for b in segs[s].boxes
            if b.frame_id == f.frame_id and not b.outside and not b.occluded
        ]
        if not any(
            b.frame_id == f.frame_id and not b.outside and not b.occluded
            for s in segments
            for b in segs[s].boxes
        ):
            raise ValueError("Target lacks visible source box at sampled time")
        for kind, rect in [
            ("scene", (0, 0, image.width, image.height)),
            ("crop", crop_rect(boxes, image.width, image.height)),
        ]:
            cropped = image.crop(rect)
            payload = jpeg_bytes(cropped, 196608)
            rendered = Image.open(io.BytesIO(payload))
            name = f"{case_id}-{f.frame_id}-{kind}.jpg"
            path = directory / "images" / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(payload)
            path.chmod(0o600)
            sx, sy = rendered.width / cropped.width, rendered.height / cropped.height
            views.append(
                View(
                    view_id=f"{f.frame_id}/{kind}",
                    frame_id=f.frame_id,
                    path=f"images/{name}",
                    sha256=digest(path),
                    kind=kind,
                    source_rect=rect,
                    source_to_view=(sx, sy, -rect[0] * sx, -rect[1] * sy),
                    width=rendered.width,
                    height=rendered.height,
                )
            )
    return InputCase(
        case_id=case_id,
        group_id=m.session_group or m.recording_group,
        clip_id=m.clip_id,
        task=task,
        track_mode=track_mode,
        actor_id=actor,
        actors=people,
        track_boxes={
            p: {
                f.frame_id: [
                    b.xyxy
                    for sid in ss
                    for b in segs[sid].boxes
                    if b.frame_id == f.frame_id and not b.outside
                ]
                for f in selected
            }
            for p, ss in people.items()
        },
        frames={f.frame_id: f.timestamp_sec for f in selected},
        source_pts={f.frame_id: frame_by_id[f.frame_id].source_pts for f in selected},
        views=views,
        window=(start, end),
        source_sha256=m.source_sha256,
        mapping_sha256=adapter.mapping_hash(),
    )


def export(path: Path, output: Path, *, training=False, seed=0):
    release, pairs, receipt = verify(path)
    private_dir(output)
    inputs = output / "inference"
    inputs.mkdir(mode=0o700)
    cases, references, excluded = [], {}, []
    for clip, m, a in pairs:
        registry = decode_video(local(path.parent, clip.media), output / "source-cache" / m.clip_id)
        if registry.source_sha256 != m.source_sha256 or registry.rotation != m.rotation:
            raise ValueError("Decoded source disagrees with producer")
        if [vars(f) for f in registry.frames] != [f.model_dump() for f in m.frames]:
            raise ValueError("Producer source frame/PTS registry mismatch")
        for f in adapter.reviewed_targets(m, a, training=training):
            start, end = f.playback_interval
            if f.kind != "role":
                start, end = max(start, f.start_sec), min(end, f.start_sec + 4)
            cid = f"c{len(cases):06d}"
            try:
                case = make_case(
                    m,
                    registry,
                    inputs,
                    case_id=cid,
                    task=f.kind,
                    start=start,
                    end=end,
                    segments=f.segment_ids,
                    counterpart=f.counterpart_actor_id,
                    seed=seed,
                    track_mode=clip.track_mode,
                )
                evidence = [id for id in f.frame_ids if id in case.frames]
                if not evidence:
                    raise ValueError("Target evidence lost by sampling")
                # Missing evidence inside this window is rejection, not truncation.
                if any(start <= a.frames[id] < end and id not in case.frames for id in f.frame_ids):
                    raise ValueError("Prescribed samples omit reviewed target evidence")
                frames = sorted(case.frames, key=case.frames.get)
                value = "unclear" if f.target_kind == "abstention" else f.value
                other = next(
                    (
                        p
                        for p, ss in case.actors.items()
                        if f.counterpart_actor_id
                        and any(
                            s.person_id == f.counterpart_actor_id and s.id in ss for s in m.segments
                        )
                    ),
                    None,
                )
                answer = Answer(
                    actor_id=case.actor_id,
                    kind=f.kind,
                    value=value,
                    other_actor_id=other,
                    start_frame_id=frames[0],
                    end_frame_id=frames[-1],
                    continues_before_window=f.start_sec < start,
                    continues_after_window=f.end_sec > case.frames[frames[-1]],
                    evidence_frame_ids=evidence,
                    visibility="unclear"
                    if value == "unclear"
                    else "reviewed_absent"
                    if f.observation_state == "not_observed_in_reviewed_interval"
                    else "observed",
                )
                validate_answer(case, answer)
            except ValueError as exc:
                excluded.append({"clip_id": m.clip_id, "fact_id": f.id, "reason": str(exc)})
                continue
            cases.append(case.model_dump())
            references[cid] = {
                "answer": answer.model_dump(),
                "split": m.split,
                "fact_id": f.id,
                "regression_only": m.regression_only,
                "group_id": case.group_id,
                "source_sha256": m.source_sha256,
                "duration_sec": m.duration_sec,
            }
    verify(path)
    write(inputs / "inputs.json", {"schema_version": 1, "seed": seed, "cases": cases})
    write(
        output / "reference/answers.json",
        {"inputs_sha256": digest(inputs / "inputs.json"), "cases": references},
    )
    write(
        output / "export.json",
        {
            "release": receipt,
            "cases": len(cases),
            "excluded": excluded,
            "training": training,
            "input_identity": canonical(cases),
        },
    )
    return len(cases)


def messages(case: InputCase, root):
    import base64

    content = [
        {
            "type": "text",
            "text": (
                f"Task {case.task}. Target {case.actor_id}. Supported tracks {case.actors}. "
                f"Normalized oriented source boxes by actor/frame: {case.track_boxes}. "
                "Use visible interaction evidence. "
                "Return unclear when actor, role or action is unsupported. "
                "Do not infer roles from departure, appearance or screen position. "
                "Do not infer transaction completion from departure. No law or identity claims. "
                "Return one JSON fact using this schema: " + str(Answer.model_json_schema())
            ),
        }
    ]
    for view in case.views:
        path = local(root, view.path)
        if digest(path) != view.sha256:
            raise ValueError("Input pixels changed")
        content.extend(
            [
                {
                    "type": "text",
                    "text": (
                        f"{view.view_id}; source {view.frame_id}; source rect {view.source_rect}; "
                        f"source-to-view affine {view.source_to_view}"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,"
                        + base64.b64encode(path.read_bytes()).decode()
                    },
                },
            ]
        )
    return [{"role": "user", "content": content}]
