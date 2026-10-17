import json
import xml.etree.ElementTree as ET

import pytest
from test_tracking import pair

from forte.track_review import apply_corrections, export_cvat, import_cvat
from forte.tracking import TrackManifest


def test_cvat_round_trip_preserves_outside_occlusion_keyframes_and_mutable_roles(tmp_path):
    raw, _ = pair()
    raw["segments"][0]["boxes"][0].update(occluded=True, keyframe=False, role_attribute="cashier")
    raw["segments"][0]["boxes"][1].update(outside=True, role_attribute="customer")
    m = TrackManifest.model_validate(raw)
    xml, sidecar = tmp_path / "a.xml", tmp_path / "map.json"
    export_cvat(m, xml, sidecar)
    restored = import_cvat(m, xml, sidecar)
    before = m.segments[0].boxes
    after = restored.segments[0].boxes
    assert [(b.xyxy, b.outside, b.occluded, b.keyframe, b.role_attribute) for b in before] == [
        (b.xyxy, b.outside, b.occluded, b.keyframe, b.role_attribute) for b in after
    ]
    assert all(b.review.status == "draft" and b.origin == "cvat_import" for b in after)
    assert not restored.training_eligible
    # A CVAT frame ordinal alone cannot substitute for the PTS/hash sidecar.
    data = json.loads(sidecar.read_text())
    data["source_sha256"] = "f" * 64
    sidecar.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="source"):
        import_cvat(m, xml, sidecar)


def test_cvat_new_tracks_and_changed_ids_do_not_reuse_a_verified_identity(tmp_path):
    raw, _ = pair()
    m = TrackManifest.model_validate(raw)
    xml, sidecar = tmp_path / "a.xml", tmp_path / "map.json"
    export_cvat(m, xml, sidecar)
    root = ET.parse(xml)
    track = root.find("track")
    track.set("id", "100")
    new = ET.SubElement(root.getroot(), "track", id="101", label="person", source="manual")
    ET.SubElement(
        new,
        "box",
        frame="0",
        xtl="50",
        ytl="5",
        xbr="80",
        ybr="45",
        outside="0",
        occluded="0",
        keyframe="1",
    )
    root.write(xml)
    r = import_cvat(m, xml, sidecar)
    assert len(r.segments) == 2
    assert r.segments[1].person_id != m.segments[0].person_id


def test_human_split_join_and_review_are_append_only_and_need_actual_reviewer():
    raw, a = pair()
    m = TrackManifest.model_validate(raw)
    with pytest.raises(ValueError):
        apply_corrections(
            m,
            a,
            [{"operation": "split", "segment_id": "s0001", "frame_id": "f000001"}],
            reviewer="",
            reason="synthetic",
        )
    revised, ann = apply_corrections(
        m,
        a,
        [{"operation": "split", "segment_id": "s0001", "frame_id": "f000001"}],
        reviewer="synthetic reviewer",
        reason="synthetic ID switch",
    )
    assert len(m.segments) == 1 and len(m.segments[0].boxes) == 2
    assert len(revised.segments) == 2 and len(revised.corrections) == 1
    assert revised.segments[0].person_id != revised.segments[1].person_id
    joined, _ = apply_corrections(
        revised,
        ann,
        [{"operation": "join", "from_segment": "s0001", "to_segment": revised.segments[1].id}],
        reviewer="synthetic reviewer",
        reason="synthetic continuity",
    )
    assert len(joined.corrections) == 2
    assert joined.joins[-1].review.status == "confirmed"


def test_import_rejects_sidecar_from_different_track_mapping_even_with_same_frame_count(tmp_path):
    raw, _ = pair()
    m = TrackManifest.model_validate(raw)
    xml, sidecar = tmp_path / "a.xml", tmp_path / "map.json"
    export_cvat(m, xml, sidecar)
    # A source hash alone is insufficient when a derivative uses another PTS origin.
    data = json.loads(sidecar.read_text())
    data["time_base"] = "1/100"
    sidecar.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="source"):
        import_cvat(m, xml, sidecar)


def test_cvat_work_area_polygons_are_source_bound_and_import_as_unreviewed(tmp_path):
    from forte.tracking import WorkArea

    raw, _ = pair()
    m = TrackManifest.model_validate(raw)
    m.work_areas = [
        WorkArea(
            id="area1",
            frame_ids=["f000000"],
            points=[(0.1, 0.1), (0.8, 0.1), (0.8, 0.9)],
            boundary_uncertain=True,
        )
    ]
    xml, sidecar = tmp_path / "a.xml", tmp_path / "map.json"
    export_cvat(m, xml, sidecar)
    restored = import_cvat(m, xml, sidecar)
    assert len(restored.work_areas) == 1
    assert restored.work_areas[0].points == m.work_areas[0].points
    assert restored.work_areas[0].frame_ids == ["f000000"]
    assert restored.work_areas[0].review.status == "draft"
    assert ET.parse(xml).find("track[@label='work_area']/polygon") is not None


