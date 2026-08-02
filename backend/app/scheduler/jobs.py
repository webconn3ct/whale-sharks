import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import Settings
from app.core.scan_service import run_scan
from app.db.repository import get_last_completed_scan_at
from app.db.session import get_session
from app.integrations.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)

SCAN_JOB_ID = "whale_scan"

EASTERN = ZoneInfo("America/New_York")
# Sized to land close to "3 scans/hour" on average: a check lands within
# CHECK_INTERVAL of crossing this staleness age, so worst case is roughly
# STALENESS + CHECK_INTERVAL between scans.
STALENESS = timedelta(minutes=17)
CHECK_INTERVAL_MINUTES = 3


def in_active_window() -> bool:
    return 9 <= datetime.now(EASTERN).hour < 24


async def _scan_if_stale(client: PolymarketClient, settings: Settings) -> None:
    """This is now the ONLY scan-scheduling mechanism — a fixed-interval
    trigger (first CronTrigger(minute="0,30"), then a 30-min IntervalTrigger)
    kept silently failing to fire in production for reasons never visible
    without server log access, sometimes for 90+ minutes at a stretch, while
    THIS same staleness-check approach (originally just a watchdog backing
    up that trigger) has reliably self-healed every single time it's been
    tested against a real gap. Simpler and more proven beats a second,
    unreliable mechanism riding alongside it — checks every
    CHECK_INTERVAL_MINUTES; if nothing has completed in over STALENESS
    during the active window, runs one directly. Safe against overlapping
    with a manual admin rescan — run_scan's own scan-lock means whichever
    gets there first wins, the other just no-ops."""
    if not in_active_window():
        return

    async with get_session() as session:
        last_completed = await get_last_completed_scan_at(session)

    if last_completed is not None and datetime.now(UTC) - last_completed < STALENESS:
        return

    logger.warning("scan check: no completed scan since %s (or ever) — running one now", last_completed)
    await run_scan(client, settings)


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
        _scan_if_stale,
        trigger=IntervalTrigger(minutes=CHECK_INTERVAL_MINUTES),
        args=[client, settings],
        id=SCAN_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_listener(_log_scheduler_event, EVENT_JOB_SUBMITTED | EVENT_JOB_MISSED | EVENT_JOB_ERROR)
    scheduler.start()
    logger.info(
        "scheduler started: staleness check every %dmin (fires if >%dmin since last scan), 9am-midnight America/New_York",
        CHECK_INTERVAL_MINUTES,
        STALENESS.total_seconds() // 60,
    )
    return scheduler
