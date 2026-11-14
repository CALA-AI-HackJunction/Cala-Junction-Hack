"""HTTP server helpers (`app` for Uvicorn + `make_server` for stdlib test compatibility)."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import uvicorn

try:
    from .app import app, create_app
    from .generation import build_generation_request
    from .service import QUESTION_SPECS, load_presets_payload
except ImportError:
    from app import app, create_app
    from generation import build_generation_request
    from service import QUESTION_SPECS, load_presets_payload

__all__ = ["app", "create_app", "make_server", "run_server"]


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")


def make_server(service, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    """Stdlib ThreadingHTTPServer maintaining 100% reference `test_service.py` compatibility."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "UnicornRadar/2.1"

        def send_json(self, code: int, data) -> None:
            payload = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            raw_path = parsed.path.rstrip("/") or "/"
            path = raw_path[4:] if raw_path.startswith("/api/") else raw_path
            if raw_path == "/api":
                path = "/"

            if path in ("/", "/health"):
                if hasattr(service, "health_payload"):
                    return self.send_json(200, service.health_payload())
                return self.send_json(200, {"status": "ok", "graph_version": service.snapshot["graph_version"]})
            if path == "/questions":
                return self.send_json(200, QUESTION_SPECS)
            if path == "/presets":
                return self.send_json(200, load_presets_payload())
            if path == "/coverage":
                manifest = service.snapshot.get("manifest", {})
                return self.send_json(200, {"graph_version": service.snapshot.get("graph_version"), **manifest})
            if path == "/entities":
                args = parse_qs(parsed.query)
                name = args.get("name", [""])[0]
                entity_type = args.get("type", [None])[0]
                if not name or not name.strip() or len(name) > 300:
                    return self.send_json(400, {"error": "Supply a name query parameter"})
                return self.send_json(200, service.engine.resolve(name, entity_type))
            if path == "/analyses":
                return self.send_json(200, {"analyses": service.store.list()})
            if path == "/infrastructure/status" and hasattr(service, "infrastructure_status_payload"):
                return self.send_json(200, service.infrastructure_status_payload())
            if path == "/craci/provenance" and hasattr(service, "craci_client"):
                args = parse_qs(parsed.query)
                return self.send_json(
                    200,
                    service.craci_client.get_provenance(
                        repo=args.get("repo", [None])[0],
                        job_id=args.get("job_id", [None])[0],
                    ),
                )
            parts = path.strip("/").split("/")
            if len(parts) in (2, 3) and parts[0] == "analyses":
                result = service.store.get(parts[1])
                if result is None:
                    return self.send_json(404, {"error": "Analysis not found"})
                if len(parts) == 3:
                    if parts[2] != "prompt":
                        return self.send_json(404, {"error": "Route not found"})
                    result = build_generation_request(result)
                return self.send_json(200, result)
            self.send_json(404, {"error": "Route not found"})

        def do_POST(self) -> None:
            raw_path = urlsplit(self.path).path.rstrip("/")
            is_api = raw_path == "/api/analyses"
            if raw_path not in ("/analyses", "/api/analyses"):
                return self.send_json(404, {"error": "Route not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16384:
                    return self.send_json(413, {"error": "Request must contain at most 16 KiB"})
                if length <= 0:
                    return self.send_json(400, {"error": "Request body must be a non-empty JSON object"})
                request_obj = json.loads(self.rfile.read(length))
                response = service.analyze(request_obj, default_template=not is_api)
                self.send_json(200, response)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.send_json(400, {"error": str(error)})
            except Exception as error:
                self.send_json(500, {"error": "Analysis failed", "error_type": type(error).__name__})

        def log_message(self, format, *args):
            return

    return ThreadingHTTPServer((host, port), Handler)
