"""Aiven for PostgreSQL + Aiven for Valkey Unified Persistence & Telemetry Layer.

Provides sub-2ms canonical caching via Aiven Valkey (`AIVEN_VALKEY_URL`, TLS `rediss://`)
and immutable JSONB run persistence via Aiven PostgreSQL (`AIVEN_PG_URI`, `sslmode=require`),
with automatic, zero-downtime fallback to local SQLite (`backend/data/analyses.sqlite3`)
and thread-safe in-memory LRU caching when cloud URIs are unset or unreachable.
"""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class UnifiedAnalysisStore:
    """Dual cloud (Aiven PG + Valkey) and local (SQLite + Memory LRU) store."""

    def __init__(
        self,
        path: Path | str,
        *,
        pg_uri: str | None = None,
        valkey_url: str | None = None,
        lru_maxsize: int = 256,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._lru_maxsize = max(16, int(lru_maxsize))
        self._memory_lru: OrderedDict[str, str] = OrderedDict()
        self._kv_memory: OrderedDict[str, str] = OrderedDict()

        # Telemetry counters
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_cache_hit_ms = 0.0
        self.write_count = 0
        self.total_write_ms = 0.0

        # Always bootstrap SQLite schema so local persistence & `_connect()` work 100%
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    graph_version TEXT NOT NULL,
                    cache_key TEXT,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS analyses_cache ON analyses(cache_key);
                CREATE INDEX IF NOT EXISTS analyses_time ON analyses(created_at DESC);
                CREATE TABLE IF NOT EXISTS kv_cache (
                    cache_key TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

        # Optional Aiven PostgreSQL setup
        raw_pg = pg_uri if pg_uri is not None else os.environ.get("AIVEN_PG_URI", "")
        self._pg_uri = raw_pg.strip()
        self.aiven_pg_configured = bool(self._pg_uri)
        self.aiven_pg_connected = False
        self._psycopg = None
        if self.aiven_pg_configured:
            self._init_postgres()

        # Optional Aiven Valkey setup
        raw_vk = valkey_url if valkey_url is not None else os.environ.get("AIVEN_VALKEY_URL", "")
        self._valkey_url = raw_vk.strip()
        self.aiven_valkey_configured = bool(self._valkey_url)
        self.aiven_valkey_connected = False
        self._valkey_client = None
        if self.aiven_valkey_configured:
            self._init_valkey()

    def _init_postgres(self) -> None:
        try:
            import psycopg  # type: ignore

            self._psycopg = psycopg
            with psycopg.connect(self._pg_uri, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS analyses (
                            run_id TEXT PRIMARY KEY,
                            created_at TIMESTAMPTZ NOT NULL,
                            question_id TEXT NOT NULL,
                            graph_version TEXT NOT NULL,
                            cache_key TEXT,
                            composer_mode TEXT,
                            status TEXT NOT NULL,
                            elapsed_ms DOUBLE PRECISION,
                            request_json JSONB NOT NULL,
                            response_json JSONB NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_analyses_cache_key ON analyses(cache_key);
                        CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC);
                        CREATE TABLE IF NOT EXISTS telemetry_events (
                            id BIGSERIAL PRIMARY KEY,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            event_type TEXT NOT NULL,
                            payload_json JSONB NOT NULL
                        );
                        """
                    )
                conn.commit()
            self.aiven_pg_connected = True
        except Exception:
            # Never echo URI credentials in logs or exceptions
            self.aiven_pg_connected = False

    def _init_valkey(self) -> None:
        try:
            import valkey  # type: ignore

            client = valkey.from_url(
                self._valkey_url,
                socket_connect_timeout=3,
                socket_timeout=3,
                decode_responses=True,
            )
            client.ping()
            self._valkey_client = client
            self.aiven_valkey_connected = True
        except Exception:
            self._valkey_client = None
            self.aiven_valkey_connected = False

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @property
    def backend_name(self) -> str:
        return "aiven_pg" if self.aiven_pg_connected else "sqlite"

    @property
    def cache_layer_name(self) -> str:
        return "aiven_valkey" if self.aiven_valkey_connected else "sqlite_cache"

    def _lru_put(self, key: str, raw_json: str) -> None:
        with self._lock:
            self._memory_lru[key] = raw_json
            self._memory_lru.move_to_end(key)
            while len(self._memory_lru) > self._lru_maxsize:
                self._memory_lru.popitem(last=False)

    def _lru_get(self, key: str) -> str | None:
        with self._lock:
            raw = self._memory_lru.get(key)
            if raw is not None:
                self._memory_lru.move_to_end(key)
            return raw

    def save(self, request: dict[str, Any], response: dict[str, Any], cache_key: str | None = None) -> None:
        started = time.perf_counter()
        req_str = json.dumps(request, ensure_ascii=False)
        resp_str = json.dumps(response, ensure_ascii=False)

        # 1. Always write to local SQLite in a single transaction
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    response["run_id"],
                    response["generated_at"],
                    response["question_id"],
                    response["graph_version"],
                    cache_key,
                    response["status"],
                    req_str,
                    resp_str,
                ),
            )

        # 2. Mirror to Aiven PostgreSQL when connected
        if self.aiven_pg_connected and self._psycopg is not None:
            try:
                with self._psycopg.connect(self._pg_uri, connect_timeout=4) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO analyses (
                                run_id, created_at, question_id, graph_version, cache_key,
                                composer_mode, status, elapsed_ms, request_json, response_json
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                            ON CONFLICT (run_id) DO NOTHING
                            """,
                            (
                                response["run_id"],
                                response["generated_at"],
                                response["question_id"],
                                response["graph_version"],
                                cache_key,
                                response.get("generation_mode"),
                                response["status"],
                                float(response.get("elapsed_ms") or 0.0),
                                req_str,
                                resp_str,
                            ),
                        )
                    conn.commit()
            except Exception:
                self.aiven_pg_connected = False

        # 3. Populate Aiven Valkey + Memory LRU canonical cache
        if cache_key:
            self._lru_put(cache_key, resp_str)
            if self.aiven_valkey_connected and self._valkey_client is not None:
                try:
                    self._valkey_client.setex(f"unicorn_radar:analysis:{cache_key}", 86400, resp_str)
                except Exception:
                    self.aiven_valkey_connected = False

        elapsed = (time.perf_counter() - started) * 1000
        with self._lock:
            self.write_count += 1
            self.total_write_ms += elapsed

    def get(self, run_id: str) -> dict[str, Any] | None:
        if self.aiven_pg_connected and self._psycopg is not None:
            try:
                with self._psycopg.connect(self._pg_uri, connect_timeout=4) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT response_json FROM analyses WHERE run_id = %s", (run_id,))
                        row = cur.fetchone()
                        if row and row[0] is not None:
                            val = row[0]
                            return copy.deepcopy(val) if isinstance(val, dict) else json.loads(val)
            except Exception:
                self.aiven_pg_connected = False

        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM analyses WHERE run_id = ?", (run_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def cached(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        started = time.perf_counter()

        # 1. Aiven Valkey (< 2ms cloud cache)
        if self.aiven_valkey_connected and self._valkey_client is not None:
            try:
                raw = self._valkey_client.get(f"unicorn_radar:analysis:{key}")
                if raw:
                    parsed = json.loads(raw)
                    self._record_hit((time.perf_counter() - started) * 1000)
                    return parsed
            except Exception:
                self.aiven_valkey_connected = False

        # 2. In-memory LRU
        lru_raw = self._lru_get(key)
        if lru_raw:
            parsed = json.loads(lru_raw)
            self._record_hit((time.perf_counter() - started) * 1000)
            return parsed

        # 3. Aiven PostgreSQL
        if self.aiven_pg_connected and self._psycopg is not None:
            try:
                with self._psycopg.connect(self._pg_uri, connect_timeout=4) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT response_json FROM analyses WHERE cache_key = %s ORDER BY created_at DESC LIMIT 1",
                            (key,),
                        )
                        row = cur.fetchone()
                        if row and row[0] is not None:
                            val = row[0]
                            parsed = copy.deepcopy(val) if isinstance(val, dict) else json.loads(val)
                            self._lru_put(key, json.dumps(parsed, ensure_ascii=False))
                            self._record_hit((time.perf_counter() - started) * 1000)
                            return parsed
            except Exception:
                self.aiven_pg_connected = False

        # 4. Local SQLite canonical cache
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM analyses WHERE cache_key = ? ORDER BY created_at DESC LIMIT 1",
                (key,),
            ).fetchone()
        if row:
            self._lru_put(key, row[0])
            self._record_hit((time.perf_counter() - started) * 1000)
            return json.loads(row[0])

        with self._lock:
            self.cache_misses += 1
        return None

    def _record_hit(self, elapsed_ms: float) -> None:
        with self._lock:
            self.cache_hits += 1
            self.total_cache_hit_ms += max(0.0, elapsed_ms)

    def kv_get(self, namespace_key: str) -> dict[str, Any] | None:
        """Auxiliary cache for Cala live enrichment payloads."""
        if self.aiven_valkey_connected and self._valkey_client is not None:
            try:
                raw = self._valkey_client.get(f"unicorn_radar:kv:{namespace_key}")
                if raw:
                    return json.loads(raw)
            except Exception:
                self.aiven_valkey_connected = False

        with self._lock:
            mem = self._kv_memory.get(namespace_key)
        if mem:
            return json.loads(mem)

        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM kv_cache WHERE cache_key = ?", (namespace_key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def kv_set(self, namespace_key: str, payload: dict[str, Any], ttl_seconds: int = 86400) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            self._kv_memory[namespace_key] = raw
            while len(self._kv_memory) > 256:
                self._kv_memory.popitem(last=False)

        if self.aiven_valkey_connected and self._valkey_client is not None:
            try:
                self._valkey_client.setex(f"unicorn_radar:kv:{namespace_key}", ttl_seconds, raw)
            except Exception:
                self.aiven_valkey_connected = False

        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO kv_cache VALUES (?, ?, ?)",
                (namespace_key, time.time(), raw),
            )

    def list(self, limit: int = 25) -> list[dict[str, Any]]:
        clamped = min(max(int(limit), 1), 100)
        if self.aiven_pg_connected and self._psycopg is not None:
            try:
                with self._psycopg.connect(self._pg_uri, connect_timeout=4) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT run_id, created_at, question_id, status, graph_version, request_json
                            FROM analyses ORDER BY created_at DESC LIMIT %s
                            """,
                            (clamped,),
                        )
                        rows = cur.fetchall()
                        return [
                            {
                                "run_id": r[0],
                                "created_at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                                "question_id": r[2],
                                "status": r[3],
                                "graph_version": r[4],
                                "request": r[5] if isinstance(r[5], dict) else json.loads(r[5]),
                            }
                            for r in rows
                        ]
            except Exception:
                self.aiven_pg_connected = False

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT run_id, created_at, question_id, status, graph_version, "
                "request_json FROM analyses ORDER BY created_at DESC LIMIT ?",
                (clamped,),
            ).fetchall()
        return [
            {
                **{key: row[key] for key in row.keys() if key != "request_json"},
                "request": json.loads(row["request_json"]),
            }
            for row in rows
        ]

    def count_saved_analyses(self) -> int:
        if self.aiven_pg_connected and self._psycopg is not None:
            try:
                with self._psycopg.connect(self._pg_uri, connect_timeout=3) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM analyses")
                        row = cur.fetchone()
                        if row:
                            return int(row[0])
            except Exception:
                self.aiven_pg_connected = False
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()
        return int(row[0]) if row else 0

    def status_report(self) -> dict[str, Any]:
        saved_count = self.count_saved_analyses()
        with self._lock:
            hits = self.cache_hits
            misses = self.cache_misses
            total_lookups = hits + misses
            hit_rate = round((hits / total_lookups) * 100.0, 1) if total_lookups else 0.0
            avg_hit_ms = round(self.total_cache_hit_ms / hits, 2) if hits else 0.0
            avg_write_ms = round(self.total_write_ms / self.write_count, 2) if self.write_count else 0.0

        return {
            "storage": {
                "primary_backend": self.backend_name,
                "aiven_pg_configured": self.aiven_pg_configured,
                "aiven_pg_connected": self.aiven_pg_connected,
                "sqlite_fallback_active": not self.aiven_pg_connected,
                "saved_analyses_count": saved_count,
                "avg_write_ms": avg_write_ms,
            },
            "cache": {
                "primary_cache": self.cache_layer_name,
                "aiven_valkey_configured": self.aiven_valkey_configured,
                "aiven_valkey_connected": self.aiven_valkey_connected,
                "memory_lru_active": True,
                "cache_hits": hits,
                "cache_misses": misses,
                "hit_rate_pct": hit_rate,
                "avg_cache_hit_ms": avg_hit_ms,
            },
        }
