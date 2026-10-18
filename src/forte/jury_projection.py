"""Conservative, opt-in projection of one frozen reasoning run into jury v1.

This is a local presentation boundary, not another inference pass or legal review.
It replays application-owned condition adjudication against the original source,
configuration, official corpus and supplied evidence. A supported assessment can
survive unrelated incomplete work. Clearance additionally needs a complete clear
schedule, the exact scoped rule inventory and explicit coverage of every subject.
All-not-applicable, sparse absence claims, draft interpretations and unknown dates
cannot produce clearance. Existing model proposals remain unreviewed.

JPEG provenance is checked against the immutable export and source-frame table;
pixels are not decoded from the MOV again and this is not semantic verification.
Private artifact reads are bounded and never follow symlinks below the job root.
"""

import base64
import copy
import hashlib
import io
import json
import math
import os
import re
import stat
import time
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

from PIL import Image

from forte.contracts import DoneJob, EvidenceFrame, Violation
from forte.contracts_v2 import ReasoningDoneJob
from forte.legal_reasoning import (
    ConditionCandidate,
    EvidenceItem,
    LegalEvidenceService,
    bounded_observation_evidence,
    evaluate_candidate,
)
from forte.reasoning_pipeline import load_reasoning_config
from forte.timeline import Observation
from forte.video import FrameRef, make_windows, nearest

PROJECTION_VERSION = "forte.jury-v1-projection/1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_RATIONAL = re.compile(r"[+-]?[0-9]{1,20}(?:/[0-9]{1,20})?\Z")
_INVALID = "Invalid reasoning projection provenance"


class _Insufficient(Exception):
    pass


def _check(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("Projection deadline exhausted")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


def _require(condition):
    if not condition:
        raise ValueError(_INVALID)


class _Artifacts:
    def __init__(self, directory, deadline):
        self.root = Path(directory).absolute()
        self.deadline = deadline
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        os.close(self.fd)

    def read(self, relative, maximum=64 * 1024**2):
        _check(self.deadline)
        parts = Path(relative).parts
        _require(
            parts and not Path(relative).is_absolute() and all(p not in {".", ".."} for p in parts)
        )
        parent = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                following = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                os.close(parent)
                parent = following
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as source:
                info = os.fstat(source.fileno())
                _require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= maximum)
                chunks, size = [], 0
                while chunk := source.read(min(1024**2, maximum + 1 - size)):
                    _check(self.deadline)
                    chunks.append(chunk)
                    size += len(chunk)
                    _require(size <= maximum)
                _require(size == info.st_size)
                return b"".join(chunks)
        finally:
            os.close(parent)

    def json(self, relative):
        raw = self.read(relative)

        def pairs(items):
            result = {}
            for key, value in items:
                _require(key not in result)
                result[key] = value
            return result

        value = json.loads(raw, object_pairs_hook=pairs)
        _canonical(value)  # Reject non-finite JSON constants, including unused fields.
        return value, raw

    def receipt(self, value):
        # A replace never follows the destination, but also reject an existing
        # symlink rather than silently removing it. All original artifacts stay put.
        name = "jury-v1-projection.json"
        try:
            _require(stat.S_ISREG(os.stat(name, dir_fd=self.fd, follow_symlinks=False).st_mode))
        except FileNotFoundError:
            pass
        temporary = ".jury-projection-" + uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(_canonical(value))
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass


def _configuration(files, settings):
    configured = settings.reasoning_config
    if isinstance(configured, dict):
        configured = copy.deepcopy(configured)
    else:
        relative = Path(configured).absolute().relative_to(files.root)
        configured, _ = files.json(relative)
    snapshot = copy.copy(settings)
    snapshot.reasoning_config = configured
    return load_reasoning_config(snapshot)


