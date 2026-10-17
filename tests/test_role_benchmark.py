import hashlib
import json

import pytest

from forte.role_benchmark import RoleAnswer, load_inputs, validate_answer


def inputs(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"synthetic bytes; image decoding belongs to the processor")
    manifest = {
        "schema_version": 1,
        "cases": [
            {
                "case_id": "synthetic",
                "target_sec": 2.0,
                "frames": [
                    {
                        "frame_id": "f01",
                        "timestamp_sec": 1.0,
                        "path": image.name,
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    }
                ],
            }
        ],
    }
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


def test_private_benchmark_inputs_are_pinned_and_cannot_embed_expected_answers(tmp_path):
    path, manifest = inputs(tmp_path)
    assert load_inputs(path)[0].case_id == "synthetic"
    (tmp_path / "frame.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA256"):
        load_inputs(path)
    manifest["cases"][0]["expected_role"] = "customer"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_inputs(path)


def test_unprovided_evidence_and_unsupported_certain_roles_are_rejected(tmp_path):
    path, _ = inputs(tmp_path)
    case = load_inputs(path)[0]
    answer = RoleAnswer(
        actor_role="cashier",
        evidence_frame_ids=["invented"],
        continuity_supported=True,
        explanation="Synthetic",
    )
    with pytest.raises(ValueError, match="supplied"):
        validate_answer(case, answer)
    answer.evidence_frame_ids = []
    with pytest.raises(ValueError, match="evidence"):
        validate_answer(case, answer)
    answer.actor_role = "unclear"
    answer.continuity_supported = False
    validate_answer(case, answer)
