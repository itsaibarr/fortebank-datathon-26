"""Actor-bound scene/crop packs. References never enter inference metadata."""

import io
import math
import random
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import Field

from forte.video import decode_video, jpeg_bytes, nearest
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


class RoleHint(Strict):
    actor_id: str
    segment_ids: list[str]
    value: Literal["cashier", "customer", "unclear"]
    supported_window: tuple[float, float]
    evidence_frame_ids: list[str]
    origin: Literal["model"] = "model"
    review_status: Literal["unreviewed"] = "unreviewed"


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
    predicted_roles: list[RoleHint] = Field(default_factory=list)


class Answer(Strict):
    actor_id: str
    kind: Literal["role", "action", "context"]
    value: str = Field(min_length=1, max_length=80)
    other_actor_id: str | None = None
    other_actor_evidence_frame_ids: list[str] = Field(default_factory=list, max_length=16)
    actor_participation: Literal["giver", "receiver", "actor", "unclear"] = "unclear"
    service_completion_uncertain: bool = True
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
    if answer.other_actor_id and (
        not answer.other_actor_evidence_frame_ids
        or any(
            id not in case.frames or not case.track_boxes.get(answer.other_actor_id, {}).get(id)
            for id in answer.other_actor_evidence_frame_ids
        )
    ):
        raise ValueError("Counterpart needs separate supplied source evidence")
    ids = [answer.start_frame_id, answer.end_frame_id, *answer.evidence_frame_ids]
    if not set(ids) <= case.frames.keys():
        raise ValueError("Invalid source reference")
    if any(not case.track_boxes.get(answer.actor_id, {}).get(id) for id in ids):
        raise ValueError("Actor lacks source box at cited frame")
    start, end = case.frames[answer.start_frame_id], case.frames[answer.end_frame_id]
    if start > end or any(
        not start <= case.frames[f] <= end
        for f in answer.evidence_frame_ids + answer.other_actor_evidence_frame_ids
    ):
        raise ValueError("Unordered answer interval/evidence")
    if answer.visibility != "observed" and answer.value != "unclear":
        if answer.visibility != "reviewed_absent":
            raise ValueError("Unsupported visible assertion")
    if case.task == "role" and answer.value not in {"cashier", "customer", "unclear"}:
        raise ValueError("Unknown role")
    if (
        case.task == "role"
        and answer.value != "unclear"
        and len({case.frames[id] for id in answer.evidence_frame_ids}) < 2
    ):
        raise ValueError("Certain role needs temporally separated evidence")


