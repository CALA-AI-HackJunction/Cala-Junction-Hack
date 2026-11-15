# Cala Live REST `/v1` Query & Investor Enrichment Specification

> **Owner**: `cala-intelligence-agent`  
> **Consumers**: `backend-agent` (live enrichment client & caching), `frontend-agent` (provenance & status badges), `qa-integrations-agent` (zero-confabulation audit)  
> **Status**: Verified against `C:\Users\Nico\.gemini\config\plugins\cala\skills\cala\SKILL.md`, `https://api.cala.ai/openapi.json`, `snapshot.json`, and `docs/cala_investors_verification.json`.

---

## 1. Architecture Principle: Snapshot-First + Optional Live Cala Enrichment

1. **Primary Offline Baseline (`snapshot.json`)**:
   - All four networking questions (`person_to_company`, `company_to_company`, `company_network`, `company_representatives`) execute deterministically in `< 5 ms` against the reconciled Cala + Slush 2026 graph (`graph_version: b2e1e3d55b0e200e1923f7dfd0f723d8d5736f8a646f95fd1200ad8ecae7cf70`).
   - Remember why optional live enrichment matters: the bundled Cala export (`slush-2026-graph.json`) stopped at time limit (`complete: false`) with **41 full entity records** (40 companies + 1 event) and **3,238 stub endpoint nodes**.
2. **Optional Live Cala `/v1` Enrichment (`cala_live_enrichment`)**:
   - When `CALA_API_KEY` is configured and live enrichment is requested (e.g., to hydrate a stub node such as `Y Combinator`, `Martin Studer`, or a confirmed Slush VC like `Maki.vc`), `backend-agent` queries Cala's REST `/v1` API using the **structured-first** workflow below.
   - Live Cala facts MUST be stored in a clearly labeled `cala_live_verified` / `cala_verified` namespace with full `sources` (`publisher`/`name`, `url`/`document`, `date`) and cached (SQLite / Valkey / PostgreSQL) keyed by `(entity_id, projection_hash)`.

---

## 2. Transport, Authentication & Timeout Rules

| Setting | Exact Requirement | Notes |
| :--- | :--- | :--- |
| **Base URL** | `https://api.cala.ai/v1` | OpenAPI server `https://api.cala.ai` + `/v1` prefix (`https://api.cala.ai/openapi.json`) |
| **Auth Header** | `X-API-KEY: <CALA_API_KEY>` | Read strictly from server env `CALA_API_KEY`. **Never** log, echo in errors, or expose to browser |
| **Content-Type** | `application/json` | Required on `POST` requests |
| **Client Timeout** | **`180.0` seconds (`180_000 ms`)** | Cala multi-hop / knowledge queries can legitimately take up to ~180s |
| **Timeout Retry** | Retry **at most once** (`max_retries = 1`) | Only on client/gateway timeout. Never retry `402` or `429` |

---

## 3. Exact Endpoint Mapping (Cala Tool Names ↔ OpenAPI `/v1` Wire Routes)

> [!IMPORTANT]
> While Cala MCP tools use snake_case operation names (`entity_search`, `entity_introspection`, `entity_retrieval`, `entity_lookup`, `knowledge_query`, `knowledge_search`), the live REST `/v1` HTTP endpoints follow RESTful resource paths per `https://api.cala.ai/openapi.json`. Implementers MUST use the exact HTTP method and path column below:

| Logical Cala Tool | Exact HTTP Method & `/v1` Route | Request Shape | When to Use |
| :--- | :--- | :--- | :--- |
| `entity_search` | `GET /v1/entities` | Query params: `?name=<str>&entity_types=<Type>&limit=10` | Fuzzy name → candidate `id` (UUID), `name`, `entity_type`, `description` |
| `entity_lookup` | `POST /v1/entities/lookup` | Body: `{"id": {"lei": "..."}}` (schemes: `lei`, `cik`, `siren`, `rssd_id`, `companies_house_uk_company_number`) | Exact external identifier → seed UUID (prefer over `entity_search` when ID is known) |
| `entity_introspection` | `GET /v1/entities/{entity_id}/introspection` | Path param: `{entity_id}` (UUID) | Discover populated `properties`, `relationships` (`incoming`/`outgoing`), and `numerical_observations` metric UUIDs |
| `entity_retrieval` | `POST /v1/entities/{entity_id}` | Path param: `{entity_id}` + optional projected JSON body | Retrieve sourced properties, directed relationships, and time-series observations |
| `knowledge_query` | `POST /v1/knowledge/query` | Body: `{"input": "<dot-notation>", "return_entities": true}` | Structured multi-entity filtering & hop queries (`results` + `entities`) |
| `knowledge_search` | `POST /v1/knowledge/search` | Body: `{"input": "<question>", "explainability": true, "return_entities": true}` | Last resort for open-ended prose questions; cite via `explainability[].references` → `context[].origins[].document.url` |

