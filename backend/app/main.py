import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import admin, auth, bot, chat, consensus, cron, health, highlights, summary, teaser
from app.config import get_settings
from app.core import cache as cache_module
from app.core.logging import configure_logging
from app.core.scan_service import run_scan
from app.db import repository
from app.db.session import dispose_engine, get_session, init_engine
from app.integrations.polymarket_client import PolymarketClient
from app.scheduler.jobs import start_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    init_engine(settings)

    client = PolymarketClient(settings)
    app.state.client = client

    # No try/except here used to mean a slow/unresponsive DB at exactly the
    # moment the process boots (observed happening for real — see the same
    # DB behind scan failures) took down the ENTIRE app, not just scans:
    # this raises -> FastAPI startup fails -> Render restarts -> same
    # unguarded call runs again -> crash-loops until a boot attempt gets
    # lucky with DB timing. Degrade to an empty cache instead — the
    # scheduler's own catch-up scan (below) retries this shortly after, and
    # the site stays up and serving (readable via /api/health) the whole time.
    snapshot = None
    try:
        async with get_session() as session:
            snapshot = await repository.load_latest_snapshot(session)
    except Exception:
        logger.exception("failed to load latest scan at startup — starting with an empty cache")
    if snapshot is not None:
        cache_module.cache.refresh(snapshot)
        logger.info("cache warmed from scan %s (completed %s)", snapshot.scan_id, snapshot.last_refresh_at)
    else:
        logger.warning("no completed scan in database yet — cache will be empty until the first scan finishes")

    scheduler = start_scheduler(client, settings)
    app.state.scheduler = scheduler

    # Only catch up with an out-of-band scan if the cache is empty or the
    # last-good scan is stale — NOT unconditionally on every startup. This used
    # to fire a full scan on every process restart (deploys, platform-initiated
    # restarts), which produced off-boundary scans that drifted the cadence away
    # from the :00/:30 cron schedule and could collide with a cron-triggered run
    # in flight. The cron job will pick up the next tick on its own otherwise.
    STARTUP_SCAN_STALENESS = timedelta(minutes=20)
    needs_catchup_scan = snapshot is None or (
        snapshot.last_refresh_at is not None and datetime.now(UTC) - snapshot.last_refresh_at > STARTUP_SCAN_STALENESS
    )
    initial_scan_task = asyncio.create_task(run_scan(client, settings)) if needs_catchup_scan else None
    if not needs_catchup_scan:
        logger.info("cache is fresh enough (last refresh %s) — skipping startup catch-up scan", snapshot.last_refresh_at)

    yield

    if initial_scan_task is not None:
        initial_scan_task.cancel()
    scheduler.shutdown(wait=False)
    await client.aclose()
    await dispose_engine()


app = FastAPI(title="Whale Sharks API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,  # auth relies on httpOnly cookies, not headers
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
# /api/consensus rows embed full holder detail, so unfiltered payloads can run
# to several hundred KB — cheap to compress, no reason not to.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(health.router, prefix="/api")
app.include_router(summary.router, prefix="/api")
app.include_router(consensus.router, prefix="/api")
app.include_router(highlights.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(bot.router, prefix="/api")
app.include_router(teaser.router, prefix="/api")
app.include_router(cron.router, prefix="/api")
