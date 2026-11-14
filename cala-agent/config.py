"""Configuration — loads secrets from env vars (locally from .env, on Cloud Run from Secret Manager)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    cala_api_key: str
    cala_mcp_url: str
    gemini_model: str
    google_cloud_project: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        key = os.environ.get("CALA_API_KEY")
        if not key:
            raise RuntimeError("CALA_API_KEY is required — set it in .env or Secret Manager")
        return cls(
            cala_api_key=key,
            cala_mcp_url=os.environ.get("CALA_MCP_URL", "https://api.cala.ai/mcp"),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            google_cloud_project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        )


settings = Settings.from_env() if os.environ.get("CALA_API_KEY") else None


def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = Settings.from_env()
    return settings
