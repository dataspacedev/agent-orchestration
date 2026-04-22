"""Unit tests for RemoteTaskStoreClient and from_env() factory."""
from __future__ import annotations

import os

import httpx
import pytest
import respx
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import Task, TaskState, TaskStatus

from core_tools.task_store import RemoteTaskStoreClient, from_env

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "task-1") -> Task:
    """Return a minimal valid Task instance."""
    return Task(
        id=task_id,
        contextId="ctx-1",
        status=TaskStatus(state=TaskState.submitted),
    )


# ---------------------------------------------------------------------------
# from_env() factory
# ---------------------------------------------------------------------------


def test_from_env_with_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_STORE_URL", "http://task-store:80")
    result = from_env()
    assert isinstance(result, RemoteTaskStoreClient)


def test_from_env_no_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TASK_STORE_URL", raising=False)
    result = from_env()
    assert isinstance(result, InMemoryTaskStore)


# ---------------------------------------------------------------------------
# RemoteTaskStoreClient HTTP methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remote_save_posts() -> None:
    task = _make_task()
    with respx.mock(base_url="http://task-store") as mock:
        route = mock.post("/tasks").mock(return_value=httpx.Response(200))
        client = RemoteTaskStoreClient("http://task-store")
        await client.save(task)
        assert route.called


@pytest.mark.asyncio
async def test_remote_get_returns_task() -> None:
    task = _make_task("task-42")
    task_json = task.model_dump_json()
    with respx.mock(base_url="http://task-store") as mock:
        mock.get("/tasks/task-42").mock(
            return_value=httpx.Response(200, content=task_json.encode())
        )
        client = RemoteTaskStoreClient("http://task-store")
        result = await client.get("task-42")
        assert result is not None
        assert result.id == "task-42"


@pytest.mark.asyncio
async def test_remote_get_returns_none_on_404() -> None:
    with respx.mock(base_url="http://task-store") as mock:
        mock.get("/tasks/missing").mock(return_value=httpx.Response(404))
        client = RemoteTaskStoreClient("http://task-store")
        result = await client.get("missing")
        assert result is None


@pytest.mark.asyncio
async def test_remote_delete_calls_delete() -> None:
    with respx.mock(base_url="http://task-store") as mock:
        route = mock.delete("/tasks/task-1").mock(return_value=httpx.Response(204))
        client = RemoteTaskStoreClient("http://task-store")
        await client.delete("task-1")
        assert route.called
