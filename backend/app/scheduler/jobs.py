import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.core.scan_service import run_scan
from app.integrations.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)

SCAN_JOB_ID = "whale_scan"


def start_scheduler(client: PolymarketClient, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scan,
        trigger="interval",
        minutes=settings.scan_interval_minutes,
        args=[client, settings],
        id=SCAN_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("scheduler started: scan every %s minutes", settings.scan_interval_minutes)
    return scheduler
