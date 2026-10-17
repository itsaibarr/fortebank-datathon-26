"""Complete duration scheduling and bounded internal visual timeline; no verdicts."""

import base64
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from forte.video import decode_video, make_windows, sample_window
from forte_visual.inputs import (
    Answer,
    InputCase,
    RoleHint,
    View,
    aliases,
    make_case,
    validate_answer,
)
from forte_visual.io import digest, private_dir, write


def union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def complement(intervals, duration):
    result, cursor = [], 0
    for start, end in union(intervals):
        if start > cursor:
            result.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < duration:
        result.append([cursor, duration])
    return result


def fine_windows(center, duration):
    start = max(0, min(center - 4, duration - 8))
    return [(s, min(duration, s + 4)) for s in (start, start + 2, start + 4) if s < duration]


@dataclass
class Bounds:
    deadline: float
    max_calls: int = 48
    max_tokens: int = 100000
    max_memory_bytes: int = 80 * 1024**3
    calls: int = 0
    tokens: int = 0
    peak_memory_bytes: int = 0
    clock: object = time.monotonic
    receipts: list = field(default_factory=list)

    def check(self):
        if (
            self.clock() >= self.deadline
            or self.calls >= self.max_calls
            or self.tokens >= self.max_tokens
        ):
            raise TimeoutError("Scan budget exhausted")

    def invoke(self, executor, request, root):
        self.check()
        self.calls += 1
        remaining = self.deadline - self.clock()
        began = self.clock()
        receipt = {
            "task": request.task if request else None,
            "window": request.window if request else None,
            "images": len(request.views) if request else None,
        }
        try:
            response = executor(request, root, remaining)
            receipt.update(
                {
                    k: response.get(k)
                    for k in (
                        "input_tokens",
                        "output_tokens",
                        "peak_memory_bytes",
                        "memory_samples",
                    )
                }
            )
        except Exception as exc:
            receipt["error"] = type(exc).__name__
            raise
        finally:
            receipt["seconds"] = self.clock() - began
            self.receipts.append(receipt)
        self.tokens += response.get("input_tokens", 0) + response.get("output_tokens", 0)
        self.peak_memory_bytes = max(self.peak_memory_bytes, response.get("peak_memory_bytes") or 0)
        if (
            response.get("input_tokens", 0) + 768 > 8192
            or response.get("output_tokens", 0) > 768
            or self.tokens > self.max_tokens
            or self.peak_memory_bytes > self.max_memory_bytes
            or self.clock() >= self.deadline
        ):
            raise TimeoutError("Scan executor exceeded budget")
        return response


@dataclass
class RoleCache:
    values: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)

    def add(self, clip_id, segment_ids, fact):
        key = (clip_id, tuple(sorted(segment_ids)))
        old = self.values.get(key)
        if old and old["value"] != fact["value"]:
            self.conflicts.append({"segments": list(segment_ids), "facts": [old, fact]})
            self.values[key] = {"value": "unclear", "origin": "model", "conflict": True}
            return
        # Agreement does not upgrade origin or review status.
        self.values[key] = {**fact, "origin": "model", "review_status": "unreviewed"}


def role_hints(cache, case, manifest):
    result = []
    for actor, segments in case.actors.items():
        cached = cache.values.get((case.clip_id, tuple(sorted(segments))))
        if not cached or "start_sec" not in cached:
            continue
        if not cached["start_sec"] <= case.window[0] <= case.window[1] <= cached["end_sec"]:
            continue
        if any(
            set(gap.segment_ids).intersection(segments)
            and max(gap.start_sec, case.window[0]) < min(gap.end_sec, case.window[1])
            for gap in manifest.gaps
        ):
            continue
        result.append(
            RoleHint(
                actor_id=actor,
                segment_ids=segments,
                value=cached["value"],
                supported_window=(cached["start_sec"], cached["end_sec"]),
                evidence_frame_ids=cached["evidence_frame_ids"],
            )
        )
    return result


