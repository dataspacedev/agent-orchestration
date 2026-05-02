---
phase: quick-1
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - serp-agent/pyproject.toml
  - serp-agent/src/serp_agent/__init__.py
  - serp-agent/src/serp_agent/config.py
  - serp-agent/src/serp_agent/browser.py
  - serp-agent/src/serp_agent/proxy.py
  - serp-agent/src/serp_agent/agent.py
  - serp-agent/tests/__init__.py
  - serp-agent/tests/test_agent.py
autonomous: true
requirements: [SERP-01]

must_haves:
  truths:
    - "Running `python -m serp_agent --query 'openai'` fetches a SERP page without being blocked (returns HTML > 5KB)"
    - "Proxy rotation cycles through the configured pool; successive requests use different proxies"
    - "User-agent header differs across requests (drawn from randomized pool of 10+ real UA strings)"
    - "Each request waits a randomized human-like delay of 8-15 seconds before sending"
    - "Playwright headless browser renders JavaScript-heavy pages; raw HTML is returned after JS execution"
    - "Module is importable and passes ruff + mypy strict checks"
  artifacts:
    - path: "serp-agent/src/serp_agent/proxy.py"
      provides: "ProxyPool — round-robin rotation with health tracking"
      exports: ["ProxyPool"]
    - path: "serp-agent/src/serp_agent/browser.py"
      provides: "BrowserSession — Playwright async context manager with proxy + UA injection"
      exports: ["BrowserSession"]
    - path: "serp-agent/src/serp_agent/agent.py"
      provides: "SerpAgent — orchestrates pool, delays, browser fetch, returns HTML"
      exports: ["SerpAgent"]
    - path: "serp-agent/src/serp_agent/config.py"
      provides: "SerpConfig — pydantic-validated settings loaded from env / kwargs"
      exports: ["SerpConfig"]
  key_links:
    - from: "serp_agent/agent.py"
      to: "serp_agent/proxy.py"
      via: "ProxyPool.next() called before each page load"
    - from: "serp_agent/browser.py"
      to: "playwright.async_api"
      via: "async_playwright context manager with proxy dict"
    - from: "serp_agent/agent.py"
      to: "asyncio.sleep"
      via: "random.uniform(8, 15) delay before each fetch"
---

<objective>
Create `serp-agent/` — a self-contained Python package that scrapes SERP pages using Playwright with proxy rotation, user-agent randomization, and human-like delays.

Purpose: Standalone scraping module deployable as a CLI tool or importable library, following the same toolchain conventions (Python 3.13, hatchling, ruff, mypy strict, pytest-asyncio) used by the rest of this repo.
Output: Runnable package at `serp-agent/` with full test coverage of the three core behaviours (proxy rotation, UA randomization, delay range).
</objective>

<execution_context>
@/Users/justinbrewer/.claude/get-shit-done/workflows/execute-plan.md
@/Users/justinbrewer/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Package scaffold + proxy/UA/delay unit</name>
  <files>
    serp-agent/pyproject.toml,
    serp-agent/src/serp_agent/__init__.py,
    serp-agent/src/serp_agent/config.py,
    serp-agent/src/serp_agent/proxy.py,
    serp-agent/tests/__init__.py,
    serp-agent/tests/test_agent.py
  </files>
  <behavior>
    - ProxyPool([]) raises ValueError("proxy pool cannot be empty")
    - ProxyPool(["p1","p2","p3"]).next() cycles: p1, p2, p3, p1 (round-robin)
    - ProxyPool.mark_dead("p1") skips p1; if all dead raises RuntimeError
    - SerpConfig(proxies=["p1"]) — missing proxies field raises pydantic ValidationError
    - random_user_agent() returns a string from UA_POOL; called 50 times returns at least 5 distinct values
    - human_delay() (no arg) calls asyncio.sleep with a value in [8.0, 15.0]; mock sleep, assert bounds
  </behavior>
  <action>
    Create the package scaffold and pure-logic modules (no Playwright dependency yet):

    1. `serp-agent/pyproject.toml`:
       - name = "serp-agent", version = "0.1.0"
       - requires-python = ">=3.13"
       - dependencies: playwright>=1.44, pydantic>=2.9, anyio>=4.0
       - optional dev deps: pytest>=8, pytest-asyncio>=0.24, ruff, mypy
       - [tool.pytest.ini_options] asyncio_mode = "auto"
       - [tool.ruff] line-length = 100, target-version = "py313"
       - [tool.ruff.lint] select = ["E","F","I","UP","B","SIM"], ignore = ["B008"]
       - [tool.mypy] python_version="3.13", strict=true, ignore_missing_imports=true

    2. `serp-agent/src/serp_agent/__init__.py` — re-export SerpAgent, SerpConfig

    3. `serp-agent/src/serp_agent/config.py`:
       - `SerpConfig(BaseModel)`: proxies: list[str] (min_length=1), search_url_template: str = "https://www.google.com/search?q={query}", headless: bool = True, timeout_ms: int = 30_000
       - Class method `from_env()` reads SERP_PROXIES (comma-separated), SERP_HEADLESS, SERP_TIMEOUT_MS from os.environ

    4. `serp-agent/src/serp_agent/proxy.py`:
       - `ProxyPool`: `__init__(proxies: list[str])` — raises ValueError if empty; stores list + dead set; `_idx` counter
       - `next() -> str` — iterates round-robin skipping dead; raises RuntimeError if all dead
       - `mark_dead(proxy: str) -> None` — adds to dead set
       - `reset() -> None` — clears dead set

    5. Add `UA_POOL: list[str]` constant (15 real desktop Chrome/Firefox/Safari UAs from 2024) and `random_user_agent() -> str` (random.choice) to `proxy.py`

    6. Add `async def human_delay() -> None` to `proxy.py` — `await asyncio.sleep(random.uniform(8.0, 15.0))`

    7. `serp-agent/tests/test_agent.py` — write failing tests first (RED cycle per TDD), then implement above so tests pass (GREEN). Tests must cover all behavior items listed above; mock asyncio.sleep with pytest monkeypatch for delay bounds test.

    After implementation: `cd serp-agent && python -m pytest tests/ -x -q`
  </action>
  <verify>
    <automated>cd /Users/justinbrewer/Documents/repos/agent-orchestration/serp-agent && python -m pytest tests/ -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>All tests pass. `ruff check src/ tests/` and `mypy src/` both exit 0.</done>
