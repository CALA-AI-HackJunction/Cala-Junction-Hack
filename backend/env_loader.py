"""Safe .env loader with zero credential logging."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
FRONTEND_DIR = REPO_ROOT / "frontend"
DOCS_DIR = REPO_ROOT / "docs"

_ENV_LOADED = False


def load_dotenv_once(env_path: Path | None = None) -> None:
    """Load key=value pairs from .env without overriding existing process env vars."""
    global _ENV_LOADED
    if _ENV_LOADED and env_path is None:
        return
    target = env_path or (REPO_ROOT / ".env")
    if target.is_file():
        try:
            for raw_line in target.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            pass
    if env_path is None:
        _ENV_LOADED = True