def assemble(facts):
    """Merge only overlaps with same supported segment component and participants.

    Open/clipped outer boundaries stay open. No gap bridging, identity guessing or
    inferred completion. Contradictions remain explicit timeline facts.
    """
    result = []
    for fact in sorted(facts, key=lambda f: (f["start_sec"], f["end_sec"])):
        merged = False
        for old in result:
            relation = (
                "clip_id",
                "segments",
                "actor_id",
                "other_actor_id",
                "actor_participation",
                "kind",
                "value",
                "visibility",
            )
            if all(old.get(k) == fact.get(k) for k in relation) and (
                max(old["start_sec"], fact["start_sec"]) <= min(old["end_sec"], fact["end_sec"])
            ):
                if fact["start_sec"] == old["start_sec"]:
                    old["continues_before_window"] &= fact["continues_before_window"]
                if fact["end_sec"] > old["end_sec"]:
                    old["continues_after_window"] = fact["continues_after_window"]
                    old["end_frame_id"] = fact["end_frame_id"]
                elif fact["end_sec"] == old["end_sec"]:
                    old["continues_after_window"] &= fact["continues_after_window"]
                old["end_sec"] = max(old["end_sec"], fact["end_sec"])
                old["evidence_frame_ids"] = sorted(
                    set(old["evidence_frame_ids"]) | set(fact["evidence_frame_ids"])
                )
                old["other_actor_evidence_frame_ids"] = sorted(
                    set(old.get("other_actor_evidence_frame_ids", []))
                    | set(fact.get("other_actor_evidence_frame_ids", []))
                )
                merged = True
                break
        if not merged:
            result.append(dict(fact))
    for item in result:
        item["contradiction"] = any(
            other is not item
            and other["clip_id"] == item["clip_id"]
            and other["segments"] == item["segments"]
            and other["actor_id"] == item["actor_id"]
            and other["kind"] == item["kind"]
            and (
                item["kind"] == "role"
                or (
                    item["kind"] == "context"
                    and context_family(item["value"]) is not None
                    and context_family(item["value"]) == context_family(other["value"])
                )
            )
            and other["value"] != item["value"]
            and max(other["start_sec"], item["start_sec"]) <= min(other["end_sec"], item["end_sec"])
            for other in result
        )
    return result


def context_family(value):
    if value in {"cash_acceptance", "cash_payout", "collection_handoff", "cash_processing"}:
        return "operation_phase"
    if value in {"service_ongoing", "service_complete"}:
        return "service_state"
    return None


class MockScanExecutor:
    def __call__(self, request, root, timeout):
        # Deterministic no-fact response, not a false negative visual claim.
        return {"facts": [], "proposals": [], "input_tokens": 128, "output_tokens": 16}


def coarse_case(m, registry, output, start, end, seed):
    frames = sample_window(registry, start, end, fps=1)
    people = aliases(m, seed)
    ids = {f.frame_id for f in frames}
    people = {
        p: ss
        for p, ss in people.items()
        if any(
            b.frame_id in ids and not b.outside for s in m.segments if s.id in ss for b in s.boxes
        )
    }
    views = []
    # One verified extraction pass per window, not one full decode per image.
    extracted = registry.evidence([f.frame_id for f in frames])
    for f, evidence in zip(frames, extracted, strict=True):
        raw = base64.b64decode(evidence.image_base64)
        import io

        from PIL import Image

        from forte.video import jpeg_bytes

        image = Image.open(io.BytesIO(raw))
        payload = jpeg_bytes(image, 196608)
        size = Image.open(io.BytesIO(payload)).size
        name = f"coarse-{f.frame_id}.jpg"
        target = output / name
        if not target.exists():
            target.write_bytes(payload)
            target.chmod(0o600)
        views.append(
            View(
                view_id=f.frame_id + "/scene",
                frame_id=f.frame_id,
                path=name,
                sha256=digest(target),
                kind="scene",
                source_rect=(0, 0, m.oriented_width, m.oriented_height),
                source_to_view=(size[0] / m.oriented_width, size[1] / m.oriented_height, 0, 0),
                width=size[0],
                height=size[1],
            )
        )
    return InputCase(
        case_id=f"coarse-{start}",
        group_id=m.session_group or m.recording_group,
        clip_id=m.clip_id,
        task="coarse",
        track_mode="automatic",
        actor_id="scene",
        actors=people,
        track_boxes={
            p: {
                f.frame_id: [
                    b.xyxy
                    for segment in m.segments
                    if segment.id in ss
                    for b in segment.boxes
                    if b.frame_id == f.frame_id and not b.outside
                ]
                for f in frames
            }
            for p, ss in people.items()
        },
        frames={f.frame_id: f.timestamp_sec for f in frames},
        source_pts={f.frame_id: f.source_pts for f in frames},
        views=views,
        window=(start, end),
        source_sha256=m.source_sha256,
        mapping_sha256="scan/1",
    )


