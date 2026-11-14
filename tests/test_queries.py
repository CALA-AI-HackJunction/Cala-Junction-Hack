"""Graph query engine, bounded 4-hop traversal, epistemic rules, and snapshot provenance tests."""
from __future__ import annotations

import unittest

from backend.ingest import ensure_snapshot
from backend.queries import QueryEngine


def fixture():
    return {
        "graph_version": "test-v1",
        "manifest": {"complete": True, "limitations": []},
        "nodes": {},
        "edges": [],
        "evidence": {},
    }


def node(snap, ident, name, kind="Company", statuses=(), **extra):
    evidence_id = "profile:" + ident
    snap["evidence"][evidence_id] = {
        "id": evidence_id,
        "dataset": "fixture",
        "record_pointer": "/" + ident,
    }
    snap["nodes"][ident] = {
        "id": ident,
        "name": name,
        "entity_type": kind,
        "properties": {},
        "aliases": [],
        "evidence_ids": [evidence_id],
        "participation": [{"status": status, "evidence_ids": [evidence_id]} for status in statuses],
        **extra,
    }


def edge(snap, ident, a, b, predicate="WORKS_AT", *, hop_cost=1, **extra):
    evidence_id = "evidence:" + ident
    snap["evidence"][evidence_id] = {
        "id": evidence_id,
        "dataset": "fixture",
        "record_pointer": "/edges/" + ident,
        "source_documents": [{"url": "https://example.org/" + ident}],
    }
    snap["edges"].append({
        "id": ident,
        "source": a,
        "target": b,
        "type": predicate,
        "properties": {},
        "traversable": True,
        "hop_cost": hop_cost,
        "temporal_status": "undated",
        "evidence_ids": [evidence_id],
        "origins": ["fixture"],
        **extra,
    })


