# Unicorn Radar — Shared Frontend <-> Backend API Contract (`v2.1`)

> **Product**: **Unicorn Radar — Cala × Slush Connection Intelligence** (*"Make Unicorns Real — separating the unicorns from the horses"*, Hackjunction 2026)
> **Contract Owner**: `architect-coordinator` (`020b1bb6-d7f6-4b35-8164-94c03c73b06f`)
> **Consumers**: `backend-agent`, `frontend-agent`, `cala-intelligence-agent`, `qa-integrations-agent`
> **Status**: **LOCKED FOR PARALLEL IMPLEMENTATION**

---

## 1. Runtime & Zero-Build Frontend Architecture

### 1.1 Base URL & Dual-Mount Routing
- **Default Local Origin**: `http://127.0.0.1:8080` (`HOST=127.0.0.1`, `PORT=8080`).
- **Same-Origin Static Frontend Serving**:
  - `GET /` serves `frontend/index.html` (`text/html; charset=utf-8`) for browser navigation. (If `Accept: application/json` is explicitly sent with no `text/html` or `frontend/index.html` is absent during headless backend unit tests, `GET /` may return the `/health` JSON payload).
  - Static assets under `frontend/` (`frontend/css/*`, `frontend/js/*`, `frontend/assets/*`) are served at `/css/*`, `/js/*`, `/assets/*` (and `/static/*` alias if needed) with `Cache-Control: no-cache` in local dev.
- **Zero-Build Native ES2022 Requirement (CRITICAL)**:
  - **Node.js / npm / Vite / Webpack are NOT installed on the target demo machine.**
  - `frontend/` MUST be pure, dependency-free **native browser ES2022 modules** (`index.html` + `css/` + `js/*.js` loaded via `<script type="module" src="/js/app.js"></script>`), using native SVG/Canvas2D force/layered graph rendering, native `fetch` + `ReadableStream` SSE parsing, and CSS variables. Zero bundling or compilation steps may be required to run the app!
- **100% Reference Backward Compatibility + Extended `/api/*` Namespace**:
  - Every core endpoint MUST be mounted at **both** `/api/<route>` **and** root legacy `/<route>`:
    - `/api/health` **and** `/health`
    - `/api/questions` **and** `/questions`
    - `/api/coverage` **and** `/coverage`
    - `/api/entities` **and** `/entities`
    - `/api/analyses` **and** `/analyses` (`GET` & `POST`)
    - `/api/analyses/{run_id}` **and** `/analyses/{run_id}`
    - `/api/analyses/{run_id}/prompt` **and** `/analyses/{run_id}/prompt`
  - Extended Webapp & Partner Tech Challenge endpoints live under `/api/*`:
    - `GET /api/presets`
    - `POST /api/analyses/stream` (Server-Sent Events)
    - `GET /api/cala/enrich/{entity_id}`
    - `GET /api/infrastructure/status`
    - `GET /api/craci/provenance`
    - `POST /api/craci/audit`

### 1.2 Core Epistemic & Zero-Confabulation Invariants
1. **Strict Provenance (`ev:...`)**: Every traversable edge, entity profile attribute, attendance record, generated claim, and meeting-brief bullet MUST reference valid `evidence_ids` present in `response.evidence[]`.
2. **Non-Bridge Edge Exclusion**: `PARTICIPATES_IN_EVENT` (2,990 Slush event links), generic industry/location links (95), and unattributed Cala provider-only edges without `source_documents` are **never** used as professional connection bridges (`traversable: false`).
3. **Strict Source Namespace Separation**:
   - **Snapshot Verified Graph** (`nodes`, `edges`, `evidence` from reconciled `cala_graph.json` + `slush_people.json` + `slush_companies.json`).
   - **`cala_live_enrichment`**: Live `/v1` Cala Knowledge Graph API lookups (`https://api.cala.ai/v1`) kept in a dedicated `cala_live_enrichment` envelope with full publisher/URL/date `sources[]`. Never silently merged into snapshot hop counts; halts cleanly on missing key / HTTP 402 / 429 / timeout.
   - **`generated_claims` & `meeting_brief`**: Gemini API synthesis + Gemma Open Model entailment audit, strictly constrained to `evidence_ids` from the retrieved subgraph, with automatic deterministic fallback (`evidence_template_fallback`) if validation fails.
4. **Error Envelope Convention**:
   - Validation / bad input errors (`HTTP 400`, `HTTP 404`, `HTTP 413`, `HTTP 500`) MUST always include `{"error": "Human-readable message"}` (FastAPI exception handlers must normalize `RequestValidationError` / `ValueError` to `{"error": "..."}` with HTTP 400 so legacy tests asserting `"error" in result` pass).
   - Non-JSON bodies, arrays (`["not", "an", "object"]`), unknown `question_id`, or unpermitted user-control fields (`prompt`, `objective`, `max_hops`, etc.) MUST return `HTTP 400 {"error": "..."}`. Request bodies > 16 KiB return `HTTP 413 {"error": "Request must contain at most 16 KiB"}`.

---

## 2. Core Data Models

### 2.1 Entity Node View (`NodeView`)
```json
{
  "id": "slush-person:a853ebe4032701b5326988a7",
  "name": "Camille Accolas",
  "entity_type": "Person",
  "record_completeness": "full",
  "participation": [
    {
      "status": "announced_attendee",
      "event_id": "cala:bc844d56-6ab4-452b-96bf-2661e86e592b",
      "evidence_ids": ["ev:c978302e3e133606c2d3ac70", "ev:cb541847e912bd0879c59544"]
    }
  ],
  "evidence_ids": ["ev:d0cc7c796bae9386e77c1f35", "ev:f682ef8649906af9968fb02d"],
  "identity_warnings": [],
  "profile": {
    "job_title": "Co-Founder",
    "headline": "Co-Founder",
    "biography": "Camille Accolas co-founded Trust Exchange...",
    "description": null,
    "professional_topics": ["Impact finance", "Climate ventures", "Institutional capital"],
    "location_raw": null,
    "profile_url": null,
    "linkedin_url": null,
    "personal_website": null,
    "website": null,
    "work_experience": {
      "section_present": false,
      "entries": [
        {
          "organization": "The Decision Room",
          "role": "Co-founder & Advisor",
          "source_url": "https://thedecisionroom.net/about",
          "start_date": null,
          "end_date": null,
          "provenance": [
            {
              "source_kind": "public_source_research",
              "url": "https://thedecisionroom.net/about",
              "title": "The Decision Room — About",
              "checked_at": "2026-11-14"
            }
          ]
        }
      ]
    }
  },
  "source_ids": {
    "slush": ["imported_person:20b90a5b99f9e01d4073"],
    "cala": ["f2539cca-dfe2-524c-bd78-7780a2d75505"]
  }
}
```
*Note*: Compact `NodeView` (used in `results[].target` or `results[].entity`) omits `profile` and `source_ids`; full `NodeView` (used in `resolved_entities`, `graph.nodes[]`, and `results[].person`) includes `profile` and `source_ids`.