def bind_facts(case, raw_facts, m):
    result = []
    segments = {s.id: s for s in m.segments}
    for raw in raw_facts:
        answer = Answer.model_validate(raw)
        if answer.actor_id not in case.actors:
            raise ValueError("Unprovided actor")
        specific = case.model_copy(update={"task": answer.kind, "actor_id": answer.actor_id})
        if case.task != "coarse" and (
            answer.actor_id != case.actor_id or (case.task == "role" and answer.kind != "role")
        ):
            raise ValueError("Target actor/task substitution")
        if answer.visibility == "reviewed_absent":
            raise ValueError(
                "Runtime absence requires independently validated complete opportunity"
            )
        validate_answer(specific, answer)
        owned = case.actors[answer.actor_id]
        for frame_id in [answer.start_frame_id, answer.end_frame_id, *answer.evidence_frame_ids]:
            if not any(
                b.frame_id == frame_id and not b.outside and not b.occluded
                for s in owned
                for b in segments[s].boxes
            ):
                raise ValueError("Fact actor absent at cited source frame")
        if any(segments[s].identity_uncertain for s in owned) and answer.value != "unclear":
            raise ValueError("Uncertain identity cannot support assertion")
        if answer.other_actor_id:
            other = case.actors[answer.other_actor_id]
            if not any(
                b.frame_id in answer.other_actor_evidence_frame_ids
                and not b.outside
                and not b.occluded
                for s in other
                for b in segments[s].boxes
            ):
                raise ValueError("Counterpart lacks source evidence")
        result.append(
            {
                **answer.model_dump(),
                "clip_id": m.clip_id,
                "segments": owned,
                "start_sec": case.frames[answer.start_frame_id],
                "end_sec": case.frames[answer.end_frame_id],
                "origin": "model",
            }
        )
    return result


def inside(point, polygon):
    x, y = point
    result = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            result = not result
    return result


def geometry_proposals(m):
    frames = {f.frame_id: f.timestamp_sec for f in m.frames}
    proposals = []
    for s in m.segments:
        for area in m.work_areas:
            previous = None
            for box in s.boxes:
                if box.outside or box.occluded:
                    previous = None
                    continue
                x1, y1, x2, y2 = box.xyxy
                state = inside(((x1 + x2) / 2, (y1 + y2) / 2), area.points)
                if previous is not None and state != previous:
                    proposals.append((frames[box.frame_id], s.id, "area_crossing"))
                previous = state
    for gap in m.gaps:
        for s in gap.segment_ids:
            proposals.append(((gap.start_sec + gap.end_sec) / 2, s, "track_gap"))
    return proposals


