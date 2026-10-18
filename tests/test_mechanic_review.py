"""Generated saved-result fixtures only; no sponsor facts or model calls."""

import copy
import hashlib
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from forte.mechanic_review import digest, generate_run, private_path, project_review, render_review


@pytest.fixture
def saved():
    people = []
    for number in (1, 2):
        people.append(
            {
                "participant_id": f"p{number}",
                "identity_status": "model_proposal",
                "role_hypotheses": [],
                "appearance_gallery": [{"embedding": [1, 0]}],
                "track_segments": [
                    {
                        "segment_id": f"s{number}",
                        "tracker_id": number,
                        "observations": [
                            {"frame_id": "f000000", "timestamp_sec": 0},
                            {"frame_id": "f000001", "timestamp_sec": 1},
                        ],
                    }
                ],
            }
        )
    observations = [
        {
            "observation_id": "action1",
            "kind": "interaction",
            "value": "Synthetic handoff",
            "actor_ids": ["p1"],
            "recipient_ids": ["p2"],
            "source_sha256": "a" * 64,
            "phase": "synthetic interaction",
            "localization": "source_evidence_envelope",
            "start_sec": 0,
            "end_sec": 1,
            "decisive_sec": 1,
            "evidence_frame_ids": ["f000000", "f000001"],
            "origin": "model",
            "review_status": "unreviewed",
            "visibility": "partly_occluded",
            "uncertainty": ["Object identity unresolved"],
        }
    ]
    return {
        "status": "done",
        "result": {
            "schema_version": "forte.reasoning/1",
            "source_sha256": "a" * 64,
            "source": {"duration_sec": 2, "frame_count": 2},
            "execution": {"status": "partial"},
            "assessment": "insufficient_evidence",
            "review_status": "unreviewed",
            "participants": {
                "participants": people,
                "segments": [],
                "frame_boxes": {"f000000": {"p1": [0, 0, 0.4, 1], "p2": [0.6, 0, 1, 1]}},
                "sampled_source_frames": [{"frame_id": "f000000", "timestamp_sec": 0}],
                "view_observations": [],
                "unresolved_matches": [],
            },
            "timeline": {
                "status": "budget_exhausted",
                "observations": observations,
                "coverage": {
                    "scheduled_intervals": [[0, 2]],
                    "examined_intervals": [[0, 1]],
                    "unexamined_intervals": [[1, 2]],
                    "continuous_visibility_validated": False,
                },
                "unresolved_questions": ["Synthetic role question"],
            },
            "events": [
                {
                    "event_id": "event1",
                    "value": "Synthetic event",
                    "assessment": "insufficient_evidence",
                    "actor_ids": ["p1"],
                    "recipient_ids": ["p2"],
                    "observation_ids": ["action1"],
                    "start_sec": 0,
                    "end_sec": 1,
                    "evidence_frame_ids": ["f000000", "f000001"],
                    "evidence": [],
                }
            ],
            "legal": {
                "rule_coverage": [
                    {
                        "rule_id": "synthetic-rule",
                        "status": "not_evaluated",
                        "reason": "Synthetic budget limit",
                    }
                ],
                "assessments": [],
            },
            "limitations": ["Synthetic partial inspection"],
            "metrics": {"total_seconds": 3},
        },
    }


def test_multiple_independent_people_and_actor_recipient_survive(saved):
    original = copy.deepcopy(saved)
    view = project_review(saved, "b" * 64)
    assert [p["participant_id"] for p in view["people"]] == ["p1", "p2"]
    assert all(p["role_state"] == "not_established" for p in view["people"])
    assert view["summary"]["physical_person_count"] is None
    assert view["observations"][0]["actor_ids"] == ["p1"]
    assert view["observations"][0]["recipient_ids"] == ["p2"]
    assert view["observations"][0]["source_sha256"] == "a" * 64
    assert view["observations"][0]["phase"] == "synthetic interaction"
    assert view["findings"][0]["observation_ids"] == ["action1"]
    assert "appearance_gallery" not in json.dumps(view)
    assert saved == original


