from datetime import UTC, datetime

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

# The "Markets" spotlight slots deliberately stay off politics — it's the
# single biggest category by volume and would otherwise crowd out every
# slot. Real category tags observed in production (see `markets.category`):
# the flat "Politics" bucket plus more specific election/office tags that
# don't roll up into it.
_EXCLUDED_TOP_PICK_KEYWORDS = ("politic", "election", "midterm", "primaries", "president", "congress", "senate", "governor")


def _is_political(category: str | None) -> bool:
    if not category:
        return False
    lowered = category.lower()
    return any(keyword in lowered for keyword in _EXCLUDED_TOP_PICK_KEYWORDS)


async def _build_top_picks(matchup_pool: list, settings: Settings, scan_id: int) -> list[TopPickOut]:
    """The 3 "Markets" cards: the highest-volume genuine matchups right now —
    real whale money on both sides, ranked by combined dollar value, not by
    consensus score. `matchup_pool` should be the widest available cut so a
    high-volume market with a merely middling score still surfaces."""
    by_condition: dict[str, list] = {}
    for r in matchup_pool:
        by_condition.setdefault(r.condition_id, []).append(r)

    candidates: list[tuple] = []  # (leader, other, total_volume)
    seen_conditions: set[str] = set()

    for row in matchup_pool:
        if row.condition_id in seen_conditions or _is_political(row.category):
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

    selected = candidates[:3]
    # High-volume markets skew heavily toward politics, which can crowd out
    # every slot — guarantee at least one Sports matchup when one exists,
    # swapping in for the lowest-volume slot rather than a top one.
    if selected and not any(c[0].category == "Sports" for c in selected):
        best_sports = next((c for c in candidates if c[0].category == "Sports"), None)
        if best_sports is not None:
            selected = selected[:-1] + [best_sports]
            selected.sort(key=lambda c: c[2], reverse=True)

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
            day_rows = [r for r in snapshot.variants.get(variant_key(Variant.DAY, DEFAULT_TOP_N), []) if r.is_active]
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
    most_volume = max(combined_rows, key=lambda r: r.combined_value, default=None)

    by_timeframe = {Variant.DAY.value: await _get_daily_catch(snapshot)}
    for variant in _TIMEFRAME_VARIANTS:
        rows = [r for r in snapshot.variants.get(variant_key(variant, DEFAULT_TOP_N), []) if r.is_active]
        by_timeframe[variant.value] = rows[0] if rows else None

    return HighlightsOut(top_picks=top_picks, most_volume=most_volume, by_timeframe=by_timeframe)
