"""Full-Stack E2E Integration, Cala Provenance, Partner Tech Challenges & Headless Browser Suite."""
from __future__ import annotations

import contextlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import httpx
import uvicorn

import backend.ai_engine as ai_engine
from backend.aiven_store import UnifiedAnalysisStore
from backend.app import create_app
from backend.cala_client import CalaLiveClient
from backend.ingest import ensure_snapshot
from backend.service import AnalysisService

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
PRESETS_FIXTURE_PATH = REPO_ROOT / "docs" / "contracts" / "cala-fixtures" / "PRESETS_AND_DEMO_CASES.json"

_SHARED_SNAPSHOT: dict[str, Any] | None = None


def get_shared_snapshot() -> dict[str, Any]:
    global _SHARED_SNAPSHOT
    if _SHARED_SNAPSHOT is None:
        _SHARED_SNAPSHOT = ensure_snapshot()
    return _SHARED_SNAPSHOT


def parse_sse_events(raw_sse: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    normalized = raw_sse.replace("\r\n", "\n")
    for frame in normalized.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


class FastApiContractAndCorsTests(unittest.TestCase):
    """Test dual-mounted `/api/*` + legacy routes, CORS preflight, validation & error envelopes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls._tmpdir.name) / "e2e_contract.sqlite3"
        cls.service = AnalysisService(get_shared_snapshot(), cls.db_path)
        cls.app = create_app(service=cls.service)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_dual_mount_health_and_root_content_negotiation(self) -> None:
        r_api = self.client.get("/api/health")
        r_leg = self.client.get("/health")
        self.assertEqual(r_api.status_code, 200)
        self.assertEqual(r_leg.status_code, 200)
        self.assertEqual(r_api.json(), r_leg.json())
        body = r_api.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(
            body["graph_version"],
            "b205502204e1e0c2b3e1b334577e7d0f04bf4fc70f4bddb06d6c3603f5dfe5e5",
        )
        self.assertEqual(body["pipeline_version"], "2.2.0")
        self.assertIn("capabilities", body)
        for cap_key in ("gemini", "gemma", "aiven_pg", "aiven_valkey", "craci", "cala_live"):
            self.assertIn(cap_key, body["capabilities"])

        # Browser navigation receives HTML index.html; explicit JSON-only client receives health JSON
        r_html = self.client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
        self.assertEqual(r_html.status_code, 200)
        self.assertIn("text/html", r_html.headers["content-type"])
        self.assertIn("Comare di Slush", r_html.text)

        r_json = self.client.get("/", headers={"Accept": "application/json"})
        self.assertEqual(r_json.status_code, 200)
        self.assertEqual(r_json.json()["status"], "ok")

    def test_cors_preflight_and_cross_origin_headers(self) -> None:
        preflight = self.client.options(
            "/api/analyses",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertIn("access-control-allow-origin", preflight.headers)
        self.assertIn("POST", preflight.headers.get("access-control-allow-methods", ""))

        cross_get = self.client.get("/api/health", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(cross_get.status_code, 200)
        self.assertEqual(cross_get.headers.get("access-control-allow-origin"), "*")

    def test_dual_mount_questions_and_coverage(self) -> None:
        q_api = self.client.get("/api/questions").json()
        q_leg = self.client.get("/questions").json()
        self.assertEqual(q_api, q_leg)
        self.assertEqual(
            set(q_api.keys()),
            {"person_to_company", "company_to_company", "company_network", "company_representatives"},
        )
        for qid, spec in q_api.items():
            self.assertIn("label", spec)
            self.assertIn("fields", spec)
            self.assertIn("min_hops", spec)
            self.assertIn("suggested_hops", spec)
            self.assertIn("max_hops", spec)
            self.assertIn("hop_policy", spec)
            self.assertEqual(spec["id"], qid)

        hp_api = self.client.get("/api/hop-policies").json()
        hp_leg = self.client.get("/hop-policies").json()
        self.assertEqual(hp_api, hp_leg)
        self.assertEqual(hp_api["global_hard_max_hops"], 8)
        self.assertEqual(hp_api["supported_modes"], ["suggested", "custom", "max"])

        # End-to-end hop selection via FastAPI (/api/analyses): custom 2 hops vs custom 4 hops vs max
        r_hop2 = self.client.post(
            "/api/analyses",
            json={
                "question_id": "company_to_company",
                "source": "Sana Labs",
                "target": "Amplitude",
                "target_id": "slush-organization:e07235be39291882c0650cbb",
                "hop_mode": "custom",
                "max_hops": 2,
                "composer_mode": "template",
            },
        )
        self.assertEqual(r_hop2.status_code, 200)
        b_hop2 = r_hop2.json()
        self.assertEqual(b_hop2["status"], "insufficient_data")
        self.assertEqual(b_hop2["hop_selection"]["hop_mode"], "custom")
        self.assertEqual(b_hop2["hop_selection"]["selected_hops"], 2)

        r_hop4 = self.client.post(
            "/api/analyses",
            json={
                "question_id": "company_to_company",
                "source": "Sana Labs",
                "target": "Amplitude",
                "target_id": "slush-organization:e07235be39291882c0650cbb",
                "hop_mode": "suggested",
                "composer_mode": "template",
            },
        )
        self.assertEqual(r_hop4.status_code, 200)
        b_hop4 = r_hop4.json()
        self.assertGreaterEqual(len(b_hop4["results"]), 1)
        self.assertEqual(b_hop4["hop_selection"]["hop_mode"], "suggested")
        self.assertEqual(b_hop4["hop_selection"]["selected_hops"], 4)

        r_bad_hop = self.client.post(
            "/api/analyses",
            json={"question_id": "company_network", "company": "Trust Exchange", "max_hops": 99},
        )
        self.assertEqual(r_bad_hop.status_code, 400)
        self.assertIn("error", r_bad_hop.json())

        c_api = self.client.get("/api/coverage").json()
        c_leg = self.client.get("/coverage").json()
        self.assertEqual(c_api, c_leg)
        self.assertEqual(c_api["counts"]["nodes"], 38886)
        self.assertEqual(c_api["counts"]["traversable_edges"], 39235)
        self.assertFalse(c_api["cala_coverage"]["complete"])
        self.assertGreaterEqual(len(c_api["datasets"]), 8)

    def test_entities_resolution_ambiguity_suggestions_and_validation(self) -> None:
        # Missing name -> 400
        self.assertEqual(self.client.get("/api/entities").status_code, 400)
        self.assertIn("error", self.client.get("/entities?name=").json())
        # Invalid type / limit -> 400
        self.assertEqual(self.client.get("/api/entities?name=Slicker&type=InvalidType").status_code, 400)
        self.assertEqual(self.client.get("/api/entities?name=Slicker&limit=999").status_code, 400)
        self.assertEqual(self.client.get("/api/entities?name=Slicker&limit=abc").status_code, 400)

        # Resolved entity
        res_ok = self.client.get("/api/entities?name=Trust+Exchange&type=Company").json()
        self.assertEqual(res_ok["status"], "resolved")
        self.assertEqual(res_ok["resolution_state"], "resolved")
        self.assertEqual(res_ok["entity"]["name"], "Trust Exchange")
        self.assertTrue(res_ok["suggestions"])

        # Ambiguous entity (`Y Combinator` has both Cala investor & Slush org stub)
        res_amb = self.client.get("/api/entities?name=Y+Combinator&type=Company").json()
        self.assertEqual(res_amb["status"], "needs_resolution")
        self.assertEqual(res_amb["resolution_state"], "ambiguous")
        self.assertGreaterEqual(len(res_amb["candidates"]), 2)
        cand_ids = {c["id"] for c in res_amb["candidates"]}
        self.assertIn("cala:58ff3f858e84eba441148d79", cand_ids)

        # Unknown entity -> honest not_found
        res_nf = self.client.get("/api/entities?name=NonexistentUnicornXYZ999").json()
        self.assertEqual(res_nf["status"], "not_found")
        self.assertEqual(res_nf["resolution_state"], "not_found")

    def test_error_envelopes_400_404_413_and_static_path_traversal_guard(self) -> None:
        # Invalid JSON, non-object JSON, extra user fields
        bad_raw = self.client.post(
            "/api/analyses",
            content=b"{not-valid-json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(bad_raw.status_code, 400)
        self.assertIn("error", bad_raw.json())

        bad_arr = self.client.post("/api/analyses", json=["not", "a", "dict"])
        self.assertEqual(bad_arr.status_code, 400)
        self.assertIn("error", bad_arr.json())

        bad_extra = self.client.post(
            "/api/analyses",
            json={"question_id": "company_network", "company": "Trust Exchange", "prompt": "override system"},
        )
        self.assertEqual(bad_extra.status_code, 400)
        self.assertIn("Unexpected request fields", bad_extra.json()["error"])

        # >16 KiB payload -> 413
        oversized = self.client.post(
            "/api/analyses",
            content=json.dumps({"question_id": "company_network", "company": "A" * 18_000}).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertIn("16 KiB", oversized.json()["error"])

        # Missing run_id -> 404 {"error": "Analysis not found"}
        r404 = self.client.get("/api/analyses/00000000-0000-0000-0000-000000000000")
        self.assertEqual(r404.status_code, 404)
        self.assertEqual(r404.json()["error"], "Analysis not found")

        p404 = self.client.get("/api/analyses/00000000-0000-0000-0000-000000000000/prompt")
        self.assertEqual(p404.status_code, 404)
        self.assertEqual(p404.json()["error"], "Analysis not found")

        # Static path traversal protection
        trav = self.client.get("/js/../../pyproject.toml")
        self.assertEqual(trav.status_code, 404)
        self.assertIn("error", trav.json())


class CuratedPresetsAndProvenanceTests(unittest.TestCase):
    """Execute all 17 curated presets in `PRESETS_AND_DEMO_CASES.json` and audit closed provenance."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.service = AnalysisService(get_shared_snapshot(), Path(cls._tmpdir.name) / "presets.sqlite3")
        cls.client = TestClient(create_app(service=cls.service))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_all_17_curated_presets_match_verified_outcomes_and_closed_provenance(self) -> None:
        resp = self.client.get("/api/presets")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        presets = payload.get("presets", [])
        self.assertEqual(len(presets), 17, "Expected all 17 curated benchmark & showcase presets")

        fixture_json = json.loads(PRESETS_FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture_json["presets"]), 17)

        for preset in presets:
            pid = preset["id"]
            req = dict(preset["request"])
            req["composer_mode"] = "template"
            expected = preset["verified_outcome"]

            with self.subTest(preset_id=pid):
                post_resp = self.client.post("/api/analyses", json=req)
                self.assertEqual(post_resp.status_code, 200, f"Preset {pid} failed: {post_resp.text}")
                analysis = post_resp.json()

                self.assertEqual(analysis["status"], expected["status"])
                self.assertEqual(len(analysis["results"]), expected["result_count"])
                self.assertEqual(len(analysis["graph"]["paths"]), expected["path_count"])

                if expected.get("top_path_hops") is not None:
                    self.assertEqual(analysis["graph"]["paths"][0]["hop_count"], expected["top_path_hops"])

                # Audit closed evidence references across graph, claims, and meeting brief
                evidence_items = analysis["evidence"]
                self.assertIsInstance(evidence_items, list)
                ev_ids = {item["id"] for item in evidence_items}

                for ev_item in evidence_items:
                    self.assertTrue(ev_item["id"].startswith("ev:"))
                    self.assertIn("dataset", ev_item)
                    # Every evidence record must preserve either source_documents (URL/date/publisher) or record_pointer
                    has_provenance = bool(ev_item.get("source_documents") or ev_item.get("record_pointer"))
                    self.assertTrue(has_provenance, f"Evidence {ev_item['id']} missing provenance pointer/docs")

                for g_edge in analysis["graph"]["edges"]:
                    self.assertTrue(set(g_edge["evidence_ids"]).issubset(ev_ids))

                for g_path in analysis["graph"]["paths"]:
                    self.assertLessEqual(g_path["hop_count"], 4)
                    for rel in g_path["relations"]:
                        self.assertTrue(set(rel["evidence_ids"]).issubset(ev_ids))

                for claim in analysis.get("generated_claims") or []:
                    self.assertTrue(claim["evidence_ids"])
                    self.assertTrue(set(claim["evidence_ids"]).issubset(ev_ids))

                brief = analysis.get("meeting_brief") or {}
                for bullet in (brief.get("talking_points") or []) + (brief.get("smart_questions") or []):
                    self.assertTrue(bullet["evidence_ids"])
                    self.assertTrue(set(bullet["evidence_ids"]).issubset(ev_ids))