def test_time_scoped_roles_allow_same_role_and_null_without_assignment(saved):
    roles = []
    for number in (1, 2):
        roles.append(
            {
                "observation_id": f"role{number}",
                "kind": "role",
                "value": "Synthetic counter operation",
                "actor_ids": [f"p{number}"],
                "start_sec": 0.2,
                "end_sec": 0.7,
                "origin": "model",
                "review_status": "unreviewed",
                "evidence_frame_ids": ["f000000"],
                "uncertainty": ["Only a sampled activity"],
            }
        )
    saved["result"]["timeline"]["observations"] += roles
    saved["result"]["participants"]["participants"][0]["role_hypotheses"] = [
        {k: v for k, v in roles[0].items() if k not in {"kind", "actor_ids", "uncertainty"}},
        {
            "observation_id": "unresolved-role",
            "value": None,
            "start_sec": 1,
            "end_sec": 2,
            "origin": "model",
            "uncertainty": ["Role unavailable"],
            "evidence_frame_ids": [],
        },
    ]
    view = project_review(saved, "b" * 64)
    first = view["people"][0]["role_hypotheses"]
    assert len(first) == 2
    assert first[0]["record_sources"] == ["participant_registry", "timeline"]
    assert first[0]["claim"]["start_sec"] == 0.2
    assert first[0]["claim"]["end_sec"] == 0.7
    assert first[0]["claim"]["uncertainty"] == ["Only a sampled activity"]
    assert first[1]["claim"]["value"] is None
    assert view["people"][1]["role_hypotheses"][0]["claim"]["value"] == roles[0]["value"]


def test_conflicting_role_records_and_reflection_ownership_are_not_merged(saved):
    registry = saved["result"]["participants"]
    registry["participants"][0]["role_hypotheses"] = [
        {"observation_id": "same-id", "value": "Synthetic A"},
        {"observation_id": "same-id", "value": "Synthetic B"},
    ]
    registry["view_observations"] = [
        {"view_kind": "reflection", "canonical_person_id": None, "review_status": "confirmed"}
    ]
    registry["segments"] = [
        {"segment_id": "unassociated", "tracker_id": -1, "participant_id": None, "observations": []}
    ]
    view = project_review(saved, "b" * 64)
    assert len(view["people"][0]["role_hypotheses"]) == 2
    assert view["views"][0]["canonical_person_id"] is None
    assert view["geometry_only"][0]["participant_id"] is None
    assert len(view["people"]) == 2


@pytest.mark.parametrize("status", ["failed", "processing"])
def test_unfinished_jobs_keep_unknown_assessment(status):
    view = project_review({"status": status, "error": {"code": "synthetic"}}, "b" * 64)
    assert view["processing"]["assessment"] is None
    assert view["processing"]["presentation_state"] == "incomplete_inspection"
    assert "Incomplete inspection" in render_review(view, {}, [])


def test_readable_sections_preserve_partial_coverage_and_escape_content(saved):
    attack = '</script><script>alert("synthetic")</script>'
    saved["result"]["timeline"]["observations"][0]["value"] = attack
    saved["result"]["assessment"] = "no_violation_observed"
    view = project_review(saved, "b" * 64)
    page = render_review(view, {}, [{"t": 0, "boxes": {attack: [0, 0, 1, 1]}}])
    assert view["processing"]["assessment"] == "no_violation_observed"
    assert "Incomplete inspection: no whole-recording clearance" in page
    assert "Examined and skipped coverage" in page and "unexamined intervals" in page
    assert "<pre" not in page
    assert page.count("<script>") == 1
    assert attack not in page and "&lt;/script&gt;" in page and "\\u003c/script>" in page
    assert "Structured review JSON" in page and "Complete original API JSON" in page


def test_private_paths_and_fresh_output_are_enforced(tmp_path):
    repo = tmp_path / "repository"
    repo.mkdir()
    (repo / ".git").write_text("synthetic worktree marker")
    with pytest.raises(ValueError, match="outside Git"):
        private_path(repo / "private-output")
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="new output"):
        generate_run(tmp_path, existing)


