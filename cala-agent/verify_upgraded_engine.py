import asyncio
from traversal import CalaGraphTraversalEngine

async def test():
    engine = CalaGraphTraversalEngine()
    print("Testing Slush 2026 attendees...")
    attendees = await engine.get_slush_attendees(limit=5)
    print("Found attendees:", len(attendees))
    for a in attendees:
        print(f"  - {a['name']} ({a['role']})")

    print("\nTesting traversal with deduplication and source rank...")
    conns = await engine.traverse_network([
        "af1c7427-b685-4e0c-b03a-7efb074bc3ff",  # Ilkka
        "86420e0b-4f82-4516-a434-aadcb10db0fb",  # Miki
        "1666f898-8809-4d0c-a008-07d7cf755309",  # Luciana
    ])
    print(f"Discovered unique connections: {len(conns)}")
    for c in conns:
        print(f"  * [{c.connection_type}] {c.source_person_name} <-> {c.target_person_name} | Shared: {c.shared_entity_name} | Source Rank: {c.source_rank}")

if __name__ == "__main__":
    asyncio.run(test())
