"""Live Cala `/v1` Structured Entity Enrichment Client (`cala_live_enrichment`).

Follows `docs/contracts/cala-fixtures/CALA_LIVE_QUERY_SPEC.md` and `API_CONTRACT.md` §3.9:
- Base URL: `https://api.cala.ai/v1` with `X-API-KEY` header (never logged or echoed).
- Timeout: 180.0s with at most 1 retry on timeout/504; ZERO retries on HTTP 402 or 429.
- Structured-first workflow: Seed UUID -> `GET /entities/{id}/introspection` -> `POST /entities/{id}`.
- Strict provenance normalization (`publisher`, `url`, `date`) and zero confabulation on failure.
"""

from __future__ import annotations

import copy
import os
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

try:
    from .investor_registry import get_investor_registry
except ImportError:
    from investor_registry import get_investor_registry


UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

ALLOWED_PROPERTIES = [
    "name",
    "legal_name",
    "aliases",
    "website",
    "description",
    "headquarters_address",
    "registered_address",
    "founding_date",
    "operational_status",
    "employee_count",
    "employee_count_range",
    "hq_country",
    "founded_year",
]

PROPERTY_LABELS = {
    "name": "Canonical Name",
    "legal_name": "Registered Legal Name",
    "aliases": "Known Aliases",
    "website": "Official Website",
    "description": "Verified Description",
    "headquarters_address": "Headquarters Address",
    "registered_address": "Registered Address",
    "founding_date": "Founding Date",
    "operational_status": "Operational Status",
    "employee_count": "Employee Count",
    "employee_count_range": "Employee Range",
    "hq_country": "HQ Country",
    "founded_year": "Founded Year",
}

ALLOWED_RELATIONSHIPS = {
    "FOUNDED",
    "IS_CEO_OF",
    "IS_CTO_OF",
    "IS_CFO_OF",
    "IS_COO_OF",
    "IS_CSO_OF",
    "IS_CMO_OF",
    "IS_CCO_OF",
    "IS_BOARD_MEMBER_OF",
    "IS_MANAGING_DIRECTOR_OF",
    "IS_VICEPRESIDENT_OF",
    "ADVISES",
    "IS_ADVISOR_OF",
    "WORKS_AT",
    "IS_MEMBER_OF",
    "INVESTED_IN",
    "IS_DIRECT_OWNER_OF",
    "IS_ULTIMATE_PARENT_OF",
    "IS_BENEFICIARY_OWNER_OF",
    "IS_CONTROL_PERSON_OF",
    "PARTICIPATES_IN_FUNDING_ROUND",
    "OWNS",
    "ACQUIRED",
}


def cala_live_is_configured() -> bool:
    return bool((os.environ.get("CALA_API_KEY") or "").strip())


def _host(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value if "://" in value else "https://" + value)
        return (parsed.hostname or "").casefold().removeprefix("www.") or None
    except ValueError:
        return None


def _normalize_sources(raw_sources: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_sources, list):
        return []
    out: list[dict[str, Any]] = []
    seen = set()
    for src in raw_sources:
        if not isinstance(src, dict):
            continue
        doc = src.get("document") or src.get("url")
        if isinstance(doc, dict):
            url = doc.get("url") or doc.get("endpoint")
            pub = src.get("name") or src.get("publisher") or doc.get("publisher") or _host(url) or "Cala Source"
        else:
            url = doc
            pub = src.get("name") or src.get("publisher") or _host(url) or "Cala Source"
        if not isinstance(url, str) or not url.strip():
            continue
        date = src.get("date") or src.get("published_time") or src.get("checked_at")
        entry: dict[str, Any] = {
            "publisher": str(pub),
            "url": url.strip(),
            "date": str(date) if date else None,
        }
        if src.get("source_rank"):
            entry["source_rank"] = src["source_rank"]
        sig = (entry["publisher"], entry["url"], entry["date"])
        if sig not in seen:
            seen.add(sig)
            out.append(entry)
    return out