def scan(
    m,
    media: Path,
    output: Path,
    executor=None,
    bounds=None,
    *,
    upload_started=None,
    seed=0,
    registry=None,
):
    started = upload_started if upload_started is not None else time.monotonic()
    bounds = bounds or Bounds(deadline=started + 270)
    executor = executor or MockScanExecutor()
    private_dir(output)
    facts, failures, proposals, sampled, inspected, scheduled = [], [], [], set(), [], []
    roles = RoleCache()
    status = "complete_schedule"
    visibility, areas = [], []
    participant_pairs = {}

    def assess(case, response):
        from forte_visual.live import validate_response

        validated = validate_response(
            case,
            {
                k: response[k]
                for k in ("facts", "proposals", "work_areas", "visibility")
                if k in response
            },
        )
        for item in validated.visibility:
            visibility.append(
                {
                    "start_sec": case.frames[item.start_frame_id],
                    "end_sec": case.frames[item.end_frame_id],
                    "state": item.state,
                    "model_resolution_assessment": item.object_resolution_adequate,
                    "origin": "model",
                    "continuous_visibility_validated": False,
                }
            )
        for area in validated.work_areas:
            areas.append({**area.model_dump(), "origin": "model", "review_status": "draft"})

    try:
        bounds.check()
        registry = registry or decode_video(
            media, output / "source-cache", deadline=bounds.deadline
        )
        if registry.source_sha256 != m.source_sha256 or registry.rotation != m.rotation:
            raise ValueError("Scan source mismatch")
        if [vars(f) for f in registry.frames] != [f.model_dump() for f in m.frames]:
            raise ValueError("Scan frame registry mismatch")
        windows = make_windows(m.duration_sec, 16, 12)
        proposals.extend(geometry_proposals(m))
        for start, end in windows:
            bounds.check()
            case = coarse_case(m, registry, output, start, end, seed)
            try:
                case.predicted_roles = role_hints(roles, case, m)
                response = bounds.invoke(executor, case, output)
                assess(case, response)
                sampled.update(case.frames)
                scheduled.append([start, end])
                observations = bind_facts(case, response.get("facts", []), m)
                facts.extend(observations)
                for observation in observations:
                    if observation["kind"] == "role":
                        roles.add(m.clip_id, observation["segments"], observation)
                    elif observation["kind"] == "action" and observation["value"] != "unclear":
                        segment = observation["segments"][0]
                        proposals.append(
                            (
                                (observation["start_sec"] + observation["end_sec"]) / 2,
                                segment,
                                "coarse_visual_action",
                            )
                        )
                        if observation["other_actor_id"]:
                            participant_pairs[segment] = case.actors[observation["other_actor_id"]]
                for p in response.get("proposals", []):
                    if p["frame_id"] not in case.frames or p["actor_id"] not in case.actors:
                        raise ValueError("Invalid proposal source/track")
                    proposals.append(
                        (case.frames[p["frame_id"]], case.actors[p["actor_id"]][0], "model_action")
                    )
            except TimeoutError:
                raise
            except Exception as exc:
                failures.append(
                    {"stage": "coarse", "window": [start, end], "error": type(exc).__name__}
                )
        people = aliases(m, seed)
        if areas:
            from forte.tracking import WorkArea

            predicted = m.model_copy(
                update={
                    "work_areas": [
                        WorkArea(
                            id=f"predicted-area-{i}",
                            frame_ids=a["frame_ids"],
                            points=a["points"],
                            notes="Unreviewed model-origin runtime proposal",
                        )
                        for i, a in enumerate(areas)
                    ]
                }
            )
            proposals.extend(geometry_proposals(predicted))
        # Establish roles separately on supported segment context, once per component.
        for p, segments in people.items():
            times = [
                f.timestamp_sec
                for f in m.frames
                if any(
                    b.frame_id == f.frame_id and not b.outside and not b.occluded
                    for s in m.segments
                    if s.id in segments
                    for b in s.boxes
                )
            ]
            if not times:
                continue
            try:
                bounds.check()
                case = make_case(
                    m,
                    registry,
                    output,
                    case_id=f"role-{p}",
                    task="role",
                    start=min(times),
                    end=min(m.duration_sec, max(times) + 0.5),
                    segments=segments,
                    seed=seed,
                )
                response = bounds.invoke(executor, case, output)
                assess(case, response)
                bound = bind_facts(case, response.get("facts", []), m)
                facts.extend(bound)
                for fact in bound:
                    if fact["kind"] != "role":
                        raise ValueError("Role pass returned different task")
                    roles.add(m.clip_id, segments, fact)
                if not bound or any(f["value"] == "unclear" for f in bound):
                    proposals.append(
                        ((min(times) + max(times)) / 2, segments[0], "role_uncertainty")
                    )
            except TimeoutError:
                raise
            except Exception as exc:
                failures.append(
                    {"stage": "role", "segments": segments, "error": type(exc).__name__}
                )
        # Quiet ranges are reproducible and independent of known action classes.
        rng = random.Random(seed)
        for start, end in windows:
            if people:
                proposals.append(
                    (rng.uniform(start, end), rng.choice(list(people.values()))[0], "quiet_sample")
                )
        seen = set()
        for center, segment, _reason in proposals:
            for start, end in fine_windows(center, m.duration_sec):
                key = (segment, start, end)
                if key in seen:
                    continue
                seen.add(key)
                component = next(ss for ss in people.values() if segment in ss)
                try:
                    bounds.check()
                    case = make_case(
                        m,
                        registry,
                        output,
                        case_id=f"fine-{len(seen)}",
                        task="action",
                        start=start,
                        end=end,
                        segments=component,
                        seed=seed,
                        max_pixels=393216,
                        counterpart_segments=participant_pairs.get(segment),
                        counterpart=next(
                            (
                                s.person_id
                                for s in m.segments
                                if s.id in participant_pairs.get(segment, [])
                            ),
                            None,
                        ),
                    )
                    case.predicted_roles = role_hints(roles, case, m)
                    response = bounds.invoke(executor, case, output)
                    assess(case, response)
                    facts.extend(bind_facts(case, response.get("facts", []), m))
                    inspected.append([start, end])
                    sampled.update(case.frames)
                except TimeoutError:
                    raise
                except Exception as exc:
                    failures.append(
                        {"stage": "fine", "window": [start, end], "error": type(exc).__name__}
                    )
    except TimeoutError:
        status = "incomplete_budget"
    except Exception as exc:
        status = "incomplete_source"
        failures.append({"stage": "source", "error": type(exc).__name__})
    if failures and status == "complete_schedule":
        status = "incomplete_failures"
    ledger = {
        "duration_sec": m.duration_sec,
        "scheduled_coarse": scheduled,
        "decoded_ranges": [[0, registry.duration]] if registry else [],
        "sampled_frame_ids": sorted(sampled),
        "sampled_instants_only": True,
        "closely_inspected_ranges": union(inspected),
        "not_closely_inspected_ranges": complement(inspected, m.duration_sec),
        "tracking_gaps": [g.model_dump() for g in m.gaps],
        "decoding_gaps": m.provenance.get("undecodable_ranges", []),
        "sampling_gaps": [
            [a.timestamp_sec, b.timestamp_sec]
            for a, b in zip(
                [f for f in m.frames if f.frame_id in sampled],
                [f for f in m.frames if f.frame_id in sampled][1:],
                strict=False,
            )
            if b.timestamp_sec - a.timestamp_sec > 1.5
        ],
        "occluded_frame_ids": sorted(
            {b.frame_id for s in m.segments for b in s.boxes if b.occluded}
        ),
        "sample_visibility_assessments": visibility,
        "occluded_ranges": union(
            [[v["start_sec"], v["end_sec"]] for v in visibility if v["state"] == "occluded"]
        ),
        "unresolved_ranges": complement(
            [[v["start_sec"], v["end_sec"]] for v in visibility if v["state"] == "visible_samples"],
            m.duration_sec,
        ),
        "unresolved_for_absence_ranges": [[0, m.duration_sec]],
        "continuous_visibility_validated": False,
        "adequate_for_omission": False,
        "inspection_temporal_resolution_fps": 2,
        "object_resolution_validated": False,
    }
    if time.monotonic() >= bounds.deadline:
        status = "incomplete_budget"
    report = {
        "clip_id": m.clip_id,
        "source_sha256": m.source_sha256,
        "actor_segments": aliases(m, seed),
        "status": status,
        "visual_timeline": assemble(facts),
        "coverage": ledger,
        "roles": list(roles.values.values()),
        "role_conflicts": roles.conflicts,
        "predicted_work_areas": areas,
        "proposals": [{"center_sec": t, "segment_id": s, "reason": r} for t, s, r in proposals],
        "failures": failures,
        "calls": bounds.calls,
        "call_receipts": bounds.receipts,
        "tokens": bounds.tokens,
        "peak_memory_bytes": bounds.peak_memory_bytes,
        "seconds": time.monotonic() - started,
        "spend": {
            "paid_resources_created": 0,
            "measured_usd": 0 if isinstance(executor, MockScanExecutor) else None,
        },
    }
    write(output / "timeline.json", report)
    return report
