"""Strict public jury schemas and model-independent observation boundaries."""

import base64
import binascii
import io
from typing import Annotated, Literal, Self
from uuid import UUID

from PIL import Image
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    ValidationInfo,
    field_validator,
    model_validator,
)

Seconds = Annotated[FiniteFloat, Field(ge=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ErrorDetail(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field: str | None = None


class AcceptedJob(StrictModel):
    job_id: UUID


class ProcessingJob(AcceptedJob):
    status: Literal["processing"] = "processing"


class EvidenceFrame(StrictModel):
    timestamp_sec: Seconds
    image_base64: str = Field(min_length=16, max_length=12_000_000)

    @field_validator("image_base64")
    @classmethod
    def actual_jpeg(cls, value: str) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != "JPEG" or image.width * image.height > 8_400_000:
                    raise ValueError("Evidence must be a bounded JPEG")
                image.verify()
        except (ValueError, binascii.Error, OSError) as exc:
            raise ValueError("Evidence must decode as JPEG") from exc
        return value


class Violation(StrictModel):
    type: str = Field(min_length=1, max_length=160)
    timecode_sec: Seconds
    description: str = Field(min_length=1, max_length=2400)
    evidence_frames: list[EvidenceFrame] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def ordered_evidence(self) -> Self:
        times = [f.timestamp_sec for f in self.evidence_frames]
        if times != sorted(set(times)):
            raise ValueError("Evidence must have distinct ordered source times")
        return self


class DoneJob(AcceptedJob):
    status: Literal["done"] = "done"
    verdict: Literal["no_violation", "violation"]
    violations: list[Violation]

    @model_validator(mode="after")
    def consistent_verdict(self) -> Self:
        if (self.verdict == "violation") != bool(self.violations):
            raise ValueError("Verdict and events disagree")
        return self


class FailedJob(AcceptedJob):
    status: Literal["failed"] = "failed"
    error: ErrorDetail


class EventObservation(StrictModel):
    rule_id: str = Field(min_length=1, max_length=80)
    start_id: str
    end_id: str
    decisive_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=3)
    visible_facts: str = Field(min_length=1, max_length=500)
    preconditions: list[str] = Field(max_length=12)


class WindowObservation(StrictModel):
    complete: bool
    events: list[EventObservation] = Field(max_length=12)

    @model_validator(mode="after")
    def supplied_references(self, info: ValidationInfo) -> Self:
        if info.context:
            for event in self.events:
                ids = {event.start_id, event.end_id, event.decisive_id, *event.evidence_ids}
                if not ids <= info.context["frame_ids"]:
                    raise ValueError("Model referenced an unsupplied frame")
                if event.rule_id not in info.context["rule_ids"]:
                    raise ValueError("Model referenced an unapproved rule")
        return self


class ActorGrounding(StrictModel):
    role: Literal["cashier", "customer", "unclear"]
    role_evidence_ids: list[str] = Field(max_length=3)
    continuity_supported: bool

    def departure_verdict(
        self, frame_times: dict[str, float], decisive_id: str
    ) -> Literal["supported", "unsupported", "unclear"]:
        ids = set(self.role_evidence_ids)
        if (
            self.role == "unclear"
            or not self.continuity_supported
            or not ids
            or not ids <= frame_times.keys()
            or decisive_id not in frame_times
            or not any(frame_times[id] < frame_times[decisive_id] for id in ids)
        ):
            return "unclear"
        return "supported" if self.role == "cashier" else "unsupported"


class EvidenceCheck(StrictModel):
    verdict: Literal["supported", "unsupported", "unclear"]
    evidence_ids: list[str] = Field(max_length=3)
    preconditions: list[str] = Field(max_length=12)
    actor: ActorGrounding | None = None
