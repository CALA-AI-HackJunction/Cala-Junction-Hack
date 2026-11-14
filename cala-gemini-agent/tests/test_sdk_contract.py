import json

import httpx
from google import genai

from setup_agent import save_credential


def test_installed_sdk_serializes_credentials_and_interactions():
    seen = []

    def handle(request):
        path = request.url.path
        seen.append((request.method, path))
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "fake-gemini-key"
        if path == "/v1beta/credentials":
            assert json.loads(request.content) == {
                "id": "cala-api-key", "type": "bearer_token", "token": "fake-cala-key",
                "header_name": "X-API-KEY", "prefix": "",
            }
            return httpx.Response(409, json={"error": {"message": "Already exists"}})
        if path == "/v1beta/credentials/cala-api-key":
            assert json.loads(request.content) == {
                "type": "bearer_token", "token": "fake-cala-key",
                "header_name": "X-API-KEY", "prefix": "",
            }
            return httpx.Response(200, json={"id": "cala-api-key", "type": "bearer_token", "status": "active"})
        if path == "/v1beta/interactions":
            payload = json.loads(request.content)
            assert payload["agent"] == "test-agent"
            assert payload["environment"] == "sandbox1"
            assert payload["previous_interaction_id"] == "previous"
            assert payload["background"] is True
            return httpx.Response(200, json={"id": "job1", "status": "in_progress", "environment_id": "sandbox1"})
        assert path == "/v1beta/interactions/job1"
        return httpx.Response(200, json={
            "id": "job1",
            "status": "completed",
            "environment_id": "sandbox1",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": "Test answer"}]}],
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as http, genai.Client(
        api_key="fake-gemini-key",
        vertexai=False,
        http_options={"api_version": "v1beta", "httpx_client": http, "retry_options": {"attempts": 0}},
    ) as sdk:
        save_credential(sdk.credentials, "fake-cala-key")
        job = sdk.interactions.create(
            agent="test-agent", input="Test", environment="sandbox1",
            previous_interaction_id="previous", background=True,
        )
        assert job.status == "in_progress"
        completed = sdk.interactions.get(id=job.id)
        assert completed.environment_id == "sandbox1"
        assert completed.output_text == "Test answer"
    credential_create = ("POST", "/v1beta/credentials")
    assert seen[0] == credential_create
    assert all(event == credential_create for event in seen[:-3])
    assert seen[-3:] == [
        ("PATCH", "/v1beta/credentials/cala-api-key"),
        ("POST", "/v1beta/interactions"),
        ("GET", "/v1beta/interactions/job1"),
    ]