### 2.2 Graph Edge & Discovered Path (`GraphEdge`, `GraphPath`)
```json
{
  "id": "edge:c04fc7bf9ea7f920569c7ea6",
  "source": "slush-person:a853ebe4032701b5326988a7",
  "target": "slush-company:ad355578-0a33-40e0-bb20-cc7e3e56d890",
  "type": "FOUNDED",
  "properties": { "role": "Co-Founder" },
  "evidence_ids": ["ev:20e2530641e051ed4c5c056d", "ev:77e50c5a7cb324cf6ca4eda4"],
  "origins": ["slush", "cala"],
  "traversable": true,
  "hop_cost": 1,
  "temporal_status": "undated",
  "derived": false,
  "evidence_strength": "documented_primary",
  "support_status": "documented",
  "source_support": "documented"
}
```

```json
{
  "id": "path:227b87338383156ca7fe",
  "node_ids": [
    "slush-person:a853ebe4032701b5326988a7",
    "slush-company:ad355578-0a33-40e0-bb20-cc7e3e56d890"
  ],
  "edge_ids": ["edge:c04fc7bf9ea7f920569c7ea6"],
  "hop_count": 1,
  "relations": [
    {
      "edge_id": "edge:c04fc7bf9ea7f920569c7ea6",
      "source_id": "slush-person:a853ebe4032701b5326988a7",
      "target_id": "slush-company:ad355578-0a33-40e0-bb20-cc7e3e56d890",
      "predicate": "FOUNDED",
      "from_id": "slush-person:a853ebe4032701b5326988a7",
      "to_id": "slush-company:ad355578-0a33-40e0-bb20-cc7e3e56d890",
      "traversal": "forward",
      "evidence_ids": ["ev:20e2530641e051ed4c5c056d"],
      "temporal_status": "undated",
      "hop_cost": 1,
      "statement": "Camille Accolas founded Trust Exchange."
    }
  ],
  "explanation": "Camille Accolas founded Trust Exchange.",
  "rank_reasons": [
    "1 supported relationship step",
    "Every relationship has a preserved evidence record",
    "Every relationship also has a source-document reference",
    "Some relationship dates are unverified"
  ]
}
```

### 2.3 Evidence Record (`EvidenceItem`)
```json
{
  "id": "ev:d0cc7c796bae9386e77c1f35",
  "dataset": "slush_people",
  "record_pointer": "/people/148",
  "source_documents": [
    {
      "url": "https://ie.linkedin.com/showcase/discover-swisstech",
      "title": "Discover SwissTech Slush 2026 Delegation",
      "publisher": "LinkedIn / SwissTech",
      "source_type": "official_2026_delegation_person_announcement",
      "checked_at": "2026-11-14",
      "evidence": "Camille Accolas: named Slush 2026 startup representative."
    }
  ],
  "record": { "...raw source record snapshot..." }
}
```
*Note*: `response.evidence` in live snapshot queries is a JSON array `EvidenceItem[]` where each element carries `"id": "ev:..."`. Frontend helpers should support indexing `evidence` whether passed as `EvidenceItem[]` or `{[id]: EvidenceItem}`.

### 2.4 Grounded AI Claims, Gemma Audit & Meeting Brief
```json
{
  "generated_claims": [
    {
      "text": "Camille Accolas is documented as having founded Trust Exchange and holds a board role at the company.",
      "evidence_ids": ["ev:20e2530641e051ed4c5c056d", "ev:f682ef8649906af9968fb02d"],
      "gemma_audit": {
        "verdict": "supported",
        "model": "gemma-3-27b-it",
        "note": "Entailed directly by FOUNDED and IS_BOARD_MEMBER_OF assertions; no unverified attendance inferred."
      }
    }
  ],
  "gemma_audit_summary": {
    "enabled": true,
    "provider": "google_ai_studio",
    "model": "gemma-3-27b-it",
    "overall_verdict": "pass",
    "audited_claims": 3,
    "supported_claims": 3,
    "flagged_claims": 0,
    "elapsed_ms": 412.5
  },
  "meeting_brief": {
    "composer": "gemini",
    "model": "gemini-2.5-flash",
    "executive_summary": "Camille Accolas has a direct 1-hop founding and board relationship with Trust Exchange and is a named Slush 2026 startup representative (physical check-in unverified).",
    "talking_points": [
      {
        "text": "Trust Exchange builds a stakeholder-agnostic venture evaluation standard for European startups and investors.",
        "evidence_ids": ["ev:9f12cf630d86eae5a72258b5"]
      },
      {
        "text": "Accolas previously led Brainforest's accelerator programme and co-founded The Decision Room.",
        "evidence_ids": ["ev:d0cc7c796bae9386e77c1f35"]
      }
    ],
    "smart_questions": [
      {
        "text": "How does Trust Exchange carry venture evaluations across investor conversations without standardizing away sector nuance?",
        "evidence_ids": ["ev:9f12cf630d86eae5a72258b5"]
      }
    ],
    "attendance_verification": {
      "status": "announced_attendee",
      "note": "Named Slush 2026 participation is documented, but physical check-in and meeting availability are not established.",
      "evidence_ids": ["ev:c978302e3e133606c2d3ac70"]
    },
    "warm_intro_paths": [
      {
        "path_id": "path:227b87338383156ca7fe",
        "hop_count": 1,
        "summary": "Camille Accolas founded Trust Exchange.",
        "evidence_ids": ["ev:20e2530641e051ed4c5c056d"]
      }
    ]
  },
  "storage_meta": {
    "backend": "aiven_pg",
    "cache_layer": "aiven_valkey",
    "cached": false,
    "elapsed_ms": 384.2
  }
}
```
*Fallback Rule*: Even when `GEMINI_API_KEY` is absent or `composer_mode == "template"`, the backend MUST still populate a deterministic, evidence-backed `meeting_brief` (`composer: "evidence_template"`) derived strictly from `results`, `graph.paths`, and `evidence_ids` so the UI Meeting Brief card always renders rich, cited intelligence offline and online!

