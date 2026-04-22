"""Remote task-store client and factory for core-tools agents.

Agents automatically use remote task persistence when TASK_STORE_URL is set
in the environment, and fall back to InMemoryTaskStore for local development.
"""
from __future__ import annotations

import os

import httpx
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_store import TaskStore
from a2a.types import Task


class RemoteTaskStoreClient(TaskStore):
    """TaskStore implementation that delegates to the remote task-store HTTP service."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Content-Type": "application/json"},
        )

    async def save(self, task: Task, context=None) -> None:
        await self._client.post("/tasks", content=task.model_dump_json())

    async def get(self, task_id: str, context=None) -> Task | None:
        r = await self._client.get(f"/tasks/{task_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return Task.model_validate_json(r.content)

    async def delete(self, task_id: str, context=None) -> None:
        r = await self._client.delete(f"/tasks/{task_id}")
        r.raise_for_status()


def from_env() -> TaskStore:
    """Return RemoteTaskStoreClient if TASK_STORE_URL is set, else InMemoryTaskStore."""
    url = os.getenv("TASK_STORE_URL")
    if url:
        return RemoteTaskStoreClient(url)
    return InMemoryTaskStore()
