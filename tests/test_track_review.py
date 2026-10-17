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
