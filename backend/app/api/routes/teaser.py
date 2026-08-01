from fastapi import APIRouter, Depends

from app.api.deps import get_ready_snapshot
from app.api.schemas import ConsensusSnapshot, TeaserOut
from app.db import repository
from app.db.session import get_session

# No require_visitor dependency — deliberately public. Only ever returns
# aggregate counts/dollar totals and KrillBot's equity curve shape, never
# any specific market, pick, or trader identity, so there's nothing here
# an unauthenticated caller could act on.
router = APIRouter()


@router.get("/teaser", response_model=TeaserOut)
async def get_teaser(snapshot: ConsensusSnapshot = Depends(get_ready_snapshot)) -> TeaserOut:
    async with get_session() as session:
        state = await repository.get_or_create_bot_state(session)
        equity_curve = await repository.get_bot_equity_curve(session)

    starting = float(state.starting_balance)
    current = equity_curve[-1] if equity_curve else starting

    return TeaserOut(
        tracked_traders=snapshot.tracked_traders,
        total_whale_exposure=snapshot.total_whale_exposure,
        bot_return_pct=((current - starting) / starting * 100) if starting else 0.0,
        bot_equity_curve=equity_curve,
    )
