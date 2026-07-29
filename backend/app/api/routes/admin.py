from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.config import Settings, get_settings
from app.core.auth import hash_secret
from app.core.scan_service import run_scan
from app.db import repository
from app.db.session import get_session

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


# ---- operational controls -------------------------------------------------


class ScoringWeightsOut(BaseModel):
    value_normalizer: float
    max_value_boost: float


class ScoringWeightsIn(BaseModel):
    value_normalizer: float = Field(gt=0, le=20)
    max_value_boost: float = Field(gt=0, le=5)


@router.get("/config", response_model=ScoringWeightsOut)
async def get_config():
    async with get_session() as session:
        config = await repository.get_app_config(session)
    if config is None:
        raise HTTPException(status_code=500, detail="App config not initialized")
    return ScoringWeightsOut(value_normalizer=float(config.value_normalizer), max_value_boost=float(config.max_value_boost))


@router.put("/config", response_model=ScoringWeightsOut)
async def update_config(body: ScoringWeightsIn):
    async with get_session() as session:
        await repository.update_app_config(
            session, value_normalizer=body.value_normalizer, max_value_boost=body.max_value_boost
        )
    return ScoringWeightsOut(value_normalizer=body.value_normalizer, max_value_boost=body.max_value_boost)


class ScanOut(BaseModel):
    id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    traders_count: int
    positions_count: int
    total_value: float
    error: str | None


@router.get("/scans", response_model=list[ScanOut])
async def list_scans():
    async with get_session() as session:
        scans = await repository.list_recent_scans(session, limit=20)
    return [
        ScanOut(
            id=s.id,
            started_at=s.started_at,
            completed_at=s.completed_at,
            status=s.status.value,
            traders_count=s.traders_count,
            positions_count=s.positions_count,
            total_value=float(s.total_value),
            error=s.error,
        )
        for s in scans
    ]


@router.post("/rescan")
async def trigger_rescan(request: Request, background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings)):
    client = request.app.state.client
    background_tasks.add_task(run_scan, client, settings)
    return {"ok": True, "detail": "Scan started in the background — check /api/admin/scans shortly"}


# ---- KrillBot kill switch -----------------------------------------------------


class BotPauseStateOut(BaseModel):
    entries_paused: bool


@router.get("/bot/pause-state", response_model=BotPauseStateOut)
async def get_bot_pause_state():
    async with get_session() as session:
        state = await repository.get_or_create_bot_state(session)
    return BotPauseStateOut(entries_paused=state.entries_paused)


@router.post("/bot/pause", response_model=BotPauseStateOut)
async def pause_bot_entries():
    async with get_session() as session:
        await repository.update_bot_state(session, entries_paused=True)
        await session.commit()
    return BotPauseStateOut(entries_paused=True)


@router.post("/bot/resume", response_model=BotPauseStateOut)
async def resume_bot_entries():
    async with get_session() as session:
        await repository.update_bot_state(session, entries_paused=False)
        await session.commit()
    return BotPauseStateOut(entries_paused=False)


# ---- login tracking ---------------------------------------------------------


class LoginStatsOut(BaseModel):
    total_logins: int
    unique_visitors: int
    logins_last_24h: int
    unique_visitors_last_24h: int


@router.get("/login-stats", response_model=LoginStatsOut)
async def get_login_stats():
    async with get_session() as session:
        stats = await repository.get_login_stats(session)
    return LoginStatsOut(**stats)


# ---- notifications: large single-whale trades --------------------------------


class WhaleAlertOut(BaseModel):
    id: int
    wallet_address: str
    username: str | None
    condition_id: str
    outcome_label: str
    market_title: str
    position_value: float
    detected_at: datetime
    acknowledged: bool


@router.get("/whale-alerts", response_model=list[WhaleAlertOut])
async def get_whale_alerts(limit: int = 50):
    async with get_session() as session:
        alerts = await repository.list_whale_alerts(session, limit=limit)
    return [
        WhaleAlertOut(
            id=a.id,
            wallet_address=a.wallet_address,
            username=a.username,
            condition_id=a.condition_id,
            outcome_label=a.outcome_label,
            market_title=a.market_title,
            position_value=float(a.position_value),
            detected_at=a.detected_at,
            acknowledged=a.acknowledged,
        )
        for a in alerts
    ]


@router.get("/whale-alerts/unacknowledged-count")
async def get_unacknowledged_whale_alert_count():
    async with get_session() as session:
        count = await repository.count_unacknowledged_whale_alerts(session)
    return {"count": count}