---

## 3. Endpoint Specifications

### 3.1 `GET /api/health` & `GET /health`
Returns service readiness, deterministic snapshot hash, and active partner integration flags.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "graph_version": "b2e1e3d55b0e200e1923f7dfd0f723d8d5736f8a646f95fd1200ad8ecae7cf70",
  "pipeline_version": "2.1.0",
  "query_policy_version": "four-task-ranking-2.0.0",
  "capabilities": {
    "gemini": true,
    "gemma": true,
    "aiven_pg": false,
    "aiven_valkey": false,
    "craci": true,
    "cala_live": true
  }
}
```

---

### 3.2 `GET /api/questions` & `GET /questions`
Returns the 4 fixed connection-intelligence tasks keyed by `question_id` (preserving exact legacy dictionary shape `resp[question_id]["label"]` and `resp[question_id]["fields"]`, enriched with UI metadata).

**Response `200 OK`**:
```json
{
  "person_to_company": {
    "id": "person_to_company",
    "label": "How is this person connected to this company?",
    "short_label": "Person → Company",
    "subtitle": "Bounded 4-hop warm-path discovery across Slush & Cala assertions",
    "max_hops": 4,
    "fields": {
      "source": "Person",
      "target": "Company"
    },
    "placeholders": {
      "source": "e.g. Camille Accolas or Dani Penev",
      "target": "e.g. Trust Exchange or Y Combinator"
    }
  },
  "company_to_company": {
    "id": "company_to_company",
    "label": "How is this company connected to that company?",
    "short_label": "Company ↔ Company",
    "subtitle": "Shared founders, executives, investors, funding rounds & board bridges",
    "max_hops": 4,
    "fields": {
      "source": "Company",
      "target": "Company"
    },
    "placeholders": {
      "source": "e.g. Slicker",
      "target": "e.g. Y Combinator"
    }
  },
  "company_network": {
    "id": "company_network",
    "label": "What professional network surrounds this company?",
    "short_label": "Company Network",
    "subtitle": "2-hop ecosystem map grouped into Direct People, Investors, Direct Companies & Indirect Connections",
    "max_hops": 2,
    "fields": {
      "company": "Company"
    },
    "placeholders": {
      "company": "e.g. Trust Exchange"
    }
  },
  "company_representatives": {
    "id": "company_representatives",
    "label": "Who from this company can I approach at Slush, and what should I know about them?",
    "short_label": "Slush Representatives",
    "subtitle": "Affiliated people with named Slush participation evidence vs. unverified-attendance affiliates",
    "max_hops": 1,
    "fields": {
      "company": "Company"
    },
    "placeholders": {
      "company": "e.g. Trust Exchange"
    }
  }
}
```

---

### 3.3 `GET /api/presets`
Curated one-click demo scenarios covering all 4 questions, multi-hop investor paths, cross-source identity ambiguity (`Y Combinator`, `Ben Fletcher`), and verified negative (`insufficient_data`) cases.

**Response `200 OK`**:
```json
{
  "presets": [
    {
      "id": "founder_path_trust_exchange",
      "title": "Camille Accolas → Trust Exchange",
      "badge": "Q1 · 1-Hop Dual-Source",
      "description": "Cross-source joined founder & board paths backed by Cala + SwissTech delegation evidence.",
      "expected_status": "partial",
      "request": {
        "question_id": "person_to_company",
        "source": "Camille Accolas",
        "target": "Trust Exchange"
      }
    },
    {
      "id": "investor_multihop_yc",
      "title": "Dani Penev → Y Combinator (Cala Investor)",
      "badge": "Q1 · Multi-Hop Investor",
      "description": "3-path founder/investor bridge to canonical Cala Y Combinator identity.",
      "expected_status": "partial",
      "request": {
        "question_id": "person_to_company",
        "source": "Dani Penev",
        "target": "Y Combinator",
        "target_id": "cala:1e86655e-373d-4fe8-be13-af3713581f73"
      }
    },
    {
      "id": "company_bridge_slicker_yc",
      "title": "Slicker ↔ Y Combinator",
      "badge": "Q2 · Company-to-Investor",
      "description": "Company-to-company investment & funding-round path in Cala graph.",
      "expected_status": "partial",
      "request": {
        "question_id": "company_to_company",
        "source": "Slicker",
        "target": "Y Combinator",
        "target_id": "cala:1e86655e-373d-4fe8-be13-af3713581f73"
      }
    },
    {
      "id": "ecosystem_trust_exchange",
      "title": "Trust Exchange — 2-Hop Ecosystem",
      "badge": "Q3 · Surrounded Network",
      "description": "Bounded 2-step network grouped into direct people, investors, and indirect connections.",
      "expected_status": "partial",
      "request": {
        "question_id": "company_network",
        "company": "Trust Exchange"
      }
    },
    {
      "id": "slush_reps_trust_exchange",
      "title": "Trust Exchange — Slush Approach Brief",
      "badge": "Q4 · Slush Representatives",
      "description": "Separates named Slush 2026 participants from affiliated people with unverified attendance.",
      "expected_status": "partial",
      "request": {
        "question_id": "company_representatives",
        "company": "Trust Exchange"
      }
    },
    {
      "id": "ambiguous_yc",
      "title": "Ambiguity Guardrail: Dani Penev → 'Y Combinator'",
      "badge": "Disambiguation Picker",
      "description": "Demonstrates zero silent entity merging between Cala investor node and Slush text org stubs.",
      "expected_status": "needs_resolution",
      "request": {
        "question_id": "person_to_company",
        "source": "Dani Penev",
        "target": "Y Combinator"
      }
    },
    {
      "id": "ambiguous_ben_fletcher",
      "title": "Duplicate Person Guardrail: 'Ben Fletcher'",
      "badge": "Identity Integrity",
      "description": "Preserves unresolved duplicate person candidates rather than fabricating a merge.",
      "expected_status": "needs_resolution",
      "request": {
        "question_id": "person_to_company",
        "source": "Ben Fletcher",
        "target": "Trust Exchange"
      }
    },
    {
      "id": "no_path_honest_negative",
      "title": "Zero-Confabulation Negative: Trust Exchange ↔ Slicker",
      "badge": "Honest No-Path",
      "description": "Both attend Slush 2026, but event co-attendance is excluded as a bridge — returns insufficient_data.",
      "expected_status": "insufficient_data",
      "request": {
        "question_id": "company_to_company",
        "source": "Trust Exchange",
        "target": "Slicker"
      }
    }
  ]
}
```

---

### 3.4 `GET /api/coverage` & `GET /coverage`
Returns the full snapshot manifest, dataset SHA-256 digests, reconciliation counts, and explicit Cala `complete: false` snapshot limitations.

**Response `200 OK`**:
```json
{
  "graph_version": "b2e1e3d55b0e200e1923f7dfd0f723d8d5736f8a646f95fd1200ad8ecae7cf70",
  "importer_version": "2.0.0",
  "datasets": [
    {
      "id": "slush_people",
      "filename": "slush_people.json",
      "sha256": "...",
      "size_bytes": 1234567
    },
    {
      "id": "cala",
      "filename": "cala_graph.json",
      "sha256": "...",
      "size_bytes": 2345678
    },
    {
      "id": "slush_companies",
      "filename": "slush_companies.json",
      "sha256": "...",
      "size_bytes": 3456789
    }
  ],
  "counts": {
    "nodes": 10785,
    "edges": 4023,
    "traversable_edges": 933,
    "evidence_records": 7800,
    "cala_full_entity_records": 41,
    "cala_full_company_records": 40,
    "cala_endpoint_entities": 3279,
    "cala_input_edges": 3411,
    "slush_people_primary_records": 952,
    "slush_people_platform_ids": 10,
    "slush_company_records": 6275,
    "slush_company_attendee_rows": 210,
    "cross_source_company_merges": 32,
    "cross_source_person_merges": 1,
    "unresolved_identity_candidates": 2371,
    "slush_supported_edges": 618,
    "cala_supported_edges": 3406,
    "both_source_edges": 1,
    "node_types": { "Company": 6800, "Person": 3800, "Event": 1 },
    "edge_types": { "PARTICIPATES_IN_EVENT": 2990, "WORKS_AT": 280, "INVESTED_IN": 190 }
  },
  "cala_coverage": {
    "complete": false,
    "reason": "time_budget_exceeded",
    "maximum_hops": 4,
    "retrieved_by_hop": {}
  },
  "people_coverage": {
    "collection_status": "partial",
    "platform_person_records": 10,
    "all_event_attendees_exported": false,
    "directory_exhaustion_verified": false
  },
  "identity_policy": "Source IDs first; company name/alias plus matching domain; person exact name plus resolved company affiliation. Name-only candidates are retained without merging.",
  "limitations": [
    "Cala export completeness is False; 41 full entity records (40 companies) were captured. Other edge endpoints can be stubs.",
    "The people file is partial; directory evidence and announcements do not independently establish physical event attendance.",
    "Missing fields, paths, attendees or relationships mean not established in these snapshots, not absence in the real world."
  ]
}
```

---

### 3.5 `GET /api/entities` & `GET /entities`
Resolves a `Person` or `Company` name/ID AND returns ranked fuzzy/prefix `suggestions[]` for interactive typeahead search bars.

**Query Parameters**:
- `name` *(required, string, 1..300 chars)*: Entity name, alias, prefix, or canonical ID (`cala:...`, `slush-person:...`, `slush-company:...`). Missing/empty/>300 returns `HTTP 400 {"error": "Supply a name query parameter"}`.
- `type` *(optional, `"Person"` | `"Company"`)*: Filters entity class (`Company` matches `Company`, `Investor`, `Organization`, `Fund`).
- `limit` *(optional, int, default `15`, min `1`, max `50`)*: Max `suggestions` / `candidates` items returned.

**Status Values Note (Backward Compatibility + Clarity)**:
- `status`: `"resolved"` | `"needs_resolution"` | `"not_found"` (matches reference `QueryEngine.resolve` 100%).
- `resolution_state`: `"resolved"` | `"ambiguous"` | `"not_found"` (normalized alias where `"needs_resolution"` maps to `"ambiguous"` so frontend components can check either field).
- `suggestions`: Always populated (up to `limit` items) with prefix + fuzzy matches ordered by exact match, prefix match, degree (traversable connections), and record completeness (`full` before `stub`), so typeahead dropdowns feel instantaneous even when `status == "resolved"` or partial characters are typed!

**Response `200 OK`**:
```json
{
  "status": "needs_resolution",
  "resolution_state": "ambiguous",
  "query": "Y Combinator",
  "entity_type": "Company",
  "entity": null,
  "candidates": [
    {
      "id": "cala:1e86655e-373d-4fe8-be13-af3713581f73",
      "name": "Y Combinator",
      "entity_type": "Company",
      "record_completeness": "stub",
      "participation": [],
      "evidence_ids": ["ev:..."],
      "origin_badges": ["cala"],
      "traversable_degree": 18,
      "context": {
        "website": "https://www.ycombinator.com",
        "location_raw": "Mountain View, CA"
      },
      "affiliations": ["Slicker", "..."]
    },
    {
      "id": "slush-organization:8f41...",
      "name": "Y Combinator",
      "entity_type": "Company",
      "record_completeness": "stub",
      "participation": [],
      "evidence_ids": ["ev:..."],
      "origin_badges": ["slush_reference"],
      "traversable_degree": 1,
      "context": {},
      "affiliations": []
    }
  ],
  "suggestions": [
    {
      "id": "cala:1e86655e-373d-4fe8-be13-af3713581f73",
      "name": "Y Combinator",
      "entity_type": "Company",
      "record_completeness": "stub",
      "origin_badges": ["cala"],
      "traversable_degree": 18,
      "subtitle": "Cala Investor / Organization · 18 verified links"
    }
  ],
  "reason": "Multiple distinct records share this name; select a canonical ID."
}
```

---

### 3.6 `POST /api/analyses` & `POST /analyses`
Executes one of the 4 fixed graph queries, composes grounded explanations + meeting brief (and optional Gemma entailment audit), persists the run in Aiven PostgreSQL / SQLite, caches in Aiven Valkey / SQLite, and returns the complete analysis envelope.

**Request Body**:
```json
{
  "question_id": "person_to_company",
  "source": "Camille Accolas",
  "target": "Trust Exchange",
  "source_id": null,
  "target_id": null,
  "refresh": false,
  "composer_mode": "auto",
  "include_cala_live": false
}
```
- **Required fields by `question_id`**:
  - `person_to_company`: `source` (or `source_id`) AND `target` (or `target_id`)
  - `company_to_company`: `source` (or `source_id`) AND `target` (or `target_id`)
  - `company_network`: `company` (or `company_id`)
  - `company_representatives`: `company` (or `company_id`)
- **Optional Execution Options** (accepted on `/api/analyses` and `/analyses`; `null` values for unused `_id` fields are ignored cleanly, whereas ANY unknown/arbitrary field such as `prompt`, `objective`, `max_hops` MUST raise `HTTP 400 {"error": "Unexpected request fields: ..."}`):
  - `refresh` (`bool`, default `false`): Bypass cache and persist a fresh `run_id`.
  - `composer_mode` (`"auto"` | `"template"` | `"gemini"` | `"gemma"` | `"gemini_gemma_audit"`, default `"auto"`):
    - `"template"`: Pure deterministic offline `evidence_template` (< 10ms).
    - `"gemini"`: Gemini structured `generated_claims` + `meeting_brief` validated against `evidence_ids`.
    - `"gemma"`: Gemma open-model structured `generated_claims` + `meeting_brief` validated against `evidence_ids`.
    - `"gemini_gemma_audit"`: Gemini composes `generated_claims` + `meeting_brief`, then Gemma audits each claim for strict entailment (`gemma_audit: {verdict, model, note}`).
    - `"auto"`: Uses `"gemini_gemma_audit"` if both Gemini & Gemma are configured, `"gemini"` if Gemini is configured, `"gemma"` if Gemma is configured, or `"template"` if neither key is configured (note: on legacy `POST /analyses` when `composer_mode` is omitted, defaults to `"template"` unless `CALA_DEMO_COMPOSER_URL` or explicit `composer_mode` is requested, preserving sub-5ms deterministic behavior and exact `test_service.py` compatibility!).
  - `include_cala_live` (`bool`, default `false`): When `true`, attaches `cala_live_enrichment` for resolved focal entities that have a `source_ids.cala` UUID (or live lookup match) if `CALA_API_KEY` is configured.
- **Canonical Cache Key Rule**:
  - `cache_key` hashes `{ canonical_entity_ids, question_id, graph_version, pipeline_version, query_policy_version, prompt_version, effective_composer_mode, include_cala_live }`.
  - On `GET /analyses/{run_id}`, the exact originally saved JSON is recovered (`cached: false` as originally stored). When a subsequent `POST` hits cache, the returned copy sets `cached: true`, `storage_meta.cached: true`, `submitted_inputs`, and `request_elapsed_ms`.

**Response `200 OK` (Complete / Partial / Ambiguous / Insufficient Data)**:
Note: Ambiguous (`"status": "needs_resolution"`) and no-path (`"status": "insufficient_data"`) are valid analytical outcomes returned with `HTTP 200` and saved with a `run_id`!
```json
{
  "schema_version": "2.0",
  "run_id": "fea99c56-4080-49b7-ad00-7125b49b5465",
  "question_id": "person_to_company",
  "question": "How is this person connected to this company?",
  "inputs": {
    "source": "Camille Accolas",
    "target": "Trust Exchange"
  },
  "original_request": {
    "question_id": "person_to_company",
    "source": "Camille Accolas",
    "target": "Trust Exchange"
  },
  "status": "partial",
  "resolved_entities": {
    "source": { "...NodeView (profile=true)..." },
    "target": { "...NodeView (profile=true)..." }
  },
  "resolution": null,
  "summary": "Found 2 supported professional paths from Camille Accolas to Trust Exchange within 4 steps.",
  "template_summary": "Found 2 supported professional paths from Camille Accolas to Trust Exchange within 4 steps.",
  "results": [
    {
      "rank": 1,
      "path_id": "path:227b87338383156ca7fe",
      "target": { "...NodeView..." },
      "rank_reasons": [
        "1 supported relationship step",
        "Every relationship has a preserved evidence record",
        "Every relationship also has a source-document reference",
        "Some relationship dates are unverified"
      ],
      "explanation": "Camille Accolas founded Trust Exchange."
    }
  ],
  "groups": null,
  "attendance_unverified": null,
  "graph": {
    "nodes": [ "...NodeView (profile=true)..." ],
    "edges": [ "...GraphEdge..." ],
    "paths": [ "...GraphPath..." ]
  },
  "evidence": [ "...EvidenceItem (id='ev:...')..." ],
  "generated_claims": [
    {
      "text": "Camille Accolas founded Trust Exchange and holds a documented board role at the company.",
      "evidence_ids": ["ev:20e2530641e051ed4c5c056d", "ev:f682ef8649906af9968fb02d"],
      "gemma_audit": {
        "verdict": "supported",
        "model": "gemma-3-27b-it",
        "note": "Directly supported by FOUNDED and IS_BOARD_MEMBER_OF edges."
      }
    }
  ],
  "gemma_audit_summary": {
    "enabled": true,
    "provider": "google_ai_studio",
    "model": "gemma-3-27b-it",
    "overall_verdict": "pass",
    "audited_claims": 2,
    "supported_claims": 2,
    "flagged_claims": 0,
    "elapsed_ms": 390.1
  },
  "meeting_brief": {
    "composer": "gemini",
    "model": "gemini-2.5-flash",
    "executive_summary": "...",
    "talking_points": [{ "text": "...", "evidence_ids": ["ev:..."] }],
    "smart_questions": [{ "text": "...", "evidence_ids": ["ev:..."] }],
    "attendance_verification": {
      "status": "announced_attendee",
      "note": "Named Slush participation documented; physical check-in and availability unverified.",
      "evidence_ids": ["ev:c978302e3e133606c2d3ac70"]
    },
    "warm_intro_paths": [
      {
        "path_id": "path:227b87338383156ca7fe",
        "hop_count": 1,
        "summary": "Camille Accolas founded Trust Exchange.",
        "evidence_ids": ["ev:20e2530641e051ed4c5c056d"]
      }
    ]
  },
  "cala_live_enrichment": null,
  "coverage": {
    "snapshot_complete": false,
    "snapshot_limitations": ["..."],
    "truncated": false,
    "max_hops": 4,
    "visited_nodes": 19,
    "visited_states": 22,
    "truncation_reasons": [],
    "path_result_limit_applied": false,
    "data_quality_exclusions": { "professional_edges_without_evidence": 12 },
    "max_displayed_results": 10,
    "max_paths_per_endpoint": 3
  },
  "generation_mode": "gemini_gemma_audit",
  "prompt_version": "cala-slush-four-questions-v2",
  "graph_version": "b2e1e3d55b0e200e1923f7dfd0f723d8d5736f8a646f95fd1200ad8ecae7cf70",
  "pipeline_version": "2.1.0",
  "query_policy_version": "four-task-ranking-2.0.0",
  "generated_at": "2026-11-14T20:00:00+00:00",
  "cached": false,
  "elapsed_ms": 642.8,
  "storage_meta": {
    "backend": "sqlite",
    "cache_layer": "sqlite_cache",
    "cached": false,
    "elapsed_ms": 642.8
  },
  "interpretation": "Paths describe sourced professional relationships, not personal acquaintance, a guaranteed introduction, meeting availability, or physical event attendance."
}
```

**Per-Question `results[]` Item Variants**:
- **`person_to_company` & `company_to_company`**:
  `{ rank, path_id, target: NodeView, rank_reasons: string[], explanation: string }`
- **`company_network`**:
  `{ rank, entity: NodeView, group: "direct_people" | "investors" | "direct_companies" | "indirect_connections", path_ids: string[], rank_reasons: string[], explanation: string }` plus top-level `groups: Record<string, string[]>`.
- **`company_representatives`**:
  `{ rank, person: NodeView(profile=true), attendance: Participation[], path_ids: string[], rank_reasons: string[], explanation: string, contact_interpretation: string }` plus top-level `attendance_unverified: Array<NodeView & { path_ids: string[] }>`.
- **When `status` is `"needs_resolution"` or `"not_found"`**:
  `response.resolution` contains `{ source?: ResolutionResult, target?: ResolutionResult, company?: ResolutionResult }` with `candidates[]` so the UI immediately opens the Disambiguation Picker card!

---

### 3.7 `POST /api/analyses/stream` (Server-Sent Events)
Accepts the exact same JSON body as `POST /api/analyses` and streams live multi-stage pipeline telemetry (`Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`).

**SSE Wire Format**:
Each event uses `event: stage\ndata: <JSON>\n\n` (and `event: error\ndata: {"error": "..."}\n\n` on failure).

**Ordered Pipeline Stages (`stage` field)**:
1. `resolving`: `{ "stage": "resolving", "status": "running", "message": "Resolving canonical Slush & Cala identities...", "elapsed_ms": 1.2 }`
2. `cache_check`: `{ "stage": "cache_check", "status": "running" | "hit" | "miss", "cache_layer": "aiven_valkey" | "sqlite_cache", "message": "Checking Aiven Valkey / canonical versioned cache...", "elapsed_ms": 3.4 }`
3. `traversing`: `{ "stage": "traversing", "status": "running", "message": "Traversing 933 verified assertions (excluding 2,990 event links)...", "visited_nodes": 24, "elapsed_ms": 8.1 }`
4. `ranking`: `{ "stage": "ranking", "status": "running", "message": "Ranking paths by primary-document provenance, hop cost & hub penalty...", "path_count": 2, "elapsed_ms": 10.5 }`
5. `composing_gemini`: `{ "stage": "composing_gemini", "status": "running" | "skipped", "model": "gemini-2.5-flash", "message": "Synthesizing citation-locked claims & Slush meeting brief with Gemini...", "elapsed_ms": 310.0 }`
6. `auditing_gemma`: `{ "stage": "auditing_gemma", "status": "running" | "skipped", "model": "gemma-3-27b-it", "message": "Auditing claim entailment & zero-confabulation rules with Gemma...", "elapsed_ms": 590.2 }`
7. `persisting_aiven`: `{ "stage": "persisting_aiven", "status": "running", "backend": "aiven_pg" | "sqlite", "message": "Persisting immutable run & evidence package...", "elapsed_ms": 612.0 }`
8. `complete`:
   ```json
   {
     "stage": "complete",
     "status": "done",
     "run_id": "fea99c56-4080-49b7-ad00-7125b49b5465",
     "elapsed_ms": 620.4,
     "analysis": { "...exact same full Analysis JSON returned by POST /api/analyses..." }
   }
   ```

---

### 3.8 `GET /api/analyses`, `GET /api/analyses/{run_id}`, `GET /api/analyses/{run_id}/prompt`
(Also mounted at `/analyses`, `/analyses/{run_id}`, `/analyses/{run_id}/prompt`)

1. **`GET /api/analyses?limit=25`**:
   ```json
   {
     "analyses": [
       {
         "run_id": "fea99c56-4080-49b7-ad00-7125b49b5465",
         "created_at": "2026-11-14T20:00:00+00:00",
         "question_id": "person_to_company",
         "status": "partial",
         "graph_version": "b2e1e3d55b0e200e1923f7dfd0f723d8d5736f8a646f95fd1200ad8ecae7cf70",
         "request": {
           "question_id": "person_to_company",
           "source": "Camille Accolas",
           "target": "Trust Exchange"
         }
       }
     ]
   }
   ```
2. **`GET /api/analyses/{run_id}`**:
   Returns `200 OK` with the **byte-for-byte identical** JSON object saved when `run_id` was created, or `404 {"error": "Analysis not found"}`.
3. **`GET /api/analyses/{run_id}/prompt`**:
   Returns `200 OK` with `{ prompt_version, system, input: { question_id, status, inputs, resolved_entities, summary, results, graph, evidence, coverage, limitations, conflicts }, response_schema }`, or `404 {"error": "Analysis not found"}`.

---

### 3.9 `GET /api/cala/enrich/{entity_id}`
Performs optional live Cala `/v1` structured entity enrichment (`entity_search`/`entity_lookup` -> `entity_introspection` -> projected `entity_retrieval` against `https://api.cala.ai/v1` with `X-API-KEY`), strictly isolated in `cala_live_enrichment` and cached in Valkey/SQLite.

