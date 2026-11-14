# Cala Junction 2026 — Multi-Agent Workspace Constitution (`AGENTS.md`)

> **Mission**: *"Make Unicorns Real — separating the unicorns from the horses"* (Hackjunction 2026).

## 1. Multi-Agent Squad & File Ownership Boundaries

To allow multiple AI agents to work **simultaneously in parallel** without merge or edit collisions, every agent MUST respect strict directory ownership:

| Agent | Role | Exclusive Write Scope | Primary Peers |
| :--- | :--- | :--- | :--- |
| `architect-coordinator` | System/Product Lead & Contract Owner | `docs/contracts/`, `docs/agent-bus/`, root configs | All agents |
| `cala-intelligence-agent` | Cala Knowledge Graph & Provenance Specialist | `docs/contracts/cala-fixtures/`, Cala query specs | `backend-agent`, `frontend-agent` |
| `backend-agent` | API Server, AI Agents Engine & DB/Cache | `backend/` (or `src/server/` & `src/app/api/`) | `cala-intelligence-agent`, `frontend-agent` |
| `frontend-agent` | Webapp UI/UX, Interactive Graph & Streaming | `frontend/` (or `src/components/` & UI routes) | `backend-agent`, `cala-intelligence-agent` |
| `qa-integrations-agent` | E2E Testing, Provenance Audit & CI/CD | `tests/`, `.github/workflows/`, QA reports | `backend-agent`, `frontend-agent` |

**Golden Rule**: Never directly edit files inside another agent's exclusive write scope unless explicitly instructed by the orchestrator. Instead, request contract or implementation updates via `send_message` and `docs/contracts/API_CONTRACT.md`.

---

## 2. Inter-Agent Communication Protocol (Direct & Asynchronous)

1. **Direct Peer Messaging (`send_message`)**:
   - Active agent `conversationId`s are posted in `docs/agent-bus/STATUS_BOARD.md` (and passed in spawn prompts).
   - When `backend-agent` exposes or updates an endpoint/SSE stream, it immediately messages `frontend-agent` via `send_message`.
   - When `frontend-agent` needs an extra graph field or endpoint adjustment, it messages `backend-agent` (and/or `cala-intelligence-agent`) directly via `send_message`.
2. **Contract-First Parallel Execution**:
   - Both `frontend-agent` and `backend-agent` build against `docs/contracts/API_CONTRACT.md` and real Cala JSON fixtures in `docs/contracts/cala-fixtures/` so UI never waits on backend and backend never waits on UI.

---

## 3. Cala Knowledge Graph Non-Negotiable Rules

Always follow the `cala` skill (`C:\Users\Nico\.gemini\config\plugins\cala\skills\cala\SKILL.md`):
- **Structured first**: Prefer `knowledge_query` and `entity_search`/`entity_lookup` -> `entity_introspection` -> projected `entity_retrieval` over `knowledge_search` when the answer shape is known.
- **Provenance is mandatory**: Every Cala attribute, relationship, and metric carries `sources` (publisher name, URL, date). Preserve and render provenance badges in the UI.
- **Zero Confabulation**: Never silently substitute web search or LLM recall for missing Cala data. When enriching with external live web data (e.g., Context.dev), keep it in a separate, clearly labeled namespace (`live_web_signals` vs `cala_verified_facts`).
- **Security & Timeouts**: Never log or hardcode `CALA_API_KEY` (or any API key). Configure ~180s client timeouts and cache responses (e.g., Aiven Valkey/PostgreSQL) for instant live-demo responsiveness.
