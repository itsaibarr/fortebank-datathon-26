"""Synthetic tests of the selected text boundary; no runtime/weight downloads."""

import json
import sys
import time
import types
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from synthetic_decisions import UnknownDecisions
from test_jury_projection import _fixture

from forte.api import create_app
from forte.laya import IDENTITY, OPTIONS, LocalLaya, validate_proposal
from forte.laya_service import load_agent, predict
from forte.legal_reasoning import LegalEvidenceService
from forte.settings import Settings


@pytest.mark.parametrize(
    "url",
    ["https://example.org", "http://127.0.0.1.evil", "http://localhost/a", "http://a:b@localhost"],
)
def test_laya_has_no_external_endpoint(url):
    with pytest.raises(ValueError):
        LocalLaya(url)


@pytest.mark.parametrize("state", OPTIONS)
def test_three_states_are_explicit_choices(state):
    result = {"choice": state, "probabilities": {key: float(key == state) for key in OPTIONS}}
    assert validate_proposal(result)["choice"] == state


@pytest.mark.parametrize(
    "bad",
    [
        {"choice": "yes", "probabilities": {}},
        {"choice": "satisfied", "probabilities": {"satisfied": 1.0}},
        {
            "choice": "satisfied",
            "probabilities": {"satisfied": float("nan"), "contradicted": 0.0, "unknown": 0.0},
        },
        {
            "choice": "satisfied",
            "probabilities": {"satisfied": 0.1, "contradicted": 0.1, "unknown": 0.8},
        },
    ],
)
def test_malformed_predictions_do_not_become_conditions(bad):
    with pytest.raises(ValueError):
        validate_proposal(bad)


def test_missing_or_wrong_cpu_model_fails_admission_without_fallback(tmp_path, monkeypatch):
    from forte.inference import LocalVLM

    monkeypatch.setattr(LocalVLM, "ready", lambda self: True)
    monkeypatch.setattr(LocalLaya, "ready", lambda self: False)
    settings = Settings(
        "synthetic-key-long-enough", tmp_path, reasoning_config={"tracking": {}, "legal": {}}
    )
    consumed = []

    def body():
        consumed.append(True)
        yield b"private-body-must-not-be-read"

    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 503
        response = client.post(
            "/api/v1/analyze", content=body(), headers={"X-API-Key": settings.api_key}
        )
        assert response.status_code == 503
    assert consumed == []
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={**IDENTITY, "revision": "wrong"})
    )
    assert not LocalLaya(client=httpx.Client(transport=transport)).ready()


def test_choice_client_checks_identity_questions_and_absolute_deadline():
    seen = []

    def reply(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "identity": IDENTITY,
                "answers": {
                    "c": {
                        "choice": "unknown",
                        "probabilities": {"satisfied": 0.0, "contradicted": 0.0, "unknown": 1.0},
                    }
                },
            },
        )

    backend = LocalLaya(client=httpx.Client(transport=httpx.MockTransport(reply)))
    questions = {
        "c": {"type": "choice", "instructions": "An action is visible.", "criteria": OPTIONS}
    }
    assert (
        backend.propose({"facts": []}, questions, deadline=time.monotonic() + 5)["c"]["choice"]
        == "unknown"
    )
    assert set(seen[0]) == {"state", "questions"}
    with pytest.raises(TimeoutError):
        backend.propose({}, questions, deadline=time.monotonic() - 1)