def reflection_fixture():
    raw, annotation = pair()
    for number in range(2, 5):
        raw["segments"].append(
            dict(
                id=f"s{number:04d}",
                person_id=f"p{number:04d}",
                upstream_id=number,
                boxes=[
                    dict(frame_id="f000000", xyxy=[0.5, 0.1, 0.8, 0.9]),
                    dict(frame_id="f000001", xyxy=[0.5, 0.1, 0.8, 0.9]),
                ],
            )
        )
    mappings = []
    for i, role, canonical, kind in [
        (1, "cashier", 1, "direct"),
        (2, "customer", 2, "direct"),
        (3, "cashier", 1, "reflection"),
        (4, "customer", 2, "reflection"),
    ]:
        mappings.append(
            dict(
                operation="role_binding",
                binding=dict(
                    id=f"rb{i}",
                    segment_id=f"s{i:04d}",
                    canonical_person_id=f"p{canonical:04d}",
                    role=role,
                    view_kind=kind,
                    candidate_frame_ids=["f000000", "f000001"],
                    reviewed_frame_ids=["f000000"],
                    review_scope="anchor_mapping_only",
                ),
            )
        )
    for primary, mirror in [(1, 3), (2, 4)]:
        mappings.append(
            dict(
                operation="view_relation",
                relation=dict(
                    id=f"vr{primary}",
                    direct_segment_id=f"s{primary:04d}",
                    reflected_segment_id=f"s{mirror:04d}",
                    canonical_person_id=f"p{primary:04d}",
                ),
            )
        )
    return TrackManifest.model_validate(raw), annotation, mappings


def test_reviewed_reflections_are_same_entity_views_not_temporal_joins_or_training_truth():
    from forte.tracking import training_targets

    m, a, operations = reflection_fixture()
    revised, annotation = apply_corrections(
        m,
        a,
        operations,
        reviewer="synthetic human",
        reason="Synthetic view/role mapping; intervals and geometry unreviewed",
    )
    assert m.schema_version == 1 and len(m.segments) == 4
    assert revised.schema_version == 2
    assert len(revised.role_bindings) == 4 and len(revised.view_relations) == 2
    assert len({b.canonical_person_id for b in revised.role_bindings}) == 2
    assert all(b.review.status == "confirmed" for b in revised.role_bindings)
    assert revised.joins == []
    assert all(s.review.status == "draft" for s in revised.segments)
    assert all(b.review.status == "draft" for s in revised.segments for b in s.boxes)
    assert annotation.facts == [] and training_targets(revised, annotation) == []
    assert not revised.training_eligible


def test_reflection_mapping_rejects_missing_sources_and_conflicting_roles():
    import copy

    m, a, operations = reflection_fixture()
    bad = copy.deepcopy(operations)
    bad[2]["binding"]["role"] = "customer"
    with pytest.raises(ValueError, match="role"):
        apply_corrections(m, a, bad, reviewer="synthetic human", reason="synthetic")
    bad = copy.deepcopy(operations)
    bad[0]["binding"]["reviewed_frame_ids"] = ["f999999"]
    with pytest.raises(ValueError, match="frame"):
        apply_corrections(m, a, bad, reviewer="synthetic human", reason="synthetic")
    bad = copy.deepcopy(operations)
    bad[-1]["relation"]["reflected_segment_id"] = "missing"
    with pytest.raises(ValueError, match="segment"):
        apply_corrections(m, a, bad, reviewer="synthetic human", reason="synthetic")


def test_reflection_review_counts_mapped_entities_without_claiming_reviewed_tracks():
    from forte.tracking_cli import aggregate

    m, a, operations = reflection_fixture()
    m, a = apply_corrections(
        m, a, operations, reviewer="synthetic human", reason="synthetic mapping"
    )
    report = aggregate([({"clip_id": "clip000"}, m)], annotations=[a])
    assert report["confirmed_role_mappings"] == 4
    assert report["physical_people_with_role_mapping"] == 2
    assert report["confirmed_reflection_relations"] == 2
    assert report["human_reviewed_segments"] == 0
    assert report["confirmed_roles"] == 0 and report["training_targets"] == 0


def test_later_conflicting_role_fact_cannot_override_the_reviewed_mapping():
    from forte.annotations import VisualFact
    from forte.tracking import validate_pair

    m, a, operations = reflection_fixture()
    m, a = apply_corrections(
        m, a, operations, reviewer="synthetic human", reason="synthetic mapping"
    )
    a.facts = [
        VisualFact(
            id="conflict",
            kind="role",
            actor_id="p0001",
            value="customer",
            start_sec=0,
            end_sec=1,
            frame_ids=["f000000", "f000001"],
            continuity_supported=True,
            segment_ids=["s0001"],
        )
    ]
    with pytest.raises(ValueError, match="human role mapping"):
        validate_pair(m, a)
