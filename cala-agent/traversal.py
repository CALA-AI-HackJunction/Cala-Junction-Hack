"""Upgraded Graph Traversal Engine with Slush 2026 Attendees, Funding Rounds (is_lead), 
Temporal Roles (valid_since/valid_until), and Source Ranking."""

from dataclasses import dataclass, field
from typing import Any
import httpx

from config import get_settings

BASE_URL = "https://api.cala.ai/v1"
SLUSH_2026_UUID = "bc844d56-6ab4-452b-96bf-2661e86e592b"
SLUSH_2025_UUID = "0b5b355d-94a2-43f6-9bd2-b3b7f92c67e0"
SLUSH_2024_UUID = "7e6eb50e-b1af-4776-9088-654373d1e015"


@dataclass
class ConnectionPath:
    source_person_id: str
    source_person_name: str
    target_person_id: str
    target_person_name: str
    connection_type: str  # e.g. "shared_lead_investor", "shared_investor", "co_attendee", "co_speaker", "investor_founder"
    hops: int
    shared_entity_id: str
    shared_entity_name: str
    round_label: str | None = None  # e.g. "SERIES_A", "SEED"
    is_lead: bool = False
    source_rank: str | None = None  # "FILING", "PRIMARY", "PRESS"
    active: bool = True  # Based on valid_until
    description: str = ""
    path: list[dict[str, str]] = field(default_factory=list)


