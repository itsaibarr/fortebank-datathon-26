import copy

import pytest

from forte.manifest import (
    assert_development_recording,
    development_allowlist,
    evaluate_events,
    freeze_manifest,
    prepare_manifest,
    record_group_review,
)


def selection():
    return {
        "schema_version": 1,
        "purpose": "synthetic",
        "split_status": "historically_frozen",
        "groups": [
            {
                "recording_id": c * 64,
                "canonical_file": f"opaque-original-{i}.MOV",
                "files": [f"opaque-original-{i}.MOV", f"opaque-copy-{i}.MOV"],
                "positive": i == 0,
                "label_points_sec": [57, 68] if i == 0 else [],
                "proxy_block": "opaque",
                "split": split,
                "strict_point_scoring_eligible": False,
                "requires_point_adjudication": i == 0,
                "neutral_file": f"clip{i:03d}.mov",
            }
            for i, (c, split) in enumerate([("a", "development"), ("b", "reserved")])
        ],
    }


def test_metadata_upgrade_preserves_coarse_conflicts_without_inventing_session_or_date():
    source = selection()
    original = copy.deepcopy(source)
    manifest = prepare_manifest(source)
    assert source == original
    assert manifest["records"][0]["original_selection"] == source["groups"][0]
    assert manifest["records"][0]["original_selection"]["label_points_sec"] == [57, 68]
    assert manifest["split_status"] == "provisional_pending_session_review"
    assert all(r["session_group"]["session_id"] is None for r in manifest["records"])
    assert all(r["recording_date"]["date"] is None for r in manifest["records"])
    assert all(not r["training_permitted"] for r in manifest["records"])
    with pytest.raises(ValueError, match="human review"):
        freeze_manifest(manifest, reviewer="synthetic", reviewed_at="2026-10-18", basis="synthetic")


def test_allowlist_omits_original_names_and_labels_rejects_reserved_and_wrong_hash():
    manifest = prepare_manifest(selection())
    assert development_allowlist(manifest) == [
        {
            "recording_id": "a" * 64,
            "neutral_file": "clip000.mov",
            "split": "development",
        }
    ]
    assert_development_recording(manifest, "a" * 64, "a" * 64)
    with pytest.raises(ValueError, match="Reserved"):
        assert_development_recording(manifest, "b" * 64, "b" * 64)
    with pytest.raises(ValueError, match="hash mismatch"):
        assert_development_recording(manifest, "a" * 64, "b" * 64)


def test_duplicate_split_leak_and_neutral_alias_collision_rejected():
    source = selection()
    source["groups"][1]["recording_id"] = "a" * 64
    with pytest.raises(ValueError, match="exactly one"):
        prepare_manifest(source)


def test_reserved_inventory_can_preserve_old_locked_holdout_without_media_alias():
    source = selection()
    source["groups"][1].pop("neutral_file")
    source["groups"][1]["split"] = "locked_holdout"
    manifest = prepare_manifest(source)
    reserved = manifest["records"][1]
    assert reserved["split"] == "reserved" and reserved["neutral_file"] is None
    assert reserved["original_selection"]["split"] == "locked_holdout"
    source = selection()
    source["groups"][1]["neutral_file"] = source["groups"][0]["neutral_file"]
    with pytest.raises(ValueError, match="neutral source name"):
        prepare_manifest(source)


def reviewed_manifest(same_session=False):
    manifest = prepare_manifest(selection())
    for i, c in enumerate("ab"):
        manifest = record_group_review(
            manifest,
            c * 64,
            session_id="same" if same_session else f"session{i}",
            reviewer="synthetic human fixture",
            reviewed_at="2026-10-18",
            basis="synthetic review",
        )
    return manifest


def test_freeze_requires_reviewed_session_no_leak_and_retains_lineage():
    with pytest.raises(ValueError, match="cannot cross"):
        freeze_manifest(
            reviewed_manifest(True), reviewer="fixture", reviewed_at="today", basis="fixture"
        )
    manifest = reviewed_manifest()
    frozen = freeze_manifest(manifest, reviewer="fixture", reviewed_at="today", basis="fixture")
    assert manifest["split_status"] != "frozen"
    assert frozen["split_status"] == "frozen"
    assert len(frozen["records"][0]["correction_lineage"]) == 1
    assert frozen["history"][-1]["prior_manifest_sha256"]
    with pytest.raises(ValueError, match="new explicit"):
        record_group_review(
            frozen,
            "a" * 64,
            session_id="changed",
            reviewer="fixture",
            reviewed_at="today",
            basis="fixture",
        )
    manifest["records"][1]["exposure_audit"].append({"purpose": "prompt_tuning"})
    with pytest.raises(ValueError, match="exposure"):
        freeze_manifest(manifest, reviewer="fixture", reviewed_at="today", basis="fixture")


def event(**changes):
    return {
        "event_type": "synthetic_action",
        "start_sec": 1.0,
        "end_sec": 2.0,
        "actor_id": "p1",
        "role": "customer",
        "provision_id": "public-clause",
        "provision_version": "snapshot-a",
        "review_status": "human_confirmed",
        **changes,
    }


def test_event_matching_is_one_to_one_and_requires_actor_role_version_and_interval():
    result = evaluate_events([event()], [event(), event()], complete_reviewed_population=True)
    assert result["true_positives"] == 1 and result["false_negatives"] == 1
    for replacement in [
        {"actor_id": "other"},
        {"role": "cashier"},
        {"provision_version": "wrong"},
        {"start_sec": 10, "end_sec": 11},
    ]:
        result = evaluate_events(
            [event(**replacement)], [event()], tolerance_sec=0.1, complete_reviewed_population=True
        )
        assert result["false_positives"] == result["false_negatives"] == 1
    duplicate = evaluate_events([event(), event()], [event()], complete_reviewed_population=True)
    assert duplicate["true_positives"] == duplicate["false_positives"] == 1


def test_unreviewed_targets_do_not_supply_quality_and_sparse_review_cannot_define_false_positives():
    result = evaluate_events([event()], [event(review_status="model_proposal")])
    assert result["unreviewed_targets_excluded"] == 1
    assert result["true_positives"] == result["reviewed_event_targets"] == 0
    assert result["false_positives"] is result["precision"] is result["recall"] is None


def test_abstention_is_visible_coverage_and_still_misses_confirmed_event():
    result = evaluate_events(
        [event(assessment="abstain")],
        [
            event(),
            event(target_kind="abstention"),
            event(start_sec=20, end_sec=21, target_kind="abstention"),
        ],
    )
    assert result["prediction_abstentions"] == result["false_negatives"] == 1
    assert result["event_targets_with_overlapping_abstention"] == 1
    assert (
        result["reviewed_abstention_targets_covered"]
        == result["reviewed_abstention_targets_missed"]
        == 1
    )


def test_maximum_cardinality_match_does_not_consume_unique_target_greedily():
    # First prediction can match either target; second can match only target 0.
    result = evaluate_events(
        [event(start_sec=1.5, end_sec=2.5), event(start_sec=0.5, end_sec=1.5)],
        [event(), event(start_sec=2, end_sec=3)],
        tolerance_sec=0.75,
    )
    assert result["true_positives"] == 2
