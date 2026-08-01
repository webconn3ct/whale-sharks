import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import ConsensusRowOut, ConsensusSnapshot, HolderOut, variant_key
from app.core.auth import hash_secret, verify_secret
from app.core.consensus_engine import (
    CANONICAL_TOP_N,
    TOP_N_OPTIONS,
    VARIANT_TO_TIMEFRAME,
    ConsensusGroup,
    Trader,
    TrackRecord,
    Variant,
    score_from_weight_and_value,
)
from app.db.models import (
    AccessCode,
    AppConfig,
    BotExitReason,
    BotPosition,
    BotPositionStatus,
    BotRecalibration,
    BotState,
    ConsensusPosition,
    ConsensusPositionTrader,
    DailyCatchPick,
    ExcludedMarket,
    ExcludedTrader,
    LoginEvent,
    Market,
    Scan,
    ScanStatus,
    Signup,
    SupportRequest,
    TraderLeaderboardRank,
    TraderTrackRecord,
    WhaleAlert,
)
from app.db.models import Trader as TraderModel
from app.integrations.polymarket_client import MarketMetadata

logger = logging.getLogger(__name__)

# Fixed key for pg_try_advisory_xact_lock — arbitrary but stable across the app.
SCAN_LOCK_KEY = 0x57484C53  # "WHLS"

# asyncpg caps a single query at 32767 bound parameters. With sizeThreshold=1 on
# /positions, a scan can produce tens of thousands of rows across ~100 traders,
# so bulk inserts are chunked well under that limit regardless of column count.
INSERT_CHUNK_SIZE = 1000


async def _bulk_insert(session: AsyncSession, table, rows: list[dict]) -> None:
    for i in range(0, len(rows), INSERT_CHUNK_SIZE):
        await session.execute(table.insert().values(rows[i : i + INSERT_CHUNK_SIZE]))


async def _bulk_insert_returning(session: AsyncSession, table, rows: list[dict], returning_col) -> list:
    ids = []
    for i in range(0, len(rows), INSERT_CHUNK_SIZE):
        result = await session.execute(
            table.insert().values(rows[i : i + INSERT_CHUNK_SIZE]).returning(returning_col)
        )
        ids.extend(row[0] for row in result.all())
    return ids


class ScanLockNotAcquired(Exception):
    """Another process is already writing a scan; caller should skip this cycle."""


async def create_running_scan(session: AsyncSession) -> int:
    scan = Scan(started_at=datetime.now(UTC), status=ScanStatus.RUNNING)
    session.add(scan)
    await session.flush()
    return scan.id


async def get_fresh_market_condition_ids(session: AsyncSession, condition_ids: list[str], ttl_hours: int) -> set[str]:
    if not condition_ids:
        return set()
    cutoff = datetime.now(UTC) - timedelta(hours=ttl_hours)
    rows = await session.execute(
        select(Market.condition_id).where(
            Market.condition_id.in_(condition_ids), Market.metadata_updated_at >= cutoff
        )
    )
    return {r[0] for r in rows}


async def get_fresh_track_record_wallets(session: AsyncSession, wallets: list[str], ttl_hours: int) -> set[str]:
    """Wallets whose cached track record is still within the TTL — callers
    should skip refetching /closed-positions for these."""
    if not wallets:
        return set()
    cutoff = datetime.now(UTC) - timedelta(hours=ttl_hours)
    rows = await session.execute(
        select(TraderModel.wallet_address)
        .join(TraderTrackRecord, TraderTrackRecord.trader_id == TraderModel.id)
        .where(TraderModel.wallet_address.in_(wallets), TraderTrackRecord.computed_at >= cutoff)
    )
    return {r[0] for r in rows}


async def upsert_track_records(
    session: AsyncSession, records: dict[str, TrackRecord], trader_ids: dict[str, int]
) -> None:
    if not records:
        return
    now = datetime.now(UTC)
    values = [
        {
            "trader_id": trader_ids[wallet],
            "win_rate": record.win_rate,
            "recent_form": record.recent_form,
            "sample_size": record.sample_size,
            "computed_at": now,
        }
        for wallet, record in records.items()
        if wallet in trader_ids
    ]
    stmt = pg_insert(TraderTrackRecord).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[TraderTrackRecord.trader_id],
        set_={
            "win_rate": stmt.excluded.win_rate,
            "recent_form": stmt.excluded.recent_form,
            "sample_size": stmt.excluded.sample_size,
            "computed_at": stmt.excluded.computed_at,
        },
    )
    await session.execute(stmt)


