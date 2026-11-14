#!/usr/bin/env python3
"""Command-line interface (`python -m backend.cli build|query|resolve|coverage|history|get|serve`)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from .env_loader import DATA_DIR, load_dotenv_once
except ImportError:
    from env_loader import DATA_DIR, load_dotenv_once


def emit(value, output: str | None = None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(str(path.resolve()))
    else:
        print(text)


def main() -> None:
    load_dotenv_once()
    parser = argparse.ArgumentParser(description="Unicorn Radar — Cala x Slush 2026 CLI")
    parser.add_argument("--snapshot", type=Path, default=DATA_DIR / "snapshot.json")
    parser.add_argument("--database", type=Path, default=DATA_DIR / "analyses.sqlite3")

    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Import the three supplied Cala & Slush datasets")
    build.add_argument("--people", type=Path, default=DATA_DIR / "slush_people.json")
    build.add_argument("--cala", type=Path, default=DATA_DIR / "cala_graph.json")
    build.add_argument("--companies", type=Path, default=DATA_DIR / "slush_companies.json")

    query = commands.add_parser("query", help="Run one of the four fixed connection tasks")
    query.add_argument(
        "question_id",
        choices=["person_to_company", "company_to_company", "company_network", "company_representatives"],
    )
    for field in ("source", "target", "company", "source-id", "target-id", "company-id"):
        query.add_argument("--" + field)
    query.add_argument("--composer-mode", choices=["auto", "template", "gemini", "gemma", "gemini_gemma_audit"])
    query.add_argument("--include-cala-live", action="store_true")
    query.add_argument("--output")
    query.add_argument("--refresh", action="store_true")

    resolve = commands.add_parser("resolve", help="Resolve an entity or list ambiguous/fuzzy candidates")
    resolve.add_argument("name")
    resolve.add_argument("--type", choices=["Person", "Company", "Organization"])
    resolve.add_argument("--limit", type=int, default=15)

    commands.add_parser("coverage", help="Show actual imported data coverage and SHA-256 digests")
    commands.add_parser("history", help="List saved analyses")

    recover = commands.add_parser("get", help="Recover a saved analysis by run_id")
    recover.add_argument("run_id")
    recover.add_argument("--output")

    serve = commands.add_parser("serve", help="Start the Unicorn Radar FastAPI + Static Webapp server")
    serve.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))

    args = parser.parse_args()

    if args.command == "build":
        try:
            from .ingest import build_snapshot
        except ImportError:
            from ingest import build_snapshot

        snapshot = build_snapshot(args.people, args.cala, args.companies)
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.snapshot.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(args.snapshot)
        emit({"snapshot": str(args.snapshot), "graph_version": snapshot["graph_version"], "manifest": snapshot["manifest"]})
        return

    if args.command in ("history", "get"):
        try:
            from .store import AnalysisStore
        except ImportError:
            from store import AnalysisStore

        store = AnalysisStore(args.database)
        result = store.list() if args.command == "history" else store.get(args.run_id)
        if result is None:
            parser.exit(1, "Analysis not found\n")
        emit(result, getattr(args, "output", None))
        return

    try:
        from .ingest import ensure_snapshot
        from .service import AnalysisService
    except ImportError:
        from ingest import ensure_snapshot
        from service import AnalysisService

    snapshot = ensure_snapshot(snapshot_path=args.snapshot, data_dir=args.snapshot.parent)
    if args.command == "coverage":
        emit({"graph_version": snapshot.get("graph_version"), **snapshot.get("manifest", {})})
        return

    service = AnalysisService(snapshot, args.database, os.environ.get("CALA_DEMO_COMPOSER_URL") or None)

    if args.command == "resolve":
        emit(service.engine.resolve(args.name, args.type, limit=args.limit))
    elif args.command == "query":
        request_obj = {"question_id": args.question_id}
        for field in ("source", "target", "company", "source_id", "target_id", "company_id"):
            if getattr(args, field):
                request_obj[field] = getattr(args, field)
        if args.composer_mode:
            request_obj["composer_mode"] = args.composer_mode
        if args.include_cala_live:
            request_obj["include_cala_live"] = True
        try:
            emit(
                service.analyze(
                    request_obj,
                    refresh=args.refresh,
                    default_template=(args.composer_mode is None),
                ),
                args.output,
            )
        except ValueError as error:
            parser.exit(2, str(error) + "\n")
    elif args.command == "serve":
        import uvicorn

        try:
            from .app import create_app
        except ImportError:
            from app import create_app

        fastapi_app = create_app(service=service)
        print(f"Unicorn Radar API & Webapp: http://{args.host}:{args.port}", flush=True)
        uvicorn.run(fastapi_app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
