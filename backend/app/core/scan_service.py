import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.core import bot_service
from app.core import cache as cache_module
from app.core.consensus_engine import (
    CANONICAL_TOP_N,
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

# repository.try_acquire_scan_lock (a transaction-scoped DB advisory lock)
# only guards the final write portion of a scan — by design, since holding
# one DB transaction open for the ~60-500s a scan can take (most of it spent
# waiting on Polymarket's API, not the DB) would tie up a pooled connection
# for the whole scan and works against pgbouncer's transaction-mode pooling.
# But that means, without this, TWO overlapping triggers (the staleness
# check firing again before a slow first attempt finishes, a manual rescan,
# the cron endpoint, a fresh boot's catch-up scan) would each redundantly
# run the ENTIRE expensive external-API fetch sequence before either one
# even checks the DB lock — multiplying Polymarket API load and very
# plausibly cascading into the exact kind of rate-limit-driven failures
# seen in production. Single-instance is already a hard architectural
# constraint for this app (in-process caches, in-process rate limiter), so
# a plain in-process lock is a complete, correct guard for that case — the
# DB lock remains as a second, independent safety net for the multi-replica
# case this app isn't actually designed to run under.
_scan_in_progress = asyncio.Lock()

# The staleness check re-fires every 3min regardless of why the previous
# attempt failed. If the failure is a slow/overloaded database (observed:
# a single indexed lookup taking 30-45s instead of milliseconds), retrying
# immediately every 3min just adds more concurrent load on top of whatever
# is already struggling, worsening it. Back off exponentially on consecutive
# failures so a struggling DB gets room to recover instead of getting hit
# harder; reset to normal cadence the moment a scan actually succeeds.
BACKOFF_BASE_SECONDS = 180
BACKOFF_MAX_SECONDS = 1800
_consecutive_failures = 0
_retry_not_before: datetime | None = None


async def run_scan(client: PolymarketClient, settings: Settings) -> None:
    global _consecutive_failures, _retry_not_before
    if _scan_in_progress.locked():
        logger.warning("a scan is already running in this process — skipping this trigger")
        return
    if _retry_not_before is not None and datetime.now(UTC) < _retry_not_before:
        logger.warning(
            "backing off after %d consecutive failure(s) — next attempt at %s",
            _consecutive_failures,
            _retry_not_before,
        )
        return
    async with _scan_in_progress:
        try:
            await asyncio.wait_for(_run_scan(client, settings), timeout=SCAN_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.error("scan timed out after %ss — will retry next cycle", SCAN_TIMEOUT_SECONDS)
            _consecutive_failures += 1
            _retry_not_before = datetime.now(UTC) + _backoff_delay(_consecutive_failures)
        except Exception:
            logger.exception("scan failed — will retry next cycle, serving last-good cache")
            _consecutive_failures += 1
            _retry_not_before = datetime.now(UTC) + _backoff_delay(_consecutive_failures)
        else:
            _consecutive_failures = 0
            _retry_not_before = None


def _backoff_delay(consecutive_failures: int) -> timedelta:
    seconds = min(BACKOFF_BASE_SECONDS * (2 ** (consecutive_failures - 1)), BACKOFF_MAX_SECONDS)
    return timedelta(seconds=seconds)


async def _run_scan(client: PolymarketClient, settings: Settings) -> None:
    value_normalizer, max_value_boost = await _load_scoring_weights(settings)

    entries_by_timeframe = await _fetch_all_leaderboards(client)
    traders = merge_leaderboards(entries_by_timeframe)
    if not traders:
        logger.error("no traders found on any leaderboard — aborting scan")
        return
    logger.info("checkpoint: leaderboards fetched, %d unique traders", len(traders))

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
    logger.info(
        "checkpoint: positions fetched for %d/%d traders, %d total positions",
        len(positions_by_wallet),
        len(traders),
        sum(len(p) for p in positions_by_wallet.values()),
    )

    if excluded_markets:
        positions_by_wallet = {
            wallet: [p for p in positions if p.condition_id not in excluded_markets]
            for wallet, positions in positions_by_wallet.items()
        }

    condition_ids = sorted({p.condition_id for positions in positions_by_wallet.values() for p in positions})
    market_metadata = await _enrich_market_metadata(client, settings, condition_ids)
    logger.info("checkpoint: market metadata enriched, %d markets refreshed", len(market_metadata))

    new_track_records, track_records = await _load_track_records(client, settings, list(traders.keys()))
    logger.info("checkpoint: track records loaded, %d newly computed", len(new_track_records))

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

        new_whale_alerts = await _record_whale_alerts(session, settings, traders, positions_by_wallet, condition_ids)
        if new_whale_alerts:
            logger.info("checkpoint: %d new whale alert(s) ($%.0f+ single positions)", new_whale_alerts, settings.whale_alert_threshold)

        # Only the widest cut (top_n=CANONICAL_TOP_N) is computed/persisted per
        # variant — smaller top-N cuts are derived from it at snapshot-load
        # time (see repository.load_latest_snapshot), since a trader
        # qualifying for a smaller cut always also qualifies for this one.
        # Persisting all 5 cuts independently multiplied scan write volume 5x
        # for no benefit and blew past a gigabyte of DB storage in under a day.
        combined_top_count = 0
        for variant in Variant:
            groups = build_consensus_groups(
                traders, positions_by_wallet, variant, CANONICAL_TOP_N, track_records, value_normalizer, max_value_boost
            )
            if variant == Variant.COMBINED:
                combined_top_count = len(groups)
            await repository.insert_consensus_groups(session, scan_id, variant, CANONICAL_TOP_N, groups, trader_ids)
            del groups
            logger.info("checkpoint: persisted bucket variant=%s top_n=%d", variant, CANONICAL_TOP_N)

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
        # Runs against the fresh snapshot in its own session/try-except — a
        # bot failure must never break the real scan (see run_bot_cycle).
        await bot_service.run_bot_cycle(snapshot, settings)

    logger.info(
        "scan %s completed: %d traders, %d positions, %d combined/top%d consensus groups, "
        "%d fresh track records",
        scan_id,
        len(traders),
        active_positions,
        combined_top_count,
        CANONICAL_TOP_N,
        len(new_track_records),
    )


async def _record_whale_alerts(session, settings: Settings, traders: dict, positions_by_wallet: dict, condition_ids: list[str]) -> int:
    """Flags any single trader's position worth >= whale_alert_threshold —
    surfaced in the admin notifications feed. Insert-once per (wallet,
    market, outcome), so a whale holding a big position for weeks only
    alerts once, not every 15-minute scan."""
    market_titles = await repository.get_market_titles(session, condition_ids)
    now = datetime.now(UTC)
    rows = [
        {
            "wallet_address": wallet,
            "username": traders[wallet].username if wallet in traders else None,
            "condition_id": p.condition_id,
            "outcome_index": p.outcome_index,
            "outcome_label": p.outcome,
            "market_title": market_titles.get(p.condition_id, ""),
            "position_value": p.current_value,
            "detected_at": now,
            "acknowledged": False,
        }
        for wallet, positions in positions_by_wallet.items()
        for p in positions
        if p.current_value >= settings.whale_alert_threshold
    ]
    return await repository.record_whale_alerts(session, rows)


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