**Query Parameters**:
- `refresh` *(optional, bool, default `false`)*

**Response `200 OK`** (Always returns HTTP 200 with structured transparent `status` when Cala key is unconfigured, entity is unmapped, or upstream returns 402/429/timeout — **never** fabricates fallback facts):
```json
{
  "status": "ok",
  "entity_id": "slush-company:ad355578-0a33-40e0-bb20-cc7e3e56d890",
  "entity_name": "Trust Exchange",
  "cala_uuid": "0220cf38-d013-5600-9616-31da01caa416",
  "namespace": "cala_live_enrichment",
  "cached": true,
  "elapsed_ms": 14.2,
  "message": "Verified live facts retrieved from Cala Knowledge Graph API (/v1).",
  "introspection": {
    "available_attributes": ["name", "website", "hq_country", "founded_year", "description"],
    "available_relationships": ["FOUNDED", "IS_BOARD_MEMBER_OF", "INVESTED_IN"]
  },
  "verified_facts": [
    {
      "field": "website",
      "label": "Official Website",
      "value": "https://trustexchange.world/",
      "sources": [
        {
          "publisher": "Trust Exchange",
          "url": "https://trustexchange.world/",
          "date": "2026-10-22"
        }
      ]
    }
  ],
  "verified_relationships": [
    {
      "predicate": "FOUNDED",
      "direction": "incoming",
      "peer_name": "Camille Accolas",
      "peer_cala_id": "f2539cca-dfe2-524c-bd78-7780a2d75505",
      "sources": [
        {
          "publisher": "The Decision Room",
          "url": "https://thedecisionroom.net/about",
          "date": "2026-10-22"
        }
      ]
    }
  ]
}
```
*Possible `status` values*: `"ok"` | `"unconfigured"` | `"not_mapped"` | `"payment_required"` | `"rate_limited"` | `"timeout"` | `"unavailable"`.

