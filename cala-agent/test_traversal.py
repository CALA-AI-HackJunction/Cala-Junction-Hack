import json
import httpx

headers = {
    "X-API-KEY": "clsk_9BMKS0Fqk92xAhDq1NLNP12QmpHiEd3w_7imRPh50do",
    "Content-Type": "application/json",
}

people = {
    "Ilkka Paananen": "af1c7427-b685-4e0c-b03a-7efb074bc3ff",
    "Miki Kuusi": "86420e0b-4f82-4516-a434-aadcb10db0fb",
    "Laurent Sifre": "414ac222-96b0-4538-ab4d-0e992433dca9",
    "Peter Sarlin": "b1e3b86c-d300-46e0-be41-cc860b4744bd",
    "Luciana Lixandru": "1666f898-8809-4d0c-a008-07d7cf755309",
}

print("Fetching companies/affiliations for 5 Slush figures...\n")

person_data = {}

for name, uuid in people.items():
    r = httpx.post(
        f"https://api.cala.ai/v1/entities/{uuid}",
        headers=headers,
        json={
            "properties": ["name", "description"],
            "relationships": {
                "outgoing": {
                    "WORKS_AT": {"limit": 10},
                    "FOUNDED": {"limit": 10},
                    "IS_CEO_OF": {"limit": 10},
                    "IS_CTO_OF": {"limit": 10},
                    "INVESTED_IN": {"limit": 10},
                    "SPOKE_AT": {"limit": 10},
                }
            },
        },
        timeout=30.0,
    )
    res = r.json()
    rels = res.get("relationships", {}).get("outgoing", {})
    person_data[name] = {
        "id": uuid,
        "name": res.get("name"),
        "relationships": rels,
    }
    print(f"=== {name} ===")
    for rel_name, targets in rels.items():
        if targets:
            print(f"  {rel_name}:")
            for t in targets:
                print(f"    -> {t.get('name')} ({t.get('entity_type')}, id: {t.get('id')})")
    print()

# Now inspect the companies to find shared investors or parent companies
companies = set()
for p in person_data.values():
    for rel_type, targets in p["relationships"].items():
        if rel_type in ("WORKS_AT", "FOUNDED", "IS_CEO_OF", "IS_CTO_OF"):
            for t in targets:
                if t.get("entity_type") in ("Company", "Organization"):
                    companies.add((t["name"], t["id"]))

print(f"\nDiscovered {len(companies)} affiliated companies. Fetching investors for each...")
company_investors = {}
for cname, cid in companies:
    cr = httpx.post(
        f"https://api.cala.ai/v1/entities/{cid}",
        headers=headers,
        json={
            "properties": ["name"],
            "relationships": {
                "incoming": {
                    "INVESTED_IN": {"limit": 10},
                }
            },
        },
        timeout=30.0,
    )
    cres = cr.json()
    investors = cres.get("relationships", {}).get("incoming", {}).get("INVESTED_IN", [])
    company_investors[cid] = investors
    if investors:
        print(f"Company: {cname}")
        for inv in investors:
            print(f"  <- INVESTED_IN by: {inv.get('name')} ({inv.get('id')})")