async def get_track_records_by_wallet(session: AsyncSession, wallets: list[str]) -> dict[str, TrackRecord]:
    """Load every current trader's cached track record (freshly-updated ones
    included, since upsert_track_records already committed by the time this
    is called) — used directly as build_consensus_groups' track_records arg."""
    if not wallets:
        return {}
    rows = await session.execute(
        select(TraderModel.wallet_address, TraderTrackRecord)
        .join(TraderTrackRecord, TraderTrackRecord.trader_id == TraderModel.id)
        .where(TraderModel.wallet_address.in_(wallets))
    )
    return {
        wallet: TrackRecord(win_rate=float(rec.win_rate), recent_form=float(rec.recent_form), sample_size=rec.sample_size)
        for wallet, rec in rows.all()
    }


async def upsert_markets(session: AsyncSession, metadata: dict[str, MarketMetadata]) -> None:
    if not metadata:
        return
    now = datetime.now(UTC)
    values = [
        {
            "condition_id": m.condition_id,
            "title": m.title,
            "slug": m.slug,
            "event_slug": m.event_slug,
            "category": m.category,
            "image_url": m.image_url,
            "end_date": parse_market_date(m.end_date),
            "active": m.active,
            "metadata_updated_at": now,
        }
        for m in metadata.values()
    ]
    for i in range(0, len(values), INSERT_CHUNK_SIZE):
        chunk = values[i : i + INSERT_CHUNK_SIZE]
        stmt = pg_insert(Market).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Market.condition_id],
            set_={
                "title": stmt.excluded.title,
                "slug": stmt.excluded.slug,
                "event_slug": stmt.excluded.event_slug,
                "category": stmt.excluded.category,
                "image_url": stmt.excluded.image_url,
                "end_date": stmt.excluded.end_date,
                "active": stmt.excluded.active,
                "metadata_updated_at": stmt.excluded.metadata_updated_at,
            },
        )
        await session.execute(stmt)


async def ensure_markets_exist_without_metadata(session: AsyncSession, condition_ids: list[str]) -> None:
    """Fallback for condition_ids we have positions for but couldn't enrich via
    Gamma (e.g. a transient failure) — insert a bare row so the FK is satisfiable."""
    if not condition_ids:
        return
    now = datetime.now(UTC)
    values = [{"condition_id": cid, "metadata_updated_at": now} for cid in condition_ids]
    for i in range(0, len(values), INSERT_CHUNK_SIZE):
        chunk = values[i : i + INSERT_CHUNK_SIZE]
        stmt = pg_insert(Market).values(chunk).on_conflict_do_nothing(index_elements=[Market.condition_id])
        await session.execute(stmt)


async def upsert_traders(session: AsyncSession, traders: dict[str, Trader]) -> dict[str, int]:
    if not traders:
        return {}
    now = datetime.now(UTC)
    values = [
        {
            "wallet_address": t.wallet,
            "username": t.username,
            "profile_image": t.profile_image,
            "x_username": t.x_username,
            "verified": t.verified,
            "first_seen_at": now,
        }
        for t in traders.values()
    ]
    stmt = pg_insert(TraderModel).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[TraderModel.wallet_address],
        set_={
            "username": stmt.excluded.username,
            "profile_image": stmt.excluded.profile_image,
            "x_username": stmt.excluded.x_username,
            "verified": stmt.excluded.verified,
        },
    ).returning(TraderModel.id, TraderModel.wallet_address)
    rows = await session.execute(stmt)
    return {wallet: trader_id for trader_id, wallet in rows.all()}


async def insert_leaderboard_ranks(
    session: AsyncSession, scan_id: int, traders: dict[str, Trader], trader_ids: dict[str, int]
) -> None:
    values = [
        {
            "scan_id": scan_id,
            "trader_id": trader_ids[trader.wallet],
            "timeframe": r.timeframe,
            "rank": r.rank,
            "pnl": r.pnl,
            "vol": r.vol,
        }
        for trader in traders.values()
        for r in trader.ranks
    ]
    await _bulk_insert(session, TraderLeaderboardRank.__table__, values)


