import asyncio
import logging

from app.config import Settings
from app.core import cache as cache_module
from app.core.consensus_engine import (
    TOP_N_OPTIONS,
    TrackRecord,
    Variant,
    build_consensus_groups,
    compute_track_record,
    merge_leaderboards,
)
from app.db import repository
from app.db.session import get_session
from app.integrations.polymarket_client import PolymarketClient, Timeframe

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SECONDS = 480
MIN_POSITION_FETCH_SUCCESS_RATE = 0.9


async def run_scan(client: PolymarketClient, settings: Settings) -> None:
    try:
        await asyncio.wait_for(_run_scan(client, settings), timeout=SCAN_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.error("scan timed out after %ss — will retry next cycle", SCAN_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("scan failed — will retry next cycle, serving last-good cache")


async def _run_scan(client: PolymarketClient, settings: Settings) -> None:
    value_normalizer, max_value_boost = await _load_scoring_weights(settings)

    entries_by_timeframe = await _fetch_all_leaderboards(client)
    traders = merge_leaderboards(entries_by_timeframe)
    if not traders:
        logger.error("no traders found on any leaderboard — aborting scan")
        return

    async with get_session() as session:
        excluded_markets = await repository.get_excluded_market_ids(session)
        excluded_wallets = await repository.get_excluded_wallet_addresses(session)

    traders = {w: t for w, t in traders.items() if w not in excluded_wallets}
    if not traders:
        logger.error("all traders excluded by moderation — aborting scan")
        return

    positions_by_wallet = await client.fetch_positions_for_wallets(list(traders.keys()))
    success_rate = len(positions_by_wallet) / len(traders)
    if success_rate < MIN_POSITION_FETCH_SUCCESS_RATE:
        logger.error(
            "position fetch success rate %.0f%% below threshold — aborting scan", success_rate * 100
        )
        return

    if excluded_markets:
        positions_by_wallet = {
            wallet: [p for p in positions if p.condition_id not in excluded_markets]
            for wallet, positions in positions_by_wallet.items()
        }

    condition_ids = sorted({p.condition_id for positions in positions_by_wallet.values() for p in positions})
    market_metadata = await _enrich_market_metadata(client, settings, condition_ids)

    new_track_records, track_records = await _load_track_records(client, settings, list(traders.keys()))

    groups_by_bucket = {
        (variant, top_n): build_consensus_groups(
            traders, positions_by_wallet, variant, top_n, track_records, value_normalizer, max_value_boost
        )
        for variant in Variant
        for top_n in TOP_N_OPTIONS
    }

    active_positions = sum(len(p) for p in positions_by_wallet.values())
    total_value = sum(p.current_value for positions in positions_by_wallet.values() for p in positions)

    async with get_session() as session:
        if not await repository.try_acquire_scan_lock(session):
            logger.warning("another process is already writing a scan — skipping this cycle")
            return

        scan_id = await repository.create_running_scan(session)
        await repository.upsert_markets(session, market_metadata)
        missing_metadata = [cid for cid in condition_ids if cid not in market_metadata]
        await repository.ensure_markets_exist_without_metadata(session, missing_metadata)

        trader_ids = await repository.upsert_traders(session, traders)
        await repository.insert_leaderboard_ranks(session, scan_id, traders, trader_ids)
        await repository.upsert_track_records(session, new_track_records, trader_ids)
        for (variant, top_n), groups in groups_by_bucket.items():
            await repository.insert_consensus_groups(session, scan_id, variant, top_n, groups, trader_ids)

        await repository.complete_scan(
            session, scan_id, traders_count=len(traders), positions_count=active_positions, total_value=total_value
        )
        await repository.prune_old_scans(session, settings.scan_retention_days)
        await session.commit()

    # Rebuild the cache from the DB rather than from what this cycle fetched in
    # memory: market metadata for condition_ids that were already fresh (within
    # market_metadata_ttl_hours) is intentionally NOT in `market_metadata` above
    # — it was already correct in the `markets` table and skipped to save Gamma
    # calls — so only the DB has the complete, merged picture.
    async with get_session() as session:
        snapshot = await repository.load_latest_snapshot(session)
    if snapshot is not None:
        cache_module.cache.refresh(snapshot)

    logger.info(
        "scan %s completed: %d traders, %d positions, %d combined/top25 consensus groups, "
        "%d fresh track records",
        scan_id,
        len(traders),
        active_positions,
        len(groups_by_bucket[(Variant.COMBINED, 25)]),
        len(new_track_records),
    )


async def _load_scoring_weights(settings: Settings) -> tuple[float, float]:
    async with get_session() as session:
        config = await repository.get_app_config(session)
    if config is None:
        return settings.value_normalizer, settings.max_value_boost
    return float(config.value_normalizer), float(config.max_value_boost)


async def _fetch_all_leaderboards(client: PolymarketClient) -> dict[Timeframe, list]:
    timeframes = list(Timeframe)
    results = await asyncio.gather(*(client.fetch_leaderboard(tf) for tf in timeframes))
    return dict(zip(timeframes, results, strict=True))


async def _enrich_market_metadata(client: PolymarketClient, settings: Settings, condition_ids: list[str]) -> dict:
    if not condition_ids:
        return {}
    async with get_session() as session:
        fresh_ids = await repository.get_fresh_market_condition_ids(
            session, condition_ids, settings.market_metadata_ttl_hours
        )
    stale_ids = [cid for cid in condition_ids if cid not in fresh_ids]
    if not stale_ids:
        return {}
    try:
        return await client.fetch_market_metadata(stale_ids)
    except Exception:
        logger.warning("gamma metadata fetch failed for %d markets — will retry next cycle", len(stale_ids))
        return {}


async def _load_track_records(
    client: PolymarketClient, settings: Settings, wallets: list[str]
) -> tuple[dict[str, TrackRecord], dict[str, TrackRecord]]:
    """Returns (newly_computed, all_current) — the first is what this cycle
    needs to persist, the second is what scoring needs (fresh cache hits +
    whatever was just computed). A trader with no data either way scores with
    consensus_engine's neutral default (1.0x multiplier), never blocking scoring.
    """
    async with get_session() as session:
        fresh_wallets = await repository.get_fresh_track_record_wallets(session, wallets, settings.track_record_ttl_hours)
        cached_records = await repository.get_track_records_by_wallet(session, list(fresh_wallets))

    stale_wallets = [w for w in wallets if w not in fresh_wallets]
    new_records: dict[str, TrackRecord] = {}
    if stale_wallets:
        try:
            closed_by_wallet = await client.fetch_closed_positions_for_wallets(stale_wallets)
            new_records = {wallet: compute_track_record(positions) for wallet, positions in closed_by_wallet.items()}
        except Exception:
            logger.warning("closed-positions fetch failed for %d wallets — scoring with neutral track record this cycle", len(stale_wallets))

    return new_records, {**cached_records, **new_records}
