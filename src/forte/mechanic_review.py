"""Readable, local-only views of saved predictions. No inference or role assignment."""

import argparse
import copy
import hashlib
import html
import json
import math
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def selected(value, keys):
    return {key: copy.deepcopy(value[key]) for key in keys if key in value}


OBSERVATION_KEYS = (
    "observation_id",
    "kind",
    "value",
    "actor_ids",
    "recipient_ids",
    "source_sha256",
    "phase",
    "localization",
    "start_sec",
    "end_sec",
    "decisive_sec",
    "start_frame_id",
    "end_frame_id",
    "decisive_frame_id",
    "evidence_frame_ids",
    "origin",
    "review_status",
    "visibility",
    "uncertainty",
    "continues_before_window",
    "continues_after_window",
)


def project_review(job, prediction_sha256):
    """An additive projection, never a replacement API result or a new prediction."""
    if not re.fullmatch(r"[a-f0-9]{64}", prediction_sha256):
        raise ValueError("A saved prediction fingerprint is required")
    status = job.get("status")
    if status not in {"done", "failed", "processing"}:
        raise ValueError("Unsupported saved job status")
    result = job.get("result", {}) if status == "done" else {}
    if status == "done" and result.get("schema_version") != "forte.reasoning/1":
        raise ValueError("Expected a saved v2 reasoning result")
    timeline = result.get("timeline", {})
    registry = result.get("participants", {})
    observations = [selected(o, OBSERVATION_KEYS) for o in timeline.get("observations", [])]
    people = []
    for person in registry.get("participants", []):
        pid = person["participant_id"]
        segments = person.get("track_segments", [])
        samples = [o for s in segments for o in s.get("observations", [])]
        times = [o["timestamp_sec"] for o in samples]
        roles = []
        # Enrich duplicate references to the SAME observation only when all shared
        # fields agree. Conflicts/null claims remain separate; no interval grows.
        for source, rows in (
            ("participant_registry", person.get("role_hypotheses", [])),
            (
                "timeline",
                [
                    o
                    for o in observations
                    if o.get("kind") == "role" and pid in o.get("actor_ids", [])
                ],
            ),
        ):
            for row in rows:
                role = selected(row, OBSERVATION_KEYS)
                previous = next(
                    (
                        r
                        for r in roles
                        if role.get("observation_id")
                        and r["claim"].get("observation_id") == role["observation_id"]
                        and all(r["claim"][k] == role[k] for k in r["claim"].keys() & role.keys())
                    ),
                    None,
                )
                if previous is None:
                    roles.append({"claim": role, "record_sources": [source]})
                else:
                    previous["claim"].update(role)
                    if source not in previous["record_sources"]:
                        previous["record_sources"].append(source)
        people.append(
            {
                "participant_id": pid,
                "identity_status": person.get("identity_status"),
                "sample_span_sec": [min(times), max(times)] if times else None,
                "sample_count": len(samples),
                "source_frame_ids": list(dict.fromkeys(o["frame_id"] for o in samples)),
                "segment_ids": [s["segment_id"] for s in segments],
                "tracking_basis": {
                    "assigned_tracker_segments": sum(
                        s.get("tracker_id", -1) >= 0 for s in segments
                    ),
                    "unmatched_tracker_segments": sum(
                        s.get("tracker_id", -1) < 0 for s in segments
                    ),
                },
                "role_hypotheses": roles,
                "role_state": "hypotheses_only" if roles else "not_established",
                "conflicts": copy.deepcopy(person.get("conflicts", [])),
                "visibility_gaps": copy.deepcopy(person.get("visibility_gaps", [])),
            }
        )
    findings = [
        selected(
            e,
            (
                *OBSERVATION_KEYS,
                "event_id",
                "assessment",
                "observation_ids",
                "evidence",
                "evidence_export_complete",
                "legal_assessment_ids",
            ),
        )
        for e in result.get("events", [])
    ]
    return {
        "schema_version": "forte.review-packet/1",
        "original_prediction": {"sha256": prediction_sha256, "file": "original-result.json"},
        "source": {
            **selected(result.get("source", {}), ("duration_sec", "frame_count")),
            "sha256": result.get("source_sha256"),
            "frame_table": "source-frames.json",
        },
        "processing": {
            "job_status": status,
            "execution": copy.deepcopy(result.get("execution")),
            "assessment": result.get("assessment"),
            "review_status": result.get("review_status"),
            "error": copy.deepcopy(job.get("error")),
            "presentation_state": "incomplete_inspection"
            if status != "done"
            or result.get("execution", {}).get("status") != "completed"
            or timeline.get("coverage", {}).get("unexamined_intervals")
            or timeline.get("coverage", {}).get("unclear_intervals")
            or timeline.get("coverage", {}).get("output_capacity_limited_intervals")
            else "saved_prediction",
        },
        "summary": {
            "participant_proposals": len(people),
            "physical_person_count": None,
            "role_observations": sum(o.get("kind") == "role" for o in observations),
            "observations": len(observations),
            "event_candidates": len(findings),
        },
        "people": people,
        "views": copy.deepcopy(registry.get("view_observations", [])),
        "unresolved_identity": copy.deepcopy(registry.get("unresolved_matches", [])),
        "role_conflicts": copy.deepcopy(timeline.get("role_conflicts", [])),
        "geometry_only": [
            selected(
                s, ("segment_id", "tracker_id", "participant_id", "observations", "review_status")
            )
            for s in registry.get("segments", [])
            if s.get("participant_id") is None and s.get("tracker_id", 0) < 0
        ],
        "observations": observations,
        "findings": findings,
        "evidence_frames": {},
        "coverage": {
            "timeline_status": timeline.get("status"),
            "temporal": copy.deepcopy(timeline.get("coverage", {})),
            "rules": copy.deepcopy(result.get("legal", {}).get("rule_coverage", [])),
        },
        "legal": copy.deepcopy(result.get("legal", {}).get("assessments", [])),
        "unresolved_questions": copy.deepcopy(timeline.get("unresolved_questions", [])),
        "limitations": copy.deepcopy(result.get("limitations", [])),
        "legal_limitations": copy.deepcopy(result.get("legal", {}).get("limitations", [])),
        "metrics": selected(
            result.get("metrics", {}),
            (
                "decoding_seconds",
                "tracking_seconds",
                "timeline_seconds",
                "legal_seconds",
                "total_seconds",
            ),
        ),
        "provenance": copy.deepcopy(result.get("provenance", {})),
        "projection_limits": [
            "Participant IDs are recording-local proposals, not verified physical identities.",
            "Role hypotheses retain source intervals and evidence; missing roles stay unknown.",
            "Sample spans are not continuous visibility or complete role intervals.",
            "Presentation creates no identity, geometry, role, action or legal approval.",
        ],
    }


