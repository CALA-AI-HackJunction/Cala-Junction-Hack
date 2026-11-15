"""Conservative, offline import of the supplied Cala Slush 2026 spreadsheets (or legacy JSON) + Slush datasets.

The importer records evidence rather than treating descriptions as relationship
instructions. It uses only Python's standard library and performs no network IO.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .investor_registry import get_investor_registry
except ImportError:
    from investor_registry import get_investor_registry


IMPORTER_VERSION = "3.0.0"
EVENT_SOURCE_ID = "bc844d56-6ab4-452b-96bf-2661e86e592b"
PROFESSIONAL_TYPES = {
    "WORKS_AT", "FOUNDED", "INVESTED_IN", "IS_BOARD_MEMBER_OF",
    "IS_CEO_OF", "IS_CTO_OF", "IS_CFO_OF", "IS_COO_OF", "IS_CSO_OF",
    "IS_CMO_OF", "IS_CCO_OF", "IS_CRO_OF", "IS_EXECUTIVE_OF",
    "IS_VICEPRESIDENT_OF", "IS_MANAGING_DIRECTOR_OF", "IS_MEMBER_OF",
    "IS_BENEFICIARY_OWNER_OF", "IS_CONTROL_PERSON_OF", "AFFILIATED_WITH", "ADVISES",
    "IS_SUBSIDIARY_OF", "IS_ULTIMATE_PARENT_OF", "IS_DIRECT_OWNER_OF",
    "PARTICIPATES_IN_FUNDING_ROUND", "PARTICIPATES_IN_CORPORATE_EVENT",
}
AFFILIATION_TYPES = PROFESSIONAL_TYPES - {
    "INVESTED_IN", "PARTICIPATES_IN_FUNDING_ROUND", "PARTICIPATES_IN_CORPORATE_EVENT",
    "IS_SUBSIDIARY_OF", "IS_ULTIMATE_PARENT_OF", "IS_DIRECT_OWNER_OF",
}
GENERIC_NODE_TYPES = {
    "Event", "Industry", "DomainName", "Country", "CountrySubdivision", "City",
    "Place", "Location", "Group", "DependentTerritory", "CorporateEvent",
}
ARRAY_FIELDS = {
    "secondary_industry", "focus_industries", "business_types", "software_hardware",
    "round_role", "lp_class", "lp_fund_stage", "focus_startup_stage",
    "investment_into_vc_as_a_lp", "curated_collections_tags",
}
SPREADSHEET_REQUIRED_FILES = (
    "slush_2026_roster.csv",
    "company_dossier.csv",
    "people_speakers_and_connectors.csv",
    "top_warm_intros.csv",
    "shared_bridges.csv",
    "edges_human_readable.csv",
)


def stable_hash(value, size=24):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:size]


def normalized_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def company_name_key(value):
    value = normalized_name(value)
    return re.sub(r"(?:\s+(?:oy|ab|gmbh|ltd|limited|inc|llc|sa|ag|ug|bv|bvba|plc|flexco|aps|ou|oü|b\s*v|s\s*a))+$", "", value)


def host(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        p = urlsplit(value if "://" in value else "https://" + value)
        return (p.hostname or "").casefold().removeprefix("www.") or None
    except ValueError:
        return None


def profile_id(value, kind="companies"):
    if not isinstance(value, str):
        return None
    m = re.search(r"/" + re.escape(kind) + r"/([0-9a-fA-F-]{36})(?:[/?#]|$)", value)
    return m.group(1).lower() if m else None


def unique(items):
    if not items:
        return []
    if all(isinstance(x, str) for x in items):
        return list(dict.fromkeys(items))
    seen, result = set(), []
    for item in items:
        key = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _append_unique_str(lst: list[str], seen: set[str], value: str) -> None:
    if value and value not in seen:
        seen.add(value)
        lst.append(value)


def documents_from(value):
    """Keep source documents, without upgrading a retrieved record to verified truth."""
    if not value:
        return []
    if isinstance(value, str):
        return [{"url": value}] if value.startswith(("https://", "http://")) else []
    if isinstance(value, list):
        return unique([d for item in value for d in documents_from(item)])
    if isinstance(value, dict):
        out = []
        if value.get("document") or value.get("url"):
            out.append(value)
        for key in ("sources", "source_urls", "source_references", "provenance"):
            out.extend(documents_from(value.get(key)))
        if value.get("source_url"):
            out.extend(documents_from(value["source_url"]))
        return unique(out)
    return []


def document_host(doc):
    value = doc.get("url") or doc.get("document")
    if isinstance(value, dict):
        value = value.get("endpoint") or value.get("url")
    return host(value)


def temporal_status(properties):
    if properties.get("valid_until") or properties.get("end_date"):
        return "historical"
    if properties.get("is_current") is True:
        return "current"
    raw = str(properties.get("date_range_raw") or "").casefold()
    if re.search(r"\b(?:present|current)\b", raw):
        return "current"
    return "undated"


def role_predicates(role, default="AFFILIATED_WITH"):
    """Map explicit structured role labels, never general biographies."""
    if not role:
        return [default]
    text = str(role).casefold()
    found = bool(re.search(r"\b(?:co[\s-]?)?founder\b(?!['’]s)", text))
    predicates = ["FOUNDED"] if found else []
    if re.search(r"\b(?:advis(?:or|er)|advisory)\b", text):
        predicates.append("ADVISES")
    elif "board" in text and ("member" in text or "chair" in text or "director" in text) and "observer" not in text:
        predicates.append("IS_BOARD_MEMBER_OF")
    elif not re.search(r"\b(?:deputy|assistant|associate|office of|former)\b", text):
        for acronym, long_name in (
            ("CEO", "chief executive"), ("CTO", "chief technology"),
            ("CFO", "chief financial"), ("COO", "chief operating"),
            ("CMO", "chief marketing"), ("CCO", "chief commercial"),
        ):
            if re.search(r"\b" + acronym.casefold() + r"\b", text) or long_name in text:
                predicates.append("IS_" + acronym + "_OF")
    if not predicates:
        predicates.append(default)
    return predicates


def _load_cala_spreadsheets(cala_source: Path) -> tuple[dict[str, list[dict[str, str]]], list[tuple[str, Path | bytes]]]:
    """Load CSV tables from a directory or .zip archive."""
    tables: dict[str, list[dict[str, str]]] = {}
    dataset_files: list[tuple[str, Path | bytes]] = []

    if cala_source.is_dir():
        for fn in SPREADSHEET_REQUIRED_FILES:
            fpath = cala_source / fn
            if not fpath.is_file():
                raise FileNotFoundError(f"Missing required Cala spreadsheet {fn} in {cala_source}")
            raw_bytes = fpath.read_bytes()
            dataset_files.append((f"cala_{fpath.stem}", fpath))
            tables[fpath.stem] = list(csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig"))))
        sql_path = cala_source / "readable_views.sql"
        if sql_path.is_file():
            dataset_files.append(("cala_readable_views_sql", sql_path))
    elif cala_source.is_file() and cala_source.suffix.lower() == ".zip":
        dataset_files.append(("cala_spreadsheets_zip", cala_source))
        with zipfile.ZipFile(cala_source, "r") as zf:
            names = set(zf.namelist())
            for fn in SPREADSHEET_REQUIRED_FILES:
                if fn not in names:
                    raise FileNotFoundError(f"Missing required Cala spreadsheet {fn} inside {cala_source}")
                text = zf.read(fn).decode("utf-8-sig")
                tables[Path(fn).stem] = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ValueError(f"Unsupported Cala spreadsheets path: {cala_source}")
    return tables, dataset_files


def _parse_affiliations_targets(raw_affs: str) -> set[str]:
    """Extract normalized target names from `Org Name [REL],Other Org [REL]` for homonym disambiguation."""
    if not raw_affs:
        return set()
    targets = set()
    for part in raw_affs.split(","):
        cleaned = re.sub(r"\s*\[[^\]]*\]\s*$", "", part).strip()
        if cleaned:
            targets.add(normalized_name(cleaned))
    return targets


class Builder:
    def __init__(self, people, cala_data, companies, dataset_entries, *, cala_mode="spreadsheets"):
        self.people = people
        self.cala_data = cala_data
        self.companies = companies
        self.dataset_entries = dataset_entries
        self.cala_mode = cala_mode

        self.nodes, self.edges, self.evidence = {}, {}, {}
        self._node_ev_sets: dict[str, set[str]] = defaultdict(set)
        self._edge_ev_sets: dict[str, set[str]] = defaultdict(set)
        self.slush_company_ids, self.cala_ids, self.people_keys = {}, {}, {}
        self.slush_platform_person_index: dict[str, str] = {}
        self.name_index, self.domain_index = defaultdict(set), defaultdict(set)
        self.identity_decisions, self.unresolved_matches, self.warnings = [], [], []
        self.stats = Counter()
        self.cala_coverage_meta: dict = {}
        self.investor_registry = get_investor_registry()

    def ev(self, dataset, pointer, record, docs=None, **extra):
        ident = "ev:" + stable_hash([dataset, pointer, record])
        if ident not in self.evidence:
            self.evidence[ident] = {
                "id": ident,
                "dataset": dataset,
                "record_pointer": pointer,
                "source_documents": documents_from(record) if docs is None else unique(docs),
                "record": record,
                **extra,
            }
        return ident

    def _add_node_evidence(self, ident: str, eid: str | None) -> None:
        if not eid:
            return
        _append_unique_str(self.nodes[ident]["evidence_ids"], self._node_ev_sets[ident], eid)

    def node(self, ident, name, entity_type, provider, source_id, properties=None,
             evidence_id=None, completeness="stub", aliases=None):
        if ident not in self.nodes:
            self.nodes[ident] = {
                "id": ident,
                "name": name or ident,
                "entity_type": entity_type or "Unknown",
                "aliases": [],
                "source_ids": {},
                "properties": {},
                "source_properties": {},
                "participation": [],
                "evidence_ids": [],
                "record_completeness": completeness,
                "identity_status": "supported",
            }
        n = self.nodes[ident]
        if name and name != n["name"] and name not in n["aliases"]:
            n["aliases"].append(name)
        if aliases:
            for al in aliases:
                if al and al != n["name"] and al not in n["aliases"]:
                    n["aliases"].append(al)
        if source_id is not None:
            existing_sids = n["source_ids"].setdefault(provider, [])
            if source_id not in existing_sids:
                existing_sids.append(source_id)
        if properties:
            clean_props = {k: v for k, v in properties.items() if v is not None and v != ""}
            if clean_props:
                n["source_properties"].setdefault(provider, {}).update(clean_props)
                for key, value in clean_props.items():
                    if key not in n["properties"] or n["properties"][key] is None or n["properties"][key] == "":
                        n["properties"][key] = value
                    elif value is not None and n["properties"][key] != value:
                        alts = n.setdefault("property_alternatives", {}).setdefault(key, [])
                        alt_item = {"source": provider, "value": value, "evidence_id": evidence_id}
                        if alt_item not in alts:
                            alts.append(alt_item)
        if evidence_id:
            self._add_node_evidence(ident, evidence_id)
        if completeness == "full":
            n["record_completeness"] = "full"
        return ident

    def participation(self, ident, status, evidence_ids, event_id=None):
        target_event = event_id or ("cala:" + EVENT_SOURCE_ID)
        for existing in self.nodes[ident]["participation"]:
            if existing["status"] == status and existing["event_id"] == target_event:
                for eid in evidence_ids:
                    if eid and eid not in existing["evidence_ids"]:
                        existing["evidence_ids"].append(eid)
                return
        self.nodes[ident]["participation"].append({
            "status": status,
            "event_id": target_event,
            "evidence_ids": [e for e in evidence_ids if e],
        })

    def edge(self, source, target, predicate, props, evidence_ids, origin):
        props = {k: v for k, v in (props or {}).items() if k not in ("id", "sources") and v is not None and v != ""}
        ident = "edge:" + stable_hash([source, predicate, target, props])
        if ident not in self.edges:
            self.edges[ident] = {
                "id": ident,
                "source": source,
                "target": target,
                "type": predicate,
                "properties": props,
                "evidence_ids": [],
                "origins": [],
                "traversable": predicate in PROFESSIONAL_TYPES,
                "hop_cost": 1,
                "temporal_status": temporal_status(props),
                "derived": False,
            }
        e_obj = self.edges[ident]
        ev_set = self._edge_ev_sets[ident]
        for eid in evidence_ids:
            _append_unique_str(e_obj["evidence_ids"], ev_set, eid)
        if origin not in e_obj["origins"]:
            e_obj["origins"].append(origin)
        return ident

    def index_company(self, ident):
        n = self.nodes[ident]
        if n["entity_type"] not in ("Company", "Organization", "EducationalInstitution", "NonprofitOrganization"):
            return
        for name in [n["name"], *n["aliases"]]:
            if name:
                self.name_index[normalized_name(name)].add(ident)
        website = n["properties"].get("website")
        h = host(website)
        if h:
            self.domain_index[h].add(ident)

    def import_companies(self):
        for i, raw in enumerate(self.companies):
            sid = raw.get("slush_company_id") or profile_id(raw.get("profile_link"))
            ident = "slush-company:" + (sid or stable_hash([i, raw.get("company_name")]))
            props = {k: v for k, v in raw.items() if k not in ("slush_2026_attendees", "slush_2026_attendee_research")}
            for key in ARRAY_FIELDS:
                if isinstance(props.get(key), str):
                    try:
                        parsed = json.loads(props[key])
                        if isinstance(parsed, (list, dict)):
                            props[key] = parsed
                    except (ValueError, TypeError):
                        self.warnings.append({"kind": "unparsed_array_field", "company_index": i, "field": key})
            props["description"] = props.get("company_description")
            eid = self.ev("slush_companies", "/" + str(i), props, docs=documents_from(raw.get("profile_link")))
            self.node(ident, raw.get("company_name"), "Company", "slush", sid or str(i), props, eid, "full")
            self.participation(ident, "company_listed", [eid])
            if sid:
                self.slush_company_ids[sid] = ident
            self.index_company(ident)
        self.stats["slush_company_records"] = len(self.companies)

    def _match_existing_slush_company(self, name: str, website: str | None, aliases: list[str] | None = None) -> str | None:
        h = host(website)
        if not h:
            return None
        domain_candidates = set(self.domain_index.get(h, set()))
        if not domain_candidates:
            return None
        name_keys = {company_name_key(x) for x in [name, *(aliases or [])] if x}
        candidates = [
            x for x in domain_candidates
            if name_keys & {company_name_key(n) for n in [self.nodes[x]["name"], *self.nodes[x]["aliases"]]}
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _check_invalid_collective_name(self, ident: str, raw_name: str | None) -> None:
        low = str(raw_name or "").casefold()
        if "including renowned industry leaders" in low:
            self.nodes[ident]["identity_status"] = "invalid"
            self.nodes[ident]["invalid_identity"] = True
            self.nodes[ident]["identity_warnings"] = ["Source uses a collective phrase rather than an identifiable entity."]
            self.warnings.append({"kind": "vague_source_entity", "id": ident, "name": raw_name})

    def import_cala_spreadsheets(self):
        tables = self.cala_data
        roster_rows = tables["slush_2026_roster"]
        dossier_rows = tables["company_dossier"]
        people_rows = tables["people_speakers_and_connectors"]
        bridge_rows = tables["shared_bridges"]
        edge_rows = tables["edges_human_readable"]
        warm_rows = tables["top_warm_intros"]

        # 0. Canonical Slush 2026 Event node
        seed_node_id = "cala:" + EVENT_SOURCE_ID
        seed_ev = self.ev(
            "cala_roster",
            "/event/slush-2026",
            {"id": EVENT_SOURCE_ID, "name": "Slush 2026", "entity_type": "Event"},
            docs=[{"url": "https://slush.org", "publisher": "Slush"}],
        )
        self.node(
            seed_node_id,
            "Slush 2026",
            "Event",
            "cala",
            EVENT_SOURCE_ID,
            {"description": "Slush 2026 startup and technology conference in Helsinki, Finland."},
            seed_ev,
            "full",
        )
        self.cala_ids[EVENT_SOURCE_ID] = seed_node_id

        # Lookup maps for Cala entities in spreadsheets
        org_by_norm_name: dict[str, str] = {}
        roster_uuid_by_name_type: dict[tuple[str, str], str] = {}
        roster_row_by_uuid: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)

        for idx, r in enumerate(roster_rows):
            mid = (r.get("member_id") or "").strip()
            mname = (r.get("member_name") or "").strip()
            mtype = (r.get("member_type") or "Company").strip()
            if mid and mname:
                roster_uuid_by_name_type[(normalized_name(mname), mtype)] = mid
                roster_row_by_uuid[mid].append((idx, r))

        def _lookup_confirmed_investor_uuid(name: str, website: str | None = None) -> str | None:
            n_key = normalized_name(name)
            h = host(website)
            if h and (n_key, h) in self.investor_registry.by_name_and_host:
                return self.investor_registry.by_name_and_host[(n_key, h)]["cala_id"]
            matches = self.investor_registry.by_unique_name.get(n_key) or []
            if len(matches) == 1:
                raw_inv, entry = matches[0]
                inv_h = host(raw_inv.get("website"))
                if not h or not inv_h or h == inv_h:
                    return entry["cala_id"]
            return None

        # 1. Import Company Dossiers (3,006 hydrated Cala Company / Organization profiles)
        for idx, row in enumerate(dossier_rows):
            cname = (row.get("company_name") or "").strip()
            if not cname:
                continue
            n_key = normalized_name(cname)
            website = (row.get("website") or "").strip() or None

            cala_uuid = (
                roster_uuid_by_name_type.get((n_key, "Company"))
                or roster_uuid_by_name_type.get((n_key, "Organization"))
                or _lookup_confirmed_investor_uuid(cname, website)
            )
            source_id = cala_uuid or ("dossier:" + stable_hash(["company_dossier", n_key, website or idx]))

            hop_val = None
            if (row.get("hop_from_slush") or "").strip().isdigit():
                hop_val = int(row["hop_from_slush"].strip())

            industries_raw = (row.get("industries") or "").strip()
            industries_list = [x.strip() for x in industries_raw.split(",") if x.strip()] if industries_raw else None

            props = {
                "website": website,
                "headquarters": (row.get("headquarters") or "").strip() or None,
                "location_raw": (row.get("headquarters") or "").strip() or None,
                "founded": (row.get("founded") or "").strip() or None,
                "funding_stage": (row.get("funding_stage") or "").strip() or None,
                "total_funding": (row.get("total_funding") or "").strip() or None,
                "employees": (row.get("employees") or "").strip() or None,
                "industries": industries_list,
                "primary_industry": industries_list[0] if industries_list else None,
                "hop_from_slush": hop_val,
                "leadership_and_team": (row.get("leadership_and_team") or "").strip() or None,
                "investors_summary": (row.get("investors") or "").strip() or None,
                "description": (row.get("description") or "").strip() or None,
            }
            docs = documents_from("https://" + website if website and "://" not in website else website)
            eid = self.ev("cala_company_dossier", f"/company_dossier/{idx}", row, docs=docs)

            # Reuse already-created node if duplicate dossier row for same company_name
            ident = org_by_norm_name.get(n_key)
            if ident is None:
                matched_slush = self._match_existing_slush_company(cname, website)
                if matched_slush:
                    ident = matched_slush
                    self.identity_decisions.append({
                        "source": "cala",
                        "source_id": source_id,
                        "canonical_id": ident,
                        "method": "unique_matching_domain_and_name_or_alias",
                    })
                else:
                    ident = "cala:" + (cala_uuid or stable_hash(["cala_org", "Company", n_key]))
                    candidates = sorted(self.name_index.get(n_key, set()))
                    if candidates:
                        self.unresolved_matches.append({
                            "source_id": source_id,
                            "name": cname,
                            "candidate_ids": candidates,
                            "reason": "name_only_without_independent_identity_corroboration",
                        })
                org_by_norm_name[n_key] = ident

            self.node(ident, cname, "Company", "cala", source_id, props, eid, "full")
            if cala_uuid:
                self.cala_ids[cala_uuid] = ident
            self._check_invalid_collective_name(ident, cname)
            self.index_company(ident)

        # 2. Import People, Speakers & Connectors (10,490 Cala Person records with real UUIDs)
        person_candidates_by_name: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
        for idx, row in enumerate(people_rows):
            pid = (row.get("person_id") or "").strip()
            pname = (row.get("person_name") or "").strip()
            if not pid or not pname:
                continue
            ident = "cala:" + pid
            at_slush = (row.get("at_slush_2026") or "").strip()
            bio = (row.get("bio") or "").strip() or None
            affs_raw = (row.get("affiliations_and_investments") or "").strip() or None
            conn_cnt = int(row["connected_orgs_count"]) if (row.get("connected_orgs_count") or "").strip().isdigit() else None

            props = {
                "biography": bio,
                "description": bio,
                "at_slush_2026": at_slush or None,
                "connected_orgs_count": conn_cnt,
                "affiliations_summary": affs_raw,
            }
            is_hydrated = bool(bio or (at_slush and at_slush.startswith("YES")))
            eid = self.ev("cala_people_connectors", f"/people_speakers_and_connectors/{idx}", row)
            self.node(ident, pname, "Person", "cala", pid, props, eid, "full" if is_hydrated else "stub")
            self.cala_ids[pid] = ident
            self._check_invalid_collective_name(ident, pname)
            person_candidates_by_name[normalized_name(pname)].append((ident, _parse_affiliations_targets(affs_raw or "")))

            if "SPEAKER" in at_slush:
                self.participation(ident, "announced_speaker", [eid], seed_node_id)
            elif at_slush.startswith("YES"):
                self.participation(ident, "announced_attendee", [eid], seed_node_id)

        # 3. Import Slush 2026 Roster (3,194 verified Slush 2026 attendees & speakers with real UUIDs)
        for idx, row in enumerate(roster_rows):
            mid = (row.get("member_id") or "").strip()
            mname = (row.get("member_name") or "").strip()
            mtype = (row.get("member_type") or "Company").strip()
            rel = (row.get("slush_relationship") or "PARTICIPATES_IN_EVENT").strip()
            srole = (row.get("slush_role") or "").strip()
            hyd = (row.get("hydration_status") or "").strip()
            if not mid or not mname:
                continue

            eid = self.ev("cala_roster", f"/slush_2026_roster/{idx}", row)
            n_key = normalized_name(mname)

            if mid in self.cala_ids:
                ident = self.cala_ids[mid]
            elif mtype != "Person" and n_key in org_by_norm_name:
                ident = org_by_norm_name[n_key]
                self.cala_ids[mid] = ident
            else:
                ident = "cala:" + mid
                self.cala_ids[mid] = ident
                if mtype != "Person":
                    org_by_norm_name.setdefault(n_key, ident)

            self.node(
                ident,
                mname,
                mtype,
                "cala",
                mid,
                {"slush_role": srole or None, "hydration_status": hyd or None},
                eid,
                "full" if hyd == "done" else "stub",
            )
            if mtype in ("Company", "Organization", "EducationalInstitution"):
                self.index_company(ident)

            if mtype == "Person":
                if rel == "SPOKE_AT" or srole == "SPEAKER":
                    self.participation(ident, "announced_speaker", [eid], seed_node_id)
                else:
                    self.participation(ident, "announced_attendee", [eid], seed_node_id)
            else:
                self.participation(ident, "cala_event_link", [eid], seed_node_id)

        # 4. Import Shared Bridges (4,630 high-connectivity ecosystem bridges)
        for idx, row in enumerate(bridge_rows):
            bname = (row.get("connector_name") or "").strip()
            btype = (row.get("entity_type") or "Company").strip()
            if not bname:
                continue
            n_key = normalized_name(bname)
            branches = int(row["slush_branches_connected"]) if (row.get("slush_branches_connected") or "").strip().isdigit() else None
            try:
                pscore = float(row["priority_score"]) if (row.get("priority_score") or "").strip() else None
            except ValueError:
                pscore = None
            hop_v = int(row["hop"]) if (row.get("hop") or "").strip().isdigit() else None
            b_status = (row.get("status") or "").strip()

            eid = self.ev("cala_shared_bridges", f"/shared_bridges/{idx}", row)
            props = {
                "slush_branches_connected": branches,
                "priority_score": pscore,
                "hop_from_slush": hop_v,
            }

            if btype == "Person":
                p_cands = person_candidates_by_name.get(n_key) or []
                if len(p_cands) == 1:
                    ident = p_cands[0][0]
                    self.node(ident, bname, "Person", "cala", None, props, eid, "full" if b_status == "done" else "stub")
            else:
                ident = org_by_norm_name.get(n_key)
                if ident is None:
                    inv_uuid = _lookup_confirmed_investor_uuid(bname)
                    ident = "cala:" + (inv_uuid or stable_hash(["cala_org", btype, n_key]))
                    org_by_norm_name[n_key] = ident
                    if inv_uuid:
                        self.cala_ids[inv_uuid] = ident
                self.node(ident, bname, btype, "cala", inv_uuid if ident.startswith("cala:") and len(ident) == 41 else None,
                          props, eid, "full" if b_status == "done" else "stub")
                self.index_company(ident)

        # 5. Pre-analyze FundingRound groups in edges_human_readable.csv so unrelated "Seed" rounds never merge
        fr_types = {"FundingRound", "PrivateCompanyFundingRound", "FundingRoundTranche"}
        fr_groups: dict[tuple[str, str, str, str], list[tuple[str, str]]] = defaultdict(list)
        for row in edge_rows:
            if row.get("relationship") == "PARTICIPATES_IN_FUNDING_ROUND" and row.get("target_type") in fr_types:
                url = (row.get("primary_source_url") or "").strip()
                if url:
                    key = (
                        row.get("target_type") or "FundingRound",
                        (row.get("target_name") or "").strip(),
                        (row.get("valid_since") or "").strip(),
                        url,
                    )
                    fr_groups[key].append(((row.get("source_name") or "").strip(), (row.get("role") or "").strip()))

        valid_shared_fr_keys = {
            key for key, members in fr_groups.items()
            if sum(1 for _, role in members if role == "ISSUER") == 1 and len(members) >= 2
        }

        generic_node_cache: dict[tuple[str, str], str] = {}

        def _resolve_edge_endpoint(name: str, etype: str, *, peer_name: str, row_idx: int, is_target: bool, row: dict[str, str]) -> str:
            n_key = normalized_name(name)
            if etype == "Event" and name == "Slush 2026":
                return seed_node_id
            if etype in fr_types:
                url = (row.get("primary_source_url") or "").strip()
                v_since = (row.get("valid_since") or "").strip()
                fr_key = (etype, name, v_since, url)
                if url and fr_key in valid_shared_fr_keys:
                    ident = "cala:fr-" + stable_hash(list(fr_key))
                else:
                    ident = "cala:fr-" + stable_hash([etype, name, v_since, url, row.get("source_name") or row_idx])
                self.node(ident, name or etype, etype, "cala", ident.removeprefix("cala:"), completeness="stub")
                return ident
            if etype in GENERIC_NODE_TYPES:
                gkey = (etype, n_key)
                ident = generic_node_cache.get(gkey)
                if ident is None:
                    ident = "cala:" + stable_hash(["cala_generic", etype, n_key])
                    generic_node_cache[gkey] = ident
                    self.node(ident, name, etype, "cala", ident.removeprefix("cala:"), completeness="stub")
                return ident
            if etype == "Person":
                cands = person_candidates_by_name.get(n_key) or []
                if len(cands) == 1:
                    return cands[0][0]
                if len(cands) > 1:
                    peer_norm = normalized_name(peer_name)
                    corroborated = [cid for cid, aff_targets in cands if peer_norm in aff_targets]
                    if len(corroborated) == 1:
                        return corroborated[0]
                    return cands[0][0]
                ident = "cala:" + stable_hash(["cala_person_edge", n_key])
                self.node(ident, name, "Person", "cala", ident.removeprefix("cala:"), completeness="stub")
                person_candidates_by_name[n_key].append((ident, set()))
                return ident

            # Company / Organization / EducationalInstitution / NonprofitOrganization
            ident = org_by_norm_name.get(n_key)
            if ident is None:
                inv_uuid = (
                    roster_uuid_by_name_type.get((n_key, etype))
                    or roster_uuid_by_name_type.get((n_key, "Company"))
                    or _lookup_confirmed_investor_uuid(name)
                )
                ident = "cala:" + (inv_uuid or stable_hash(["cala_org", etype, n_key]))
                org_by_norm_name[n_key] = ident
                if inv_uuid:
                    self.cala_ids[inv_uuid] = ident
                self.node(ident, name, etype, "cala", inv_uuid or ident.removeprefix("cala:"), completeness="stub")
                self._check_invalid_collective_name(ident, name)
                self.index_company(ident)
            return ident

        # 6. Import all 52,142 Cala Edges from edges_human_readable.csv
        for idx, row in enumerate(edge_rows):
            sname = (row.get("source_name") or "").strip()
            stype = (row.get("source_type") or "Unknown").strip()
            rel = (row.get("relationship") or "").strip()
            tname = (row.get("target_name") or "").strip()
            ttype = (row.get("target_type") or "Unknown").strip()
            if not sname or not tname or not rel:
                continue

            source = _resolve_edge_endpoint(sname, stype, peer_name=tname, row_idx=idx, is_target=False, row=row)
            target = _resolve_edge_endpoint(tname, ttype, peer_name=sname, row_idx=idx, is_target=True, row=row)

            # Attach domain name to company website if missing
            if rel == "HAS_DOMAIN_NAME" and tname and not self.nodes[source]["properties"].get("website"):
                self.nodes[source]["properties"]["website"] = tname
                self.index_company(source)

            url = (row.get("primary_source_url") or "").strip()
            srank = (row.get("source_rank") or "").strip()
            docs = []
            if url and url.startswith(("http://", "https://")):
                doc_entry = {"url": url, "publisher": host(url) or "Cala Source"}
                if srank:
                    doc_entry["source_rank"] = srank
                docs.append(doc_entry)

            props = {}
            if (row.get("role") or "").strip():
                props["role"] = row["role"].strip()
            if (row.get("is_lead") or "").strip():
                props["is_lead"] = row["is_lead"].strip() in ("1", "true", "True", "YES")
            if (row.get("valid_since") or "").strip():
                props["valid_since"] = row["valid_since"].strip()
            if (row.get("valid_until") or "").strip():
                props["valid_until"] = row["valid_until"].strip()
            if srank:
                props["source_rank"] = srank
            if (row.get("signal_weight") or "").strip():
                try:
                    props["signal_weight"] = float(row["signal_weight"])
                except ValueError:
                    pass

            compact_rec = {
                "source_name": sname,
                "relationship": rel,
                "target_name": tname,
                **props,
            }
            if url:
                compact_rec["primary_source_url"] = url

            eid = self.ev("cala", f"/edges_human_readable/{idx}", compact_rec, docs=docs)
            self.edge(source, target, rel, props, [eid], "cala")
            self._add_node_evidence(source, eid)
            self._add_node_evidence(target, eid)

            if target == seed_node_id:
                if rel == "SPOKE_AT":
                    self.participation(
                        source,
                        "announced_speaker" if self.nodes[source]["entity_type"] == "Person" else "cala_event_link",
                        [eid],
                        seed_node_id,
                    )
                elif rel == "PARTICIPATES_IN_EVENT":
                    self.participation(
                        source,
                        "announced_attendee" if self.nodes[source]["entity_type"] == "Person" else "cala_event_link",
                        [eid],
                        seed_node_id,
                    )

        self.stats["cala_roster_records"] = len(roster_rows)
        self.stats["cala_full_entity_records"] = len(dossier_rows) + sum(
            1 for r in people_rows if (r.get("bio") or "").strip() or (r.get("at_slush_2026") or "").startswith("YES")
        )
        self.stats["cala_full_company_records"] = len(dossier_rows)
        self.stats["cala_people_connector_records"] = len(people_rows)
        self.stats["cala_shared_bridges"] = len(bridge_rows)
        self.stats["cala_top_warm_intros"] = len(warm_rows)
        self.stats["cala_endpoint_entities"] = sum(
            1 for n in self.nodes.values() if "cala" in n.get("source_ids", {}) or n["id"].startswith("cala:")
        )
        self.stats["cala_input_edges"] = len(edge_rows)

        hop_dist = Counter(str(r.get("hop_from_slush") or "unknown") for r in dossier_rows)
        self.cala_coverage_meta = {
            "complete": False,
            "format": "slush_2026_spreadsheets",
            "reason": "Cala 5-hop Slush 2026 spreadsheets export (capped/pruned frontier).",
            "maximum_hops": 5,
            "retrieved_by_hop": dict(sorted(hop_dist.items())),
            "spreadsheets_counts": {
                "slush_2026_roster": len(roster_rows),
                "company_dossier": len(dossier_rows),
                "people_speakers_and_connectors": len(people_rows),
                "shared_bridges": len(bridge_rows),
                "top_warm_intros": len(warm_rows),
                "edges_human_readable": len(edge_rows),
            },
        }

    def import_cala_legacy_json(self):
        """Backward-compatible importer if a legacy Cala JSON graph dict is supplied."""
        cala = self.cala_data
        full = {entry["record"]["id"]: (i, entry["record"]) for i, entry in enumerate(cala.get("entities", []))}
        records = {}
        for e_raw in cala.get("edges", []):
            for rec in e_raw.get("records", []):
                if rec.get("id"):
                    records.setdefault(rec["id"], rec)
        for sid, (_, rec) in full.items():
            records[sid] = rec
        for sid, rec in records.items():
            kind = rec.get("entity_type") or "Unknown"
            aliases, props, evidence_id = [], {}, None
            if sid in full:
                i, _ = full[sid]
                props = {
                    k: v.get("value") if isinstance(v, dict) and "value" in v else v
                    for k, v in rec.get("properties", {}).items()
                }
                props.setdefault("description", rec.get("description"))
                aliases = props.get("aliases") if isinstance(props.get("aliases"), list) else []
                evidence_id = self.ev(
                    "cala",
                    "/entities/" + str(i) + "/record",
                    {k: v for k, v in rec.items() if k != "relationships"},
                    docs=[d for v in rec.get("properties", {}).values() for d in documents_from(v)],
                )
            ident = None
            if kind == "Company" and sid in full:
                ident = self._match_existing_slush_company(rec.get("name"), props.get("website"), aliases)
                if ident:
                    self.identity_decisions.append({
                        "source": "cala",
                        "source_id": sid,
                        "canonical_id": ident,
                        "method": "unique_matching_domain_and_name_or_alias",
                    })
            if ident is None:
                ident = "cala:" + sid
                if kind in ("Company", "Organization"):
                    candidates = sorted(self.name_index.get(normalized_name(rec.get("name")), set()))
                    if candidates:
                        self.unresolved_matches.append({
                            "source_id": sid,
                            "name": rec.get("name"),
                            "candidate_ids": candidates,
                            "reason": "name_only_without_independent_identity_corroboration",
                        })
            self.node(ident, rec.get("name"), kind, "cala", sid, props, evidence_id, "full" if sid in full else "stub", aliases)
            self.cala_ids[sid] = ident
            self._check_invalid_collective_name(ident, rec.get("name"))
            if kind in ("Company", "Organization"):
                self.index_company(ident)
        for raw in cala.get("edges", []):
            for sid in (raw.get("source"), raw.get("target")):
                if sid and sid not in self.cala_ids:
                    ident = "cala:" + sid
                    self.node(ident, sid, "Unknown", "cala", sid)
                    self.nodes[ident]["identity_status"] = "unresolved"
                    self.cala_ids[sid] = ident
        for i, raw in enumerate(cala.get("edges", [])):
            source, target = self.cala_ids[raw["source"]], self.cala_ids[raw["target"]]
            recs = raw.get("records") or []
            docs = unique([d for r in recs for d in documents_from(r.get("properties"))])
            eid = self.ev("cala", "/edges/" + str(i), raw, docs=docs)
            qualifier_sets = unique([
                {k: v for k, v in r.get("properties", {}).items() if k not in ("id", "sources")}
                for r in recs
            ]) or [{}]
            for props in qualifier_sets:
                self.edge(source, target, raw["type"], props, [eid], "cala")
            self._add_node_evidence(source, eid)
            self._add_node_evidence(target, eid)
            if raw["type"] == "PARTICIPATES_IN_EVENT" and raw["target"] == cala.get("seed", {}).get("id", EVENT_SOURCE_ID):
                self.participation(source, "cala_event_link", [eid], target)
        self.stats["cala_full_entity_records"] = len(full)
        self.stats["cala_full_company_records"] = sum(r.get("entity_type") == "Company" for _, r in full.values())
        self.stats["cala_endpoint_entities"] = len(self.cala_ids)
        self.stats["cala_input_edges"] = len(cala.get("edges", []))
        self.cala_coverage_meta = {k: cala.get(k) for k in ("complete", "reason", "maximum_hops", "retrieved_by_hop")}

    def company_reference(self, name, sid=None, url=None, docs=None, context=None):
        sid = sid or profile_id(url)
        if sid and sid in self.slush_company_ids:
            return self.slush_company_ids[sid]
        candidates = set(self.name_index.get(normalized_name(name), set()))
        doc_hosts = {document_host(d) for d in (docs or [])} - {None}
        corroborated = [x for x in candidates if host(self.nodes[x]["properties"].get("website")) in doc_hosts]
        if len(corroborated) == 1:
            ident = corroborated[0]
            self.identity_decisions.append({
                "source": "slush_text_organization",
                "source_id": context,
                "canonical_id": ident,
                "method": "exact_name_and_official_source_domain",
            })
            return ident
        ident = "slush-organization:" + stable_hash([sid or context, normalized_name(name)])
        self.node(ident, name or "Unresolved organization", "Company", "slush_reference", sid or context,
                  {"profile_link": url}, completeness="stub")
        if sid:
            self.slush_company_ids[sid] = ident
        if candidates:
            self.nodes[ident]["identity_match_candidates"] = sorted(candidates)
            self.unresolved_matches.append({
                "source_id": context,
                "name": name,
                "candidate_ids": sorted(candidates),
                "reason": "organization_mention_has_no_shared_identifier",
            })
        self.stats["scoped_organization_references"] += 1
        return ident

    def add_role_edges(self, person, company, role, properties, evidence_id, employment=False):
        self._add_node_evidence(person, evidence_id)
        self._add_node_evidence(company, evidence_id)
        predicates = role_predicates(role, "WORKS_AT" if employment else "AFFILIATED_WITH")
        for predicate in predicates:
            props = dict(properties)
            if predicate in ("WORKS_AT", "AFFILIATED_WITH", "ADVISES") and role:
                props["role"] = role
            self.edge(person, company, predicate, props, [evidence_id], "slush")

    def import_people(self):
        for i, raw in enumerate(self.people.get("people", [])):
            source_key = raw.get("record_key") or "people/" + str(i)
            ident = "slush-person:" + (raw.get("slush_person_id") or stable_hash(source_key))
            props = {k: raw.get(k) for k in (
                "job_title", "headline", "biography", "profile_url", "linkedin_url", "personal_website",
                "location_raw", "country_code_raw", "professional_topics", "tags", "education",
                "work_experience", "social_media", "identity_limitations", "source_type",
            )}
            docs = documents_from(raw.get("source_references"))
            if raw.get("profile_url"):
                docs += documents_from(raw["profile_url"])
            if raw.get("directory_memberships"):
                docs += documents_from(self.people.get("export_metadata", {}).get("source_directory_url"))
            evidence_id = self.ev("slush_people", "/people/" + str(i), raw, docs=unique(docs))
            self.node(ident, raw.get("name"), "Person", "slush", source_key, props,
                      evidence_id, "full", raw.get("aliases") or [])
            if raw.get("slush_person_id"):
                self.nodes[ident]["source_ids"]["slush_platform"] = [raw["slush_person_id"]]
                self.slush_platform_person_index[raw["slush_person_id"]] = ident
            if raw.get("possible_duplicate_record_keys"):
                self.nodes[ident]["possible_duplicate_record_keys"] = raw["possible_duplicate_record_keys"]
            self.people_keys[source_key] = ident
            if raw.get("directory_memberships") or raw.get("source_type") in ("directory_card", "full_profile", "profile_page"):
                self.participation(ident, "platform_directory", [evidence_id])
            for j, attendance in enumerate(raw.get("attendance_evidence") or []):
                aid = self.ev("slush_people", f"/people/{i}/attendance_evidence/{j}", attendance)
                if attendance.get("attendance_status"):
                    self.participation(ident, attendance["attendance_status"], [aid])

            affiliations = raw.get("affiliations") or []
            for j, aff in enumerate(affiliations):
                afdocs = documents_from(aff)
                for att in raw.get("attendance_evidence") or []:
                    if att.get("source_company_id") == aff.get("slush_company_id"):
                        afdocs += documents_from(att)
                afid = self.ev("slush_people", f"/people/{i}/affiliations/{j}", aff, docs=unique(afdocs))
                company = self.company_reference(
                    aff.get("company_name"), aff.get("slush_company_id"),
                    aff.get("company_profile_url"), afdocs, context=f"{source_key}/affiliations/{j}",
                )
                self.add_role_edges(ident, company, aff.get("role_as_supplied"), {}, afid)
            company = raw.get("company")
            if isinstance(company, dict) and not affiliations:
                docs = documents_from(company.get("company_profile_url"))
                cid = self.company_reference(
                    company.get("displayed_name"), company.get("slush_company_id"),
                    company.get("company_profile_url"), docs, context=source_key + "/company",
                )
                ceid = self.ev("slush_people", f"/people/{i}/company", company, docs=docs)
                self.add_role_edges(ident, cid, None, {}, ceid)

            for j, entry in enumerate((raw.get("work_experience") or {}).get("entries") or []):
                name = entry.get("organization")
                if not isinstance(name, str) or not name.strip():
                    self.stats["work_entries_without_organization"] += 1
                    continue
                docs = documents_from(entry)
                wid = self.ev("slush_people", f"/people/{i}/work_experience/entries/{j}", entry, docs=docs)
                cid = self.company_reference(name, docs=docs, context=f"{source_key}/work/{j}")
                properties = {k: entry[k] for k in (
                    "start_date", "end_date", "date_range_raw", "is_current", "date_semantics",
                    "organization_join_year", "organization_join_date", "documented_service_period",
                ) if k in entry and entry[k] is not None}
                self.add_role_edges(ident, cid, entry.get("role") or entry.get("title"), properties, wid, employment=True)
        self.stats["slush_people_primary_records"] = len(self.people.get("people", []))
        self.stats["slush_people_platform_ids"] = sum(bool(p.get("slush_person_id")) for p in self.people.get("people", []))

    def import_company_attendees(self):
        links = {}
        for link in self.people.get("imported_attendee_row_links", []):
            key = (link.get("input_company_index"), link.get("input_attendee_index"))
            if link.get("person_record_key") in self.people_keys:
                links[key] = link
        for i, company in enumerate(self.companies):
            sid = company.get("slush_company_id") or profile_id(company.get("profile_link"))
            company_id = self.slush_company_ids.get(sid)
            if company_id is None:
                continue
            for j, attendee in enumerate(company.get("slush_2026_attendees") or []):
                self.stats["slush_company_attendee_rows"] += 1
                link = links.get((i, j))
                person = None
                if (
                    link
                    and normalized_name(link.get("input_name")) == normalized_name(attendee.get("name"))
                    and normalized_name(link.get("input_company_name")) == normalized_name(company.get("company_name"))
                ):
                    person = self.people_keys[link["person_record_key"]]
                    self.stats["company_attendee_rows_linked_to_primary_people"] += 1
                if person is None:
                    attendee_sid = attendee.get("slush_person_id") or profile_id(attendee.get("slush_person_profile_url"), "people")
                    if attendee_sid and attendee_sid in self.slush_platform_person_index:
                        person = self.slush_platform_person_index[attendee_sid]
                    else:
                        person = "slush-person-attendee:" + stable_hash([sid, j, attendee.get("name")])
                        self.node(person, attendee.get("name"), "Person", "slush_company_attendee",
                                  f"{i}/{j}", {"job_title": attendee.get("role")}, completeness="stub")
                        self.stats["additional_company_attendee_candidates"] += 1
                aid = self.ev("slush_companies", f"/{i}/slush_2026_attendees/{j}", attendee)
                self._add_node_evidence(person, aid)
                if attendee.get("attendance_status"):
                    self.participation(person, attendee["attendance_status"], [aid])
                self.add_role_edges(person, company_id, attendee.get("role"), {}, aid)

    def merge_people_by_affiliation(self):
        slush_by_name, cala_by_name = defaultdict(set), defaultdict(set)
        affiliations = defaultdict(set)
        for e_obj in self.edges.values():
            if e_obj["type"] in AFFILIATION_TYPES and self.nodes[e_obj["source"]]["entity_type"] == "Person":
                affiliations[e_obj["source"]].add(e_obj["target"])
        for nid, n_obj in self.nodes.items():
            if n_obj["entity_type"] != "Person":
                continue
            index = cala_by_name if nid.startswith("cala:") else slush_by_name
            for name in [n_obj["name"], *n_obj["aliases"]]:
                index[normalized_name(name)].add(nid)
        replacements = {}
        for key, cala_people in cala_by_name.items():
            if len(cala_people) != 1:
                continue
            cala_person = next(iter(cala_people))
            candidates = [p for p in slush_by_name.get(key, set()) if affiliations[p] & affiliations[cala_person]]
            if len(candidates) == 1:
                target = candidates[0]
                replacements[cala_person] = target
                self.identity_decisions.append({
                    "source": "cala_person",
                    "source_id": cala_person,
                    "canonical_id": target,
                    "method": "unique_exact_name_and_resolved_company_affiliation",
                    "corroborating_company_ids": sorted(affiliations[target] & affiliations[cala_person]),
                })
        for source, target in replacements.items():
            old = self.nodes.pop(source)
            for provider, source_ids in old["source_ids"].items():
                for sid in source_ids:
                    self.node(
                        target, old["name"], old["entity_type"], provider, sid,
                        old["source_properties"].get(provider), completeness=old["record_completeness"], aliases=old["aliases"],
                    )
            for eid in old["evidence_ids"]:
                self._add_node_evidence(target, eid)
            self.nodes[target]["participation"] = unique(self.nodes[target]["participation"] + old["participation"])
            for sid, nid in list(self.cala_ids.items()):
                if nid == source:
                    self.cala_ids[sid] = target
        if replacements:
            old_edges = list(self.edges.values())
            self.edges = {}
            self._edge_ev_sets = defaultdict(set)
            for e_obj in old_edges:
                for origin in e_obj["origins"]:
                    self.edge(
                        replacements.get(e_obj["source"], e_obj["source"]),
                        replacements.get(e_obj["target"], e_obj["target"]),
                        e_obj["type"],
                        e_obj["properties"],
                        e_obj["evidence_ids"],
                        origin,
                    )

    def finish(self):
        for e_obj in self.edges.values():
            endpoints = [self.nodes[e_obj[k]] for k in ("source", "target")]
            if any(
                n["entity_type"] in GENERIC_NODE_TYPES
                or n.get("invalid_identity")
                or n.get("identity_status") == "unresolved"
                for n in endpoints
            ):
                e_obj["traversable"] = False
            if not e_obj["evidence_ids"]:
                e_obj["traversable"] = False
            e_obj["evidence_strength"] = "source_record"
            sources = [doc for eid in e_obj["evidence_ids"] for doc in self.evidence[eid]["source_documents"]]
            e_obj["support_status"] = "documented" if sources else "record_only"
            e_obj["source_support"] = "documented" if sources else "supplied_record"
            if e_obj["origins"] == ["cala"] and not sources:
                e_obj["traversable"] = False
                e_obj["support_status"] = "unattributed_provider_assertion"
                e_obj["source_support"] = "provider_only"
                self.warnings.append({
                    "kind": "cala_edge_without_document",
                    "edge_id": e_obj["id"],
                    "type": e_obj["type"],
                    "source": e_obj["source"],
                    "target": e_obj["target"],
                })
            if any(
                d.get("source_rank") in ("PRIMARY", "FILING")
                or str(d.get("source_type") or "").startswith("official_")
                or d.get("access_status") == "opened_primary"
                for d in sources
            ):
                e_obj["evidence_strength"] = "documented_primary"

        datasets = []
        for ds_id, path in self.dataset_entries:
            p = Path(path)
            raw_bytes = p.read_bytes()
            datasets.append({
                "id": ds_id,
                "filename": p.name,
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "size_bytes": len(raw_bytes),
            })

        graph_version = stable_hash([IMPORTER_VERSION, datasets], 64)
        counts = dict(self.stats)
        counts.update({
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "evidence_records": len(self.evidence),
            "traversable_edges": sum(e["traversable"] for e in self.edges.values()),
            "node_types": dict(Counter(n["entity_type"] for n in self.nodes.values())),
            "edge_types": dict(Counter(e["type"] for e in self.edges.values())),
            "cross_source_company_merges": sum(x["source"] == "cala" for x in self.identity_decisions),
            "cross_source_person_merges": sum(x["source"] == "cala_person" for x in self.identity_decisions),
            "unresolved_identity_candidates": len(self.unresolved_matches),
            "slush_supported_edges": sum("slush" in e["origins"] for e in self.edges.values()),
            "cala_supported_edges": sum("cala" in e["origins"] for e in self.edges.values()),
            "both_source_edges": sum(set(e["origins"]) == {"slush", "cala"} for e in self.edges.values()),
        })
        limitations = [
            f"Cala export completeness is {self.cala_coverage_meta.get('complete')}; {counts['cala_full_entity_records']} hydrated entity dossiers ({counts['cala_full_company_records']} companies) and {counts['cala_input_edges']} relationship rows were imported.",
            "The people file is partial; directory evidence and announcements do not independently establish physical event attendance.",
            "Missing fields, paths, attendees or relationships mean not established in these snapshots, not absence in the real world.",
            "Cross-source name-only matches remain unresolved candidates; this intentionally reduces recall to avoid invented identity joins.",
            "Organization names in work history without corroborating identifiers remain scoped references and do not create shared-employer bridges by name alone.",
            "Employment and role records with null end dates are not automatically current.",
            "Possible duplicate people flagged in the source dataset are preserved separately.",
            "Source-provided entity types, unusual dates and conflicting profile wording are retained rather than silently corrected.",
            "Cala relationships without a nonempty primary source URL remain audit assertions and are excluded from traversable networking paths.",
        ]
        manifest = {
            "importer_version": IMPORTER_VERSION,
            "datasets": datasets,
            "counts": counts,
            "cala_coverage": self.cala_coverage_meta,
            "people_coverage": {
                k: self.people.get("export_metadata", {}).get(k)
                for k in ("collection_status", "platform_person_records", "all_event_attendees_exported", "directory_exhaustion_verified")
            },
            "identity_policy": "Source IDs first; company name/alias plus matching domain; person exact name plus resolved company affiliation. Name-only candidates are retained without merging.",
            "identity_decisions": self.identity_decisions,
            "unresolved_matches": self.unresolved_matches,
            "possible_duplicate_people": self.people.get("possible_duplicate_people", []),
            "warnings": self.warnings,
            "limitations": limitations,
        }
        return {
            "schema_version": "2.0",
            "graph_version": graph_version,
            "nodes": self.nodes,
            "edges": list(self.edges.values()),
            "evidence": self.evidence,
            "manifest": manifest,
        }


def build_snapshot(people_path, cala_path, companies_path):
    """Read Slush people/companies + Cala Slush 2026 spreadsheets (or legacy JSON) and return a normalized snapshot."""
    p_people = Path(people_path)
    p_cala = Path(cala_path)
    p_companies = Path(companies_path)

    people = json.loads(p_people.read_text(encoding="utf-8"))
    companies = json.loads(p_companies.read_text(encoding="utf-8"))
    if not isinstance(people, dict) or not isinstance(people.get("people"), list):
        raise ValueError("People file must contain a 'people' array.")
    if not isinstance(companies, list):
        raise ValueError("Companies file must be a JSON array.")

    dataset_entries: list[tuple[str, Path]] = [("slush_people", p_people)]
    if p_cala.is_dir() or (p_cala.is_file() and p_cala.suffix.lower() == ".zip"):
        cala_tables, cala_files = _load_cala_spreadsheets(p_cala)
        dataset_entries.extend(cala_files)  # type: ignore[arg-type]
        cala_mode = "spreadsheets"
        cala_payload = cala_tables
    else:
        cala_json = json.loads(p_cala.read_text(encoding="utf-8"))
        if not isinstance(cala_json, dict) or not isinstance(cala_json.get("edges"), list):
            raise ValueError("Cala JSON file must contain an 'edges' array.")
        dataset_entries.append(("cala", p_cala))
        cala_mode = "legacy_json"
        cala_payload = cala_json
    dataset_entries.append(("slush_companies", p_companies))

    b = Builder(people, cala_payload, companies, dataset_entries, cala_mode=cala_mode)
    b.import_companies()
    if cala_mode == "spreadsheets":
        b.import_cala_spreadsheets()
    else:
        b.import_cala_legacy_json()
    b.import_people()
    b.import_company_attendees()
    b.merge_people_by_affiliation()
    result = b.finish()
    assert all(e["source"] in result["nodes"] and e["target"] in result["nodes"] for e in result["edges"])
    assert all(all(k in result["evidence"] for k in e["evidence_ids"]) for e in result["edges"])
    return result


def resolve_default_cala_path(base_dir: Path) -> Path:
    spreadsheets_dir = base_dir / "slush_2026_spreadsheets"
    if spreadsheets_dir.is_dir():
        return spreadsheets_dir
    spreadsheets_zip = base_dir / "slush_2026_spreadsheets.zip"
    if spreadsheets_zip.is_file():
        return spreadsheets_zip
    return base_dir / "cala_graph.json"


def ensure_snapshot(snapshot_path: Path | str | None = None, data_dir: Path | str | None = None) -> dict:
    """Load snapshot.json, or deterministically build it on fresh clones / CI."""
    base_dir = Path(data_dir) if data_dir else (Path(__file__).resolve().parent / "data")
    snap_file = Path(snapshot_path) if snapshot_path else (base_dir / "snapshot.json")
    if snap_file.is_file():
        return json.loads(snap_file.read_text(encoding="utf-8"))

    people_path = base_dir / "slush_people.json"
    cala_path = resolve_default_cala_path(base_dir)
    companies_path = base_dir / "slush_companies.json"
    missing = [str(p) for p in (people_path, companies_path) if not p.is_file()]
    if not cala_path.exists():
        missing.append(str(cala_path))
    if missing:
        raise FileNotFoundError(
            f"Snapshot not found at {snap_file} and raw source datasets missing: {', '.join(missing)}"
        )

    snapshot = build_snapshot(people_path, cala_path, companies_path)
    snap_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = snap_file.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp_file.replace(snap_file)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", required=True)
    parser.add_argument("--cala", required=True)
    parser.add_argument("--companies", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = build_snapshot(args.people, args.cala, args.companies)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "graph_version": snapshot["graph_version"],
                      "counts": snapshot["manifest"]["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
