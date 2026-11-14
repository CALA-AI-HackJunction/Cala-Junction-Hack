"""Verified Slush 2026 Investor <-> Cala UUID registry loader.

Loads `docs/cala_investors_verification.json` (791 CONFIRMED investor records)
to attach `cala_verified_investor_match` metadata on matching Company/Organization
nodes without mutating graph traversal hop rules or snapshot hashes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _norm(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def _host(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value if "://" in value else "https://" + value)
        return (parsed.hostname or "").casefold().removeprefix("www.") or None
    except ValueError:
        return None


class InvestorVerificationRegistry:
    """Read-only index over docs/cala_investors_verification.json."""

    def __init__(self, records: list[dict[str, Any]] | None = None):
        self.by_cala_id: dict[str, dict[str, Any]] = {}
        self.by_name_and_host: dict[tuple[str, str], dict[str, Any]] = {}
        self.by_unique_name: dict[str, list[dict[str, Any]]] = {}
        self.confirmed_count = 0

        for row in records or []:
            if not isinstance(row, dict) or row.get("status") != "CONFIRMED":
                continue
            cala_id = row.get("cala_id")
            if not isinstance(cala_id, str) or not cala_id.strip():
                continue
            self.confirmed_count += 1
            entry = self._format_match(row)
            self.by_cala_id[cala_id.strip()] = entry

            for candidate_name in (row.get("company_name"), row.get("cala_name")):
                n_key = _norm(candidate_name)
                if not n_key:
                    continue
                self.by_unique_name.setdefault(n_key, []).append((row, entry))
                h = _host(row.get("website"))
                if h:
                    self.by_name_and_host[(n_key, h)] = entry

    @staticmethod
    def _format_match(row: dict[str, Any]) -> dict[str, Any]:
        idx = row.get("idx", 0)
        return {
            "cala_id": row["cala_id"],
            "cala_name": row.get("cala_name") or row.get("company_name"),
            "cala_entity_type": row.get("cala_type") or "Company",
            "cala_type": row.get("cala_type") or "Company",
            "cala_description": row.get("cala_desc"),
            "cala_desc": row.get("cala_desc"),
            "company_type": row.get("company_type"),
            "country": row.get("country"),
            "website": row.get("website"),
            "verification_status": "CONFIRMED",
            "match_score": row.get("best_score"),
            "best_score": row.get("best_score"),
            "namespace": "cala_verified_investor_match",
            "sources": [
                {
                    "publisher": "Cala Entity Verification Audit (Slush 2026 Investors)",
                    "url": f"docs/cala_investors_verification.json#idx={idx}",
                    "date": "2026-11-14",
                }
            ],
        }

    def match_node(self, node: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(node, dict):
            return None
        entity_type = str(node.get("entity_type") or "").casefold()
        if entity_type not in {"company", "organization", "organisation", "investor", "fund"}:
            return None

        # 1. Direct Cala ID match
        cala_ids = (node.get("source_ids") or {}).get("cala") or []
        for cid in cala_ids:
            if cid in self.by_cala_id:
                return dict(self.by_cala_id[cid])
        node_id = str(node.get("id") or "")
        if node_id.startswith("cala:"):
            raw_cid = node_id.split("cala:", 1)[1]
            if raw_cid in self.by_cala_id:
                return dict(self.by_cala_id[raw_cid])

        # Only match real Slush/Cala nodes with source_ids so synthetic test fixtures remain untouched.
        if not node.get("source_ids") and not node_id.startswith(("slush-", "cala:")):
            return None

        props = node.get("properties") or {}
        node_host = _host(props.get("website"))
        names = [node.get("name"), *(node.get("aliases") or [])]

        # 2. Exact normalized name + matching website domain
        if node_host:
            for nm in names:
                n_key = _norm(nm)
                if n_key and (n_key, node_host) in self.by_name_and_host:
                    return dict(self.by_name_and_host[(n_key, node_host)])

        # 3. Unique confirmed Slush investor record with corroborating country or investor company_type
        node_country = str(props.get("country") or props.get("hq_country") or "").strip().upper()
        for nm in names:
            n_key = _norm(nm)
            matches = self.by_unique_name.get(n_key) or []
            if len(matches) == 1:
                raw_row, entry = matches[0]
                row_host = _host(raw_row.get("website"))
                row_country = str(raw_row.get("country") or "").strip().upper()
                if node_host and row_host and node_host == row_host:
                    return dict(entry)
                if not node_host and not row_host and node_country and row_country == node_country:
                    return dict(entry)
                # Slush investor record with exact name in slush_companies
                if node_id.startswith("slush-company:") and (
                    (node_country and row_country == node_country) or not node_country
                ) and (not node_host or not row_host or node_host == row_host):
                    return dict(entry)
        return None


@lru_cache(maxsize=1)
def get_investor_registry(verification_path: str | None = None) -> InvestorVerificationRegistry:
    path = (
        Path(verification_path)
        if verification_path
        else (Path(__file__).resolve().parents[1] / "docs" / "cala_investors_verification.json")
    )
    if not path.is_file():
        return InvestorVerificationRegistry([])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return InvestorVerificationRegistry(data)
    except (OSError, ValueError):
        pass
    return InvestorVerificationRegistry([])