def _source_table(table, report):
    duration = report["source"]["duration_sec"]
    _require(
        table["schema_version"] == "forte.source-frames/1"
        and table["source_sha256"] == report["source_sha256"]
        and table["duration_sec"] == duration
        and type(report["source"]["frame_count"]) is int
        and 0 < len(table["frames"]) <= 60000
        and len(table["frames"]) == report["source"]["frame_count"]
    )
    rows, previous, origin = {}, -1.0, None
    for index, row in enumerate(table["frames"]):
        fid, pts, stamp = row["frame_id"], row["source_pts"], row["timestamp_sec"]
        _require(
            fid == f"f{index:06d}"
            and type(row["ordinal"]) is int
            and row["ordinal"] == index
            and type(pts) is int
            and -(2**63) < pts < 2**63
            and type(stamp) in {int, float}
            and math.isfinite(stamp)
            and previous < stamp < duration
            and _RATIONAL.fullmatch(row["time_base"])
            and _RATIONAL.fullmatch(row["absolute_presentation_time"])
        )
        base = Fraction(row["time_base"])
        _require(base > 0)
        absolute = pts * base
        origin = absolute if origin is None else origin
        _require(abs(float(absolute - origin) - stamp) < 1e-7)
        _require(Fraction(row["absolute_presentation_time"]) == absolute)
        width, height = row["source_size"]
        _require(
            type(width) is int
            and type(height) is int
            and 0 < width <= 4096
            and 0 < height <= 4096
            and width * height <= 8_400_000
            and type(row["rotation_degrees"]) in {int, float}
            and math.isfinite(row["rotation_degrees"])
            and row["rotation_degrees"] % 90 == 0
        )
        size = [height, width] if row["rotation_degrees"] % 180 else [width, height]
        _require(row["oriented_size"] == size)
        rows[fid], previous = row, stamp
    return rows


def _observations(report, rows):
    timeline, digest = report["timeline"], report["source_sha256"]
    _require(
        timeline["source_sha256"] == digest
        and timeline["duration_sec"] == report["source"]["duration_sec"]
    )
    participants = [p["participant_id"] for p in timeline["participants"]]
    _require(len(set(participants)) == len(participants))
    _require(
        set(participants) == {p["participant_id"] for p in report["participants"]["participants"]}
    )
    _require(report["participants"].get("source_sha256", digest) == digest)
    result = {}
    for row in timeline["observations"]:
        _require(
            _IDENTIFIER.fullmatch(row["observation_id"]) and row["observation_id"] not in result
        )
        value = Observation.model_validate({k: row[k] for k in Observation.model_fields})
        refs = {
            value.start_frame_id,
            value.end_frame_id,
            value.decisive_frame_id,
            *value.evidence_frame_ids,
        }
        _require(
            row["source_sha256"] == digest
            and row["origin"] == "model"
            and row["review_status"] == "unreviewed"
            and refs <= rows.keys()
            and set(value.actor_ids + value.recipient_ids) <= set(participants)
            and value.decisive_frame_id in value.evidence_frame_ids
        )
        for key in ("start", "end", "decisive"):
            _require(row[f"{key}_sec"] == rows[row[f"{key}_frame_id"]]["timestamp_sec"])
        _require(row["start_sec"] <= row["decisive_sec"] <= row["end_sec"])
        _require(
            all(row["start_sec"] <= rows[fid]["timestamp_sec"] <= row["end_sec"] for fid in refs)
        )
        result[row["observation_id"]] = row
    return result, participants


def _exports(files, revision, report, rows):
    associations, _ = files.json(f"{revision}/evidence-association.json")
    _require(isinstance(associations, list) and len(associations) <= 48)
    exported = {}
    for item in associations:
        fid = item["frame_id"]
        _require(fid in rows and fid not in exported and item["file"] == f"evidence/{fid}.jpg")
        source = rows[fid]
        _require(item["source_sha256"] == report["source_sha256"])
        for key in (
            "source_pts",
            "time_base",
            "timestamp_sec",
            "oriented_size",
            "rotation_degrees",
        ):
            _require(item[key] == source[key])
        _require(item["kind"] == "decoded_source_jpeg_no_overlay_no_resize")
        raw = files.read(f"{revision}/{item['file']}", 9_000_000)
        _require(_digest(raw) == item["jpeg_sha256"] == item["image_sha256"])
        with Image.open(io.BytesIO(raw)) as image:
            _require(image.format == "JPEG" and list(image.size) == source["oriented_size"])
            image.verify()
        exported[fid] = (item, raw)
    for event in report["events"]:
        _require(
            set(event["observation_ids"])
            <= {o["observation_id"] for o in report["timeline"]["observations"]}
        )
        for item in event["evidence"]:
            _require(item["frame_id"] in exported and item == exported[item["frame_id"]][0])
    return exported


