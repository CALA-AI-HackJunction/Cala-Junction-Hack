"""FastAPI Dual-Mount Server + SSE Pipeline Stream + Same-Origin ES2022 Static Host.

Implements 100% of `docs/contracts/API_CONTRACT.md` (`v2.1`):
- Dual mounts at both `/api/*` and legacy root `/health`, `/questions`, `/coverage`,
  `/entities`, `/analyses`, `/analyses/{run_id}`, `/analyses/{run_id}/prompt`.
- Extended endpoints: `GET /api/presets`, `POST /api/analyses/stream` (SSE),
  `GET /api/cala/enrich/{entity_id}`, `GET /api/infrastructure/status`,
  `GET /api/craci/provenance`, `POST /api/craci/audit`.
- 16 KiB request body guard (`HTTP 413 {"error": "..."}`) and uniform `{"error": "..."}`
  error envelopes on `400`, `404`, `413`, and `500`.
- Same-origin zero-build frontend serving (`frontend/index.html` at `/` and `/css/*`,
  `/js/*`, `/assets/*`, `/static/*`).
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from .env_loader import FRONTEND_DIR, load_dotenv_once
    from .generation import build_generation_request
    from .service import QUESTION_SPECS, AnalysisService, build_default_service, load_presets_payload
except ImportError:
    from env_loader import FRONTEND_DIR, load_dotenv_once
    from generation import build_generation_request
    from service import QUESTION_SPECS, AnalysisService, build_default_service, load_presets_payload


MAX_BODY_BYTES = 16_384

MIME_OVERRIDES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _json_resp(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=data,
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


async def _parse_bounded_json(request: Request, *, allow_empty: bool = False) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return None, _json_resp({"error": "Request must contain at most 16 KiB"}, 413)
        except ValueError:
            return None, _json_resp({"error": "Invalid Content-Length header"}, 400)

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return None, _json_resp({"error": "Request must contain at most 16 KiB"}, 413)
    if not raw or not raw.strip():
        if allow_empty:
            return {}, None
        return None, _json_resp({"error": "Request body must be a non-empty JSON object"}, 400)

    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        return None, _json_resp({"error": f"Invalid JSON request body: {exc}"}, 400)

    if not isinstance(parsed, dict):
        return None, _json_resp({"error": "Request must be a JSON object"}, 400)
    return parsed, None


def _serve_frontend_file(sub_dir: str, rel_path: str, frontend_root: Path) -> Response:
    base = (frontend_root / sub_dir).resolve() if sub_dir else frontend_root.resolve()
    candidate = (base / rel_path).resolve()
    try:
        candidate.relative_to(frontend_root.resolve())
    except ValueError:
        return _json_resp({"error": "Route not found"}, 404)
    if not candidate.is_file():
        return _json_resp({"error": "Route not found"}, 404)
    ext = candidate.suffix.lower()
    media_type = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
    return FileResponse(candidate, media_type=media_type, headers={"Cache-Control": "no-cache"})


def create_app(
    service: AnalysisService | None = None,
    *,
    frontend_dir: Path | str | None = None,
) -> FastAPI:
    load_dotenv_once()
    fe_root = Path(frontend_dir) if frontend_dir else FRONTEND_DIR

    fastapi_app = FastAPI(
        title="Unicorn Radar — Cala × Slush Connection Intelligence",
        version="2.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    state: dict[str, AnalysisService | None] = {"service": service}

    def get_service() -> AnalysisService:
        if state["service"] is None:
            state["service"] = build_default_service()
        return state["service"]

    @fastapi_app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Route not found"
        if exc.status_code == 404 and detail == "Not Found":
            detail = "Route not found"
        return _json_resp({"error": detail}, exc.status_code)

    @fastapi_app.exception_handler(RequestValidationError)
    async def validation_exc_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _json_resp({"error": str(exc)}, 400)

    @fastapi_app.exception_handler(ValueError)
    async def value_exc_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return _json_resp({"error": str(exc)}, 400)

    @fastapi_app.exception_handler(Exception)
    async def generic_exc_handler(_request: Request, exc: Exception) -> JSONResponse:
        return _json_resp({"error": "Analysis failed", "error_type": type(exc).__name__}, 500)

    # ------------------------------------------------------------------
    # 1. Root & Static Frontend Serving
    # ------------------------------------------------------------------
    @fastapi_app.get("/", include_in_schema=False)
    async def root_route(request: Request) -> Response:
        accept = (request.headers.get("accept") or "").lower()
        wants_json_only = "application/json" in accept and "text/html" not in accept and "*/*" not in accept
        index_file = fe_root / "index.html"
        if not wants_json_only and index_file.is_file():
            return FileResponse(
                index_file,
                media_type="text/html; charset=utf-8",
                headers={"Cache-Control": "no-cache"},
            )
        svc = await run_in_threadpool(get_service)
        return _json_resp(svc.health_payload())

    @fastapi_app.get("/favicon.ico", include_in_schema=False)
    async def favicon_route() -> Response:
        for rel in ("favicon.ico", "assets/favicon.ico", "assets/favicon.svg"):
            target = fe_root / rel
            if target.is_file():
                media = "image/svg+xml" if target.suffix == ".svg" else "image/x-icon"
                return FileResponse(target, media_type=media, headers={"Cache-Control": "no-cache"})
        return Response(status_code=204)

    @fastapi_app.get("/css/{rel_path:path}", include_in_schema=False)
    async def serve_css(rel_path: str) -> Response:
        return _serve_frontend_file("css", rel_path, fe_root)

    @fastapi_app.get("/js/{rel_path:path}", include_in_schema=False)
    async def serve_js(rel_path: str) -> Response:
        return _serve_frontend_file("js", rel_path, fe_root)

    @fastapi_app.get("/assets/{rel_path:path}", include_in_schema=False)
    async def serve_assets(rel_path: str) -> Response:
        return _serve_frontend_file("assets", rel_path, fe_root)

    @fastapi_app.get("/static/{rel_path:path}", include_in_schema=False)
    async def serve_static(rel_path: str) -> Response:
        return _serve_frontend_file("", rel_path, fe_root)

    # ------------------------------------------------------------------
    # 2. Health, Questions, Presets, Coverage, Entity Resolution
    # ------------------------------------------------------------------
    @fastapi_app.get("/api/health")
    @fastapi_app.get("/health", include_in_schema=False)
    async def health_endpoint() -> JSONResponse:
        svc = await run_in_threadpool(get_service)
        return _json_resp(svc.health_payload())

    @fastapi_app.get("/api/questions")
    @fastapi_app.get("/questions", include_in_schema=False)
    async def questions_endpoint() -> JSONResponse:
        return _json_resp(QUESTION_SPECS)

    @fastapi_app.get("/api/hop-policies")
    @fastapi_app.get("/hop-policies", include_in_schema=False)
    async def hop_policies_endpoint() -> JSONResponse:
        return _json_resp(
            {
                "supported_modes": ["suggested", "custom", "max"],
                "global_hard_max_hops": 8,
                "cala_snapshot_crawl_hops": 4,
                "questions": {qid: spec["hop_policy"] for qid, spec in QUESTION_SPECS.items()},
            }
        )

    @fastapi_app.get("/api/presets")
    async def presets_endpoint() -> JSONResponse:
        payload = await run_in_threadpool(load_presets_payload)
        return _json_resp(payload)

    @fastapi_app.get("/api/coverage")
    @fastapi_app.get("/coverage", include_in_schema=False)
    async def coverage_endpoint() -> JSONResponse:
        svc = await run_in_threadpool(get_service)
        manifest = svc.snapshot.get("manifest") or {}
        return _json_resp({"graph_version": svc.snapshot.get("graph_version"), **manifest})

    @fastapi_app.get("/api/entities")
    @fastapi_app.get("/entities", include_in_schema=False)
    async def entities_endpoint(request: Request) -> JSONResponse:
        name = request.query_params.get("name", "")
        entity_type = request.query_params.get("type")
        raw_limit = request.query_params.get("limit", "15")

        if not name or not name.strip() or len(name) > 300:
            return _json_resp({"error": "Supply a name query parameter"}, 400)
        if entity_type is not None and entity_type not in {"Person", "Company", "Organization", "Investor", "Fund"}:
            return _json_resp({"error": "type must be Person or Company"}, 400)
        try:
            limit = int(raw_limit)
        except ValueError:
            return _json_resp({"error": "limit must be an integer between 1 and 50"}, 400)
        if not (1 <= limit <= 50):
            return _json_resp({"error": "limit must be between 1 and 50"}, 400)

        svc = await run_in_threadpool(get_service)

        def _do_resolve() -> dict[str, Any]:
            try:
                return svc.engine.resolve(name, entity_type, limit=limit)
            except TypeError:
                return svc.engine.resolve(name, entity_type)

        result = await run_in_threadpool(_do_resolve)
        return _json_resp(result)

    # ------------------------------------------------------------------
    # 3. Analyses (GET list, POST run, POST SSE stream, GET by ID, GET prompt)
    # ------------------------------------------------------------------
    @fastapi_app.get("/api/analyses")
    @fastapi_app.get("/analyses", include_in_schema=False)
    async def list_analyses_endpoint(request: Request) -> JSONResponse:
        raw_limit = request.query_params.get("limit", "25")
        try:
            limit = int(raw_limit)
        except ValueError:
            return _json_resp({"error": "limit must be an integer"}, 400)
        svc = await run_in_threadpool(get_service)
        rows = await run_in_threadpool(svc.store.list, limit)
        return _json_resp({"analyses": rows})

    @fastapi_app.post("/api/analyses")
    async def post_api_analyses(request: Request) -> JSONResponse:
        body, err = await _parse_bounded_json(request)
        if err is not None:
            return err
        svc = await run_in_threadpool(get_service)
        try:
            result = await run_in_threadpool(lambda: svc.analyze(body, default_template=False))
            return _json_resp(result)
        except (ValueError, TypeError) as exc:
            return _json_resp({"error": str(exc)}, 400)

    @fastapi_app.post("/analyses", include_in_schema=False)
    async def post_legacy_analyses(request: Request) -> JSONResponse:
        body, err = await _parse_bounded_json(request)
        if err is not None:
            return err
        svc = await run_in_threadpool(get_service)
        try:
            result = await run_in_threadpool(lambda: svc.analyze(body, default_template=True))
            return _json_resp(result)
        except (ValueError, TypeError) as exc:
            return _json_resp({"error": str(exc)}, 400)

    @fastapi_app.post("/api/analyses/stream")
    async def stream_analyses_endpoint(request: Request) -> Response:
        body, err = await _parse_bounded_json(request)
        if err is not None:
            return err
        svc = await run_in_threadpool(get_service)
        # Pre-validate request synchronously so bad inputs return HTTP 400 before SSE starts
        try:
            await run_in_threadpool(lambda: svc._validate_and_prepare(body, default_template=False))
        except (ValueError, TypeError) as exc:
            return _json_resp({"error": str(exc)}, 400)

        def _event_generator():
            try:
                for event_name, payload in svc.analyze_stream(body):
                    encoded = json.dumps(payload, ensure_ascii=False)
                    yield f"event: {event_name}\ndata: {encoded}\n\n"
            except Exception as exc:
                err_payload = json.dumps({"error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False)
                yield f"event: error\ndata: {err_payload}\n\n"

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @fastapi_app.get("/api/analyses/{run_id}")
    @fastapi_app.get("/analyses/{run_id}", include_in_schema=False)
    async def get_analysis_endpoint(run_id: str) -> JSONResponse:
        svc = await run_in_threadpool(get_service)
        record = await run_in_threadpool(svc.store.get, run_id)
        if record is None:
            return _json_resp({"error": "Analysis not found"}, 404)
        return _json_resp(record)

    @fastapi_app.get("/api/analyses/{run_id}/prompt")
    @fastapi_app.get("/analyses/{run_id}/prompt", include_in_schema=False)
    async def get_analysis_prompt_endpoint(run_id: str) -> JSONResponse:
        svc = await run_in_threadpool(get_service)
        record = await run_in_threadpool(svc.store.get, run_id)
        if record is None:
            return _json_resp({"error": "Analysis not found"}, 404)
        prompt_pkg = build_generation_request(record)
        return _json_resp(prompt_pkg)

    # ------------------------------------------------------------------
    # 4. Partner Tech Challenge Endpoints (Cala Live, Aiven + AI Infra, CRACI)
    # ------------------------------------------------------------------
    @fastapi_app.get("/api/cala/warm-intros")
    async def cala_warm_intros_endpoint(request: Request) -> JSONResponse:
        entity = request.query_params.get("entity")
        raw_limit = request.query_params.get("limit", "25")
        try:
            limit = int(raw_limit)
        except ValueError:
            return _json_resp({"error": "limit must be an integer"}, 400)
        svc = await run_in_threadpool(get_service)
        rows = await run_in_threadpool(lambda: svc.query_warm_intros(entity=entity, limit=limit))
        return _json_resp({"count": len(rows), "warm_intros": rows})

    @fastapi_app.get("/api/cala/shared-bridges")
    async def cala_shared_bridges_endpoint(request: Request) -> JSONResponse:
        entity = request.query_params.get("entity")
        raw_limit = request.query_params.get("limit", "25")
        try:
            limit = int(raw_limit)
        except ValueError:
            return _json_resp({"error": "limit must be an integer"}, 400)
        svc = await run_in_threadpool(get_service)
        rows = await run_in_threadpool(lambda: svc.query_shared_bridges(entity=entity, limit=limit))
        return _json_resp({"count": len(rows), "shared_bridges": rows})

    @fastapi_app.get("/api/cala/enrich/{entity_id:path}")
    async def cala_live_enrich_endpoint(entity_id: str, request: Request) -> JSONResponse:
        if not entity_id or not entity_id.strip() or len(entity_id) > 300:
            return _json_resp({"error": "Invalid entity_id"}, 400)
        raw_refresh = (request.query_params.get("refresh") or "false").strip().lower()
        refresh = raw_refresh in {"1", "true", "yes"}
        svc = await run_in_threadpool(get_service)
        enrichment = await run_in_threadpool(lambda: svc.cala_client.enrich(entity_id.strip(), refresh=refresh))
        return _json_resp(enrichment)

    @fastapi_app.get("/api/infrastructure/status")
    async def infrastructure_status_endpoint() -> JSONResponse:
        svc = await run_in_threadpool(get_service)
        payload = await run_in_threadpool(svc.infrastructure_status_payload)
        return _json_resp(payload)

    @fastapi_app.get("/api/craci/provenance")
    async def craci_provenance_endpoint(request: Request) -> JSONResponse:
        repo = request.query_params.get("repo")
        job_id = request.query_params.get("job_id")
        svc = await run_in_threadpool(get_service)
        payload = await run_in_threadpool(lambda: svc.craci_client.get_provenance(repo=repo, job_id=job_id))
        return _json_resp(payload)

    @fastapi_app.post("/api/craci/audit")
    async def craci_audit_endpoint(request: Request) -> JSONResponse:
        body, err = await _parse_bounded_json(request, allow_empty=True)
        if err is not None:
            return err
        allowed = {"job_id", "repo", "focus", "composer_mode"}
        extra = set(body) - allowed
        if extra:
            return _json_resp({"error": "Unexpected request fields: " + ", ".join(sorted(extra))}, 400)

        focus = body.get("focus") or "full"
        if not isinstance(focus, str):
            return _json_resp({"error": "focus must be a string"}, 400)
        composer_mode = body.get("composer_mode") or "auto"
        if not isinstance(composer_mode, str):
            return _json_resp({"error": "composer_mode must be a string"}, 400)

        svc = await run_in_threadpool(get_service)
        try:
            payload = await run_in_threadpool(
                lambda: svc.craci_client.audit_provenance(
                    job_id=body.get("job_id"),
                    repo=body.get("repo"),
                    focus=focus,
                    composer_mode=composer_mode,
                )
            )
            return _json_resp(payload)
        except ValueError as exc:
            return _json_resp({"error": str(exc)}, 400)

    return fastapi_app


app = create_app()
