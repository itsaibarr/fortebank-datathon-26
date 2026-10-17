import json

import httpx
import pytest
from pydantic import ValidationError

from forte.contracts import WindowObservation
from forte.worker import failure_diagnostics


def test_diagnostics_never_copy_model_text_validation_inputs_or_request_urls():
    secret = "private-scene-canary"
    with pytest.raises(ValidationError) as caught:
        WindowObservation.model_validate({"complete": True, "events": [], secret: secret})
    details = failure_diagnostics(caught.value)
    assert details["validation_types"] == {"extra_forbidden": 1}
    assert secret not in json.dumps(details)
    request = httpx.Request("POST", "http://127.0.0.1:8001/" + secret)
    response = httpx.Response(400, request=request, text=secret)
    error = httpx.HTTPStatusError(secret, request=request, response=response)
    assert failure_diagnostics(error) == {"error_type": "HTTPStatusError", "http_status": 400}
    assert failure_diagnostics(ValueError(secret)) == {"error_type": "ValueError"}


def test_incomplete_generation_has_a_safe_specific_reason():
    assert failure_diagnostics(ValueError("Model answer was incomplete"))["reason"] == (
        "model_output_truncated"
    )
