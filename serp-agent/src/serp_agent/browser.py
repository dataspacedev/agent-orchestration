"""BrowserSession — Playwright async context manager with stealth patches."""

from __future__ import annotations

import asyncio
import contextlib
import random
from types import TracebackType
from typing import Any

from serp_agent.fingerprint import UaProfile

# Injected into every new page before any scripts run.
# Patches the properties that bot-detection scripts probe most aggressively.
_STEALTH_JS = """\
(() => {
  // Remove the most obvious automation tell-tale
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined, configurable: true});

  // Headless Chrome lacks window.chrome — real Chrome always has it
  if (!window.chrome) window.chrome = {runtime: {}};

  // Headless Chrome reports zero plugins; spoof a realistic set
  const _pluginData = [
    {name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
    {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
    {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: ''},
    {name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: ''},
    {name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: ''},
  ];
  Object.defineProperty(navigator, 'plugins', {
    get: () => {
      const a = [..._pluginData];
      a.refresh = () => {};
      a.item = i => a[i] ?? null;
      a.namedItem = n => a.find(p => p.name === n) ?? null;
      return a;
    },
    configurable: true,
  });

  // Headless Chrome returns [] for languages; real browsers return at least ['en-US', 'en']
  Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en'], configurable: true});

  // Headless Chrome returns 'denied' for notification permission checks in a way that
  // differs from real Chrome — fix it to avoid tripping the permissions fingerprint
  try {
    if (navigator.permissions && navigator.permissions.query) {
      const _origQuery = navigator.permissions.query.bind(navigator.permissions);
      Object.defineProperty(navigator.permissions, 'query', {
        value: params =>
          params.name === 'notifications'
            ? Promise.resolve({state: Notification.permission, onchange: null})
            : _origQuery(params),
      });
    }
  } catch (_) {}

  // Realistic hardware values instead of headless defaults
  Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8, configurable: true});
  Object.defineProperty(navigator, 'deviceMemory', {get: () => 8, configurable: true});
})();
"""

# Chromium flags that suppress the automation indicator built into Chrome DevTools Protocol
_STEALTH_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]


async def _simulate_human(page: Any, viewport: dict[str, int]) -> None:
    """Move the mouse naturally and scroll down a bit to mimic a real user."""
    w, h = viewport["width"], viewport["height"]
    for _ in range(random.randint(2, 5)):
        await page.mouse.move(
            random.randint(50, w - 50),
            random.randint(50, h - 50),
            steps=random.randint(5, 12),
        )
        await asyncio.sleep(random.uniform(0.05, 0.18))
    await page.mouse.wheel(0, random.randint(80, 420))
    await asyncio.sleep(random.uniform(0.4, 1.2))


class BrowserSession:
    """Async context manager that wraps a stealth Playwright browser session.

    Launches a headless Chromium browser with proxy, UA, and a full suite of
    anti-detection patches, then tears it down cleanly on exit.

    Parameters
    ----------
    proxy_url:
        Full proxy URL, e.g. ``http://user:pass@host:3128``.
    ua_profile:
        Full UA identity bundle (UA string + sec-ch-ua metadata).
    viewport:
        Browser viewport dimensions, e.g. ``{"width": 1920, "height": 1080}``.
    headless:
        Whether to run the browser without a visible window.
    timeout_ms:
        Default page-load timeout in milliseconds.
    """

    def __init__(
        self,
        proxy_url: str | None,
        ua_profile: UaProfile,
        viewport: dict[str, int],
        headless: bool,
        timeout_ms: int,
    ) -> None:
        self._proxy_url = proxy_url
        self._ua_profile = ua_profile
        self._viewport = viewport
        self._headless = headless
        self._timeout_ms = timeout_ms

        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def __aenter__(self) -> BrowserSession:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self._headless,
            "args": _STEALTH_ARGS,
        }
        if self._proxy_url:
            launch_kwargs["proxy"] = {"server": self._proxy_url}

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        extra_headers: dict[str, str] = {"Accept-Language": "en-US,en;q=0.9"}
        if self._ua_profile.sec_ch_ua is not None:
            extra_headers["sec-ch-ua"] = self._ua_profile.sec_ch_ua
            extra_headers["sec-ch-ua-mobile"] = self._ua_profile.sec_ch_ua_mobile
            if self._ua_profile.sec_ch_ua_platform is not None:
                extra_headers["sec-ch-ua-platform"] = self._ua_profile.sec_ch_ua_platform

        self._context = await self._browser.new_context(
            user_agent=self._ua_profile.ua,
            viewport=self._viewport,
            extra_http_headers=extra_headers,
        )
        await self._context.add_init_script(_STEALTH_JS)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self._timeout_ms)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        for obj, method in [
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright, "stop"),
        ]:
            if obj is not None:
                with contextlib.suppress(Exception):
                    await getattr(obj, method)()

    async def fetch(self, url: str) -> str:
        """Navigate to *url*, simulate human interaction, and return rendered HTML.

        Parameters
        ----------
        url:
            Absolute URL to load.

        Returns
        -------
        str
            HTML string after JavaScript execution and human-like interaction.
        """
        await self._page.goto(url, wait_until="load")
        await _simulate_human(self._page, self._viewport)
        content: str = await self._page.content()
        return content