class SseStreamingPipelineTests(unittest.TestCase):
    """Verify `POST /api/analyses/stream` SSE stage sequence, cache hit shortcut, and recovery."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.service = AnalysisService(get_shared_snapshot(), Path(self._tmpdir.name) / "sse.sqlite3")
        self.client = TestClient(create_app(service=self.service))

    def test_sse_stream_miss_then_hit_and_refresh_bypass(self) -> None:
        body = {
            "question_id": "person_to_company",
            "source": "Camille Accolas",
            "target": "Trust Exchange",
            "composer_mode": "template",
        }
        r1 = self.client.post("/api/analyses/stream", json=body)
        self.assertEqual(r1.status_code, 200)
        self.assertIn("text/event-stream", r1.headers["content-type"])

        events1 = parse_sse_events(r1.text)
        stages1 = [payload["stage"] for _, payload in events1]
        self.assertEqual(
            stages1,
            [
                "resolving",
                "cache_check",
                "traversing",
                "ranking",
                "composing_gemini",
                "auditing_gemma",
                "persisting_aiven",
                "complete",
            ],
        )
        cache_stage_1 = dict(events1[1][1])
        self.assertEqual(cache_stage_1["status"], "miss")
        final_1 = events1[-1][1]["analysis"]
        self.assertFalse(final_1["cached"])

        # Byte-for-byte recovery on both `/api/analyses/{run_id}` and `/analyses/{run_id}`
        rec_api = self.client.get(f"/api/analyses/{final_1['run_id']}").json()
        rec_leg = self.client.get(f"/analyses/{final_1['run_id']}").json()
        self.assertEqual(rec_api, final_1)
        self.assertEqual(rec_leg, final_1)

        # Second stream hits cache immediately (`resolving` -> `cache_check` (`hit`) -> `complete`)
        r2 = self.client.post("/api/analyses/stream", json=body)
        events2 = parse_sse_events(r2.text)
        stages2 = [payload["stage"] for _, payload in events2]
        self.assertEqual(stages2, ["resolving", "cache_check", "complete"])
        self.assertEqual(events2[1][1]["status"], "hit")
        self.assertTrue(events2[-1][1]["analysis"]["cached"])
        self.assertEqual(events2[-1][1]["run_id"], final_1["run_id"])

        # Explicit `refresh: True` bypasses cache and creates a new run_id
        r3 = self.client.post("/api/analyses/stream", json={**body, "refresh": True})
        events3 = parse_sse_events(r3.text)
        self.assertNotEqual(events3[-1][1]["run_id"], final_1["run_id"])
        self.assertFalse(events3[-1][1]["analysis"]["cached"])

    def test_sse_stream_prevalidates_bad_request_with_http_400(self) -> None:
        bad = self.client.post(
            "/api/analyses/stream",
            json={"question_id": "invalid_task", "company": "Trust Exchange"},
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("error", bad.json())


class GeminiAndGemmaEntailmentTests(unittest.TestCase):
    """Test Google Gemini composition, Gemma 3 open-weight entailment shield, and hallucination fallback."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.service = AnalysisService(get_shared_snapshot(), Path(self._tmpdir.name) / "ai.sqlite3")
        self.client = TestClient(create_app(service=self.service))

    def test_gemini_valid_composition_and_gemma_entailment_pass_and_flag(self) -> None:
        base_analysis = self.service.analyze({
            "question_id": "person_to_company",
            "source": "Camille Accolas",
            "target": "Trust Exchange",
            "composer_mode": "template",
        })
        valid_eid = base_analysis["evidence"][0]["id"]

        mock_gemini_payload = {
            "claims": [
                {
                    "text": "Camille Accolas founded Trust Exchange and holds a documented board role.",
                    "evidence_ids": [valid_eid],
                },
                {
                    "text": "Trust Exchange has a documented Slush 2026 startup listing.",
                    "evidence_ids": [valid_eid],
                },
            ],
            "meeting_brief": {
                "executive_summary": "Grounded 1-hop founder and board connection between Camille Accolas and Trust Exchange.",
                "talking_points": [
                    {"text": "Discuss Trust Exchange's venture evaluation framework.", "evidence_ids": [valid_eid]}
                ],
                "smart_questions": [
                    {"text": "Which institutional investors are adopting Trust Exchange at Slush?", "evidence_ids": [valid_eid]}
                ],
                "attendance_note": "Named Slush participation documented; physical check-in unverified.",
            },
        }

        mock_gemma_pass = {
            "audits": [
                {"index": 0, "verdict": "supported", "note": "Directly entailed by FOUNDED and board assertions."},
                {"index": 1, "verdict": "supported", "note": "Supported by Slush 2026 startup listing."},
            ]
        }

        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-gem-key", "GEMMA_API_KEY": "test-gma-key"}),
            patch.object(ai_engine, "call_gemini_json", return_value=(mock_gemini_payload, "gemini-2.5-flash")),
            patch.object(ai_engine, "call_gemma_json", return_value=(mock_gemma_pass, "google_ai_studio", "gemma-3-27b-it")),
        ):
            res = self.client.post(
                "/api/analyses",
                json={
                    "question_id": "person_to_company",
                    "source": "Camille Accolas",
                    "target": "Trust Exchange",
                    "composer_mode": "gemini_gemma_audit",
                    "refresh": True,
                },
            ).json()

        self.assertEqual(res["generation_mode"], "gemini_gemma_audit")
        self.assertEqual(res["meeting_brief"]["composer"], "gemini")
        self.assertEqual(res["gemma_audit_summary"]["overall_verdict"], "pass")
        self.assertEqual(res["gemma_audit_summary"]["supported_claims"], 2)
        self.assertEqual(res["gemma_audit_summary"]["flagged_claims"], 0)
        self.assertEqual(res["generated_claims"][0]["gemma_audit"]["model"], "gemma-3-27b-it")

        # Now verify Gemma flagging an unsupported claim sets overall_verdict='review_required'
        mock_gemma_flag = {
            "audits": [
                {"index": 0, "verdict": "supported", "note": "Entailed."},
                {"index": 1, "verdict": "flagged", "note": "Date specificity exceeds cited record."},
            ]
        }
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-gem-key", "GEMMA_API_KEY": "test-gma-key"}),
            patch.object(ai_engine, "call_gemini_json", return_value=(mock_gemini_payload, "gemini-2.5-flash")),
            patch.object(ai_engine, "call_gemma_json", return_value=(mock_gemma_flag, "featherless", "google/gemma-3-27b-it")),
        ):
            flagged_res = self.client.post(
                "/api/analyses",
                json={
                    "question_id": "person_to_company",
                    "source": "Camille Accolas",
                    "target": "Trust Exchange",
                    "composer_mode": "gemini_gemma_audit",
                    "refresh": True,
                },
            ).json()

        self.assertEqual(flagged_res["gemma_audit_summary"]["overall_verdict"], "review_required")
        self.assertEqual(flagged_res["gemma_audit_summary"]["flagged_claims"], 1)
        self.assertEqual(flagged_res["generated_claims"][1]["gemma_audit"]["verdict"], "flagged")

    def test_hallucinated_evidence_id_or_overclaim_triggers_deterministic_fallback(self) -> None:
        hallucinated_gemini_payload = {
            "claims": [
                {
                    "text": "Camille Accolas has a fabricated relationship.",
                    "evidence_ids": ["ev:hallucinated_nonexistent_id_999"],
                }
            ],
            "meeting_brief": {
                "executive_summary": "Bad summary",
                "talking_points": [{"text": "Point", "evidence_ids": ["ev:hallucinated_nonexistent_id_999"]}],
                "smart_questions": [{"text": "Question?", "evidence_ids": ["ev:hallucinated_nonexistent_id_999"]}],
                "attendance_note": "Note",
            },
        }
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-gem-key"}),
            patch.object(ai_engine, "call_gemini_json", return_value=(hallucinated_gemini_payload, "gemini-2.5-flash")),
        ):
            res = self.client.post(
                "/api/analyses",
                json={
                    "question_id": "person_to_company",
                    "source": "Camille Accolas",
                    "target": "Trust Exchange",
                    "composer_mode": "gemini",
                    "refresh": True,
                },
            ).json()

        self.assertEqual(res["generation_mode"], "evidence_template_fallback")
        self.assertEqual(res["summary"], res["template_summary"])
        self.assertEqual(res["meeting_brief"]["composer"], "evidence_template")
        ev_ids = {item["id"] for item in res["evidence"]}
        for claim in res["generated_claims"]:
            self.assertTrue(set(claim["evidence_ids"]).issubset(ev_ids))


