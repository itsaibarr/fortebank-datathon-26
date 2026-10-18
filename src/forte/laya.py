"""Mandatory loopback CPU decision boundary. No images, routing or fallback."""

import math
import time
from urllib.parse import urlsplit

import httpx

MODEL = "convaiinnovations/laya-multilingual"
REVISION = "1720e3e3357cfe1e281542e223f8273b0890ca34"
RUNTIME_COMMIT = "d74e8be46ef5241e4ba2b16cd25e896f24f71373"
IDENTITY = {
    "model": MODEL,
    "revision": REVISION,
    "runtime_commit": RUNTIME_COMMIT,
    "device": "cpu",
    "precision": "float32",
    "max_tokens": 1024,
}
OPTIONS = {
    "satisfied": "Evidence establishes the positive proposition.",
    "contradicted": "Counterevidence establishes the proposition is false.",
    "unknown": "Missing, insufficient, inconsistent or unobservable evidence.",
}


def validate_proposal(answer):
    if not isinstance(answer, dict) or answer.get("choice") not in OPTIONS:
        raise ValueError("Invalid three-state Laya proposal")
    probabilities = answer.get("probabilities", {})
    if (
        set(probabilities) != set(OPTIONS)
        or any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or not 0 <= v <= 1
            for v in probabilities.values()
        )
        or abs(sum(probabilities.values()) - 1) > 0.002
    ):
        raise ValueError("Invalid Laya probability distribution")
    if probabilities[answer["choice"]] != max(probabilities.values()):
        raise ValueError("Laya choice disagrees with distribution")
    return answer


class LocalLaya:
    def __init__(self, url="http://127.0.0.1:8002", *, client=None):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Laya requires a plain controlled loopback origin")
        self.url = url.rstrip("/")
        self.client = client or httpx.Client(trust_env=False, follow_redirects=False)
        self.identity = IDENTITY.copy()

    def ready(self):
        try:
            response = self.client.get(self.url + "/health/ready", timeout=2)
            return response.status_code == 200 and response.json() == self.identity
        except (httpx.HTTPError, ValueError):
            return False

    def propose(self, state, questions, *, deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError("Condition deadline exhausted")
        if not 1 <= len(questions) <= 4:
            raise ValueError("At most four independent CPU condition rows per batch")
        response = self.client.post(
            self.url + "/conditions",
            json={
                "state": state,
                "questions": questions,
            },
            timeout=max(0.001, deadline - time.monotonic()),
        )
        response.raise_for_status()
        result = response.json()
        if (
            not isinstance(result, dict)
            or result.get("identity") != self.identity
            or not isinstance(result.get("answers"), dict)
            or set(result["answers"]) != set(questions)
        ):
            raise ValueError("Laya response identity/questions differ")
        for answer in result["answers"].values():
            if not isinstance(answer, dict):
                raise ValueError("Invalid Laya answer shape")
            if answer.get("refusal") == "token_limit":
                if answer.get("choice") != "unknown":
                    raise ValueError("Token refusal cannot establish a condition")
            else:
                validate_proposal(answer)
        return result["answers"]
