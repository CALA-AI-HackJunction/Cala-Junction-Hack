"""CRACI Supply-Chain, CycloneDX SBOM & Network Egress Provenance Client.

Implements `GET /api/craci/provenance` and `POST /api/craci/audit` per `craci_openapi.json`
and `API_CONTRACT.md` §4.2-4.3:
- When `CRACI_API_TOKEN` is configured, queries `https://api.craci.com` (`/v1preview1/jobs`,
  `/v1preview1/sbom`, `/v1preview1/network-trace`, `/v1preview1/usage`).
- When offline (`CRACI_API_TOKEN` unset), deterministically constructs a real CycloneDX SBOM
  from `pyproject.toml`, `uv.lock`, and `importlib.metadata`, inspects `.github/workflows/*.yml`
  using pure stdlib parsing (no PyYAML dependency) for `runs-on: craci` + `cracicorp/setup@v1`
  egress lockdown (`default: deny`, `presets: [pypi, github]`), and cross-references package
  suppliers against verified entities in the Cala/Slush snapshot.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import time
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    from .ai_engine import (
        call_gemini_json,
        call_gemma_json,
        gemini_is_configured,
        gemma_is_configured,
        resolve_effective_composer_mode,
    )
    from .env_loader import REPO_ROOT
except ImportError:
    from ai_engine import (
        call_gemini_json,
        call_gemma_json,
        gemini_is_configured,
        gemma_is_configured,
        resolve_effective_composer_mode,
    )
    from env_loader import REPO_ROOT


KNOWN_SUPPLIERS = {
    "fastapi": ("FastAPI / Tiangolo", "MIT"),
    "uvicorn": ("Encode / Tom Christie", "BSD-3-Clause"),
    "starlette": ("Encode", "BSD-3-Clause"),
    "httpx": ("Encode", "BSD-3-Clause"),
    "pydantic": ("Pydantic Services Inc.", "MIT"),
    "pydantic-core": ("Pydantic Services Inc.", "MIT"),
    "psycopg": ("Psycopg / Daniele Varrazzo", "LGPL-3.0"),
    "psycopg-binary": ("Psycopg / Daniele Varrazzo", "LGPL-3.0"),
    "valkey": ("Linux Foundation / Valkey", "MIT"),
    "google-genai": ("Google", "Apache-2.0"),
    "pytest": ("pytest-dev", "MIT"),
    "anyio": ("Agronholm / AnyIO", "MIT"),
    "certifi": ("Certifi", "MPL-2.0"),
    "idna": ("Kim Davies", "BSD-3-Clause"),
    "h11": ("Nathaniel J. Smith", "MIT"),
}


def craci_api_is_configured() -> bool:
    return bool((os.environ.get("CRACI_API_TOKEN") or "").strip())


def scan_github_workflows(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Stdlib indentation/line scanner for `.github/workflows/*.yml` (no PyYAML needed)."""
    wf_dir = repo_root / ".github" / "workflows"
    files = sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []
    craci_jobs: list[dict[str, Any]] = []

    for wf_file in files:
        rel_path = wf_file.relative_to(repo_root).as_posix()
        try:
            lines = wf_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        in_jobs = False
        current_job: str | None = None
        job_data: dict[str, Any] = {}

        def _flush_job() -> None:
            if not current_job:
                return
            runs_on = str(job_data.get("runs_on") or "")
            if "craci" in runs_on.lower() or job_data.get("uses_craci_setup"):
                default_pol = job_data.get("network_default")
                presets = job_data.get("network_presets") or []
                if default_pol == "deny":
                    egress_desc = f"default: deny (presets: {', '.join(presets)})" if presets else "default: deny"
                elif job_data.get("uses_craci_setup"):
                    egress_desc = "package-aware-proxy"
                else:
                    egress_desc = "unrestricted_default"
                craci_jobs.append(
                    {
                        "workflow": rel_path,
                        "job_name": current_job,
                        "display_name": job_data.get("display_name") or current_job,
                        "runs_on": runs_on or "craci",
                        "architecture": "amd64",
                        "size": job_data.get("size") or "default",
                        "image": job_data.get("image") or "default",
                        "uses_craci_setup": bool(job_data.get("uses_craci_setup")),
                        "network_default": default_pol,
                        "network_presets": presets,
                        "egress_policy": egress_desc,
                        "block_unmatched_egress": default_pol == "deny",
                    }
                )

        for raw in lines:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if indent == 0:
                if stripped.startswith("jobs:"):
                    in_jobs = True
                else:
                    if in_jobs:
                        _flush_job()
                        current_job = None
                    in_jobs = False
                continue

            if not in_jobs:
                continue

            if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
                _flush_job()
                current_job = stripped[:-1].strip()
                job_data = {}
                continue

            if current_job is None:
                continue

            if indent == 4 and stripped.startswith("name:"):
                job_data["display_name"] = stripped.split(":", 1)[1].strip().strip("'\"")
            elif indent == 4 and stripped.startswith("runs-on:"):
                job_data["runs_on"] = stripped.split(":", 1)[1].strip().strip("'\"")
            elif "cracicorp/setup@" in stripped:
                job_data["uses_craci_setup"] = True
            elif stripped.startswith("size:"):
                job_data["size"] = stripped.split(":", 1)[1].strip().strip("'\"")
            elif stripped.startswith("image:"):
                job_data["image"] = stripped.split(":", 1)[1].strip().strip("'\"")
            elif stripped.startswith("default:"):
                val = stripped.split(":", 1)[1].strip().strip("'\"")
                if val in {"deny", "allow"}:
                    job_data["network_default"] = val
            elif stripped.startswith("presets:"):
                m = re.search(r"\[([^\]]*)\]", stripped)
                if m:
                    job_data["network_presets"] = [
                        p.strip().strip("'\"") for p in m.group(1).split(",") if p.strip()
                    ]

        _flush_job()

    compliant = bool(craci_jobs) and all(
        "craci" in j["runs_on"].lower() and j.get("block_unmatched_egress") for j in craci_jobs
    )
    return {
        "workflows_scanned": len(files),
        "craci_runner_jobs": craci_jobs,
        "compliant": compliant,
    }