class CalaGraphTraversalEngine:
    def __init__(self, api_key: str | None = None):
        cfg = get_settings()
        self.api_key = api_key or cfg.cala_api_key
        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        self._cache: dict[str, dict[str, Any]] = {}

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await client.post(
            f"{BASE_URL}{path}",
            headers=self.headers,
            json=body,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_slush_attendees(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch verified participating startups/companies for Slush 2026."""
        async with httpx.AsyncClient() as client:
            proj = {
                "properties": ["name"],
                "relationships": {
                    "incoming": {
                        "PARTICIPATES_IN_EVENT": {"limit": limit}
                    }
                },
            }
            res = await self._post(client, f"/entities/{SLUSH_2026_UUID}", proj)
            attendees = res.get("relationships", {}).get("incoming", {}).get("PARTICIPATES_IN_EVENT", [])
            return [
                {
                    "id": a["id"],
                    "name": a.get("name", "Unknown"),
                    "entity_type": a.get("entity_type", "Company"),
                    "role": a.get("properties", {}).get("role", "ATTENDEE"),
                }
                for a in attendees
            ]

    async def get_entity_profile(self, client: httpx.AsyncClient, entity_id: str, projection: dict[str, Any]) -> dict[str, Any]:
        cache_key = f"{entity_id}:{str(projection)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = await self._post(client, f"/entities/{entity_id}", projection)
        self._cache[cache_key] = data
        return data

    async def traverse_network(self, people_ids: list[str]) -> list[ConnectionPath]:
        """
        Runs full 2-stage traversal across people, their companies/events, and funding rounds:
        - Stage 1: People -> Companies & Events (WORKS_AT, FOUNDED, IS_CEO_OF, SPOKE_AT, PARTICIPATES_IN_EVENT)
        - Stage 2: Companies -> Incoming INVESTED_IN & Outgoing PARTICIPATES_IN_FUNDING_ROUND
        Extracts lead investors (is_lead), round labels, temporal flags, and source ranks.
        """
        async with httpx.AsyncClient() as client:
            people_profiles: dict[str, dict[str, Any]] = {}

            # 1. Retrieve Stage 1 for all people
            for pid in people_ids:
                proj = {
                    "properties": ["name", "description"],
                    "relationships": {
                        "outgoing": {
                            "WORKS_AT": {"limit": 10},
                            "FOUNDED": {"limit": 10},
                            "IS_CEO_OF": {"limit": 10},
                            "IS_CTO_OF": {"limit": 10},
                            "INVESTED_IN": {"limit": 10},
                            "SPOKE_AT": {"limit": 10},
                            "PARTICIPATES_IN_EVENT": {"limit": 10},
                        }
                    },
                }
                profile = await self.get_entity_profile(client, pid, proj)
                people_profiles[pid] = profile

            # 2. Collect unique companies to expand
            companies_to_expand: dict[str, str] = {}
            for pid, prof in people_profiles.items():
                rels = prof.get("relationships", {}).get("outgoing", {})
                for rel_type in ("WORKS_AT", "FOUNDED", "IS_CEO_OF", "IS_CTO_OF"):
                    for target in rels.get(rel_type, []):
                        if target.get("entity_type") in ("Company", "Organization"):
                            companies_to_expand[target["id"]] = target["name"]

            # 3. Retrieve Stage 2: Incoming INVESTED_IN and funding rounds
            company_investors: dict[str, list[dict[str, Any]]] = {}
            company_rounds: dict[str, list[dict[str, Any]]] = {}

            for cid in companies_to_expand:
                cproj = {
                    "properties": ["name", "funding_stage"],
                    "relationships": {
                        "incoming": {
                            "INVESTED_IN": {"limit": 20},
                        },
                        "outgoing": {
                            "PARTICIPATES_IN_FUNDING_ROUND": {"limit": 10},
                        },
                    },
                }
                cdata = await self.get_entity_profile(client, cid, cproj)
                company_investors[cid] = cdata.get("relationships", {}).get("incoming", {}).get("INVESTED_IN", [])
                company_rounds[cid] = cdata.get("relationships", {}).get("outgoing", {}).get("PARTICIPATES_IN_FUNDING_ROUND", [])

            connections: list[ConnectionPath] = []
            pids = list(people_profiles.keys())

            for i in range(len(pids)):
                for j in range(i + 1, len(pids)):
                    p1_id, p2_id = pids[i], pids[j]
                    p1, p2 = people_profiles[p1_id], people_profiles[p2_id]
                    p1_rels = p1.get("relationships", {}).get("outgoing", {})
                    p2_rels = p2.get("relationships", {}).get("outgoing", {})

                    # A. Co-Speaker or Co-Attendee at Event (2 Hops)
                    p1_events = {e["id"]: e["name"] for e in (p1_rels.get("SPOKE_AT", []) + p1_rels.get("PARTICIPATES_IN_EVENT", []))}
                    p2_events = p2_rels.get("SPOKE_AT", []) + p2_rels.get("PARTICIPATES_IN_EVENT", [])

                    for e2 in p2_events:
                        if e2["id"] in p1_events:
                            connections.append(
                                ConnectionPath(
                                    source_person_id=p1_id,
                                    source_person_name=p1["name"],
                                    target_person_id=p2_id,
                                    target_person_name=p2["name"],
                                    connection_type="co_speaker",
                                    hops=2,
                                    shared_entity_id=e2["id"],
                                    shared_entity_name=e2["name"],
                                    description=f"Both featured at {e2['name']}",
                                    path=[
                                        {"node": p1["name"], "edge": "SPOKE_AT"},
                                        {"node": e2["name"], "edge": "SPOKE_AT_INCOMING"},
                                        {"node": p2["name"], "edge": ""},
                                    ],
                                )
                            )

                    # B. Shared Company (2 Hops)
                    p1_companies = {}
                    for rtype in ("WORKS_AT", "FOUNDED", "IS_CEO_OF", "IS_CTO_OF"):
                        for c in p1_rels.get(rtype, []):
                            p1_companies[c["id"]] = (c["name"], rtype, c.get("properties", {}))

                    for rtype in ("WORKS_AT", "FOUNDED", "IS_CEO_OF", "IS_CTO_OF"):
                        for c2 in p2_rels.get(rtype, []):
                            if c2["id"] in p1_companies:
                                cname, r1_type, props1 = p1_companies[c2["id"]]
                                props2 = c2.get("properties", {})
                                is_active = not bool(props1.get("valid_until") or props2.get("valid_until"))
                                connections.append(
                                    ConnectionPath(
                                        source_person_id=p1_id,
                                        source_person_name=p1["name"],
                                        target_person_id=p2_id,
                                        target_person_name=p2["name"],
                                        connection_type="shared_company",
                                        hops=2,
                                        shared_entity_id=c2["id"],
                                        shared_entity_name=cname,
                                        active=is_active,
                                        description=f"Both affiliated with {cname} ({'Current' if is_active else 'Former'})",
                                        path=[
                                            {"node": p1["name"], "edge": r1_type},
                                            {"node": cname, "edge": f"{rtype}_INCOMING"},
                                            {"node": p2["name"], "edge": ""},
                                        ],
                                    )
                                )

                    # C. Direct Investor-Founder (3 Hops)
                    for rtype in ("WORKS_AT", "FOUNDED", "IS_CEO_OF", "IS_CTO_OF"):
                        for c1 in p1_rels.get(rtype, []):
                            for inv in company_investors.get(c1["id"], []):
                                for p2_work in p2_rels.get("WORKS_AT", []):
                                    if inv["id"] == p2_work["id"]:
                                        sources = inv.get("properties", {}).get("sources", [])
                                        s_rank = sources[0].get("source_rank") if sources else None
                                        connections.append(
                                            ConnectionPath(
                                                source_person_id=p1_id,
                                                source_person_name=p1["name"],
                                                target_person_id=p2_id,
                                                target_person_name=p2["name"],
                                                connection_type="investor_founder",
                                                hops=3,
                                                shared_entity_id=inv["id"],
                                                shared_entity_name=inv["name"],
                                                source_rank=s_rank,
                                                description=f"{p2['name']} affiliated with {inv['name']}, which backed {p1['name']}'s {c1['name']}",
                                                path=[
                                                    {"node": p1["name"], "edge": rtype},
                                                    {"node": c1["name"], "edge": "INVESTED_IN_INCOMING"},
                                                    {"node": inv["name"], "edge": "WORKS_AT_INCOMING"},
                                                    {"node": p2["name"], "edge": ""},
                                                ],
                                            )
                                        )

                    # D. Shared Investor (4 Hops) with is_lead & source_rank inspection
                    p1_cos = [c["id"] for r in ("WORKS_AT", "FOUNDED", "IS_CEO_OF") for c in p1_rels.get(r, [])]
                    p2_cos = [c["id"] for r in ("WORKS_AT", "FOUNDED", "IS_CEO_OF") for c in p2_rels.get(r, [])]

                    for c1_id in p1_cos:
                        c1_invs = {inv["id"]: inv for inv in company_investors.get(c1_id, [])}
                        for c2_id in p2_cos:
                            if c1_id == c2_id:
                                continue
                            for inv2 in company_investors.get(c2_id, []):
                                if inv2["id"] in c1_invs:
                                    inv1 = c1_invs[inv2["id"]]
                                    c1_name = companies_to_expand.get(c1_id, c1_id)
                                    c2_name = companies_to_expand.get(c2_id, c2_id)
                                    shared_vc_name = inv1["name"]

                                    # Check source ranking from either edge
                                    srcs1 = inv1.get("properties", {}).get("sources", [])
                                    srcs2 = inv2.get("properties", {}).get("sources", [])
                                    rank = None
                                    for s in srcs1 + srcs2:
                                        if s.get("source_rank"):
                                            rank = s["source_rank"]
                                            break

                                    is_lead = inv1.get("properties", {}).get("is_lead", False) or inv2.get("properties", {}).get("is_lead", False)

                                    connections.append(
                                        ConnectionPath(
                                            source_person_id=p1_id,
                                            source_person_name=p1["name"],
                                            target_person_id=p2_id,
                                            target_person_name=p2["name"],
                                            connection_type="shared_lead_investor" if is_lead else "shared_investor",
                                            hops=4,
                                            shared_entity_id=inv2["id"],
                                            shared_entity_name=shared_vc_name,
                                            is_lead=is_lead,
                                            source_rank=rank,
                                            description=f"{'Lead Investor' if is_lead else 'Shared Investor'} {shared_vc_name} backed both {c1_name} and {c2_name}",
                                            path=[
                                                {"node": p1["name"], "edge": "WORKS_AT/FOUNDED"},
                                                {"node": c1_name, "edge": "INVESTED_IN_INCOMING"},
                                                {"node": shared_vc_name, "edge": "INVESTED_IN"},
                                                {"node": c2_name, "edge": "WORKS_AT/FOUNDED_INCOMING"},
                                                {"node": p2["name"], "edge": ""},
                                            ],
                                        )
                                    )

            # Deduplicate connection records
            unique_conns: list[ConnectionPath] = []
            seen = set()
            for c in connections:
                key = (c.source_person_id, c.target_person_id, c.connection_type, c.shared_entity_id)
                if key not in seen:
                    seen.add(key)
                    unique_conns.append(c)

            return unique_conns