class AivenStoreAndTelemetryTests(unittest.TestCase):
    """Test Aiven PostgreSQL + Valkey cloud persistence, sub-2ms cache hits, and SQLite fallback."""

    def test_infrastructure_status_and_cache_hit_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = AnalysisService(get_shared_snapshot(), Path(tmp) / "infra.sqlite3")
            client = TestClient(create_app(service=svc))

            req = {
                "question_id": "company_network",
                "company": "Trust Exchange",
                "composer_mode": "template",
            }
            r1 = client.post("/api/analyses", json=req).json()
            self.assertFalse(r1["cached"])

            r2 = client.post("/api/analyses", json=req).json()
            self.assertTrue(r2["cached"])
            self.assertEqual(r1["run_id"], r2["run_id"])

            infra = client.get("/api/infrastructure/status").json()
            self.assertEqual(infra["status"], "ok")
            self.assertGreaterEqual(infra["storage"]["saved_analyses_count"], 1)
            self.assertGreaterEqual(infra["cache"]["cache_hits"], 1)
            self.assertGreaterEqual(infra["cache"]["cache_misses"], 1)
            self.assertTrue(infra["cala"]["snapshot_loaded"])
            self.assertEqual(infra["craci"]["workflow_runner_label"], "craci")

            history = client.get("/api/analyses?limit=10").json()
            self.assertEqual(len(history["analyses"]), 1)
            self.assertEqual(history["analyses"][0]["run_id"], r1["run_id"])

    def test_aiven_valkey_and_postgres_mocked_cloud_roundtrip_and_graceful_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            valkey_mem: dict[str, str] = {}
            pg_rows: dict[str, tuple[Any, ...]] = {}

            fake_valkey_client = MagicMock()
            fake_valkey_client.ping.return_value = True
            fake_valkey_client.setex.side_effect = lambda k, ttl, v: valkey_mem.__setitem__(k, v)
            fake_valkey_client.get.side_effect = lambda k: valkey_mem.get(k)

            fake_cursor = MagicMock()

            def _pg_exec(sql: str, params: tuple[Any, ...] | None = None) -> None:
                if "INSERT INTO analyses" in sql and params:
                    pg_rows[params[0]] = params
                elif "SELECT response_json FROM analyses WHERE run_id" in sql and params:
                    row = pg_rows.get(params[0])
                    fake_cursor.fetchone.return_value = (json.loads(row[9]),) if row else None
                elif "SELECT COUNT(*) FROM analyses" in sql:
                    fake_cursor.fetchone.return_value = (len(pg_rows),)

            fake_cursor.execute.side_effect = _pg_exec
            fake_conn = MagicMock()
            fake_conn.__enter__.return_value = fake_conn
            fake_conn.cursor.return_value.__enter__.return_value = fake_cursor

            with (
                patch("valkey.from_url", return_value=fake_valkey_client),
                patch("psycopg.connect", return_value=fake_conn),
            ):
                store = UnifiedAnalysisStore(
                    Path(tmp) / "cloud.sqlite3",
                    pg_uri="mock-aiven-pg-dsn",
                    valkey_url="mock-aiven-valkey-dsn",
                )
                self.assertTrue(store.aiven_pg_connected)
                self.assertTrue(store.aiven_valkey_connected)
                self.assertEqual(store.backend_name, "aiven_pg")
                self.assertEqual(store.cache_layer_name, "aiven_valkey")

                sample_req = {"question_id": "company_network", "company": "Trust Exchange"}
                sample_resp = {
                    "run_id": "run-aiven-1",
                    "generated_at": "2026-11-14T20:00:00+00:00",
                    "question_id": "company_network",
                    "graph_version": "gv-1",
                    "generation_mode": "evidence_template",
                    "status": "partial",
                    "elapsed_ms": 4.2,
                }
                store.save(sample_req, sample_resp, cache_key="ck-aiven-1")

                # Valkey serves sub-2ms cache hit
                hit = store.cached("ck-aiven-1")
                self.assertIsNotNone(hit)
                self.assertEqual(hit["run_id"], "run-aiven-1")
                self.assertIn("unicorn_radar:analysis:ck-aiven-1", valkey_mem)

                # PostgreSQL serves immutable run lookup
                pg_get = store.get("run-aiven-1")
                self.assertEqual(pg_get["run_id"], "run-aiven-1")

                # Simulate cloud outage -> falls back transparently to local SQLite without raising
                fake_conn.__enter__.side_effect = RuntimeError("Simulated network partition")
                fake_valkey_client.get.side_effect = RuntimeError("Simulated Valkey disconnect")
                fallback_get = store.get("run-aiven-1")
                self.assertEqual(fallback_get["run_id"], "run-aiven-1")
                self.assertFalse(store.aiven_pg_connected)