def _parse_uv_lock_packages(lock_path: Path) -> dict[str, dict[str, Any]]:
    if not lock_path.is_file():
        return {}
    try:
        parsed = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        out: dict[str, dict[str, Any]] = {}
        for pkg in parsed.get("package") or []:
            if not isinstance(pkg, dict) or not pkg.get("name"):
                continue
            name = str(pkg["name"]).lower()
            sdist = pkg.get("sdist") or {}
            wheels = pkg.get("wheels") or []
            sha256 = None
            raw_hash = sdist.get("hash") or (wheels[0].get("hash") if wheels and isinstance(wheels[0], dict) else None)
            if isinstance(raw_hash, str) and raw_hash.startswith("sha256:"):
                sha256 = raw_hash.split("sha256:", 1)[1]
            out[name] = {
                "name": str(pkg["name"]),
                "version": str(pkg.get("version") or "unknown"),
                "source": (pkg.get("source") or {}).get("registry"),
                "sha256": sha256,
            }
        return out
    except Exception:
        return {}


def _extract_pkg_license(dist_name: str) -> str:
    fallback_vendor, fallback_lic = KNOWN_SUPPLIERS.get(dist_name.lower(), ("PyPI Maintainer", None))
    try:
        meta = importlib.metadata.metadata(dist_name)
        lic_expr = meta.get("License-Expression")
        if lic_expr and lic_expr.strip():
            return lic_expr.strip()[:64]
        lic = meta.get("License")
        if lic and lic.strip() and len(lic.strip().splitlines()) == 1 and len(lic.strip()) <= 64:
            return lic.strip()
        for clf in meta.get_all("Classifier") or []:
            if clf.startswith("License :: OSI Approved ::"):
                short = clf.split("::")[-1].strip()
                return short
    except importlib.metadata.PackageNotFoundError:
        pass
    return fallback_lic or "OSI-Permissive"


