# Comare di Slush

> Find the connections behind the names.

**[Open the live demo](https://comare-di-slush-cala-junction.andrearitratto.chatgpt.site/)**

**Comare di Slush** helps founders, investors, and other Slush participants understand who is connected to whom, find relevant people to approach, and prepare for useful conversations. It combines **Cala's professional relationship data** with **Slush 2026 company and people datasets**, bringing connection paths, company networks, and their supporting sources into one interactive website.

Built for **HackJunction 2026**, for Cala's **Make Unicorns Real** challenge, the project addresses a practical event problem: a long attendee list tells you who is there, but understanding how people and companies relate takes more work. Comare di Slush makes those relationships easier to explore, with evidence and data gaps visible alongside the results.

## What you can do

The website has four search modes. Choose a question and enter the relevant person or company names.

| Search mode | Question | What the results show | Examples |
| --- | --- | --- | --- |
| **Person → Company** | How is this person connected to this company? | Ranked professional paths through founders, employers, investors, board members, and other documented relationships. | David Silver → Lovable; Deedy Das → Lovable; Markus Villig → Lovable; Ilkka Paananen → Linear; Anton Osika → Amplitude; Ted Persson → Lovable. |
| **Company → Company** | How is this company connected to that company? | Connections between two companies through shared people, investors, and other professional bridges. | Sana Labs → Lovable; Lovable → OpenAI; Supercell → Linear; Vanta → Lovable; Lovable → Sequoia Capital; Bolt → Atomico. |
| **Company network** | What relationships surround this company? | A local network grouped into people, investors, companies, and indirect connections. | Lovable; Linear; Supercell; Bolt. |
| **People at Slush** | Who from this company can I approach at Slush? | People with individual Slush participation evidence, shown separately from company affiliates whose attendance is unverified. Greater search depths can also reveal indirectly connected participants. | Lovable; Bolt; Supercell; Atomico; Linear. |

### Using the website

1. **Choose a search mode.** Fill in the sentence using the name fields, or start with an example search.
2. **Select the right identity.** Autocomplete and the disambiguation picker help distinguish records with similar names. 
3. **Set the search depth.** Use **Suggested**, adjust the number of relationship steps, or select **Max**. The allowed depth depends on the question.
4. **Explore the relationship graph.** Switch between **Auto**, **Paths**, and **Network** layouts; drag nodes, pan, zoom, or fit the graph to the view. Click a person, company, or relationship to inspect it, or select a connection result to focus on its path.
5. **Read the connection details.** Inspect relationship types, available profile information, source records, and meeting context. Reopen previous analyses from **Recent**.

Results include a searchable evidence explorer with dataset filters and source-document links where available. Meeting briefs provide a summary, talking points, and questions grounded in the retrieved information. When an AI provider is configured, it can compose the brief; the local evidence-based fallback keeps the core experience available without API keys.

## How it works

### Cala relationships + Slush context

Cala supplies the professional relationship graph. Slush records add event-specific people, company profiles, and participation evidence. Combining them helps answer both **how an entity is connected** and **which relevant people appear in the event data**.

| Data source | Role in the application |
| --- | --- |
| Cala relationship exports | Company and person records, professional relationships, and supporting source documents. The importer supports the CSV bundle in `backend/data/slush_2026_spreadsheets/`, its ZIP equivalent, and the legacy `cala_graph.json` export. |
| `backend/data/slush_people.json` | Individual profiles, affiliations, and Slush participation information. |
| `backend/data/slush_companies.json` | Company profiles and named attendee information where supplied. |

The backend builds or reuses a normalized local snapshot, reconciles identities using corroborating identifiers and affiliations, and indexes the supporting evidence. Each query searches documented professional relationships within the selected depth, ranks the resulting paths, and returns the graph, connection details, and evidence together. Completed analyses are saved so they can be reopened.

**The main website searches the loaded snapshot.** Optional live Cala enrichment is a separate backend capability. Current dataset coverage can be inspected with the `coverage` command in the quickstart below; totals depend on the loaded export.

### Reading the results correctly

- **A path is a documented professional connection.** It does not establish personal friendship or guarantee an introduction. Shared event attendance, industry, or location alone is not used as a professional bridge.
- **Participation evidence has limits.** A directory listing or event announcement is distinct from confirmed physical attendance.
- **Matching names need corroboration.** Ambiguous identities remain separate until the appropriate record is selected.
- **Coverage is partial.** Missing results mean that no supported path was found in the available snapshot and search bounds. Relationship dates, sparse profiles, and uncertainty should be considered when planning outreach.

The current **Log in** control displays session information; account authentication is not implemented in the main website.

### Optional AI and backend services

The main application uses a Python/FastAPI backend and a native JavaScript frontend. These integrations extend it when configured:

| Integration | Purpose | Configuration |
| --- | --- | --- |
| **Google Gemini** | Structured, evidence-constrained summaries and meeting briefs. Generated evidence references are checked against the retrieved records. | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| **Gemma** | Optional open-weights composition or an additional review of generated claims. Supports Google AI Studio, Featherless, and OpenAI-compatible endpoints. | `GEMMA_PROVIDER`, `GEMMA_MODEL`, `GEMMA_API_KEY`, `FEATHERLESS_API_KEY`, `GEMMA_BASE_URL` |
| **Aiven PostgreSQL + Valkey** | Persistent analysis storage and caching. Local SQLite and in-memory caching provide the default fallback. | `AIVEN_PG_URI`, `AIVEN_VALKEY_URL` |
| **Cala live API** | Optional enrichment beyond the loaded snapshot, kept separate from the main graph search. | `CALA_API_KEY`, `CALA_BASE_URL`, `CALA_TIMEOUT_SECONDS` |
| **CRACI** | Build provenance, dependency inspection, and supply-chain audit support in the backend and CI workflow. | `CRACI_API_TOKEN`, `CRACI_ORG`, `CRACI_REPO`, `CRACI_BASE_URL` |

See [`.env.example`](.env.example) for configuration details and provider options. These backend integrations support the search experience; the current website centres on the relationship graph and connection details.

## Run locally

Comare di Slush has a **zero-build native ES2022 frontend** (`frontend/index.html`, `css/`, `js/`) served directly by the Python backend on `http://127.0.0.1:8080`. No Node.js, npm, or bundler step is needed. The core graph search and deterministic briefing engine work locally with the supplied datasets; optional `.env` keys enable cloud integrations.

### Launch the Webapp & API Server
```powershell
# Windows (PowerShell)
.\scripts\start.ps1

# Linux / macOS / WSL / Git Bash
./scripts/start.sh

# Or directly via the spec-compatible root CLI:
uv run --python 3.12 python demo.py serve --port 8080
```
Then open **`http://127.0.0.1:8080`** in your browser.

### Optional Cloud Configuration (`.env`)
```bash
cp .env.example .env
# Populate any combination of CALA_API_KEY, GEMINI_API_KEY, GEMMA_API_KEY / FEATHERLESS_API_KEY,
# AIVEN_PG_URI, AIVEN_VALKEY_URL, CRACI_API_TOKEN — missing keys degrade cleanly with zero errors.
```

### Run the 4 Fixed Queries via CLI (`demo.py`)
```bash
# Inspect dataset manifest, SHA-256 digests, and Cala coverage disclosures
uv run --python 3.12 python demo.py coverage

# Q1: Person -> Company (1-hop cross-source founder & board paths)
uv run --python 3.12 python demo.py query person_to_company --source "Camille Accolas" --target "Trust Exchange"

# Disambiguation Guardrail: inspect 'Y Combinator' candidates (Cala investor vs Slush text stubs)
uv run --python 3.12 python demo.py resolve "Y Combinator" --type Company

# Q1 & Q2 with canonical Cala Investor ID (multi-hop investor paths)
uv run --python 3.12 python demo.py query person_to_company --source "Dani Penev" --target-id "cala:1e86655e-373d-4fe8-be13-af3713581f73"
uv run --python 3.12 python demo.py query company_to_company --source "Slicker" --target-id "cala:1e86655e-373d-4fe8-be13-af3713581f73"

# Q3: Bounded 2-step Company Network (grouped into Direct People, Investors, Direct Companies, Indirect)
uv run --python 3.12 python demo.py query company_network --company "Trust Exchange"

# Q4: Slush Representatives (separates named Slush 2026 participants from unverified-attendance affiliates)
uv run --python 3.12 python demo.py query company_representatives --company "Trust Exchange"

# Execute all 8 benchmark scenarios & verify byte-for-byte persistence recovery
uv run --python 3.12 python run_examples.py
```


## Repository structure

| Path | Purpose |
| --- | --- |
| `frontend/` | Main Comare di Slush website: search form, interactive SVG graph, connection details, evidence explorer, and recent searches. |
| `backend/` | FastAPI server, dataset ingestion, identity resolution, graph queries, briefing generation, persistence, and integration clients. |
| `backend/data/` | Input datasets and local graph/analysis storage. |
| `demo.py` | Root CLI for `build`, `query`, `resolve`, `coverage`, `history`, `get`, and `serve`. |
| `run_examples.py` | Example query scenarios and persistence round-trip checks. |
| `scripts/start.ps1`, `scripts/start.sh` | Windows and POSIX launchers for the main website. |
| `pyproject.toml`, `uv.lock` | Python project configuration and dependency lockfile. |
| `docs/contracts/` | Frontend/backend API contract and Cala reference fixtures. |
| `tests/` | Automated service, query, integration, and workflow checks. |
| `.github/workflows/ci.yml` | CI workflow with CRACI integration. |
| `cala-agent/`, `cala-gemini-agent/` | Separate Cala agent applications with their own READMEs and launch instructions. |

## Verification

### Run the Automated Test Suite
```bash
uv run --python 3.12 pytest
```
