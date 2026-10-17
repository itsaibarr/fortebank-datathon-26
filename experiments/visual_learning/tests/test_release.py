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
