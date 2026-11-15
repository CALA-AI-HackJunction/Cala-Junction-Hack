"""Bounded, evidence-preserving queries for the four Cala/Slush tasks.

Preserves 100% of the deterministic graph invariants (4 fixed questions, max 4 hops,
exclusion of event/category hubs and unattributed edges, factual edge direction on
reverse traversal, ambiguity preservation, and verified vs unverified Slush attendance)
while adding fast ranked typeahead `suggestions`, `resolution_state`, and optional
`cala_verified_investor_match` profile metadata.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import heapq
import math
import unicodedata
from collections import defaultdict
from typing import Any

try:
    from .investor_registry import get_investor_registry
except ImportError:
    from investor_registry import get_investor_registry


QUESTION_TEMPLATES = {
    "person_to_company": "How is this person connected to this company?",
    "company_to_company": "How are these two companies connected?",
    "company_network": "What professional network surrounds this company?",
    "company_representatives": (
        "Who from this company can I approach at Slush, and what should I know about them?"
    ),
}

COMPANY_TYPES = {
    "company", "organization", "organisation", "investor", "fund",
    "nonprofitorganization", "educationalinstitution",
}
PROFESSIONAL_NODE_TYPES = COMPANY_TYPES | {
    "person", "fundinground", "privatecompanyfundinground",
    "fundingroundtranche", "corporateevent",
}
AFFILIATION_TYPES = {
    "WORKS_AT", "FOUNDED", "AFFILIATED_WITH", "ADVISES", "IS_ADVISOR_OF",
    "IS_BOARD_MEMBER_OF", "IS_CEO_OF", "IS_CTO_OF", "IS_CFO_OF", "IS_COO_OF",
    "IS_CSO_OF", "IS_CMO_OF", "IS_CCO_OF", "IS_CRO_OF", "IS_VICEPRESIDENT_OF",
    "IS_MANAGING_DIRECTOR_OF", "IS_EXECUTIVE_OF", "IS_MEMBER_OF",
}
PROFESSIONAL_TYPES = AFFILIATION_TYPES | {
    "INVESTED_IN", "IS_BENEFICIARY_OWNER_OF", "IS_CONTROL_PERSON_OF",
    "PARTICIPATES_IN_FUNDING_ROUND", "PARTICIPATES_IN_CORPORATE_EVENT",
    "OWNS", "ACQUIRED", "SUBSIDIARY_OF", "IS_SUBSIDIARY_OF",
    "IS_ULTIMATE_PARENT_OF", "IS_DIRECT_OWNER_OF",
    "PARTNER_OF", "PARTNERS_WITH",
}
PERSON_EVENT_STATUSES = {
    "platform_directory", "platform_profile", "announced_speaker",
    "announced_attendee", "reported_in_supplied_slush26_company_profile",
}
PROFILE_FIELDS = (
    "job_title", "public_source_job_title", "headline", "biography",
    "description", "professional_topics", "location_raw", "profile_url",
    "linkedin_url", "personal_website", "website", "work_experience",
    "company_type", "country", "primary_industry",
)


def _norm(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _unique(values):
    return list(dict.fromkeys(values))


def _unwrapped(value):
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def _status_to_resolution_state(status: str) -> str:
    if status == "resolved":
        return "resolved"
    if status == "needs_resolution":
        return "ambiguous"
    return "not_found"


class QueryEngine:
    """Query an immutable normalized snapshot.

    All limits are backend settings. The user supplies only entity names or a
    canonical ID selected from a resolution list, plus a fixed question ID.
    """

    def __init__(self, snapshot: dict, *, max_results=10, max_paths=3,
                 max_hops=4, network_hops=2, max_neighbours=100,
                 max_visited_nodes=5000, max_states=5000):
        self.snapshot = snapshot
        self.nodes = snapshot.get("nodes", {})
        self.evidence = snapshot.get("evidence", {})
        self.manifest = snapshot.get("manifest", {})
        self.max_results = max(1, int(max_results))
        self.max_paths = max(1, int(max_paths))
        self.max_hops = min(4, max(1, int(max_hops)))
        self.network_hops = min(self.max_hops, max(1, int(network_hops)))
        self.max_neighbours = max(1, int(max_neighbours))
        self.max_visited_nodes = max(1, int(max_visited_nodes))
        self.max_states = max(1, int(max_states))
        self.name_index = defaultdict(set)
        self.edges = {}
        self.adj = defaultdict(list)
        self.diagnostics = defaultdict(int)
        self._investor_registry = get_investor_registry()

        for node_id, node in self.nodes.items():
            names = [node.get("name", "")] + list(node.get("aliases") or [])
            for name in names:
                if isinstance(name, str) and _norm(name):
                    self.name_index[_norm(name)].add(node_id)

        for raw in snapshot.get("edges", []):
            edge = copy.deepcopy(raw)
            edge_id, a, b = edge.get("id"), edge.get("source"), edge.get("target")
            if not edge_id or a not in self.nodes or b not in self.nodes:
                self.diagnostics["dangling_or_unidentified_edges"] += 1
                continue
            if edge_id in self.edges:
                self.diagnostics["duplicate_edge_ids"] += 1
                continue
            valid_evidence = _unique(x for x in edge.get("evidence_ids", []) if x in self.evidence)
            if len(valid_evidence) != len(set(edge.get("evidence_ids", []))):
                self.diagnostics["invalid_evidence_references"] += 1
            edge["evidence_ids"] = valid_evidence
            self.edges[edge_id] = edge
            if not self._usable_edge(edge):
                continue
            self.adj[a].append((b, edge_id))
            self.adj[b].append((a, edge_id))

        self.degree = {node_id: len(links) for node_id, links in self.adj.items()}
        for node_id in self.adj:
            self.adj[node_id].sort(key=self._neighbour_key)

        # Precompute fast typeahead search catalog for < 2ms suggestions
        self._search_catalog: list[tuple[str, str, tuple[str, ...], str, int, bool]] = []
        for node_id, node in self.nodes.items():
            typ = _norm(node.get("entity_type"))
            if typ not in (COMPANY_TYPES | {"person"}) or not self._valid_identity(node):
                continue
            nm = _norm(node.get("name", ""))
            if not nm:
                continue
            aliases_norm = tuple(_norm(a) for a in (node.get("aliases") or []) if isinstance(a, str) and _norm(a))
            deg = self.degree.get(node_id, 0)
            is_full = node.get("record_completeness") == "full"
            self._search_catalog.append((node_id, nm, aliases_norm, typ, deg, is_full))

    def _valid_identity(self, node):
        identity = node.get("identity") or {}
        status = _norm(node.get("identity_status") or
                       (identity.get("status") if isinstance(identity, dict) else None))
        return not (node.get("invalid_identity") or status in {"invalid", "unresolved", "rejected"})

    def _type_matches(self, node, entity_type=None):
        typ = _norm(node.get("entity_type"))
        wanted = _norm(entity_type)
        if not wanted:
            return True
        if wanted in COMPANY_TYPES:
            return typ in COMPANY_TYPES
        return typ == wanted

    def _usable_edge(self, edge):
        if not edge.get("traversable", False) or edge.get("type") not in PROFESSIONAL_TYPES:
            return False
        if not edge.get("evidence_ids"):
            self.diagnostics["professional_edges_without_evidence"] += 1
            return False
        if _norm(edge.get("status") or edge.get("review_status")) in {
            "conflict", "conflicted", "disputed", "unsupported", "unresolved", "rejected"
        } or edge.get("conflict"):
            return False
        for endpoint in (edge["source"], edge["target"]):
            node = self.nodes[endpoint]
            if _norm(node.get("entity_type")) not in PROFESSIONAL_NODE_TYPES or not self._valid_identity(node):
                return False
        cost = edge.get("hop_cost", 1)
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 1:
            self.diagnostics["invalid_hop_costs"] += 1
            return False
        return True

    def _node_origins(self, node_id: str) -> list[str]:
        node = self.nodes[node_id]
        source_ids = node.get("source_ids") or {}
        origins = []
        if "cala" in source_ids or node_id.startswith("cala:"):
            origins.append("cala")
        if "slush" in source_ids or node_id.startswith(("slush-company:", "slush-person:")):
            origins.append("slush")
        if "slush_reference" in source_ids or node_id.startswith("slush-organization:"):
            origins.append("slush_reference")
        if "slush_company_attendee" in source_ids or node_id.startswith("slush-person-attendee:"):
            origins.append("slush_company_attendee")
        if not origins and source_ids:
            origins.extend(sorted(source_ids.keys()))
        return _unique(origins)

    def _suggestion_subtitle(self, node_id: str) -> str:
        node = self.nodes[node_id]
        props = node.get("properties") or {}
        parts = []
        origins = self._node_origins(node_id)
        if "cala" in origins and "slush" in origins:
            parts.append("Cala + Slush Verified")
        elif "cala" in origins:
            parts.append(f"Cala {node.get('entity_type') or 'Entity'}")
        elif "slush_reference" in origins:
            parts.append("Slush Work-History Reference")
        elif "slush" in origins:
            parts.append(f"Slush {node.get('entity_type') or 'Entity'}")

        role_or_type = _unwrapped(props.get("job_title") or props.get("headline") or props.get("company_type"))
        if isinstance(role_or_type, str) and role_or_type.strip():
            parts.append(role_or_type.strip()[:48])

        deg = self.degree.get(node_id, 0)
        if deg > 0:
            parts.append(f"{deg} verified link{'s' if deg != 1 else ''}")
        elif node.get("record_completeness") == "stub":
            parts.append("stub record")
        return " · ".join(parts) if parts else str(node.get("entity_type") or "")

    def _suggestion_item(self, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        origins = self._node_origins(node_id)
        deg = self.degree.get(node_id, 0)
        item = {
            "id": node_id,
            "name": node.get("name", node_id),
            "entity_type": node.get("entity_type"),
            "record_completeness": node.get("record_completeness", "unknown"),
            "origin_badges": origins,
            "origins": origins,
            "traversable_degree": deg,
            "subtitle": self._suggestion_subtitle(node_id),
        }
        investor_match = self._investor_registry.match_node(node)
        if investor_match:
            item["cala_verified_investor_match"] = investor_match
        return item

    def _compute_suggestions(self, query_norm: str, entity_type: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
        if not query_norm:
            return []
        wanted = _norm(entity_type)
        want_company = wanted in COMPANY_TYPES if wanted else False

        scored: list[tuple[int, int, int, str, str]] = []
        seen_ids: set[str] = set()

        for node_id, nm, aliases_norm, typ, deg, is_full in self._search_catalog:
            if wanted:
                if want_company and typ not in COMPANY_TYPES:
                    continue
                if not want_company and typ != wanted:
                    continue

            tier = None
            if nm == query_norm or query_norm in aliases_norm:
                tier = 0
            elif nm.startswith(query_norm) or any(a.startswith(query_norm) for a in aliases_norm):
                tier = 1
            elif any(w.startswith(query_norm) for w in nm.split()):
                tier = 2
            elif query_norm in nm or any(query_norm in a for a in aliases_norm):
                tier = 3

            if tier is not None:
                scored.append((tier, -deg, 0 if is_full else 1, nm, node_id))
                seen_ids.add(node_id)

        if len(scored) < limit and len(query_norm) >= 3:
            close_keys = difflib.get_close_matches(query_norm, list(self.name_index.keys()), n=min(limit, 12), cutoff=0.65)
            for key in close_keys:
                for node_id in self.name_index[key]:
                    if node_id in seen_ids:
                        continue
                    node = self.nodes[node_id]
                    if not self._type_matches(node, entity_type) or not self._valid_identity(node):
                        continue
                    deg = self.degree.get(node_id, 0)
                    is_full = node.get("record_completeness") == "full"
                    scored.append((4, -deg, 0 if is_full else 1, _norm(node.get("name", "")), node_id))
                    seen_ids.add(node_id)

        scored.sort()
        return [self._suggestion_item(row[4]) for row in scored[:limit]]

    def _node_evidence(self, node):
        ids = list(node.get("evidence_ids") or [])
        for participation in node.get("participation") or []:
            ids.extend(participation.get("evidence_ids") or [])
        for value in (node.get("properties") or {}).values():
            if isinstance(value, dict):
                ids.extend(value.get("evidence_ids") or [])
        return _unique(x for x in ids if x in self.evidence)

    def _node_view(self, node_id, *, profile=False):
        node = self.nodes[node_id]
        participation = []
        for row in node.get("participation") or []:
            valid = [x for x in row.get("evidence_ids", []) if x in self.evidence]
            participation.append({**copy.deepcopy(row), "evidence_ids": valid})
        view = {
            "id": node_id,
            "name": node.get("name", node_id),
            "entity_type": node.get("entity_type"),
            "record_completeness": node.get("record_completeness", "unknown"),
            "participation": participation,
            "evidence_ids": self._node_evidence(node),
        }
        if node.get("identity_warnings"):
            view["identity_warnings"] = copy.deepcopy(node["identity_warnings"])
        if profile:
            props = node.get("properties") or {}
            view["profile"] = {key: copy.deepcopy(props[key]) for key in PROFILE_FIELDS
                               if key in props and props[key] is not None}
            view["source_ids"] = copy.deepcopy(node.get("source_ids") or {})
            investor_match = self._investor_registry.match_node(node)
            if investor_match:
                view["cala_verified_investor_match"] = investor_match
                view["profile"]["cala_investor_match"] = investor_match
        return view

    def resolve(self, name, entity_type=None, limit=15):
        """Resolve a unique exact name/alias or canonical ID; otherwise offer candidates + typeahead suggestions."""
        clamped_limit = min(max(int(limit or 15), 1), 50)
        if not isinstance(name, str) or not name.strip():
            return {
                "status": "not_found",
                "resolution_state": "not_found",
                "query": name,
                "entity_type": entity_type,
                "entity": None,
                "candidates": [],
                "suggestions": [],
                "reason": "A nonempty entity name or canonical ID is required.",
            }

        raw_query = name.strip()
        if raw_query in self.nodes:
            node = self.nodes[raw_query]
            if self._type_matches(node, entity_type) and self._valid_identity(node):
                entity_view = self._node_view(raw_query, profile=True)
                return {
                    "status": "resolved",
                    "resolution_state": "resolved",
                    "query": name,
                    "entity_type": entity_type or node.get("entity_type"),
                    "entity": entity_view,
                    "candidates": [],
                    "suggestions": [self._suggestion_item(raw_query)],
                    "match_method": "canonical_id",
                }
            return {
                "status": "not_found",
                "resolution_state": "not_found",
                "query": name,
                "entity_type": entity_type,
                "entity": None,
                "candidates": [],
                "suggestions": [],
                "reason": "The selected ID does not have the required entity type or a usable identity.",
            }

        normalized = _norm(raw_query)
        suggestions = self._compute_suggestions(normalized, entity_type=entity_type, limit=clamped_limit)

        exact = sorted(node_id for node_id in self.name_index.get(normalized, set())
                       if self._type_matches(self.nodes[node_id], entity_type)
                       and self._valid_identity(self.nodes[node_id]))
        if len(exact) == 1:
            resolved_id = exact[0]
            return {
                "status": "resolved",
                "resolution_state": "resolved",
                "query": name,
                "entity_type": entity_type or self.nodes[resolved_id].get("entity_type"),
                "entity": self._node_view(resolved_id, profile=True),
                "candidates": [],
                "suggestions": suggestions or [self._suggestion_item(resolved_id)],
                "match_method": "unique_exact_name_or_alias",
            }
        if exact:
            max_cands = max(20, clamped_limit)
            return {
                "status": "needs_resolution",
                "resolution_state": "ambiguous",
                "query": name,
                "entity_type": entity_type,
                "entity": None,
                "candidates": [self._candidate(x) for x in exact[:max_cands]],
                "candidates_truncated": len(exact) > max_cands,
                "suggestions": suggestions,
                "reason": "Multiple distinct records share this name; select a canonical ID.",
            }

        candidate_keys = [key for key in self.name_index if normalized in key or key in normalized]
        close = difflib.get_close_matches(normalized, list(self.name_index), n=12, cutoff=0.65)
        candidate_ids = set()
        for key in _unique(candidate_keys + close):
            candidate_ids.update(node_id for node_id in self.name_index[key]
                                 if self._type_matches(self.nodes[node_id], entity_type)
                                 and self._valid_identity(self.nodes[node_id]))
        candidates = sorted(candidate_ids, key=lambda x: (
            -difflib.SequenceMatcher(None, normalized, _norm(self.nodes[x].get("name"))).ratio(),
            -self.degree.get(x, 0),
            _norm(self.nodes[x].get("name")),
            x,
        ))[:clamped_limit]
        status = "needs_resolution" if candidates else "not_found"
        return {
            "status": status,
            "resolution_state": _status_to_resolution_state(status),
            "query": name,
            "entity_type": entity_type,
            "entity": None,
            "candidates": [self._candidate(x) for x in candidates],
            "suggestions": suggestions,
            "reason": (
                "No unique exact match; select a suggested identity before graph traversal."
                if candidates else "No matching entity was found in the loaded snapshot."
            ),
        }

    def _candidate(self, node_id):
        view = self._node_view(node_id)
        props = self.nodes[node_id].get("properties") or {}
        origins = self._node_origins(node_id)
        view["origin_badges"] = origins
        view["origins"] = origins
        view["traversable_degree"] = self.degree.get(node_id, 0)
        view["subtitle"] = self._suggestion_subtitle(node_id)
        view["context"] = {key: _unwrapped(props.get(key)) for key in
                           ("job_title", "website", "location_raw", "company_name")
                           if props.get(key) is not None}
        view["affiliations"] = _unique(self.nodes[neighbour].get("name", neighbour)
            for neighbour, edge_id in self.adj.get(node_id, [])
            if self.edges[edge_id]["type"] in AFFILIATION_TYPES
            and self._type_matches(self.nodes[neighbour], "Company"))[:6]
        investor_match = self._investor_registry.match_node(self.nodes[node_id])
        if investor_match:
            view["cala_verified_investor_match"] = investor_match
        return view

    def _edge_quality(self, edge):
        # Heuristic evidence ordering only; not a calibrated confidence score.
        for evidence_id in edge["evidence_ids"]:
            record = self.evidence[evidence_id]
            documents = record.get("source_documents") or []
            if any((isinstance(doc, str) and doc.strip()) or
                   (isinstance(doc, dict) and any(doc.get(k) for k in ("url", "document", "endpoint")))
                   for doc in documents):
                return 2
        return 1

    @staticmethod
    def _temporal_penalty(edge):
        if edge.get("type") == "FOUNDED":
            return 0  # A historical founding fact does not expire.
        return {"current": 0, "undated": 1, "historical": 2}.get(edge.get("temporal_status"), 1)

    def _neighbour_key(self, link):
        neighbour, edge_id = link
        edge = self.edges[edge_id]
        return (-self._edge_quality(edge), self._temporal_penalty(edge),
                self.degree.get(neighbour, 0), _norm(self.nodes[neighbour].get("name")), edge_id)

    def _path_key(self, node_ids, edge_ids):
        if not edge_ids:
            return (-3, 0, 0, 0, ())
        edges = [self.edges[x] for x in edge_ids]
        return (-min(self._edge_quality(x) for x in edges),
                sum(x.get("hop_cost", 1) for x in edges),
                sum(self._temporal_penalty(x) for x in edges),
                sum(math.log1p(self.degree.get(x, 0)) for x in node_ids[1:-1]),
                tuple(edge_ids))

    def _search(self, source_id, target_id=None, *, max_hops=None):
        limit = self.max_hops if max_hops is None else max_hops
        queue = [(self._path_key((source_id,), ()), 0, (source_id,), ())]
        serial = 0
        states = 0
        seen_nodes = {source_id}
        seen_paths = set()
        results = defaultdict(list)
        reasons = set()
        while queue:
            if states >= self.max_states:
                reasons.add("visited_state_budget")
                break
            _, _, node_ids, edge_ids = heapq.heappop(queue)
            states += 1
            last = node_ids[-1]
            cost = sum(self.edges[x].get("hop_cost", 1) for x in edge_ids)
            is_endpoint = (_norm(self.nodes[last].get("entity_type")) in (COMPANY_TYPES | {"person"}))
            if edge_ids and ((target_id is not None and last == target_id) or
                             (target_id is None and is_endpoint)):
                signature = (node_ids, edge_ids)
                if signature not in seen_paths:
                    results[last].append((node_ids, edge_ids))
                    seen_paths.add(signature)
                if target_id is not None and last == target_id:
                    continue
            if cost >= limit:
                continue
            neighbours = self.adj.get(last, [])
            if len(neighbours) > self.max_neighbours:
                reasons.add("neighbour_budget")
            for neighbour, edge_id in neighbours[:self.max_neighbours]:
                if neighbour in node_ids:
                    continue
                new_cost = cost + self.edges[edge_id].get("hop_cost", 1)
                if new_cost > limit:
                    continue
                if neighbour not in seen_nodes and len(seen_nodes) >= self.max_visited_nodes:
                    reasons.add("visited_node_budget")
                    continue
                seen_nodes.add(neighbour)
                new_nodes, new_edges = node_ids + (neighbour,), edge_ids + (edge_id,)
                serial += 1
                heapq.heappush(queue, (self._path_key(new_nodes, new_edges), serial,
                                       new_nodes, new_edges))
        paths_limited = False
        for node_id in results:
            results[node_id].sort(key=lambda item: self._path_key(*item))
            paths_limited = paths_limited or len(results[node_id]) > self.max_paths
            results[node_id] = results[node_id][:self.max_paths]
        coverage = {"max_hops": limit, "visited_nodes": len(seen_nodes),
                    "visited_states": states, "truncated": bool(reasons),
                    "truncation_reasons": sorted(reasons),
                    "path_result_limit_applied": paths_limited}
        return dict(results), coverage

    def _edge_sentence(self, edge):
        source = self.nodes[edge["source"]].get("name", edge["source"])
        target = self.nodes[edge["target"]].get("name", edge["target"])
        predicate = edge["type"]
        labels = {
            "WORKS_AT": "has a documented employment link to",
            "FOUNDED": "founded",
            "AFFILIATED_WITH": "has a documented affiliation with",
            "INVESTED_IN": "has a documented investment in",
            "ADVISES": "has a documented advisory relationship with",
            "IS_ADVISOR_OF": "has a documented advisory relationship with",
            "IS_BOARD_MEMBER_OF": "has a documented board role at",
            "IS_MEMBER_OF": "has a documented membership of",
            "IS_BENEFICIARY_OWNER_OF": "has a documented beneficial-ownership link to",
            "IS_CONTROL_PERSON_OF": "has a documented control-person role at",
            "PARTICIPATES_IN_FUNDING_ROUND": "is recorded as a participant in",
        }
        if predicate in labels:
            relation = labels[predicate]
        elif predicate.startswith("IS_") and predicate.endswith("_OF"):
            relation = "has a documented " + predicate[3:-3].replace("_", " ").lower() + " role at"
        else:
            relation = "is linked by " + predicate.lower().replace("_", " ") + " to"
        suffix = ""
        if predicate != "FOUNDED" and edge.get("temporal_status") == "historical":
            suffix = " (historical relationship)"
        elif predicate != "FOUNDED" and edge.get("temporal_status", "undated") == "undated":
            suffix = " (relationship dates unverified)"
        return f"{source} {relation} {target}{suffix}."

    def _path(self, nodes, edges):
        digest = hashlib.sha256(("|".join(nodes) + "//" + "|".join(edges)).encode()).hexdigest()[:20]
        relations = []
        for index, edge_id in enumerate(edges):
            edge = self.edges[edge_id]
            relations.append({
                "edge_id": edge_id, "source_id": edge["source"], "target_id": edge["target"],
                "predicate": edge["type"], "from_id": nodes[index], "to_id": nodes[index + 1],
                "traversal": "forward" if edge["source"] == nodes[index] else "reverse",
                "evidence_ids": edge["evidence_ids"],
                "temporal_status": edge.get("temporal_status", "undated"),
                "hop_cost": edge.get("hop_cost", 1),
                "statement": self._edge_sentence(edge),
            })
        hop_count = sum(row["hop_cost"] for row in relations)
        reasons = [f"{hop_count} supported relationship step{'s' if hop_count != 1 else ''}",
                   "Every relationship has a preserved evidence record"]
        if all(self._edge_quality(self.edges[x]) == 2 for x in edges):
            reasons.append("Every relationship also has a source-document reference")
        if any(self.edges[x].get("temporal_status") == "historical" for x in edges):
            reasons.append("Includes a historical relationship; no current connection is implied")
        if any(self.edges[x].get("temporal_status", "undated") == "undated" for x in edges):
            reasons.append("Some relationship dates are unverified")
        return {"id": "path:" + digest, "node_ids": list(nodes), "edge_ids": list(edges),
                "hop_count": hop_count, "relations": relations,
                "explanation": " ".join(row["statement"] for row in relations),
                "rank_reasons": reasons}

    def _participation(self, node_id):
        node = self.nodes[node_id]
        supported = []
        for row in node.get("participation") or []:
            evidence_ids = [x for x in row.get("evidence_ids", []) if x in self.evidence]
            if row.get("status") in PERSON_EVENT_STATUSES and evidence_ids:
                supported.append({**copy.deepcopy(row), "evidence_ids": evidence_ids})
        return supported

    def _group(self, source, endpoint, best_edges):
        if len(best_edges) != 1:
            return "indirect_connections"
        edge = self.edges[best_edges[0]]
        if edge["type"] == "INVESTED_IN" and edge["source"] == endpoint and edge["target"] == source:
            return "investors"
        if _norm(self.nodes[endpoint].get("entity_type")) == "person":
            return "direct_people"
        return "direct_companies"

    def _snapshot_complete(self):
        flag_keys = {"complete", "snapshot_complete", "cala_complete", "all_event_attendees_exported",
                     "all_displayed_directory_people_exported", "directory_exhaustion_verified"}

        def has_false(value):
            if isinstance(value, dict):
                return any((key in flag_keys and item is False) or has_false(item)
                           for key, item in value.items())
            if isinstance(value, list):
                return any(has_false(item) for item in value)
            return False

        return not has_false(self.manifest)

    def _base_response(self, question_id, inputs):
        limitations = copy.deepcopy(self.manifest.get("limitations") or [])
        return {
            "schema_version": "2.0", "question_id": question_id,
            "question": QUESTION_TEMPLATES[question_id], "inputs": inputs,
            "status": "complete", "resolved_entities": {}, "resolution": None,
            "summary": "", "results": [], "groups": None, "attendance_unverified": None,
            "graph": {"nodes": [], "edges": [], "paths": []}, "evidence": [],
            "coverage": {"snapshot_complete": self._snapshot_complete(),
                         "snapshot_limitations": limitations, "truncated": False,
                         "data_quality_exclusions": dict(self.diagnostics),
                         "max_displayed_results": self.max_results,
                         "max_paths_per_endpoint": self.max_paths},
            "generation_mode": "evidence_template",
            "versions": {"graph": self.snapshot.get("graph_version"),
                         "query": "2.0.0", "ranking": "evidence_then_steps_v1"},
            "interpretation": (
                "Paths describe sourced professional relationships, not personal acquaintance, "
                "a guaranteed introduction, meeting availability, or physical event attendance."
            ),
        }

    def _attach_graph(self, response, paths, extra_node_ids=()):
        node_ids = list(extra_node_ids)
        edge_ids = []
        evidence_ids = []
        for path in paths:
            node_ids.extend(path["node_ids"])
            edge_ids.extend(path["edge_ids"])
        node_ids = _unique(x for x in node_ids if x in self.nodes)
        edge_ids = _unique(edge_ids)
        for node_id in node_ids:
            evidence_ids.extend(self._node_evidence(self.nodes[node_id]))
        for edge_id in edge_ids:
            evidence_ids.extend(self.edges[edge_id]["evidence_ids"])
        response["graph"] = {
            "nodes": [self._node_view(x, profile=True) for x in node_ids],
            "edges": [copy.deepcopy(self.edges[x]) for x in edge_ids],
            "paths": paths,
        }
        response["evidence"] = [copy.deepcopy({**self.evidence[x], "id": x})
                                for x in _unique(evidence_ids) if x in self.evidence]

    def run(self, question_id, source=None, target=None, company=None,
            source_id=None, target_id=None, company_id=None):
        if question_id not in QUESTION_TEMPLATES:
            raise ValueError("question_id must be one of: " + ", ".join(QUESTION_TEMPLATES))
        inputs = {key: value for key, value in {
            "source": source, "target": target, "company": company,
            "source_id": source_id, "target_id": target_id, "company_id": company_id,
        }.items() if value is not None}
        response = self._base_response(question_id, inputs)
        if question_id in {"person_to_company", "company_to_company"}:
            source_type = "Person" if question_id == "person_to_company" else "Company"
            slots = {"source": (source_id or source, source_type), "target": (target_id or target, "Company")}
        else:
            slots = {"company": (company_id or company, "Company")}
        resolutions = {key: self.resolve(value, kind) for key, (value, kind) in slots.items()}
        unresolved = {key: result for key, result in resolutions.items() if result["status"] != "resolved"}
        response["resolved_entities"] = {
            key: result["entity"] for key, result in resolutions.items() if result["status"] == "resolved"
        }
        if unresolved:
            response["status"] = "needs_resolution" if any(
                value["status"] == "needs_resolution" for value in unresolved.values()) else "not_found"
            response["resolution"] = resolutions
            response["summary"] = "Resolve the indicated entity before searching its professional connections."
            return response
        if question_id in {"person_to_company", "company_to_company"}:
            a = resolutions["source"]["entity"]["id"]
            b = resolutions["target"]["entity"]["id"]
            if a == b:
                response["status"] = "insufficient_data"
                response["reason"] = "same_entity"
                response["summary"] = "Both inputs resolve to the same entity; choose a distinct target company."
                self._attach_graph(response, [], [a])
                return response
            found, search_coverage = self._search(a, b)
            paths = [self._path(*raw) for raw in found.get(b, [])]
            response["coverage"].update(search_coverage)
            response["results"] = [{"rank": index + 1, "path_id": path["id"],
                                    "target": self._node_view(b),
                                    "rank_reasons": path["rank_reasons"],
                                    "explanation": path["explanation"]}
                                   for index, path in enumerate(paths)]
            if paths:
                response["summary"] = (
                    f"Found {len(paths)} supported professional path{'s' if len(paths) != 1 else ''} "
                    f"from {self.nodes[a]['name']} to {self.nodes[b]['name']} within {self.max_hops} steps."
                )
            else:
                response["status"] = "insufficient_data"
                response["summary"] = (
                    f"No supported professional path was found from {self.nodes[a]['name']} to "
                    f"{self.nodes[b]['name']} within {self.max_hops} steps in the loaded snapshot."
                )
            self._attach_graph(response, paths, [a, b])
        elif question_id == "company_network":
            a = resolutions["company"]["entity"]["id"]
            found, search_coverage = self._search(a, max_hops=self.network_hops)
            endpoint_ids = sorted(found, key=lambda endpoint: self._path_key(*found[endpoint][0]))
            response["coverage"].update(search_coverage)
            response["coverage"]["result_limit_applied"] = len(endpoint_ids) > self.max_results
            response["coverage"]["eligible_endpoints_found"] = len(endpoint_ids)
            all_paths = []
            groups = defaultdict(list)
            for index, endpoint in enumerate(endpoint_ids[:self.max_results]):
                paths = [self._path(*raw) for raw in found[endpoint]]
                all_paths.extend(paths)
                group = self._group(a, endpoint, found[endpoint][0][1])
                row = {"rank": index + 1, "entity": self._node_view(endpoint), "group": group,
                       "path_ids": [x["id"] for x in paths],
                       "rank_reasons": paths[0]["rank_reasons"],
                       "explanation": paths[0]["explanation"]}
                response["results"].append(row)
                groups[group].append(endpoint)
            response["groups"] = dict(groups)
            if response["results"]:
                response["summary"] = (f"Showing {len(response['results'])} people or organizations "
                    f"within {self.network_hops} supported professional steps of {self.nodes[a]['name']}.")
            else:
                response["status"] = "insufficient_data"
                response["summary"] = f"No supported professional neighbours were found for {self.nodes[a]['name']} in this snapshot."
            self._attach_graph(response, all_paths, [a])
        else:
            a = resolutions["company"]["entity"]["id"]
            candidates = defaultdict(list)
            unknown_attendance = defaultdict(list)
            for person_id, edge_id in self.adj.get(a, []):
                edge = self.edges[edge_id]
                if edge["type"] not in AFFILIATION_TYPES or _norm(self.nodes[person_id].get("entity_type")) != "person":
                    continue
                if self._participation(person_id):
                    candidates[person_id].append(((a, person_id), (edge_id,)))
                else:
                    unknown_attendance[person_id].append(edge_id)
            for person_id in candidates:
                candidates[person_id].sort(key=lambda raw: self._path_key(*raw))
            candidate_ids = sorted(candidates, key=lambda person_id: self._path_key(*candidates[person_id][0]))
            response["coverage"].update({"max_hops": 1, "truncated": False,
                "result_limit_applied": len(candidate_ids) > self.max_results,
                "eligible_people_found": len(candidate_ids),
                "affiliated_people_without_named_participation": len(unknown_attendance)})
            paths = []
            for index, person_id in enumerate(candidate_ids[:self.max_results]):
                person_paths = [self._path(*raw) for raw in candidates[person_id][:self.max_paths]]
                paths.extend(person_paths)
                attendance = self._participation(person_id)
                reasons = ["Direct documented affiliation", "Named Slush participation evidence"] + person_paths[0]["rank_reasons"]
                response["results"].append({"rank": index + 1, "person": self._node_view(person_id, profile=True),
                    "attendance": attendance, "path_ids": [x["id"] for x in person_paths],
                    "rank_reasons": reasons, "explanation": person_paths[0]["explanation"],
                    "contact_interpretation": "A person to investigate or approach; availability and introduction are not established."})
            response["attendance_unverified"] = []
            for person_id in sorted(unknown_attendance)[:self.max_results]:
                edge_ids = sorted(unknown_attendance[person_id], key=lambda edge_id:
                                  self._path_key((a, person_id), (edge_id,)))[:self.max_paths]
                unverified_paths = [self._path((a, person_id), (edge_id,)) for edge_id in edge_ids]
                for path in unverified_paths:
                    path["endpoint_attendance"] = "unverified"
                paths.extend(unverified_paths)
                response["attendance_unverified"].append({**self._node_view(person_id),
                    "path_ids": [path["id"] for path in unverified_paths]})
            if response["results"]:
                people_label = "person" if len(response["results"]) == 1 else "people"
                response["summary"] = (f"Found {len(response['results'])} {people_label} with documented affiliations to "
                    f"{self.nodes[a]['name']} and named Slush participation evidence. Physical attendance and meeting availability are unverified.")
            else:
                response["status"] = "insufficient_data"
                response["summary"] = (f"No named Slush participants with supported direct affiliations to {self.nodes[a]['name']} "
                    "were established in this snapshot. A company listing does not establish its employees' attendance.")
            self._attach_graph(response, paths, [a] + [x["id"] for x in response["attendance_unverified"]])
        if response["status"] == "complete" and (
                response["coverage"]["truncated"] or not response["coverage"]["snapshot_complete"]):
            response["status"] = "partial"
        if response["coverage"].get("truncated"):
            response["summary"] += " Search limits were reached; further supported paths may exist."
        return response
