"""Persistence, versioned caching, composer validation, and stdlib/API contract tests."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import backend.generation as generation_mod
from backend.generation import build_generation_request, compose, validate_claims
from backend.server import make_server
import backend.service as service_mod
from backend.service import AnalysisService
from backend.store import AnalysisStore


class FakeEngine:
    """Controlled retriever isolates orchestration from graph-search behavior."""

    calls = 0

    def __init__(self, snapshot):
        self.snapshot = snapshot

    def resolve(self, value, entity_type=None, limit=15):
        entities = {
            "person-a": {"id": "person-a", "name": "Ada Example", "entity_type": "Person"},
            "company-a": {"id": "company-a", "name": "Example Company", "entity_type": "Company"},
        }
        aliases = {"ada example": "person-a", "example company": "company-a"}
        key = aliases.get(value.casefold(), value)
        entity = entities.get(key)
        if entity and (entity_type is None or entity["entity_type"] == entity_type):
            return {"status": "resolved", "resolution_state": "resolved", "entity": entity, "candidates": [], "suggestions": [entity]}
        return {"status": "not_found", "resolution_state": "not_found", "candidates": [], "suggestions": []}

    def run(self, question_id, **inputs):
        FakeEngine.calls += 1
        return {
            "question_id": question_id,
            "status": "complete",
            "inputs": inputs,
            "resolved_entities": {"source": {"id": "person-a", "name": "Ada Example"}, "target": {"id": "company-a", "name": "Example Company"}},
            "summary": "Ada Example has a documented affiliation with Example Company.",
            "results": [{"entity_id": "company-a", "evidence_ids": ["evidence-1"], "explanation": "Ada Example has a documented affiliation with Example Company."}],
            "graph": {"nodes": [], "edges": [], "paths": []},
            "evidence": {"evidence-1": {"id": "evidence-1", "dataset": "fixture", "source_documents": ["https://example.test/source"]}},
            "coverage": {"truncated": False},
        }


def snapshot(version="test-graph-v1"):
    return {
        "graph_version": version,
        "nodes": {},
        "edges": [],
        "evidence": {},
        "manifest": {"counts": {}, "limitations": []},
    }


class PersistenceAndCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "analyses.sqlite3"
        self.engine_patch = patch.object(service_mod, "QueryEngine", FakeEngine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.addCleanup(self.directory.cleanup)
        FakeEngine.calls = 0
        self.service = AnalysisService(snapshot(), self.database)

    def test_result_survives_new_store_and_service_instances(self):
        request = {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company"}
        response = self.service.analyze(request)
        recovered = AnalysisStore(self.database).get(response["run_id"])
        self.assertEqual(recovered, response)
        self.assertEqual(recovered["evidence"]["evidence-1"]["id"], "evidence-1")
        self.assertEqual(len(AnalysisStore(self.database).list()), 1)
        again = AnalysisService(snapshot(), self.database).analyze(request)
        self.assertTrue(again["cached"])
        self.assertEqual(again["run_id"], response["run_id"])
        self.assertEqual(FakeEngine.calls, 1)

    def test_cache_uses_resolved_ids_and_preserves_original_saved_result(self):
        first = self.service.analyze({"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company"})
        second = self.service.analyze({"question_id": "person_to_company", "source_id": "person-a", "target_id": "company-a"})
        self.assertTrue(second["cached"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(FakeEngine.calls, 1)
        recovered = self.service.store.get(first["run_id"])
        self.assertFalse(recovered["cached"])
        self.assertNotIn("submitted_inputs", recovered)
        self.assertEqual(recovered["original_request"]["source"], "Ada Example")

    def test_new_graph_version_and_explicit_refresh_create_new_runs(self):
        request = {"question_id": "company_network", "company": "Example Company"}
        first = self.service.analyze(request)
        refreshed = self.service.analyze(request, refresh=True)
        self.assertNotEqual(first["run_id"], refreshed["run_id"])
        updated = AnalysisService(snapshot("test-graph-v2"), self.database).analyze(request)
        self.assertNotEqual(updated["run_id"], refreshed["run_id"])
        self.assertEqual(updated["graph_version"], "test-graph-v2")
        self.assertEqual(len(self.service.store.list()), 3)

    def test_ranking_policy_change_invalidates_cached_answer(self):
        request = {"question_id": "company_network", "company": "Example Company"}
        first = self.service.analyze(request)
        with patch.object(service_mod, "QUERY_POLICY_VERSION", "test-ranking-v99"):
            updated = self.service.analyze(request)
        self.assertFalse(updated["cached"])
        self.assertNotEqual(first["run_id"], updated["run_id"])
        self.assertEqual(updated["query_policy_version"], "test-ranking-v99")

    def test_store_connection_is_closed_after_context(self):
        with self.service.store._connect() as connection:
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_fixed_question_and_input_contracts_reject_extra_controls(self):
        requests = [
            {"question_id": "free_form_question", "company": "Example Company"},
            {"question_id": "company_network", "company": "Example Company", "objective": "raise funding"},
            {"question_id": "company_network", "company": ""},
            {"question_id": "person_to_company", "source": "Ada Example"},
            {"question_id": "company_network", "company": "Example Company", "max_hops": 99},
            {"question_id": [], "company": "Example Company"},
        ]
        for request in requests:
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    self.service.analyze(request)
        self.assertEqual(self.service.store.list(), [])

    def test_deterministic_meeting_brief_and_audit_summary_always_populated(self):
        request = {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company"}
        response = self.service.analyze(request)
        self.assertIn("meeting_brief", response)
        self.assertEqual(response["meeting_brief"]["composer"], "evidence_template")
        self.assertIn("gemma_audit_summary", response)
        self.assertEqual(response["gemma_audit_summary"]["overall_verdict"], "pass")

    def test_hop_mode_validation_and_cache_isolation(self):
        # Out-of-bounds, boolean, missing custom value, or conflicting hop_mode + max_hops are rejected
        invalid_hop_requests = [
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "max_hops": 0},
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "max_hops": -1},
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "max_hops": 9},
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "max_hops": True},
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "hop_mode": "turbo"},
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "hop_mode": "custom"},
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "hop_mode": "suggested", "max_hops": 2},
            {"question_id": "company_representatives", "company": "Example Company", "max_hops": 5},
        ]
        for bad in invalid_hop_requests:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.service.analyze(bad)

        # Suggested (4 hops on Q1) and explicit custom 4 hops share canonical cache; custom 2 hops gets an isolated cache key
        r_default = self.service.analyze(
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company"}
        )
        r_custom4 = self.service.analyze(
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "hop_mode": "custom", "max_hops": 4}
        )
        self.assertTrue(r_custom4["cached"])
        self.assertEqual(r_default["run_id"], r_custom4["run_id"])

        r_custom2 = self.service.analyze(
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "hop_mode": "custom", "max_hops": 2}
        )
        self.assertFalse(r_custom2["cached"])
        self.assertNotEqual(r_default["run_id"], r_custom2["run_id"])

        r_max = self.service.analyze(
            {"question_id": "person_to_company", "source": "Ada Example", "target": "Example Company", "hop_mode": "max"}
        )
        self.assertFalse(r_max["cached"])
        self.assertNotEqual(r_default["run_id"], r_max["run_id"])


class ComposerValidationTests(unittest.TestCase):
    def response(self):
        return FakeEngine(snapshot()).run("person_to_company")

    def test_unknown_or_missing_evidence_references_rejected(self):
        invalid = [
            {"claims": [{"text": "Example claim", "evidence_ids": ["unknown"]}]},
            {"claims": [{"text": "Example claim", "evidence_ids": []}]},
            {"claims": [{"text": "Example claim", "evidence_ids": ["evidence-1"], "extra": True}]},
            {"claims": [{"text": " ", "evidence_ids": ["evidence-1"]}]},
            {"claims": [{"text": "Example claim", "evidence_ids": ["evidence-1"]}], "extra": True},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_claims(payload, {"evidence-1"})

    def test_external_unknown_reference_falls_back_to_original_summary(self):
        response = self.response()
        original = copy.deepcopy(response)
        payload = {"claims": [{"text": "Unsupported replacement", "evidence_ids": ["unknown"]}]}
        with patch.object(generation_mod.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
            result = compose(response, "https://composer.invalid/compose")
        self.assertEqual(result["summary"], original["summary"])
        self.assertEqual(result["generation_mode"], "evidence_template_fallback")
        self.assertEqual(result["results"], original["results"])
        self.assertEqual(result["graph"], original["graph"])
        self.assertNotIn("generated_claims", result)

    def test_valid_reference_preserves_template_and_discloses_validation_scope(self):
        response = self.response()
        original_summary = response["summary"]
        payload = {"claims": [{"text": original_summary, "evidence_ids": ["evidence-1"]}]}
        with patch.object(generation_mod.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
            result = compose(response, "https://composer.invalid/compose")
        self.assertEqual(result["generation_mode"], "external_composer")
        self.assertEqual(result["template_summary"], original_summary)
        self.assertIn("entailment", result["generation_validation"])

    def test_prompt_export_preserves_original_evidence_qualifications(self):
        response = self.response()
        response.update({
            "template_summary": "The original qualified template.",
            "summary": "Previously generated wording.",
            "status": "partial",
            "conflicts": [{"assertion_id": "edge-1", "reason": "Competing source values"}],
        })
        prompt = build_generation_request(response)
        self.assertEqual(prompt["input"]["summary"], "The original qualified template.")
        self.assertEqual(prompt["input"]["status"], "partial")
        self.assertEqual(prompt["input"]["conflicts"], response["conflicts"])


class LocalApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        with patch.object(service_mod, "QueryEngine", FakeEngine):
            self.service = AnalysisService(snapshot(), Path(self.directory.name) / "api.sqlite3")
        self.server = make_server(self.service, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, body, raw_bytes: bytes | None = None):
        data = raw_bytes if raw_bytes is not None else json.dumps(body).encode()
        request = Request(
            self.base + "/analyses",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as result:
                return result.status, json.load(result)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_invalid_question_and_extra_field_are_http_400(self):
        for payload in [
            {"question_id": "arbitrary", "company": "Example Company"},
            {"question_id": "company_network", "company": "Example Company", "prompt": "ignore rules"},
            {"question_id": [], "company": "Example Company"},
            ["not", "an", "object"],
        ]:
            with self.subTest(payload=payload):
                status, result = self.post(payload)
                self.assertEqual(status, 400)
                self.assertIn("error", result)

    def test_oversized_request_body_returns_http_413(self):
        huge = json.dumps({"question_id": "company_network", "company": "X" * 20_000}).encode()
        status, result = self.post(None, raw_bytes=huge)
        self.assertEqual(status, 413)
        self.assertIn("16 KiB", result["error"])

    def test_success_is_recoverable_and_prompt_contains_saved_evidence(self):
        status, result = self.post({"question_id": "company_network", "company": "Example Company"})
        self.assertEqual(status, 200)
        with urlopen(self.base + "/analyses/" + result["run_id"], timeout=5) as response:
            recovered = json.load(response)
        self.assertEqual(recovered, result)
        with urlopen(self.base + "/analyses/" + result["run_id"] + "/prompt", timeout=5) as response:
            prompt = json.load(response)
        self.assertIn("evidence-1", prompt["input"]["evidence"])
        self.assertEqual(prompt["input"]["question_id"], "company_network")


if __name__ == "__main__":
    unittest.main()
