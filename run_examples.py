#!/usr/bin/env python3
"""Execute the 8 source-grounded reference examples and verify exact store recovery."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.env_loader import DATA_DIR, load_dotenv_once  # noqa: E402
from backend.ingest import ensure_snapshot  # noqa: E402
from backend.service import AnalysisService  # noqa: E402

EXAMPLES = [
    ("01_person_to_company", {"question_id": "person_to_company", "source": "Camille Accolas", "target": "Trust Exchange"}),
    ("02_ambiguous_target", {"question_id": "person_to_company", "source": "Dani Penev", "target": "Y Combinator"}),
    ("03_person_to_company_selected_target", {"question_id": "person_to_company", "source": "Dani Penev", "target_id": "cala:1e86655e-373d-4fe8-be13-af3713581f73"}),
    ("04_company_to_company", {"question_id": "company_to_company", "source": "Slicker", "target_id": "cala:1e86655e-373d-4fe8-be13-af3713581f73"}),
    ("05_company_network", {"question_id": "company_network", "company": "Trust Exchange"}),
    ("06_company_representatives", {"question_id": "company_representatives", "company": "Trust Exchange"}),
    ("07_no_supported_path", {"question_id": "company_to_company", "source": "Trust Exchange", "target": "Slicker"}),
    ("08_ambiguous_person", {"question_id": "person_to_company", "source": "Ben Fletcher", "target": "Trust Exchange"}),
]


def main() -> None:
    load_dotenv_once()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DATA_DIR / "snapshot.json")
    parser.add_argument("--database", type=Path, default=DATA_DIR / "analyses.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "examples")
    args = parser.parse_args()

    start = time.perf_counter()
    snapshot = ensure_snapshot(snapshot_path=args.snapshot, data_dir=args.snapshot.parent)
    service = AnalysisService(snapshot, args.database)
    load_seconds = time.perf_counter() - start
    args.output.mkdir(parents=True, exist_ok=True)

    summary = []
    for filename, request in EXAMPLES:
        started = time.perf_counter()
        response = service.analyze(request, refresh=True, default_template=True)
        roundtrip_ms = (time.perf_counter() - started) * 1000
        out_path = args.output / f"{filename}.json"
        out_path.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        recovered = service.store.get(response["run_id"])
        assert recovered == response, "Persistence changed the saved response"
        known_ids = {item["id"] for item in response.get("evidence", [])}
        graph = response.get("graph", {})
        node_ids = {node["id"] for node in graph.get("nodes", [])}
        edge_map = {edge["id"]: edge for edge in graph.get("edges", [])}
        for edge in edge_map.values():
            assert edge["source"] in node_ids and edge["target"] in node_ids
            assert edge["evidence_ids"] and set(edge["evidence_ids"]) <= known_ids
            assert edge["type"] != "PARTICIPATES_IN_EVENT"
        for graph_path in graph.get("paths", []):
            assert all(eid in edge_map for eid in graph_path["edge_ids"])
            assert graph_path["hop_count"] <= 4
            assert len(graph_path["node_ids"]) == len(graph_path["edge_ids"]) + 1

        summary.append({
            "file": out_path.name,
            "request": request,
            "status": response["status"],
            "summary": response["summary"],
            "result_count": len(response["results"]),
            "path_count": len(graph.get("paths", [])),
            "run_id": response["run_id"],
            "graph_version": response["graph_version"],
            "elapsed_ms_including_save": round(roundtrip_ms, 3),
            "saved_result_recovered_exactly": True,
        })

    cached = service.analyze(EXAMPLES[0][1], default_template=True)
    assert cached["cached"] and cached["run_id"] == summary[0]["run_id"]
    report = {
        "basis": "Executed on the supplied data with deterministic evidence templates; original web sources not reverified.",
        "load_seconds": round(load_seconds, 3),
        "generation_mode": "evidence_template",
        "external_model_called": False,
        "cache_recovery_verified": True,
        "examples": summary,
    }
    (args.output / "execution_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
