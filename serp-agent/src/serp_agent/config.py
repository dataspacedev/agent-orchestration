"""SerpConfig — pydantic-validated settings for the SERP scraping agent."""

from __future__ import annotations

import os

from pydantic import BaseModel


class SerpConfig(BaseModel):
    """Configuration for the SERP scraping agent.

    All fields can be supplied directly as keyword arguments or loaded from
    environment variables via :meth:`from_env`.
    """

    proxies: list[str] = []
    """Proxy URLs (e.g. ``http://user:pass@host:port``). Empty list = direct connection."""

    search_url_template: str = "https://duckduckgo.com/?q={query}"
    """URL template with a ``{query}`` placeholder.

    The default targets DuckDuckGo's JS-rendered search page, which is the right
    choice when ``use_browser=True``.  Switch to
    ``https://html.duckduckgo.com/html/?q={query}`` (or set ``SERP_SEARCH_URL``)
    when running in HTTP-only mode (``use_browser=False``)."""

    use_browser: bool = True
    """Launch a headless browser (Playwright) to fetch the SERP page.
    Set to ``False`` to use a plain HTTP GET instead."""

    headless: bool = True
    """Whether to run the browser in headless mode (only used when ``use_browser=True``)."""

    timeout_ms: int = 30_000
    """Page-load / HTTP-read timeout in milliseconds."""

    @classmethod
    def from_env(cls) -> SerpConfig:
        """Build a :class:`SerpConfig` from environment variables.

        Environment variables:
            SERP_PROXIES: Comma-separated proxy URLs. Omit or leave empty for direct connection.
            SERP_SEARCH_URL: URL template with a ``{query}`` placeholder (default: DuckDuckGo JS search).
            SERP_USE_BROWSER: ``"false"`` to use plain HTTP GET instead of Playwright (default ``"true"``).
            SERP_HEADLESS: ``"false"`` disables headless mode (default ``"true"``).
            SERP_TIMEOUT_MS: Page-load / HTTP-read timeout in ms (default ``"30000"``).
        """
        raw_proxies = os.environ.get("SERP_PROXIES", "")
        proxies = [p.strip() for p in raw_proxies.split(",") if p.strip()]
        search_url_template = os.environ.get(
            "SERP_SEARCH_URL", "https://duckduckgo.com/?q={query}"
        )
        use_browser_str = os.environ.get("SERP_USE_BROWSER", "true").lower()
        use_browser = use_browser_str not in {"false", "0", "no"}
        headless_str = os.environ.get("SERP_HEADLESS", "true").lower()
        headless = headless_str not in {"false", "0", "no"}
        timeout_ms = int(os.environ.get("SERP_TIMEOUT_MS", "30000"))
        return cls(
            proxies=proxies,
            search_url_template=search_url_template,
            use_browser=use_browser,
            headless=headless,
            timeout_ms=timeout_ms,
        )