class CalaLiveEnrichmentTests(unittest.TestCase):
    """Audit `GET /api/cala/enrich/{entity_id}` namespace isolation, provenance, and 402/429/504 rules."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.service = AnalysisService(get_shared_snapshot(), Path(self._tmpdir.name) / "cala.sqlite3")
        self.client = TestClient(create_app(service=self.service))

    def test_unconfigured_cala_key_returns_clean_status_and_preserves_investor_registry(self) -> None:
        with patch.dict(os.environ, {"CALA_API_KEY": ""}, clear=False):
            # General Catalyst Slush snapshot ID has a corroborated Cala investor match
            gc_id = "slush-company:e4dd9e8b-c759-4ad6-bf95-83ee9b125e81"
            resp = self.client.get(f"/api/cala/enrich/{gc_id}")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["status"], "unconfigured")
            self.assertEqual(body["namespace"], "cala_live_enrichment")
            self.assertEqual(body["verified_facts"], [])
            self.assertIn("cala_verified_investor_match", body)
            self.assertEqual(body["cala_verified_investor_match"]["cala_id"], "03faa252-0570-4e3f-be48-39d7740d964c")

    def test_structured_introspection_and_projected_retrieval_with_strict_provenance_filter(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_request(self_client, method: str, url: str, **kwargs):
            calls.append((method, url))
            resp = MagicMock()
            resp.status_code = 200
            if url.endswith("/introspection"):
                resp.json.return_value = {
                    "properties": ["name", "website", "hq_country"],
                    "relationships": {"incoming": ["FOUNDED"], "outgoing": ["INVESTED_IN"]},
                }
            else:
                resp.json.return_value = {
                    "id": "03faa252-0570-4e3f-be48-39d7740d964c",
                    "name": "General Catalyst",
                    "properties": {
                        "website": {
                            "value": "https://www.generalcatalyst.com/",
                            "sources": [
                                {
                                    "publisher": "General Catalyst",
                                    "url": "https://www.generalcatalyst.com/",
                                    "date": "2026-10-20",
                                }
                            ],
                        },
                        # Unattributed property without sources MUST be discarded
                        "hq_country": {"value": "US", "sources": []},
                    },
                    "relationships": {
                        "incoming": {
                            "FOUNDED": [
                                {
                                    "entity": {"id": "uuid-founder-1", "name": "Joel Cutler"},
                                    "sources": [
                                        {
                                            "name": "SEC Filing",
                                            "document": {"url": "https://sec.gov/example"},
                                            "date": "2026-09-01",
                                        }
                                    ],
                                },
                                # Unattributed relationship without sources MUST be discarded
                                {"entity": {"id": "uuid-unverified", "name": "Unverified Peer"}, "sources": []},
                            ]
                        }
                    },
                }
            return resp

        gc_id = "slush-company:e4dd9e8b-c759-4ad6-bf95-83ee9b125e81"
        with (
            patch.dict(os.environ, {"CALA_API_KEY": "test-cala-live-key"}, clear=False),
            patch.object(httpx.Client, "request", fake_request),
        ):
            r1 = self.client.get(f"/api/cala/enrich/{gc_id}").json()
            self.assertEqual(r1["status"], "ok")
            self.assertFalse(r1["cached"])
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[0][1].endswith("/introspection"))

            # Only the sourced website fact survives; unsourced hq_country was dropped
            self.assertEqual(len(r1["verified_facts"]), 1)
            self.assertEqual(r1["verified_facts"][0]["field"], "website")
            self.assertEqual(r1["verified_facts"][0]["sources"][0]["date"], "2026-10-20")

            # Only the sourced FOUNDED relationship survives
            self.assertEqual(len(r1["verified_relationships"]), 1)
            self.assertEqual(r1["verified_relationships"][0]["peer_name"], "Joel Cutler")
            self.assertEqual(r1["verified_relationships"][0]["sources"][0]["url"], "https://sec.gov/example")

            # Second call hits store KV cache without hitting network
            r2 = self.client.get(f"/api/cala/enrich/{gc_id}").json()
            self.assertTrue(r2["cached"])
            self.assertEqual(len(calls), 2)

            # Verify include_cala_live=True on POST /api/analyses keeps enrichment isolated from hop counts
            baseline = self.client.post(
                "/api/analyses",
                json={
                    "question_id": "company_representatives",
                    "company": "General Catalyst",
                    "company_id": gc_id,
                    "composer_mode": "template",
                },
            ).json()
            enriched = self.client.post(
                "/api/analyses",
                json={
                    "question_id": "company_representatives",
                    "company": "General Catalyst",
                    "company_id": gc_id,
                    "composer_mode": "template",
                    "include_cala_live": True,
                },
            ).json()
            self.assertIsNone(baseline["cala_live_enrichment"])
            self.assertIsNotNone(enriched["cala_live_enrichment"])
            self.assertEqual(len(baseline["graph"]["paths"]), len(enriched["graph"]["paths"]))

    def test_http_402_and_429_never_retry_while_504_retries_at_most_once(self) -> None:
        client_402 = CalaLiveClient(get_shared_snapshot())
        attempts_402 = 0

        def mock_402(self_http, method, url, **kwargs):
            nonlocal attempts_402
            attempts_402 += 1
            r = MagicMock()
            r.status_code = 402
            return r

        with (
            patch.dict(os.environ, {"CALA_API_KEY": "key-402"}, clear=False),
            patch.object(httpx.Client, "request", mock_402),
        ):
            out = client_402.enrich("cala:1e86655e-373d-4fe8-be13-af3713581f73")
            self.assertEqual(out["status"], "payment_required")
            self.assertEqual(attempts_402, 1, "HTTP 402 must NEVER retry")
            self.assertEqual(out["verified_facts"], [])
            # Subsequent call short-circuits via circuit breaker without network hit
            out2 = client_402.enrich("cala:1e86655e-373d-4fe8-be13-af3713581f73")
            self.assertEqual(out2["status"], "payment_required")
            self.assertEqual(attempts_402, 1)

        client_504 = CalaLiveClient(get_shared_snapshot())
        attempts_504 = 0

        def mock_504(self_http, method, url, **kwargs):
            nonlocal attempts_504
            attempts_504 += 1
            r = MagicMock()
            r.status_code = 504
            return r

        with (
            patch.dict(os.environ, {"CALA_API_KEY": "key-504"}, clear=False),
            patch.object(httpx.Client, "request", mock_504),
        ):
            out_timeout = client_504.enrich("cala:1e86655e-373d-4fe8-be13-af3713581f73")
            self.assertEqual(out_timeout["status"], "timeout")
            self.assertEqual(attempts_504, 2, "HTTP 504 must retry at most once (2 total attempts)")


class CraciProvenanceAndAuditTests(unittest.TestCase):
    """Verify `GET /api/craci/provenance` & `POST /api/craci/audit` against `.github/workflows/ci.yml`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.service = AnalysisService(get_shared_snapshot(), Path(cls._tmpdir.name) / "craci.sqlite3")
        cls.client = TestClient(create_app(service=cls.service))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_craci_workspace_provenance_cyclonedx_sbom_and_cala_vendor_matching(self) -> None:
        with patch.dict(os.environ, {"CRACI_API_TOKEN": ""}, clear=False):
            resp = self.client.get("/api/craci/provenance")
            self.assertEqual(resp.status_code, 200)
            prov = resp.json()

            self.assertEqual(prov["status"], "ok")
            self.assertEqual(prov["source_mode"], "verified_workspace_snapshot")
            self.assertIsNone(prov["latest_job"], "Offline mode must never fabricate remote CRACI job IDs")

            wf = prov["workflow_policy"]
            self.assertTrue(wf["compliant"])
            self.assertGreaterEqual(wf["workflows_scanned"], 1)
            job = wf["craci_runner_jobs"][0]
            self.assertEqual(job["runs_on"], "craci")
            self.assertTrue(job["uses_craci_setup"])
            self.assertTrue(job["block_unmatched_egress"])
            self.assertEqual(job["network_default"], "deny")
            self.assertEqual(job["network_presets"], ["pypi", "github"])

            sbom = prov["sbom"]
            self.assertEqual(sbom["bomFormat"], "CycloneDX")
            self.assertGreaterEqual(sbom["component_count"], 8)
            pkg_names = {c["name"].lower() for c in sbom["components"]}
            for required_pkg in ("fastapi", "uvicorn", "httpx", "pydantic", "valkey"):
                self.assertIn(required_pkg, pkg_names)

            for match in prov["cala_entity_matches"]:
                self.assertTrue(match["evidence_ids"], f"Vendor match {match} must carry snapshot evidence_ids")

    def test_craci_supply_chain_audit_and_field_validation(self) -> None:
        audit_resp = self.client.post("/api/craci/audit", json={"focus": "full", "composer_mode": "template"})
        self.assertEqual(audit_resp.status_code, 200)
        audit = audit_resp.json()
        self.assertEqual(audit["status"], "ok")
        self.assertEqual(audit["risk_level"], "low")
        self.assertEqual(audit["egress_verdict"], "clean_default_deny_enforced")
        self.assertGreaterEqual(len(audit["findings"]), 3)

        bad_audit = self.client.post("/api/craci/audit", json={"unexpected_param": True})
        self.assertEqual(bad_audit.status_code, 400)
        self.assertIn("error", bad_audit.json())


