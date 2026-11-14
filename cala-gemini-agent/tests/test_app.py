from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import errors

from app import app

KEY = "fake-gemini-key"
TOKEN = "t" * 40


def interaction(id="job1", status="completed", text="**Cala** result", environment="sandbox1"):
    return SimpleNamespace(id=id, status=status, environment_id=environment, output_text=text)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("GEMINI_AGENT_ID", "test-agent")
    monkeypatch.setenv("CHAT_SIGNING_KEY", "s" * 48)
    monkeypatch.setenv("APP_ACCESS_TOKEN", "")
    monkeypatch.setenv("CALA_CONNECTION_MODE", "managed")
    monkeypatch.delenv("K_SERVICE", raising=False)
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(genai, "Client", factory)
    return client, factory


@pytest.fixture
def web(provider):
    with TestClient(app) as client:
        yield client, provider[0]


def receipt(response):
    return {"X-Chat-Receipt": response.headers["X-Chat-Receipt"]}


def test_health_and_ui(web):
    client, service = web
    assert client.get("/health").json() == {"status": "ok"}
    home = client.get("/")
    assert "Cala Research" in home.text
    assert "frame-ancestors 'none'" in home.headers["Content-Security-Policy"]
    assert client.get("/static/chat.js").is_success
    assert KEY not in home.text
    service.interactions.create.assert_not_called()


def test_chat_and_continuation(web):
    client, service = web
    service.interactions.create.side_effect = [interaction(), interaction(id="job2")]
    first = client.post("/api/chat", json={"message": "  Find sources  "})
    assert first.json() == {
        "reply": "**Cala** result", "interaction_id": "job1", "environment_id": "sandbox1"
    }
    assert first.headers["Cache-Control"] == "no-store"
    service.interactions.create.assert_called_once_with(
        agent="test-agent", input="Find sources", previous_interaction_id=None,
        environment="remote", background=False, timeout=840,
    )
    second = client.post(
        "/api/chat", headers=receipt(first),
        json={"message": "Summarize", "previous_interaction_id": "job1", "environment_id": "sandbox1"},
    )
    assert second.json()["interaction_id"] == "job2"
    assert service.interactions.create.call_args.kwargs["previous_interaction_id"] == "job1"
    assert service.interactions.create.call_args.kwargs["environment"] == "sandbox1"


def test_background_poll_markdown_and_redaction(web):
    client, service = web
    service.interactions.create.return_value = interaction(status="in_progress", environment=None)
    service.interactions.get.return_value = interaction(text=(
        "**Cala** [source](https://example.org) <script>bad()</script> "
        "![pixel](https://example.org/pixel.png) " + KEY
    ))
    started = client.post("/api/jobs", json={"message": "Analyze"})
    assert started.status_code == 202
    assert started.json()["output_text"] is None
    assert service.interactions.create.call_args.kwargs["background"] is True
    completed = client.get("/api/jobs/job1", headers=receipt(started))
    assert completed.json()["status"] == "completed"
    html = completed.json()["output_html"]
    assert "<strong>Cala</strong>" in html and 'href="https://example.org"' in html
    assert "<script>" not in html and "<img" not in html and KEY not in completed.text
    assert completed.json()["environment_id"] == "sandbox1"
    service.interactions.get.assert_called_once_with(id="job1", timeout=15)


def test_receipts_prevent_cross_job_access(web):
    client, service = web
    service.interactions.create.return_value = interaction(status="in_progress")
    started = client.post("/api/jobs", json={"message": "Analyze"})
    assert client.get("/api/jobs/job1").status_code == 404
    assert client.get("/api/jobs/other", headers=receipt(started)).status_code == 404
    assert client.post(
        "/api/chat", headers=receipt(started), json={"message": "Continue", "environment_id": "other"},
    ).status_code == 404
    service.interactions.get.assert_not_called()
    assert service.interactions.create.call_count == 1


@pytest.mark.parametrize(("failure", "status"), [
    (RuntimeError("secret upstream detail"), 502),
    (httpx.ReadTimeout("secret upstream detail"), 504),
    (errors.ClientError(429, {"message": "secret upstream detail"}), 429),
])
def test_upstream_errors(web, caplog, failure, status):
    client, service = web
    service.interactions.create.side_effect = failure
    response = client.post("/api/chat", json={"message": "Hello"})
    assert response.status_code == status
    assert "secret upstream detail" not in response.text + caplog.text


def test_validation_hides_original_input(web):
    client, service = web
    response = client.post("/api/jobs", json={"message": " ", "unexpected": "secret input"})
    assert response.status_code == 422
    assert "secret input" not in response.text
    service.interactions.create.assert_not_called()


def test_optional_auth(provider, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_TOKEN", TOKEN)
    provider[0].interactions.create.return_value = interaction()
    with TestClient(app) as client:
        assert client.post("/api/jobs", json={"message": "Hi"}).status_code == 401
        assert client.get("/api/jobs/job1").status_code == 401
        allowed = client.post("/api/jobs", json={"message": "Hi"}, headers={"Authorization": f"Bearer {TOKEN}"})
        assert allowed.status_code == 202


def test_direct_mode_only_sends_evidence_to_gemini(provider, monkeypatch):
    monkeypatch.setenv("CALA_CONNECTION_MODE", "direct")
    monkeypatch.setenv("CALA_API_KEY", "fake-cala-key")
    search = AsyncMock(return_value="Cala evidence with fake-cala-key")
    monkeypatch.setattr("app.search_cala", search)
    provider[0].interactions.create.return_value = interaction(environment=None)
    with TestClient(app) as client:
        response = client.post("/api/jobs", json={"message": "Find a source"})
        assert response.status_code == 202
    search.assert_awaited_once_with("Find a source", "fake-cala-key")
    kwargs = provider[0].interactions.create.call_args.kwargs
    assert kwargs["model"] == "gemini-3.8-flash"
    assert "Cala evidence" in kwargs["input"]
    assert "fake-cala-key" not in kwargs["input"]
    assert "agent" not in kwargs and "environment" not in kwargs
