"""Law-independent private role diagnostic. Expected answers never enter model inputs."""

import base64
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputFrame(Strict):
    frame_id: str
    timestamp_sec: float = Field(ge=0, allow_inf_nan=False)
    path: str
    sha256: str


class RoleCase(Strict):
    case_id: str
    target_sec: float = Field(ge=0, allow_inf_nan=False)
    frames: list[InputFrame] = Field(min_length=1, max_length=12)


class Inputs(Strict):
    schema_version: Literal[1]
    cases: list[RoleCase] = Field(min_length=1, max_length=6)


class RoleAnswer(Strict):
    actor_role: Literal["cashier", "customer", "unclear"]
    evidence_frame_ids: list[str] = Field(max_length=3)
    continuity_supported: bool
    explanation: str = Field(min_length=1, max_length=1600)


def load_inputs(path: Path):
    inputs = Inputs.model_validate_json(path.read_bytes())
    if len({c.case_id for c in inputs.cases}) != len(inputs.cases):
        raise ValueError("Duplicate diagnostic case")
    for case in inputs.cases:
        if len({f.frame_id for f in case.frames}) != len(case.frames):
            raise ValueError("Duplicate diagnostic frame")
        if [f.timestamp_sec for f in case.frames] != sorted(f.timestamp_sec for f in case.frames):
            raise ValueError("Diagnostic frames must be chronological")
        for frame in case.frames:
            image = (path.parent / frame.path).resolve()
            if not image.is_relative_to(path.parent.resolve()):
                raise ValueError("Diagnostic image must be local to the input pack")
            if hashlib.sha256(image.read_bytes()).hexdigest() != frame.sha256:
                raise ValueError("Diagnostic frame SHA256 mismatch")
    return inputs.cases


def messages(case: RoleCase, root: Path):
    content = [
        {
            "type": "text",
            "text": (
                f"The images are chronological views of one interaction. Around {case.target_sec:.2f} "
                "seconds, identify the person moving away from the interaction/workstation area. "
                "Classify THAT MOVING PERSON as cashier, customer, or unclear. Establish their role "
                "from visible service actions and continuity across images. Do not define roles by "
                "appearance, fixed screen position, standing up, or departure alone. If no unique "
                "moving person or reliable role/continuity is visible, use unclear. Cite up to three "
                "supplied frame IDs that support the role. Explain only visible evidence and limits. "
                "This is a factual role task; do not judge law, compliance or intent. Return JSON."
            ),
        }
    ]
    for frame in case.frames:
        raw = base64.b64encode((root / frame.path).read_bytes()).decode()
        content.extend(
            [
                {"type": "text", "text": f"Frame {frame.frame_id}, {frame.timestamp_sec:.2f} s:"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + raw}},
            ]
        )
    return [{"role": "user", "content": content}]


def validate_answer(case, answer):
    if not set(answer.evidence_frame_ids) <= {f.frame_id for f in case.frames}:
        raise ValueError("Role answer cites a frame not supplied")
    if answer.actor_role != "unclear" and (
        not answer.evidence_frame_ids or not answer.continuity_supported
    ):
        raise ValueError("Certain role requires evidence and continuity")


def save_report(path, report):
    """Write privately; callers keep generated descriptions out of stdout and Git."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)
