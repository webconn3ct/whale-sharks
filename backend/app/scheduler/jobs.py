import logging

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings
from app.core.scan_service import run_scan
from app.integrations.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)

SCAN_JOB_ID = "whale_scan"


def _log_scheduler_event(event) -> None:
    # A scheduled tick silently vanishing (no scans row at all, no error in
    # the app's own logs) has happened before with no clear root cause —
    # these are APScheduler's OWN lifecycle events, a level below run_scan's
    # try/except, so a future occurrence leaves a trail even if run_scan
    # itself never got the chance to log anything.
    if event.code == EVENT_JOB_SUBMITTED:
        logger.info("scheduler: job %s submitted for run at %s", event.job_id, event.scheduled_run_times)
    elif event.code == EVENT_JOB_MISSED:
        logger.error("scheduler: job %s MISSED its scheduled run at %s", event.job_id, event.scheduled_run_time)
    elif event.code == EVENT_JOB_ERROR:
        logger.error("scheduler: job %s raised an uncaught exception: %s", event.job_id, event.exception)


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
        trigger=CronTrigger(minute="0,30", hour="9-23", timezone="America/New_York"),
        args=[client, settings],
        id=SCAN_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_listener(_log_scheduler_event, EVENT_JOB_SUBMITTED | EVENT_JOB_MISSED | EVENT_JOB_ERROR)
    scheduler.start()
    logger.info("scheduler started: scan at :00 and :30, 9am-midnight America/New_York")
    return scheduler
