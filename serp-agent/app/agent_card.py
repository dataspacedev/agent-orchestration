"""AgentCard and DefaultRequestHandler factory for the SERP agent."""

from __future__ import annotations

from importlib.metadata import version

from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from app.executor import SerpAgentExecutor
from serp_agent.agent import SerpAgent

_VERSION = version("serp-agent")


def build_agent_card(agent_url: str) -> AgentCard:
    """Build the A2A AgentCard from package metadata and static skill definitions."""
    return AgentCard(
        name="serp-agent",
        description="SERP scraping agent with proxy rotation, UA randomization, and human-like delays",
        url=agent_url,
        version=_VERSION,
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="serp_search",
                name="SERP Search",
                description="Fetches a search engine results page and returns the rendered HTML",
                tags=["search", "scraping", "web"],
                input_modes=["text/plain"],
                output_modes=["text/html"],
                examples=["python asyncio tutorial"],
            ),
            AgentSkill(
                id="fetch_url",
                name="Fetch URL",
                description=(
                    "Fetches the fully rendered HTML of any URL using the same stealth "
                    "browser session — proxy rotation, UA randomisation, and human-like delays"
                ),
                tags=["scraping", "web", "html"],
                input_modes=["text/plain"],
                output_modes=["text/html"],
                examples=["https://example.com/article"],
            ),
        ],
    )


def build_request_handler(agent: SerpAgent) -> DefaultRequestHandler:
    """Build the A2A DefaultRequestHandler wired to the given SerpAgent."""
    return DefaultRequestHandler(
        agent_executor=SerpAgentExecutor(agent),
        task_store=InMemoryTaskStore(),
    )
