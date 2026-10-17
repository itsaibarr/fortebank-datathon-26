"""CVAT Community video XML exchange and explicit append-only human corrections."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from forte.annotations import VisualFact
from forte.tracking import (
    Box,
    Correction,
    Join,
    Review,
    RoleBinding,
    Segment,
    TrackManifest,
    ViewObservation,
    ViewRelation,
    WorkArea,
    validate_pair,
)


def export_cvat(manifest, xml_path, sidecar_path):
    from forte.person_proposals import write_json

    m = TrackManifest.model_validate(manifest.model_dump())
    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    task = ET.SubElement(ET.SubElement(root, "meta"), "task")
    for key, value in dict(
        name=f"{m.clip_id}-{m.source_sha256[:12]}",
        size=len(m.frames),
        mode="interpolation",
        overlap=0,
        start_frame=0,
        stop_frame=len(m.frames) - 1,
        flipped=False,
    ).items():
        ET.SubElement(task, key).text = str(value)
    size = ET.SubElement(task, "original_size")
    ET.SubElement(size, "width").text = str(m.oriented_width)
    ET.SubElement(size, "height").text = str(m.oriented_height)
    labels = ET.SubElement(task, "labels")
    label = ET.SubElement(labels, "label")
    ET.SubElement(label, "name").text = "person"
    ET.SubElement(label, "type").text = "rectangle"
    attributes = ET.SubElement(label, "attributes")
    for name, mutable, kind, values in [
        ("segment_id", False, "text", ""),
        ("person_id", False, "text", ""),
        ("role", True, "select", "unclear\ncashier\ncustomer"),
    ]:
        attr = ET.SubElement(attributes, "attribute")
        for key, value in dict(
            name=name,
            mutable=str(mutable).lower(),
            input_type=kind,
            default_value="unclear" if name == "role" else "",
            values=values,
        ).items():
            ET.SubElement(attr, key).text = value
    area_label = ET.SubElement(labels, "label")
    ET.SubElement(area_label, "name").text = "work_area"
    ET.SubElement(area_label, "type").text = "polygon"
    area_attrs = ET.SubElement(area_label, "attributes")
    for name, kind, default in [
        ("area_id", "text", ""),
        ("boundary_uncertain", "checkbox", "true"),
    ]:
        attr = ET.SubElement(area_attrs, "attribute")
        for key, value in dict(
            name=name, mutable="false", input_type=kind, default_value=default, values=""
        ).items():
            ET.SubElement(attr, key).text = value
    for i, segment in enumerate(m.segments):
        track = ET.SubElement(root, "track", id=str(i), label="person", source="auto")
        boxes = list(segment.boxes)
        last = boxes[-1]
        next_ordinal = int(last.frame_id[1:]) + 1
        if not last.outside and next_ordinal < len(m.frames):
            boxes.append(
                last.model_copy(
                    update=dict(
                        frame_id=m.frames[next_ordinal].frame_id,
                        outside=True,
                        origin="interpolation",
                    )
                )
            )
        for b in boxes:
            box = ET.SubElement(
                track,
                "box",
                frame=str(int(b.frame_id[1:])),
                xtl=str(b.xyxy[0] * m.oriented_width),
                ytl=str(b.xyxy[1] * m.oriented_height),
                xbr=str(b.xyxy[2] * m.oriented_width),
                ybr=str(b.xyxy[3] * m.oriented_height),
                outside=str(int(b.outside)),
                occluded=str(int(b.occluded)),
                keyframe=str(int(b.keyframe)),
                z_order="0",
            )
            for name, value in [
                ("segment_id", segment.id),
                ("person_id", segment.person_id),
                ("role", b.role_attribute),
            ]:
                ET.SubElement(box, "attribute", name=name).text = value
    for i, area in enumerate(m.work_areas, start=len(m.segments)):
        track = ET.SubElement(root, "track", id=str(i), label="work_area", source="manual")
        indices = sorted(int(id[1:]) for id in area.frame_ids)
        for ordinal in indices + ([indices[-1] + 1] if indices[-1] + 1 < len(m.frames) else []):
            polygon = ET.SubElement(
                track,
                "polygon",
                frame=str(ordinal),
                points=";".join(
                    f"{x * m.oriented_width},{y * m.oriented_height}" for x, y in area.points
                ),
                outside=str(int(ordinal not in indices)),
                occluded="0",
                keyframe="1",
                z_order="0",
            )
            ET.SubElement(polygon, "attribute", name="area_id").text = area.id
            ET.SubElement(polygon, "attribute", name="boundary_uncertain").text = str(
                area.boundary_uncertain
            ).lower()
    ET.indent(root)
    Path(xml_path).write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    write_json(
        sidecar_path,
        dict(
            schema_version=1,
            source_sha256=m.source_sha256,
            clip_id=m.clip_id,
            task_name=f"{m.clip_id}-{m.source_sha256[:12]}",
            width=m.oriented_width,
            height=m.oriented_height,
            time_base=m.time_base,
            frames=[f.model_dump() for f in m.frames],
            tracks={
                str(i): dict(segment_id=s.id, person_id=s.person_id)
                for i, s in enumerate(m.segments)
            },
            coordinate_convention=m.coordinate_convention,
            import_policy="Imported boxes/attributes are drafts; semantic facts remain separate",
        ),
    )


def import_cvat(manifest, xml_path, sidecar_path):
    m = TrackManifest.model_validate(manifest.model_dump())
    sidecar = json.loads(Path(sidecar_path).read_bytes())
    if (
        sidecar["source_sha256"] != m.source_sha256
        or sidecar["time_base"] != m.time_base
        or sidecar["coordinate_convention"] != m.coordinate_convention
        or sidecar["frames"] != [f.model_dump() for f in m.frames]
        or (sidecar["width"], sidecar["height"]) != (m.oriented_width, m.oriented_height)
    ):
        raise ValueError("CVAT source sidecar mismatch")
    raw = Path(xml_path).read_bytes()
    if len(raw) > 100_000_000 or b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("Unsupported CVAT XML")
    root = ET.fromstring(raw)
    if root.findtext("meta/task/name") != sidecar["task_name"] or int(
        root.findtext("meta/task/size", "-1")
    ) != len(m.frames):
        raise ValueError("CVAT task source mismatch")
    if (
        int(root.findtext("meta/task/original_size/width", "-1")),
        int(root.findtext("meta/task/original_size/height", "-1")),
    ) != (m.oriented_width, m.oriented_height):
        raise ValueError("CVAT frame dimensions mismatch")
    segments, areas = [], []
    original = {s.id: s for s in m.segments}
    next_number = max([int(s.id[1:]) for s in m.segments] + [0]) + 1
    for track in root.findall("track"):
        if track.attrib["label"] == "work_area":
            for item in track.findall("polygon"):
                ordinal = int(item.attrib["frame"])
                if not 0 <= ordinal < len(m.frames):
                    raise ValueError("CVAT area outside source")
                if item.get("outside", "0") == "1":
                    continue
                attrs = {a.attrib["name"]: a.text or "" for a in item.findall("attribute")}
                points = [
                    (
                        float(pair.split(",")[0]) / m.oriented_width,
                        float(pair.split(",")[1]) / m.oriented_height,
                    )
                    for pair in item.attrib["points"].split(";")
                ]
                id = attrs.get("area_id") or "area-" + track.attrib["id"]
                previous = next((a for a in areas if a.id == id), None)
                frame_id = m.frames[ordinal].frame_id
                if previous and previous.points == points:
                    previous.frame_ids.append(frame_id)
                else:
                    # A moving outline is a distinct source-bound outline,
                    # never silently projected across a camera movement.
                    if previous:
                        id += "-" + frame_id
                    areas.append(
                        WorkArea(
                            id=id,
                            frame_ids=[frame_id],
                            points=points,
                            boundary_uncertain=attrs.get("boundary_uncertain", "true") != "false",
                            review=Review(),
                            notes="CVAT import; outline/extent require local review",
                        )
                    )
            continue
        if track.attrib["label"] != "person":
            raise ValueError("Unexpected CVAT track label")
        boxes = []
        segment_ids, person_ids = set(), set()
        for item in track.findall("box"):
            ordinal = int(item.attrib["frame"])
            if not 0 <= ordinal < len(m.frames):
                raise ValueError("CVAT box outside source")
            attrs = {a.attrib["name"]: a.text or "" for a in item.findall("attribute")}
            if attrs.get("segment_id"):
                segment_ids.add(attrs["segment_id"])
            if attrs.get("person_id"):
                person_ids.add(attrs["person_id"])
            flags = [
                item.get(k, "1" if k == "keyframe" else "0")
                for k in ["outside", "occluded", "keyframe"]
            ]
            if any(f not in {"0", "1"} for f in flags):
                raise ValueError("Invalid CVAT box flags")
            coords = [
                float(item.attrib[k]) / scale
                for k, scale in zip(
                    ["xtl", "ytl", "xbr", "ybr"],
                    [m.oriented_width, m.oriented_height] * 2,
                    strict=True,
                )
            ]
            boxes.append(
                Box(
                    frame_id=m.frames[ordinal].frame_id,
                    xyxy=coords,
                    origin="cvat_import",
                    outside=flags[0] == "1",
                    occluded=flags[1] == "1",
                    keyframe=flags[2] == "1",
                    role_attribute=attrs.get("role", "unclear"),
                )
            )
        if len(segment_ids) > 1 or len(person_ids) > 1 or not boxes:
            raise ValueError("CVAT identity changed within a segment; split it explicitly")
        id = next(iter(segment_ids), None)
        if id is not None:
            if id not in original or person_ids != {original[id].person_id}:
                raise ValueError("CVAT immutable identity/source mapping changed")
            old = original[id]
            segment = old.model_copy(deep=True, update=dict(boxes=boxes, review=Review()))
        else:
            segment = Segment(
                id=f"s{next_number:05d}",
                person_id=f"p{next_number:05d}",
                upstream_id=-next_number,
                boxes=boxes,
                identity_uncertain=True,
            )
            next_number += 1
        segments.append(segment)
    # Original manifest/review history is retained by the caller in a new revision.
    m.segments = segments
    m.work_areas = areas
    live = {s.id for s in segments}
    m.joins = [j for j in m.joins if {j.from_segment, j.to_segment} <= live]
    m.training_eligible = False
    m.exclusion_reasons = sorted(set(m.exclusion_reasons) | {"cvat_edits_unreviewed"})
    return TrackManifest.model_validate(m.model_dump())


def apply_corrections(
    manifest, annotation, operations, *, reviewer, reason, artifact="review.json"
):
    """Explicit human-only changes, copied rather than mutating proposals/history."""
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Actual reviewer and correction reason required")
    m, a = validate_pair(manifest, annotation)
    before = hashlib.sha256(m.model_dump_json().encode()).hexdigest()
    at = datetime.now(UTC)
    reviewed = Review(status="confirmed", reviewer=reviewer, reviewed_at=at, notes=reason)
    for op in operations:
        kind = op["operation"]
        affected = []
        if kind == "split":
            segment = next(s for s in m.segments if s.id == op["segment_id"])
            cut = int(op["frame_id"][1:])
            left = [b for b in segment.boxes if int(b.frame_id[1:]) < cut]
            right = [b for b in segment.boxes if int(b.frame_id[1:]) >= cut]
            if not left or not right:
                raise ValueError("Split requires boxes on both sides")
            number = max(int(s.id[1:]) for s in m.segments) + 1
            new = Segment(
                id=f"s{number:05d}",
                person_id=f"p{number:05d}",
                upstream_id=segment.upstream_id,
                boxes=right,
                review=Review(),
            )
            segment.boxes = left
            segment.review = Review()
            m.segments.append(new)
            # Existing facts are never automatically transferred to the new person.
            affected = [segment.id, new.id]
        elif kind == "join":
            endpoints = [op["from_segment"], op["to_segment"]]
            m.joins.append(
                Join(
                    id=f"jh{len(m.joins) + 1:05d}",
                    from_segment=endpoints[0],
                    to_segment=endpoints[1],
                    reason=reason,
                    origin="human",
                    review=reviewed,
                )
            )
            # Supersede the same proposed hypothesis, retaining it as rejected history.
            for j in m.joins[:-1]:
                if [j.from_segment, j.to_segment] == endpoints and j.review.status == "draft":
                    j.review = reviewed.model_copy(update=dict(status="rejected"))
            affected = endpoints
        elif kind == "box":
            segment = next(s for s in m.segments if s.id == op["segment_id"])
            replacement = Box.model_validate(op["box"])
            replacement.origin = "human"
            replacement.review = reviewed
            segment.boxes = sorted(
                [b for b in segment.boxes if b.frame_id != replacement.frame_id] + [replacement],
                key=lambda b: int(b.frame_id[1:]),
            )
            segment.review = Review()
            affected = [segment.id, replacement.frame_id]
        elif kind == "box_review":
            segment = next(s for s in m.segments if s.id == op["segment_id"])
            frame_ids = op["frame_ids"]
            if (
                not isinstance(frame_ids, list)
                or not frame_ids
                or len(set(frame_ids)) != len(frame_ids)
                or not set(frame_ids) <= {b.frame_id for b in segment.boxes}
            ):
                raise ValueError("Box review requires unique, existing source box frames")
            for box in segment.boxes:
                if box.frame_id in frame_ids:
                    box.review = reviewed.model_copy(update=dict(status=op["status"]))
            # Acceptance preserves detector/interpolation origin and scores.
            # It never approves the identity segment or any other source box.
            affected = [segment.id, *frame_ids]
        elif kind == "review":
            segment = next(s for s in m.segments if s.id == op["segment_id"])
            status = op.get("status", "confirmed")
            segment.review = reviewed.model_copy(update=dict(status=status))
            if op.get("resolve_identity", False):
                if status != "confirmed":
                    raise ValueError("Resolving identity requires explicit confirmation")
                segment.identity_uncertain = False
            # Geometry approval is a separate explicit operation, never implied
            # by accepting identity or a role.
            if op.get("approve_boxes", False):
                for b in segment.boxes:
                    b.review = reviewed.model_copy(update=dict(status=status))
            affected = [segment.id]
        elif kind == "area":
            area = WorkArea.model_validate(op["area"])
            area.review = reviewed
            m.work_areas = [x for x in m.work_areas if x.id != area.id] + [area]
            affected = [area.id]
        elif kind == "role_binding":
            binding = RoleBinding.model_validate(op["binding"])
            binding.review = reviewed
            m.schema_version = 2
            m.role_bindings = [b for b in m.role_bindings if b.id != binding.id] + [binding]
            affected = [binding.id, binding.segment_id]
        elif kind == "view_relation":
            relation = ViewRelation.model_validate(op["relation"])
            relation.review = reviewed
            m.schema_version = 2
            m.view_relations = [v for v in m.view_relations if v.id != relation.id] + [relation]
            affected = [relation.id, relation.direct_segment_id, relation.reflected_segment_id]
        elif kind == "view_observation":
            observation = ViewObservation.model_validate(op["observation"])
            observation.review = reviewed
            m.schema_version = 2
            m.view_observations = [v for v in m.view_observations if v.id != observation.id] + [
                observation
            ]
            affected = [observation.id, observation.segment_id]
        elif kind == "fact":
            f = VisualFact.model_validate(op["fact"])
            f.reviewer, f.reviewed_at, f.origin = reviewer, at, "human"
            # Human chooses confirmed/rejected/draft explicitly in the operation.
            if "review_status" not in op["fact"]:
                raise ValueError("Fact correction requires explicit review status")
            a.facts = [x for x in a.facts if x.id != f.id] + [f]
            affected = [f.id]
        else:
            raise ValueError("Unsupported correction operation")
        m.corrections.append(
            Correction(
                operation=kind,
                reviewer=reviewer,
                reviewed_at=at,
                before_sha256=before,
                affected_ids=affected,
                reason=reason,
                artifact=artifact,
            )
        )
    m.training_eligible = False
    return validate_pair(m, a)
