"""Tests for app.executor and app.routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a2a.types import DataPart, Message, Part, Role, TextPart

from app.executor import SerpAgentExecutor, _extract_text
from app.routes import make_router


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------


def _text_message(text: str) -> Message:
    return Message(
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
        message_id="test-id",
    )


def _empty_message() -> Message:
    return Message(
        role=Role.user,
        parts=[Part(root=DataPart(data={}))],
        message_id="test-id",
    )


def test_extract_text_returns_first_text_part() -> None:
    assert _extract_text(_text_message("hello world")) == "hello world"


def test_extract_text_returns_empty_for_non_text_parts() -> None:
    assert _extract_text(_empty_message()) == ""


# ---------------------------------------------------------------------------
# SerpAgentExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_calls_search_with_query() -> None:
    agent = MagicMock()
    agent.search = AsyncMock(return_value="<html>results</html>")

    executor = SerpAgentExecutor(agent)
    context = MagicMock()
    context.message = _text_message("python asyncio")
    context.task_id = "task-1"
    context.context_id = "ctx-1"

    event_queue = MagicMock()
    updater = MagicMock()
    updater.update_status = AsyncMock()

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.executor.TaskUpdater", lambda *_: updater)
        await executor.execute(context, event_queue)

    agent.search.assert_awaited_once_with("python asyncio")
    updater.update_status.assert_awaited_once()
    reply: Message = updater.update_status.call_args.kwargs["message"]
    assert reply.parts[0].root.text == "<html>results</html>"


@pytest.mark.asyncio
async def test_executor_empty_query_returns_no_query_message() -> None:
    agent = MagicMock()
    agent.search = AsyncMock()

    executor = SerpAgentExecutor(agent)
    context = MagicMock()
    context.message = _empty_message()
    context.task_id = "task-2"
    context.context_id = "ctx-2"

    event_queue = MagicMock()
    updater = MagicMock()
    updater.update_status = AsyncMock()

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.executor.TaskUpdater", lambda *_: updater)
        await executor.execute(context, event_queue)

    agent.search.assert_not_awaited()
    reply: Message = updater.update_status.call_args.kwargs["message"]
    assert "No query provided" in reply.parts[0].root.text


# ---------------------------------------------------------------------------
# REST routes — /api/search and /ui
# ---------------------------------------------------------------------------


def _make_test_client(search_result: str | Exception) -> TestClient:
    agent = MagicMock()
    if isinstance(search_result, Exception):
        agent.search = AsyncMock(side_effect=search_result)
    else:
        agent.search = AsyncMock(return_value=search_result)

    test_app = FastAPI()
    test_app.include_router(make_router(agent))
    return TestClient(test_app)


def test_api_search_returns_html_and_metadata() -> None:
    client = _make_test_client("<html>results</html>")
    resp = client.post("/api/search", json={"query": "test query"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "test query"
    assert data["html"] == "<html>results</html>"
    assert isinstance(data["elapsed_ms"], int)


def test_api_search_empty_query_returns_400() -> None:
    client = _make_test_client("<html/>")
    resp = client.post("/api/search", json={"query": "   "})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_api_search_agent_error_returns_500() -> None:
    client = _make_test_client(RuntimeError("proxy failed"))
    resp = client.post("/api/search", json={"query": "something"})
    assert resp.status_code == 500
    assert "proxy failed" in resp.json()["error"]


def test_ui_returns_html() -> None:
    client = _make_test_client("<html/>")
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "SERP Agent" in resp.text
