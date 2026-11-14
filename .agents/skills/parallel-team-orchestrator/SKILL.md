---
name: parallel-team-orchestrator
description: Playbook for launching and coordinating the multi-agent full-stack squad (architect-coordinator, cala-intelligence-agent, backend-agent, frontend-agent, qa-integrations-agent) in parallel with direct peer-to-peer messaging.
---

# Parallel Multi-Agent Team Orchestrator

Use this playbook whenever building features, refactoring, or running full-stack sprints on the Cala Junction 2026 webapp.

## Mode A: Interactive Peer-Communicating Squad (`invoke_subagent` + `send_message`)

Best when Frontend, Backend, and Cala Data agents need live two-way communication while working concurrently:

1. **Phase 1 — Contract & Graph Seed (`architect-coordinator` + `cala-intelligence-agent` in parallel)**:
   - Launch `architect-coordinator` to lock `docs/contracts/API_CONTRACT.md`.
   - Simultaneously launch `cala-intelligence-agent` to introspect real Cala entities and save verified JSON fixtures in `docs/contracts/cala-fixtures/`.
2. **Phase 2 — Parallel Full-Stack Build (`backend-agent` + `frontend-agent` simultaneously)**:
   - Call `invoke_subagent` for `backend-agent` and `frontend-agent` in the **same turn** so both run concurrently.
   - Immediately write both returned `conversationId`s into `docs/agent-bus/STATUS_BOARD.md` AND call `send_message` to each agent sharing its peer's `conversationId`:
     - To `backend-agent`: `"Peer frontend-agent is live at conversationId=<ID>. Message it directly via send_message when endpoints or SSE schemas are ready."`
     - To `frontend-agent`: `"Peer backend-agent is live at conversationId=<ID>. Message it directly via send_message if you need contract tweaks or CORS updates."`
3. **Phase 3 — Integration & Demo Audit (`qa-integrations-agent`)**:
   - Launch `qa-integrations-agent` with the IDs of `backend-agent` and `frontend-agent` so it can test end-to-end and dispatch fixes directly to the responsible peer.

## Mode B: Automated Staged Pipeline (`run_workflow`)

When python3 is installed and you want code-driven fan-out/pipeline execution, run `scripts/workflows/fullstack_sprint.py` via `run_workflow(ScriptPath=..., Args={"feature": "..."})` (read the `run-workflow` skill first).
