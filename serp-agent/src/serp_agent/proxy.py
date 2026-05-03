"""Round-robin proxy pool with dead-proxy tracking."""

from __future__ import annotations


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
        total = len(self._proxies)
        for _ in range(total):
            candidate = self._proxies[self._idx % total]
            self._idx += 1
            if candidate not in self._dead:
                return candidate
        raise RuntimeError("all proxies are dead")  # pragma: no cover

    def mark_dead(self, proxy: str) -> None:
        """Mark *proxy* as dead so it is skipped by :meth:`next`."""
        self._dead.add(proxy)

    def reset(self) -> None:
        """Clear the dead-proxy set, reactivating all proxies."""
        self._dead.clear()
