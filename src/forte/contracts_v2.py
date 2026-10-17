"""Versioned execution result. Assessment uncertainty never changes job success."""

import math
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReasoningDoneJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    status: Literal["done"] = "done"
    api_version: Literal[2] = 2
    result: dict[str, Any]

    @field_validator("result")
    @classmethod
    def source_bound_result(cls, value):
        if value.get("schema_version") != "forte.reasoning/1":
            raise ValueError("Unsupported reasoning result")
        digest = value.get("source_sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Missing source binding")
        if value.get("assessment") not in {
            "supported_violation",
            "no_violation_observed",
            "insufficient_evidence",
            "not_applicable",
        }:
            raise ValueError("Missing explicit assessment")
        revision = value.get("artifacts", {}).get("revision", "")
        if not re.fullmatch(r"reasoning-[a-f0-9]{32}", revision):
            raise ValueError("Invalid private artifact revision")
        source = value.get("source", {})
        duration = source.get("duration_sec")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
            or not 0 < duration <= 180
        ):
            raise ValueError("Invalid source duration")
        if source.get("frame_table") != "source-frames.json":
            raise ValueError("Invalid frame table reference")
        timeline_digest = value.get("timeline", {}).get("source_sha256", digest)
        if timeline_digest != digest:
            raise ValueError("Timeline belongs to another source")
        for event in value.get("events", []):
            for item in event.get("evidence", []):
                fid = item.get("frame_id", "")
                if (
                    not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", fid)
                    or item.get("file") != f"evidence/{fid}.jpg"
                ):
                    raise ValueError("Invalid source evidence path")
                stamp = item.get("timestamp_sec")
                if (
                    isinstance(stamp, bool)
                    or not isinstance(stamp, (int, float))
                    or not math.isfinite(stamp)
                    or not 0 <= stamp <= duration
                ):
                    raise ValueError("Invalid source evidence timestamp")
                if item.get("source_sha256") != digest:
                    raise ValueError("Evidence belongs to another source")
        return value


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}\.json$")
    scope: Literal["visual", "identity", "geometry", "role", "legal"]
    target_id: str = Field(min_length=1, max_length=128)
    reviewer: str = Field(min_length=1, max_length=128)
    change: dict[str, Any]

    @field_validator("change")
    @classmethod
    def bounded_change(cls, value):
        import json

        if not value or len(json.dumps(value, allow_nan=False)) > 16384:
            raise ValueError("A bounded correction is required")
        return value