---

## 4. Mandatory Structured Live Workflow

Always prefer the deterministic 3-step entity pipeline (`Search/Lookup` → `Introspect` → `Projected Retrieval`) or `knowledge_query` over `knowledge_search`.

### Step 1: Seed UUID Resolution (Zero-Call Fast Path First!)
Before calling `GET /v1/entities`, check local verified registries:
1. **`snapshot.json` node `source_ids.cala`**: e.g., `Trust Exchange` → `0220cf38-d013-5600-9616-31da01caa416`, `Slicker` → `017826f8-558b-4209-b4e8-0b6a1e5f3b9e`, `Y Combinator` → `1e86655e-373d-4fe8-be13-af3713581f73`.
2. **`docs/cala_investors_verification.json` (`status === "CONFIRMED"`)**: **791** Slush investors already have verified Cala UUIDs (see Section 5).
3. **Live `GET /v1/entities` (`entity_search`)**: Only if no UUID is known locally:
   ```http
   GET https://api.cala.ai/v1/entities?name=Forciot&entity_types=Company&limit=5
   X-API-KEY: <CALA_API_KEY>
   ```
   - **Disambiguation rule**: Never auto-pick index `0` on a name-only match if multiple candidates share the name without domain/country/description corroboration. Surface candidates in `resolution` (`status: "needs_resolution"`).

### Step 2: Schema Introspection (`entity_introspection`)
Queryable properties and edges vary per entity. Always introspect the seed UUID before projecting:
```http
GET https://api.cala.ai/v1/entities/017826f8-558b-4209-b4e8-0b6a1e5f3b9e/introspection
X-API-KEY: <CALA_API_KEY>
```
Intersect the returned schema against our allowed professional projection whitelist:
- **Properties**: `name`, `legal_name`, `aliases`, `website`, `description`, `headquarters_address`, `registered_address`, `founding_date`, `operational_status`, `employee_count`, `employee_count_range`.
- **Professional Traversable Edges ONLY**:
  - Affiliation/leadership: `FOUNDED`, `IS_CEO_OF`, `IS_CTO_OF`, `IS_CFO_OF`, `IS_COO_OF`, `IS_CSO_OF`, `IS_CMO_OF`, `IS_CCO_OF`, `IS_BOARD_MEMBER_OF`, `IS_MANAGING_DIRECTOR_OF`, `IS_VICEPRESIDENT_OF`, `ADVISES`, `IS_ADVISOR_OF`, `WORKS_AT`, `IS_MEMBER_OF`.
  - Capital/ownership: `INVESTED_IN`, `IS_DIRECT_OWNER_OF`, `IS_ULTIMATE_PARENT_OF`, `IS_BENEFICIARY_OWNER_OF`, `IS_CONTROL_PERSON_OF`, `PARTICIPATES_IN_FUNDING_ROUND`, `OWNS`, `ACQUIRED`.
  - **Excluded as path bridges**: `PARTICIPATES_IN_EVENT`, `OPERATES_IN_INDUSTRY`, `HAS_HEADQUARTERS_IN`, `HAS_PRESENCE_IN`, `HAS_DOMAIN_NAME`, `IS_REGISTERED_IN` (may display as profile metadata, **never** as networking bridges).

### Step 3: Projected Entity Retrieval (`entity_retrieval`)
Request only fields confirmed by introspection:
```http
POST https://api.cala.ai/v1/entities/017826f8-558b-4209-b4e8-0b6a1e5f3b9e
X-API-KEY: <CALA_API_KEY>
Content-Type: application/json

{
  "properties": [
    "name",
    "legal_name",
    "website",
    "headquarters_address",
    "founding_date",
    "employee_count_range",
    "operational_status",
    "description"
  ],
  "relationships": {
    "incoming": {
      "FOUNDED": {"limit": 10, "offset": 0},
      "IS_CEO_OF": {"limit": 5, "offset": 0},
      "IS_BOARD_MEMBER_OF": {"limit": 10, "offset": 0},
      "INVESTED_IN": {"limit": 20, "offset": 0}
    },
    "outgoing": {
      "PARTICIPATES_IN_FUNDING_ROUND": {"limit": 10, "offset": 0}
    }
  },
  "numerical_observations": {
    "ObservableProperty": ["64231bfc-8b8e-548e-a215-0dcee3ea6998"]
  }
}
```

