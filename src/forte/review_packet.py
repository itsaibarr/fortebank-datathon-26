"""Static private review navigation, not an annotation frontend or a reviewer."""

import html
import json
import os
from pathlib import Path

from forte.person_proposals import boxes_at, write_json
from forte.tracking import TrackManifest


def write_overview(directory):
    directory = Path(directory)
    index = json.loads((directory / "index.json").read_bytes())
    links = []
    for row in index["records"]:
        path = (directory / row["manifest"]).parent
        if not (path / "tracks.json").exists():
            continue
        rel = Path(os.path.relpath(path, directory)).as_posix()
        links.append(
            f'<li><a href="{rel}/review.html">{html.escape(row["clip_id"])} full review</a>'
            + (
                f' · <a href="{rel}/human-check.html">priority human check</a>'
                if row.get("pilot")
                else ""
            )
            + " · draft / training excluded</li>"
        )
        if not row.get("pilot"):
            continue
        assets = json.loads((path / "review-assets.json").read_bytes())
        binding = json.loads((path / "correction-binding-pending.json").read_bytes())
        review = json.loads((path / "legacy-review.json").read_bytes())
        intervals = json.loads((path / "review-intervals.json").read_bytes())
        m = TrackManifest.model_validate_json((path / "tracks.json").read_bytes())
        reference = binding.get("preserved_role_reference")
        if reference:
            refs = reference["variants"][0]["frames"]
            ids = [refs[i]["frame_id"] for i in [0, len(refs) // 2, len(refs) - 1]]
            selected = [next(a for a in assets if a["frame_id"] == id) for id in ids]
        else:
            start, end = (
                (intervals[0]["start_sec"], intervals[0]["end_sec"])
                if intervals
                else (0, m.duration_sec)
            )
            selected = [
                min(assets, key=lambda a: abs(a["timestamp_sec"] - t))
                for t in [start, (start + end) / 2, end]
            ]
        middle = selected[1]
        candidates = [s.id for s, _, _ in boxes_at(m, int(middle["frame_id"][1:]))]
        start = max(0, selected[0]["timestamp_sec"] - 5)
        end = min(m.duration_sec, selected[-1]["timestamp_sec"] + 5)
        request = dict(
            status="pending",
            frame_id=middle["frame_id"],
            candidate_segment_ids=candidates,
            surrounding_frame_ids=[a["frame_id"] for a in selected],
            playback_start_sec=start,
            playback_end_sec=end,
            question="Which outlined segment matches the preserved correction? "
            "Check service context; return segment IDs or unclear. "
            "This does not approve geometry/joins.",
            actual_reviewer=None,
        )
        request_path = path / "human-review-request.json"
        if not request_path.exists():
            write_json(request_path, request)
        notes = "".join(
            "<dt>" + html.escape(k) + "</dt><dd>" + html.escape(str(review.get(k, ""))) + "</dd>"
            for k in [
                "private_remarks",
                "actor_assignment_certainty",
                "review_scope",
                "reviewer",
                "reviewed_at_utc",
            ]
        )
        cards = []
        for asset in selected:
            crops = "".join(
                f'<a href="{html.escape(c["path"])}"><img class="crop" '
                f'src="{html.escape(c["path"])}"><br>{html.escape(c["segment_id"])}</a>'
                for c in asset["crops"]
            )
            cards.append(
                f"<section><h2>{asset['frame_id']} · {asset['timestamp_sec']:.3f}s</h2>"
                f'<a href="{asset["overlay"]}"><img class="scene" src="{asset["overlay"]}"></a>'
                f'<p><a href="{asset["full_scene"]}">Full scene without overlays</a></p>'
                f'<div class="crops">{crops}</div></section>'
            )
        page = (
            HEADER + f"<h1>Local human check — {m.clip_id}</h1><p>At <b>{middle['frame_id']}</b>, "
        )
        page += (
            "outlined choices: <b>"
            + html.escape(", ".join(candidates) or "no detector box")
            + "</b>"
        )
        page += (
            """ or <b>unclear</b>. Watch surrounding service context before choosing.
These IDs/boxes are proposals. A role answer does not approve all geometry or joins.</p>
<h2>Preserved human correction</h2><dl>"""
            + notes
            + "</dl>"
        )
        page += f"""<p><a href="legacy-review.json">Original review</a> ·
<a href="correction-binding-pending.json">Preserved reference and pending binding</a></p>
<h2>Full-scene context playback</h2><video controls preload="metadata"
src="review.mp4#t={start:.3f},{end:.3f}"></video>
<p><a href="review.mp4">Entire clip with draft IDs</a> ·
<a href="oriented-source.mp4">Clean entire clip</a></p><div class="grid">"""
        (path / "human-check.html").write_text(page + "".join(cards) + "</div>")
    (directory / "review.html").write_text(
        HEADER + "<h1>Private development review queue</h1>"
        "<p>Draft proposals; reviewed-label and session-split gates remain pending. "
        "Inspect context and track continuity before labeling a role or action.</p><ul>"
        + "".join(links)
        + "</ul>"
    )


HEADER = """<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' file: data:;
style-src 'unsafe-inline'">
<title>Private human review</title><style>
body{font:17px system-ui;background:#181818;color:#eee;margin:28px;line-height:1.5}
a{color:#aaf}video{width:100%;max-height:70vh;background:#080808}
.grid{display:grid;grid-template-columns:repeat(3,minmax(260px,1fr));gap:20px}
.scene{width:100%;max-height:900px;object-fit:contain}section{background:#242424;padding:12px}
dt{font-weight:bold}dd{white-space:pre-wrap;margin:0 0 12px}
.crops{display:flex;gap:12px;overflow:auto}
.crop{max-height:230px;max-width:150px}h1{font-size:26px}h2{font-size:18px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}</style>"""
