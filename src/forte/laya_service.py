"""Resident CPU Laya process, pinned local-only assets, bounded text rows."""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from forte.laya import IDENTITY, MODEL, OPTIONS, REVISION, RUNTIME_COMMIT, validate_proposal
from forte.model_profile import hash_file


def preflight(agent, state, questions):
    """Use the pinned runtime's exact sequence builder; forbid all hidden slicing."""
    from laya.common import build_sequence, encode_text, render_options

    accepted, refusals = {}, {}
    for key, definition in questions.items():
        if (
            set(definition) != {"type", "instructions", "criteria"}
            or definition["type"] != "choice"
            or definition["criteria"] != OPTIONS
        ):
            raise ValueError("Only explicit condition choices are supported")
        question = agent._to_internal(definition)
        instruction_tokens = encode_text(
            agent.tok, "choice question: " + question["ins"], add_special_tokens=False
        )["input_ids"]
        option_tokens = [
            encode_text(agent.tok, " " + option, add_special_tokens=False)["input_ids"]
            for option in render_options(question)
        ]
        # Upstream build_head caps each option at 48 and slices the instruction to
        # head_max_len minus options. This larger head budget avoids that slicing;
        # the exact builder then proves the complete state also fits 1,024.
        head_budget = len(instruction_tokens) + sum(len(ids) + 1 for ids in option_tokens) + 16
        seq, markers, stats, state_stats = build_sequence(
            agent.tok,
            state,
            question,
            1024,
            head_budget,
            return_stats=True,
            return_truncation_stats=True,
        )
        if (
            head_budget > 1024
            or any(len(ids) > 48 for ids in option_tokens)
            or state_stats["truncated"]
            or len(markers) != 3
            or stats["options_distinct"] != 3
            or stats["tokens_per_option"] is not None
        ):
            refusals[key] = {"choice": "unknown", "refusal": "token_limit", "tokens": len(seq)}
        else:
            accepted[key] = (definition, head_budget, len(seq))
    return accepted, refusals


def predict(agent, state, questions):
    if (
        not isinstance(state, dict)
        or not isinstance(questions, dict)
        or not 1 <= len(questions) <= 4
    ):
        raise ValueError("Bounded structured facts and one to four questions required")
    accepted, answers = preflight(agent, state, questions)
    # A shared sufficient head ceiling does not pad the shorter heads; preflight
    # proved each exact sequence fits. One batch contains at most four encoder rows.
    if accepted:
        budget = max(row[1] for row in accepted.values())
        batch = {key: row[0] for key, row in accepted.items()}
        result = agent.predict(state, batch, max_len=1024, head_max_len=budget)
        if set(result["answers"]) != set(batch):
            raise ValueError("Missing condition response")
        for key, answer in result["answers"].items():
            answers[key] = {**validate_proposal(answer), "tokens": accepted[key][2]}
    from forte.telemetry import memory_snapshot

    memory = memory_snapshot(device=False)
    for answer in answers.values():
        answer["cpu_process_peak_rss_bytes"] = memory["process_peak_rss_bytes"]
    return {"identity": IDENTITY, "answers": answers}


def load_agent(root):
    # Paths must exist BEFORE upstream Agent is called (it otherwise downloads).
    root = root.resolve(strict=True)
    manifest = json.loads((root / "model-hashes.json").read_bytes())
    if (
        manifest.get("model") != MODEL
        or manifest.get("revision") != REVISION
        or root.name != REVISION
    ):
        raise ValueError("Selected Laya snapshot identity differs")
    files = manifest["files"]
    required = {
        "model.safetensors",
        "rl_agent_config.json",
        "tokenizer/tokenizer.json",
        "tokenizer/tokenizer_config.json",
        "encoder/config.json",
    }
    if not required <= files.keys():
        raise ValueError("Incomplete Laya snapshot inventory")
    for name, expected in files.items():
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root) or hash_file(path) != expected:
            raise ValueError("Laya snapshot bytes differ")
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.name != "model-hashes.json"
    }
    if actual != set(files):
        raise ValueError("Unmanifested Laya asset")
    from importlib.metadata import distribution

    direct = json.loads(distribution("laya").read_text("direct_url.json") or "{}")
    if direct.get("vcs_info", {}).get("commit_id") != RUNTIME_COMMIT:
        raise ValueError("Laya runtime commit is not the selected pin")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", LAYA_CPU_AMP="off")
    from laya import Agent

    agent = Agent(str(root), device="cpu", backend="eager", expected_sha256=files)
    agent.model.float().eval()
    agent.amp_enabled = False
    if str(agent.device) != "cpu":
        raise ValueError("Laya must remain on CPU")
    if any(hash_file(root / name) != expected for name, expected in files.items()):
        raise ValueError("Laya runtime modified immutable staged assets")
    return agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    agent = load_agent(args.root)
    # Readiness is advertised only after an actual synthetic CPU forward.
    predict(
        agent,
        {"facts": ["Synthetic startup check: evidence is unavailable."]},
        {
            "warmup": {
                "type": "choice",
                "instructions": "Evidence establishes an observed action.",
                "criteria": OPTIONS,
            }
        },
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, status, value):
            raw = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.send_json(200, IDENTITY) if self.path == "/health/ready" else self.send_json(
                404, {}
            )

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/conditions" or not 0 < size <= 131072:
                    raise ValueError("Invalid bounded request")
                self.connection.settimeout(5)
                data = json.loads(self.rfile.read(size))
                result = predict(agent, data["state"], data["questions"])
                self.send_json(200, result)
            except (ValueError, KeyError, TypeError):
                self.send_json(422, {"error": "invalid_condition_request"})
            except Exception:
                self.send_json(503, {"error": "condition_runtime_unavailable"})

    HTTPServer(("127.0.0.1", 8002), Handler).serve_forever()


if __name__ == "__main__":
    main()