class QueryTests(unittest.TestCase):
    """All 14 reference epistemic & bounded-traversal invariants + extended v2.1 checks."""

    def test_event_and_category_hubs_are_never_professional_paths(self):
        snap = fixture()
        node(snap, "a", "Alpha")
        node(snap, "b", "Beta")
        node(snap, "slush", "Slush", "Event")
        node(snap, "sector", "AI", "Industry")
        edge(snap, "one", "a", "slush", "PARTICIPATES_IN_EVENT")
        edge(snap, "two", "b", "slush", "PARTICIPATES_IN_EVENT")
        edge(snap, "three", "a", "sector", "OPERATES_IN_INDUSTRY")
        edge(snap, "four", "b", "sector", "OPERATES_IN_INDUSTRY")
        result = QueryEngine(snap).run("company_to_company", source="Alpha", target="Beta")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["graph"]["paths"], [])

    def test_homonyms_need_resolution_and_exact_ids_resolve(self):
        snap = fixture()
        node(snap, "p1", "Alex Smith", "Person")
        node(snap, "p2", "Alex Smith", "Person")
        node(snap, "a", "Alpha")
        edge(snap, "one", "p1", "a")
        engine = QueryEngine(snap)
        resolved = engine.resolve("Alex Smith", "Person")
        self.assertEqual(resolved["status"], "needs_resolution")
        self.assertEqual(resolved["resolution_state"], "ambiguous")
        result = engine.run("person_to_company", source="Alex Smith", target="Alpha")
        self.assertEqual(result["status"], "needs_resolution")
        self.assertEqual(result["graph"]["edges"], [])
        selected = engine.run("person_to_company", source_id="p1", target="Alpha")
        self.assertEqual(len(selected["graph"]["paths"]), 1)

    def test_reverse_traversal_preserves_investor_direction(self):
        snap = fixture()
        node(snap, "a", "Alpha")
        node(snap, "fund", "Fund Z", "Organization")
        edge(snap, "investment", "fund", "a", "INVESTED_IN")
        result = QueryEngine(snap).run("company_to_company", source="Alpha", target="Fund Z")
        rel = result["graph"]["paths"][0]["relations"][0]
        self.assertEqual(rel["traversal"], "reverse")
        self.assertEqual((rel["source_id"], rel["target_id"]), ("fund", "a"))
        self.assertIn("Fund Z has a documented investment in Alpha", rel["statement"])
        self.assertEqual(result["resolved_entities"]["target"]["entity_type"], "Organization")

    def test_maximum_four_underlying_steps(self):
        snap = fixture()
        for index in range(6):
            node(snap, str(index), "Company " + str(index))
        for index in range(5):
            edge(snap, "e" + str(index), str(index), str(index + 1), "INVESTED_IN")
        engine = QueryEngine(snap)
        four = engine.run("company_to_company", source="Company 0", target="Company 4")
        self.assertEqual(four["graph"]["paths"][0]["hop_count"], 4)
        five = engine.run("company_to_company", source="Company 0", target="Company 5")
        self.assertEqual(five["status"], "insufficient_data")
        self.assertFalse(five["graph"]["paths"])

    def test_derived_shortcuts_retain_underlying_cost(self):
        snap = fixture()
        for ident in ("a", "b", "c", "d"):
            node(snap, ident, ident)
        edge(snap, "ab", "a", "b", "INVESTED_IN", hop_cost=2, derived=True)
        edge(snap, "bc", "b", "c", "INVESTED_IN", hop_cost=2, derived=True)
        edge(snap, "cd", "c", "d", "INVESTED_IN")
        engine = QueryEngine(snap)
        self.assertEqual(
            engine.run("company_to_company", source="a", target="c")["graph"]["paths"][0]["hop_count"],
            4,
        )
        self.assertEqual(engine.run("company_to_company", source="a", target="d")["status"], "insufficient_data")

    def test_company_presence_does_not_propagate_to_employees(self):
        snap = fixture()
        node(snap, "a", "Alpha", statuses=["company_listed"])
        node(snap, "p", "Pat", "Person")
        edge(snap, "pa", "p", "a")
        result = QueryEngine(snap).run("company_representatives", company="Alpha")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertFalse(result["results"])
        self.assertEqual(result["attendance_unverified"][0]["id"], "p")
        self.assertTrue(result["attendance_unverified"][0]["path_ids"])

    def test_explicit_person_participation_and_affiliation_are_kept_distinct(self):
        snap = fixture()
        node(snap, "a", "Alpha", statuses=["company_listed"])
        node(snap, "p", "Pat", "Person", statuses=["platform_directory"])
        snap["nodes"]["p"]["properties"]["biography"] = "A documented professional background."
        edge(snap, "pa", "p", "a", "AFFILIATED_WITH")
        result = QueryEngine(snap).run("company_representatives", company="Alpha")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["attendance"][0]["status"], "platform_directory")
        self.assertIn("documented affiliation", result["results"][0]["explanation"])
        self.assertNotIn("works at", result["results"][0]["explanation"])
        self.assertIn("Physical attendance", result["summary"])

    def test_no_attendance_without_evidence(self):
        snap = fixture()
        node(snap, "a", "Alpha")
        node(snap, "p", "Pat", "Person", statuses=["announced_attendee"])
        snap["nodes"]["p"]["participation"][0]["evidence_ids"] = ["missing"]
        edge(snap, "pa", "p", "a")
        result = QueryEngine(snap).run("company_representatives", company="Alpha")
        self.assertFalse(result["results"])

    def test_graph_and_evidence_references_are_closed(self):
        snap = fixture()
        node(snap, "p", "Pat", "Person", statuses=["announced_attendee"])
        node(snap, "a", "Alpha")
        node(snap, "b", "Beta")
        edge(snap, "pa", "p", "a")
        edge(snap, "ba", "b", "a", "INVESTED_IN")
        result = QueryEngine(snap).run("person_to_company", source="Pat", target="Beta")
        evidence = {row["id"] for row in result["evidence"]}
        nodes = {row["id"] for row in result["graph"]["nodes"]}
        edges = {row["id"] for row in result["graph"]["edges"]}
        for row in result["graph"]["edges"]:
            self.assertIn(row["source"], nodes)
            self.assertIn(row["target"], nodes)
            self.assertTrue(set(row["evidence_ids"]).issubset(evidence))
        for path in result["graph"]["paths"]:
            self.assertTrue(set(path["edge_ids"]).issubset(edges))
            self.assertTrue(set(path["node_ids"]).issubset(nodes))
        self.assertEqual(result["generation_mode"], "evidence_template")

    def test_missing_edge_evidence_excluded(self):
        snap = fixture()
        node(snap, "a", "Alpha")
        node(snap, "b", "Beta")
        edge(snap, "ab", "a", "b", "INVESTED_IN")
        snap["edges"][0]["evidence_ids"] = ["does-not-exist"]
        result = QueryEngine(snap).run("company_to_company", source="Alpha", target="Beta")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertGreater(result["coverage"]["data_quality_exclusions"]["invalid_evidence_references"], 0)

    def test_search_budget_is_explicit(self):
        snap = fixture()
        for ident in ("a", "b", "c"):
            node(snap, ident, ident)
        edge(snap, "ab", "a", "b", "INVESTED_IN")
        edge(snap, "bc", "b", "c", "INVESTED_IN")
        result = QueryEngine(snap, max_states=1).run("company_to_company", source="a", target="c")
        self.assertTrue(result["coverage"]["truncated"])
        self.assertIn("visited_state_budget", result["coverage"]["truncation_reasons"])
        self.assertIn("further supported paths may exist", result["summary"])

    def test_snapshot_incompleteness_is_preserved(self):
        snap = fixture()
        snap["manifest"]["datasets"] = [{"name": "cala", "complete": False}]
        node(snap, "a", "Alpha")
        node(snap, "b", "Beta")
        edge(snap, "ab", "a", "b", "INVESTED_IN")
        result = QueryEngine(snap).run("company_to_company", source="Alpha", target="Beta")
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["coverage"]["snapshot_complete"])

    def test_company_network_groups_direct_and_indirect(self):
        snap = fixture()
        node(snap, "a", "Alpha")
        node(snap, "p", "Pat", "Person")
        node(snap, "i", "Investor", "Organization")
        node(snap, "b", "Beta")
        edge(snap, "pa", "p", "a", "FOUNDED")
        edge(snap, "ia", "i", "a", "INVESTED_IN")
        edge(snap, "ib", "i", "b", "INVESTED_IN")
        result = QueryEngine(snap).run("company_network", company="Alpha")
        self.assertEqual(result["groups"]["direct_people"], ["p"])
        self.assertEqual(result["groups"]["investors"], ["i"])
        self.assertEqual(result["groups"]["indirect_connections"], ["b"])

    def test_invalid_collective_identity_is_not_a_bridge(self):
        snap = fixture()
        node(snap, "a", "Alpha")
        node(snap, "b", "Beta")
        node(snap, "bad", "including renowned industry leaders", "Organization", invalid_identity=True)
        edge(snap, "ba", "bad", "a", "INVESTED_IN")
        edge(snap, "bb", "bad", "b", "INVESTED_IN")
        engine = QueryEngine(snap)
        self.assertEqual(engine.resolve("including renowned industry leaders")["status"], "not_found")
        self.assertFalse(engine.run("company_to_company", source="Alpha", target="Beta")["results"])

    def test_geography_and_domain_predicates_are_never_traversable_bridges(self):
        snap = fixture()
        node(snap, "a", "Alpha")
        node(snap, "b", "Beta")
        node(snap, "fi", "Finland", "Place")
        node(snap, "dom", "alpha.example", "Domain")
        for idx, pred in enumerate(("HAS_HEADQUARTERS_IN", "HAS_PRESENCE_IN", "IS_REGISTERED_IN")):
            edge(snap, f"ga{idx}", "a", "fi", pred)
            edge(snap, f"gb{idx}", "b", "fi", pred)
        edge(snap, "da", "a", "dom", "HAS_DOMAIN_NAME")
        edge(snap, "db", "b", "dom", "HAS_DOMAIN_NAME")
        result = QueryEngine(snap).run("company_to_company", source="Alpha", target="Beta")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["graph"]["paths"], [])

    def test_typeahead_suggestions_respect_limit_and_degree_ranking(self):
        snap = fixture()
        node(snap, "c1", "Nordic Stub", "Company", record_completeness="stub")
        node(snap, "c2", "Nordic Connected", "Company", record_completeness="full")
        node(snap, "c3", "Nordic Peer", "Company", record_completeness="full")
        edge(snap, "e1", "c2", "c3", "INVESTED_IN")
        engine = QueryEngine(snap)
        res = engine.resolve("Nordic", "Company", limit=2)
        self.assertIn("suggestions", res)
        self.assertLessEqual(len(res["suggestions"]), 2)
        self.assertEqual(res["suggestions"][0]["id"], "c2")

    def test_real_snapshot_graph_version_and_provenance_invariants(self):
        snap = ensure_snapshot()
        self.assertEqual(
            snap["graph_version"],
            "b2e1e3d55b0e200e1923f7dfd0f723d8d5736f8a646f95fd1200ad8ecae7cf70",
        )
        counts = snap["manifest"]["counts"]
        self.assertEqual(counts["nodes"], 10785)
        self.assertEqual(counts["edges"], 4023)
        self.assertEqual(counts["traversable_edges"], 933)
        self.assertEqual(counts["edge_types"]["PARTICIPATES_IN_EVENT"], 2990)
        self.assertFalse(snap["manifest"]["cala_coverage"]["complete"])

        evidence_map = snap["evidence"]
        for raw_edge in snap["edges"]:
            if not raw_edge.get("traversable"):
                continue
            self.assertNotIn(
                raw_edge["type"],
                {"PARTICIPATES_IN_EVENT", "OPERATES_IN_INDUSTRY", "HAS_DOMAIN_NAME", "HAS_HEADQUARTERS_IN"},
            )
            eids = raw_edge.get("evidence_ids") or []
            self.assertTrue(eids, f"Traversable edge {raw_edge['id']} lacks evidence_ids")
            has_doc = False
            has_provenance = False
            for eid in eids:
                self.assertIn(eid, evidence_map)
                ev_rec = evidence_map[eid]
                docs = ev_rec.get("source_documents") or []
                if docs:
                    has_doc = True
                if docs or ev_rec.get("record_pointer"):
                    has_provenance = True
            self.assertTrue(has_provenance, f"Traversable edge {raw_edge['id']} lacks provenance record")
            if raw_edge.get("origins") == ["cala"]:
                self.assertTrue(has_doc, f"Cala traversable edge {raw_edge['id']} lacks source_documents provenance")


if __name__ == "__main__":
    unittest.main()
