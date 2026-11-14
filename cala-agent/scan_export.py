"""Find evidence-backed Slush connections in an offline Cala graph export."""

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path


def relationship_kind(edge_type):
    if edge_type in {"INVESTED_IN", "FOUNDED", "WORKS_AT"}:
        return {
            "INVESTED_IN": "shared_investor",
            "FOUNDED": "shared_founder",
            "WORKS_AT": "shared_personnel",
        }[edge_type]
    if edge_type in {
        "IS_BOARD_MEMBER_OF", "IS_CCO_OF", "IS_CEO_OF", "IS_CFO_OF", "IS_CMO_OF",
        "IS_COO_OF", "IS_CSO_OF", "IS_CTO_OF", "IS_MANAGING_DIRECTOR_OF",
        "IS_VICEPRESIDENT_OF",
    }:
        return "shared_personnel"
    return None


def shortest_paths(adjacency, origins, destinations, max_hops):
    """Yield one shortest route per pair. Parallel and alternate edges stay in the graph."""
    for origin in sorted(origins):
        parents = {origin: None}
        queue = deque([(origin, 0)])
        while queue:
            current, depth = queue.popleft()
            if current in destinations and current != origin:
                steps = []
                cursor = current
                while cursor != origin:
                    previous, index = parents[cursor]
                    steps.append((previous, cursor, index))
                    cursor = previous
                yield origin, current, list(reversed(steps))
            if depth == max_hops:
                continue
            for neighbor, index in adjacency[current]:
                if neighbor not in parents:
                    parents[neighbor] = (current, index)
                    queue.append((neighbor, depth + 1))


def scan(graph, focus=None, max_hops=4):
    edges = graph["edges"]
    seed_id = graph["seed"]["id"]
    retrieved = {item["record"]["id"]: item["record"] for item in graph["entities"]}
    nodes = {record["id"]: record for edge in edges for record in edge["records"]}
    nodes.update(retrieved)

    def entity(entity_id):
        row = nodes.get(entity_id, {})
        return {
            "id": entity_id,
            "name": row.get("name"),
            "entity_type": row.get("entity_type"),
            "record_retrieved": entity_id in retrieved,
        }

    attendees = {
        edge["source"]
        for edge in edges
        if edge["target"] == seed_id
        and edge["type"] == "PARTICIPATES_IN_EVENT"
        and entity(edge["source"])["entity_type"] == "Company"
        and any(r.get("properties", {}).get("role") == "ATTENDEE" for r in edge["records"])
    }
    groups = defaultdict(lambda: defaultdict(list))
    direct = []
    investments = []
    observed = set()
    for index, edge in enumerate(edges):
        source, target, relation = (edge[key] for key in ("source", "target", "type"))
        if relation != "PARTICIPATES_IN_EVENT":
            observed.update({source, target} & attendees)
        if relation in {"OPERATES_IN_INDUSTRY", "HAS_HEADQUARTERS_IN"} and source in attendees:
            kind = {"OPERATES_IN_INDUSTRY": "same_industry",
                    "HAS_HEADQUARTERS_IN": "same_headquarters_country"}[relation]
            groups[kind, target][source].append(index)
        if target in attendees:
            kind = relationship_kind(relation)
            if relation == "INVESTED_IN":
                investments.append(index)
            if kind in {"shared_investor", "shared_founder"} or (
                kind == "shared_personnel" and entity(source)["entity_type"] == "Person"
            ):
                groups[kind, source][target].append(index)
        if source in attendees and target in attendees and relation != "PARTICIPATES_IN_EVENT":
            direct.append(index)

    def evidence(index):
        edge = edges[index]
        properties = [record.get("properties", {}) for record in edge["records"]]
        sources = {
            json.dumps(source, ensure_ascii=False, sort_keys=True): source
            for row in properties for source in row.get("sources", [])
        }
        return {
            "pointer": f"/edges/{index}",
            "type": edge["type"],
            "source": entity(edge["source"]),
            "target": entity(edge["target"]),
            "sources": list(sources.values()),
            "properties": [
                {key: value for key, value in row.items() if key != "sources"}
                for row in properties
            ],
        }

    adjacency = defaultdict(list)
    network_indices = []
    for index, edge in enumerate(edges):
        source, target = edge["source"], edge["target"]
        if edge["type"] == "PARTICIPATES_IN_EVENT" and seed_id in (source, target):
            continue
        network_indices.append(index)
        adjacency[source].append((target, index))
        adjacency[target].append((source, index))

    if focus is not None and focus not in nodes:
        raise ValueError(f"Entity ID not found in export: {focus}")
    origins = {focus} if focus is not None else attendees & adjacency.keys()
    paths = []
    for start, end, steps in shortest_paths(adjacency, origins, attendees, max_hops):
        if focus is None and start > end:
            continue
        paths.append({
            "source": entity(start),
            "target": entity(end),
            "hops": len(steps),
            "steps": [
                {
                    "from_id": previous,
                    "to_id": following,
                    "edge": f"/edges/{index}",
                    "direction": "forward" if edges[index]["source"] == previous else "reverse",
                }
                for previous, following, index in steps
            ],
        })

    matches = []
    for (kind, bridge), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        matches.append({
            "kind": kind,
            "shared_entity": entity(bridge),
            "companies": [
                {"company": entity(company), "evidence": [evidence(i) for i in indices]}
                for company, indices in sorted(members.items(), key=lambda item: (
                    entity(item[0])["name"] or "", item[0]
                ))
            ],
        })
    return {
        "event": entity(seed_id),
        "coverage": {
            "complete": graph.get("complete"),
            "reason": graph.get("reason"),
            "retrieved_by_hop": graph.get("retrieved_by_hop"),
            "retrieved_entity_records": len(retrieved),
            "edges": len(edges),
            "listed_company_attendees": len(attendees),
            "company_attendees_with_retrieved_records": len(attendees & retrieved.keys()),
            "company_attendees_with_observed_non_attendance_edges": len(observed),
        },
        "connections": [match for match in matches if not match["kind"].startswith("same_")],
        "similarities": [match for match in matches if match["kind"].startswith("same_")],
        "direct_company_relationships": [evidence(index) for index in direct],
        "attendee_investment_edges": [evidence(index) for index in investments],
        "network": {
            "max_hops": max_hops,
            "focus": entity(focus) if focus is not None else None,
            "attendees": [entity(i) for i in sorted(attendees)],
            "edges": [evidence(index) for index in network_indices],
            "shortest_paths": paths,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--focus", help="Find routes from a Cala entity ID to Slush companies.")
    parser.add_argument("--max-hops", type=int, default=4)
    parser.add_argument("--output", type=Path, help="Write the report here instead of stdout.")
    args = parser.parse_args()
    if args.max_hops < 1:
        parser.error("--max-hops must be at least 1.")
    if args.output and args.output.resolve() == args.export.resolve():
        parser.error("Choose a report path different from the export.")
    try:
        report = scan(
            json.loads(args.export.read_text(encoding="utf-8-sig")),
            focus=args.focus,
            max_hops=args.max_hops,
        )
        result = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(result, encoding="utf-8")
        else:
            sys.stdout.write(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Cala scan failed: {error}\n")


if __name__ == "__main__":
    main()