def test_supported_event_stays_linked_and_visible_during_incomplete_inspection(saved):
    saved["result"]["execution"]["status"] = "completed"
    event = saved["result"]["events"][0]
    event["assessment"] = "supported_violation"
    event["legal_assessment_ids"] = ["legal1", "missing-assessment"]
    saved["result"]["legal"]["assessments"] = [
        {
            "assessment_id": "legal1",
            "rule_id": "synthetic-rule",
            "assessment": "supported_violation",
            "interpretation_status": "approved",
            "review_status": "unreviewed",
            "condition_specs": [
                {
                    "id": "opportunity",
                    "proposition": "Synthetic opportunity completely visible",
                    "category": "coverage",
                    "violation_when": "satisfied",
                    "requires_complete_opportunity": True,
                }
            ],
            "conditions": [
                {"condition_id": "opportunity", "result": "unknown", "participant_ids": []}
            ],
            "citations": [
                {"title": "Synthetic rule", "url": "javascript:alert(1)", "text": "No load"}
            ],
        }
    ]
    view = project_review(saved, "b" * 64)
    page = render_review(view, {}, [])
    assert view["processing"]["presentation_state"] == "incomplete_inspection"
    assert view["findings"][0]["assessment"] == "supported_violation"
    assert "supported violation" in page
    assert 'href="#observation-action1"' in page
    assert 'href="#assessment-legal1"' in page
    assert 'id="assessment-legal1"' in page
    assert "missing-assessment" in page and 'href="#assessment-missing-assessment"' not in page
    assert "Needs complete opportunity" in page and "Synthetic opportunity" in page
    assert 'href="javascript:' not in page


def synthetic_run(tmp_path, saved):
    root = tmp_path / "synthetic-run"
    root.mkdir()
    source = root / "clip001.mov"
    source.write_bytes(b"generated source bytes; renderer never decodes media")
    source_hash = digest(source)
    saved["result"]["source_sha256"] = source_hash
    row = {"neutral_file": source.name, "source": str(source), "source_sha256": source_hash}
    (root / "inference-inputs.json").write_text(json.dumps([row]))
    restored = root / "gpu-case-1-restored"
    (restored / "config").mkdir(parents=True)
    (restored / "config/development-allowlist.json").write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "neutral_file": source.name,
                        "recording_id": source_hash,
                        "split": "development",
                    }
                ]
            }
        )
    )
    client = restored / "rehearsal/clip001"
    (client / "evidence").mkdir(parents=True)
    original = client / "job-response.json"
    origin = root / "executions/clip001"
    origin.mkdir(parents=True)
    (origin / "source.mp4").write_bytes(b"synthetic playback placeholder")
    (origin / "original.mov").symlink_to(source)
    frames = [
        {"frame_id": f"f{i:06d}", "timestamp_sec": i, "source_pts": i * 10, "time_base": "1/10"}
        for i in range(2)
    ]
    (origin / "source-frames.json").write_text(
        json.dumps({"source_sha256": source_hash, "frames": frames})
    )
    prior = root / "gpu-review-v4/case-1"
    prior.mkdir(parents=True)
    (prior / "review.html").write_text("<h1>Synthetic prior revision</h1>")
    (prior / "review-template.json").write_text(json.dumps({"reviewer": None}))
    evidence = []
    for i in range(2):
        fid = f"f{i:06d}"
        image = client / "evidence" / (fid + ".jpg")
        image.write_bytes(b"synthetic evidence bytes " + bytes([i]))
        evidence.append({"frame_id": fid, "image_sha256": digest(image), **frames[i]})
        (prior / ("api-" + fid + ".jpg")).symlink_to(image)
    saved["result"]["events"][0]["evidence"] = evidence
    original.write_text(json.dumps(saved, ensure_ascii=False, indent=3))
    (restored / "preservation-manifest.json").write_text(
        json.dumps({"files": {"rehearsal/clip001/job-response.json": digest(original)}})
    )
    return root, original


