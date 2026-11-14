import json
from unittest.mock import Mock

import httpx
import pytest
from google.genai import errors

from setup_agent import AGENTS_API, SetupError, agent_definition, provision


def test_provision_preserves_mcp_credential_on_the_wire():
    sdk = Mock()
    requests = []

    def handle(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        assert request.url == AGENTS_API
        payload = json.loads(request.content)
        assert payload["tools"][-1] == {
            "name": "cala", "type": "mcp_server", "url": "https://api.cala.ai/mcp/",
            "credential": "cala-api-key",
        }
        assert b"fake-cala-key" not in request.content
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        provision(sdk, http, "demo", "fake-cala-key")
    assert [request.method for request in requests] == ["GET", "POST"]
    sdk.credentials.create.assert_called_once_with(
        id="cala-api-key", type="bearer_token", token="fake-cala-key",
        header_name="X-API-KEY", prefix="",
    )


def test_rerun_rotates_credential_and_keeps_matching_agent():
    sdk = Mock()
    sdk.credentials.create.side_effect = errors.ClientError(409, {"message": "Already exists"})

    def handle(request):
        assert request.method == "GET"
        return httpx.Response(200, json=agent_definition("demo"))

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        provision(sdk, http, "demo", "rotated-key")
    sdk.credentials.update.assert_called_once_with(
        id="cala-api-key", type="bearer_token", token="rotated-key",
        header_name="X-API-KEY", prefix="",
    )


def test_existing_unrelated_agent_is_preserved():
    sdk = Mock()
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"id": "demo"}))
    with httpx.Client(transport=transport) as http:
        with pytest.raises(SetupError, match="differs"):
            provision(sdk, http, "demo", "fake")
    sdk.credentials.create.assert_not_called()
