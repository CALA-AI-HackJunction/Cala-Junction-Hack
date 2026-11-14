"""FastAPI entry point — exposes /query and /health endpoints."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import run_agent_turn
from mcp_client import CalaMCPClient, connect_cala
from traversal import CalaGraphTraversalEngine, ConnectionPath

logger = logging.getLogger("cala-agent")

# ── App lifespan: hold a persistent MCP connection ──────────────────────────

_cala_client: CalaMCPClient | None = None
_cala_cm = None  # context manager reference for cleanup


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cala_client, _cala_cm
    try:
        logger.info("Connecting to Cala MCP server…")
        _cala_cm = connect_cala()
        _cala_client = await _cala_cm.__aenter__()
        logger.info(f"Connected — discovered tools: {_cala_client.tool_names}")
    except Exception as exc:
        _cala_cm = None
        _cala_client = None
        logger.warning(f"Starting in UI preview mode (Cala MCP not connected: {exc})")
    try:
        yield
    finally:
        if _cala_cm is not None:
            await _cala_cm.__aexit__(None, None, None)
            logger.info("Cala MCP connection closed.")


app = FastAPI(title="Cala + Gemini Agent", lifespan=lifespan)


# ── Request / Response models ───────────────────────────────────────────────

class QueryRequest(BaseModel):
    message: str
    session_id: str | None = None  # future: per-session history


class QueryResponse(BaseModel):
    answer: str


class TraverseRequest(BaseModel):
    people_ids: list[str]


class TraverseResponse(BaseModel):
    count: int
    connections: list[dict]


# ── Routes ──────────────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "network.html")


@app.get("/health")
async def health():
    active_tools = [t for t in _cala_client.tool_names if t != "knowledge_search"] if _cala_client else []
    return {
        "status": "ok",
        "cala_connected": _cala_client is not None,
        "tools": active_tools,
    }


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    if not _cala_client:
        raise HTTPException(503, "Cala MCP client not connected")
    # TODO: retrieve per-session history using req.session_id
    answer, _ = await run_agent_turn(req.message, _cala_client)
    return QueryResponse(answer=answer)


@app.get("/slush/attendees")
async def slush_attendees(limit: int = 50):
    try:
        engine = CalaGraphTraversalEngine()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    attendees = await engine.get_slush_attendees(limit=limit)
    return {"count": len(attendees), "attendees": attendees}


@app.post("/traverse", response_model=TraverseResponse)
async def traverse(req: TraverseRequest):
    try:
        engine = CalaGraphTraversalEngine()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    results = await engine.traverse_network(req.people_ids)
    conns = [
        {
            "person1": c.source_person_name,
            "person1_id": c.source_person_id,
            "person2": c.target_person_name,
            "person2_id": c.target_person_id,
            "connection_type": c.connection_type,
            "hops": c.hops,
            "shared_entity": c.shared_entity_name,
            "shared_entity_id": c.shared_entity_id,
            "is_lead": c.is_lead,
            "source_rank": c.source_rank,
            "active": c.active,
            "description": c.description,
            "path": c.path,
        }
        for c in results
    ]
    return TraverseResponse(count=len(conns), connections=conns)
