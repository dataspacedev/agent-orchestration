"""Proxy rotation, user-agent pool, and human-like delay utilities."""

from __future__ import annotations

import asyncio
import random

# ---------------------------------------------------------------------------
# User-agent pool — 15 real desktop Chrome/Firefox/Safari UAs from 2024
# ---------------------------------------------------------------------------

UA_POOL: list[str] = [
    # Chrome 124 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    # Chrome 124 — macOS
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.6367.82 Safari/537.36"
    ),
    # Chrome 123 — Linux
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    # Chrome 122 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.6261.128 Safari/537.36"
    ),
    # Firefox 125 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    # Firefox 124 — macOS
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    # Firefox 123 — Linux
    (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
    # Safari 17 — macOS Sonoma
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4.1 Safari/605.1.15"
    ),
    # Safari 17 — macOS Ventura
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_6) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15"
    ),
    # Edge 124 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
    ),
    # Edge 123 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0"
    ),
    # Chrome 124 — Windows (high-DPI)
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.6367.60 Safari/537.36"
    ),
    # Firefox 122 — Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
        "Gecko/20100101 Firefox/122.0"
    ),
    # Chrome 121 — macOS
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    # Safari 16 — macOS Monterey
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7_4) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Safari/605.1.15"
    ),
]


def random_user_agent() -> str:
    """Return a random user-agent string drawn from :data:`UA_POOL`."""
    return random.choice(UA_POOL)


async def human_delay() -> None:
    """Sleep for a randomized human-like delay between 8.0 and 15.0 seconds."""
    await asyncio.sleep(random.uniform(8.0, 15.0))


# ---------------------------------------------------------------------------
# ProxyPool
# ---------------------------------------------------------------------------


class ProxyPool:
    """Round-robin proxy pool with dead-proxy tracking.

    Parameters
    ----------
    proxies:
        Non-empty list of proxy URL strings.

    Raises
    ------
    ValueError
        If *proxies* is empty.
    """

    def __init__(self, proxies: list[str]) -> None:
        if not proxies:
            raise ValueError("proxy pool cannot be empty")
        self._proxies: list[str] = list(proxies)
        self._dead: set[str] = set()
        self._idx: int = 0

    def next(self) -> str:
        """Return the next live proxy in round-robin order.

        Raises
        ------
        RuntimeError
            If all proxies have been marked dead.
        """
        live = [p for p in self._proxies if p not in self._dead]
        if not live:
            raise RuntimeError("all proxies are dead; call reset() to reactivate them")
        # advance _idx within the full list, skipping dead entries
        total = len(self._proxies)
        for _ in range(total):
            candidate = self._proxies[self._idx % total]
            self._idx += 1
            if candidate not in self._dead:
                return candidate
        # Unreachable if live is non-empty, but satisfies type checker
        raise RuntimeError("all proxies are dead")  # pragma: no cover

    def mark_dead(self, proxy: str) -> None:
        """Mark *proxy* as dead so it is skipped by :meth:`next`."""
        self._dead.add(proxy)

    def reset(self) -> None:
        """Clear the dead-proxy set, reactivating all proxies."""
        self._dead.clear()