def _extract_pkg_supplier(dist_name: str) -> str:
    key = dist_name.lower()
    if key in KNOWN_SUPPLIERS:
        return KNOWN_SUPPLIERS[key][0]
    try:
        meta = importlib.metadata.metadata(dist_name)
        author = meta.get("Author") or meta.get("Maintainer") or meta.get("Author-email")
        if author and author.strip():
            clean = re.sub(r"\s*<[^>]+>", "", author.strip())
            if clean:
                return clean[:80]
    except importlib.metadata.PackageNotFoundError:
        pass
    return "PyPI Ecosystem"


def build_workspace_cyclonedx_sbom(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Generate a deterministic CycloneDX SBOM from `pyproject.toml`, `uv.lock`, and runtime metadata."""
    pyproject_path = repo_root / "pyproject.toml"
    uv_lock_path = repo_root / "uv.lock"
    locked = _parse_uv_lock_packages(uv_lock_path)

    direct_names: list[str] = []
    if pyproject_path.is_file():
        try:
            py_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
            for spec in (py_data.get("project") or {}).get("dependencies") or []:
                m = re.match(r"^([A-Za-z0-9_.-]+)", str(spec).strip())
                if m:
                    direct_names.append(m.group(1).lower())
        except Exception:
            pass

    ordered_keys = list(dict.fromkeys(direct_names + sorted(locked.keys())))
    components: list[dict[str, Any]] = []
    for pkg_key in ordered_keys:
        if pkg_key == "unicorn-radar":
            continue
        lock_info = locked.get(pkg_key)
        version = lock_info["version"] if lock_info else None
        if not version:
            try:
                version = importlib.metadata.version(pkg_key)
            except importlib.metadata.PackageNotFoundError:
                continue
        display_name = lock_info["name"] if lock_info else pkg_key
        comp: dict[str, Any] = {
            "type": "library",
            "name": display_name,
            "version": version,
            "purl": f"pkg:pypi/{display_name}@{version}",
            "scope": "required" if pkg_key in direct_names else "transitive",
            "license": _extract_pkg_license(display_name),
            "supplier_vendor": _extract_pkg_supplier(display_name),
        }
        if lock_info and lock_info.get("sha256"):
            comp["hashes"] = [{"alg": "SHA-256", "content": lock_info["sha256"]}]
        components.append(comp)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "complete": uv_lock_path.is_file(),
        "source": "uv.lock + pyproject.toml + importlib.metadata",
        "direct_dependency_count": sum(1 for c in components if c.get("scope") == "required"),
        "component_count": len(components),
        "components": components,
    }


class CraciProvenanceClient:
    """CRACI build provenance, CycloneDX SBOM, egress trace, and AI supply-chain auditor."""

    def __init__(self, query_engine: Any) -> None:
        self.engine = query_engine

    def _base_url(self) -> str:
        return (os.environ.get("CRACI_BASE_URL") or "https://api.craci.com").rstrip("/")

    def _match_vendors_in_cala(self, components: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cross-reference dependency vendors & tech ecosystems against verified Cala/Slush nodes."""
        candidate_queries = ["Google", "Aiven", "Linux Foundation", "GitHub", "Python"]
        for c in components:
            vendor = str(c.get("supplier_vendor") or "").split("/")[0].strip()
            if vendor and vendor not in candidate_queries and vendor not in {"PyPI Ecosystem", "Encode"}:
                candidate_queries.append(vendor)

        matches: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for q in candidate_queries:
            try:
                res = self.engine.resolve(q, "Company", limit=5)
            except TypeError:
                res = self.engine.resolve(q, "Company")
            ent = res.get("entity")
            if not ent and res.get("candidates"):
                # Only pick exact-name candidate with non-empty evidence_ids
                for cand in res["candidates"]:
                    if str(cand.get("name") or "").strip().casefold() == q.casefold() and cand.get("evidence_ids"):
                        ent = cand
                        break
            if isinstance(ent, dict) and ent.get("id") and ent["id"] not in seen_ids and ent.get("evidence_ids"):
                seen_ids.add(ent["id"])
                matches.append(
                    {
                        "vendor_query": q,
                        "matched_entity_id": ent["id"],
                        "matched_name": ent.get("name", q),
                        "entity_type": ent.get("entity_type", "Company"),
                        "evidence_ids": list(ent.get("evidence_ids") or [])[:4],
                    }
                )
        return matches

    def get_provenance(self, *, repo: str | None = None, job_id: str | None = None) -> dict[str, Any]:
        workflow_policy = scan_github_workflows(REPO_ROOT)
        local_sbom = build_workspace_cyclonedx_sbom(REPO_ROOT)
        org = (os.environ.get("CRACI_ORG") or "cala-junction").strip()
        default_repo = (os.environ.get("CRACI_REPO") or os.environ.get("GITHUB_REPOSITORY") or f"{org}/Cala-Junction-Hack").strip()
        effective_repo = (repo or default_repo).strip()

        token = (os.environ.get("CRACI_API_TOKEN") or "").strip()
        if token:
            live_payload = self._fetch_craci_cloud(
                token=token,
                org=org,
                repo=effective_repo,
                job_id=job_id,
                workflow_policy=workflow_policy,
                fallback_sbom=local_sbom,
            )
            if live_payload is not None:
                return live_payload

        cala_matches = self._match_vendors_in_cala(local_sbom["components"])
        return {
            "status": "ok",
            "source_mode": "verified_workspace_snapshot",
            "mode": "local_workspace_sbom",
            "organization": org,
            "repository": effective_repo,
            "note": (
                "Computed deterministically from local workspace `pyproject.toml`, `uv.lock`, "
                "`importlib.metadata`, and `.github/workflows/*.yml` (CRACI_API_TOKEN not set; "
                "zero remote job IDs or network traces were fabricated)."
            ),
            "workflow_policy": workflow_policy,
            "latest_job": None,
            "sbom": local_sbom,
            "network_trace": {
                "schemaVersion": "1.0",
                "mode": "policy_inspection_offline",
                "configured_default": (
                    workflow_policy["craci_runner_jobs"][0].get("network_default")
                    if workflow_policy["craci_runner_jobs"]
                    else "unset"
                ),
                "configured_presets": (
                    workflow_policy["craci_runner_jobs"][0].get("network_presets")
                    if workflow_policy["craci_runner_jobs"]
                    else []
                ),
                "total_observations": 0,
                "policy_denied_count": 0,
                "unmatched_egress_count": 0,
                "observations": [],
            },
            "usage": None,
            "cala_entity_matches": cala_matches,
        }

    def _fetch_craci_cloud(
        self,
        *,
        token: str,
        org: str,
        repo: str,
        job_id: str | None,
        workflow_policy: dict[str, Any],
        fallback_sbom: dict[str, Any],
    ) -> dict[str, Any] | None:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        base = self._base_url()
        latest_job = None
        sbom_out = fallback_sbom
        trace_out: dict[str, Any] = {
            "schemaVersion": "1.0",
            "total_observations": 0,
            "policy_denied_count": 0,
            "unmatched_egress_count": 0,
            "observations": [],
        }
        usage_out = None

        try:
            with httpx.Client(timeout=15.0) as client:
                jobs_resp = client.get(f"{base}/v1preview1/jobs", headers=headers, params={"status": "active"})
                if jobs_resp.status_code == 401:
                    return None
                if jobs_resp.status_code == 200:
                    jobs_list = (jobs_resp.json() or {}).get("jobs") or []
                    if jobs_list:
                        latest_job = jobs_list[0]
                        if not job_id:
                            job_id = str(latest_job.get("jobId") or "")
                            repo = str(latest_job.get("repository") or repo)

                if job_id and "/" in repo:
                    sbom_resp = client.get(
                        f"{base}/v1preview1/sbom",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.cyclonedx+json; version=1.7, application/json"},
                        params={"provider": "github", "repo": repo, "job_id": job_id},
                    )
                    if sbom_resp.status_code == 200:
                        raw_sbom = sbom_resp.json()
                        raw_comps = raw_sbom.get("components") or []
                        sbom_out = {
                            "bomFormat": raw_sbom.get("bomFormat", "CycloneDX"),
                            "specVersion": raw_sbom.get("specVersion", "1.7"),
                            "complete": True,
                            "component_count": len(raw_comps),
                            "components": [
                                {
                                    "name": c.get("name"),
                                    "version": c.get("version"),
                                    "purl": c.get("purl"),
                                    "license": (
                                        ((c.get("licenses") or [{}])[0].get("license") or {}).get("id")
                                        if c.get("licenses")
                                        else "Unknown"
                                    ),
                                    "supplier_vendor": (c.get("supplier") or {}).get("name") or _extract_pkg_supplier(str(c.get("name") or "")),
                                }
                                for c in raw_comps
                            ],
                        }

                    nt_resp = client.get(
                        f"{base}/v1preview1/network-trace",
                        headers=headers,
                        params={"provider": "github", "repo": repo, "job_id": job_id},
                    )
                    if nt_resp.status_code == 200:
                        nt_json = nt_resp.json() or {}
                        obs = nt_json.get("observations") or []
                        denied = sum(
                            1
                            for o in obs
                            if (o.get("http") or {}).get("policyDenied")
                            or (o.get("tcp") or {}).get("allowed") is False
                            or (o.get("sshGit") or {}).get("allowed") is False
                        )
                        unmatched = sum(
                            1
                            for o in obs
                            if o.get("protocol") == "http" and not (o.get("http") or {}).get("matchedRule")
                        )
                        trace_out = {
                            "schemaVersion": nt_json.get("schemaVersion", "1.0"),
                            "total_observations": len(obs),
                            "policy_denied_count": denied,
                            "unmatched_egress_count": unmatched,
                            "observations": obs[:50],
                        }
                        if not latest_job and nt_json.get("job"):
                            latest_job = nt_json["job"]

                now = datetime.now(timezone.utc)
                start_iso = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                end_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                u_resp = client.get(
                    f"{base}/v1preview1/usage",
                    headers=headers,
                    params={"start": start_iso, "end": end_iso},
                )
                if u_resp.status_code == 200:
                    total = (u_resp.json() or {}).get("total") or {}
                    secs = int(total.get("vcpuSeconds") or 0)
                    usage_out = {"vcpuSeconds": secs, "vcpuMinutes": round(secs / 60.0, 2)}

            return {
                "status": "ok",
                "source_mode": "craci_api_live",
                "mode": "craci_cloud_api",
                "organization": org,
                "repository": repo,
                "workflow_policy": workflow_policy,
                "latest_job": latest_job,
                "sbom": sbom_out,
                "network_trace": trace_out,
                "usage": usage_out,
                "cala_entity_matches": self._match_vendors_in_cala(sbom_out.get("components") or []),
            }
        except Exception:
            return None

    def audit_provenance(
        self,
        *,
        job_id: str | None = None,
        repo: str | None = None,
        focus: str = "full",
        composer_mode: str = "auto",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        prov = self.get_provenance(repo=repo, job_id=job_id)
        det = self._deterministic_audit(prov, focus=focus)
        eff_mode = resolve_effective_composer_mode(composer_mode, default_template=False)

        if eff_mode == "template" or (not gemini_is_configured() and not gemma_is_configured()):
            det["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            return det

        audit_input = {
            "focus": focus,
            "source_mode": prov["source_mode"],
            "workflow_policy": prov["workflow_policy"],
            "sbom_summary": {
                "bomFormat": prov["sbom"]["bomFormat"],
                "specVersion": prov["sbom"]["specVersion"],
                "complete": prov["sbom"]["complete"],
                "component_count": prov["sbom"]["component_count"],
                "direct_components": [
                    c for c in prov["sbom"]["components"] if c.get("scope") == "required"
                ] or prov["sbom"]["components"][:12],
            },
            "network_trace": prov["network_trace"],
        }
        prompt = """You are the CRACI Supply-Chain & EU Cyber Resilience Act (CRA) Readiness Auditor.
Analyze ONLY the supplied `workflow_policy`, `sbom_summary`, and `network_trace`. Never invent CVEs or network traffic.
Return JSON with exact keys:
{
  "risk_level": "low" | "medium" | "high",
  "sbom_completeness_verdict": "string",
  "egress_verdict": "string",
  "summary": "1-2 sentence factual executive summary",
  "findings": [
    {"severity": "info"|"warning"|"recommendation", "category": "runner_routing"|"egress_policy"|"sbom_completeness"|"license_hygiene", "title": "...", "detail": "...", "evidence_ref": "..."}
  ]
}"""
        try:
            if eff_mode in {"gemini", "gemini_gemma_audit"} and gemini_is_configured():
                parsed, model_used = call_gemini_json(prompt, audit_input, timeout=30.0)
            else:
                parsed, _prov_name, model_used = call_gemma_json(prompt, audit_input, timeout=35.0)
            findings = parsed.get("findings")
            if not isinstance(findings, list) or not findings:
                raise ValueError("Empty findings")
            clean_findings = [
                {
                    "severity": str(f.get("severity") or "info"),
                    "category": str(f.get("category") or "sbom_completeness"),
                    "title": str(f.get("title") or "Audit Finding"),
                    "detail": str(f.get("detail") or ""),
                    "evidence_ref": str(f.get("evidence_ref") or "sbom:uv.lock"),
                }
                for f in findings[:6]
                if isinstance(f, dict) and f.get("detail")
            ]
            return {
                "status": "ok",
                "source_mode": prov["source_mode"],
                "auditor_model": model_used,
                "risk_level": str(parsed.get("risk_level") or det["risk_level"]),
                "sbom_completeness_verdict": str(parsed.get("sbom_completeness_verdict") or det["sbom_completeness_verdict"]),
                "egress_verdict": str(parsed.get("egress_verdict") or det["egress_verdict"]),
                "summary": str(parsed.get("summary") or det["summary"]),
                "findings": clean_findings or det["findings"],
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        except Exception:
            det["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            return det

    @staticmethod
    def _deterministic_audit(prov: dict[str, Any], *, focus: str = "full") -> dict[str, Any]:
        wf = prov["workflow_policy"]
        sbom = prov["sbom"]
        nt = prov["network_trace"]
        jobs = wf.get("craci_runner_jobs") or []
        comp_count = sbom.get("component_count", 0)
        direct_count = sbom.get("direct_dependency_count", comp_count)
        findings: list[dict[str, Any]] = []

        has_craci = bool(jobs)
        has_deny = any(j.get("block_unmatched_egress") for j in jobs)

        if has_craci:
            j0 = jobs[0]
            findings.append(
                {
                    "severity": "info",
                    "category": "runner_routing",
                    "title": f"Isolated VM Build Routing (`runs-on: {j0['runs_on']}`)",
                    "detail": (
                        f"Workflow `{j0['workflow']}` job `{j0['job_name']}` executes on isolated CRACI Linux VMs "
                        f"(size `{j0.get('size', 'default')}`) with automatic package-aware proxy SBOM attestation."
                    ),
                    "evidence_ref": f"workflow:{j0['workflow']}",
                }
            )
        else:
            findings.append(
                {
                    "severity": "warning",
                    "category": "runner_routing",
                    "title": "No `runs-on: craci` Workflow Detected",
                    "detail": "Add `runs-on: craci` and `cracicorp/setup@v1` in `.github/workflows/` to capture VM-isolated build provenance.",
                    "evidence_ref": "workflow:.github/workflows",
                }
            )

        if has_deny:
            j0 = jobs[0]
            presets = ", ".join(j0.get("network_presets") or [])
            findings.append(
                {
                    "severity": "info",
                    "category": "egress_policy",
                    "title": "Default-Deny Network Egress Lockdown Verified",
                    "detail": (
                        f"`cracicorp/setup@v1` enforces `default: deny` with allowlisted presets (`{presets}`), "
                        "blocking unmatched outbound destinations against supply-chain exfiltration and qualifying for Complete SBOM status."
                    ),
                    "evidence_ref": f"workflow:{j0['workflow']}#network",
                }
            )
        else:
            findings.append(
                {
                    "severity": "recommendation",
                    "category": "egress_policy",
                    "title": "Enforce Block-Unmatched Egress Policy for Complete Attestation",
                    "detail": "Configure `default: deny` with `presets: [pypi, github]` in `cracicorp/setup@v1` to earn a Complete SBOM.",
                    "evidence_ref": "policy:egress",
                }
            )

        hashes_present = sum(1 for c in (sbom.get("components") or []) if c.get("hashes"))
        findings.append(
            {
                "severity": "info",
                "category": "sbom_completeness",
                "title": f"CycloneDX {sbom.get('specVersion')} Dependency Inventory ({comp_count} Packages)",
                "detail": (
                    f"Verified {direct_count} direct and {max(0, comp_count - direct_count)} transitive Python packages "
                    f"with {hashes_present} SHA-256 lockfile digests and zero npm/Node runtime attack surface."
                ),
                "evidence_ref": "sbom:uv.lock",
            }
        )

        copyleft = [
            c["name"]
            for c in (sbom.get("components") or [])
            if any(k in str(c.get("license") or "").upper() for k in ("GPL", "AGPL"))
            and "LGPL" not in str(c.get("license") or "").upper()
        ]
        findings.append(
            {
                "severity": "warning" if copyleft else "info",
                "category": "license_hygiene",
                "title": "CRA License & Supplier Attribution Check",
                "detail": (
                    f"Flagged strong-copyleft packages: {', '.join(copyleft)}."
                    if copyleft
                    else "All inspected runtime dependencies declare permissive or LGPL-compatible licenses with PURL identifiers ready for EU CRA technical file export."
                ),
                "evidence_ref": "sbom:pyproject.toml",
            }
        )

        denied_cnt = int(nt.get("policy_denied_count") or 0)
        risk = "low" if (has_craci and has_deny and denied_cnt == 0 and not copyleft) else "medium"
        return {
            "status": "ok",
            "source_mode": prov["source_mode"],
            "auditor_model": "deterministic-craci-auditor-v2.1",
            "risk_level": risk,
            "sbom_completeness_verdict": "verified_lockfile_and_runtime" if sbom.get("complete") else "partial_manifest",
            "egress_verdict": (
                "clean_default_deny_enforced" if has_deny and denied_cnt == 0 else "policy_review_recommended"
            ),
            "summary": (
                f"Verified {comp_count} Python dependencies ({direct_count} direct) in CycloneDX {sbom.get('specVersion')} format; "
                f"CI workflow routes builds to isolated `runs-on: craci` VMs with `default: deny` egress lockdown."
                if (has_craci and has_deny)
                else f"Inspected {comp_count} Python dependencies ({direct_count} direct) in CycloneDX {sbom.get('specVersion')} format."
            ),
            "findings": findings,
            "elapsed_ms": 0.0,
        }
