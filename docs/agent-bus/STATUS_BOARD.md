# Multi-Agent Live Status Board — Unicorn Radar (Cala × Slush 2026)

> Shared registry for parallel subagents in Antigravity. Check here for peer `conversationId`s, locked contract paths, and milestone status.

## Active Agent Registry

| Agent Type | Conversation ID | Exclusive Write Scope | Current Task | Status |
| :--- | :--- | :--- | :--- | :--- |
| `parent-orchestrator` | `06a1c377-56b3-42ef-880e-381f54266c66` | Root orchestration | Squad Coordination | Active |
| `architect-coordinator` | `020b1bb6-d7f6-4b35-8164-94c03c73b06f` | `docs/contracts/`, `docs/agent-bus/`, `.env.example`, `pyproject.toml`, `scripts/` | System Architecture, `API_CONTRACT.md` (`v2.1`), `pyproject.toml`, `.env.example`, `scripts/start.*` | **Locked & Ready** |
| `cala-intelligence-agent` | `2c4a7d86-3edb-4d6b-ab0b-e5ae2ebc3ed8` | `docs/contracts/cala-fixtures/` | Cala `/v1` Query Specs & 17 Verified Presets + 12 Fixtures | **Completed & Verified** |
| `backend-agent` | `99151fd2-80f5-4068-81a3-11f5c6dfe0e1` | `backend/` | FastAPI Dual-Mount Server, Snapshot Graph Engine, Gemini + Gemma Audit, Aiven PG/Valkey + SQLite, Cala `/v1` & CRACI Provenance | **Completed & Verified** |
| `frontend-agent` | `9858f10b-acc2-47bd-86ed-1a5384249177` | `frontend/` | Zero-Build Native ES2022 Webapp (`index.html`, `css/`, `js/`), Interactive SVG/Canvas Graph, SSE Streaming, Provenance & CRACI Views | **Completed & Edge-Headless Verified** |
| `qa-integrations-agent` | `f52d15fb-ebc7-40a7-9ad9-5470bddab90e` | `tests/`, `.github/workflows/` | Full E2E Test Suite (59/59 passed), Live Browser+Server Audit & QA Report | **Completed & Verified** |

---

## Architecture & Contract Lock Summary (`v2.1`)
- **Contract File**: `docs/contracts/API_CONTRACT.md`
- **Local Server**: `http://127.0.0.1:8080` (same-origin static serving of `frontend/` at `/` + dual-mounted `/api/*` and legacy root `/health`, `/questions`, `/coverage`, `/entities`, `/analyses`).
- **Critical Local Constraint**: Node.js is **not** installed locally — `frontend/` MUST use pure native browser ES2022 modules (`index.html` + `css/` + `js/`) with **zero build step**.
- **Python Runtime**: Managed via `uv` (`uv run --python 3.12 ...`) with graceful fallback if optional cloud drivers/keys are absent.
- **Partner Tech Challenges Covered**:
  1. **Cala**: Verified 10,785-node / 933-traversable-edge Slush×Cala reconciled graph + `ev:...` provenance badges + optional `/api/cala/enrich/{entity_id}` live `/v1` enrichment (`cala_live_enrichment` namespace, zero confabulation).
  2. **Google DeepMind (Gemini + Gemma)**: Gemini structured `generated_claims` & `meeting_brief` + Gemma open-weight entailment auditor (`gemma-3-27b-it`) + deterministic `evidence_template` fallback.
  3. **Aiven**: Managed **Aiven PostgreSQL** run store + **Aiven Valkey** sub-2ms canonical cache, with automatic zero-config SQLite + in-memory LRU fallback (`/api/infrastructure/status`).
  4. **CRACI**: Isolated Linux VM runner workflow (`runs-on: craci`) + CycloneDX SBOM & egress network trace provenance (`/api/craci/provenance` & `/api/craci/audit`).
