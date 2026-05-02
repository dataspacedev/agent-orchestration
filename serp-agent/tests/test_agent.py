"""Unit tests for serp_agent proxy rotation, UA randomization, and delay bounds."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from serp_agent.config import SerpConfig
from serp_agent.proxy import UA_POOL, ProxyPool, human_delay, random_user_agent

# ---------------------------------------------------------------------------
# ProxyPool tests
# ---------------------------------------------------------------------------


def test_proxy_pool_empty_raises() -> None:
    """ProxyPool([]) raises ValueError."""
    with pytest.raises(ValueError, match="proxy pool cannot be empty"):
        ProxyPool([])


def test_proxy_pool_round_robin() -> None:
    """next() cycles proxies in order: p1, p2, p3, p1."""
    pool = ProxyPool(["p1", "p2", "p3"])
    assert pool.next() == "p1"
    assert pool.next() == "p2"
    assert pool.next() == "p3"
    assert pool.next() == "p1"


def test_proxy_pool_mark_dead_skips() -> None:
    """mark_dead skips a proxy; remaining proxies still served."""
    pool = ProxyPool(["p1", "p2", "p3"])
    pool.mark_dead("p1")
    # Should only return p2, p3
    results = {pool.next() for _ in range(4)}
    assert "p1" not in results
    assert {"p2", "p3"}.issubset(results)


def test_proxy_pool_all_dead_raises() -> None:
    """RuntimeError when all proxies are dead."""
    pool = ProxyPool(["p1", "p2"])
    pool.mark_dead("p1")
    pool.mark_dead("p2")
    with pytest.raises(RuntimeError):
        pool.next()


def test_proxy_pool_reset_clears_dead() -> None:
    """reset() allows previously dead proxies to be served again."""
    pool = ProxyPool(["p1", "p2"])
    pool.mark_dead("p1")
    pool.reset()
    results = {pool.next() for _ in range(4)}
    assert "p1" in results


# ---------------------------------------------------------------------------
# SerpConfig tests
# ---------------------------------------------------------------------------


def test_serp_config_valid() -> None:
    """SerpConfig accepts a valid proxies list."""
    cfg = SerpConfig(proxies=["http://proxy:8080"])
    assert cfg.proxies == ["http://proxy:8080"]
    assert cfg.headless is True
    assert cfg.timeout_ms == 30_000


def test_serp_config_missing_proxies_raises() -> None:
    """Missing proxies field raises pydantic ValidationError."""
    with pytest.raises(ValidationError):
        SerpConfig()  # type: ignore[call-arg]


def test_serp_config_empty_proxies_raises() -> None:
    """Empty proxies list raises pydantic ValidationError (min_length=1)."""
    with pytest.raises(ValidationError):
        SerpConfig(proxies=[])


# ---------------------------------------------------------------------------
# UA randomization tests
# ---------------------------------------------------------------------------


def test_ua_pool_size() -> None:
    """UA_POOL contains at least 10 entries."""
    assert len(UA_POOL) >= 10


def test_random_user_agent_returns_pool_member() -> None:
    """random_user_agent() returns a string that is in UA_POOL."""
    ua = random_user_agent()
    assert ua in UA_POOL


def test_random_user_agent_diversity() -> None:
    """Calling random_user_agent() 50 times yields at least 5 distinct values."""
    results = {random_user_agent() for _ in range(50)}
    assert len(results) >= 5


# ---------------------------------------------------------------------------
# human_delay tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_human_delay_calls_sleep_in_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """human_delay() calls asyncio.sleep with a value in [8.0, 15.0]."""
    sleep_calls: list[float] = []

    async def mock_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    await human_delay()

    assert len(sleep_calls) == 1
    delay = sleep_calls[0]
    assert 8.0 <= delay <= 15.0, f"Delay {delay} not in [8.0, 15.0]"
