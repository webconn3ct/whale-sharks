"""Mini whale bot: a simulated ($500 starting bankroll) trader that follows
the same whale-consensus signal the dashboard shows, with real entry/exit
decisions made from real prices every scan cycle.

Design, in order of priority:
1. ENTRY: whale-consensus data (whale count, consensus_score) is the primary,
   already-backtested quantitative filter — see scripts/backtest_signal.py.
   A live news-research gate (app/core/bot_research.py) can only VETO or
   DOWNSIZE a candidate that already cleared the quantitative bar; it can
   never independently create a trade.
2. EXIT: autonomous each cycle — take profit, cut losses when the whale
   signal has also decayed, or settle when the market resolves/disappears.
3. LEARNING: no ML training (unreliable at this data volume) — a rule-based
   recalibration loop that adjusts thresholds from the bot's own real
   results, logged with reasoning (see recalibrate() below).

Runs once per scan cycle, called from scan_service._run_scan() right after
the cache is refreshed, using its own DB session (a bot failure must never
break the real scan).
"""

import logging
from datetime import UTC, datetime, timedelta

from app.api.schemas import ConsensusRowOut, ConsensusSnapshot, variant_key
from app.config import Settings
from app.core.bot_research import research_gate
from app.core.consensus_engine import CANONICAL_TOP_N, Variant
from app.db import repository
from app.db.models import BotExitReason
from app.db.session import get_session

logger = logging.getLogger(__name__)

STAKE_TIERS = (10.0, 25.0, 50.0)
MAX_CONCURRENT_POSITIONS = 10
RECALIBRATION_INTERVAL = 15
RECALIBRATION_LOOKBACK = 30
# New entries require the snapshot to be this fresh — protects against
# opening a position on a line that's since moved.
ENTRY_MAX_STALENESS = timedelta(minutes=5)


async def run_bot_cycle(snapshot: ConsensusSnapshot, settings: Settings) -> None:
    try:
        await _run_bot_cycle(snapshot, settings)
    except Exception:
        logger.exception("mini whale bot cycle failed — will retry next scan")


async def _run_bot_cycle(snapshot: ConsensusSnapshot, settings: Settings) -> None:
    rows = snapshot.variants.get(variant_key(Variant.COMBINED, CANONICAL_TOP_N), [])
    rows_by_key = {(r.condition_id, r.outcome_index): r for r in rows}

    # New entries only happen against a fresh snapshot — if the scan that
    # produced this data is more than ENTRY_MAX_STALENESS old (a stuck job,
    # a delayed retry, whatever), the price the bot would enter at may no
    # longer reflect reality. Exits still run regardless of staleness —
    # protecting capital on the way out shouldn't wait on a fresh scan.
    snapshot_age = datetime.now(UTC) - snapshot.last_refresh_at
    is_fresh = snapshot_age <= ENTRY_MAX_STALENESS

    async with get_session() as session:
        state = await repository.get_or_create_bot_state(session)
        open_positions = await repository.get_open_bot_positions(session)

        closed_ids, cash_after_exits = await _process_exits(session, open_positions, rows_by_key, state)
        still_open = [p for p in open_positions if p.id not in closed_ids]
        if is_fresh:
            await _process_entry(session, rows, still_open, cash_after_exits, state, settings)
        else:
            logger.warning("skipping entries this cycle — snapshot is %s old (> %s)", snapshot_age, ENTRY_MAX_STALENESS)

        if closed_ids:
            new_count = int(state.trades_since_recalibration) + len(closed_ids)
            if new_count >= RECALIBRATION_INTERVAL:
                await _recalibrate(session, state)
                new_count = 0
            await repository.update_bot_state(session, trades_since_recalibration=new_count)

        await session.commit()


async def _process_exits(
    session, open_positions: list, rows_by_key: dict[tuple[str, int], ConsensusRowOut], state
) -> tuple[set[int], float]:
    """Returns (ids of positions closed this cycle, cash balance after settling them)."""
    closed_ids: set[int] = set()
    cash_delta = 0.0

    for position in open_positions:
        key = (position.condition_id, position.outcome_index)
        row = rows_by_key.get(key)
        stake = float(position.stake)
        shares = float(position.shares)
        entry_whale_count = position.entry_whale_count

        if row is None:
            # Every tracked whale has exited this position — we've lost the
            # thesis and can't mark-to-market. Close flat rather than hold
            # blind indefinitely.
            exit_price = float(position.entry_price)
            realized_pnl = 0.0
            reason = BotExitReason.SIGNAL_LOST
        elif not row.is_active:
            # Resolved markets pay out exactly $1 or $0 per share — never a
            # fraction. `current_price` here is just whatever was last
            # scraped (up to one scan cycle stale) and isn't guaranteed to
            # have converged to the true settlement value yet, so snap it to
            # the real binary payout instead of settling at a stale price.
            exit_price = 1.0 if row.current_price >= 0.5 else 0.0
            current_value = shares * exit_price
            realized_pnl = current_value - stake
            reason = BotExitReason.MARKET_RESOLVED
        else:
            exit_price = row.current_price
            current_value = shares * exit_price
            unrealized_pct = (current_value - stake) / stake if stake else 0.0

            if unrealized_pct >= float(state.take_profit_pct):
                realized_pnl = current_value - stake
                reason = BotExitReason.TAKE_PROFIT
            elif unrealized_pct <= -float(state.stop_loss_pct) and row.whale_count < entry_whale_count * float(
                state.signal_decay_fraction
            ):
                realized_pnl = current_value - stake
                reason = BotExitReason.STOP_LOSS
            else:
                continue  # hold

        await repository.close_bot_position(session, position.id, exit_price, reason, realized_pnl)
        cash_delta += stake + realized_pnl
        closed_ids.add(position.id)
        logger.info(
            "bot closed position %s (%s): pnl=%.2f reason=%s", position.id, position.market_title, realized_pnl, reason.value
        )

    cash_after = float(state.cash_balance) + cash_delta
    if cash_delta:
        await repository.update_bot_state(session, cash_balance=cash_after)

    return closed_ids, cash_after


