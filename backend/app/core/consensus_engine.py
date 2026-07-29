"""Pure functions that turn (leaderboard entries, positions) into ranked consensus groups.

No I/O here — everything is unit-testable in isolation. scan_service.py is the only
caller and supplies real data fetched via polymarket_client.py.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from math import log10

from app.integrations.polymarket_client import ClosedPosition, LeaderboardEntry, Position, Timeframe

QUALITY_WEIGHT: dict[Timeframe, int] = {
    Timeframe.ALL: 4,
    Timeframe.MONTH: 3,
    Timeframe.WEEK: 2,
    Timeframe.DAY: 1,
}

# Leaderboards are fetched down to this depth regardless of which top-N filter
# a request asks for, so trader_weight's rank term stays on a fixed scale
# (a rank-5 trader always outweighs a rank-50 one) no matter which cut is viewed.
MAX_LEADERBOARD_RANK = 100

TOP_N_OPTIONS: tuple[int, ...] = (5, 10, 25, 50, 100)
DEFAULT_TOP_N = 25
# Only this, widest cut is ever computed/persisted per variant — smaller
# top-N cuts are derived from it at snapshot-load time (see repository.py),
# since a trader qualifying for a smaller cut always also qualifies for this
# one. Persisting all 5 cuts independently multiplied scan write volume 5x
# for no benefit; the DB blew past a gigabyte in under a day of scans.
CANONICAL_TOP_N = max(TOP_N_OPTIONS)

# --- Track record (historical hit rate on resolved Polymarket markets) -----
#
# A trader's leaderboard rank reflects overall PnL, which one huge lucky bet
# can dominate. `realizedPnl` on each of a trader's *resolved* positions is a
# real, per-market win/loss signal (Polymarket's own accounting, not derived
# or guessed) — win_rate is the share of those that were profitable, and
# recent_form is the same over just their last ~10, which is what actually
# moves when a trader is on a hot or cold streak ("current run").
RECENT_FORM_SAMPLE = 10
# Shrinks a trader's rate toward a neutral 0.5 when their resolved-position
# sample is small, so e.g. a single lucky settled bet can't swing the
# multiplier to its extreme — equivalent to starting them off with this many
# fictitious 50/50 results.
TRACK_RECORD_PRIOR_WEIGHT = 6.0


@dataclass(frozen=True)
class TrackRecord:
    win_rate: float  # shrunk fraction of sampled resolved positions with realizedPnl > 0
    recent_form: float  # same, over just the most recent RECENT_FORM_SAMPLE
    sample_size: int


NEUTRAL_TRACK_RECORD = TrackRecord(win_rate=0.5, recent_form=0.5, sample_size=0)


def _shrunk_win_rate(wins: int, total: int) -> float:
    if total == 0:
        return 0.5
    return (wins + 0.5 * TRACK_RECORD_PRIOR_WEIGHT) / (total + TRACK_RECORD_PRIOR_WEIGHT)


def compute_track_record(closed_positions: list[ClosedPosition]) -> TrackRecord:
    """Pure function: raw resolved-position history -> a shrunk win rate +
    recent form. Called once per trader at scan time (see scan_service)."""
    if not closed_positions:
        return NEUTRAL_TRACK_RECORD
    ordered = sorted(closed_positions, key=lambda p: p.timestamp, reverse=True)
    total = len(ordered)
    wins = sum(1 for p in ordered if p.realized_pnl > 0)
    recent = ordered[:RECENT_FORM_SAMPLE]
    recent_wins = sum(1 for p in recent if p.realized_pnl > 0)
    return TrackRecord(
        win_rate=_shrunk_win_rate(wins, total),
        recent_form=_shrunk_win_rate(recent_wins, len(recent)),
        sample_size=total,
    )


def track_record_multiplier(record: TrackRecord | None) -> float:
    """Bounded 0.6x-1.4x multiplier — refines trader_weight, never overrides
    it, so a proven leaderboard trader's rank/quality still dominates the
    score. Recent form counts for more than lifetime win rate (a trader's
    *current run* is what this is meant to surface)."""
    r = record or NEUTRAL_TRACK_RECORD
    blended = 0.4 * r.win_rate + 0.6 * r.recent_form
    return 0.6 + 0.8 * blended


class Variant(StrEnum):
    """Which trader pool a consensus computation is scoped to."""

    COMBINED = "combined"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ALL_TIME = "all_time"


VARIANT_TO_TIMEFRAME: dict[Variant, Timeframe | None] = {
    Variant.COMBINED: None,  # union of every leaderboard
    Variant.DAY: Timeframe.DAY,
    Variant.WEEK: Timeframe.WEEK,
    Variant.MONTH: Timeframe.MONTH,
    Variant.ALL_TIME: Timeframe.ALL,
}


@dataclass(frozen=True)
class TraderRank:
    timeframe: Timeframe
    rank: int
    pnl: float
    vol: float


@dataclass(frozen=True)
class Trader:
    wallet: str
    username: str | None
    profile_image: str | None
    x_username: str | None
    verified: bool
    ranks: tuple[TraderRank, ...]

    def best_rank(self) -> TraderRank:
        """The single (timeframe, rank) pair used for scoring — highest quality_weight,
        ties broken by best (lowest) rank — so one trader is never double-counted
        across the leaderboards they appear on."""
        return max(self.ranks, key=lambda r: (QUALITY_WEIGHT[r.timeframe], -r.rank))

    def qualifies_for(self, timeframe: Timeframe | None, top_n: int) -> bool:
        """Whether this trader belongs in the pool for a given variant+top_n cut.

        Combined (timeframe=None): qualifies if top_n in ANY leaderboard they're on.
        A single timeframe: qualifies if top_n in THAT specific leaderboard.
        """
        if timeframe is None:
            return any(r.rank <= top_n for r in self.ranks)
        return any(r.timeframe == timeframe and r.rank <= top_n for r in self.ranks)


def trader_weight(trader: Trader, track_records: dict[str, TrackRecord]) -> float:
    best = trader.best_rank()
    base = QUALITY_WEIGHT[best.timeframe] * (MAX_LEADERBOARD_RANK + 1 - best.rank)
    return base * track_record_multiplier(track_records.get(trader.wallet))


@dataclass(frozen=True)
class TraderHolding:
    trader: Trader
    position: Position
    # trader_weight at construction time — persisted per-holder so the
    # smaller top-N cuts can be re-scored from stored data without needing
    # to re-fetch track records at read time.
    weight: float


@dataclass(frozen=True)
class ConsensusGroup:
    condition_id: str
    outcome_index: int
    outcome_label: str
    current_price: float
    holdings: tuple[TraderHolding, ...]
    whale_count: int
    combined_value: float
    consensus_score: float


def merge_leaderboards(entries_by_timeframe: dict[Timeframe, list[LeaderboardEntry]]) -> dict[str, Trader]:
    """Merge duplicate wallets across the 4 leaderboards into one Trader each,
    retaining every (timeframe, rank) appearance."""
    ranks_by_wallet: dict[str, list[TraderRank]] = defaultdict(list)
    profile_by_wallet: dict[str, LeaderboardEntry] = {}

    for timeframe, entries in entries_by_timeframe.items():
        for entry in entries:
            ranks_by_wallet[entry.proxy_wallet].append(
                TraderRank(timeframe=timeframe, rank=entry.rank, pnl=entry.pnl, vol=entry.vol)
            )
            # Prefer the entry with a username/profile image if wallet appears more than once.
            existing = profile_by_wallet.get(entry.proxy_wallet)
            if existing is None or (not existing.user_name and entry.user_name):
                profile_by_wallet[entry.proxy_wallet] = entry

    traders: dict[str, Trader] = {}
    for wallet, ranks in ranks_by_wallet.items():
        profile = profile_by_wallet[wallet]
        traders[wallet] = Trader(
            wallet=wallet,
            username=profile.user_name,
            profile_image=profile.profile_image,
            x_username=profile.x_username,
            verified=profile.verified_badge,
            ranks=tuple(ranks),
        )
    return traders


def score_from_weight_and_value(whale_score: float, combined_value: float, value_normalizer: float, max_value_boost: float) -> float:
    """The one place consensus_score is computed from its two inputs — shared
    by scan-time scoring (_score_group, below) and repository.py's read-time
    re-scoring of smaller top-N cuts derived from the persisted top_n=100
    data, so the two can never silently drift apart."""
    value_boost = min(log10(combined_value + 1) / value_normalizer, max_value_boost) if combined_value > 0 else 0.0
    return whale_score * (1 + value_boost)


def _score_group(
    holdings: list[TraderHolding],
    value_normalizer: float,
    max_value_boost: float,
) -> float:
    whale_score = sum(h.weight for h in _unique_by_trader(holdings))
    combined_value = sum(h.position.current_value for h in holdings)
    return score_from_weight_and_value(whale_score, combined_value, value_normalizer, max_value_boost)


def _unique_by_trader(holdings: list[TraderHolding]) -> list[TraderHolding]:
    """One holding per trader for score purposes (a trader shouldn't be able to
    inflate whale_score by somehow appearing twice in the same group)."""
    seen: dict[str, TraderHolding] = {}
    for h in holdings:
        seen.setdefault(h.trader.wallet, h)
    return list(seen.values())


def build_consensus_groups(
    traders: dict[str, Trader],
    positions_by_wallet: dict[str, list[Position]],
    variant: Variant,
    top_n: int,
    track_records: dict[str, TrackRecord],
    value_normalizer: float,
    max_value_boost: float,
) -> list[ConsensusGroup]:
    """Group positions by (condition_id, outcome_index) for the trader pool
    scoped to `variant` and cut to the top `top_n` of that leaderboard,
    then score and sort each group."""
    timeframe = VARIANT_TO_TIMEFRAME[variant]
    pool_wallets = {w for w, t in traders.items() if t.qualifies_for(timeframe, top_n)}

    groups: dict[tuple[str, int], list[TraderHolding]] = defaultdict(list)
    labels: dict[tuple[str, int], tuple[str, float]] = {}

    weight_by_wallet = {w: trader_weight(traders[w], track_records) for w in pool_wallets}

    for wallet in pool_wallets:
        trader = traders[wallet]
        for position in positions_by_wallet.get(wallet, []):
            key = (position.condition_id, position.outcome_index)
            groups[key].append(TraderHolding(trader=trader, position=position, weight=weight_by_wallet[wallet]))
            labels[key] = (position.outcome, position.cur_price)

    result: list[ConsensusGroup] = []
    for key, holdings in groups.items():
        outcome_label, current_price = labels[key]
        unique_holdings = _unique_by_trader(holdings)
        result.append(
            ConsensusGroup(
                condition_id=key[0],
                outcome_index=key[1],
                outcome_label=outcome_label,
                current_price=current_price,
                holdings=tuple(holdings),
                whale_count=len(unique_holdings),
                combined_value=sum(h.position.current_value for h in holdings),
                consensus_score=_score_group(holdings, value_normalizer, max_value_boost),
            )
        )

    result.sort(key=lambda g: g.consensus_score, reverse=True)
    return result
