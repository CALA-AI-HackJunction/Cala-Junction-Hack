#!/usr/bin/env python3
"""Root CLI shim forwarding to `backend.cli:main` for 100% reference compatibility."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
