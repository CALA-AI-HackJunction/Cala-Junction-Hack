"""Persistent, versioned analysis results store (Aiven PG + Valkey + SQLite)."""
from __future__ import annotations

try:
    from .aiven_store import UnifiedAnalysisStore
except ImportError:
    from aiven_store import UnifiedAnalysisStore


class AnalysisStore(UnifiedAnalysisStore):
    """Drop-in compatible AnalysisStore backed by UnifiedAnalysisStore."""
