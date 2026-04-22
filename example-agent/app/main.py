from __future__ import annotations

import os
import uuid

from mcp.server.fastmcp import FastMCP

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentSkill, Message, Role, TaskState, TextPart

from core_tools import AgentConfig, create_agent_app
from app.tools.echo import echo, reverse_text, word_count

mcp = FastMCP("example-agent")


@mcp.tool()
def echo_text(text: str) -> str:
    """Echo text back unchanged."""
    return echo(text)


@mcp.tool()
def reverse(text: str) -> str:
    """Return text with characters reversed."""
    return reverse_text(text)


@mcp.tool()
def count_words(text: str) -> dict[str, int]:
    """Count words and characters in text."""
    return word_count(text)


def _extract_text(message: Message) -> str:
    for part in message.parts:
        root = part.root
        if isinstance(root, TextPart):
            return root.text
    return ""


class EchoAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = _extract_text(context.message) if context.message else ""
        reply = Message(
            role=Role.agent,
            parts=[TextPart(text=echo(text))],
            message_id=str(uuid.uuid4()),
        )
        await updater.update_status(TaskState.completed, message=reply, final=True)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.update_status(TaskState.canceled, final=True)


config = AgentConfig(
    name="example-agent",
    description="An example agent that echoes text back",
    version="0.1.0",
    url=os.getenv("AGENT_URL", "http://localhost:8080"),
    skills=[
        AgentSkill(
            id="echo",
            name="Echo",
            description="Echoes input text back unchanged",
            tags=["text"],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
            examples=["Hello, world!"],
        ),
        AgentSkill(
            id="reverse",
            name="Reverse",
            description="Reverses input text character by character",
            tags=["text", "transform"],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
            examples=["Hello → olleH"],
        ),
    ],
)

app = create_agent_app(config=config, executor=EchoAgentExecutor(), mcp_server=mcp)
