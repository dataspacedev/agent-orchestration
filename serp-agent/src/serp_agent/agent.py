"""SerpAgent — orchestrates proxy pool, delays, browser fetch, and returns HTML."""

from __future__ import annotations

import asyncio
import sys
import urllib.parse

from serp_agent.browser import BrowserSession
from serp_agent.config import SerpConfig
from serp_agent.proxy import ProxyPool, human_delay, random_user_agent


class SerpAgent:
    """Top-level agent that searches a SERP page and returns its HTML.

    Parameters
    ----------
    config:
        Validated :class:`~serp_agent.config.SerpConfig` instance.
    """

    def __init__(self, config: SerpConfig) -> None:
        self._config = config
        self._pool = ProxyPool(config.proxies)

    async def search(self, query: str) -> str:
        """Fetch the SERP page for *query* and return its rendered HTML.

        Steps:
        1. Wait a human-like random delay (8–15 s).
        2. Pick the next live proxy from the pool.
        3. Pick a random user-agent string.
        4. Build the search URL from the configured template.
        5. Open a :class:`~serp_agent.browser.BrowserSession` and fetch the page.
        6. On Playwright or timeout error: mark the proxy dead and re-raise.

        Parameters
        ----------
        query:
            Raw search query string (URL encoding is handled internally).

        Returns
        -------
        str
            Full HTML content of the rendered SERP page.
        """
        from playwright.async_api import Error as PlaywrightError  # local import

        await human_delay()
        proxy = self._pool.next()
        ua = random_user_agent()
        url = self._config.search_url_template.format(
            query=urllib.parse.quote_plus(query)
        )

        try:
            async with BrowserSession(
                proxy_url=proxy,
                user_agent=ua,
                headless=self._config.headless,
                timeout_ms=self._config.timeout_ms,
            ) as session:
                return await session.fetch(url)
        except (PlaywrightError, TimeoutError):
            self._pool.mark_dead(proxy)
            raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m serp_agent.agent <query>")
        sys.exit(1)

    _query = sys.argv[1]
    _config = SerpConfig.from_env()
    _agent = SerpAgent(_config)
    _html = asyncio.run(_agent.search(_query))
    print(_html[:500])