def test_exact_sequence_budget_counts_options_instructions_and_counterevidence(monkeypatch):
    # This injected builder models upstream's special-token and head/state split.
    # Real tokenizer/checkpoint compatibility remains an explicit acceptance task.
    common = types.ModuleType("laya.common")
    common.encode_text = lambda tok, text, **kwargs: {"input_ids": text.split()}
    common.render_options = lambda q: [key + ": " + value for key, value in q["crit"].items()]
    built = []

    def sequence(tok, state, q, max_len, head_max_len, **kwargs):
        head = (
            len(("choice question: " + q["ins"]).split())
            + sum(len(text.split()) + 1 for text in common.render_options(q))
            + 3
        )
        full = head + len(json.dumps(state).split()) + 1
        built.append((full, state))
        return (
            list(range(min(full, max_len))),
            [1, 2, 3],
            {"options_distinct": 3, "tokens_per_option": None},
            {"truncated": full > max_len},
        )

    common.build_sequence = sequence
    monkeypatch.setitem(sys.modules, "laya.common", common)

    class Agent:
        tok = object()
        calls = []

        def _to_internal(self, question):
            return {"t": "choice", "ins": question["instructions"], "crit": question["criteria"]}

        def predict(self, state, questions, **kwargs):
            self.calls.append((state, questions, kwargs))
            return {
                "answers": {
                    key: {
                        "choice": "unknown",
                        "probabilities": {"satisfied": 0.0, "contradicted": 0.0, "unknown": 1.0},
                    }
                    for key in questions
                }
            }

    agent = Agent()
    question = {
        "condition": {
            "type": "choice",
            "instructions": "The action is visible.",
            "criteria": OPTIONS,
        }
    }
    packet = {"support": "visible action", "counterevidence": "contrary observation " * 1000}
    answer = predict(agent, packet, question)["answers"]["condition"]
    assert answer["choice"] == "unknown" and answer["refusal"] == "token_limit"
    assert not agent.calls and built[0][1]["counterevidence"] == packet["counterevidence"]
    result = predict(agent, {"facts": ["small complete packet"]}, question)
    assert result["identity"] == IDENTITY and len(agent.calls) == 1
    assert agent.calls[0][2]["max_len"] == 1024
    with pytest.raises(ValueError):
        predict(agent, {}, {str(i): question["condition"] for i in range(5)})


def test_missing_snapshot_never_invokes_hub_or_backend(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_agent(tmp_path / "missing")


@pytest.mark.parametrize("conflict", ["counterevidence", "visibility", "role", "unavailable"])
def test_text_condition_cannot_override_visual_unknowns_or_missing_backend(tmp_path, conflict):
    fixture = _fixture(tmp_path)
    timeline = fixture.report["timeline"]
    obs = timeline["observations"][0]
    if conflict == "counterevidence":
        obs["contradictory_frame_ids"] = [fixture.registry.frames[1].frame_id]
    elif conflict == "visibility":
        obs["visibility"] = "partly_occluded"
    elif conflict == "role":
        timeline["role_conflicts"] = [{"participant_id": "p0", "status": "unresolved"}]

    class Proposals(UnknownDecisions):
        calls = 0

        def propose(self, state, questions, *, deadline):
            self.calls += 1
            assert "image" not in state and "facts" in state
            if conflict == "unavailable":
                raise httpx.ReadTimeout("synthetic timeout")
            return {
                key: {
                    "choice": "satisfied",
                    "probabilities": {"satisfied": 1.0, "contradicted": 0.0, "unknown": 0.0},
                }
                for key in questions
            }

    law = fixture.settings.reasoning_config
    config = json.loads(law.read_text())["legal"]
    service = LegalEvidenceService(
        Path(config["release"]), Path(config["cards"]), applicability=config["applicability"]
    )
    backend = Proposals()
    result = service.evaluate_timeline(
        timeline,
        fixture.registry,
        backend,
        tmp_path / "text-check",
        time.monotonic() + 5,
        event_date=config["event_date"],
        operation_context=config["operation_context"],
        max_calls=10,
    )
    assert backend.calls > 0
    assert all(row["assessment"] == "insufficient_evidence" for row in result["assessments"])
    assert all(c["result"] == "unknown" for row in result["assessments"] for c in row["conditions"])


def test_only_one_production_entry_and_no_legal_vision_call():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/forte/reasoning_pipeline.py").exists()
    from forte import legal_reasoning

    assert "backend.request(" not in Path(legal_reasoning.__file__).read_text()
    assert "FORTE_V1_PIPELINE" not in (root / "src/forte/settings.py").read_text()
