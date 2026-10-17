"""Same-input sequential model driver and separately invoked reference scoring."""

import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from forte_visual.inputs import Answer, InputCase, validate_answer
from forte_visual.io import digest, read, write

CANDIDATES = {
    "8b": {
        "model": "Qwen/Qwen3-VL-8B-Instruct",
        "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        "architecture": "Qwen3VLForConditionalGeneration",
    },
    "27b": {
        "model": "Qwen/Qwen3.8-27B",
        "revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
        "architecture": "Qwen3_5ForConditionalGeneration",
    },
}
POLICY = {
    "priority": [
        "wrong_actor_at_comparable_coverage",
        "actor_event_f1_without_worse_fp",
        "runtime_memory_cost",
    ],
    "coverage_tolerance": 0.02,
    "minimum_paired_groups": 3,
    "minimum_consistent_group_wins": 2,
    "tiny_f1_gain": 0.02,
    "thinking": False,
    "seed": 0,
    "output_tokens": 768,
    "sequence_tokens": 8192,
}


@dataclass
class Result:
    answer: dict
    input_tokens: int
    output_tokens: int
    peak_memory_bytes: int | None = None
    processor: dict | None = None


class MockExecutor:
    """Abstains on every synthetic image; never receives reference answers."""

    def __call__(self, case, root):
        frames = sorted(case.frames, key=case.frames.get)
        return Result(
            Answer(
                actor_id=case.actor_id,
                kind=case.task,
                value="unclear",
                start_frame_id=frames[0],
                end_frame_id=frames[-1],
                evidence_frame_ids=[frames[0]],
                visibility="unclear",
                continues_before_window=False,
                continues_after_window=False,
            ).model_dump(),
            128,
            48,
            processor={"name": "mock", "measured": False},
        )


def load_cases(path):
    payload = read(path)
    if set(payload) != {"schema_version", "seed", "cases"} or payload["schema_version"] != 1:
        raise ValueError("Unsupported input pack")
    cases = [InputCase.model_validate(c) for c in payload["cases"]]
    if not cases or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("Empty/duplicate cases")
    return cases


def run_model(inputs: Path, output: Path, model: str, executor, *, seconds=270):
    cases = load_cases(inputs)
    rows = []
    started = time.monotonic()
    for case in cases:
        row = {"case_id": case.case_id, "first_request": not rows}
        began = time.monotonic()
        if began - started >= seconds:
            rows.append({**row, "status": "deadline", "seconds": 0})
            continue
        try:
            result = executor(case, inputs.parent)
            if result.input_tokens + POLICY["output_tokens"] > POLICY["sequence_tokens"]:
                raise ValueError("Token budget exceeded")
            if result.output_tokens > POLICY["output_tokens"]:
                raise ValueError("Output budget exceeded")
            answer = Answer.model_validate(result.answer)
            row["answer"] = answer.model_dump()
            try:
                validate_answer(case, answer)
                valid_contract = True
            except ValueError:
                valid_contract = False
            if time.monotonic() - started >= seconds:
                raise TimeoutError("Executor exceeded deadline")
            row.update(
                status="ok" if valid_contract else "invalid_answer",
                answer=answer.model_dump(),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                peak_memory_bytes=result.peak_memory_bytes,
                processor=result.processor,
            )
        except Exception as exc:
            row.update(status="failed", error=type(exc).__name__)
        row["seconds"] = time.monotonic() - began
        rows.append(row)
    report = {
        "candidate": CANDIDATES[model],
        "model_key": model,
        "input_sha256": digest(inputs),
        "policy": POLICY,
        "rows": rows,
        "total_seconds": time.monotonic() - started,
    }
    write(output, report)
    return report


def tiou(a, b):
    intersection = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return intersection / union if union else float(a == b)


def maximum_matches(predictions, references, threshold):
    edges = [
        [
            j
            for j, ref in enumerate(references)
            if p["relation"] == ref["relation"]
            and tiou(p["interval"], ref["interval"]) >= threshold
        ]
        for p in predictions
    ]
    edges = [
        sorted(js, key=lambda j: -tiou(predictions[i]["interval"], references[j]["interval"]))
        for i, js in enumerate(edges)
    ]
    return maximum_edge_matching(edges)


