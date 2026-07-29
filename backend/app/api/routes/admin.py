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


class ChangeAccessCodeIn(BaseModel):
    new_code: str = Field(min_length=4, max_length=64)


class ChangeAdminPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/access-code")
async def change_access_code(body: ChangeAccessCodeIn):
    async with get_session() as session:
        await repository.update_app_config(session, access_code_hash=hash_secret(body.new_code))
    return {"ok": True}


@router.post("/admin-password")
async def change_admin_password(body: ChangeAdminPasswordIn):
    async with get_session() as session:
        await repository.update_app_config(session, admin_password_hash=hash_secret(body.new_password))
    return {"ok": True}