</task>

<task type="auto">
  <name>Task 2: BrowserSession + SerpAgent wiring</name>
  <files>
    serp-agent/src/serp_agent/browser.py,
    serp-agent/src/serp_agent/agent.py
  </files>
  <action>
    Build the Playwright integration and the top-level agent that ties everything together.

    1. `serp-agent/src/serp_agent/browser.py`:
       - `class BrowserSession` — async context manager wrapping Playwright
       - `__init__(self, proxy_url: str, user_agent: str, headless: bool, timeout_ms: int)` — stores args
       - `async __aenter__` — launches `async_playwright()`, opens `chromium.launch(headless=headless, proxy={"server": proxy_url})`, creates `browser.new_context(user_agent=user_agent)`, creates `context.new_page()`, sets `page.set_default_timeout(timeout_ms)`, returns `self`; stores `_playwright`, `_browser`, `_context`, `_page` on instance
       - `async __aexit__` — closes `_context`, `_browser`, stops `_playwright`; swallows errors during teardown (best-effort)
       - `async def fetch(self, url: str) -> str` — `await self._page.goto(url, wait_until="networkidle")`, returns `await self._page.content()`

    2. `serp-agent/src/serp_agent/agent.py`:
       - `class SerpAgent`:
         - `__init__(self, config: SerpConfig)` — creates `ProxyPool(config.proxies)`
         - `async def search(self, query: str) -> str`:
           1. `await human_delay()`
           2. `proxy = self._pool.next()`
           3. `ua = random_user_agent()`
           4. Build URL: `config.search_url_template.format(query=urllib.parse.quote_plus(query))`
           5. Open `BrowserSession(proxy, ua, config.headless, config.timeout_ms)` as async context manager
           6. Call `session.fetch(url)`, return HTML string
           7. On `PlaywrightError` or `asyncio.TimeoutError`: call `self._pool.mark_dead(proxy)` and re-raise
       - `async def __main__` block at bottom of module: parse `sys.argv[1]` as query, load `SerpConfig.from_env()`, run `SerpAgent(config).search(query)`, print first 500 chars of HTML

    Coding rules:
    - Use `from __future__ import annotations` for forward refs
    - All public functions/classes must have docstrings
    - No `Any` type unless unavoidable; if needed add `# type: ignore[misc]` with comment
    - Line length 100 (ruff enforced)

    Do NOT run a live search during this task — Playwright + live proxies are not available in CI. Just ensure module imports cleanly.
  </action>
  <verify>
    <automated>cd /Users/justinbrewer/Documents/repos/agent-orchestration/serp-agent && python -c "from serp_agent import SerpAgent, SerpConfig; print('import ok')" 2>&1 && ruff check src/ && mypy src/ 2>&1 | tail -10</automated>
  </verify>
  <done>
    `from serp_agent import SerpAgent, SerpConfig` succeeds.
    `ruff check src/` exits 0.
    `mypy src/` exits 0 (or only emits notes, no errors).
    Module can be invoked: `python -m serp_agent.agent --help` (or with a query string) without crashing on import.
  </done>
</task>

</tasks>

<verification>
Run from `serp-agent/`:

```bash
# All unit tests pass
python -m pytest tests/ -x -q

# No lint errors
ruff check src/ tests/

# Strict type checking passes
mypy src/

# Module imports cleanly
python -c "from serp_agent import SerpAgent, SerpConfig; c = SerpConfig(proxies=['http://proxy:8080']); print(c)"
```
</verification>

<success_criteria>
- `serp-agent/` directory exists as a proper Python package with pyproject.toml
- All unit tests pass (proxy rotation, UA randomization, delay bounds)
- `ruff check` and `mypy --strict` both exit 0
- `SerpAgent`, `SerpConfig`, `ProxyPool`, `BrowserSession` are all importable from `serp_agent`
- `human_delay()` provably calls `asyncio.sleep` with a value in [8.0, 15.0]
- `ProxyPool` correctly cycles proxies round-robin and skips dead entries
</success_criteria>

<output>
After completion, create `.planning/quick/1-build-serp-scraping-agent-with-proxy-rot/1-SUMMARY.md`
</output>
