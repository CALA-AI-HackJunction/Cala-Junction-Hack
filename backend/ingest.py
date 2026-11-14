"""Conservative, offline import of the three supplied Cala / Slush JSON files.

The importer records evidence rather than treating descriptions as relationship
instructions.  It uses only Python's standard library and performs no network IO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit


IMPORTER_VERSION = "2.0.2"
EVENT_SOURCE_ID = "bc844d56-6ab4-452b-96bf-2661e86e592b"
PROFESSIONAL_TYPES = {
    "WORKS_AT", "FOUNDED", "INVESTED_IN", "IS_BOARD_MEMBER_OF",
    "IS_CEO_OF", "IS_CTO_OF", "IS_CFO_OF", "IS_COO_OF", "IS_CSO_OF",
    "IS_CMO_OF", "IS_CCO_OF", "IS_VICEPRESIDENT_OF", "IS_MANAGING_DIRECTOR_OF",
    "IS_BENEFICIARY_OWNER_OF", "IS_CONTROL_PERSON_OF", "AFFILIATED_WITH", "ADVISES",
    "PARTICIPATES_IN_FUNDING_ROUND", "PARTICIPATES_IN_CORPORATE_EVENT",
}
AFFILIATION_TYPES = PROFESSIONAL_TYPES - {
    "INVESTED_IN", "PARTICIPATES_IN_FUNDING_ROUND", "PARTICIPATES_IN_CORPORATE_EVENT",
}
GENERIC_NODE_TYPES = {
    "Event", "Industry", "DomainName", "Country", "CountrySubdivision", "City",
    "Place", "Location", "Group",
}
ARRAY_FIELDS = {
    "secondary_industry", "focus_industries", "business_types", "software_hardware",
    "round_role", "lp_class", "lp_fund_stage", "focus_startup_stage",
    "investment_into_vc_as_a_lp", "curated_collections_tags",
}


def stable_hash(value, size=24):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()[:size]


def normalized_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def company_name_key(value):
    value = normalized_name(value)
    # Legal endings are used with an independently matching domain, never alone.
    return re.sub(r"(?:\s+(?:oy|ab|gmbh|ltd|limited|inc|llc|sa|ag|ug|bv|bvba|plc|flexco))+$", "", value)


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
    seen, result = set(), []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


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
    # No end date, a recent capture, or a valid_since is not proof of currentness.
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
        # A role in an explicit employment section warrants WORKS_AT, but an
        # affiliation-only record can also describe an investor or delegate.
        predicates.append(default)
    return predicates


class Builder:
    def __init__(self, people, cala, companies, paths):
        self.people, self.cala, self.companies = people, cala, companies
        self.paths = paths
        self.nodes, self.edges, self.evidence = {}, {}, {}
        self.slush_company_ids, self.cala_ids, self.people_keys = {}, {}, {}
        self.name_index, self.domain_index = defaultdict(set), defaultdict(set)
        self.identity_decisions, self.unresolved_matches, self.warnings = [], [], []
        self.stats = Counter()
        self.company_attendee_links = {}

    def ev(self, dataset, pointer, record, docs=None, **extra):
        ident = "ev:" + stable_hash([dataset, pointer, record])
        if ident not in self.evidence:
            self.evidence[ident] = {
                "id": ident, "dataset": dataset, "record_pointer": pointer,
                "source_documents": documents_from(record) if docs is None else unique(docs),
                "record": record, **extra,
            }
        return ident

    def node(self, ident, name, entity_type, provider, source_id, properties=None,
             evidence_id=None, completeness="stub", aliases=None):
        if ident not in self.nodes:
            self.nodes[ident] = {
                "id": ident, "name": name or ident, "entity_type": entity_type or "Unknown",
                "aliases": [], "source_ids": {}, "properties": {}, "source_properties": {},
                "participation": [], "evidence_ids": [], "record_completeness": completeness,
                "identity_status": "supported",
            }
        n = self.nodes[ident]
        if name and name != n["name"]:
            n["aliases"] = unique(n["aliases"] + [name])
        n["aliases"] = unique(n["aliases"] + [x for x in (aliases or []) if x])
        if source_id is not None:
            n["source_ids"][provider] = unique(n["source_ids"].get(provider, []) + [source_id])
        if properties:
            n["source_properties"].setdefault(provider, {}).update(properties)
            for key, value in properties.items():
                if key not in n["properties"] or n["properties"][key] is None:
                    n["properties"][key] = value
                elif value is not None and n["properties"][key] != value:
                    n.setdefault("property_alternatives", {}).setdefault(key, [])
                    n["property_alternatives"][key] = unique(n["property_alternatives"][key] + [
                        {"source": provider, "value": value, "evidence_id": evidence_id}])
        if evidence_id:
            n["evidence_ids"] = unique(n["evidence_ids"] + [evidence_id])
        if completeness == "full":
            n["record_completeness"] = "full"
        return ident

    def participation(self, ident, status, evidence_ids, event_id=None):
        claim = {"status": status, "event_id": event_id or "cala:" + EVENT_SOURCE_ID,
                 "evidence_ids": list(evidence_ids)}
        for existing in self.nodes[ident]["participation"]:
            if existing["status"] == claim["status"] and existing["event_id"] == claim["event_id"]:
                existing["evidence_ids"] = unique(existing["evidence_ids"] + claim["evidence_ids"])
                return
        self.nodes[ident]["participation"].append(claim)

    def edge(self, source, target, predicate, props, evidence_ids, origin):
        # Preserve qualifiers in the assertion key, while deduplicating copied
        # records and equivalent inbound/outbound appearances of the same fact.
        props = {k: v for k, v in (props or {}).items() if k not in ("id", "sources")}
        ident = "edge:" + stable_hash([source, predicate, target, props])
        if ident not in self.edges:
            self.edges[ident] = {
                "id": ident, "source": source, "target": target, "type": predicate,
                "properties": props, "evidence_ids": [], "origins": [],
                "traversable": predicate in PROFESSIONAL_TYPES, "hop_cost": 1,
                "temporal_status": temporal_status(props), "derived": False,
            }
        edge = self.edges[ident]
        edge["evidence_ids"] = unique(edge["evidence_ids"] + list(evidence_ids))
        edge["origins"] = unique(edge["origins"] + [origin])
        return ident

    def index_company(self, ident):
        n = self.nodes[ident]
        if n["entity_type"] not in ("Company", "Organization"):
            return
        for name in [n["name"], *n["aliases"]]:
            self.name_index[normalized_name(name)].add(ident)
        website = n["properties"].get("website")
        if host(website):
            self.domain_index[host(website)].add(ident)

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
            eid = self.ev("slush_companies", "/" + str(i), props,
                          docs=documents_from(raw.get("profile_link")))
            self.node(ident, raw.get("company_name"), "Company", "slush", sid or str(i),
                      props, eid, "full")
            self.participation(ident, "company_listed", [eid])
            if sid:
                self.slush_company_ids[sid] = ident
            self.index_company(ident)
        self.stats["slush_company_records"] = len(self.companies)

    def import_cala_nodes(self):
        full = {entry["record"]["id"]: (i, entry["record"]) for i, entry in enumerate(self.cala.get("entities", []))}
        records = {}
        for edge in self.cala.get("edges", []):
            for rec in edge.get("records", []):
                if rec.get("id"):
                    records.setdefault(rec["id"], rec)
        for sid, (_, rec) in full.items():
            records[sid] = rec
        for sid, rec in records.items():
            kind = rec.get("entity_type") or "Unknown"
            aliases, props, evidence_id = [], {}, None
            if sid in full:
                i, _ = full[sid]
                props = {k: v.get("value") if isinstance(v, dict) and "value" in v else v
                         for k, v in rec.get("properties", {}).items()}
                props.setdefault("description", rec.get("description"))
                aliases = props.get("aliases") if isinstance(props.get("aliases"), list) else []
                evidence_id = self.ev("cala", "/entities/" + str(i) + "/record",
                                      {k: v for k, v in rec.items() if k != "relationships"},
                                      docs=[d for v in rec.get("properties", {}).values()
                                            for d in documents_from(v)])
            ident = None
            if kind == "Company" and sid in full:
                names = [rec.get("name"), *aliases]
                domain_candidates = set(self.domain_index.get(host(props.get("website")), set()))
                name_keys = {company_name_key(x) for x in names if x}
                candidates = [x for x in domain_candidates
                              if name_keys & {company_name_key(n) for n in [self.nodes[x]["name"], *self.nodes[x]["aliases"]]}]
                if len(candidates) == 1:
                    ident = candidates[0]
                    self.identity_decisions.append({"source": "cala", "source_id": sid, "canonical_id": ident,
                                                    "method": "unique_matching_domain_and_name_or_alias"})
            if ident is None:
                ident = "cala:" + sid
                if kind in ("Company", "Organization"):
                    candidates = sorted(self.name_index.get(normalized_name(rec.get("name")), set()))
                    if candidates:
                        self.unresolved_matches.append({"source_id": sid, "name": rec.get("name"),
                                                        "candidate_ids": candidates,
                                                        "reason": "name_only_without_independent_identity_corroboration"})
            self.node(ident, rec.get("name"), kind, "cala", sid, props, evidence_id,
                      "full" if sid in full else "stub", aliases)
            self.cala_ids[sid] = ident
            name = str(rec.get("name") or "").casefold()
            if "including renowned industry leaders" in name:
                self.nodes[ident]["identity_status"] = "invalid"
                self.nodes[ident]["invalid_identity"] = True
                self.nodes[ident]["identity_warnings"] = ["Source uses a collective phrase rather than an identifiable entity."]
                self.warnings.append({"kind": "vague_source_entity", "id": ident, "name": rec.get("name")})
            if kind in ("Company", "Organization"):
                self.index_company(ident)
        # Preserve dangling endpoints if an export lacks even a named stub.
        for raw in self.cala.get("edges", []):
            for sid in (raw.get("source"), raw.get("target")):
                if sid and sid not in self.cala_ids:
                    ident = "cala:" + sid
                    self.node(ident, sid, "Unknown", "cala", sid)
                    self.nodes[ident]["identity_status"] = "unresolved"
                    self.cala_ids[sid] = ident
        self.stats["cala_full_entity_records"] = len(full)
        self.stats["cala_full_company_records"] = sum(r.get("entity_type") == "Company" for _, r in full.values())
        self.stats["cala_endpoint_entities"] = len(self.cala_ids)

    def import_cala_edges(self):
        for i, raw in enumerate(self.cala.get("edges", [])):
            source, target = self.cala_ids[raw["source"]], self.cala_ids[raw["target"]]
            records = raw.get("records") or []
            docs = unique([d for r in records for d in documents_from(r.get("properties"))])
            eid = self.ev("cala", "/edges/" + str(i), raw, docs=docs)
            # Stub properties on edge records are RELATIONSHIP qualifiers.
            # They must never be mistaken for an entity's own profile fields.
            qualifier_sets = unique([{k: v for k, v in r.get("properties", {}).items()
                                      if k not in ("id", "sources")} for r in records]) or [{}]
            for props in qualifier_sets:
                self.edge(source, target, raw["type"], props, [eid], "cala")
            for nid in (source, target):
                self.nodes[nid]["evidence_ids"] = unique(self.nodes[nid]["evidence_ids"] + [eid])
            if raw["type"] == "PARTICIPATES_IN_EVENT" and raw["target"] == self.cala.get("seed", {}).get("id", EVENT_SOURCE_ID):
                self.participation(source, "cala_event_link", [eid], target)
        self.stats["cala_input_edges"] = len(self.cala.get("edges", []))

    def company_reference(self, name, sid=None, url=None, docs=None, context=None):
        sid = sid or profile_id(url)
        if sid and sid in self.slush_company_ids:
            return self.slush_company_ids[sid]
        candidates = set(self.name_index.get(normalized_name(name), set()))
        doc_hosts = {document_host(d) for d in (docs or [])} - {None}
        corroborated = [x for x in candidates if host(self.nodes[x]["properties"].get("website")) in doc_hosts]
        if len(corroborated) == 1:
            ident = corroborated[0]
            self.identity_decisions.append({"source": "slush_text_organization", "source_id": context,
                                            "canonical_id": ident, "method": "exact_name_and_official_source_domain"})
            return ident
        # An uncorroborated name is a scoped reference, not a fabricated identity
        # merge. The original affiliation is retained, and candidate matches are
        # exposed for a future identity-resolution action.
        ident = "slush-organization:" + stable_hash([sid or context, normalized_name(name)])
        self.node(ident, name or "Unresolved organization", "Company", "slush_reference", sid or context,
                  {"profile_link": url}, completeness="stub")
        if sid:
            self.slush_company_ids[sid] = ident
        if candidates:
            self.nodes[ident]["identity_match_candidates"] = sorted(candidates)
            self.unresolved_matches.append({"source_id": context, "name": name,
                                            "candidate_ids": sorted(candidates),
                                            "reason": "organization_mention_has_no_shared_identifier"})
        self.stats["scoped_organization_references"] += 1
        return ident

    def add_role_edges(self, person, company, role, properties, evidence_id, employment=False):
        for ident in (person, company):
            self.nodes[ident]["evidence_ids"] = unique(self.nodes[ident]["evidence_ids"] + [evidence_id])
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
                # Detailed attendance sources support this exact nested affiliation.
                for att in raw.get("attendance_evidence") or []:
                    if att.get("source_company_id") == aff.get("slush_company_id"):
                        afdocs += documents_from(att)
                afid = self.ev("slush_people", f"/people/{i}/affiliations/{j}", aff, docs=unique(afdocs))
                company = self.company_reference(aff.get("company_name"), aff.get("slush_company_id"),
                                                 aff.get("company_profile_url"), afdocs,
                                                 context=f"{source_key}/affiliations/{j}")
                self.add_role_edges(ident, company, aff.get("role_as_supplied"), {}, afid)
            company = raw.get("company")
            if isinstance(company, dict) and not affiliations:
                docs = documents_from(company.get("company_profile_url"))
                cid = self.company_reference(company.get("displayed_name"), company.get("slush_company_id"),
                                             company.get("company_profile_url"), docs,
                                             context=source_key + "/company")
                ceid = self.ev("slush_people", f"/people/{i}/company", company, docs=docs)
                # The company field supports affiliation; a global title may have
                # another provenance and is not silently attributed to it.
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
        # Explicit row links in the supplied people file connect enrichment
        # evidence to primary people; these are not new people records.
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
                if link and normalized_name(link.get("input_name")) == normalized_name(attendee.get("name")) and normalized_name(link.get("input_company_name")) == normalized_name(company.get("company_name")):
                    person = self.people_keys[link["person_record_key"]]
                    self.stats["company_attendee_rows_linked_to_primary_people"] += 1
                if person is None:
                    # A verified profile id is useful if row mapping is absent.
                    attendee_sid = attendee.get("slush_person_id") or profile_id(attendee.get("slush_person_profile_url"), "people")
                    matching = [nid for nid, n in self.nodes.items() if attendee_sid and attendee_sid in n["source_ids"].get("slush_platform", [])]
                    if len(matching) == 1:
                        person = matching[0]
                    else:
                        person = "slush-person-attendee:" + stable_hash([sid, j, attendee.get("name")])
                        self.node(person, attendee.get("name"), "Person", "slush_company_attendee",
                                  f"{i}/{j}", {"job_title": attendee.get("role")}, completeness="stub")
                        self.stats["additional_company_attendee_candidates"] += 1
                aid = self.ev("slush_companies", f"/{i}/slush_2026_attendees/{j}", attendee)
                self.nodes[person]["evidence_ids"] = unique(self.nodes[person]["evidence_ids"] + [aid])
                if attendee.get("attendance_status"):
                    self.participation(person, attendee["attendance_status"], [aid])
                self.add_role_edges(person, company_id, attendee.get("role"), {}, aid)

    def merge_people_by_affiliation(self):
        slush_by_name, cala_by_name = defaultdict(set), defaultdict(set)
        affiliations = defaultdict(set)
        for edge in self.edges.values():
            if edge["type"] in AFFILIATION_TYPES and self.nodes[edge["source"]]["entity_type"] == "Person":
                affiliations[edge["source"]].add(edge["target"])
        for nid, node in self.nodes.items():
            if node["entity_type"] != "Person":
                continue
            index = cala_by_name if nid.startswith("cala:") else slush_by_name
            for name in [node["name"], *node["aliases"]]:
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
                self.identity_decisions.append({"source": "cala_person", "source_id": cala_person,
                                                "canonical_id": target, "method": "unique_exact_name_and_resolved_company_affiliation",
                                                "corroborating_company_ids": sorted(affiliations[target] & affiliations[cala_person])})
        for source, target in replacements.items():
            old = self.nodes.pop(source)
            for provider, source_ids in old["source_ids"].items():
                for sid in source_ids:
                    self.node(target, old["name"], old["entity_type"], provider, sid,
                              old["source_properties"].get(provider), completeness=old["record_completeness"], aliases=old["aliases"])
            self.nodes[target]["evidence_ids"] = unique(self.nodes[target]["evidence_ids"] + old["evidence_ids"])
            self.nodes[target]["participation"] = unique(self.nodes[target]["participation"] + old["participation"])
            for sid, nid in list(self.cala_ids.items()):
                if nid == source:
                    self.cala_ids[sid] = target
        if replacements:
            old_edges, self.edges = list(self.edges.values()), {}
            for edge in old_edges:
                for origin in edge["origins"]:
                    self.edge(replacements.get(edge["source"], edge["source"]),
                              replacements.get(edge["target"], edge["target"]), edge["type"],
                              edge["properties"], edge["evidence_ids"], origin)

    def finish(self):
        for edge in self.edges.values():
            endpoints = [self.nodes[edge[k]] for k in ("source", "target")]
            if any(n["entity_type"] in GENERIC_NODE_TYPES or n.get("invalid_identity") or n.get("identity_status") == "unresolved" for n in endpoints):
                edge["traversable"] = False
            if not edge["evidence_ids"]:
                edge["traversable"] = False
            edge["evidence_strength"] = "source_record"
            sources = [doc for eid in edge["evidence_ids"] for doc in self.evidence[eid]["source_documents"]]
            edge["support_status"] = "documented" if sources else "record_only"
            edge["source_support"] = "documented" if sources else "supplied_record"
            if edge["origins"] == ["cala"] and not sources:
                # Preserve the provider claim for audit, but do not use an
                # unattributed assertion as a professional networking bridge.
                edge["traversable"] = False
                edge["support_status"] = "unattributed_provider_assertion"
                edge["source_support"] = "provider_only"
                self.warnings.append({"kind": "cala_edge_without_document", "edge_id": edge["id"],
                                      "type": edge["type"], "source": edge["source"], "target": edge["target"]})
            if any(d.get("source_rank") in ("PRIMARY", "FILING") or d.get("source_type", "").startswith("official_") or d.get("access_status") == "opened_primary" for d in sources):
                edge["evidence_strength"] = "documented_primary"
        datasets = []
        for name, path in self.paths.items():
            p = Path(path)
            datasets.append({"id": name, "filename": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size_bytes": p.stat().st_size})
        graph_version = stable_hash([IMPORTER_VERSION, datasets], 64)
        counts = dict(self.stats)
        counts.update({
            "nodes": len(self.nodes), "edges": len(self.edges), "evidence_records": len(self.evidence),
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
            f"Cala export completeness is {self.cala.get('complete')}; {counts['cala_full_entity_records']} full entity records ({counts['cala_full_company_records']} companies) were captured. Other edge endpoints can be stubs.",
            "The people file is partial; directory evidence and announcements do not independently establish physical event attendance.",
            "Missing fields, paths, attendees or relationships mean not established in these snapshots, not absence in the real world.",
            "Cross-source name-only matches remain unresolved candidates; this intentionally reduces recall to avoid invented identity joins.",
            "Organization names in work history without corroborating identifiers remain scoped references and do not create shared-employer bridges by name alone.",
            "Employment and role records with null end dates are not automatically current.",
            "Possible duplicate people flagged in the source dataset are preserved separately.",
            "Source-provided entity types, unusual dates and conflicting profile wording are retained rather than silently corrected.",
            "Cala relationships without a nonempty source document remain audit assertions and are excluded from traversable networking paths.",
        ]
        manifest = {
            "importer_version": IMPORTER_VERSION, "datasets": datasets, "counts": counts,
            "cala_coverage": {k: self.cala.get(k) for k in ("complete", "reason", "maximum_hops", "retrieved_by_hop")},
            "people_coverage": {k: self.people.get("export_metadata", {}).get(k) for k in (
                "collection_status", "platform_person_records", "all_event_attendees_exported", "directory_exhaustion_verified")},
            "identity_policy": "Source IDs first; company name/alias plus matching domain; person exact name plus resolved company affiliation. Name-only candidates are retained without merging.",
            "identity_decisions": self.identity_decisions, "unresolved_matches": self.unresolved_matches,
            "possible_duplicate_people": self.people.get("possible_duplicate_people", []),
            "warnings": self.warnings, "limitations": limitations,
        }
        return {"schema_version": "2.0", "graph_version": graph_version,
                "nodes": self.nodes, "edges": list(self.edges.values()),
                "evidence": self.evidence, "manifest": manifest}


def build_snapshot(people_path, cala_path, companies_path):
    """Read the three original files and return a normalized, sourced snapshot."""
    paths = {"slush_people": str(people_path), "cala": str(cala_path), "slush_companies": str(companies_path)}
    people, cala, companies = [json.loads(Path(p).read_text(encoding="utf-8"))
                               for p in (people_path, cala_path, companies_path)]
    if not isinstance(people, dict) or not isinstance(people.get("people"), list):
        raise ValueError("People file must contain a 'people' array.")
    if not isinstance(cala, dict) or not isinstance(cala.get("edges"), list):
        raise ValueError("Cala file must contain an 'edges' array.")
    if not isinstance(companies, list):
        raise ValueError("Companies file must be a JSON array.")
    b = Builder(people, cala, companies, paths)
    b.import_companies()
    b.import_cala_nodes()
    b.import_cala_edges()
    b.import_people()
    b.import_company_attendees()
    b.merge_people_by_affiliation()
    result = b.finish()
    assert all(e["source"] in result["nodes"] and e["target"] in result["nodes"] for e in result["edges"])
    assert all(all(k in result["evidence"] for k in e["evidence_ids"]) for e in result["edges"])
    return result


def ensure_snapshot(snapshot_path: Path | str | None = None, data_dir: Path | str | None = None) -> dict:
    """Load snapshot.json, or deterministically build it on fresh clones / CI."""
    base_dir = Path(data_dir) if data_dir else (Path(__file__).resolve().parent / "data")
    snap_file = Path(snapshot_path) if snapshot_path else (base_dir / "snapshot.json")
    if snap_file.is_file():
        return json.loads(snap_file.read_text(encoding="utf-8"))

    people_path = base_dir / "slush_people.json"
    cala_path = base_dir / "cala_graph.json"
    companies_path = base_dir / "slush_companies.json"
    missing = [str(p) for p in (people_path, cala_path, companies_path) if not p.is_file()]
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