---

## 4. Partner Tech Challenge Endpoints

### 4.1 `GET /api/infrastructure/status` (Aiven PostgreSQL & Valkey + Gemini & Gemma Telemetry)
Provides live operational telemetry for the **Aiven** data layer and **Google DeepMind (Gemini + Gemma)** reasoning pipeline.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "storage": {
    "primary_backend": "aiven_pg",
    "aiven_pg_configured": true,
    "aiven_pg_connected": true,
    "sqlite_fallback_active": false,
    "saved_analyses_count": 14,
    "avg_write_ms": 6.4
  },
  "cache": {
    "primary_cache": "aiven_valkey",
    "aiven_valkey_configured": true,
    "aiven_valkey_connected": true,
    "memory_lru_active": true,
    "cache_hits": 23,
    "cache_misses": 8,
    "hit_rate_pct": 74.2,
    "avg_cache_hit_ms": 1.8
  },
  "models": {
    "gemini": {
      "configured": true,
      "model": "gemini-2.5-flash",
      "role": "Primary Grounded Claim & Slush Meeting Brief Composer",
      "calls": 8,
      "avg_latency_ms": 340.5
    },
    "gemma": {
      "configured": true,
      "provider": "google_ai_studio",
      "model": "gemma-3-27b-it",
      "role": "Open-Weight Claim Entailment & Zero-Confabulation Auditor",
      "calls": 8,
      "avg_latency_ms": 280.1
    },
    "deterministic_template": {
      "available": true,
      "role": "Zero-latency offline baseline & validation fallback"
    }
  },
  "cala": {
    "snapshot_loaded": true,
    "snapshot_nodes": 10785,
    "snapshot_traversable_edges": 933,
    "live_api_configured": true
  },
  "craci": {
    "api_configured": false,
    "mode": "verified_workspace_snapshot",
    "workflow_runner_label": "craci"
  }
}
```

---

### 4.2 `GET /api/craci/provenance` (CRACI CI/CD Build, SBOM & Egress Provenance)
Queries `https://api.craci.com` (`/v1preview1/jobs`, `/v1preview1/sbom`, `/v1preview1/network-trace`, `/v1preview1/usage` using `Authorization: Bearer $CRACI_API_TOKEN`) when configured, or generates a deterministic, verifiable **local workspace CycloneDX SBOM + `.github/workflows` CRACI runner policy & dependency provenance report** when offline, cross-referenced against entities in the Cala/Slush snapshot.