def _supplied_evidence(service, card, observations, rows, duration, law, digest):
    relevant = []
    for observation in observations.values():
        hits = service.retrieve_applicable_rules(
            observation["value"], law.get("operation_context"), law.get("event_date"), limit=5
        )
        if {h["provision_id"] for h in hits} & set(card["clause_ids"]):
            relevant.append(observation)
    relevant = relevant or list(observations.values())
    supplied, wanted = bounded_observation_evidence(relevant)
    frames = [
        FrameRef(fid, row["ordinal"], row["source_pts"], row["timestamp_sec"])
        for fid, row in rows.items()
    ]
    for observation in supplied:
        wanted.extend(
            nearest(frames, max(0, observation["decisive_sec"] + delta)).frame_id
            for delta in (-1, -0.5, 0.5, 1)
        )
    wanted.extend(nearest(frames, duration * i / 7).frame_id for i in range(8))
    frame_ids = sorted(list(dict.fromkeys(wanted))[:8], key=lambda fid: rows[fid]["timestamp_sec"])
    participants = sorted({p for o in supplied for p in o["actor_ids"] + o["recipient_ids"]})
    owners = {fid: set() for fid in frame_ids}
    for observation in supplied:
        for fid in observation["evidence_frame_ids"]:
            owners[fid].update(observation["actor_ids"] + observation["recipient_ids"])
    evidence = [
        EvidenceItem(
            id=fid,
            kind="frame",
            source_id=digest,
            participant_ids=sorted(owners[fid]),
            frame_ids=[fid],
            origin="source",
            visibility="unknown",
        )
        for fid in frame_ids
    ]
    evidence.extend(
        EvidenceItem(
            id=o["observation_id"],
            kind="observation",
            source_id=digest,
            participant_ids=list(dict.fromkeys(o["actor_ids"] + o["recipient_ids"])),
            actor_ids=o["actor_ids"],
            frame_ids=o["evidence_frame_ids"],
            origin="model",
            visibility="partial" if o["visibility"] == "partly_occluded" else "unknown",
        )
        for o in supplied
    )
    for item in law.get("metadata_evidence", []):
        metadata = EvidenceItem.model_validate(item)
        _require(metadata.source_id == digest)
        if set(metadata.participant_ids) <= set(participants):
            evidence.append(metadata)
    return evidence, frame_ids, participants, len(relevant) - len(supplied)


