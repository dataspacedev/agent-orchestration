"""SerpConfig — pydantic-validated settings for the SERP scraping agent."""

from __future__ import annotations

import os

from pydantic import BaseModel, field_validator


class SerpConfig(BaseModel):
    """Configuration for the SERP scraping agent.

    All fields can be supplied directly as keyword arguments or loaded from
    environment variables via :meth:`from_env`.
    """

    proxies: list[str]
    """One or more proxy URLs (e.g. ``http://user:pass@host:port``). Required."""

    search_url_template: str = "https://www.google.com/search?q={query}"
    """URL template with a ``{query}`` placeholder."""

    headless: bool = True
    """Whether to run the browser in headless mode."""

    timeout_ms: int = 30_000
    """Page-load timeout in milliseconds."""

    @field_validator("proxies")
    @classmethod
    def proxies_not_empty(cls, v: list[str]) -> list[str]:
        """Ensure the proxy list contains at least one entry."""
        if not v:
            raise ValueError("proxies must contain at least one entry")
        return v

    @classmethod
    def from_env(cls) -> SerpConfig:
        """Build a :class:`SerpConfig` from environment variables.

        Environment variables:
            SERP_PROXIES: Comma-separated list of proxy URLs (required).
            SERP_HEADLESS: ``"false"`` disables headless mode (default ``"true"``).
            SERP_TIMEOUT_MS: Page-load timeout in ms (default ``"30000"``).
        """
        raw_proxies = os.environ.get("SERP_PROXIES", "")
        proxies = [p.strip() for p in raw_proxies.split(",") if p.strip()]
        headless_str = os.environ.get("SERP_HEADLESS", "true").lower()
        headless = headless_str not in {"false", "0", "no"}
        timeout_ms = int(os.environ.get("SERP_TIMEOUT_MS", "30000"))
        return cls(proxies=proxies, headless=headless, timeout_ms=timeout_ms)
