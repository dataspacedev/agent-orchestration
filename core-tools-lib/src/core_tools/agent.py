from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .health import router as health_router


@dataclass
class AgentConfig:
    name: str
    description: str
    version: str
    url: str
    default_input_modes: list[str] = field(default_factory=lambda: ["text/plain"])
    default_output_modes: list[str] = field(default_factory=lambda: ["text/plain"])
    skills: list[AgentSkill] = field(default_factory=list)


def create_agent_app(
    config: AgentConfig,
    executor: AgentExecutor,
    mcp_server: FastMCP | None = None,
) -> FastAPI:
    card = AgentCard(
        name=config.name,
        description=config.description,
        url=config.url,
        version=config.version,
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=config.default_input_modes,
        default_output_modes=config.default_output_modes,
        skills=config.skills,
    )

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if mcp_server is not None:
            async with mcp_server.session_manager.run():
                yield
        else:
            yield

    app = FastAPI(
        title=config.name,
        version=config.version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        redirect_slashes=False,
    )
    app.include_router(health_router)
    # Explicitly pass the spec-correct path so the SDK does not also register
    # the non-standard /.well-known/agent-card.json compat alias.
    A2AFastAPIApplication(agent_card=card, http_handler=handler).add_routes_to_app(
        app, agent_card_url="/.well-known/agent.json"
    )

    if mcp_server is not None:
        app.mount("/", mcp_server.streamable_http_app())

    return app