def _replay(files, revision, report, config, observations, rows):
    law, legal = config["legal"], report["legal"]
    service = LegalEvidenceService(
        Path(law["release"]),
        Path(law["cards"]) if law.get("cards") else None,
        applicability=law.get("applicability", []),
    )
    inventory = {c["id"]: c for c in service.scoped_rule_inventory()}
    _require(
        legal["source_sha256"] == report["source_sha256"]
        and legal["snapshot_sha256"] == service.snapshot_sha256
        and legal["rule_cards_sha256"] == service.cards_sha256
    )
    receipts = legal["metrics"]["receipts"]
    result, seen, seen_rules = [], set(), set()
    for record in legal["assessments"]:
        _check(files.deadline)
        identifier, rule = record["assessment_id"], record["rule_id"]
        _require(
            _IDENTIFIER.fullmatch(identifier)
            and identifier not in seen
            and rule in inventory
            and rule not in seen_rules
        )
        seen.add(identifier)
        seen_rules.add(rule)
        plan = service.prepare_card(
            rule, event_date=law.get("event_date"), operation_context=law.get("operation_context")
        )
        _require(
            record["plan_id"] == plan.plan_id
            and record["snapshot_sha256"] == plan.snapshot_sha256
            and record["interpretation_status"] == plan.interpretation_status
        )
        _require(
            record["source_provision_ids"] == plan.source_provision_ids
            and record["condition_specs"] == [s.model_dump() for s in plan.conditions]
        )
        matching = [
            (i, r)
            for i, r in enumerate(receipts)
            if r.get("plan_id") == plan.plan_id and r["rule_id"] == rule and not r.get("error")
        ]
        _require(len(matching) == 1)
        index, receipt = matching[0]
        evidence, frame_ids, participants, omitted = _supplied_evidence(
            service,
            inventory[rule],
            observations,
            rows,
            report["source"]["duration_sec"],
            law,
            report["source_sha256"],
        )
        _require(
            receipt["inference_attempted"] is True
            and receipt["source_frame_ids"] == frame_ids
            and receipt["participant_ids"] == participants
            and receipt["observations_not_supplied"] == omitted
        )
        candidate, _ = files.json(f"{revision}/legal/condition-reply-{index:03d}.json")
        candidate = ConditionCandidate.model_validate(candidate)
        evaluated = evaluate_candidate(plan, candidate, evidence, participants)
        for key in (
            "assessment",
            "candidate_assessment",
            "conditions",
            "participant_ids",
            "bound_observation_ids",
            "unresolved_dependencies",
            "review_status",
            "validated_legal_conclusion",
        ):
            _require(record[key] == evaluated.model_dump(mode="json")[key])
        _require(
            record["source_sha256"] == report["source_sha256"]
            and record["observation_ids"] == evaluated.bound_observation_ids
        )
        used = {
            fid
            for c in evaluated.conditions
            for eid in c.supporting_evidence_ids + c.contradictory_evidence_ids
            for e in evidence
            if e.id == eid
            for fid in e.frame_ids
        }
        _require(
            record["evidence_frame_ids"] == sorted(used, key=lambda fid: rows[fid]["timestamp_sec"])
        )
        ordered_times = sorted(rows[fid]["timestamp_sec"] for fid in used)
        _require(
            record["start_sec"] == (ordered_times[0] if ordered_times else None)
            and record["end_sec"] == (ordered_times[-1] if ordered_times else None)
            and record["interval_semantics"]
            == "source_evidence_envelope_not_exact_action_boundaries"
        )
        citations = []
        for provision in plan.source_provision_ids:
            source = service.get_source_provision(*provision.split(":"))
            citations.append(
                {
                    "provision_id": source["provision_id"],
                    "url": source["clause"]["url"],
                    "title": source["source"]["title"],
                    "version_id": source["source"]["version_id"],
                    "text": source["clause"]["text"],
                    "parent_headings": source["parent_headings"],
                    "source_effect_notices": source["source_effect_notices"],
                }
            )
        _require(record["citations"] == citations)
        result.append((record, plan, evaluated, citations))
    return inventory, result


def _negative(report, inventory, assessments, participants):
    timeline, legal = report["timeline"], report["legal"]
    coverage = timeline["coverage"]
    if not (
        report["execution"]["status"] == "completed"
        and not report["execution"].get("budget_exhausted")
        and timeline["status"] == "complete_schedule"
        and legal["status"] == "complete_scoped_schedule"
    ):
        return False
    if (
        any(
            coverage.get(k)
            for k in (
                "unexamined_intervals",
                "unclear_intervals",
                "pending_reinspections",
                "output_capacity_limited_intervals",
            )
        )
        or timeline.get("unresolved_questions")
        or timeline.get("role_conflicts")
    ):
        return False
    tracking = report["participants"]
    if tracking.get("unresolved_matches") or any(
        p.get("conflicts") or p.get("visibility_gaps") for p in tracking["participants"]
    ):
        return False
    if any(
        o["uncertainty"] or o["visibility"] != "visible_samples" for o in timeline["observations"]
    ):
        return False
    windows = coverage.get("windows", [])
    if not {"overview", "window", "reconcile"} <= {w["phase"] for w in windows} or any(
        w.get("error")
        or w.get("capacity_limited") is not False
        or w.get("visibility") != "visible_samples"
        for w in windows
    ):
        return False
    expected = make_windows(report["source"]["duration_sec"], 16, 12)
    actual = [(w["start_sec"], w["end_sec"]) for w in windows if w["phase"] == "window"]
    if (
        actual != expected
        or coverage.get("scheduled_intervals") != [list(x) for x in expected]
        or coverage.get("examined_intervals") != [list(x) for x in expected]
    ):
        return False
    by_rule = {
        record["rule_id"]: (record, plan, evaluated) for record, plan, evaluated, _ in assessments
    }
    if not inventory or set(by_rule) != set(inventory) or len(by_rule) != len(assessments):
        return False
    checks = legal["rule_coverage"]
    if len(checks) != len(inventory) or {c["rule_id"] for c in checks} != set(inventory):
        return False
    if not any(
        evaluated.assessment == "no_violation_observed" for _, _, evaluated in by_rule.values()
    ):
        return False
    for check in checks:
        record, plan, evaluated = by_rule[check["rule_id"]]
        if (
            check.get("status") != "evaluated"
            or check.get("assessment_id") != record["assessment_id"]
            or check.get("assessment") != evaluated.assessment
        ):
            return False
        if (
            plan.interpretation_status != "approved"
            or plan.version_applicability != "applicable"
            or evaluated.assessment not in {"no_violation_observed", "not_applicable"}
            or evaluated.unresolved_dependencies
        ):
            return False
        used = {
            ref
            for condition in evaluated.conditions
            for ref in condition.supporting_evidence_ids + condition.contradictory_evidence_ids
        }
        # One inventory call per rule is not evidence of coverage of uncited
        # actions, transactions or other participants. Lexical retrieval and the
        # bounded four-observation legal context cannot silently clear the rest.
        if not {o["observation_id"] for o in timeline["observations"]} <= used:
            return False
        conditions = {condition.condition_id: condition for condition in evaluated.conditions}
        for spec in plan.conditions:
            condition = conditions[spec.id]
            if condition.result == "unknown" or condition.unresolved_dependencies:
                return False
            if spec.category in {"role", "action", "sequence"} and (
                not participants or not set(participants) <= set(condition.participant_ids)
            ):
                return False
    return True


