import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import admin, auth, bot, chat, consensus, health, highlights, summary
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

    async with get_session() as session:
        snapshot = await repository.load_latest_snapshot(session)
    if snapshot is not None:
        cache_module.cache.refresh(snapshot)
        logger.info("cache warmed from scan %s (completed %s)", snapshot.scan_id, snapshot.last_refresh_at)
    else:
        logger.warning("no completed scan in database yet — cache will be empty until the first scan finishes")

    scheduler = start_scheduler(client, settings)
    app.state.scheduler = scheduler

    # Don't block startup on a full scan — kick it off in the background. If the
    # cache is still empty, routes return 503 until this completes.
    initial_scan_task = asyncio.create_task(run_scan(client, settings))

    yield

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
