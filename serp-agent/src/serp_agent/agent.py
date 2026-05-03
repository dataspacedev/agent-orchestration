"""SerpAgent — orchestrates proxy pool, delays, browser fetch, and returns HTML."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.parse
import urllib.request

from serp_agent.browser import BrowserSession
from serp_agent.config import SerpConfig
from serp_agent.fingerprint import human_delay, random_ua_profile, random_user_agent, random_viewport
from serp_agent.proxy import ProxyPool

_HTTP_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,*/*;q=0.8"
)


class SerpAgent:
    """Top-level agent that searches a SERP page and returns its HTML.

    Parameters
    ----------
    config:
        Validated :class:`~serp_agent.config.SerpConfig` instance.
    """

    def __init__(self, config: SerpConfig) -> None:
        self._config = config
        self._pool: ProxyPool | None = ProxyPool(config.proxies) if config.proxies else None

    async def search(self, query: str) -> str:
        """Fetch the SERP page for *query* and return its rendered HTML."""
        await human_delay()
        url = self._config.search_url_template.format(
            query=urllib.parse.quote_plus(query)
        )

        if self._config.use_browser:
            return await self._fetch_browser(url)
        return await self._fetch_http(url)

    async def fetch(self, url: str) -> str:
        """Fetch and return the fully rendered HTML of an arbitrary URL.

        Applies the same stealth browser session (or plain HTTP fallback) used
        by :meth:`search`, including proxy rotation and UA randomisation.

        Parameters
        ----------
        url:
            Absolute URL to fetch (must begin with ``http://`` or ``https://``).
        """
        await human_delay()
        if self._config.use_browser:
            return await self._fetch_browser(url)
        return await self._fetch_http(url)

    async def _fetch_browser(self, url: str) -> str:
        from playwright.async_api import Error as PlaywrightError

        proxy: str | None = self._pool.next() if self._pool is not None else None
        profile = random_ua_profile()
        viewport = random_viewport()
        try:
            async with BrowserSession(
                proxy_url=proxy,
                ua_profile=profile,
                viewport=viewport,
                headless=self._config.headless,
                timeout_ms=self._config.timeout_ms,
            ) as session:
                return await session.fetch(url)
        except (PlaywrightError, TimeoutError):
            if self._pool is not None and proxy is not None:
                self._pool.mark_dead(proxy)
            raise

    async def _fetch_http(self, url: str) -> str:
        ua = random_user_agent()
        timeout_s = self._config.timeout_ms / 1000

        proxy: str | None = self._pool.next() if self._pool is not None else None
        proxy_handler = (
            urllib.request.ProxyHandler(
                {"http": proxy, "https": proxy}
            )
            if proxy
            else urllib.request.ProxyHandler({})
        )
        opener = urllib.request.build_opener(proxy_handler)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": ua,
                "Accept": _HTTP_ACCEPT,
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        def _do_request() -> str:
            with opener.open(req, timeout=timeout_s) as resp:
                charset = "utf-8"
                ct = resp.headers.get_content_charset()
                if ct:
                    charset = ct
                raw: bytes = resp.read()
                return raw.decode(charset, errors="replace")

        try:
            return await asyncio.to_thread(_do_request)
        except urllib.error.URLError:
            if self._pool is not None and proxy is not None:
                self._pool.mark_dead(proxy)
            raise