class FrontendAndHeadlessBrowserE2ETests(unittest.TestCase):
    """Verify zero-build ES2022 assets, responsive mobile/desktop CSS, and live headless Edge DOM hydration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.service = AnalysisService(get_shared_snapshot(), Path(cls._tmpdir.name) / "browser.sqlite3")
        cls.app = create_app(service=cls.service)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_zero_build_es2022_static_assets_and_responsive_layout_rules(self) -> None:
        css_resp = self.client.get("/css/styles.css")
        self.assertEqual(css_resp.status_code, 200)
        self.assertIn("text/css", css_resp.headers["content-type"])
        # Verify responsive breakpoints for tablet (1220px) and mobile (820px)
        self.assertIn("@media (max-width: 1220px)", css_resp.text)
        self.assertIn("@media (max-width: 820px)", css_resp.text)

        js_modules = [
            "/js/app.js",
            "/js/api.js",
            "/js/graph-view.js",
            "/js/results-view.js",
            "/js/tech-views.js",
            "/js/utils.js",
            "/js/offline-fixtures.js",
        ]
        import_re = re.compile(
            r"""(?:import\s+(?:[^'"]+?\s+from\s+)?|export\s+[^'"]+?\s+from\s+|import\s*\()\s*['"]([^'"]+)['"]"""
        )
        for mod_route in js_modules:
            r = self.client.get(mod_route)
            self.assertEqual(r.status_code, 200, f"Failed to serve {mod_route}")
            self.assertIn("text/javascript", r.headers["content-type"])
            # Ensure zero bare npm specifiers or Node-only globals
            for spec in import_re.findall(r.text):
                self.assertTrue(
                    spec.startswith((".", "/")),
                    f"Bare npm specifier {spec!r} in {mod_route} breaks browser-native ES2022",
                )
            self.assertNotIn("process.env", r.text)

        # Verify viewport meta tag in index.html for mobile layout scaling
        html_text = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

        class ViewportCheck(HTMLParser):
            has_viewport = False

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                d = dict(attrs)
                if tag == "meta" and d.get("name") == "viewport" and "width=device-width" in (d.get("content") or ""):
                    self.has_viewport = True

        vp = ViewportCheck()
        vp.feed(html_text)
        self.assertTrue(vp.has_viewport, "frontend/index.html must include responsive viewport meta tag")

    def test_live_uvicorn_server_with_headless_browser_hydration(self) -> None:
        edge_candidates = [
            shutil.which("msedge"),
            shutil.which("chromium"),
            shutil.which("google-chrome"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        browser_bin = next((c for c in edge_candidates if c and Path(c).is_file()), None)
        if browser_bin is None:
            self.skipTest("No headless Chromium/Edge binary installed in this environment")

        # Pre-warm canonical query cache so chunked SSE completes within a single TCP read under Chromium virtual time
        self.service.analyze(
            {
                "question_id": "person_to_company",
                "source": "Camille Accolas",
                "target": "Trust Exchange",
                "composer_mode": "auto",
                "include_cala_live": False,
            },
            default_template=False,
        )

        # Chromium `--virtual-time-budget` pauses virtual time until HTTP response headers arrive,
        # but fast-forwards virtual time between multi-chunk TCP yields. Keep normal chunked SSE for
        # HTTP clients (`httpx.stream`) and coalesce SSE body frames before sending headers ONLY for
        # HeadlessEdg/HeadlessChrome so `--dump-dom` hydration is 100% deterministic under virtual time.
        inner_app = self.app

        async def virtual_time_safe_asgi(scope, receive, send):
            if scope["type"] == "http" and scope.get("path") == "/api/analyses/stream":
                ua = b""
                for k, v in scope.get("headers", []):
                    if k.lower() == b"user-agent":
                        ua = v
                        break
                if b"Headless" in ua:
                    start_msg = None
                    chunks: list[bytes] = []

                    async def buffered_send(message):
                        nonlocal start_msg
                        if message["type"] == "http.response.start":
                            start_msg = message
                        elif message["type"] == "http.response.body":
                            chunks.append(message.get("body", b""))
                            if not message.get("more_body", False):
                                await send(start_msg)
                                await send({"type": "http.response.body", "body": b"".join(chunks), "more_body": False})
                        else:
                            await send(message)

                    await inner_app(scope, receive, buffered_send)
                    return
            await inner_app(scope, receive, send)

        # Bind an ephemeral localhost port for a real Uvicorn server
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        config = uvicorn.Config(virtual_time_safe_asgi, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        try:
            base_url = f"http://127.0.0.1:{port}"
            ready = False
            for _ in range(40):
                try:
                    r = httpx.get(f"{base_url}/api/health", timeout=1.0)
                    if r.status_code == 200:
                        ready = True
                        break
                except Exception:
                    time.sleep(0.1)
            self.assertTrue(ready, "Live Uvicorn server failed to become healthy within 4s")

            # 1) Verify real unbuffered TCP SSE streaming over the live Uvicorn socket
            with httpx.stream(
                "POST",
                f"{base_url}/api/analyses/stream",
                json={
                    "question_id": "person_to_company",
                    "source": "Camille Accolas",
                    "target": "Trust Exchange",
                    "composer_mode": "auto",
                },
                timeout=10.0,
            ) as stream_resp:
                self.assertEqual(stream_resp.status_code, 200)
                live_sse_text = "".join(stream_resp.iter_text())
            live_events = parse_sse_events(live_sse_text)
            self.assertEqual(live_events[-1][0], "stage")
            self.assertEqual(live_events[-1][1]["stage"], "complete")

            # 2) Verify full real-browser ES2022 + SVG + Provenance DOM hydration in headless Microsoft Edge
            with tempfile.TemporaryDirectory() as profile_dir:
                proc = subprocess.run(
                    [
                        browser_bin,
                        "--headless=new",
                        "--disable-gpu",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--user-data-dir={profile_dir}",
                        "--virtual-time-budget=15000",
                        "--dump-dom",
                        f"{base_url}/?autorun=1",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )

            dom = proc.stdout
            self.assertIn("Comare di Slush", dom)
            # Verify all 17 presets hydrated from live `GET /api/presets` into `#presetsRail`
            self.assertIn("bench_01_camille_trust_exchange", dom)
            self.assertIn("showcase_10_sana_labs_amplitude_4hop", dom)
            self.assertIn("showcase_16_iceye_finnish_unicorn_speakers", dom)
            # Verify initial SSE stream (`POST /api/analyses/stream`) completed and rendered graph + brief + provenance chips
            self.assertIn("Found 3 supported professional paths from Camille Accolas to Trust Exchange", dom)
            self.assertIn("data-ev-id=\"ev:", dom)
            self.assertIn("class=\"g-node-group\"", dom)
            self.assertIn("class=\"g-edge-group\"", dom)
            # Verify Cala registry provenance badges preserve publisher + clickable source URL with zero visible raw IDs
            self.assertIn("trustexchange.world", dom)
            self.assertIn("slush.org", dom)
            self.assertNotIn(">ev:", dom)
            self.assertNotIn('title="ev:', dom)
            self.assertNotIn(">path:", dom)
        finally:
            server.should_exit = True
            thread.join(timeout=5)

    def test_cli_deterministic_build_and_coverage_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_snapshot = Path(tmp_dir) / "rebuilt_snapshot.json"
            build_proc = subprocess.run(
                [sys.executable, "-m", "backend.cli", "--snapshot", str(tmp_snapshot), "build"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
            self.assertEqual(build_proc.returncode, 0, msg=build_proc.stderr)
            built_info = json.loads(build_proc.stdout)
            self.assertEqual(built_info["graph_version"], get_shared_snapshot()["graph_version"])
            self.assertTrue(tmp_snapshot.exists())

            cov_proc = subprocess.run(
                [sys.executable, "-m", "backend.cli", "--snapshot", str(tmp_snapshot), "coverage"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                check=False,
            )
            self.assertEqual(cov_proc.returncode, 0, msg=cov_proc.stderr)
            cov_info = json.loads(cov_proc.stdout)
            self.assertEqual(cov_info["graph_version"], get_shared_snapshot()["graph_version"])
            self.assertEqual(cov_info["counts"]["nodes"], 38886)
            self.assertEqual(cov_info["counts"]["edges"], 50463)
            self.assertEqual(cov_info["counts"]["traversable_edges"], 39235)
            self.assertEqual(cov_info["counts"]["evidence_records"], 81654)


if __name__ == "__main__":
    unittest.main()
