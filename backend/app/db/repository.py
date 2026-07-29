import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import ConsensusRowOut, ConsensusSnapshot, HolderOut, variant_key
from app.core.consensus_engine import ConsensusGroup, Trader, TrackRecord, Variant
from app.db.models import (
    AppConfig,
    ConsensusPosition,
    ConsensusPositionTrader,
    ExcludedMarket,
    ExcludedTrader,
    Market,
    Scan,
    ScanStatus,
    TraderLeaderboardRank,
    TraderTrackRecord,
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


async def load_latest_snapshot(session: AsyncSession) -> ConsensusSnapshot | None:
    scan_row = await session.execute(
        select(Scan).where(Scan.status == ScanStatus.COMPLETED).order_by(Scan.completed_at.desc()).limit(1)
    )
    scan = scan_row.scalar_one_or_none()
    if scan is None:
        return None

    positions_result = await session.execute(
        select(ConsensusPosition)
        .where(ConsensusPosition.scan_id == scan.id)
        .options(
            selectinload(ConsensusPosition.market),
            selectinload(ConsensusPosition.traders).selectinload(ConsensusPositionTrader.trader),
        )
        .order_by(ConsensusPosition.consensus_score.desc())
    )
    positions = positions_result.scalars().all()

    variants: dict[str, list[ConsensusRowOut]] = {}
    for cp in positions:
        market = cp.market
        row = ConsensusRowOut(
            id=f"{cp.condition_id}:{cp.outcome_index}",
            condition_id=cp.condition_id,
            outcome_index=cp.outcome_index,
            outcome_label=cp.outcome_label,
            market_title=market.title if market else "",
            market_slug=market.slug if market else "",
            event_slug=market.event_slug if market else "",
            category=market.category if market else None,
            image_url=market.image_url if market else None,
            end_date=market.end_date if market else None,
            is_active=market.active if market else True,
            current_price=float(cp.current_price),
            whale_count=cp.whale_count,
            combined_value=float(cp.combined_value),
            consensus_score=float(cp.consensus_score),
            holders=[
                HolderOut(
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
                )
                for t in cp.traders
            ],
        )
        key = variant_key(Variant(cp.variant.value), cp.top_n)
        variants.setdefault(key, []).append(row)

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


async def create_app_config(session: AsyncSession, access_code_hash: str, admin_password_hash: str) -> AppConfig:
    config = AppConfig(
        id=1,
        access_code_hash=access_code_hash,
        admin_password_hash=admin_password_hash,
        updated_at=datetime.now(UTC),
    )
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


def parse_market_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
