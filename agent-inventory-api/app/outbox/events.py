"""Factory for creating AgentOutbox events."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.models.agent import Agent
from app.db.models.outbox import AgentOutbox
from app.k8s.client import make_crd_name
from app.models.agent import OutboxEventType


def make_outbox_event(agent: Agent, event_type: OutboxEventType) -> AgentOutbox:
    crd_name = make_crd_name(agent.name, agent.version)
    payload: dict[str, Any] = {
        "crd_name": crd_name,
        "name": agent.name,
        "version": agent.version,
    }
    if event_type not in (OutboxEventType.deleted, OutboxEventType.stopped):
        payload["spec"] = agent.spec or {}
    return AgentOutbox(
        id=str(uuid.uuid4()),
        agent_id=agent.id,
        event_type=event_type,
        payload=payload,
    )