async def insert_consensus_groups(
    session: AsyncSession,
    scan_id: int,
    variant: Variant,
    top_n: int,
    groups: list[ConsensusGroup],
    trader_ids: dict[str, int],
) -> None:
    if not groups:
        return
    position_values = [
        {
            "scan_id": scan_id,
            "variant": variant,
            "top_n": top_n,
            "condition_id": g.condition_id,
            "outcome_index": g.outcome_index,
            "outcome_label": g.outcome_label,
            "current_price": g.current_price,
            "whale_count": g.whale_count,
            "combined_value": g.combined_value,
            "consensus_score": g.consensus_score,
        }
        for g in groups
    ]
    position_ids = await _bulk_insert_returning(
        session, ConsensusPosition.__table__, position_values, ConsensusPosition.id
    )

    trader_rows = []
    for group, position_id in zip(groups, position_ids, strict=True):
        seen: set[str] = set()
        for holding in group.holdings:
            if holding.trader.wallet in seen:
                continue
            seen.add(holding.trader.wallet)
            best = holding.trader.best_rank()
            pos = holding.position
            trader_rows.append(
                {
                    "consensus_position_id": position_id,
                    "trader_id": trader_ids[holding.trader.wallet],
                    "best_timeframe": best.timeframe,
                    "best_rank": best.rank,
                    "position_value": pos.current_value,
                    "size": pos.size,
                    "avg_entry_price": pos.avg_price,
                    "current_price": pos.cur_price,
                    "cash_pnl": pos.cash_pnl,
                    "percent_pnl": pos.percent_pnl,
                    "trader_weight": holding.weight,
                    "hedge_opposing_value": holding.hedge_opposing_value,
                }
            )
    await _bulk_insert(session, ConsensusPositionTrader.__table__, trader_rows)


async def complete_scan(
    session: AsyncSession, scan_id: int, traders_count: int, positions_count: int, total_value: float
) -> None:
    await session.execute(
        Scan.__table__.update()
        .where(Scan.id == scan_id)
        .values(
            status=ScanStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            traders_count=traders_count,
            positions_count=positions_count,
            total_value=total_value,
        )
    )


async def try_acquire_scan_lock(session: AsyncSession) -> bool:
    """Non-blocking advisory lock held for the current transaction only — the
    safety net in case this ever runs with >1 worker/replica despite the
    documented single-instance constraint."""
    result = await session.execute(select(func.pg_try_advisory_xact_lock(SCAN_LOCK_KEY)))
    return bool(result.scalar())


