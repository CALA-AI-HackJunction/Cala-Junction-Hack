"""Orchestration: resolve, query, compose (Gemini + Gemma + Template), enrich, persist, stream."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .ai_engine import (
        MODEL_TELEMETRY,
        enrich_analysis_with_ai,
        gemini_is_configured,
        gemma_is_configured,
        get_gemini_model,
        get_gemma_model,
        resolve_effective_composer_mode,
    )
    from .cala_client import CalaLiveClient, cala_live_is_configured
    from .craci_client import CraciProvenanceClient, craci_api_is_configured
    from .env_loader import DATA_DIR, DOCS_DIR, load_dotenv_once
    from .generation import PROMPT_VERSION, compose
    from .ingest import ensure_snapshot
    from .queries import QueryEngine
    from .store import AnalysisStore
except ImportError:
    from ai_engine import (
        MODEL_TELEMETRY,
        enrich_analysis_with_ai,
        gemini_is_configured,
        gemma_is_configured,
        get_gemini_model,
        get_gemma_model,
        resolve_effective_composer_mode,
    )
    from cala_client import CalaLiveClient, cala_live_is_configured
    from craci_client import CraciProvenanceClient, craci_api_is_configured
    from env_loader import DATA_DIR, DOCS_DIR, load_dotenv_once
    from generation import PROMPT_VERSION, compose
    from ingest import ensure_snapshot
    from queries import QueryEngine
    from store import AnalysisStore


PIPELINE_VERSION = "2.1.0"
QUERY_POLICY_VERSION = "four-task-ranking-2.0.0"

QUESTION_SPECS: dict[str, dict[str, Any]] = {
    "person_to_company": {
        "id": "person_to_company",
        "label": "How is this person connected to this company?",
        "short_label": "Person → Company",
        "subtitle": "Bounded 4-hop warm-path discovery across Slush & Cala assertions",
        "max_hops": 4,
        "fields": {"source": "Person", "target": "Company"},
        "placeholders": {
            "source": "e.g. Camille Accolas or Dani Penev",
            "target": "e.g. Trust Exchange or Y Combinator",
        },
    },
    "company_to_company": {
        "id": "company_to_company",
        "label": "How is this company connected to that company?",
        "short_label": "Company ↔ Company",
        "subtitle": "Shared founders, executives, investors, funding rounds & board bridges",
        "max_hops": 4,
        "fields": {"source": "Company", "target": "Company"},
        "placeholders": {
            "source": "e.g. Slicker",
            "target": "e.g. Y Combinator",
        },
    },
    "company_network": {
        "id": "company_network",
        "label": "What professional network surrounds this company?",
        "short_label": "Company Network",
        "subtitle": "2-hop ecosystem map grouped into Direct People, Investors, Direct Companies & Indirect Connections",
        "max_hops": 2,
        "fields": {"company": "Company"},
        "placeholders": {
            "company": "e.g. Trust Exchange",
        },
    },
    "company_representatives": {
        "id": "company_representatives",
        "label": "Who from this company can I approach at Slush, and what should I know about them?",
        "short_label": "Slush Representatives",
        "subtitle": "Affiliated people with named Slush participation evidence vs. unverified-attendance affiliates",
        "max_hops": 1,
        "fields": {"company": "Company"},
        "placeholders": {
            "company": "e.g. Trust Exchange",
        },
    },
}

FALLBACK_PRESETS: list[dict[str, Any]] = [
    {
        "id": "founder_path_trust_exchange",
        "title": "Camille Accolas → Trust Exchange",
        "badge": "Q1 · 1-Hop Dual-Source",
        "description": "Cross-source joined founder & board paths backed by Cala + SwissTech delegation evidence.",
        "expected_status": "partial",
        "request": {"question_id": "person_to_company", "source": "Camille Accolas", "target": "Trust Exchange"},
    },
    {
        "id": "investor_multihop_yc",
        "title": "Dani Penev → Y Combinator (Cala Investor)",
        "badge": "Q1 · Multi-Hop Investor",
        "description": "3-path founder/investor bridge to canonical Cala Y Combinator identity.",
        "expected_status": "partial",
        "request": {
            "question_id": "person_to_company",
            "source": "Dani Penev",
            "target": "Y Combinator",
            "target_id": "cala:1e86655e-373d-4fe8-be13-af3713581f73",
        },
    },
    {
        "id": "company_bridge_slicker_yc",
        "title": "Slicker ↔ Y Combinator",
        "badge": "Q2 · Company-to-Investor",
        "description": "Company-to-company investment & funding-round path in Cala graph.",
        "expected_status": "partial",
        "request": {
            "question_id": "company_to_company",
            "source": "Slicker",
            "target": "Y Combinator",
            "target_id": "cala:1e86655e-373d-4fe8-be13-af3713581f73",
        },
    },
    {
        "id": "ecosystem_trust_exchange",
        "title": "Trust Exchange — 2-Hop Ecosystem",
        "badge": "Q3 · Surrounded Network",
        "description": "Bounded 2-step network grouped into direct people, investors, and indirect connections.",
        "expected_status": "partial",
        "request": {"question_id": "company_network", "company": "Trust Exchange"},
    },
    {
        "id": "slush_reps_trust_exchange",
        "title": "Trust Exchange — Slush Approach Brief",
        "badge": "Q4 · Slush Representatives",
        "description": "Separates named Slush 2026 participants from affiliated people with unverified attendance.",
        "expected_status": "partial",
        "request": {"question_id": "company_representatives", "company": "Trust Exchange"},
    },
    {
        "id": "ambiguous_yc",
        "title": "Ambiguity Guardrail: Dani Penev → 'Y Combinator'",
        "badge": "Disambiguation Picker",
        "description": "Demonstrates zero silent entity merging between Cala investor node and Slush text org stubs.",
        "expected_status": "needs_resolution",
        "request": {"question_id": "person_to_company", "source": "Dani Penev", "target": "Y Combinator"},
    },
    {
        "id": "ambiguous_ben_fletcher",
        "title": "Duplicate Person Guardrail: 'Ben Fletcher'",
        "badge": "Identity Integrity",
        "description": "Preserves unresolved duplicate person candidates rather than fabricating a merge.",
        "expected_status": "needs_resolution",
        "request": {"question_id": "person_to_company", "source": "Ben Fletcher", "target": "Trust Exchange"},
    },
    {
        "id": "no_path_honest_negative",
        "title": "Zero-Confabulation Negative: Trust Exchange ↔ Slicker",
        "badge": "Honest No-Path",
        "description": "Both attend Slush 2026, but event co-attendance is excluded as a bridge — returns insufficient_data.",
        "expected_status": "insufficient_data",
        "request": {"question_id": "company_to_company", "source": "Trust Exchange", "target": "Slicker"},
    },
]


def load_presets_payload() -> dict[str, Any]:
    fixture_path = DOCS_DIR / "contracts" / "cala-fixtures" / "PRESETS_AND_DEMO_CASES.json"
    if fixture_path.is_file():
        try:
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("presets"), list):
                return data
        except (OSError, ValueError):
            pass
    return {"presets": copy.deepcopy(FALLBACK_PRESETS)}


class AnalysisService:
    """Central domain service uniting graph engine, AI composition/audit, Aiven store, Cala & CRACI."""

    def __init__(self, snapshot: dict[str, Any], database: Path | str, composer_endpoint: str | None = None):
        load_dotenv_once()
        self.snapshot = snapshot
        self.engine = QueryEngine(snapshot)
        self.store = AnalysisStore(database)
        self.composer_endpoint = composer_endpoint
        self.cala_client = CalaLiveClient(snapshot, store=self.store)
        self.craci_client = CraciProvenanceClient(self.engine)

    def _validate_and_prepare(
        self,
        request: Any,
        *,
        refresh_arg: bool = False,
        default_template: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object")

        question_id = request.get("question_id")
        if not isinstance(question_id, str) or question_id not in QUESTION_SPECS:
            raise ValueError("question_id must identify one of the four fixed questions")

        spec = QUESTION_SPECS[question_id]
        entity_fields = set(spec["fields"])
        id_fields = {f + "_id" for f in entity_fields}
        optional_null_id_fields = {"source_id", "target_id", "company_id"}
        option_fields = {"refresh", "composer_mode", "include_cala_live"}

        permitted = {"question_id"} | entity_fields | id_fields | option_fields
        # Allow explicit null values on unused *_id slots sent by generic UI forms
        unexpected = {
            k
            for k in request
            if k not in permitted and not (k in optional_null_id_fields and request.get(k) is None)
        }
        if unexpected:
            raise ValueError("Unexpected request fields: " + ", ".join(sorted(unexpected)))

        req_refresh = request.get("refresh", False)
        if req_refresh is not None and not isinstance(req_refresh, bool):
            raise ValueError("refresh must be a boolean")
        effective_refresh = bool(refresh_arg or req_refresh)

        inc_cala_live = request.get("include_cala_live", False)
        if inc_cala_live is not None and not isinstance(inc_cala_live, bool):
            raise ValueError("include_cala_live must be a boolean")
        effective_cala_live = bool(inc_cala_live)

        raw_composer_mode = request.get("composer_mode")
        if raw_composer_mode is not None and not isinstance(raw_composer_mode, str):
            raise ValueError("composer_mode must be a string")
        effective_composer_mode = resolve_effective_composer_mode(
            raw_composer_mode,
            default_template=(default_template and raw_composer_mode is None),
        )

        canonical: dict[str, Any] = {"question_id": question_id}
        all_resolved = True
        for field, entity_type in spec["fields"].items():
            raw_id_val = request.get(field + "_id")
            raw_name_val = request.get(field)
            value = raw_id_val if raw_id_val is not None else raw_name_val
            if not isinstance(value, str) or not value.strip() or len(value) > 300:
                raise ValueError(field + " must be a name or a selected entity ID")
            resolution = self.engine.resolve(value.strip(), entity_type)
            if resolution.get("status") == "resolved":
                canonical[field + "_id"] = resolution["entity"]["id"]
            else:
                all_resolved = False

        cache_key = None
        if all_resolved:
            cache_description = {
                "request": canonical,
                "graph_version": self.snapshot["graph_version"],
                "pipeline_version": PIPELINE_VERSION,
                "query_policy_version": QUERY_POLICY_VERSION,
                "prompt_version": PROMPT_VERSION,
                "composer_endpoint": self.composer_endpoint,
                "composer_mode": effective_composer_mode,
                "include_cala_live": effective_cala_live,
            }
            cache_key = hashlib.sha256(
                json.dumps(cache_description, sort_keys=True).encode()
            ).hexdigest()

        engine_args = {
            k: v
            for k, v in request.items()
            if k in (entity_fields | id_fields) and v is not None
        }
        if all_resolved:
            engine_args.update({k: v for k, v in canonical.items() if k != "question_id"})

        return {
            "question_id": question_id,
            "canonical": canonical,
            "all_resolved": all_resolved,
            "cache_key": cache_key,
            "refresh": effective_refresh,
            "composer_mode": effective_composer_mode,
            "include_cala_live": effective_cala_live,
            "engine_args": engine_args,
        }

    def _attach_live_cala_if_requested(self, response: dict[str, Any], include_cala_live: bool) -> None:
        if not include_cala_live:
            response.setdefault("cala_live_enrichment", None)
            return
        resolved = response.get("resolved_entities") or {}
        enrichments: dict[str, Any] = {}
        for slot_name, ent in resolved.items():
            if isinstance(ent, dict) and ent.get("id"):
                enrichments[slot_name] = self.cala_client.enrich(ent["id"])
        response["cala_live_enrichment"] = enrichments or None

    def _finalize_and_persist(
        self,
        request: dict[str, Any],
        response: dict[str, Any],
        *,
        question_id: str,
        cache_key: str | None,
        started: float,
    ) -> dict[str, Any]:
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        response.setdefault("resolution", None)
        response.setdefault("groups", None)
        response.setdefault("attendance_unverified", None)
        response.setdefault("cala_live_enrichment", None)
        response.update(
            {
                "schema_version": "2.0",
                "run_id": str(uuid.uuid4()),
                "question_id": question_id,
                "original_request": request,
                "graph_version": self.snapshot["graph_version"],
                "pipeline_version": PIPELINE_VERSION,
                "query_policy_version": QUERY_POLICY_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "cached": False,
                "elapsed_ms": elapsed,
                "storage_meta": {
                    "backend": self.store.backend_name,
                    "cache_layer": self.store.cache_layer_name,
                    "cached": False,
                    "elapsed_ms": elapsed,
                },
            }
        )
        self.store.save(request, response, cache_key)
        return response

    def analyze(
        self,
        request: dict[str, Any],
        refresh: bool = False,
        *,
        default_template: bool = True,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        prep = self._validate_and_prepare(
            request,
            refresh_arg=refresh,
            default_template=default_template,
        )
        cache_key = prep["cache_key"]
        if cache_key and not prep["refresh"]:
            cached = self.store.cached(cache_key)
            if cached:
                cached["cached"] = True
                if isinstance(cached.get("storage_meta"), dict):
                    cached["storage_meta"]["cached"] = True
                cached["submitted_inputs"] = request
                cached["request_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
                return cached

        response = self.engine.run(prep["question_id"], **prep["engine_args"])
        if self.composer_endpoint:
            response = compose(response, self.composer_endpoint)
        response = enrich_analysis_with_ai(response, composer_mode=prep["composer_mode"])
        self._attach_live_cala_if_requested(response, prep["include_cala_live"])
        return self._finalize_and_persist(
            request,
            response,
            question_id=prep["question_id"],
            cache_key=cache_key,
            started=started,
        )

    def analyze_stream(self, request: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield live SSE `(event_type, data_dict)` pipeline stages for `POST /api/analyses/stream`."""
        started = time.perf_counter()

        def _ms() -> float:
            return round((time.perf_counter() - started) * 1000, 2)

        yield (
            "stage",
            {
                "stage": "resolving",
                "status": "running",
                "message": "Resolving canonical Slush & Cala identities...",
                "elapsed_ms": _ms(),
            },
        )

        prep = self._validate_and_prepare(request, refresh_arg=False, default_template=False)
        cache_key = prep["cache_key"]

        if cache_key and not prep["refresh"]:
            cached = self.store.cached(cache_key)
            if cached:
                cached["cached"] = True
                if isinstance(cached.get("storage_meta"), dict):
                    cached["storage_meta"]["cached"] = True
                cached["submitted_inputs"] = request
                cached["request_elapsed_ms"] = _ms()
                yield (
                    "stage",
                    {
                        "stage": "cache_check",
                        "status": "hit",
                        "cache_layer": self.store.cache_layer_name,
                        "message": f"Canonical cache hit via {self.store.cache_layer_name}.",
                        "elapsed_ms": _ms(),
                    },
                )
                yield (
                    "stage",
                    {
                        "stage": "complete",
                        "status": "done",
                        "run_id": cached["run_id"],
                        "elapsed_ms": _ms(),
                        "analysis": cached,
                    },
                )
                return

        yield (
            "stage",
            {
                "stage": "cache_check",
                "status": "miss",
                "cache_layer": self.store.cache_layer_name,
                "message": f"Checking {self.store.cache_layer_name} / canonical versioned cache...",
                "elapsed_ms": _ms(),
            },
        )

        traversable_cnt = (
            (self.snapshot.get("manifest") or {}).get("counts", {}).get("traversable_edges", 933)
        )
        yield (
            "stage",
            {
                "stage": "traversing",
                "status": "running",
                "message": f"Traversing {traversable_cnt} verified assertions (excluding event/industry hubs)...",
                "elapsed_ms": _ms(),
            },
        )

        response = self.engine.run(prep["question_id"], **prep["engine_args"])
        visited = (response.get("coverage") or {}).get("visited_nodes", len((response.get("graph") or {}).get("nodes") or []))
        path_count = len((response.get("graph") or {}).get("paths") or [])

        yield (
            "stage",
            {
                "stage": "ranking",
                "status": "running",
                "message": "Ranking paths by primary-document provenance, hop cost & hub penalty...",
                "visited_nodes": visited,
                "path_count": path_count,
                "elapsed_ms": _ms(),
            },
        )

        eff_mode = prep["composer_mode"]
        if eff_mode in {"gemini", "gemini_gemma_audit"} and response.get("results"):
            yield (
                "stage",
                {
                    "stage": "composing_gemini",
                    "status": "running",
                    "model": get_gemini_model(),
                    "message": "Synthesizing citation-locked claims & Slush meeting brief with Gemini...",
                    "elapsed_ms": _ms(),
                },
            )
        else:
            yield (
                "stage",
                {
                    "stage": "composing_gemini",
                    "status": "skipped",
                    "model": get_gemini_model() if eff_mode != "gemma" else get_gemma_model(),
                    "message": (
                        "Synthesizing grounded open-weight brief with Gemma..."
                        if eff_mode == "gemma"
                        else "Composing deterministic evidence-locked meeting brief..."
                    ),
                    "elapsed_ms": _ms(),
                },
            )

        if self.composer_endpoint:
            response = compose(response, self.composer_endpoint)
        response = enrich_analysis_with_ai(response, composer_mode=eff_mode)

        yield (
            "stage",
            {
                "stage": "auditing_gemma",
                "status": "running" if eff_mode == "gemini_gemma_audit" else "skipped",
                "model": get_gemma_model() if gemma_is_configured() else "deterministic-entailment-guard-v2.1",
                "message": "Auditing claim entailment & zero-confabulation rules...",
                "elapsed_ms": _ms(),
            },
        )

        self._attach_live_cala_if_requested(response, prep["include_cala_live"])

        yield (
            "stage",
            {
                "stage": "persisting_aiven",
                "status": "running",
                "backend": self.store.backend_name,
                "message": f"Persisting immutable run & evidence package to {self.store.backend_name}...",
                "elapsed_ms": _ms(),
            },
        )

        final_resp = self._finalize_and_persist(
            request,
            response,
            question_id=prep["question_id"],
            cache_key=cache_key,
            started=started,
        )

        yield (
            "stage",
            {
                "stage": "complete",
                "status": "done",
                "run_id": final_resp["run_id"],
                "elapsed_ms": _ms(),
                "analysis": final_resp,
            },
        )

    def health_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "graph_version": self.snapshot["graph_version"],
            "pipeline_version": PIPELINE_VERSION,
            "query_policy_version": QUERY_POLICY_VERSION,
            "capabilities": {
                "gemini": gemini_is_configured(),
                "gemma": gemma_is_configured(),
                "aiven_pg": self.store.aiven_pg_connected,
                "aiven_valkey": self.store.aiven_valkey_connected,
                "craci": True,
                "craci_cloud": craci_api_is_configured(),
                "cala_live": cala_live_is_configured(),
            },
        }

    def infrastructure_status_payload(self) -> dict[str, Any]:
        store_stats = self.store.status_report()
        counts = (self.snapshot.get("manifest") or {}).get("counts") or {}
        return {
            "status": "ok",
            "storage": store_stats["storage"],
            "cache": store_stats["cache"],
            "models": MODEL_TELEMETRY.snapshot(),
            "cala": {
                "snapshot_loaded": bool(self.snapshot.get("nodes")),
                "snapshot_nodes": counts.get("nodes", len(self.snapshot.get("nodes") or {})),
                "snapshot_traversable_edges": counts.get("traversable_edges", len(getattr(self.engine, "edges", {}))),
                "live_api_configured": cala_live_is_configured(),
            },
            "craci": {
                "api_configured": craci_api_is_configured(),
                "mode": "craci_api_live" if craci_api_is_configured() else "verified_workspace_snapshot",
                "workflow_runner_label": "craci",
            },
        }


def build_default_service(
    snapshot_path: Path | str | None = None,
    database_path: Path | str | None = None,
) -> AnalysisService:
    load_dotenv_once()
    snapshot = ensure_snapshot(snapshot_path=snapshot_path, data_dir=DATA_DIR)
    db_file = Path(database_path) if database_path else (DATA_DIR / "analyses.sqlite3")
    composer_url = (os.environ.get("CALA_DEMO_COMPOSER_URL") or "").strip() or None
    return AnalysisService(snapshot, db_file, composer_endpoint=composer_url)
