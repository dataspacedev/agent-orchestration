"""Echo agent — FastAPI + A2A application."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from app.executor import EchoExecutor

app = FastAPI(
    title="echo-agent",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/ready")
async def ready() -> JSONResponse:
    return JSONResponse({"status": "ready"})


_card = AgentCard(
    name="echo-agent",
    description="Example A2A agent — echoes messages back",
    url=os.getenv("AGENT_URL", "http://localhost:8080"),
    version="0.1.0",
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="echo",
            name="Echo",
            description="Echoes the input message back to the caller",
            tags=["example", "echo"],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
            examples=["Hello, world!"],
        )
    ],
)

A2AFastAPIApplication(
    agent_card=_card,
    http_handler=DefaultRequestHandler(
        agent_executor=EchoExecutor(),
        task_store=InMemoryTaskStore(),
    ),
).add_routes_to_app(app, agent_card_url="/.well-known/agent.json")