def test_generation_preserves_exact_originals_assets_and_local_links(tmp_path, saved):
    root, original = synthetic_run(tmp_path, saved)
    before = original.read_bytes()
    out = tmp_path / "new-packet"
    receipt = generate_run(root, out)
    assert receipt == {
        "cases_rendered": 1,
        "new_model_calls": 0,
        "original_predictions_preserved": True,
    }
    case = out / "case-1"
    assert original.read_bytes() == (case / "original-result.json").read_bytes() == before
    manifest = json.loads((case / "manifest.json").read_bytes())
    projection = json.loads((case / "review.json").read_bytes())
    assert projection["evidence_frames"]["f000001"]["source_pts"] == 10
    assert projection["evidence_frames"]["f000001"]["file"] == "frames/f000001.jpg"
    assert manifest["original_prediction_sha256"] == hashlib.sha256(before).hexdigest()
    assert manifest["original_bytes_preserved"] and manifest["original_file_unchanged"]
    assert manifest["prior_cited_images_preserved"] == 2
    assert all(digest(case / name) == expected for name, expected in manifest["files"].items())

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attrs):
            self.links += [v for k, v in attrs if k in {"src", "href"} and v]

    page = Links()
    page.feed((case / "review.html").read_text())
    for link in page.links:
        if not link.startswith("#"):
            assert ":" not in link and (case / link).exists()
    with pytest.raises(FileExistsError):
        generate_run(root, out)


def test_reserved_source_is_refused_before_source_open(tmp_path, saved):
    root, original = synthetic_run(tmp_path, saved)
    allowlist = root / "gpu-case-1-restored/config/development-allowlist.json"
    value = json.loads(allowlist.read_bytes())
    value["groups"][0]["split"] = "reserved"
    allowlist.write_text(json.dumps(value))
    (root / "clip001.mov").unlink()
    with pytest.raises(ValueError, match="development allowlist"):
        generate_run(root, tmp_path / "rejected-packet")
    assert original.exists()


def test_corrupt_evidence_is_rejected(tmp_path, saved):
    root, _ = synthetic_run(tmp_path, saved)
    (root / "gpu-case-1-restored/rehearsal/clip001/evidence/f000000.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="preserved evidence"):
        generate_run(root, tmp_path / "rejected-packet")


def test_playback_original_must_match_allowlisted_source(tmp_path, saved):
    root, _ = synthetic_run(tmp_path, saved)
    original_link = root / "executions/clip001/original.mov"
    original_link.unlink()
    original_link.write_bytes(b"different generated recording")
    with pytest.raises(ValueError, match="Playback original"):
        generate_run(root, tmp_path / "rejected-packet")


def test_changed_original_cannot_be_rebranded_as_preserved(tmp_path, saved):
    root, original = synthetic_run(tmp_path, saved)
    original.write_bytes(original.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="preserved baseline"):
        generate_run(root, tmp_path / "rejected-packet")


def test_synthetic_playback_script_draws_both_ids_and_seeks(saved):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Optional synthetic JavaScript execution requires Node")
    view = project_review(saved, "b" * 64)
    page = render_review(
        view, {}, [{"t": 0, "boxes": {"p1": [0, 0, 0.4, 1], "p2": [0.6, 0, 1, 1]}}]
    )
    script = re.search(r"<script>(.*?)</script>", page, flags=re.S).group(1)
    before = """const labels=[],button={dataset:{seek:'0.5'},
addEventListener:(k,f)=>button.click=f};
const video={videoWidth:100,videoHeight:100,currentTime:0,scrollIntoView:()=>{}};
const canvas={getContext:()=>({strokeRect:()=>{},fillText:id=>labels.push(id)})};
const document={getElementById:id=>id==='video'?video:id==='overlay'?canvas:{},
querySelectorAll:()=>[button]};const requestAnimationFrame=()=>{};
"""
    after = """button.click();
if(labels.join(',')!=='p1,p2'||video.currentTime!==0.5)process.exit(1);
"""
    checked = subprocess.run([node, "-e", before + script + after], capture_output=True, timeout=10)
    assert checked.returncode == 0
