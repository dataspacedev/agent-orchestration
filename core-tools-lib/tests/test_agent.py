"""Tests verifying create_agent_app() uses from_env() for task store selection."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

from core_tools.agent import AgentConfig, create_agent_app
from core_tools.task_store import RemoteTaskStoreClient


def _make_config() -> AgentConfig:
    return AgentConfig(
        name="test-agent",
        description="Test agent",
        version="0.0.1",
        url="http://localhost:8080",
    )


def _make_executor() -> MagicMock:
    from a2a.server.agent_execution import AgentExecutor
    return MagicMock(spec=AgentExecutor)


def test_uses_from_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_agent_app() uses InMemoryTaskStore when TASK_STORE_URL is unset."""
    monkeypatch.delenv("TASK_STORE_URL", raising=False)

    captured: list = []

    original_handler_cls = None

    import a2a.server.request_handlers.default_request_handler as drh_module

    OriginalHandler = drh_module.DefaultRequestHandler

    class CapturingHandler(OriginalHandler):
        def __init__(self, **kwargs):
            captured.append(kwargs.get("task_store"))
            super().__init__(**kwargs)

    with patch.object(drh_module, "DefaultRequestHandler", CapturingHandler):
        create_agent_app(config=_make_config(), executor=_make_executor())

    assert len(captured) == 1
    assert isinstance(captured[0], InMemoryTaskStore)


def test_uses_remote_when_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_agent_app() uses RemoteTaskStoreClient when TASK_STORE_URL is set."""
    monkeypatch.setenv("TASK_STORE_URL", "http://task-store:80")

    captured: list = []

    import a2a.server.request_handlers.default_request_handler as drh_module

    OriginalHandler = drh_module.DefaultRequestHandler

    class CapturingHandler(OriginalHandler):
        def __init__(self, **kwargs):
            captured.append(kwargs.get("task_store"))
            super().__init__(**kwargs)

    with patch.object(drh_module, "DefaultRequestHandler", CapturingHandler):
        create_agent_app(config=_make_config(), executor=_make_executor())

    assert len(captured) == 1
    assert isinstance(captured[0], RemoteTaskStoreClient)
