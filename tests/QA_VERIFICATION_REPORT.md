# Unicorn Radar — Full-Stack QA, Provenance Audit & Submission Verification Report

> **Project**: Unicorn Radar — Cala × Slush 2026 Verified Connection Intelligence (*"Make Unicorns Real — separating the unicorns from the horses"*)
> **Auditor**: `qa-integrations-agent`
> **Contract Version**: `API_CONTRACT.md v2.1`
> **Snapshot Graph Version**: `b2e1e3d55b0e200e1923f7dfd0f723d8d5736f8a646f95fd1200ad8ecae7cf70` (`importer_version: 2.0.2`)
> **Automated Suite Result**: **59 / 59 PASSED (`100%`) in `15.22s`** (`Python 3.12.16`, `pytest 9.2.0`)

---

## 1. Automated Test Suite Summary (`59 / 59` Passing)

Command executed:
```bash
uv run pytest -v
```

| Test Module | Tests | Status | Focus & Scope |
| :--- | :---: | :---: | :--- |
| `tests/test_e2e_and_partner_tech.py` | **20** | **PASS** | Dual `/api/*` + legacy FastAPI contract, CORS preflight/cross-origin headers, all 17 curated presets (`PRESETS_AND_DEMO_CASES.json`), SSE stage streaming, Gemini + Gemma 3 entailment shield & hallucination fallback, Aiven PostgreSQL + Valkey store/cache telemetry, Cala `/v1` namespace isolation & `402`/`429`/timeout clean halts, CRACI CycloneDX 1.7 SBOM + supply-chain audit, ES2022 static module & responsive CSS verification, CLI deterministic `build` + `coverage`, and live Uvicorn + headless Microsoft Edge V8 DOM hydration |
| `tests/test_queries.py` | **17** | **PASS** | Deterministic graph reconciliation (`10,785` nodes, `4,023` edges, `933` traversable professional bridges, `11,643` evidence records), 4-hop shortest-path traversal (`Q1`–`Q4`), non-bridge exclusions (`PARTICIPATES_IN_EVENT`, `OPERATES_IN_INDUSTRY`, `HAS_DOMAIN_NAME`, `HAS_HEADQUARTERS_IN`, `PARTICIPATES_IN_FUNDING_ROUND`), Cala document-backed edge enforcement, identity disambiguation (`Ben Fletcher`, `Y Combinator`), Slush named attendance vs. unverified corporate affiliation (`Camille Accolas` vs. `Martin Studer`) |
| `tests/test_service.py` | **14** | **PASS** | Versioned canonical cache hits & `refresh=True` bypass, SQLite/store persistence & byte-for-byte historical run replay, `GET /analyses/{run_id}/prompt` grounded LLM schema inspection, external composer closed-world `evidence_ids` validation & automatic template fallback, stdlib `ThreadingHTTPServer` HTTP parity (`200`, `400`, `404`, `405`, `413`) |
| `tests/test_security_and_workflow.py` | **8** | **PASS** | CRACI CI workflow (`.github/workflows/ci.yml`) structural validation (`runs-on: craci`, `cracicorp/setup@v1`, `size: "4"`, `default: deny` + `presets: [pypi, github]`), proxy CA environment preservation (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`), `.gitignore` & `.env.example` hygiene, SHA-256 dataset manifest integrity (`backend/data/input_manifest.json`), repo-wide zero-secret leakage scan |
| **Total** | **59** | **100% PASS** | **End-to-end execution time: `15.22s`** |

---

## 2. Cala Knowledge Graph Provenance & Zero-Confabulation Audit

| Epistemic / Provenance Rule | Verification Method | Result |
| :--- | :--- | :---: |
| **Mandatory Source + Date Provenance** | Verified across `backend/data/snapshot.json` (`933` traversable edges), all `17` demo scenarios, and live headless Edge DOM rendering (`shab.ch`, `zefix.admin.ch`, `trustexchange.world` clickable `<a class="source-doc-badge">` links + ISO dates). Every Cala traversable edge carries ≥1 non-empty `source_documents` entry; 4 Cala edges lacking source documents are quarantined as non-traversable audit assertions. | **VERIFIED** |
| **Closed-World Evidence Referential Integrity** | Tested across all 17 presets + AI engine unit tests: every `ev:...` ID cited in `claims[]`, `slush_brief`, `results[]`, `graph.nodes[]`, `graph.edges[]`, and `graph.paths[]` resolves inside the response's `evidence` dictionary. Any hallucinated `ev:fake` ID from an LLM triggers immediate deterministic fallback (`evidence_template_fallback`). | **VERIFIED** |
| **Zero False Bridges (Event / Industry / Country)** | `Trust Exchange → Slicker` (`bench_06`) returns `insufficient_data` with `0` paths despite both attending Slush 2026 and operating in `FINTECH`. Synthetic tests also confirm `PARTICIPATES_IN_FUNDING_ROUND` without shared entity IDs never creates an invented bridge. | **VERIFIED** |
| **Zero Silent Identity Merging** | `Dani Penev → Y Combinator` (`bench_02a`) and `Ben Fletcher → Trust Exchange` (`bench_07`) return `status: "needs_resolution"` with candidate pickers rather than silently merging name-only collisions across Cala and Slush work-history stubs. | **VERIFIED** |
| **Strict Namespace Separation for Live Cala `/v1`** | `GET /api/cala/enrich/{entity_id}` and `include_cala_live=True` store live `/v1/entities/{uuid}` attributes/relationships strictly inside `cala_live_enrichment` (`namespace: "cala_live_enrichment"`), never mutating deterministic snapshot hop counts or `graph_version`. HTTP `402` (`payment_required`), `429` (`rate_limited`), `504` (`timeout`), and missing `CALA_API_KEY` (`unconfigured`) halt cleanly without confabulation. | **VERIFIED** |
| **Zero Secret Leakage in Bundles & Repo** | Automated regex + file scan across `frontend/`, `backend/`, `docs/`, `.github/`, and `tests/` confirms zero hardcoded API keys or credentials; `.gitignore` excludes `.env*` and `*.sqlite3`. | **VERIFIED** |

---

## 3. Issues Caught & Resolved During Multi-Agent QA

1. **Cross-Origin Preflight (`CORS`) on FastAPI (`backend/app.py`)**:
   - *Finding*: Cross-origin `OPTIONS /api/analyses` preflight returned `405` before `CORSMiddleware` was attached.
   - *Resolution*: Reported to `backend-agent` via peer message; `CORSMiddleware` added in `backend/app.py` and verified by `test_cors_preflight_and_cross_origin_headers`.
2. **Cala Source Registry Link & Publisher Rendering (`frontend/js/utils.js`)**:
   - *Finding*: Headless Edge DOM audit revealed Cala snapshot `source_documents` (`{name, document, date, source_rank}`) were falling back to unlinked `"Source · Document"` badges because `renderSourceDocumentBadge` only checked `{publisher, url}` rather than Cala's `{name, document, source_rank}`.
   - *Resolution*: Reported to `frontend-agent` via peer message; `renderEvidenceChips` and `renderSourceDocumentBadge` updated in `frontend/js/utils.js`. Re-verified in live headless Microsoft Edge DOM (`shab.ch`, `zefix.admin.ch`, `2026-10-22`, and clickable `https://www.shab.ch/...` links).

---

## 4. Junction 2026 Partner Tech Challenge Readiness Matrix

### A. Cala Challenge (*"Make Unicorns Real"*)
- **17 / 17 Verified Benchmark & Deep-Graph Presets Passing**: Covers 1-hop dual-source corroboration, 2-hop VC/CVC syndicates (`Dani Penev → Slicker → Y Combinator`, `Pekka Iso-Ketola → Forciot Oy → Volvo Car Technology Fund AB`, `Speedinvest GmbH → Bliq GmbH → FJ Labs, LLC`), 3-hop cross-dataset bridges (`Martin Studer → The Decision Room`, `Anton Osika → Amplitude`), 4-hop max-depth bridges (`Sana Labs → Amplitude`, `Expander → Intel Capital`), Q3 corporate ecosystems (`Planhat`, `Trust Exchange`), Q4 Slush speaker briefs (`General Catalyst`, `ICEYE`, `Trust Exchange`), and honest guardrails (`needs_resolution`, `insufficient_data`).
- **Live Cala `/v1` Enrichment Ready**: Server-side `CalaLiveClient` (`X-API-KEY` header, 30s timeout, cache-backed, clean `402`/`429` handling) + UI Node Inspector trigger.

### B. Google DeepMind (Gemini + Open-Weight Gemma 3 Dual-Model Pipeline)
- **Stage 1 — Grounded Synthesis (`gemini-2.5-flash`)**: Structured JSON schema synthesis constrained strictly to `allowed_evidence_ids`.
- **Stage 2 — Open-Weight Claim Entailment Shield (`gemma-3-27b-it`)**: Audits every generated claim against raw source snippets (`supported` vs. `flagged_overreach`), flagging causal/temporal/attendance overreach and falling back to deterministic templates if any hallucinated `ev:...` ID appears.

### C. Aiven Challenge (Managed PostgreSQL + Managed Valkey)
- **`UnifiedAnalysisStore` (`backend/aiven_store.py`)**: Supports `AIVEN_PG_URI` (immutable JSONB run history & byte-for-byte replay) and `AIVEN_VALKEY_URI` (sub-2ms canonical versioned cache + Cala `/v1` enrichment cache) with seamless zero-config local SQLite + in-memory LRU fallback and live telemetry (`GET /api/infrastructure/status`).

### D. CRACI Challenge (Supply-Chain Hardened CI Runner & CycloneDX 1.7 SBOM)
- **Production Workflow (`.github/workflows/ci.yml`)**: Uses `runs-on: craci` + `cracicorp/setup@v1` (`size: "4"`, `default: deny`, `presets: [pypi, github]`) routing all dependency traffic through CRACI's package-aware attesting proxy for a 100% Complete Verified CycloneDX SBOM while blocking unverified outbound egress.
- **In-App Attestation & Audit (`GET /api/craci/provenance`, `POST /api/craci/audit`)**: Surfaces CycloneDX 1.7 dependency inventory, workflow egress policy, network trace telemetry, Cala cross-matched SBOM vendors, and grounded supply-chain risk audit without fabricating job IDs when offline.

---

## 5. Live Browser ↔ FastAPI End-to-End Hydration Verification

Verified in `FrontendAndHeadlessBrowserE2ETests.test_live_uvicorn_server_with_headless_browser_hydration`:
- Booted real `uvicorn` server on an ephemeral localhost TCP port serving `backend.app:create_app`.
- Confirmed live chunked TCP Server-Sent Events (`POST /api/analyses/stream`) via `httpx.stream`.
- Executed headless Microsoft Edge (`msedge --headless=new --dump-dom`) against `http://127.0.0.1:<port>/`:
  - Loaded `index.html`, `/css/styles.css` (including `@media` responsive breakpoints for mobile/tablet/desktop), and all 5 native ES2022 modules (`app.js`, `api.js`, `graph-view.js`, `results-view.js`, `tech-views.js`, `utils.js`).
  - Hydrated all 17 presets into `#presetsRail`.
  - Streamed and rendered `Camille Accolas → Trust Exchange` (`2 nodes · 2 verified edges · 2 paths`), SVG `.g-node-group` / `.g-edge-group` elements, `Slush 2026 Executive Meeting Brief`, `[ev:...]` provenance chips, and clickable Swiss registry (`shab.ch`, `zefix.admin.ch`) source badges.
