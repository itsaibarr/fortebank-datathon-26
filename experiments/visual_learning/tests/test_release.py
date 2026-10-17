import json

import pytest

from forte_visual.adapter import reviewed_targets
from forte_visual.io import digest, local
from forte_visual.release import gate, snapshot, verify
from forte_visual.synthetic import create


@pytest.fixture
def release(tmp_path):
    return create(tmp_path / "release")


def mutate(path, edit):
    value = json.loads(path.read_bytes())
    edit(value)
    path.write_text(json.dumps(value))


def test_completed_release_snapshot_is_hash_bound_and_no_training(release, tmp_path):
    r, pairs, receipt = verify(release)
    assert receipt["reviewed_evaluation_targets"] == 6
    assert receipt["eligible_training_targets"] == 0
    assert gate(pairs) == []
    assert gate(pairs, training=True)
    assert snapshot(release, tmp_path / "snapshot") == receipt
    assert verify(tmp_path / "snapshot/release.json")[2] == receipt
    with pytest.raises(FileExistsError):
        snapshot(release, tmp_path / "snapshot")


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.update(export_complete=False),
        lambda r: r.update(producer_schema="unknown/2"),
        lambda r: r["files"].update({"../escape": "0" * 64}),
        lambda r: r["clips"][0]["images"].update({"invented": "clip000/images/f000000.jpg"}),
        lambda r: r["clips"][0].update(media="missing.mov"),
    ],
)
def test_incomplete_unknown_escaping_or_unbound_release_rejected(release, edit):
    mutate(release, edit)
    with pytest.raises((ValueError, FileNotFoundError)):
        verify(release)


def test_corruption_and_changing_release_rejected(release, monkeypatch):
    import forte_visual.release as module

    real = module.digest
    calls = 0

    def changing(path):
        nonlocal calls
        if path == release:
            calls += 1
            return real(path) if calls == 1 else "0" * 64
        return real(path)

    monkeypatch.setattr(module, "digest", changing)
    with pytest.raises(ValueError, match="changed"):
        verify(release)
    monkeypatch.setattr(module, "digest", real)
    (release.parent / "clip000/images/f000000.jpg").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="corrupt"):
        verify(release)


def test_draft_conflict_and_uncertain_join_never_become_targets(release):
    _, pairs, _ = verify(release)
    _, m, a = pairs[0]
    a.facts[0].review_status = "draft"
    assert len(reviewed_targets(m, a)) == 2
    a.facts[0].review_status = "confirmed"
    conflict = a.facts[0].model_copy(update={"id": "contradiction", "value": "customer"})
    a.facts.append(conflict)
    assert all(f.kind != "role" for f in reviewed_targets(m, a))
    m.segments[0].identity_uncertain = True
    assert reviewed_targets(m, a) == []


def test_group_leakage_rejected_after_valid_hashes(release):
    r = json.loads(release.read_bytes())
    p = release.parent / r["clips"][1]["manifest"]
    mutate(p, lambda m: m.update(session_group="session0", split="validation"))
    mutate(release, lambda r: r["files"].update({str(p.relative_to(release.parent)): digest(p)}))
    with pytest.raises(ValueError, match="leakage"):
        verify(release)


def test_symlink_rejected(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path / "other")
    with pytest.raises(ValueError, match="symlink"):
        local(tmp_path, "link")


def test_only_separately_reviewed_ambiguity_can_survive_occlusion(release):
    _, pairs, _ = verify(release)
    _, m, a = pairs[0]
    for b in m.segments[0].boxes:
        b.occluded = True
    assert reviewed_targets(m, a) == []
    a.facts[0].target_kind = "abstention"
    a.facts[0].value = "unclear"
    a.facts[0].observation_state = "not_visible"
    assert [f.id for f in reviewed_targets(m, a)] == ["role"]


def test_private_writer_refuses_any_git_worktree(tmp_path):
    from forte_visual.io import private_dir

    (tmp_path / ".git").write_text("gitdir: synthetic")
    with pytest.raises(ValueError, match="outside Git"):
        private_dir(tmp_path / "private-run")


