import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

from app.config import Settings, get_settings
from app.core.scan_service import run_scan
from app.scheduler.jobs import in_active_window

logger = logging.getLogger(__name__)

# Deliberately NOT part of the visitor/admin cookie-auth system — an
# external cron service can't hold a browser session. Protected by a plain
# shared secret instead, checked with a constant-time comparison.
router = APIRouter()


@router.post("/cron/scan")
async def cron_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    x_cron_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    if not settings.cron_secret or not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not in_active_window():
        return {"ok": True, "skipped": "outside 9am-midnight America/New_York window"}

    client = request.app.state.client
    background_tasks.add_task(run_scan, client, settings)
    logger.info("cron trigger: scan started in the background")
    return {"ok": True, "detail": "Scan started in the background"}
