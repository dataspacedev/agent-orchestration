"""BrowserSession — Playwright async context manager with proxy and UA injection."""

from __future__ import annotations

import contextlib
from types import TracebackType
from typing import Any


class BrowserSession:
    """Async context manager that wraps a Playwright browser session.

    Launches a headless Chromium browser with the supplied proxy and
    user-agent, then tears it down cleanly on exit.

    Parameters
    ----------
    proxy_url:
        Full proxy URL, e.g. ``http://user:pass@host:3128``.
    user_agent:
        User-agent string injected into the browser context.
    headless:
        Whether to run the browser without a visible window.
    timeout_ms:
        Default page-load timeout in milliseconds.
    """

    def __init__(
        self,
        proxy_url: str,
        user_agent: str,
        headless: bool,
        timeout_ms: int,
    ) -> None:
        self._proxy_url = proxy_url
        self._user_agent = user_agent
        self._headless = headless
        self._timeout_ms = timeout_ms

        # Typed as Any — Playwright types are only available at runtime
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def __aenter__(self) -> BrowserSession:
        """Launch browser, create context and page; return self."""
        from playwright.async_api import async_playwright  # local import

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            proxy={"server": self._proxy_url},
        )
        self._context = await self._browser.new_context(user_agent=self._user_agent)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self._timeout_ms)  # synchronous setter
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Tear down page, context, browser, and Playwright (best-effort)."""
        for obj, method in [
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright, "stop"),
        ]:
            if obj is not None:
                with contextlib.suppress(Exception):
                    await getattr(obj, method)()

    async def fetch(self, url: str) -> str:
        """Navigate to *url* and return the fully rendered HTML content.

        Parameters
        ----------
        url:
            Absolute URL to load.

        Returns
        -------
        str
            HTML string after JavaScript execution completes.
        """
        await self._page.goto(url, wait_until="networkidle")
        content: str = await self._page.content()
        return content