### Step 4: Structured Multi-Entity Filtering (`knowledge_query`)
When discovering portfolio companies or co-investors in Cala using Dot-Notation Syntax (`filters → order_by → limit → return()`):
```http
POST https://api.cala.ai/v1/knowledge/query
X-API-KEY: <CALA_API_KEY>
Content-Type: application/json

{
  "input": "companies.investors=Lifeline Ventures.order_by=funding DESC.limit=10.return(name, funding, sector, location)",
  "return_entities": true
}
```
- Note: `,` on a single field means **AND** (`investors=Sequoia Capital,Andreessen Horowitz` = backed by both).
- Numeric fields can return approximate strings (`"over 100M"`, `"~206,753"`) — preserve raw string representation alongside parsed display text; never fabricate exact decimals.

---

## 5. Enriching Slush Investors via `docs/cala_investors_verification.json`

`docs/cala_investors_verification.json` contains **1,556** Slush 2026 investor records pre-audited against Cala:

| Verification Status | Count | Backend Handling Rule |
| :--- | ---: | :--- |
| `CONFIRMED` | **791** | Safe to attach `cala_id` under `cala_verified_investor_match` provenance |
| `UNCHECKED_BALANCE` | **470** | Audit halted cleanly on HTTP `402` balance limit — keep `unverified`, never guess |
| `NOT_FOUND` | **226** | No Cala match — keep Slush-only identity |
| `AMBIGUOUS` | **67** | Multiple Cala candidates — require human disambiguation before linking |
| `INVALID_INPUT` | **2** | Malformed source name — ignore |

### Confirmed Cala UUIDs for High-Signal Slush Investors
| Slush Investor Name | Confirmed `cala_id` (UUID) | Cala Canonical Name | Type | Country | Score |
| :--- | :--- | :--- | :--- | :--- | ---: |
| **Maki.vc** | `3100c303-0795-4673-a04d-7e612b421eb4` | `MAKI.VC FUND I Ky` | `Company` | FI | 134 |
| **Icebreaker.vc** | `70fb3317-cd8c-4c52-aa86-66502789bce3` | `Icebreaker.vc` | `Organization` | FI | 130 |
| **Lifeline Ventures** | `476a73ac-afa2-4713-9f73-188bc7ec0b95` | `Lifeline Ventures` | `Company` | FI | 130 |
| **General Catalyst** | `03faa252-0570-4e3f-be48-39d7740d964c` | `General Catalyst` | `Company` | GB | 138 |
| **Project A Ventures** | `7b1b7e16-c539-429d-8af0-883594236fdb` | `Project A Ventures GmbH & Co. KG` | `Company` | DE | 134 |
| **Speedinvest** | `94e0ca6a-4e39-4181-bd84-11f264d0aa62` | `Speedinvest GmbH` | `Company` | AT | 134 |
| **OTB Ventures** | `d26a193e-78e6-47ed-a265-877bc5a60b35` | `OTB Ventures` | `Organization` | NL | 115 |
| **AlbionVC** | `b750fe8f-886a-44df-b0e1-a3037d4727fb` | `AlbionVC` | `Company` | GB | 130 |
| **Accel** | `aee065b7-5ae9-45c7-8c30-457f6d339958` | `Accel` | `Company` | US | 138 |
| **Index Ventures** | `4a7ccd5d-1310-46b0-bd42-4ff8b409acc5` | `Index Ventures` | `Company` | GB | 138 |
| **Balderton Capital (LLP)** | `c96fa533-91c0-5674-bcbe-0d0dc934b7fa` | `Balderton Capital` | `Company` | GB | 130 |
| **Northzone** | `208d7baa-10cd-4a73-825b-5bd3e827f79f` | `Northzone` | `Organization` | GB | 130 |
| **EQT Ventures** | `d6cf13e1-92ff-4567-bd72-30316f2498e5` | `EQT Ventures` | `Organization` | SE | 115 |
| **Innovestor** | `6a966907-4006-4a4b-8d11-2330f76cb3cd` | `Innovestor Oy` | `Company` | FI | 130 |

### Provenance Preservation Contract (`cala_verified_investor_match`)
1. **Metadata Enrichment Envelope**: When returning a company or investor node whose Slush record matches a `CONFIRMED` entry (by exact normalized `company_name` + `website` host/country check), attach:
   ```json
   "cala_verified_investor_match": {
     "cala_id": "03faa252-0570-4e3f-be48-39d7740d964c",
     "cala_name": "General Catalyst",
     "cala_entity_type": "Company",
     "cala_description": "...",
     "verification_status": "CONFIRMED",
     "match_score": 138,
     "sources": [
       {
         "publisher": "Cala Entity Verification Audit (Slush 2026 Investors)",
         "url": "docs/cala_investors_verification.json#idx=...",
         "date": "2026-11-14"
       }
     ]
   }
   ```
