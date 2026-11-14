# Shared Frontend <-> Backend API Contract

> Owned by `architect-coordinator`. Read by `frontend-agent`, `backend-agent`, `cala-intelligence-agent`, and `qa-integrations-agent`.

## Status
- **Phase**: Pre-Kickoff (Awaiting stack & product vertical confirmation)
- **Base API URL (Dev)**: TBD (`http://localhost:8000/api` or `/api`)

## Core Data Envelope Rules
1. **Cala Provenance Object** (required on every Cala-sourced fact):
   ```json
   {
     "value": "...",
     "sources": [
       {
         "publisher": "Source Name",
         "url": "https://...",
         "date": "YYYY-MM-DD"
       }
     ]
   }
   ```
2. **Source Separation**:
   - `cala_verified`: Structured entities, relationships (`FOUNDED`, `IS_CEO_OF`, `IS_DIRECT_OWNER_OF`, etc.), funding rounds, sanctions, and numerical observations from Cala (`https://api.cala.ai/v1`).
   - `live_web_signals` *(optional, if Context.dev enabled)*: Live website claims, pricing, product updates, job postings — strictly separated from `cala_verified` to highlight discrepancies ("Unicorn vs Horse").
   - `ai_synthesis` *(Gemini API)*: Multi-agent analysis, thesis score, red flags, and cited reasoning grounded in `cala_verified` (+ `live_web_signals`).

## Endpoints
*(To be populated by `architect-coordinator` as soon as product scope is locked)*