**Query Parameters**:
- `repo` *(optional, string, e.g. `owner/Cala-Junction-Hack`)*
- `job_id` *(optional, string)*

**Response `200 OK`**:
```json
{
  "status": "ok",
  "source_mode": "craci_api_live",
  "organization": "cala-junction",
  "repository": "cala-junction/unicorn-radar",
  "workflow_policy": {
    "workflows_scanned": 1,
    "craci_runner_jobs": [
      {
        "workflow": ".github/workflows/craci-ci.yml",
        "job_name": "verify-and-sbom",
        "runs_on": "craci",
        "architecture": "amd64",
        "image": "default",
        "egress_policy": "package-aware-proxy"
      }
    ],
    "compliant": true
  },
  "latest_job": {
    "provider": "github",
    "repository": "cala-junction/unicorn-radar",
    "runId": "12948102910",
    "jobId": "39104829101",
    "commitSha": "a1b2c3d4e5f6...",
    "branch": "main",
    "workflow": ".github/workflows/craci-ci.yml",
    "jobName": "verify-and-sbom",
    "status": "completed",
    "startedAt": "2026-11-14T19:30:00Z"
  },
  "sbom": {
    "bomFormat": "CycloneDX",
    "specVersion": "1.7",
    "complete": true,
    "component_count": 8,
    "components": [
      {
        "name": "fastapi",
        "version": "0.115.0",
        "purl": "pkg:pypi/fastapi@0.115.0",
        "license": "MIT",
        "supplier_vendor": "FastAPI / Tiangolo"
      },
      {
        "name": "google-genai",
        "version": "1.0.0",
        "purl": "pkg:pypi/google-genai@1.0.0",
        "license": "Apache-2.0",
        "supplier_vendor": "Google"
      },
      {
        "name": "valkey",
        "version": "6.1.0",
        "purl": "pkg:pypi/valkey@6.1.0",
        "license": "MIT",
        "supplier_vendor": "Linux Foundation / Valkey"
      }
    ]
  },
  "network_trace": {
    "schemaVersion": "1.0",
    "total_observations": 4,
    "policy_denied_count": 0,
    "unmatched_egress_count": 0,
    "observations": [
      {
        "sequence": 0,
        "observedAt": "2026-11-14T19:30:04Z",
        "protocol": "http",
        "http": {
          "method": "GET",
          "originUrl": "https://pypi.org/simple/fastapi/",
          "ipAddress": "151.101.0.223",
          "statusCode": 200,
          "bodySizeBytes": "48210",
          "matchedRule": "allow-pypi-registry",
          "policyDenied": false
        }
      }
    ]
  },
  "usage": {
    "vcpuSeconds": 48,
    "vcpuMinutes": 0.8
  },
  "cala_entity_matches": [
    {
      "vendor_query": "Google",
      "matched_entity_id": "cala:...",
      "matched_name": "Google",
      "entity_type": "Company",
      "evidence_ids": ["ev:..."]
    }
  ]
}
```
*(When `CRACI_API_TOKEN` is not set, `source_mode` MUST be `"verified_workspace_snapshot"` and clearly label that `sbom` and `workflow_policy` were computed deterministically from the local workspace `pyproject.toml`, `uv.lock`/installed packages, and `.github/workflows/*.yml` without fabricating remote job IDs!)*