def maximum_edge_matching(edges):
    matched = {}

    def augment(i, visited):
        for j in edges[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in matched or augment(matched[j], visited):
                matched[j] = i
                return True
        return False

    for i in range(len(edges)):
        augment(i, set())
    return [(i, j) for j, i in matched.items()]


def fraction(n, d):
    return n / d if d else None


def score(inputs, references, predictions):
    cases = {c.case_id: c for c in load_cases(inputs)}
    refs, report = read(references), read(predictions)
    if refs["inputs_sha256"] != digest(inputs) or report["input_sha256"] != digest(inputs):
        raise ValueError("Scoring artifacts refer to different pixels/cases")
    if set(refs["cases"]) != set(cases):
        raise ValueError("References must cover every evaluation case")
    rows = {r["case_id"]: r for r in report["rows"]}
    if len(rows) != len(report["rows"]) or set(rows) != set(cases):
        raise ValueError("Predictions omit/duplicate frozen cases")
    groups = defaultdict(
        lambda: {
            "cases": 0,
            "answered": 0,
            "abstained": 0,
            "failed": 0,
            "wrong_actor": 0,
            "role_swaps": 0,
            "invalid_contract": 0,
            "invalid_sources": 0,
            "source_checked": 0,
            "role_asserted": 0,
            "role_correct": 0,
            "roles": 0,
            "actions": 0,
            "action_asserted": 0,
            "contexts": 0,
            "context_asserted": 0,
            "context_correct": 0,
            "pred": [],
            "ref": [],
            "durations": {},
            "confusion": {},
            "seconds": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
    )
    for cid, case in cases.items():
        ref = Answer.model_validate(refs["cases"][cid]["answer"])
        validate_answer(case, ref)
        g = groups[case.track_mode + ":" + case.group_id]
        g["cases"] += 1
        if case.task == "role":
            g["roles"] += 1
        if case.task == "context":
            g["contexts"] += 1
        if case.task == "action":
            g["actions"] += 1
        row = rows[cid]
        g["seconds"] += row.get("seconds", 0)
        g["input_tokens"] += row.get("input_tokens", 0)
        g["output_tokens"] += row.get("output_tokens", 0)
        # Duration counts unique scored action opportunities, not repeated crops.
        if case.task == "action":
            g["durations"].setdefault(case.clip_id, []).append(case.window)

        def event(answer, case=case):
            return {
                "relation": (
                    case.clip_id,
                    answer.actor_id,
                    answer.other_actor_id,
                    answer.actor_participation,
                    answer.value,
                ),
                "interval": (case.frames[answer.start_frame_id], case.frames[answer.end_frame_id]),
                "clipped": (answer.continues_before_window, answer.continues_after_window),
            }

        if case.task == "action" and ref.visibility == "observed" and ref.value != "unclear":
            g["ref"].append(event(ref))
        if row["status"] not in {"ok", "invalid_answer"}:
            g["failed"] += 1
            continue
        g["source_checked"] += 1
        try:
            answer = Answer.model_validate(row["answer"])
            if answer.actor_id != ref.actor_id or answer.other_actor_id != ref.other_actor_id:
                if answer.visibility == "observed" and answer.value != "unclear":
                    g["wrong_actor"] += 1
            # Score independently of the inference contract: an asserted action
            # attributed to another supplied actor is an FP/FN, not disappearing
            # evidence just because the target-actor validator rejected it.
            all_ids = [
                answer.start_frame_id,
                answer.end_frame_id,
                *answer.evidence_frame_ids,
                *answer.other_actor_evidence_frame_ids,
            ]
            if not set(all_ids) <= case.frames.keys() or answer.actor_id not in case.actors:
                raise ValueError("Invalid source/track reference")
            if answer.other_actor_id and answer.other_actor_id not in case.actors:
                raise ValueError("Invalid counterpart")
            if any(
                not case.track_boxes[answer.actor_id].get(id)
                for id in [answer.start_frame_id, answer.end_frame_id, *answer.evidence_frame_ids]
            ):
                raise ValueError("Actor has no source-frame box")
            if answer.other_actor_id and any(
                not case.track_boxes[answer.other_actor_id].get(id)
                for id in answer.other_actor_evidence_frame_ids
            ):
                raise ValueError("Counterpart has no source-frame box")
            if case.frames[answer.start_frame_id] > case.frames[answer.end_frame_id]:
                raise ValueError("Unordered source interval")
            try:
                validate_answer(case, answer)
            except ValueError:
                g["invalid_contract"] += 1
        except ValueError:
            g["invalid_sources"] += 1
            g["failed"] += 1
            continue
        if answer.value in {"unclear", "unknown"} or answer.visibility in {
            "unclear",
            "not_visible",
        }:
            g["abstained"] += 1
            continue
        g["answered"] += 1
        if case.task == "action":
            g["action_asserted"] += 1
        if case.task == "role":
            g["role_asserted"] += 1
            g["role_correct"] += answer.value == ref.value and answer.actor_id == ref.actor_id
            g["role_swaps"] += {answer.value, ref.value} == {"cashier", "customer"}
            key = f"{ref.value}->{answer.value}"
            g["confusion"][key] = g["confusion"].get(key, 0) + 1
        if case.task == "context":
            g["context_asserted"] += 1
            g["context_correct"] += answer.value == ref.value and answer.actor_id == ref.actor_id
        if case.task == "action" and answer.visibility == "observed":
            g["pred"].append(event(answer))
    summaries = {}
    for group, g in groups.items():
        minutes = 0
        for intervals in g.pop("durations").values():
            merged = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(end, merged[-1][1])
                else:
                    merged.append([start, end])
            minutes += sum(e - s for s, e in merged) / 60
        pred, ref = g.pop("pred"), g.pop("ref")
        for threshold in (0.5, 0.75):
            matches = maximum_matches(pred, ref, threshold)
            tp, fp, fn = len(matches), len(pred) - len(matches), len(ref) - len(matches)
            boundary = [
                abs(pred[i]["interval"][k] - ref[j]["interval"][k])
                for i, j in matches
                for k in (0, 1)
                if not ref[j]["clipped"][k]
            ]
            g[str(threshold)] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": fraction(tp, tp + fp),
                "recall": fraction(tp, tp + fn),
                "f1": fraction(2 * tp, 2 * tp + fp + fn),
                "boundary_mae_sec": fraction(sum(boundary), len(boundary)),
                "boundary_error_sum_sec": sum(boundary),
                "boundary_error_count": len(boundary),
            }
        g.update(
            answer_coverage=fraction(g["answered"], g["cases"]),
            role_precision=fraction(g["role_correct"], g["role_asserted"]),
            role_coverage=fraction(g["role_asserted"], g["roles"]),
            action_coverage=fraction(g["action_asserted"], g["actions"]),
            context_precision=fraction(g["context_correct"], g["context_asserted"]),
            context_coverage=fraction(g["context_asserted"], g["contexts"]),
            source_validity=fraction(
                g["source_checked"] - g["invalid_sources"], g["source_checked"]
            ),
            evaluated_minutes=minutes,
            false_events_per_minute=fraction(g["0.5"]["fp"], minutes),
        )
        summaries[group] = g
    total = {
        k: sum(g[k] for g in summaries.values())
        for k in [
            "cases",
            "answered",
            "abstained",
            "failed",
            "wrong_actor",
            "role_swaps",
            "invalid_contract",
            "invalid_sources",
            "source_checked",
            "role_asserted",
            "role_correct",
            "roles",
            "actions",
            "action_asserted",
            "contexts",
            "context_asserted",
            "context_correct",
        ]
    }
    for threshold in ("0.5", "0.75"):
        counts = {k: sum(g[threshold][k] for g in summaries.values()) for k in ("tp", "fp", "fn")}
        tp, fp, fn = counts.values()
        total[threshold] = {
            **counts,
            "precision": fraction(tp, tp + fp),
            "recall": fraction(tp, tp + fn),
            "f1": fraction(2 * tp, 2 * tp + fp + fn),
            "boundary_mae_sec": fraction(
                sum(g[threshold]["boundary_error_sum_sec"] for g in summaries.values()),
                sum(g[threshold]["boundary_error_count"] for g in summaries.values()),
            ),
        }
    minutes = sum(g["evaluated_minutes"] for g in summaries.values())
    total.update(
        answer_coverage=fraction(total["answered"], total["cases"]),
        role_precision=fraction(total["role_correct"], total["role_asserted"]),
        role_coverage=fraction(total["role_asserted"], total["roles"]),
        action_coverage=fraction(total["action_asserted"], total["actions"]),
        context_precision=fraction(total["context_correct"], total["context_asserted"]),
        context_coverage=fraction(total["context_asserted"], total["contexts"]),
        source_validity=fraction(
            total["source_checked"] - total["invalid_sources"], total["source_checked"]
        ),
        false_events_per_minute=fraction(total["0.5"]["fp"], minutes),
    )
    return {
        "groups": summaries,
        "independent_groups": len({case.group_id for case in cases.values()}),
        "aggregate": total,
        "scope": "reviewed opportunities only; dependent windows grouped by session",
        "runtime": {
            "total_seconds": report["total_seconds"],
            "peak_memory_bytes": max(
                (r.get("peak_memory_bytes") or 0 for r in rows.values()), default=0
            ),
        },
    }


def select(left, right, *, synthetic=False):
    if synthetic or set(left["groups"]) != set(right["groups"]):
        return "inconclusive"
    if (
        min(left["independent_groups"], right["independent_groups"])
        < POLICY["minimum_paired_groups"]
    ):
        return "inconclusive"
    a, b = left["aggregate"], right["aggregate"]
    if any(a[k] or b[k] for k in ("failed", "invalid_sources", "invalid_contract")):
        return "inconclusive"
    if abs(a["answer_coverage"] - b["answer_coverage"]) > POLICY["coverage_tolerance"]:
        return "inconclusive"
    for key in left["groups"]:
        for metric in ("role_coverage", "action_coverage"):
            x, y = left["groups"][key][metric], right["groups"][key][metric]
            if (x is None) != (y is None) or (
                x is not None and abs(x - y) > POLICY["coverage_tolerance"]
            ):
                return "inconclusive"
    winner = None
    actor_a, actor_b = a["wrong_actor"] + a["role_swaps"], b["wrong_actor"] + b["role_swaps"]
    if actor_a != actor_b:
        winner = "8b" if actor_a < actor_b else "27b"
    elif a["0.5"]["f1"] is not None and b["0.5"]["f1"] is not None:
        if abs(a["0.5"]["f1"] - b["0.5"]["f1"]) >= POLICY["tiny_f1_gain"]:
            winner = "8b" if a["0.5"]["f1"] > b["0.5"]["f1"] else "27b"
    if not winner:
        return "inconclusive"
    better, other = (left, right) if winner == "8b" else (right, left)
    if (
        better["aggregate"]["false_events_per_minute"]
        > other["aggregate"]["false_events_per_minute"]
    ):
        return "inconclusive"
    wins = sum(
        (g["wrong_actor"] + g["role_swaps"])
        < (other["groups"][key]["wrong_actor"] + other["groups"][key]["role_swaps"])
        or (g["0.5"]["f1"] or 0) > (other["groups"][key]["0.5"]["f1"] or 0)
        for key, g in better["groups"].items()
    )
    regressions = any(
        (g["wrong_actor"] + g["role_swaps"])
        > (other["groups"][key]["wrong_actor"] + other["groups"][key]["role_swaps"])
        or g["0.5"]["fp"] > other["groups"][key]["0.5"]["fp"]
        for key, g in better["groups"].items()
    )
    return winner if wins >= 2 and not regressions else "inconclusive"
