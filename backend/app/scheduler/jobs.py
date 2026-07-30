import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings
from app.core.scan_service import run_scan
from app.integrations.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)

SCAN_JOB_ID = "whale_scan"


def start_scheduler(client: PolymarketClient, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scan,
        # Fixed wall-clock cadence (:00 and :30 every hour) rather than an
        # interval counted from process start, so scans land on a
        # predictable schedule. A manual admin rescan can still fire any
        # time in between — the scan-lock (try_acquire_scan_lock) already
        # makes concurrent scans safely no-op rather than collide, so the
        # scheduled run still happens on its normal cadence regardless.
        trigger=CronTrigger(minute="0,30"),
        args=[client, settings],
        id=SCAN_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("scheduler started: scan at :00 and :30 every hour")
    return scheduler
