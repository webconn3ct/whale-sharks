from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import (
    BotPositionOut,
    BotRecalibrationOut,
    BotStateOut,
    ConsensusSnapshot,
    PaginatedBotPositionsOut,
    variant_key,
)
from app.core.consensus_engine import CANONICAL_TOP_N, Variant
from app.db import repository
from app.db.session import get_session

router = APIRouter(prefix="/bot", dependencies=[Depends(require_visitor)])


@router.get("/state", response_model=BotStateOut)
async def get_bot_state(snapshot: ConsensusSnapshot = Depends(get_ready_snapshot)) -> BotStateOut:
    rows_by_key = {
        (r.condition_id, r.outcome_index): r for r in snapshot.variants.get(variant_key(Variant.COMBINED, CANONICAL_TOP_N), [])
    }

    async with get_session() as session:
        state = await repository.get_or_create_bot_state(session)
        open_positions = await repository.get_open_bot_positions(session)
        await session.commit()

    open_value = 0.0
    for p in open_positions:
        row = rows_by_key.get((p.condition_id, p.outcome_index))
        price = row.current_price if row else float(p.entry_price)
        open_value += float(p.shares) * price

    cash = float(state.cash_balance)
    starting = float(state.starting_balance)
    total_value = cash + open_value

    return BotStateOut(
        cash_balance=cash,
        starting_balance=starting,
        open_positions_value=open_value,
        total_value=total_value,
        percent_return=(total_value - starting) / starting if starting else 0.0,
        open_positions_count=len(open_positions),
        entry_min_whales=int(state.entry_min_whales),
        entry_score_threshold=float(state.entry_score_threshold),
        last_recalibrated_at=state.last_recalibrated_at,
    )


BOT_POSITIONS_PAGE_SIZE = 10


@router.get("/positions", response_model=PaginatedBotPositionsOut)
async def list_bot_positions(
    snapshot: ConsensusSnapshot = Depends(get_ready_snapshot),
    status: Literal["open", "closed", "all"] = Query(default="all"),
    timeframe: Literal["day", "week", "all_time"] = Query(default="day"),
    page: int = Query(default=1, ge=1),
) -> PaginatedBotPositionsOut:
    rows_by_key = {
        (r.condition_id, r.outcome_index): r for r in snapshot.variants.get(variant_key(Variant.COMBINED, CANONICAL_TOP_N), [])
    }

    async with get_session() as session:
        positions, total = await repository.list_bot_positions_page(
            session, None if status == "all" else status, timeframe, page, BOT_POSITIONS_PAGE_SIZE
        )

    out = []
    for p in positions:
        current_price = None
        if p.status.value == "open":
            row = rows_by_key.get((p.condition_id, p.outcome_index))
            current_price = row.current_price if row else float(p.entry_price)
        out.append(
            BotPositionOut(
                id=p.id,
                condition_id=p.condition_id,
                outcome_index=p.outcome_index,
                outcome_label=p.outcome_label,
                market_title=p.market_title,
                category=p.category,
                status=p.status.value,
                stake=float(p.stake),
                shares=float(p.shares),
                entry_price=float(p.entry_price),
                entry_at=p.entry_at,
                entry_consensus_score=float(p.entry_consensus_score),
                entry_whale_count=p.entry_whale_count,
                entry_reasoning=p.entry_reasoning,
                current_price=current_price,
                exit_price=float(p.exit_price) if p.exit_price is not None else None,
                exit_at=p.exit_at,
                exit_reason=p.exit_reason.value if p.exit_reason else None,
                realized_pnl=float(p.realized_pnl) if p.realized_pnl is not None else None,
            )
        )
    total_pages = max(1, (total + BOT_POSITIONS_PAGE_SIZE - 1) // BOT_POSITIONS_PAGE_SIZE)
    return PaginatedBotPositionsOut(items=out, page=page, page_size=BOT_POSITIONS_PAGE_SIZE, total_items=total, total_pages=total_pages)


@router.get("/recalibrations", response_model=list[BotRecalibrationOut])
async def list_bot_recalibrations(limit: int = Query(default=20, ge=1, le=100)) -> list[BotRecalibrationOut]:
    async with get_session() as session:
        rows = await repository.list_bot_recalibrations(session, limit)
    return [
        BotRecalibrationOut(at=r.at, reasoning=r.reasoning, old_thresholds=r.old_thresholds, new_thresholds=r.new_thresholds)
        for r in rows
    ]
