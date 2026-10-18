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