def _scope_incomplete(report):
    timeline, legal = report["timeline"], report["legal"]
    return (
        report["execution"]["status"] != "completed"
        or timeline["status"] != "complete_schedule"
        or legal["status"] != "complete_scoped_schedule"
        or any(
            timeline["coverage"].get(key)
            for key in (
                "unexamined_intervals",
                "unclear_intervals",
                "pending_reinspections",
                "output_capacity_limited_intervals",
            )
        )
        or bool(timeline.get("unresolved_questions"))
        or bool(timeline.get("role_conflicts"))
    )


def _positive(record, plan, evaluated, citations, observations, exported, partial):
    if (
        evaluated.assessment != "supported_violation"
        or plan.interpretation_status != "approved"
        or plan.version_applicability != "applicable"
    ):
        raise _Insufficient
    bound = [observations[oid] for oid in evaluated.bound_observation_ids]
    required = {fid for o in bound for fid in o["evidence_frame_ids"]}
    if (
        not required
        or not required <= exported.keys()
        or not set(record["evidence_frame_ids"]) <= required
    ):
        # Additional legal-frame support without a bound observation/export
        # must not disappear when compressing the evidence into fixed v1.
        raise _Insufficient
    candidates = [
        o
        for o in bound
        if o["kind"] != "role" and o["decisive_frame_id"] in record["evidence_frame_ids"]
    ]
    if not candidates:
        raise _Insufficient
    anchor = min(
        candidates,
        key=lambda o: (
            o["kind"] not in {"action", "interaction"},
            o["decisive_sec"],
            o["observation_id"],
        ),
    )
    if any(
        re.search(
            r"https?://|adilet|недостач|украл|мошеннич|винов|\btheft\b|\bfraud\b", o["value"], re.I
        )
        for o in bound
    ):
        raise _Insufficient
    ids = sorted(
        required & set(record["evidence_frame_ids"]),
        key=lambda fid: exported[fid][0]["timestamp_sec"],
    )
    decisive = anchor["decisive_frame_id"]
    chosen = list(dict.fromkeys([ids[0], decisive, ids[-1]]))
    for fid in reversed(ids):
        if len(chosen) < 3 and fid not in chosen:
            chosen.append(fid)
    chosen.sort(key=lambda fid: exported[fid][0]["timestamp_sec"])
    citation = "; ".join(
        f"{c['title']}, provision {c['provision_id']}, {c['url']}" for c in citations
    )
    facts = "; ".join(dict.fromkeys(o["value"] for o in bound))
    description = (
        f"Visible observations: {facts}. Basis for review: {citation}. "
        "Unreviewed model proposal, not a validated legal conclusion. "
        "Source times describe sampled evidence, not exact action boundaries."
    )
    if partial:
        description += (
            " Other work is incomplete or uncertain; this finding concerns only its cited evidence."
        )
    if len(description) > 2400:
        raise _Insufficient
    evidence = [
        EvidenceFrame(
            timestamp_sec=exported[fid][0]["timestamp_sec"],
            image_base64=base64.b64encode(exported[fid][1]).decode("ascii"),
        )
        for fid in chosen
    ]
    return Violation(
        type=record["rule_id"],
        timecode_sec=anchor["decisive_sec"],
        description=description,
        evidence_frames=evidence,
    ), chosen