def esc(value):
    return html.escape(str(value), quote=True)


def words(value):
    return esc(value).replace("_", " ") if value is not None else "Unknown / not supplied"


def stamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "Unknown"
    return f"{value:.3f}s"


def seek(value, label=None):
    if stamp(value) == "Unknown" or value < 0:
        return "Unknown"
    return f'<button type="button" data-seek="{value}">{esc(label or stamp(value))}</button>'


def notes(items):
    return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>" if items else ""


def table(headers, rows):
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join(f"<th>{esc(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def participant_links(ids):
    return ", ".join(f'<a href="#person-{esc(pid)}">{esc(pid)}</a>' for pid in ids) or "Unresolved"


def record_links(ids, prefix, available):
    return (
        ", ".join(
            f'<a href="#{prefix}-{esc(id)}">{esc(id)}</a>' if id in available else esc(id)
            for id in ids
        )
        or "Not supplied"
    )


def render_review(view, frame_assets, overlays):
    """Return self-contained HTML; case text is escaped and no remote resource loads."""

    def evidence(ids):
        cards = []
        for fid in ids:
            asset = frame_assets.get(fid)
            if not asset:
                cards.append(f"<p>{esc(fid)} — cited frame unavailable in this packet</p>")
                continue
            filename = asset["file"]
            if not re.fullmatch(r"frames/f\d{6}\.jpg", filename):
                raise ValueError("Unexpected local frame asset name")
            cards.append(
                '<figure><a href="'
                + filename
                + '"><img loading="lazy" src="'
                + filename
                + '" alt="Source evidence '
                + esc(fid)
                + '"></a><figcaption>'
                + esc(fid)
                + " · "
                + seek(asset.get("timestamp_sec"))
                + " · source PTS "
                + esc(asset.get("source_pts"))
                + "<br>"
                + esc(asset["origin_label"])
                + "</figcaption></figure>"
            )
        return '<div class="evidence">' + "".join(cards) + "</div>"

    processing = view["processing"]
    body = (
        '<header><p class="eyebrow">LOCAL HUMAN REVIEW · SAVED PREDICTION</p>'
        "<h1>People, actions and source evidence</h1><p>Review the complete recording. "
        "Model proposals and human judgments have separate scopes.</p></header>"
        '<nav><a href="#people">People &amp; roles</a><a href="#actions">Actions</a>'
        '<a href="#findings">Event candidates</a><a href="#coverage">Coverage</a>'
        '<a href="#rules">Rules</a><a href="#technical">Files &amp; provenance</a></nav>'
        '<section class="status"><h2>Result and remaining uncertainty</h2><p><strong>'
        + words(processing.get("assessment"))
        + "</strong> · job "
        + words(processing["job_status"])
        + " · inspection "
        + words((processing.get("execution") or {}).get("status"))
        + (
            "</p><p><strong>Incomplete inspection: no whole-recording clearance.</strong>"
            if processing["presentation_state"] == "incomplete_inspection"
            else ""
        )
        + "</p><p>Source duration: "
        + stamp(view["source"].get("duration_sec"))
        + " · participant proposals: "
        + str(view["summary"]["participant_proposals"])
        + " · event candidates: "
        + str(view["summary"]["event_candidates"])
        + ". No physical-person count or human approval is created by this view.</p>"
        + notes(view["unresolved_questions"])
        + notes(view["limitations"])
        + "</section>"
        '<section><h2>Complete recording</h2><div class="playback">'
        '<video id="video" controls preload="metadata" src="source.mp4"></video>'
        '<canvas id="overlay" aria-hidden="true"></canvas></div>'
        '<p id="sample-note">Boxes are saved proposals at sampled source times.</p>'
        '<p><a href="original.mov">Original MOV</a> · '
        '<a href="source-frames.json">Source PTS table</a> · '
        '<a href="review-template.json">Independent review template</a></p></section>'
    )
    body += (
        '<section id="people"><h2>People and operational roles</h2>'
        "<p>Each ID below is an independent recording-local proposal. Multiple people "
        "can share a role; a person can have different time-scoped hypotheses. "
        "A role word does not establish permanent employment or an identity join.</p>"
    )
    actor_ids = {
        pid
        for o in view["observations"]
        for pid in o.get("actor_ids", []) + o.get("recipient_ids", [])
    }
    deferred = []
    for person in view["people"]:
        pid = person["participant_id"]
        span = person["sample_span_sec"]
        summary = [
            esc(pid),
            words(person["identity_status"]),
            str(person["sample_count"]),
            (seek(span[0]) + " – " + seek(span[1])) if span else "Unknown",
        ]
        if (
            not person["tracking_basis"]["assigned_tracker_segments"]
            and not person["role_hypotheses"]
            and pid not in actor_ids
        ):
            deferred.append([f'<span id="person-{esc(pid)}">{esc(pid)}</span>', *summary[1:]])
            continue
        body += (
            f'<article id="person-{esc(pid)}"><h3>{esc(pid)}</h3>'
            + table(
                ["Proposal", "Identity status", "Detection samples", "Sample envelope"], [summary]
            )
            + "<p>Tracking basis: "
            + esc(person["tracking_basis"]["assigned_tracker_segments"])
            + " assigned-tracker segments; "
            + esc(person["tracking_basis"]["unmatched_tracker_segments"])
            + " unmatched-origin segments. Geometry and identity remain independent.</p>"
        )
        if not person["role_hypotheses"]:
            body += '<p class="unknown">Operational role not established in the saved output.</p>'
        for role in person["role_hypotheses"]:
            claim = role["claim"]
            body += (
                '<div class="role"><h4>'
                + esc(claim.get("value") or "Unresolved role")
                + "</h4><p>"
                + seek(claim.get("start_sec"))
                + " – "
                + seek(claim.get("end_sec"))
                + " · origin "
                + words(claim.get("origin"))
                + " · review "
                + words(claim.get("review_status"))
                + "</p>"
                + "<p>Observation: "
                + esc(claim.get("observation_id", "Not supplied"))
                + " · saved in "
                + esc(", ".join(role["record_sources"]))
                + "</p>"
                + notes(claim.get("uncertainty", []))
                + evidence(claim.get("evidence_frame_ids", []))
                + "</div>"
            )
        body += "</article>"
    if deferred:
        body += (
            f"<details><summary>{len(deferred)} additional unmatched-origin / unassociated "
            "proposals — preserved separately from stable identity</summary>"
            + table(
                ["Proposal", "Identity status", "Detection samples", "Sample envelope"], deferred
            )
            + "</details>"
        )
    if not view["people"]:
        body += (
            "<p>No participant proposals were saved. Physical people may still be unobserved.</p>"
        )
    body += (
        "<p>View/reflection proposals: "
        + str(len(view["views"]))
        + "; unresolved associations: "
        + str(len(view["unresolved_identity"]))
        + ". Full saved view/identity records remain in the structured download.</p>"
    )
    body += table(
        ["View / segment", "View kind", "Owner proposal", "Review status"],
        [
            [
                esc(v.get("segment_id")),
                words(v.get("view_kind")),
                esc(v.get("canonical_person_id") or "Unresolved"),
                words(v.get("review_status")),
            ]
            for v in view["views"]
        ],
    )
    body += notes(
        [
            "Unresolved association: " + str(item.get("reason", "unknown"))
            for item in view["unresolved_identity"]
        ]
    )
    body += '</section><section id="actions"><h2>Observed actions and context</h2>'
    observation_ids = {o.get("observation_id") for o in view["observations"]}
    assessment_ids = {a.get("assessment_id") for a in view["legal"]}
    for item in sorted(view["observations"], key=lambda o: o.get("start_sec", math.inf)):
        body += (
            f'<article id="observation-{esc(item.get("observation_id"))}"><h3>'
            + words(item.get("kind"))
            + " · "
            + esc(item.get("observation_id"))
            + "</h3><p>"
            + esc(item.get("value"))
            + "</p><dl><dt>Actors</dt><dd>"
            + participant_links(item.get("actor_ids", []))
            + "</dd><dt>Recipients</dt><dd>"
            + participant_links(item.get("recipient_ids", []))
            + "</dd><dt>Source interval</dt>"
            + "<dd>"
            + seek(item.get("start_sec"))
            + " – "
            + seek(item.get("end_sec"))
            + "</dd><dt>Transaction phase</dt><dd>"
            + words(item.get("phase"))
            + "</dd><dt>Visibility / origin / review</dt><dd>"
            + words(item.get("visibility"))
            + " / "
            + words(item.get("origin"))
            + " / "
            + words(item.get("review_status"))
            + "</dd></dl>"
            + notes(item.get("uncertainty", []))
            + evidence(item.get("evidence_frame_ids", []))
            + "</article>"
        )
    body += "<p>No omitted action is established absent by a missing observation.</p></section>"
    body += '<section id="findings"><h2>Proposed event candidates</h2>'
    for event in view["findings"]:
        body += (
            "<article><h3>"
            + esc(event.get("event_id"))
            + " · "
            + words(event.get("assessment"))
            + "</h3><p>"
            + esc(event.get("value"))
            + "</p><p>Actors: "
            + participant_links(event.get("actor_ids", []))
            + " · recipients: "
            + participant_links(event.get("recipient_ids", []))
            + "</p><p>"
            + seek(event.get("start_sec"))
            + " – "
            + seek(event.get("end_sec"))
            + "</p>"
            + "<p>Observation support: "
            + record_links(event.get("observation_ids", []), "observation", observation_ids)
            + " · rule assessments: "
            + record_links(event.get("legal_assessment_ids", []), "assessment", assessment_ids)
            + "</p>"
            + "<p>Evidence export complete: "
            + words(event.get("evidence_export_complete"))
            + "</p>"
            + notes(event.get("uncertainty", []))
            + evidence(event.get("evidence_frame_ids", []))
            + "</article>"
        )
    if not view["findings"]:
        body += "<p>No event candidates were returned. This is not a clean-negative judgment.</p>"
    coverage = view["coverage"]
    temporal = coverage["temporal"]
    body += (
        '</section><section id="coverage"><h2>Examined and skipped coverage</h2><p>'
        + words(coverage["timeline_status"])
        + " · continuous visibility: "
        + words(temporal.get("continuous_visibility_validated"))
        + "</p>"
    )
    intervals = []
    for name in (
        "scheduled_intervals",
        "examined_intervals",
        "unexamined_intervals",
        "unclear_intervals",
        "output_capacity_limited_intervals",
    ):
        intervals += [[words(name), seek(a), seek(b)] for a, b in temporal.get(name, [])]
    body += table(["Coverage kind", "From", "To"], intervals)
    body += (
        "<p>Completed samples do not prove continuous visibility or an omission opportunity.</p>"
    )
    body += table(
        ["Rule", "Inspection status", "Reason / assessment"],
        [
            [
                esc(r.get("rule_id")),
                words(r.get("status")),
                esc(r.get("reason", r.get("assessment", "Unknown"))),
            ]
            for r in coverage["rules"]
        ],
    )
    body += '</section><section id="rules"><h2>Rule conditions and unresolved prerequisites</h2>'
    for assessment in view["legal"]:
        body += (
            f'<article id="assessment-{esc(assessment.get("assessment_id"))}"><h3>'
            + esc(assessment.get("rule_id"))
            + " · "
            + words(assessment.get("assessment"))
            + "</h3><p>Interpretation: "
            + words(assessment.get("interpretation_status"))
            + " · review: "
            + words(assessment.get("review_status"))
            + "</p><p>"
            + esc(assessment.get("explanation", ""))
            + "</p>"
            + notes(assessment.get("unresolved_dependencies", []))
        )
        specs = {s.get("id"): s for s in assessment.get("condition_specs", [])}
        rows = []
        for condition in assessment.get("conditions", []):
            spec = specs.get(condition["condition_id"], {})
            rows.append(
                [
                    esc(spec.get("proposition", condition["condition_id"])),
                    words(spec.get("category")),
                    words(spec.get("violation_when")),
                    words(spec.get("requires_metadata")),
                    words(spec.get("requires_complete_opportunity")),
                    words(condition.get("result")),
                    participant_links(condition.get("participant_ids", [])),
                    esc(", ".join(condition.get("supporting_evidence_ids", []))),
                    esc(", ".join(condition.get("contradictory_evidence_ids", []))),
                    esc("; ".join(condition.get("unresolved_dependencies", []))),
                ]
            )
        body += table(
            [
                "Condition",
                "Kind",
                "Violation when",
                "Needs metadata",
                "Needs complete opportunity",
                "Result",
                "Participants",
                "Support",
                "Counterevidence",
                "Unresolved",
            ],
            rows,
        )
        body += notes(assessment.get("limitations", []))
        for citation in assessment.get("citations", []):
            url = citation.get("url", "")
            allowed = urlsplit(url).scheme == "https" and urlsplit(url).hostname == "adilet.zan.kz"
            link = f'<a href="{esc(url)}" rel="noreferrer">Official source</a>' if allowed else ""
            body += (
                "<details><summary>"
                + esc(citation.get("title", "Source provision"))
                + "</summary><p>"
                + link
                + "</p><p>"
                + esc(citation.get("text", ""))
                + "</p><p>Version: "
                + esc(citation.get("version_id", "Unknown"))
                + "</p>"
                + notes(citation.get("parent_headings", []))
                + notes(citation.get("source_effect_notices", []))
                + "</details>"
            )
        body += "</article>"
    body += notes(view["legal_limitations"])
    body += (
        "<p>Draft interpretation, unknown applicability and missing metadata remain "
        "unresolved. No legislation research is required from the reviewer.</p></section>"
        '<section id="technical"><h2>Files and provenance</h2>'
        '<p><a href="review.json" download>Structured review JSON</a> · '
        '<a href="original-result.json" download>Complete original API JSON</a> · '
        '<a href="manifest.json">Integrity manifest</a> · '
        '<a href="prior-review/review.html">Original baseline review revision</a></p>'
        "<details><summary>Technical provenance and processing timings</summary>"
        + table(["Stage", "Seconds"], [[words(k), esc(v)] for k, v in view["metrics"].items()])
        + "<p>Original prediction SHA256: <code>"
        + esc(view["original_prediction"]["sha256"])
        + "</code></p>"
        + notes(view["projection_limits"])
        + "</details></section>"
    )
    payload = json.dumps(overlays, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    script = """const rows=OVERLAYS,
v=document.getElementById('video'),c=document.getElementById('overlay');

document.querySelectorAll('[data-seek]').forEach(b=>b.addEventListener('click',()=>{
const t=Number(b.dataset.seek);
if(Number.isFinite(t)&&t>=0){v.currentTime=t;
v.scrollIntoView({block:'center'});
}}));

function draw(){c.width=v.videoWidth||1;
c.height=v.videoHeight||1;
const x=c.getContext('2d');

if(rows.length){let lo=0,hi=rows.length-1;
while(lo<hi){const m=Math.floor((lo+hi)/2);

if(rows[m].t<v.currentTime)lo=m+1;
else hi=m;
}
let r=rows[lo];
if(lo&&Math.abs(rows[lo-1].t-v.currentTime)<Math.abs(r.t-v.currentTime))r=rows[lo-1];

document.getElementById('sample-note').textContent='Nearest saved sample '+r.t.toFixed(3)
  +'s · no interpolation or identity approval.';

if(Math.abs(r.t-v.currentTime)<=.101){x.lineWidth=2;
x.font='18px sans-serif';
x.strokeStyle='#facc15';
x.fillStyle='#facc15';

for(const[id,b]of Object.entries(r.boxes)){x.strokeRect(
b[0]*c.width,b[1]*c.height,(b[2]-b[0])*c.width,(b[3]-b[1])*c.height);
x.fillText(id,b[0]*c.width,Math.max(18,b[1]*c.height));
}}}
requestAnimationFrame(draw);
}draw();
""".replace("OVERLAYS", payload)
    return (
        """<!doctype html><html lang="en">
<meta charset="utf-8">
<meta name="viewport"
content="width=device-width, initial-scale=1">
<meta name="referrer"
content="no-referrer">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none';
 img-src 'self';
 media-src 'self';
 script-src 'unsafe-inline';
 style-src 'unsafe-inline'">
<title>Private structured video review</title><style>
body{font:16px/1.55 system-ui;
margin:0 auto;
padding:2rem 1.25rem;
max-width:1160px;
color:#17242f;
background:#f7f9fb}

h1{font-size:2rem;
line-height:1.2}
h2{font-size:1.4rem}
h3{font-size:1.1rem}
.eyebrow{font-size:.75rem;
letter-spacing:.1em;
color:#526574}

nav{display:flex;
gap:1rem;
flex-wrap:wrap;
margin:1.5rem 0}
a{color:#155e85}
section{margin:1.5rem 0;
padding:1.25rem;
background:white;
border:1px solid #d7e0e7;
border-radius:.5rem}

article{border-top:1px solid #d7e0e7;
padding:1rem 0}
.status{border-left:4px solid #b07b14}
.unknown{color:#805c14}
.playback{position:relative}
video{width:100%;
display:block;
background:#111}

canvas{position:absolute;
inset:0;
width:100%;
height:100%;
pointer-events:none}
.evidence{display:flex;
gap:1rem;
flex-wrap:wrap}
figure{margin:.5rem 0;
max-width:340px}
img{width:100%;
height:auto}
figcaption{font-size:.85rem}

.table-wrap{overflow:auto}
table{border-collapse:collapse;
width:100%;
font-size:.9rem}
th,td{text-align:left;
vertical-align:top;
padding:.6rem;
border-bottom:1px solid #d7e0e7}
th{background:#f1f5f8}

button{font:inherit;
color:#155e85;
background:#f1f6f9;
border:1px solid #b7ccd8;
border-radius:.25rem;
cursor:pointer;
padding:.15rem .4rem}
button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #2584b8}

dl{display:grid;
grid-template-columns:12rem 1fr;
gap:.3rem}
dt{font-weight:600}
dd{margin:0}
details{margin:1rem 0}
summary{cursor:pointer;
font-weight:600}
code{overflow-wrap:anywhere}
p,td,dd{overflow-wrap:anywhere}

@media(max-width:600px){body{padding:1rem .5rem}
section{padding:.8rem}
dl{display:block}
dd{margin-bottom:.5rem}
}

</style>"""
        + body
        + "<script>"
        + script
        + "</script></html>"
    )


def private_path(path):
    path = Path(path).resolve()
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise ValueError("Private review artifacts must stay outside Git checkouts")
    return path


def save_json(path, value):
    with path.open("x") as output:
        json.dump(value, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write("\n")
    path.chmod(0o600)


def generate_run(run_root, output):
    """Render the preserved mechanic-validation layout into a NEW private revision."""
    root, output = private_path(run_root), private_path(output)
    if output.exists():
        raise FileExistsError("Preserve old packets; choose a new output directory")
    rows = json.loads((root / "inference-inputs.json").read_bytes())
    output.mkdir(parents=True, mode=0o700)
    receipts = []
    for n, row in enumerate(rows, 1):
        neutral = row["neutral_file"]
        if not re.fullmatch(r"clip\d{3}\.mov", neutral):
            raise ValueError("Expected the saved neutral development name")
        stem = Path(neutral).stem
        restored = root / f"gpu-case-{n}-restored"
        allowlist = json.loads((restored / "config/development-allowlist.json").read_bytes())
        matches = [
            r
            for r in allowlist["groups"]
            if r.get("neutral_file") == neutral and r.get("recording_id") == row["source_sha256"]
        ]
        if len(matches) != 1 or matches[0].get("split") != "development":
            raise ValueError("Saved source is not on the development allowlist")
        source = private_path(row["source"])
        if digest(source) != row["source_sha256"]:
            raise ValueError("Original allowlisted source fingerprint changed")
        client = restored / "rehearsal" / stem
        original = client / "job-response.json"
        raw = original.read_bytes()
        fingerprint = hashlib.sha256(raw).hexdigest()
        inventory = json.loads((restored / "preservation-manifest.json").read_bytes())
        original_key = str(original.relative_to(restored))
        if inventory["files"].get(original_key) != fingerprint:
            raise ValueError("Original prediction differs from the preserved baseline")
        job = json.loads(raw)
        if job.get("result", {}).get("source_sha256", row["source_sha256"]) != row["source_sha256"]:
            raise ValueError("Prediction/source mismatch")
        view = project_review(job, fingerprint)
        case = output / f"case-{n}"
        case.mkdir(mode=0o700)
        (case / "frames").mkdir(mode=0o700)
        (case / "prior-evidence").mkdir(mode=0o700)
        (case / "original-result.json").write_bytes(raw)
        (case / "original-result.json").chmod(0o400)
        previous = root / "gpu-review-v4" / f"case-{n}"
        origin = root / "executions" / stem
        for name in ("source.mp4", "original.mov", "source-frames.json"):
            (case / name).symlink_to((origin / name).resolve(strict=True))
        if digest(case / "original.mov") != row["source_sha256"]:
            raise ValueError("Playback original differs from the allowlisted source")
        (case / "prior-review").symlink_to(previous.resolve(strict=True), target_is_directory=True)
        shutil.copyfile(previous / "review-template.json", case / "review-template.json")
        for image in previous.glob("*.jpg"):
            (case / "prior-evidence" / image.name).symlink_to(image.resolve(strict=True))
        source_table = json.loads((origin / "source-frames.json").read_bytes())
        if source_table["source_sha256"] != row["source_sha256"]:
            raise ValueError("Frame table/source mismatch")
        frame_table = source_table["frames"]
        by_frame = {f["frame_id"]: f for f in frame_table}
        ids = set()
        for item in view["observations"] + view["findings"]:
            ids.update(item.get("evidence_frame_ids", []))
        for person in view["people"]:
            for role in person["role_hypotheses"]:
                ids.update(role["claim"].get("evidence_frame_ids", []))
        assets = {}
        api_evidence = {
            e["frame_id"]: e for event in view["findings"] for e in event.get("evidence", [])
        }
        for fid in sorted(ids):
            if not re.fullmatch(r"f\d{6}", fid) or fid not in by_frame:
                raise ValueError("Cited evidence lacks an original source-frame record")
            api_image = client / "evidence" / (fid + ".jpg")
            image = api_image if api_image.exists() else previous / ("observation-" + fid + ".jpg")
            image_hash = digest(image)
            if image == api_image:
                item = api_evidence.get(fid, {})
                expected = item.get("image_sha256", item.get("jpeg_sha256"))
            else:
                relative = str(image.resolve(strict=True).relative_to(restored))
                expected = inventory["files"].get(relative)
            if expected != image_hash:
                raise ValueError("Cited image differs from preserved evidence")
            (case / "frames" / (fid + ".jpg")).symlink_to(image.resolve(strict=True))
            assets[fid] = {
                **selected(by_frame[fid], ("source_pts", "time_base", "timestamp_sec")),
                "file": "frames/" + fid + ".jpg",
                "sha256": image_hash,
                "origin_label": "Original API JPEG; verified in baseline"
                if image == api_image
                else "Persisted scene view; may be resized",
            }
        result = job.get("result", {})
        registry = result.get("participants", {})
        overlays = [
            {
                "t": f["timestamp_sec"],
                "boxes": registry.get("frame_boxes", {}).get(f["frame_id"], {}),
            }
            for f in registry.get("sampled_source_frames", [])
        ]
        view["evidence_frames"] = assets
        save_json(case / "review.json", view)
        (case / "review.html").write_text(render_review(view, assets, overlays))
        files = {str(p.relative_to(case)): digest(p) for p in case.rglob("*") if p.is_file()}
        receipt = {
            "schema_version": "forte.review-manifest/1",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "renderer_sha256": digest(Path(__file__)),
            "original_prediction_sha256": fingerprint,
            "original_bytes_preserved": digest(case / "original-result.json") == fingerprint,
            "original_file_unchanged": digest(original) == fingerprint,
            "previous_review_sha256": digest(previous / "review.html"),
            "parent_packet_revision": "gpu-review-v4",
            "prior_cited_images_preserved": len(list(previous.glob("*.jpg"))),
            "new_model_calls": 0,
            "files": files,
        }
        save_json(case / "manifest.json", receipt)
        receipts.append(receipt)
    links = "".join(
        f'<li><a href="case-{n}/review.html">Case {n}</a></li>' for n in range(1, len(rows) + 1)
    )
    (output / "index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta name="referrer" content="no-referrer">'
        "<h1>Structured saved-prediction review</h1><p>New presentation "
        "revision; original predictions and prior reviews preserved. "
        "Human-local review only. No new inference or approval.</p><ol>" + links + "</ol>"
    )
    save_json(
        output / "generation.json",
        {
            "cases": len(rows),
            "new_model_calls": 0,
            "all_prediction_bytes_preserved": all(
                r["original_bytes_preserved"] and r["original_file_unchanged"] for r in receipts
            ),
        },
    )
    return {
        "cases_rendered": len(rows),
        "new_model_calls": 0,
        "original_predictions_preserved": True,
    }


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate_run(args.run_root, args.output)))


if __name__ == "__main__":
    main()
