import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import Settings
from app.core.scan_service import run_scan
from app.db.repository import get_last_completed_scan_at
from app.db.session import get_session
from app.integrations.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)

SCAN_JOB_ID = "whale_scan"
WATCHDOG_JOB_ID = "whale_scan_watchdog"

EASTERN = ZoneInfo("America/New_York")
# Half again the normal 30-min cadence — enough slack that a scan simply
# running a bit long never trips this, but short enough that any repeat of
# the cron job silently going quiet self-heals within minutes, not hours.
WATCHDOG_STALENESS = timedelta(minutes=45)


async def _scan_watchdog(client: PolymarketClient, settings: Settings) -> None:
    """Independent of the main :00/:30 cron job — a scan cycle silently not
    firing (as happened once with no error anywhere to explain it) matters
    more than landing on a clean half-hour boundary. Checks every 5 minutes;
    if nothing has completed in a while during the active window, runs one
    directly. run_scan's own scan-lock makes this safe to overlap with the
    cron job — whichever gets there first just wins, the other no-ops."""
    now_eastern = datetime.now(EASTERN)
    if not (9 <= now_eastern.hour < 24):
        return

    async with get_session() as session:
        last_completed = await get_last_completed_scan_at(session)

    if last_completed is not None and datetime.now(UTC) - last_completed < WATCHDOG_STALENESS:
        return

    logger.warning(
        "scan watchdog: no completed scan since %s (or ever) — running one now", last_completed
    )
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
    scheduler.add_job(
        _scan_watchdog,
        trigger=IntervalTrigger(minutes=5),
        args=[client, settings],
        id=WATCHDOG_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_listener(_log_scheduler_event, EVENT_JOB_SUBMITTED | EVENT_JOB_MISSED | EVENT_JOB_ERROR)
    scheduler.start()
    logger.info("scheduler started: scan at :00 and :30, 9am-midnight America/New_York (watchdog every 5min)")
    return scheduler
