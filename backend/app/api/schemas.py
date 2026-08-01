from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.consensus_engine import Variant
from app.integrations.polymarket_client import Timeframe


def variant_key(variant: Variant, top_n: int) -> str:
    """Cache/wire key for a (leaderboard scope, top-N cut) pair, e.g. 'week:50'."""
    return f"{variant.value}:{top_n}"


class HolderOut(BaseModel):
    wallet: str
    username: str | None
    profile_image: str | None
    verified: bool
    best_timeframe: Timeframe
    best_rank: int
    position_value: float
    size: float
    avg_entry_price: float
    current_price: float
    cash_pnl: float
    percent_pnl: float
    # Shrunk hit-rate on this trader's own resolved Polymarket positions —
    # None until they have at least one resolved position on record. Distinct
    # from leaderboard rank (which reflects total PnL, not accuracy).
    win_rate: float | None = None
    recent_form: float | None = None
    # This trader's dollar value on OTHER outcomes of this same market, if
    # any — None when they hold only this side. Present, they're hedged.
    hedge_opposing_value: float | None = None


class ConsensusRowOut(BaseModel):
    id: str  # f"{condition_id}:{outcome_index}" — stable within a variant
    condition_id: str
    outcome_index: int
    outcome_label: str
    market_title: str
    market_slug: str
    event_slug: str
    category: str | None
    image_url: str | None
    end_date: datetime | None
    is_active: bool
    current_price: float
    whale_count: int
    combined_value: float
    consensus_score: float
    holders: list[HolderOut] = []


class PaginatedConsensusOut(BaseModel):
    items: list[ConsensusRowOut]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class SummaryOut(BaseModel):
    tracked_traders: int
    active_positions: int
    consensus_markets: int
    total_whale_exposure: float
    last_refresh_at: datetime | None


class TeaserOut(BaseModel):
    """Deliberately minimal, unauthenticated — the login-page teaser. No
    market names, picks, or trader identities, just aggregate numbers and
    KrillBot's real equity curve shape."""

    tracked_traders: int
    total_whale_exposure: float
    active_markets: int
    bot_return_pct: float
    bot_win_count: int
    bot_loss_count: int
    bot_equity_curve: list[float]


class HealthOut(BaseModel):
    status: str
    ready: bool
    last_refresh_at: datetime | None


class LeanOut(BaseModel):
    """Data-backed 'which way to lean' recommendation for a single market,
    shown in the market detail view."""

    facts: dict
    reasoning: str


class MatchupOut(BaseModel):
    """Two opposing outcomes of the SAME market that both scored high enough
    to be a top pick — shown together with reasoning instead of as two
    separate, contradictory picks."""

    leader: ConsensusRowOut  # higher consensus_score side
    other: ConsensusRowOut  # lower consensus_score side


class TopPickOut(BaseModel):
    kind: Literal["single", "matchup"]
    single: ConsensusRowOut | None = None
    matchup: MatchupOut | None = None


class HighlightsOut(BaseModel):
    """Curated picks shown in the 'recommendations' strip above the table."""

    top_picks: list[TopPickOut]  # top 3 slots by consensus_score, combined/top25
    most_volume: ConsensusRowOut | None  # highest combined_value, combined/top25
    by_timeframe: dict[str, ConsensusRowOut | None]  # "day"/"week"/"month"/"all_time" -> #1 pick


class ConsensusSnapshot(BaseModel):
    """One immutable, fully-serialized dataset — what ConsensusCache holds and
    what gets swapped in atomically after each scan.

    `variants` is keyed by `variant_key(variant, top_n)` — one entry per
    (leaderboard scope, top-N cut) combination precomputed at scan time.
    """

    scan_id: int
    last_refresh_at: datetime
    tracked_traders: int
    active_positions: int
    total_whale_exposure: float
    variants: dict[str, list[ConsensusRowOut]]

    def categories(self) -> list[str]:
        """Only categories with at least one currently-active trade — an
        option for a category nobody's actively holding is dead weight in
        the filter dropdown."""
        cats: set[str] = set()
        for rows in self.variants.values():
            for row in rows:
                if row.category and row.is_active:
                    cats.add(row.category)
        return sorted(cats)


class BotPositionOut(BaseModel):
    id: int
    condition_id: str
    outcome_index: int
    outcome_label: str
    market_title: str
    category: str | None
    status: str
    stake: float
    shares: float
    entry_price: float
    entry_at: datetime
    entry_consensus_score: float
    entry_whale_count: int
    entry_reasoning: str | None
    current_price: float | None = None  # mark-to-market, open positions only
    exit_price: float | None = None
    exit_at: datetime | None = None
    exit_reason: str | None = None
    realized_pnl: float | None = None


class PaginatedBotPositionsOut(BaseModel):
    items: list[BotPositionOut]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class BotStateOut(BaseModel):
    cash_balance: float
    starting_balance: float
    open_positions_value: float
    total_value: float
    percent_return: float
    open_positions_count: int
    entry_min_whales: int
    entry_score_threshold: float
    last_recalibrated_at: datetime | None


class BotRecalibrationOut(BaseModel):
    at: datetime
    reasoning: str
    old_thresholds: dict
    new_thresholds: dict