@router.post("/whale-alerts/{alert_id}/acknowledge")
async def acknowledge_whale_alert(alert_id: int):
    async with get_session() as session:
        await repository.acknowledge_whale_alert(session, alert_id)
    return {"ok": True}


@router.post("/whale-alerts/acknowledge-all")
async def acknowledge_all_whale_alerts():
    async with get_session() as session:
        await repository.acknowledge_all_whale_alerts(session)
    return {"ok": True}


# ---- content moderation -----------------------------------------------------


class ExcludeMarketIn(BaseModel):
    condition_id: str
    reason: str | None = None


class ExcludedMarketOut(BaseModel):
    condition_id: str
    title: str | None
    reason: str | None
    excluded_at: datetime


class ExcludeTraderIn(BaseModel):
    wallet_address: str
    reason: str | None = None


class ExcludedTraderOut(BaseModel):
    wallet_address: str
    username: str | None
    reason: str | None
    excluded_at: datetime


@router.get("/moderation/markets", response_model=list[ExcludedMarketOut])
async def get_excluded_markets():
    async with get_session() as session:
        rows = await repository.list_excluded_markets(session)
    return [ExcludedMarketOut(**r) for r in rows]


@router.post("/moderation/markets", response_model=ExcludedMarketOut)
async def exclude_market(body: ExcludeMarketIn):
    async with get_session() as session:
        await repository.add_excluded_market(session, body.condition_id, body.reason)
        rows = await repository.list_excluded_markets(session)
    match = next((r for r in rows if r["condition_id"] == body.condition_id), None)
    return ExcludedMarketOut(**match)


@router.delete("/moderation/markets/{condition_id}")
async def unexclude_market(condition_id: str):
    async with get_session() as session:
        await repository.remove_excluded_market(session, condition_id)
    return {"ok": True}


@router.get("/moderation/traders", response_model=list[ExcludedTraderOut])
async def get_excluded_traders():
    async with get_session() as session:
        rows = await repository.list_excluded_traders(session)
    return [ExcludedTraderOut(**r) for r in rows]


@router.post("/moderation/traders", response_model=ExcludedTraderOut)
async def exclude_trader(body: ExcludeTraderIn):
    wallet = body.wallet_address.lower()
    async with get_session() as session:
        await repository.add_excluded_trader(session, wallet, body.reason)
        rows = await repository.list_excluded_traders(session)
    match = next((r for r in rows if r["wallet_address"] == wallet), None)
    return ExcludedTraderOut(**match)


@router.delete("/moderation/traders/{wallet_address}")
async def unexclude_trader(wallet_address: str):
    async with get_session() as session:
        await repository.remove_excluded_trader(session, wallet_address.lower())
    return {"ok": True}


# ---- access management -------------------------------------------------------


class CreateAccessCodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=4, max_length=64)


class AccessCodeOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    active: bool


class ChangeAdminPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/access-codes", response_model=list[AccessCodeOut])
async def get_access_codes():
    async with get_session() as session:
        codes = await repository.list_access_codes(session)
    return [AccessCodeOut(id=c.id, name=c.name, created_at=c.created_at, active=c.active) for c in codes]


@router.post("/access-codes", response_model=AccessCodeOut)
async def add_access_code(body: CreateAccessCodeIn):
    async with get_session() as session:
        code = await repository.create_access_code(session, body.name.strip(), body.code)
    return AccessCodeOut(id=code.id, name=code.name, created_at=code.created_at, active=code.active)


@router.post("/access-codes/{code_id}/revoke")
async def revoke_access_code(code_id: int):
    async with get_session() as session:
        await repository.revoke_access_code(session, code_id)
    return {"ok": True}


@router.post("/admin-password")
async def change_admin_password(body: ChangeAdminPasswordIn):
    async with get_session() as session:
        await repository.update_app_config(session, admin_password_hash=hash_secret(body.new_password))
    return {"ok": True}


# ---- KrillBot admin-help escalations ------------------------------------------


class SupportRequestOut(BaseModel):
    id: int
    summary: str
    contact: str
    created_at: datetime
    acknowledged: bool


@router.get("/support-requests", response_model=list[SupportRequestOut])
async def get_support_requests():
    async with get_session() as session:
        requests = await repository.list_support_requests(session)
    return [
        SupportRequestOut(id=r.id, summary=r.summary, contact=r.contact, created_at=r.created_at, acknowledged=r.acknowledged)
        for r in requests
    ]


@router.post("/support-requests/{request_id}/acknowledge")
async def acknowledge_support_request(request_id: int):
    async with get_session() as session:
        await repository.acknowledge_support_request(session, request_id)
    return {"ok": True}