def project_reasoning_to_v1(job_id, report: dict, directory: Path, settings, *, deadline=None):
    """Project one immutable run; abstention is ``ValueError('insufficient_evidence')``.

    Invalid provenance raises a static ValueError; a deadline raises TimeoutError.
    No settings, report, original prediction or prior artifact is modified.
    """
    _check(deadline)
    files = None
    receipt = {
        "schema_version": PROJECTION_VERSION,
        "projection_version": 1,
        "status": "failed",
        "assessment_ids": [],
        "chosen_frame_ids": {},
        "exclusions": [],
    }
    try:
        files = _Artifacts(directory, deadline)
        ReasoningDoneJob(job_id=job_id, result=report)
        digest = report["source_sha256"]
        _require(_DIGEST.fullmatch(digest))
        receipt.update(source_sha256=digest, original_result_sha256=_digest(_canonical(report)))
        revision = report["artifacts"]["revision"]
        saved, _ = files.json(f"{revision}/result.json")
        _require(saved == report)
        _require(_digest(files.read("input.mov", 268435456)) == digest)
        config = _configuration(files, settings)
        saved_config, raw_config = files.json(f"{revision}/configuration.json")
        _require(
            saved_config == config and _digest(raw_config) == report["provenance"]["config_sha256"]
        )
        table, _ = files.json(f"{revision}/source-frames.json")
        rows = _source_table(table, report)
        observations, participants = _observations(report, rows)
        saved_timeline, _ = files.json(f"{revision}/scan/timeline.json")
        saved_legal, _ = files.json(f"{revision}/legal-assessments.json")
        _require(saved_timeline == report["timeline"] and saved_legal == report["legal"])
        exports = _exports(files, revision, report, rows)
        inventory, assessments = _replay(files, revision, report, config, observations, rows)
        clear = _negative(report, inventory, assessments, participants)
        receipt["coverage"] = {
            "execution_status": report["execution"]["status"],
            "timeline_status": report["timeline"]["status"],
            "scoped_rules": len(inventory),
            "evaluated_assessments": len(assessments),
            "clearance_supported": clear,
        }
        violations = []
        for record, plan, evaluated, citations in assessments:
            _check(deadline)
            try:
                violation, chosen = _positive(
                    record,
                    plan,
                    evaluated,
                    citations,
                    observations,
                    exports,
                    _scope_incomplete(report),
                )
            except _Insufficient:
                receipt["exclusions"].append(
                    {
                        "assessment_id": record["assessment_id"],
                        "reason": "not_independently_projectable",
                    }
                )
                continue
            violations.append(violation)
            receipt["assessment_ids"].append(record["assessment_id"])
            receipt["chosen_frame_ids"][record["assessment_id"]] = chosen
        if not violations and not clear:
            raise _Insufficient
        result = DoneJob(
            job_id=job_id,
            verdict="violation" if violations else "no_violation",
            violations=violations,
        )
        receipt.update(
            status="projected",
            projected_result_sha256=_digest(_canonical(result.model_dump(mode="json"))),
        )
        _check(deadline)
        files.receipt(receipt)
        return result
    except _Insufficient:
        receipt["exclusions"].append({"reason": "insufficient_evidence"})
        if files is not None:
            files.receipt(receipt)
        raise ValueError("insufficient_evidence") from None
    except TimeoutError:
        raise
    except Exception:
        receipt["exclusions"].append({"reason": "invalid_provenance"})
        if files is not None:
            try:
                files.receipt(receipt)
            except (OSError, ValueError):
                pass
        raise ValueError(_INVALID) from None
    finally:
        if files is not None:
            files.close()
