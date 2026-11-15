"""Primary Uvicorn ASGI entrypoint (`backend.main:app`)."""

from __future__ import annotations

import os

import uvicorn

try:
    from .app import app, create_app
    from .env_loader import load_dotenv_once
except ImportError:
    from app import app, create_app
    from env_loader import load_dotenv_once

__all__ = ["app", "create_app", "main"]


def main() -> None:
    load_dotenv_once()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
