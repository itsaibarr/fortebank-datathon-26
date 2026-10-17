import json

import pytest

from forte_visual.inputs import (
    Answer,
    InputCase,
    aliases,
    crop_rect,
    export,
    messages,
    validate_answer,
)
from forte_visual.io import read
from forte_visual.release import verify
from forte_visual.synthetic import create


def test_export_separates_references_and_preserves_shapes_and_transforms(tmp_path):
    source = create(tmp_path / "source")
    assert export(source, tmp_path / "run") == 6
    raw = read(tmp_path / "run/inference/inputs.json")
    references = read(tmp_path / "run/reference/answers.json")
    assert not (tmp_path / "run/inference/reference").exists()
    for row in raw["cases"]:
        case = InputCase.model_validate(row)
        assert len(case.views) == (12 if case.task == "role" else 16)
        assert len(case.frames) == len(case.views) // 2
        prompt = json.dumps(messages(case, tmp_path / "run/inference"))
        assert "synthetic-reviewer" not in prompt
        assert "expected" not in row and "value" not in row
        validate_answer(case, Answer.model_validate(references["cases"][case.case_id]["answer"]))
        for view in case.views:
            sx, sy, tx, ty = view.source_to_view
            assert view.source_rect[0] * sx + tx == pytest.approx(0)
            assert view.source_rect[1] * sy + ty == pytest.approx(0)
    assert crop_rect([[0.2, 0.2, 0.4, 0.8], [0.6, 0.1, 0.9, 0.9]], 100, 100) == (9, 0, 100, 100)


def test_id_permutation_changes_names_and_order_without_role_metadata(tmp_path):
    source = create(tmp_path / "source")
    m = verify(source)[1][0][1]
    first, second = aliases(m, 1), aliases(m, 2)
    assert set(first) != set(second)
    assert sorted(first.values()) == sorted(second.values())
    # Same person_id is insufficient to merge segments across an unverified gap.
    m.segments[1].person_id = m.segments[0].person_id
    assert len(aliases(m, 1)) == 2


def test_answer_actor_participant_and_source_invariants(tmp_path):
    source = create(tmp_path / "source")
    export(source, tmp_path / "run")
    case = InputCase.model_validate(read(tmp_path / "run/inference/inputs.json")["cases"][1])
    answer = Answer.model_validate(
        read(tmp_path / "run/reference/answers.json")["cases"][case.case_id]["answer"]
    )
    for updates in [
        {"actor_id": "wrong"},
        {"other_actor_id": case.actor_id},
        {"end_frame_id": "invented"},
        {"start_frame_id": answer.end_frame_id, "end_frame_id": answer.start_frame_id},
    ]:
        with pytest.raises(ValueError):
            validate_answer(case, answer.model_copy(update=updates))
    changed = case.model_dump()
    changed["expected_role"] = "cashier"
    with pytest.raises(ValueError):
        InputCase.model_validate(changed)
