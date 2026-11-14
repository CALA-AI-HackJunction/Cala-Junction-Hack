import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parent
DEFAULT_AGENT_ID = "cala-research-agent"


def load_settings():
    load_dotenv(ROOT / ".env", interpolate=False)


def required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} before running this command.")
    return value


def configured_agent_id() -> str:
    return os.getenv("GEMINI_AGENT_ID", "").strip() or DEFAULT_AGENT_ID


def make_client(key: str):
    return genai.Client(
        api_key=key,
        vertexai=False,
        http_options={
            "api_version": "v1beta",
            "timeout": 120_000,
            "retry_options": {"attempts": 0},
            "client_args": {"follow_redirects": False},
        },
    )


def upstream_status(error: Exception) -> int | None:
    for field in ("status_code", "code"):
        code = getattr(error, field, None)
        if isinstance(code, int):
            return code
    return None
