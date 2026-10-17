import base64
import io
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError

from forte.contracts import DoneJob, EvidenceFrame, WindowObservation


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (32, 24), "blue").save(out, "JPEG")
    return base64.b64encode(out.getvalue()).decode()


def test_verdict_requires_consistent_events_and_strict_keys():
    with pytest.raises(ValidationError):
        DoneJob(job_id=uuid4(), verdict="violation", violations=[])
    with pytest.raises(ValidationError):
        DoneJob(job_id=uuid4(), verdict="unclear", violations=[])
    with pytest.raises(ValidationError):
        DoneJob(job_id=uuid4(), verdict="no_violation", violations=[], confidence=0.9)
    assert DoneJob(job_id=uuid4(), verdict="no_violation", violations=[]).status == "done"


def test_evidence_must_be_a_finite_timestamp_and_actual_jpeg():
    for t in [float("nan"), float("inf"), -1]:
        with pytest.raises(ValidationError):
            EvidenceFrame(timestamp_sec=t, image_base64=jpeg())
    for value in ["not-base64", base64.b64encode(b"not a JPEG").decode()]:
        with pytest.raises(ValidationError):
            EvidenceFrame(timestamp_sec=0, image_base64=value)
    assert EvidenceFrame(timestamp_sec=0.125, image_base64=jpeg()).timestamp_sec == 0.125


def test_model_cannot_reference_unsupplied_frames_or_rules():
    observation = {
        "complete": True,
        "events": [
            {
                "rule_id": "unknown",
                "start_id": "f0",
                "end_id": "f1",
                "decisive_id": "f1",
                "evidence_ids": ["f1"],
                "visible_facts": "A visible action.",
                "preconditions": ["ongoing_service"],
            }
        ],
    }
    with pytest.raises(ValidationError):
        WindowObservation.model_validate(
            observation,
            context={
                "frame_ids": {"f0", "f1"},
                "rule_ids": {"service_departure"},
            },
        )
    observation["events"][0]["rule_id"] = "service_departure"
    observation["events"][0]["decisive_id"] = "invented"
    with pytest.raises(ValidationError):
        WindowObservation.model_validate(
            observation,
            context={
                "frame_ids": {"f0", "f1"},
                "rule_ids": {"service_departure"},
            },
        )