class CalaLiveClient:
    """Resilient 180s-timeout Cala REST `/v1` client with strict provenance pass-through."""

    def __init__(self, snapshot: dict[str, Any], store: Any = None) -> None:
        self.snapshot = snapshot
        self.nodes = snapshot.get("nodes") or {}
        self.store = store
        self.investor_registry = get_investor_registry()
        self._payment_required_tripped = False

    def _base_url(self) -> str:
        return (os.environ.get("CALA_BASE_URL") or "https://api.cala.ai/v1").rstrip("/")

    def _timeout(self) -> float:
        try:
            return max(5.0, float(os.environ.get("CALA_TIMEOUT_SECONDS") or "180.0"))
        except ValueError:
            return 180.0

    def _resolve_local_seed(self, entity_id: str) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any] | None]:
        """Return (entity_name, cala_uuid, node_dict, investor_match) from offline verified registries."""
        node = self.nodes.get(entity_id)
        investor_match = self.investor_registry.match_node(node) if node else None
        entity_name = node.get("name") if isinstance(node, dict) else None

        cala_uuid = None
        if entity_id.startswith("cala:"):
            candidate = entity_id.split("cala:", 1)[1]
            if UUID_RE.match(candidate):
                cala_uuid = candidate
        elif UUID_RE.match(entity_id):
            cala_uuid = entity_id
            if entity_id in self.investor_registry.by_cala_id:
                investor_match = dict(self.investor_registry.by_cala_id[entity_id])
                entity_name = entity_name or investor_match.get("cala_name")

        if not cala_uuid and isinstance(node, dict):
            cids = (node.get("source_ids") or {}).get("cala") or []
            for cid in cids:
                if isinstance(cid, str) and UUID_RE.match(cid):
                    cala_uuid = cid
                    break

        if not cala_uuid and investor_match and UUID_RE.match(str(investor_match.get("cala_id") or "")):
            cala_uuid = investor_match["cala_id"]

        return entity_name, cala_uuid, node, investor_match

    def _request_with_policy(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any] | list[Any] | None, str | None]:
        """Execute Cala `/v1` call with 180s timeout and at-most-once timeout retry."""
        url = f"{self._base_url()}{path}"
        headers = {"X-API-KEY": api_key, "Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        timeout = self._timeout()
        attempts = 0
        while attempts < 2:
            attempts += 1
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(method, url, headers=headers, params=params, json=json_body)
                if resp.status_code == 504 and attempts == 1:
                    continue
                if resp.status_code == 504:
                    return 504, None, "timeout"
                if resp.status_code == 402:
                    self._payment_required_tripped = True
                    return 402, None, "payment_required"
                if resp.status_code == 429:
                    return 429, None, "rate_limited"
                if resp.status_code in (401, 403) or resp.status_code >= 500:
                    return resp.status_code, None, "unavailable"
                if resp.status_code == 404:
                    return 404, None, "not_mapped"
                if resp.status_code != 200:
                    return resp.status_code, None, "unavailable"
                return 200, resp.json(), None
            except httpx.TimeoutException:
                if attempts == 1:
                    continue
                return 0, None, "timeout"
            except Exception:
                return 0, None, "unavailable"
        return 0, None, "timeout"

    def enrich(self, entity_id: str, *, refresh: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        entity_name, cala_uuid, node, investor_match = self._resolve_local_seed(entity_id)

        def _envelope(status: str, message: str, **extra: Any) -> dict[str, Any]:
            out: dict[str, Any] = {
                "status": status,
                "entity_id": entity_id,
                "entity_name": entity_name or entity_id,
                "cala_uuid": cala_uuid,
                "namespace": "cala_live_enrichment",
                "cached": False,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "message": message,
                "introspection": None,
                "verified_facts": [],
                "verified_relationships": [],
            }
            if investor_match:
                out["cala_verified_investor_match"] = investor_match
            out.update(extra)
            return out

        api_key = (os.environ.get("CALA_API_KEY") or "").strip()
        if not api_key:
            return _envelope(
                "unconfigured",
                "CALA_API_KEY is not configured. Serving verified offline snapshot & audited Slush investor registry only.",
            )

        cache_ns_key = f"cala_live:{entity_id}"
        if not refresh and self.store is not None and hasattr(self.store, "kv_get"):
            cached_payload = self.store.kv_get(cache_ns_key)
            if isinstance(cached_payload, dict) and cached_payload.get("status") == "ok":
                copied = copy.deepcopy(cached_payload)
                copied["cached"] = True
                copied["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                return copied

        if self._payment_required_tripped and not refresh:
            return _envelope(
                "payment_required",
                "Live Cala API returned HTTP 402 (Insufficient Balance). Showing verified offline snapshot & investor audit facts only; zero unverified fallback was used.",
            )

        # Step 1: Live entity_search only if UUID is not already known from snapshot or investor registry
        if not cala_uuid:
            if not entity_name:
                return _envelope(
                    "not_mapped",
                    "Entity ID is not in the loaded snapshot and is not a Cala UUID; live lookup skipped to prevent confabulation.",
                )
            etype = node.get("entity_type") if isinstance(node, dict) else None
            params: dict[str, Any] = {"name": entity_name, "limit": 5}
            if etype in ("Person", "Company", "Organization"):
                params["entity_types"] = etype
            _, search_data, err_status = self._request_with_policy("GET", "/entities", api_key=api_key, params=params)
            if err_status:
                return _envelope(err_status, self._status_message(err_status))
            items = search_data.get("results") if isinstance(search_data, dict) else (search_data if isinstance(search_data, list) else [])
            exact_hits = [
                it for it in (items or [])
                if isinstance(it, dict) and str(it.get("name") or "").strip().casefold() == entity_name.strip().casefold()
            ]
            if len(exact_hits) == 1 and UUID_RE.match(str(exact_hits[0].get("id") or "")):
                cala_uuid = str(exact_hits[0]["id"])
            else:
                return _envelope(
                    "not_mapped",
                    "No unique corroborated Cala UUID was established for this entity; halted live enrichment rather than guessing.",
                )

        # Step 2: Schema Introspection (`GET /v1/entities/{cala_uuid}/introspection`)
        _, intro_data, err_status = self._request_with_policy(
            "GET",
            f"/entities/{cala_uuid}/introspection",
            api_key=api_key,
        )
        if err_status:
            return _envelope(err_status, self._status_message(err_status))

        intro_dict = intro_data if isinstance(intro_data, dict) else {}
        raw_props = intro_dict.get("properties") or []
        if isinstance(raw_props, dict):
            avail_props = list(raw_props.keys())
        elif isinstance(raw_props, list):
            avail_props = [p.get("name") if isinstance(p, dict) else str(p) for p in raw_props]
        else:
            avail_props = []

        rels_meta = intro_dict.get("relationships") or {}
        inc_raw = rels_meta.get("incoming") or []
        out_raw = rels_meta.get("outgoing") or []
        inc_types = list(inc_raw.keys()) if isinstance(inc_raw, dict) else [str(x) for x in inc_raw if isinstance(x, str)]
        out_types = list(out_raw.keys()) if isinstance(out_raw, dict) else [str(x) for x in out_raw if isinstance(x, str)]

        projected_props = [p for p in ALLOWED_PROPERTIES if p in avail_props] or ["name", "website", "description"]
        proj_inc = {r: {"limit": 10, "offset": 0} for r in inc_types if r in ALLOWED_RELATIONSHIPS}
        proj_out = {r: {"limit": 10, "offset": 0} for r in out_types if r in ALLOWED_RELATIONSHIPS}

        projection_body: dict[str, Any] = {"properties": projected_props}
        if proj_inc or proj_out:
            projection_body["relationships"] = {}
            if proj_inc:
                projection_body["relationships"]["incoming"] = proj_inc
            if proj_out:
                projection_body["relationships"]["outgoing"] = proj_out

        # Step 3: Projected Entity Retrieval (`POST /v1/entities/{cala_uuid}`)
        _, entity_data, err_status = self._request_with_policy(
            "POST",
            f"/entities/{cala_uuid}",
            api_key=api_key,
            json_body=projection_body,
        )
        if err_status:
            return _envelope(err_status, self._status_message(err_status))

        ent = entity_data if isinstance(entity_data, dict) else {}
        entity_name = entity_name or ent.get("name") or entity_id

        verified_facts: list[dict[str, Any]] = []
        ent_props = ent.get("properties") or {}
        if isinstance(ent_props, dict):
            for field_name, field_obj in ent_props.items():
                if isinstance(field_obj, dict):
                    val = field_obj.get("value")
                    sources = _normalize_sources(field_obj.get("sources"))
                else:
                    val = field_obj
                    sources = []
                if val is None or val == "" or val == []:
                    continue
                if not sources:
                    continue
                verified_facts.append(
                    {
                        "field": field_name,
                        "label": PROPERTY_LABELS.get(field_name, field_name.replace("_", " ").title()),
                        "value": val,
                        "sources": sources,
                    }
                )

        verified_relationships: list[dict[str, Any]] = []
        ent_rels = ent.get("relationships") or {}
        if isinstance(ent_rels, dict):
            for direction in ("incoming", "outgoing"):
                dir_block = ent_rels.get(direction) or {}
                if not isinstance(dir_block, dict):
                    continue
                for predicate, rel_items in dir_block.items():
                    if predicate not in ALLOWED_RELATIONSHIPS:
                        continue
                    rows = rel_items.get("results") if isinstance(rel_items, dict) else (rel_items if isinstance(rel_items, list) else [])
                    for row in rows or []:
                        if not isinstance(row, dict):
                            continue
                        peer = row.get("entity") or row.get("peer") or row
                        sources = _normalize_sources(row.get("sources") or (row.get("properties") or {}).get("sources"))
                        # Discard unattributed relationship assertions per CALA_LIVE_QUERY_SPEC §6
                        if not sources:
                            continue
                        verified_relationships.append(
                            {
                                "predicate": predicate,
                                "direction": direction,
                                "peer_name": peer.get("name") or peer.get("id") or "Unknown",
                                "peer_cala_id": peer.get("id"),
                                "sources": sources,
                            }
                        )

        result = _envelope(
            "ok",
            "Verified live facts retrieved from Cala Knowledge Graph API (/v1).",
            introspection={
                "available_attributes": sorted(set(avail_props)),
                "available_relationships": sorted(set(inc_types) | set(out_types)),
            },
            verified_facts=verified_facts,
            verified_relationships=verified_relationships,
        )
        if self.store is not None and hasattr(self.store, "kv_set"):
            self.store.kv_set(cache_ns_key, result, ttl_seconds=86400)
        return result

    @staticmethod
    def _status_message(status: str) -> str:
        messages = {
            "payment_required": (
                "Live Cala API returned HTTP 402 (Insufficient Balance). Showing verified offline snapshot "
                "& investor audit facts only; zero unverified fallback was used."
            ),
            "rate_limited": (
                "Live Cala API returned HTTP 429 (Rate Limited). Halted live lookup without retry; "
                "showing offline verified snapshot only."
            ),
            "timeout": (
                "Live Cala API timed out at the 180s client limit (after 1 retry). Halted cleanly with zero confabulation."
            ),
            "not_mapped": (
                "Entity was not found or uniquely corroborated in Cala /v1; halted cleanly."
            ),
            "unavailable": (
                "Live Cala API (/v1) is currently unreachable or rejected credentials (check https://console.cala.ai/api-keys). "
                "Showing offline verified snapshot only."
            ),
        }
        return messages.get(status, "Live Cala enrichment halted; showing offline verified snapshot.")
