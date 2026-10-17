"""Cover the clip, refine candidates, verify evidence, map public rules."""

import time
from pathlib import Path
from uuid import UUID

from forte.contracts import DoneJob, Violation
from forte.rules import description, load_rules
from forte.video import decode_video, make_windows, sample_window


def event_times(event, by_id):
    times = [by_id[x].timestamp_sec for x in [event.start_id, event.decisive_id, event.end_id]]
    if times != sorted(times):
        raise ValueError("invalid_event_order")
    return times


def merge_candidates(events, by_id):
    merged = []
    for event in sorted(events, key=lambda x: by_id[x.decisive_id].timestamp_sec):
        start, _, end = event_times(event, by_id)
        duplicate = False
        for prior in merged:
            pstart, _, pend = event_times(prior, by_id)
            linked = set(event.evidence_ids) & set(prior.evidence_ids)
            if event.rule_id == prior.rule_id and linked and max(start, pstart) <= min(end, pend):
                duplicate = True
                break
        if not duplicate:
            merged.append(event)
    return merged


def analyze_video(path: Path, work: Path, job_id: UUID, backend, deadline=None, stats=None):
    deadline = deadline or time.monotonic() + 270
    stats = stats if stats is not None else {}
    started = time.monotonic()
    registry = decode_video(path, work / "frames", deadline)
    by_id = {f.frame_id: f for f in registry.frames}
    rules = load_rules()
    catalog = {r["id"]: r for r in rules}
    candidates, confirmed = [], []
    unclear = False
    stats["calls"] = []

    def inspect(frames, pixels, tokens):
        if time.monotonic() >= deadline:
            raise ValueError("processing_timeout")
        t = time.monotonic()
        answer = backend.analyze(registry, frames, rules, pixels, tokens)
        stats["calls"].append(
            {
                "frames": len(frames),
                "pixels": pixels,
                "seconds": time.monotonic() - t,
                "usage": getattr(backend, "last_usage", {}),
                "reviewable": answer.complete,
                "candidate_count": len(answer.events),
            }
        )
        return answer

    for start, end in make_windows(registry.duration, 16, 12):
        frames = sample_window(registry, start, end, 1)
        observation = inspect(frames, 196608, 256)
        unclear |= not observation.complete
        candidates.extend(observation.events)
    for candidate in merge_candidates(candidates, by_id):
        _, center, _ = event_times(candidate, by_id)
        start, end = max(0, center - 4), min(registry.duration, center + 4)
        frames = sample_window(registry, start, end, 2)
        fine = inspect(frames, 393216, 384)
        unclear |= not fine.complete
        for event in fine.events:
            a, _, b = event_times(event, by_id)
            rule = catalog[event.rule_id]
            if not set(rule["required"]) <= set(event.preconditions):
                unclear = True
                continue
            check = backend.verify(registry, frames, event, rule)
            if check.verdict == "unclear":
                context = sample_window(
                    registry, max(0, center - 8), min(registry.duration, center + 8), 1
                )
                mandatory = {event.decisive_id, *event.evidence_ids}
                context = {f.frame_id: f for f in context}
                context.update({id: by_id[id] for id in mandatory})
                ordered = sorted(context.values(), key=lambda f: f.timestamp_sec)
                if len(ordered) > 16:
                    rest = [f for f in ordered if f.frame_id not in mandatory]
                    budget = 16 - len(mandatory)
                    keep = {
                        rest[round(i * (len(rest) - 1) / max(1, budget - 1))].frame_id
                        for i in range(budget)
                    } | mandatory
                    ordered = [f for f in ordered if f.frame_id in keep]
                check = backend.verify(registry, ordered, event, rule)
            if check.verdict == "unsupported":
                continue
            ids = set(check.evidence_ids)
            if (
                check.verdict != "supported"
                or not ids
                or event.decisive_id not in ids
                or not ids <= {f.frame_id for f in registry.frames}
                or not set(rule["required"]) <= set(check.preconditions)
            ):
                unclear = True
                continue
            event = event.model_copy(
                update={"evidence_ids": sorted(ids, key=lambda id: by_id[id].timestamp_sec)}
            )
            confirmed.append(event)
    confirmed = merge_candidates(confirmed, by_id)
    if unclear and not confirmed:
        raise ValueError("insufficient_evidence")
    selected = {id for e in confirmed for id in e.evidence_ids}
    evidence = {e.timestamp_sec: e for e in registry.evidence(list(selected))} if selected else {}
    violations = [
        Violation(
            type=catalog[e.rule_id]["title"],
            timecode_sec=by_id[e.decisive_id].timestamp_sec,
            description=description(e, catalog[e.rule_id], unclear),
            evidence_frames=[evidence[by_id[id].timestamp_sec] for id in e.evidence_ids],
        )
        for e in confirmed
    ]
    stats.update(
        duration_sec=registry.duration,
        decoded_frames=len(registry.frames),
        source_sha256=registry.source_sha256,
        total_seconds=time.monotonic() - started,
        candidates=len(candidates),
        confirmed_events=len(violations),
    )
    return DoneJob(
        job_id=job_id, verdict="violation" if violations else "no_violation", violations=violations
    )
