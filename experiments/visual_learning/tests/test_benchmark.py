import pytest

from forte_visual.benchmark import (
    MockExecutor,
    Result,
    maximum_matches,
    run_model,
    score,
    select,
    tiou,
)
from forte_visual.inputs import export
from forte_visual.io import read
from forte_visual.synthetic import create


def test_abstentions_and_failures_remain_denominators_and_pairs_do_not_select_mock(tmp_path):
    source = create(tmp_path / "release")
    export(source, tmp_path / "run")
    inputs = tmp_path / "run/inference/inputs.json"
    refs = tmp_path / "run/reference/answers.json"
    for model in ("8b", "27b"):
        run_model(inputs, tmp_path / (model + ".json"), model, MockExecutor())
    a = score(inputs, refs, tmp_path / "8b.json")
    b = score(inputs, refs, tmp_path / "27b.json")
    assert a["aggregate"]["cases"] == 6 and a["aggregate"]["abstained"] == 6
    assert a["aggregate"]["0.5"]["fn"] == 2
    assert a["aggregate"]["answer_coverage"] == 0
    assert a["aggregate"]["role_precision"] is None
    assert len(a["groups"]) == 2
    assert select(a, b, synthetic=True) == "inconclusive"

    def broken(case, root):
        raise RuntimeError("mock failure")

    run_model(inputs, tmp_path / "failed.json", "8b", broken)
    c = score(inputs, refs, tmp_path / "failed.json")
    assert c["aggregate"]["failed"] == 6 and c["aggregate"]["0.5"]["fn"] == 2


def test_actor_recipient_correct_events_and_temporal_matching(tmp_path):
    source = create(tmp_path / "release")
    export(source, tmp_path / "run")
    inputs, references = (
        tmp_path / "run/inference/inputs.json",
        tmp_path / "run/reference/answers.json",
    )
    refs = read(references)["cases"]

    def oracle(case, root):
        return Result(refs[case.case_id]["answer"], 100, 100)

    run_model(inputs, tmp_path / "oracle.json", "8b", oracle)
    report = score(inputs, references, tmp_path / "oracle.json")
    assert report["aggregate"]["0.5"]["f1"] == 1
    assert report["aggregate"]["role_precision"] == 1
    assert report["aggregate"]["false_events_per_minute"] == 0
    assert tiou([0, 4], [2, 6]) == pytest.approx(1 / 3)
    pred = [{"relation": "actor1", "interval": [0, 4]}, {"relation": "actor2", "interval": [0, 4]}]
    ref = [{"relation": "actor1", "interval": [0, 4]}]
    assert maximum_matches(pred, ref, 0.5) == [(0, 0)]


def test_wrong_actor_and_recipient_assertions_are_not_hidden_as_abstention(tmp_path):
    source = create(tmp_path / "release")
    export(source, tmp_path / "run")
    inputs = tmp_path / "run/inference/inputs.json"
    refs = tmp_path / "run/reference/answers.json"
    expected = read(refs)["cases"]

    def substituted(case, root):
        answer = dict(expected[case.case_id]["answer"])
        if case.task == "action":
            answer["actor_id"], answer["other_actor_id"] = (
                answer["other_actor_id"],
                answer["actor_id"],
            )
        elif case.task == "role":
            answer["value"] = "customer"
        return Result(answer, 100, 100)

    run_model(inputs, tmp_path / "wrong.json", "8b", substituted)
    report = score(inputs, refs, tmp_path / "wrong.json")["aggregate"]
    assert report["wrong_actor"] == 2
    assert report["role_swaps"] == 2
    assert report["invalid_contract"] == 2
    assert report["0.5"]["fp"] == report["0.5"]["fn"] == 2
    assert report["answer_coverage"] == pytest.approx(4 / 6) and report["abstained"] == 2


def test_one_to_one_matching_uses_maximum_cardinality_not_greedy():
    from forte_visual.benchmark import maximum_edge_matching

    assert len(maximum_edge_matching([[0, 1], [0]])) == 2


def test_selection_preserves_27b_advantage_and_rejects_abstention_gain():
    import copy

    def report(swaps):
        return {
            "independent_groups": 3,
            "aggregate": {
                "cases": 9,
                "failed": 0,
                "invalid_sources": 0,
                "invalid_contract": 0,
                "answer_coverage": 1,
                "wrong_actor": 0,
                "role_swaps": swaps,
                "0.5": {"f1": 0.8},
                "false_events_per_minute": 0,
            },
            "groups": {
                str(i): {
                    "wrong_actor": 0,
                    "role_swaps": swaps // 3,
                    "role_coverage": 1,
                    "action_coverage": 1,
                    "0.5": {"f1": 0.8, "fp": 0},
                }
                for i in range(3)
            },
        }

    eight, larger = report(3), report(0)
    assert select(eight, larger) == "27b"
    assert select(larger, larger) == "inconclusive"
    abstaining = copy.deepcopy(larger)
    abstaining["groups"]["0"]["role_coverage"] = 0
    assert select(eight, abstaining) == "inconclusive"
