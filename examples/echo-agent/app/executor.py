"""A2A AgentExecutor for the echo agent."""

from __future__ import annotations

import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import Message, Role, TaskState, TextPart


def _extract_text(message: Message) -> str:
    for part in message.parts:
        root = part.root
        if isinstance(root, TextPart):
            return root.text
    return ""


class EchoExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = _extract_text(context.message) if context.message else ""
        reply = Message(
            role=Role.agent,
            parts=[TextPart(text=f"Echo: {text}" if text else "No input received.")],
            message_id=str(uuid.uuid4()),
        )
        await updater.update_status(TaskState.completed, message=reply, final=True)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.update_status(TaskState.canceled, final=True)