2. **Cross-Dataset Stub Bridge Bonus (9 Confirmed Overlaps in `snapshot.json`)**:
   9 `CONFIRMED` investors in `cala_investors_verification.json` (`Speedinvest`, `Innovestor`, `Capnamic`, `Supercell Investments`, `Capmont Technology GmbH`, `42CAP`, `BII - BioInnovation Institute`, `Hard2beat`, `Vinthera`) already exist as `cala:<uuid>` stub nodes in `snapshot.json`! If `backend-agent` links e.g. `slush-company:1aaec80d-f0d4-464b-92ce-f9eef1e136e5` (`Speedinvest`) ↔ `cala:94e0ca6a-4e39-4181-bd84-11f264d0aa62` (`Speedinvest GmbH`), it MUST record an explicit `identity_decision` with provenance `cala_verified_investor_match` so every path step remains 100% auditable.

---

## 6. Provenance Normalization Rule

Every Cala property, relationship, and numerical observation carries source metadata. Normalize and preserve all three fields on every fact surfaced to `frontend-agent`:
```json
{
  "value": "Trust Exchange AG",
  "sources": [
    {
      "publisher": "zefix.admin.ch",
      "url": "https://www.zefix.admin.ch/ZefixREST/api/v1/firm/1773204.json",
      "date": "2026-10-22",
      "source_rank": "FILING"
    }
  ]
}
```
- Map Cala property/edge `sources[i].name` → `publisher`, `sources[i].document` → `url`, `sources[i].date` → `date`.
- Map Cala `numerical_observations[i].data[j].origin` (`origin.name` → `publisher`, `origin.url` → `url`, `origin.published_time` → `date`).
- Discard any Cala relationship assertion lacking a non-empty source document from traversable networking paths (keep in audit diagnostics only).

---

## 7. Strict Failure & Zero-Confabulation Protocol

> [!CAUTION]
> **Halt Live Enrichment, Never Confabulate.** On any Cala live API failure, `backend-agent` MUST immediately halt live enrichment, return the deterministic offline `snapshot.json` graph result (if available), and attach a structured `live_enrichment` status block so `frontend-agent` renders an honest status badge. **Never** substitute LLM training recall, unverified web scraping, or guessed edges for missing Cala data.

| Condition / HTTP Status | Retry Policy | `GET /api/cala/enrich/{id}` `status` (`API_CONTRACT.md` v2.1) | Exact UI Badge Label | Required Backend Action |
| :--- | :--- | :--- | :--- | :--- |
| No `CALA_API_KEY` set | Do not call | `"unconfigured"` | `Offline Verified Snapshot` | Serve `snapshot.json` baseline; return HTTP 200 with `status: "unconfigured"` |
| Entity has no Cala UUID & no verified match | Do not call / empty search | `"not_mapped"` | `Cala Live: No Verified Match` | Halt live enrichment; distinguish empty match (`results: []`) from `too complex` query error |
| HTTP `200 OK` (with data) | — | `"ok"` | `Cala Live Verified` | Return sourced facts under `namespace: "cala_live_enrichment"` + cache in Valkey/SQLite |
| **HTTP `402 Payment Required`** | **NEVER retry** | `"payment_required"` | `Cala Live Paused (402 Insufficient Balance)` | Trip circuit-breaker for session; still attach `cala_verified_investor_match` UUID if in `docs/cala_investors_verification.json` |
| **HTTP `429 Too Many Requests`** | **NEVER retry** | `"rate_limited"` | `Cala Live Rate-Limited (429)` | Halt live call immediately; surface status badge |
| **Timeout (`> 180s`) / `504`** | **Retry ONCE** | `"timeout"` | `Cala Live Timeout (180s Limit)` | Retry same request once at 180s timeout; if second attempt times out, halt & return `"timeout"` |
| **HTTP `401`/`403` / `5xx` / Network** | Do not retry | `"unavailable"` | `Cala Live Unavailable — Snapshot Only` | Halt live call; point operator to `https://console.cala.ai/api-keys` / `https://docs.cala.ai` (never echo key!) |

### Exact `GET /api/cala/enrich/{entity_id}` Response on HTTP 402 (`API_CONTRACT.md` §3.9)
```json
{
  "status": "payment_required",
  "entity_id": "slush-company:064d2f99-f6e2-4933-982a-e9b0db023afb",
  "entity_name": "Maki.vc",
  "cala_uuid": "3100c303-0795-4673-a04d-7e612b421eb4",
  "cala_verified_investor_match": {
    "cala_id": "3100c303-0795-4673-a04d-7e612b421eb4",
    "cala_name": "MAKI.VC FUND I Ky",
    "cala_type": "Company",
    "country": "FI",
    "best_score": 134,
    "namespace": "cala_verified_investor_match"
  },
  "namespace": "cala_live_enrichment",
  "cached": false,
  "elapsed_ms": 84.3,
  "message": "Live Cala API returned HTTP 402 (Insufficient Balance). Showing verified offline snapshot & investor audit facts only; zero unverified fallback was used.",
  "introspection": null,
  "verified_facts": [],
  "verified_relationships": []
}
```