async def prune_old_scans(session: AsyncSession, retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(
        delete(Scan).where(Scan.status != ScanStatus.RUNNING, Scan.started_at < cutoff)
    )
    await session.commit()
    return result.rowcount or 0


def _qualifies_for_cut(ranks: dict[str, int], variant: Variant, top_n: int) -> bool:
    timeframe = VARIANT_TO_TIMEFRAME[variant]
    if timeframe is None:  # combined: qualifies if top_n on ANY leaderboard
        return any(rank <= top_n for rank in ranks.values())
    rank = ranks.get(timeframe.value)
    return rank is not None and rank <= top_n


def _holder_out(t, track_record_by_trader: dict[int, tuple[float, float]]) -> HolderOut:
    track_record = track_record_by_trader.get(t.trader_id)
    return HolderOut(
        wallet=t.trader.wallet_address,
        username=t.trader.username,
        profile_image=t.trader.profile_image,
        verified=t.trader.verified,
        best_timeframe=t.best_timeframe,
        best_rank=t.best_rank,
        position_value=float(t.position_value),
        size=float(t.size),
        avg_entry_price=float(t.avg_entry_price),
        current_price=float(t.current_price),
        cash_pnl=float(t.cash_pnl),
        percent_pnl=float(t.percent_pnl),
        win_rate=track_record[0] if track_record else None,
        recent_form=track_record[1] if track_record else None,
        hedge_opposing_value=float(t.hedge_opposing_value) if t.hedge_opposing_value is not None else None,
    )


async def load_latest_snapshot(session: AsyncSession) -> ConsensusSnapshot | None:
    scan_row = await session.execute(
        select(Scan).where(Scan.status == ScanStatus.COMPLETED).order_by(Scan.completed_at.desc()).limit(1)
    )
    scan = scan_row.scalar_one_or_none()
    if scan is None:
        return None

    config = await get_app_config(session)
    value_normalizer = float(config.value_normalizer) if config else 6.0
    max_value_boost = float(config.max_value_boost) if config else 1.0

    # Only the widest (top_n=CANONICAL_TOP_N) cut is ever persisted per variant
    # — smaller cuts are derived below, since a trader qualifying for a
    # smaller top-N always also qualifies for this one.
    positions_result = await session.execute(
        select(ConsensusPosition)
        .where(ConsensusPosition.scan_id == scan.id, ConsensusPosition.top_n == CANONICAL_TOP_N)
        .options(
            selectinload(ConsensusPosition.market),
            selectinload(ConsensusPosition.traders).selectinload(ConsensusPositionTrader.trader),
        )
    )
    positions = positions_result.scalars().all()

    ranks_result = await session.execute(
        select(TraderLeaderboardRank.trader_id, TraderLeaderboardRank.timeframe, TraderLeaderboardRank.rank).where(
            TraderLeaderboardRank.scan_id == scan.id
        )
    )
    ranks_by_trader: dict[int, dict[str, int]] = defaultdict(dict)
    for trader_id, timeframe, rank in ranks_result.all():
        ranks_by_trader[trader_id][timeframe.value] = rank

    track_records_result = await session.execute(
        select(TraderTrackRecord.trader_id, TraderTrackRecord.win_rate, TraderTrackRecord.recent_form)
    )
    track_record_by_trader: dict[int, tuple[float, float]] = {
        trader_id: (float(win_rate), float(recent_form)) for trader_id, win_rate, recent_form in track_records_result.all()
    }

    now = datetime.now(UTC)
    variants: dict[str, list[ConsensusRowOut]] = {}

    for cp in positions:
        market = cp.market
        # A market with no title (Gamma metadata missing/not yet fetched) has
        # nothing meaningful to show — skip it rather than render "Untitled market".
        if market is None or not market.title.strip():
            continue

        variant = Variant(cp.variant.value)
        # A market whose price has already converged to (effectively) 0% or
        # 100% is done in every way that matters, even if Gamma's `active`
        # flag / end_date metadata hasn't caught up yet (up to a 24h TTL) —
        # same 0.5%/99.5% band the UI itself rounds to those displayed
        # percentages, so "shows 100% on screen" and "counted as finished"
        # never disagree.
        price_resolved = float(cp.current_price) <= 0.005 or float(cp.current_price) >= 0.995
        is_active = bool(market.active) and (market.end_date is None or market.end_date > now) and not price_resolved

        for top_n in TOP_N_OPTIONS:
            if top_n == CANONICAL_TOP_N:
                filtered = list(cp.traders)
            else:
                filtered = [
                    t for t in cp.traders if _qualifies_for_cut(ranks_by_trader.get(t.trader_id, {}), variant, top_n)
                ]
            if not filtered:
                continue

            combined_value = sum(float(t.position_value) for t in filtered)
            whale_score = sum(float(t.trader_weight or 0) for t in filtered)
            consensus_score = score_from_weight_and_value(whale_score, combined_value, value_normalizer, max_value_boost)

            row = ConsensusRowOut(
                id=f"{cp.condition_id}:{cp.outcome_index}",
                condition_id=cp.condition_id,
                outcome_index=cp.outcome_index,
                outcome_label=cp.outcome_label,
                market_title=market.title,
                market_slug=market.slug,
                event_slug=market.event_slug,
                category=market.category,
                image_url=market.image_url,
                end_date=market.end_date,
                is_active=is_active,
                current_price=float(cp.current_price),
                whale_count=len(filtered),
                combined_value=combined_value,
                consensus_score=consensus_score,
                holders=[_holder_out(t, track_record_by_trader) for t in filtered],
            )
            key = variant_key(variant, top_n)
            variants.setdefault(key, []).append(row)

    for rows in variants.values():
        rows.sort(key=lambda r: r.consensus_score, reverse=True)

    return ConsensusSnapshot(
        scan_id=scan.id,
        last_refresh_at=scan.completed_at,
        tracked_traders=scan.traders_count,
        active_positions=scan.positions_count,
        total_whale_exposure=float(scan.total_value),
        variants=variants,
    )


async def get_excluded_market_ids(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(ExcludedMarket.condition_id))
    return {r[0] for r in rows}


async def get_excluded_wallet_addresses(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(ExcludedTrader.wallet_address))
    return {r[0] for r in rows}


async def list_excluded_markets(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(ExcludedMarket, Market.title)
        .outerjoin(Market, Market.condition_id == ExcludedMarket.condition_id)
        .order_by(ExcludedMarket.excluded_at.desc())
    )
    return [
        {"condition_id": em.condition_id, "reason": em.reason, "excluded_at": em.excluded_at, "title": title}
        for em, title in result.all()
    ]


async def add_excluded_market(session: AsyncSession, condition_id: str, reason: str | None) -> None:
    stmt = pg_insert(ExcludedMarket).values(
        condition_id=condition_id, reason=reason, excluded_at=datetime.now(UTC)
    )
    stmt = stmt.on_conflict_do_update(index_elements=[ExcludedMarket.condition_id], set_={"reason": stmt.excluded.reason})
    await session.execute(stmt)
    await session.commit()


async def remove_excluded_market(session: AsyncSession, condition_id: str) -> None:
    await session.execute(delete(ExcludedMarket).where(ExcludedMarket.condition_id == condition_id))
    await session.commit()


async def list_excluded_traders(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(ExcludedTrader, TraderModel.username)
        .outerjoin(TraderModel, TraderModel.wallet_address == ExcludedTrader.wallet_address)
        .order_by(ExcludedTrader.excluded_at.desc())
    )
    return [
        {
            "wallet_address": et.wallet_address,
            "reason": et.reason,
            "excluded_at": et.excluded_at,
            "username": username,
        }
        for et, username in result.all()
    ]


async def add_excluded_trader(session: AsyncSession, wallet_address: str, reason: str | None) -> None:
    stmt = pg_insert(ExcludedTrader).values(
        wallet_address=wallet_address, reason=reason, excluded_at=datetime.now(UTC)
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[ExcludedTrader.wallet_address], set_={"reason": stmt.excluded.reason}
    )
    await session.execute(stmt)
    await session.commit()


async def remove_excluded_trader(session: AsyncSession, wallet_address: str) -> None:
    await session.execute(delete(ExcludedTrader).where(ExcludedTrader.wallet_address == wallet_address))
    await session.commit()


async def get_app_config(session: AsyncSession) -> AppConfig | None:
    result = await session.execute(select(AppConfig).where(AppConfig.id == 1))
    return result.scalar_one_or_none()


async def create_app_config(session: AsyncSession, admin_password_hash: str) -> AppConfig:
    config = AppConfig(id=1, admin_password_hash=admin_password_hash, updated_at=datetime.now(UTC))
    session.add(config)
    await session.commit()
    return config


async def update_app_config(session: AsyncSession, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now(UTC)
    await session.execute(AppConfig.__table__.update().where(AppConfig.id == 1).values(**fields))
    await session.commit()


async def list_recent_scans(session: AsyncSession, limit: int = 20) -> list[Scan]:
    result = await session.execute(select(Scan).order_by(Scan.id.desc()).limit(limit))
    return list(result.scalars().all())


async def get_last_completed_scan_at(session: AsyncSession) -> datetime | None:
    """Cheap staleness check for the scan watchdog — just the timestamp, not
    the full snapshot (load_latest_snapshot does real work re-hydrating every
    consensus row/trader, overkill for a check that runs every few minutes)."""
    result = await session.execute(
        select(Scan.completed_at).where(Scan.status == ScanStatus.COMPLETED).order_by(Scan.completed_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


def parse_market_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- mini whale bot ---------------------------------------------------------


async def get_or_create_bot_state(session: AsyncSession) -> BotState:
    result = await session.execute(select(BotState).where(BotState.id == 1))
    state = result.scalar_one_or_none()
    if state is None:
        state = BotState(id=1, updated_at=datetime.now(UTC))
        session.add(state)
        await session.flush()
    return state


async def update_bot_state(session: AsyncSession, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now(UTC)
    await session.execute(BotState.__table__.update().where(BotState.id == 1).values(**fields))


async def get_open_bot_positions(session: AsyncSession) -> list[BotPosition]:
    result = await session.execute(select(BotPosition).where(BotPosition.status == BotPositionStatus.OPEN))
    return list(result.scalars().all())


async def get_bot_win_loss_counts(session: AsyncSession) -> tuple[int, int]:
    """(wins, losses) across all closed trades — aggregate record only, no
    market names/sizes/timestamps, safe for the unauthenticated teaser."""
    result = await session.execute(
        select(BotPosition.realized_pnl).where(
            BotPosition.status == BotPositionStatus.CLOSED, BotPosition.realized_pnl.is_not(None)
        )
    )
    pnls = [float(p) for p in result.scalars().all()]
    wins = sum(1 for p in pnls if p > 0)
    return wins, len(pnls) - wins


MAX_TEASER_EQUITY_POINTS = 40


async def get_bot_equity_curve(session: AsyncSession) -> list[float]:
    """Chronological running bankroll value (starting balance + cumulative
    realized P&L) after each closed trade — a real shape for the login-page
    teaser chart, capped to the most recent MAX_TEASER_EQUITY_POINTS so it
    doesn't reveal the exact trade count to an unauthenticated caller. No
    market names, sizes, or timestamps — just the balance trajectory."""
    state = await get_or_create_bot_state(session)
    result = await session.execute(
        select(BotPosition.realized_pnl)
        .where(BotPosition.status == BotPositionStatus.CLOSED, BotPosition.exit_at.is_not(None))
        .order_by(BotPosition.exit_at.asc())
    )
    running = float(state.starting_balance)
    curve = [running]
    for pnl in result.scalars().all():
        running += float(pnl or 0)
        curve.append(running)
    return curve[-MAX_TEASER_EQUITY_POINTS:]


async def create_bot_position(session: AsyncSession, **fields) -> BotPosition:
    position = BotPosition(status=BotPositionStatus.OPEN, **fields)
    session.add(position)
    await session.flush()
    return position


async def count_bot_entries_since(session: AsyncSession, since: datetime) -> int:
    return await session.scalar(
        select(func.count()).select_from(BotPosition).where(BotPosition.entry_at >= since)
    ) or 0


async def close_bot_position(
    session: AsyncSession,
    position_id: int,
    exit_price: float,
    exit_reason: BotExitReason,
    realized_pnl: float,
) -> None:
    await session.execute(
        BotPosition.__table__.update()
        .where(BotPosition.id == position_id)
        .values(
            status=BotPositionStatus.CLOSED,
            exit_price=exit_price,
            exit_at=datetime.now(UTC),
            exit_reason=exit_reason,
            realized_pnl=realized_pnl,
        )
    )


async def get_recent_closed_bot_positions(session: AsyncSession, limit: int) -> list[BotPosition]:
    result = await session.execute(
        select(BotPosition)
        .where(BotPosition.status == BotPositionStatus.CLOSED)
        .order_by(BotPosition.exit_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_bot_positions(session: AsyncSession, status: str | None, limit: int) -> list[BotPosition]:
    query = select(BotPosition).order_by(BotPosition.entry_at.desc()).limit(limit)
    if status == "open":
        query = query.where(BotPosition.status == BotPositionStatus.OPEN)
    elif status == "closed":
        query = query.where(BotPosition.status == BotPositionStatus.CLOSED)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_bot_positions_page(
    session: AsyncSession, status: str | None, timeframe: str, page: int, page_size: int
) -> tuple[list[BotPosition], int]:
    """Paginated positions for the trade-history view. `timeframe` (day/week/
    all_time) filters on exit_at — a rolling window, not a calendar-day cutoff,
    so it doesn't go empty right after midnight. Open positions have no
    exit_at yet, so they're never excluded by the timeframe filter."""
    filters = []
    if status == "open":
        filters.append(BotPosition.status == BotPositionStatus.OPEN)
    elif status == "closed":
        filters.append(BotPosition.status == BotPositionStatus.CLOSED)

    if timeframe != "all_time":
        cutoff = datetime.now(UTC) - (timedelta(days=1) if timeframe == "day" else timedelta(days=7))
        filters.append(or_(BotPosition.status == BotPositionStatus.OPEN, BotPosition.exit_at >= cutoff))

    count_query = select(func.count()).select_from(BotPosition)
    query = select(BotPosition).order_by(BotPosition.entry_at.desc())
    for f in filters:
        count_query = count_query.where(f)
        query = query.where(f)

    total = await session.scalar(count_query) or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    return list(result.scalars().all()), total


async def insert_bot_recalibration(
    session: AsyncSession, reasoning: str, old_thresholds: dict, new_thresholds: dict
) -> None:
    session.add(
        BotRecalibration(
            at=datetime.now(UTC), reasoning=reasoning, old_thresholds=old_thresholds, new_thresholds=new_thresholds
        )
    )


async def list_bot_recalibrations(session: AsyncSession, limit: int = 20) -> list[BotRecalibration]:
    result = await session.execute(select(BotRecalibration).order_by(BotRecalibration.id.desc()).limit(limit))
    return list(result.scalars().all())


# --- admin: login tracking ---------------------------------------------------


async def record_login_event(session: AsyncSession, role: str, visitor_hash: str) -> None:
    session.add(LoginEvent(role=role, visitor_hash=visitor_hash, occurred_at=datetime.now(UTC)))
    await session.commit()


async def get_login_stats(session: AsyncSession) -> dict:
    since_24h = datetime.now(UTC) - timedelta(hours=24)
    total = await session.scalar(select(func.count()).select_from(LoginEvent))
    unique_all_time = await session.scalar(select(func.count(func.distinct(LoginEvent.visitor_hash))))
    total_24h = await session.scalar(
        select(func.count()).select_from(LoginEvent).where(LoginEvent.occurred_at >= since_24h)
    )
    unique_24h = await session.scalar(
        select(func.count(func.distinct(LoginEvent.visitor_hash))).where(LoginEvent.occurred_at >= since_24h)
    )
    return {
        "total_logins": total or 0,
        "unique_visitors": unique_all_time or 0,
        "logins_last_24h": total_24h or 0,
        "unique_visitors_last_24h": unique_24h or 0,
    }


# --- admin: large-trade ("whale alert") notifications -------------------------


async def get_market_titles(session: AsyncSession, condition_ids: list[str]) -> dict[str, str]:
    if not condition_ids:
        return {}
    result = await session.execute(
        select(Market.condition_id, Market.title).where(Market.condition_id.in_(condition_ids))
    )
    return {cid: title for cid, title in result.all()}


async def record_whale_alerts(session: AsyncSession, alerts: list[dict]) -> int:
    """Insert-once per (wallet, market, outcome) — a whale sitting on a big
    position for weeks shouldn't re-alert every 15-minute scan. Returns the
    number of genuinely NEW alerts inserted."""
    if not alerts:
        return 0
    stmt = pg_insert(WhaleAlert).values(alerts)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[WhaleAlert.wallet_address, WhaleAlert.condition_id, WhaleAlert.outcome_index]
    )
    result = await session.execute(stmt.returning(WhaleAlert.id))
    return len(result.all())


async def list_whale_alerts(session: AsyncSession, limit: int = 50) -> list[WhaleAlert]:
    result = await session.execute(select(WhaleAlert).order_by(WhaleAlert.detected_at.desc()).limit(limit))
    return list(result.scalars().all())


async def count_unacknowledged_whale_alerts(session: AsyncSession) -> int:
    return await session.scalar(
        select(func.count()).select_from(WhaleAlert).where(WhaleAlert.acknowledged.is_(False))
    ) or 0


async def acknowledge_whale_alert(session: AsyncSession, alert_id: int) -> None:
    await session.execute(WhaleAlert.__table__.update().where(WhaleAlert.id == alert_id).values(acknowledged=True))
    await session.commit()


async def acknowledge_all_whale_alerts(session: AsyncSession) -> None:
    await session.execute(WhaleAlert.__table__.update().where(WhaleAlert.acknowledged.is_(False)).values(acknowledged=True))
    await session.commit()


# --- admin: named visitor access codes ---------------------------------------


async def list_access_codes(session: AsyncSession) -> list[AccessCode]:
    result = await session.execute(select(AccessCode).order_by(AccessCode.created_at.desc()))
    return list(result.scalars().all())


async def create_access_code(session: AsyncSession, name: str, code: str) -> AccessCode:
    access_code = AccessCode(name=name, code_hash=hash_secret(code), created_at=datetime.now(UTC), active=True)
    session.add(access_code)
    await session.commit()
    return access_code


async def revoke_access_code(session: AsyncSession, access_code_id: int) -> None:
    await session.execute(AccessCode.__table__.update().where(AccessCode.id == access_code_id).values(active=False))
    await session.commit()


async def verify_any_access_code(session: AsyncSession, code: str) -> bool:
    result = await session.execute(select(AccessCode.code_hash).where(AccessCode.active.is_(True)))
    return any(verify_secret(code, code_hash) for (code_hash,) in result.all())


# --- chat: KrillBot admin-help escalations -------------------------------------


async def create_support_request(session: AsyncSession, summary: str, contact: str) -> SupportRequest:
    request = SupportRequest(summary=summary, contact=contact, created_at=datetime.now(UTC), acknowledged=False)
    session.add(request)
    await session.commit()
    return request


async def list_support_requests(session: AsyncSession, limit: int = 50) -> list[SupportRequest]:
    result = await session.execute(select(SupportRequest).order_by(SupportRequest.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def count_unacknowledged_support_requests(session: AsyncSession) -> int:
    return await session.scalar(
        select(func.count()).select_from(SupportRequest).where(SupportRequest.acknowledged.is_(False))
    ) or 0


async def acknowledge_support_request(session: AsyncSession, request_id: int) -> None:
    await session.execute(
        SupportRequest.__table__.update().where(SupportRequest.id == request_id).values(acknowledged=True)
    )
    await session.commit()


# --- login-page signup box ------------------------------------------------------


async def create_signup(session: AsyncSession, contact: str) -> Signup:
    signup = Signup(contact=contact, submitted_at=datetime.now(UTC), acknowledged=False)
    session.add(signup)
    await session.commit()
    return signup


async def list_signups(session: AsyncSession, limit: int = 100) -> list[Signup]:
    result = await session.execute(select(Signup).order_by(Signup.submitted_at.desc()).limit(limit))
    return list(result.scalars().all())


async def acknowledge_signup(session: AsyncSession, signup_id: int) -> None:
    await session.execute(Signup.__table__.update().where(Signup.id == signup_id).values(acknowledged=True))
    await session.commit()


# --- admin: hot-streak traders --------------------------------------------------


_TIMEFRAME_QUALITY = {"ALL": 4, "MONTH": 3, "WEEK": 2, "DAY": 1}


async def get_hot_traders(session: AsyncSession, limit: int = 5, min_sample: int = 3) -> list[dict]:
    """Top traders by recent form (win rate over their last ~10 resolved
    positions) — real Polymarket-reported outcomes, not a guess. Restricted
    to traders who are on some leaderboard in the latest scan, so this
    never surfaces someone who's since dropped off entirely, and to a
    minimum sample size so one lucky trade can't look like a hot streak."""
    latest_scan_id = await session.scalar(
        select(Scan.id).where(Scan.status == ScanStatus.COMPLETED).order_by(Scan.id.desc()).limit(1)
    )
    if latest_scan_id is None:
        return []

    tracked_ids = select(TraderLeaderboardRank.trader_id).where(TraderLeaderboardRank.scan_id == latest_scan_id).distinct()

    result = await session.execute(
        select(
            TraderModel.id,
            TraderModel.username,
            TraderModel.wallet_address,
            TraderTrackRecord.recent_form,
            TraderTrackRecord.win_rate,
            TraderTrackRecord.sample_size,
        )
        .join(TraderTrackRecord, TraderTrackRecord.trader_id == TraderModel.id)
        .where(TraderModel.id.in_(tracked_ids), TraderTrackRecord.sample_size >= min_sample)
        .order_by(TraderTrackRecord.recent_form.desc())
        .limit(limit)
    )
    rows = result.all()
    if not rows:
        return []

    trader_ids = [r[0] for r in rows]
    rank_result = await session.execute(
        select(TraderLeaderboardRank.trader_id, TraderLeaderboardRank.timeframe, TraderLeaderboardRank.rank).where(
            TraderLeaderboardRank.scan_id == latest_scan_id, TraderLeaderboardRank.trader_id.in_(trader_ids)
        )
    )
    # Best rank per trader = highest-quality timeframe first, ties broken by
    # the lowest (best) rank — mirrors consensus_engine.Trader.best_rank().
    best_rank_by_trader: dict[int, tuple[str, int]] = {}
    for trader_id, timeframe, rank in rank_result.all():
        tf_value = timeframe.value if hasattr(timeframe, "value") else str(timeframe)
        current = best_rank_by_trader.get(trader_id)
        if current is None or (_TIMEFRAME_QUALITY[tf_value], -rank) > (_TIMEFRAME_QUALITY[current[0]], -current[1]):
            best_rank_by_trader[trader_id] = (tf_value, rank)

    return [
        {
            "username": username,
            "wallet_address": wallet_address,
            "recent_form": float(recent_form),
            "win_rate": float(win_rate),
            "sample_size": sample_size,
            "best_rank": best_rank_by_trader[trader_id][1] if trader_id in best_rank_by_trader else None,
            "best_rank_timeframe": best_rank_by_trader[trader_id][0] if trader_id in best_rank_by_trader else None,
        }
        for trader_id, username, wallet_address, recent_form, win_rate, sample_size in rows
    ]


# --- whale spotlight: daily catch pick lock ------------------------------------


async def get_daily_catch_pick(session: AsyncSession, pick_date: date) -> DailyCatchPick | None:
    result = await session.execute(select(DailyCatchPick).where(DailyCatchPick.pick_date == pick_date))
    return result.scalar_one_or_none()


async def create_daily_catch_pick(session: AsyncSession, pick_date: date, condition_id: str, outcome_index: int) -> None:
    # ON CONFLICT DO NOTHING: if two requests race to pick "today" at once,
    # whichever commits first wins and the other is silently a no-op — never
    # two different picks for the same day.
    stmt = pg_insert(DailyCatchPick).values(
        pick_date=pick_date, condition_id=condition_id, outcome_index=outcome_index, picked_at=datetime.now(UTC)
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=[DailyCatchPick.pick_date])
    await session.execute(stmt)
    await session.commit()


async def update_daily_catch_pick(session: AsyncSession, pick_date: date, condition_id: str, outcome_index: int) -> None:
    """Re-roll an already-locked pick — used when the current pick has
    resolved (or its price already hit 0%/100%) partway through the day,
    so the spotlight doesn't keep showing a finished market."""
    await session.execute(
        update(DailyCatchPick)
        .where(DailyCatchPick.pick_date == pick_date)
        .values(condition_id=condition_id, outcome_index=outcome_index, picked_at=datetime.now(UTC))
    )
    await session.commit()
