"""CLI entry point: python -m serp_agent <query>"""

from __future__ import annotations

import asyncio
import sys

from serp_agent.agent import SerpAgent
from serp_agent.config import SerpConfig


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m serp_agent <query>")
        sys.exit(1)
    config = SerpConfig.from_env()
    agent = SerpAgent(config)
    html = asyncio.run(agent.search(sys.argv[1]))
    print(html[:500])


if __name__ == "__main__":
    main()