def aliases(manifest, seed):
    # Do not collapse producer person IDs across unverified joins. Segment identity
    # components include only independently confirmed joins.
    components = {s.id: {s.id} for s in manifest.segments}
    for j in manifest.joins:
        if j.review.status == "confirmed":
            merged = components[j.from_segment] | components[j.to_segment]
            for s in merged:
                components[s] = merged
    known_reflections = set()
    for relation in manifest.view_relations:
        if relation.review.status == "confirmed":
            direct, reflected = relation.direct_segment_id, relation.reflected_segment_id
            merged = components[direct] | components[reflected]
            for s in merged:
                components[s] = merged
            known_reflections.add(reflected)
    # A confirmed reflection with unknown ownership is a view, never a newly
    # counted physical person or an automatic role-abstention training target.
    unknown_reflections = {
        v.segment_id
        for v in manifest.view_observations
        if v.review.status == "confirmed" and v.view_kind == "reflection"
    } - known_reflections
    unique = sorted(
        {tuple(sorted(v)) for k, v in components.items() if k not in unknown_reflections}
    )
    rng = random.Random(f"{seed}:{manifest.source_sha256}")
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
    counterpart_segments=None,
    seed=0,
    track_mode="oracle",
    allow_occluded=False,
    max_pixels=196608,
    allow_missing_target=False,
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
        else [available[0].timestamp_sec + i / 2 for i in range(8)]
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
            if counterpart
            and (
                set(counterpart_segments or []) <= set(ss)
                and any(segs[s].person_id == counterpart for s in ss)
            )
        ),
        None,
    )
    if counterpart and other is None:
        raise ValueError("Counterpart identity unavailable")
    visible = {
        f.frame_id: any(
            b.frame_id == f.frame_id and not b.outside and (allow_occluded or not b.occluded)
            for s in segments
            for b in segs[s].boxes
        )
        for f in selected
    }
    if not any(visible.values()) or (not allow_missing_target and not all(visible.values())):
        raise ValueError("Target lacks visible source box at sampled time")
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
            if b.frame_id == f.frame_id and not b.outside and (allow_occluded or not b.occluded)
        ]
        rectangles = [("scene", (0, 0, image.width, image.height))]
        if visible[f.frame_id]:
            rectangles.append(("crop", crop_rect(boxes, image.width, image.height)))
        # Missing-target context is a full scene, never an invented/interpolated
        # crop or an absence fact. Cited actor evidence still requires a real box.
        for kind, rect in rectangles:
            cropped = image.crop(rect)
            payload = jpeg_bytes(cropped, max_pixels)
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
        if m.split == "test" or (training and m.split not in {"train", "validation"}):
            continue
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
                    counterpart_segments=f.counterpart_segment_ids,
                    seed=seed,
                    track_mode=clip.track_mode,
                    allow_occluded=f.target_kind == "abstention",
                )
                evidence = [id for id in f.frame_ids if id in case.frames]
                if not evidence:
                    raise ValueError("Target evidence lost by sampling")
                if f.counterpart_actor_id and not set(f.counterpart_frame_ids).intersection(
                    case.frames
                ):
                    raise ValueError("Counterpart evidence is outside supplied task window")
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
                    other_actor_evidence_frame_ids=[
                        id for id in f.counterpart_frame_ids if id in case.frames
                    ],
                    actor_participation=f.actor_participation,
                    service_completion_uncertain=f.service_completion_uncertain,
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

    # Prompt precision only. Source geometry in the case/manifest is unchanged.
    shown_boxes = {
        a: {
            f: [[round(v, 4) for v in box] for box in boxes] for f, boxes in frames.items() if boxes
        }
        for a, frames in case.track_boxes.items()
    }
    visible_actors = {a: ss for a, ss in case.actors.items() if shown_boxes.get(a)}
    content = [
        {
            "type": "text",
            "text": (
                f"Task {case.task}. Target {case.actor_id}. Supported tracks {visible_actors}. "
                f"Oriented source boxes by actor/frame (normalized, 4 decimals): {shown_boxes}. "
                f"Prior unreviewed model role hints, restricted to their evidence intervals: "
                f"{[hint.model_dump() for hint in case.predicted_roles]}. "
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


def validate_pack(release_path, input_path, references=None, *, training=False):
    """Bind an exported pack back to the reviewed source, not just its JSON shape."""
    from forte_visual.benchmark import load_cases

    release, pairs, receipt = verify(release_path)
    by_clip = {m.clip_id: (clip, m, a) for clip, m, a in pairs}
    refs = None
    if references is not None:
        from forte_visual.io import read

        refs = read(references)
        if refs["inputs_sha256"] != digest(input_path):
            raise ValueError("Reference pack mismatch")
    cases = load_cases(input_path)
    from forte_visual.io import read

    seed = read(input_path)["seed"]
    if refs and set(refs["cases"]) != {c.case_id for c in cases}:
        raise ValueError("Reference completeness mismatch")
    for case in cases:
        if case.predicted_roles:
            raise ValueError("Frozen benchmark/training inputs cannot contain prior role answers")
        clip, m, a = by_clip[case.clip_id]
        if case.actors != aliases(m, seed):
            raise ValueError("Anonymous IDs or supported identity components changed")
        source = {f.frame_id: f for f in m.frames}
        if case.source_sha256 != m.source_sha256 or case.track_mode != clip.track_mode:
            raise ValueError("Input source/tracker mismatch")
        if case.mapping_sha256 != adapter.mapping_hash():
            raise ValueError("Consumer mapping changed since export")
        if any(
            id not in source
            or source[id].timestamp_sec != t
            or source[id].source_pts != case.source_pts[id]
            for id, t in case.frames.items()
        ):
            raise ValueError("Input frame timing mismatch")
        if any(
            v.frame_id not in case.frames
            or v.source_rect[0] < 0
            or v.source_rect[1] < 0
            or not v.source_rect[0] < v.source_rect[2] <= m.oriented_width
            or not v.source_rect[1] < v.source_rect[3] <= m.oriented_height
            for v in case.views
        ):
            raise ValueError("Input crop/source provenance mismatch")
        # Pixel files are opaque paths; labels/points/role attributes are never admitted.
        for v in case.views:
            if digest(local(input_path.parent, v.path)) != v.sha256:
                raise ValueError("Frozen pixels changed")
        if refs:
            ref = refs["cases"][case.case_id]
            eligible = {f.id: f for f in adapter.reviewed_targets(m, a, training=training)}
            if ref["fact_id"] not in eligible or ref["split"] != m.split:
                raise ValueError("Reference not eligible in producer release")
            fact = eligible[ref["fact_id"]]
            answer = Answer.model_validate(ref["answer"])
            validate_answer(case, answer)
            if answer.value != fact.value or not set(fact.segment_ids) <= set(
                case.actors[answer.actor_id]
            ):
                raise ValueError("Reference changed actor or reviewed target")
            if answer.actor_participation != fact.actor_participation:
                raise ValueError("Reference changed reviewed participant direction")
            if answer.service_completion_uncertain != fact.service_completion_uncertain:
                raise ValueError("Reference changed service uncertainty")
            if fact.counterpart_actor_id:
                if (
                    not answer.other_actor_id
                    or not set(fact.counterpart_segment_ids)
                    <= set(case.actors[answer.other_actor_id])
                    or not set(answer.other_actor_evidence_frame_ids)
                    <= set(fact.counterpart_frame_ids)
                ):
                    raise ValueError("Reference changed reviewed counterpart evidence")
            elif answer.other_actor_id:
                raise ValueError("Reference invents a known counterpart")
            if not set(answer.evidence_frame_ids) <= set(fact.frame_ids):
                raise ValueError("Reference evidence not independently reviewed")
            if training and (m.regression_only or not m.training_eligible):
                raise ValueError("Ineligible source in training pack")
    return receipt
