"""Browser fingerprinting — UA profiles with sec-ch-ua metadata and human-like timing."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class UaProfile:
    """Full browser identity bundle used to build a convincing browser context."""

    ua: str
    # sec-ch-ua and sec-ch-ua-platform are None for Firefox/Safari (they don't send these headers)
    sec_ch_ua: str | None
    sec_ch_ua_mobile: str
    sec_ch_ua_platform: str | None
    platform: str  # navigator.platform override value


UA_PROFILES: list[UaProfile] = [
    # Chrome 135 — Windows
    UaProfile(
        ua=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
        platform="Win32",
    ),
    # Chrome 136 — macOS
    UaProfile(
        ua=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.7103.49 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="136", "Not-A.Brand";v="8", "Chromium";v="136"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"macOS"',
        platform="MacIntel",
    ),
    # Chrome 135 — Linux
    UaProfile(
        ua=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Linux"',
        platform="Linux x86_64",
    ),
    # Chrome 134 — Windows (slightly older, realistic spread)
    UaProfile(
        ua=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.6998.165 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="134", "Not-A.Brand";v="8", "Chromium";v="134"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
        platform="Win32",
    ),
    # Chrome 136 — Windows
    UaProfile(
        ua=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.7103.25 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="136", "Not-A.Brand";v="8", "Chromium";v="136"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
        platform="Win32",
    ),
    # Chrome 135 — macOS
    UaProfile(
        ua=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.7149.103 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"macOS"',
        platform="MacIntel",
    ),
    # Firefox 137 — Windows
    UaProfile(
        ua=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) "
            "Gecko/20100101 Firefox/137.0"
        ),
        sec_ch_ua=None,
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=None,
        platform="Win32",
    ),
    # Firefox 136 — macOS
    UaProfile(
        ua=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:136.0) "
            "Gecko/20100101 Firefox/136.0"
        ),
        sec_ch_ua=None,
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=None,
        platform="MacIntel",
    ),
    # Firefox 137 — Linux
    UaProfile(
        ua=(
            "Mozilla/5.0 (X11; Linux x86_64; rv:137.0) "
            "Gecko/20100101 Firefox/137.0"
        ),
        sec_ch_ua=None,
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=None,
        platform="Linux x86_64",
    ),
    # Firefox 135 — Linux
    UaProfile(
        ua=(
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:135.0) "
            "Gecko/20100101 Firefox/135.0"
        ),
        sec_ch_ua=None,
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=None,
        platform="Linux x86_64",
    ),
    # Safari 18 — macOS Sequoia
    UaProfile(
        ua=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_4_1) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.4 Safari/605.1.15"
        ),
        sec_ch_ua=None,
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=None,
        platform="MacIntel",
    ),
    # Safari 18 — macOS Sonoma
    UaProfile(
        ua=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_5) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.3 Safari/605.1.15"
        ),
        sec_ch_ua=None,
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=None,
        platform="MacIntel",
    ),
    # Safari 17 — macOS Monterey
    UaProfile(
        ua=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7_4) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.6 Safari/605.1.15"
        ),
        sec_ch_ua=None,
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=None,
        platform="MacIntel",
    ),
    # Edge 135 — Windows
    UaProfile(
        ua=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
        ),
        sec_ch_ua='"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
        platform="Win32",
    ),
    # Edge 134 — Windows
    UaProfile(
        ua=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
        ),
        sec_ch_ua='"Microsoft Edge";v="134", "Not-A.Brand";v="8", "Chromium";v="134"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
        platform="Win32",
    ),
]

# UA_POOL is a flat string list kept for backward-compatibility.
UA_POOL: list[str] = [p.ua for p in UA_PROFILES]

# Common desktop viewport sizes drawn from real user traffic distributions.
VIEWPORT_POOL: list[dict[str, int]] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 1600, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 1920, "height": 1200},
]


def random_ua_profile() -> UaProfile:
    """Return a random :class:`UaProfile` from the pool."""
    return random.choice(UA_PROFILES)


def random_user_agent() -> str:
    """Return a random user-agent string drawn from :data:`UA_POOL`."""
    return random_ua_profile().ua


def random_viewport() -> dict[str, int]:
    """Return a copy of a random viewport size from :data:`VIEWPORT_POOL`."""
    return dict(random.choice(VIEWPORT_POOL))


async def human_delay() -> None:
    """Sleep for a randomized human-like delay between 8.0 and 15.0 seconds."""
    await asyncio.sleep(random.uniform(8.0, 15.0))
