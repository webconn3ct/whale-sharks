from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import ConsensusSnapshot, HighlightsOut, MatchupOut, TopPickOut, variant_key
from app.config import Settings, get_settings
from app.core.consensus_engine import CANONICAL_TOP_N, Variant
from app.core.recommendation import MIN_OPPOSING_WHALES, compute_lean_facts, get_reasoning
from app.db import repository
from app.db.session import get_session

router = APIRouter(dependencies=[Depends(require_visitor)])

DEFAULT_TOP_N = 25
_TIMEFRAME_VARIANTS = [Variant.WEEK, Variant.MONTH, Variant.ALL_TIME]

# Every whale-spotlight slot (all 5 boxes, not just the 3 "Markets" cards)
# deliberately stays off politics/geopolitics — it's the single biggest
# category by volume and would otherwise crowd out every slot. Still fully
# visible/searchable in the main table — this only affects the spotlight.
# Real category tags observed in production (see `markets.category`): the
# flat "Politics" bucket plus more specific election/office/geopolitical
# tags that don't roll up into it.
_EXCLUDED_TOP_PICK_KEYWORDS = (
    "politic", "election", "midterm", "primaries", "president", "congress", "senate", "governor",
    "united states", "military", "nato", "geopolitic",
)


def _is_political(category: str | None) -> bool:
    if not category:
        return False
    lowered = category.lower()
    return any(keyword in lowered for keyword in _EXCLUDED_TOP_PICK_KEYWORDS)


def _is_daily_sports(row) -> bool:
    """Strictly "Sports" category (not a keyword guess — the exact tag, so a
    stray "Esports"/"Motorsport"-style category can't slip through) and
    scheduled to play within about a day, so the top-3 "Markets" cards read
    as today's games, not a market that happens to also be tagged sports."""
    if row.category != "Sports":
        return False
    if row.end_date is None:
        return False
    now = datetime.now(UTC)
    return now - timedelta(hours=12) <= row.end_date <= now + timedelta(hours=36)


async def _build_top_picks(matchup_pool: list, settings: Settings, scan_id: int) -> list[TopPickOut]:
    """The 3 "Markets" cards: the highest-volume genuine sports matchups
    happening today — real whale money on both sides, ranked by combined
    dollar value, not by consensus score. `matchup_pool` should be the
    widest available cut so a high-volume market with a merely middling
    score still surfaces. Strictly sports-only — no politics, weather,
    crypto, or anything else, regardless of volume."""
    by_condition: dict[str, list] = {}
    for r in matchup_pool:
        by_condition.setdefault(r.condition_id, []).append(r)

    candidates: list[tuple] = []  # (leader, other, total_volume)
    seen_conditions: set[str] = set()

    for row in matchup_pool:
        if row.condition_id in seen_conditions or not _is_daily_sports(row):
            continue
        siblings = by_condition[row.condition_id]
        opposing = max(
            (s for s in siblings if s.id != row.id and s.whale_count >= MIN_OPPOSING_WHALES),
            key=lambda s: s.consensus_score,
            default=None,
        )
        if opposing is None:
            continue
        seen_conditions.add(row.condition_id)
        leader, other = (row, opposing) if row.consensus_score >= opposing.consensus_score else (opposing, row)
        candidates.append((leader, other, leader.combined_value + other.combined_value))

    candidates.sort(key=lambda c: c[2], reverse=True)

    # The same real-world game can spawn several markets (different point
    # totals, alternate lines, etc.) that share an event_slug but have
    # different condition_ids — only the single highest-volume one per event
    # gets a slot, so the same matchup never fills two of the three cards.
    selected: list[tuple] = []
    seen_events: set[str] = set()
    for candidate in candidates:
        if len(selected) >= 3:
            break
        event_slug = candidate[0].event_slug
        if event_slug and event_slug in seen_events:
            continue
        if event_slug:
            seen_events.add(event_slug)
        selected.append(candidate)

    picks: list[TopPickOut] = []
    for leader, other, _total_volume in selected:
        facts = compute_lean_facts(leader, other)
        reasoning = await get_reasoning(settings, scan_id, f"matchup:{leader.id}:{other.id}", facts)
        picks.append(TopPickOut(kind="matchup", matchup=MatchupOut(leader=leader, other=other, reasoning=reasoning)))

    return picks


async def _get_daily_catch(snapshot: ConsensusSnapshot):
    """The "Daily Catch" card is picked once per calendar day (UTC) — highest
    whale rating in the DAY variant at pick time — and locked there for the
    rest of the day instead of being able to flip on every 15-minute scan.
    Concurrent requests can't create duplicate picks for the same day (a
    unique constraint + re-fetch-after-insert resolves any race)."""
    today = datetime.now(UTC).date()
    async with get_session() as session:
        pick = await repository.get_daily_catch_pick(session, today)

        if pick is None:
            day_rows = [
                r for r in snapshot.variants.get(variant_key(Variant.DAY, DEFAULT_TOP_N), [])
                if r.is_active and not _is_political(r.category)
            ]
            if not day_rows:
                return None  # nothing to pick yet today — frontend shows a loading state
            best = max(day_rows, key=lambda r: r.consensus_score)
            await repository.create_daily_catch_pick(session, today, best.condition_id, best.outcome_index)
            pick = await repository.get_daily_catch_pick(session, today)
            if pick is None:
                return best

    wide_day_rows = snapshot.variants.get(variant_key(Variant.DAY, CANONICAL_TOP_N), [])
    return next(
        (r for r in wide_day_rows if r.condition_id == pick.condition_id and r.outcome_index == pick.outcome_index),
        None,
    )


@router.get("/highlights", response_model=HighlightsOut)
async def get_highlights(
    snapshot: ConsensusSnapshot = Depends(get_ready_snapshot),
    settings: Settings = Depends(get_settings),
) -> HighlightsOut:
    combined_rows = [r for r in snapshot.variants.get(variant_key(Variant.COMBINED, DEFAULT_TOP_N), []) if r.is_active]
    widest_rows = [r for r in snapshot.variants.get(variant_key(Variant.COMBINED, CANONICAL_TOP_N), []) if r.is_active]

    top_picks = await _build_top_picks(widest_rows, settings, snapshot.scan_id)
    non_political_rows = [r for r in combined_rows if not _is_political(r.category)]
    most_volume = max(non_political_rows, key=lambda r: r.combined_value, default=None)

    by_timeframe = {Variant.DAY.value: await _get_daily_catch(snapshot)}
    for variant in _TIMEFRAME_VARIANTS:
        rows = [r for r in snapshot.variants.get(variant_key(variant, DEFAULT_TOP_N), []) if r.is_active]
        by_timeframe[variant.value] = rows[0] if rows else None

    return HighlightsOut(top_picks=top_picks, most_volume=most_volume, by_timeframe=by_timeframe)
