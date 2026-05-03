"""SERP agent — FastAPI application wiring."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication

from core_tools.health import router as health_router
from serp_agent.agent import SerpAgent
from serp_agent.config import SerpConfig

from app.agent_card import build_agent_card, build_request_handler
from app.routes import make_router

_config = SerpConfig.from_env()
_agent = SerpAgent(_config)

mcp = FastMCP("serp-agent")


@mcp.tool()
async def serp_search(query: str) -> str:
    """Fetch a search engine results page and return the rendered HTML."""
    return await _agent.search(query)


@mcp.tool()
async def fetch_url(url: str) -> str:
    """Fetch the fully rendered HTML of any URL using the same stealth browser session.

    Use this to scrape the content of a page once you have its URL (e.g. a
    result from serp_search).  Applies proxy rotation, UA randomisation, and
    human-like delays identical to serp_search.
    """
    return await _agent.fetch(url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="serp-agent",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(health_router)

A2AFastAPIApplication(
    agent_card=build_agent_card(os.getenv("AGENT_URL", "http://localhost:8080")),
    http_handler=build_request_handler(_agent),
).add_routes_to_app(app, agent_card_url="/.well-known/agent.json")

app.include_router(make_router(_agent))

# MCP mounted last — a root mount shadows everything registered after it.
app.mount("/", mcp.streamable_http_app())
