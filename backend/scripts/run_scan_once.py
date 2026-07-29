"""Manually trigger one scan cycle — useful for local dev iteration and
post-deploy smoke tests. Usage: python -m scripts.run_scan_once
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.scan_service import run_scan
from app.db.session import dispose_engine, init_engine
from app.integrations.polymarket_client import PolymarketClient


async def main() -> None:
    configure_logging()
    settings = get_settings()
    init_engine(settings)
    client = PolymarketClient(settings)
    try:
        await run_scan(client, settings)
    finally:
        await client.aclose()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