---

### 4.3 `POST /api/craci/audit` (Grounded Supply-Chain & Egress Audit via Gemini/Gemma)
Runs Gemini / Gemma (with deterministic template fallback) strictly over the CRACI provenance payload (`sbom`, `network_trace`, `workflow_policy`) to verify supply-chain hygiene, SBOM completeness, and egress lock-down.

**Request Body**:
```json
{
  "job_id": null,
  "repo": null,
  "focus": "full",
  "composer_mode": "auto"
}
```

**Response `200 OK`**:
```json
{
  "status": "ok",
  "source_mode": "verified_workspace_snapshot",
  "auditor_model": "gemma-3-27b-it",
  "risk_level": "low",
  "sbom_completeness_verdict": "verified_lockfile_and_runtime" ,
  "egress_verdict": "clean_no_exfiltration_detected",
  "summary": "All 8 Python runtime dependencies carry permissive OSI licenses (MIT / Apache-2.0 / BSD) and Linux CI jobs route to isolated CRACI runners (`runs-on: craci`).",
  "findings": [
    {
      "severity": "info",
      "category": "runner_routing",
      "title": "Isolated VM Build Routing (`runs-on: craci`)",
      "detail": "Workflow jobs target CRACI isolated Linux VMs with automatic package-proxy SBOM capture.",
      "evidence_ref": "workflow:.github/workflows/craci-ci.yml"
    },
    {
      "severity": "recommendation",
      "category": "sbom_completeness",
      "title": "Enforce Block-Unmatched Egress Policy for Complete Attestation",
      "detail": "Per CRACI guidelines, pair `runs-on: craci` with a restricted egress policy blocking unmatched destinations so compromised transitive hooks cannot exfiltrate secrets and builds earn a complete SBOM.",
      "evidence_ref": "policy:egress"
    }
  ],
  "elapsed_ms": 295.4
}
```

---

## 5. File Ownership Summary (`AGENTS.md` Enforcement)

| Directory / Path | Exclusive Owner | Notes |
| :--- | :--- | :--- |
| `docs/contracts/`, `docs/agent-bus/`, `pyproject.toml`, `.env.example`, `scripts/` | `architect-coordinator` | Shared specs, env template, launcher scripts |
| `docs/contracts/cala-fixtures/` | `cala-intelligence-agent` | Verified Cala `/v1` JSON fixtures & query templates |
| `backend/` | `backend-agent` | FastAPI server (`backend/main.py` or `backend/app.py`), `ingest.py`, `queries.py`, `service.py`, `store.py` (Aiven PG + Valkey + SQLite), `generation.py` (Gemini + Gemma + Template), `cala_client.py`, `craci_client.py`, `data/` |
| `frontend/` | `frontend-agent` | Zero-build ES2022 `index.html`, `css/`, `js/` |
| `tests/`, `.github/workflows/` | `qa-integrations-agent` | Unit + E2E API/provenance tests & `runs-on: craci` CI workflow |
