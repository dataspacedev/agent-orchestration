"""REST routes: POST /api/search and GET /ui."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from serp_agent.agent import SerpAgent

_UI_PATH = Path(__file__).parent / "ui" / "index.html"


class SearchRequest(BaseModel):
    query: str


class FetchRequest(BaseModel):
    url: str


def make_router(agent: SerpAgent) -> APIRouter:
    """Return an APIRouter with /api/search, /api/fetch, and /ui wired to *agent*."""
    router = APIRouter()

    @router.post("/api/search")
    async def api_search(req: SearchRequest) -> JSONResponse:
        if not req.query.strip():
            return JSONResponse({"error": "query is required"}, status_code=400)
        t0 = time.monotonic()
        try:
            html = await agent.search(req.query)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        return JSONResponse({"query": req.query, "html": html, "elapsed_ms": elapsed_ms})

    @router.post("/api/fetch")
    async def api_fetch(req: FetchRequest) -> JSONResponse:
        if not req.url.strip():
            return JSONResponse({"error": "url is required"}, status_code=400)
        if not req.url.startswith(("http://", "https://")):
            return JSONResponse({"error": "url must begin with http:// or https://"}, status_code=400)
        t0 = time.monotonic()
        try:
            html = await agent.fetch(req.url)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        return JSONResponse({"url": req.url, "html": html, "elapsed_ms": elapsed_ms})

    @router.get("/ui", response_class=HTMLResponse)
    async def ui() -> str:
        return _UI_PATH.read_text()

    return router
