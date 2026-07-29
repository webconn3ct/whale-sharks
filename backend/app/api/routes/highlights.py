from fastapi import APIRouter, Depends

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import ConsensusSnapshot, HighlightsOut, MatchupOut, TopPickOut, variant_key
from app.config import Settings, get_settings
from app.core.consensus_engine import CANONICAL_TOP_N, Variant
from app.core.recommendation import MIN_OPPOSING_WHALES, compute_lean_facts, get_reasoning

router = APIRouter(dependencies=[Depends(require_visitor)])

DEFAULT_TOP_N = 25
_TIMEFRAME_VARIANTS = [Variant.DAY, Variant.WEEK, Variant.MONTH, Variant.ALL_TIME]


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
        if row.condition_id in seen_conditions:
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

    picks: list[TopPickOut] = []
    for leader, other, _total_volume in candidates[:3]:
        facts = compute_lean_facts(leader, other)
        reasoning = await get_reasoning(settings, scan_id, f"matchup:{leader.id}:{other.id}", facts)
        picks.append(TopPickOut(kind="matchup", matchup=MatchupOut(leader=leader, other=other, reasoning=reasoning)))

    return picks


@router.get("/highlights", response_model=HighlightsOut)
async def get_highlights(
    snapshot: ConsensusSnapshot = Depends(get_ready_snapshot),
    settings: Settings = Depends(get_settings),
) -> HighlightsOut:
    combined_rows = [r for r in snapshot.variants.get(variant_key(Variant.COMBINED, DEFAULT_TOP_N), []) if r.is_active]
    widest_rows = [r for r in snapshot.variants.get(variant_key(Variant.COMBINED, CANONICAL_TOP_N), []) if r.is_active]

    top_picks = await _build_top_picks(widest_rows, settings, snapshot.scan_id)
    most_volume = max(combined_rows, key=lambda r: r.combined_value, default=None)

    by_timeframe = {}
    for variant in _TIMEFRAME_VARIANTS:
        rows = [r for r in snapshot.variants.get(variant_key(variant, DEFAULT_TOP_N), []) if r.is_active]
        by_timeframe[variant.value] = rows[0] if rows else None

    return HighlightsOut(top_picks=top_picks, most_volume=most_volume, by_timeframe=by_timeframe)