def _stake_for_score(score: float, state) -> float:
    if score >= float(state.large_bet_score):
        return 50.0
    if score >= float(state.medium_bet_score):
        return 25.0
    return 10.0


def _downsize(stake: float) -> float | None:
    if stake >= 50.0:
        return 25.0
    if stake >= 25.0:
        return 10.0
    return None  # already at the smallest tier — a downsize verdict means skip


async def _process_entry(
    session, rows: list[ConsensusRowOut], open_positions: list, cash: float, state, settings: Settings
) -> None:
    if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
        return
    if cash < min(STAKE_TIERS):
        return

    held_conditions = {p.condition_id for p in open_positions}

    for row in rows:
        if not row.is_active:
            continue
        if row.condition_id in held_conditions:
            continue
        if row.whale_count < int(state.entry_min_whales):
            continue
        if row.consensus_score < float(state.entry_score_threshold):
            break  # rows are sorted descending by score — nothing further qualifies

        stake = _stake_for_score(row.consensus_score, state)
        if cash < stake:
            affordable = [t for t in STAKE_TIERS if t <= cash]
            if not affordable:
                continue  # can't afford even the smallest tier — try the next candidate
            stake = max(affordable)

        verdict = await research_gate(
            settings, row.market_title, row.outcome_label, row.category, row.whale_count, row.consensus_score
        )
        if verdict["verdict"] == "veto":
            logger.info("bot research gate vetoed %s: %s", row.market_title, verdict["reasoning"])
            continue
        if verdict["verdict"] == "downsize":
            downsized = _downsize(stake)
            if downsized is None:
                logger.info("bot research gate downsized %s below minimum stake — skipping", row.market_title)
                continue
            stake = downsized

        shares = stake / row.current_price if row.current_price > 0 else 0.0
        if shares <= 0:
            continue

        await repository.create_bot_position(
            session,
            condition_id=row.condition_id,
            outcome_index=row.outcome_index,
            outcome_label=row.outcome_label,
            market_title=row.market_title,
            category=row.category,
            stake=stake,
            shares=shares,
            entry_price=row.current_price,
            entry_at=datetime.now(UTC),
            entry_consensus_score=row.consensus_score,
            entry_whale_count=row.whale_count,
            entry_reasoning=verdict["reasoning"],
        )
        await repository.update_bot_state(session, cash_balance=cash - stake)
        logger.info(
            "bot opened position on %s (%s): stake=$%.0f score=%.0f whales=%d",
            row.market_title,
            row.outcome_label,
            stake,
            row.consensus_score,
            row.whale_count,
        )
        return  # at most one new position per cycle


async def _recalibrate(session, state) -> None:
    """Rule-based recalibration from real results — no ML training, just
    honest bookkeeping: look at what actually happened and tighten or loosen
    the bar accordingly. Every adjustment is logged with its reasoning."""
    closed = await repository.get_recent_closed_bot_positions(session, RECALIBRATION_LOOKBACK)
    if not closed:
        return

    def win_rate(positions) -> float:
        if not positions:
            return 0.5
        wins = sum(1 for p in positions if float(p.realized_pnl or 0) > 0)
        return wins / len(positions)

    overall = win_rate(closed)
    by_tier = {tier: win_rate([p for p in closed if abs(float(p.stake) - tier) < 0.01]) for tier in STAKE_TIERS}

    old = {
        "entry_score_threshold": float(state.entry_score_threshold),
        "medium_bet_score": float(state.medium_bet_score),
        "large_bet_score": float(state.large_bet_score),
        "stop_loss_pct": float(state.stop_loss_pct),
    }
    new = dict(old)
    reasons = [f"overall win rate over last {len(closed)} trades: {overall:.0%}"]

    if overall < 0.45:
        new["entry_score_threshold"] *= 1.15
        reasons.append("below 45% overall — raising entry bar 15% to be more selective")
    elif overall > 0.65:
        new["entry_score_threshold"] *= 0.95
        reasons.append("above 65% overall — loosening entry bar 5% to capture more opportunities")

    if by_tier[50.0] < 0.45 and sum(1 for p in closed if abs(float(p.stake) - 50.0) < 0.01) >= 3:
        new["large_bet_score"] *= 1.15
        reasons.append(f"$50-tier win rate {by_tier[50.0]:.0%} — raising the bar required for a $50 bet")
    if by_tier[25.0] < 0.45 and sum(1 for p in closed if abs(float(p.stake) - 25.0) < 0.01) >= 3:
        new["medium_bet_score"] *= 1.15
        reasons.append(f"$25-tier win rate {by_tier[25.0]:.0%} — raising the bar required for a $25 bet")

    if new == old:
        reasons.append("no threshold changes warranted this cycle")
    else:
        await repository.update_bot_state(session, **new)

    await repository.insert_bot_recalibration(session, "; ".join(reasons), old, new)
    await repository.update_bot_state(session, last_recalibrated_at=datetime.now(UTC))
    logger.info("bot recalibrated: %s", "; ".join(reasons))
