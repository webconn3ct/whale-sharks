from datetime import datetime

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


class SummaryOut(BaseModel):
    tracked_traders: int
    active_positions: int
    consensus_markets: int
    total_whale_exposure: float
    last_refresh_at: datetime | None


class HealthOut(BaseModel):
    status: str
    ready: bool
    last_refresh_at: datetime | None


class HighlightsOut(BaseModel):
    """Curated picks shown in the 'recommendations' strip above the table."""

    top_picks: list[ConsensusRowOut]  # top 2 by consensus_score, combined/top25
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
        cats: set[str] = set()
        for rows in self.variants.values():
            for row in rows:
                if row.category:
                    cats.add(row.category)
        return sorted(cats)
