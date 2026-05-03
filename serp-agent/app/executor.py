"""A2A AgentExecutor implementation for the SERP agent."""

from __future__ import annotations

import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import Message, Role, TaskState, TextPart

from serp_agent.agent import SerpAgent


def _extract_text(message: Message) -> str:
    """Return the first TextPart text from a message, or empty string."""
    for part in message.parts:
        root = part.root
        if isinstance(root, TextPart):
            return root.text
    return ""


class SerpAgentExecutor(AgentExecutor):
    """Bridges A2A task lifecycle with :class:`~serp_agent.agent.SerpAgent`."""

    def __init__(self, agent: SerpAgent) -> None:
        self._agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = _extract_text(context.message) if context.message else ""
        if not text:
            reply = Message(
                role=Role.agent,
                parts=[TextPart(text="No input provided. Send a search query or a URL.")],
                message_id=str(uuid.uuid4()),
            )
            await updater.update_status(TaskState.completed, message=reply, final=True)
            return

        # Dispatch: a URL goes to fetch(); anything else is a search query
        if text.startswith(("http://", "https://")):
            html = await self._agent.fetch(text)
        else:
            html = await self._agent.search(text)

        reply = Message(
            role=Role.agent,
            parts=[TextPart(text=html)],
            message_id=str(uuid.uuid4()),
        )
        await updater.update_status(TaskState.completed, message=reply, final=True)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.update_status(TaskState.canceled, final=True)
