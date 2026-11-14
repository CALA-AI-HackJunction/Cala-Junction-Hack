import json
import httpx

headers = {
    "X-API-KEY": "clsk_9BMKS0Fqk92xAhDq1NLNP12QmpHiEd3w_7imRPh50do",
    "Content-Type": "application/json",
}

# 1. Slush 2024
slush_2024_id = "7e6eb50e-b1af-4776-9088-654373d1e015"
r = httpx.post(
    f"https://api.cala.ai/v1/entities/{slush_2024_id}",
    headers=headers,
    json={
        "properties": ["name"],
        "relationships": {
            "incoming": {
                "SPOKE_AT": {"limit": 20}
            }
        },
    },
    timeout=30.0,
)

speakers = r.json().get("relationships", {}).get("incoming", {}).get("SPOKE_AT", [])
print(f"Slush 2024 speakers ({len(speakers)}):")
for s in speakers:
    print(f"  - {s.get('name')} | UUID: {s.get('id')}")

# Also check Slush 2025
slush_2025_id = "0b5b355d-94a2-43f6-9bd2-b3b7f92c67e0"
r2 = httpx.post(
    f"https://api.cala.ai/v1/entities/{slush_2025_id}",
    headers=headers,
    json={
        "properties": ["name"],
        "relationships": {
            "incoming": {
                "SPOKE_AT": {"limit": 20}
            }
        },
    },
    timeout=30.0,
)
speakers2 = r2.json().get("relationships", {}).get("incoming", {}).get("SPOKE_AT", [])
print(f"\nSlush 2025 speakers ({len(speakers2)}):")
for s in speakers2:
    print(f"  - {s.get('name')} | UUID: {s.get('id')}")