def test_real_release_requires_authoritative_development_allowlist_and_excludes_reserved(release):
    r = json.loads(release.read_bytes())
    r["synthetic"] = False
    release.write_text(json.dumps(r))
    with pytest.raises(ValueError, match="allowlist"):
        verify(release)
    allow = release.parent / "selection.json"
    allow.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "split": "development",
                        "neutral_file": "clip000.mov",
                        "recording_id": r["files"]["clip000/source.mov"],
                    },
                    {
                        "split": "holdout",
                        "neutral_file": "clip001.mov",
                        "recording_id": r["files"]["clip001/source.mov"],
                    },
                ]
            }
        )
    )
    r["development_allowlist"] = allow.name
    r["files"][allow.name] = digest(allow)
    release.write_text(json.dumps(r))
    with pytest.raises(ValueError, match="Reserved"):
        verify(release)


def test_training_gate_counts_independent_groups_per_action_not_windows(tmp_path):
    path = create(tmp_path / "release", count=6)
    raw = json.loads(path.read_bytes())
    for i, clip in enumerate(raw["clips"]):
        manifest_path = path.parent / clip["manifest"]
        m = json.loads(manifest_path.read_bytes())
        if i:
            m.update(
                split="train" if i <= 3 else "validation",
                split_frozen=True,
                training_eligible=True,
                exclusion_reasons=[],
            )
        manifest_path.write_text(json.dumps(m))
        raw["files"][clip["manifest"]] = digest(manifest_path)
    path.write_text(json.dumps(raw))
    pairs = verify(path)[1]
    assert gate(pairs, training=True) == []
    pairs[-1][1].session_group = pairs[-2][1].session_group
    assert gate(pairs, training=True)  # another crop/session copy cannot satisfy floor


def test_actorless_positive_action_producer_bypass_rejected_by_consumer(release):
    from forte.tracking import training_targets, validate_pair

    from forte_visual.adapter import load_pair

    _, pairs, _ = verify(release)
    clip, m, a = pairs[0]
    f = next(f for f in a.facts if f.kind == "action")
    f.actor_id = None
    f.segment_ids = []
    f.counterpart_actor_id = None
    f.counterpart_segment_ids = []
    f.counterpart_frame_ids = []
    # Demonstrated producer bypass remains pending its owner's fix.
    validate_pair(m, a)
    m.regression_only = False
    m.split_frozen = True
    m.training_eligible = True
    m.exclusion_reasons = []
    assert f.id in {x.id for x in training_targets(m, a)}
    with pytest.raises(ValueError, match="requires actor"):
        reviewed_targets(m, a, training=True)
    target = release.parent / clip.annotation
    target.write_text(a.model_dump_json())
    with pytest.raises(ValueError, match="requires actor"):
        load_pair(release.parent / clip.manifest, target)
    mutate(release, lambda r: r["files"].update({clip.annotation: digest(target)}))
    with pytest.raises(ValueError, match="requires actor"):
        verify(release)


def test_v2_unknown_reflection_is_preserved_without_creating_person_or_target(release):
    from forte.tracking import TrackManifest

    from forte_visual.inputs import aliases

    _, pairs, _ = verify(release)
    _, m, a = pairs[0]
    raw = m.model_dump(mode="json")
    raw["schema_version"] = 2
    raw["view_observations"] = [
        {
            "id": "reflection",
            "segment_id": "s0002",
            "view_kind": "reflection",
            "review_scope": "synthetic view observation only",
            "candidate_frame_ids": ["f000000"],
            "reviewed_frame_ids": ["f000000"],
            "review": {
                "status": "confirmed",
                "reviewer": "synthetic-reviewer",
                "reviewed_at": "2026-10-18T00:00:00Z",
            },
        }
    ]
    updated = TrackManifest.model_validate(raw)
    assert len(aliases(updated, 0)) == 1
    assert len(updated.view_observations) == 1
    assert updated.segments[1].review == m.segments[1].review
    assert len(reviewed_targets(updated, a)) == len(reviewed_targets(m, a))
