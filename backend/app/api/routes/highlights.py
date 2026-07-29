from fastapi import APIRouter, Depends

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import ConsensusSnapshot, HighlightsOut, MatchupOut, TopPickOut, variant_key
from app.config import Settings, get_settings
from app.core.consensus_engine import Variant
from app.core.recommendation import compute_lean_facts, get_reasoning
from app.db import repository
from app.db.session import get_session

router = APIRouter(dependencies=[Depends(require_visitor)])

DEFAULT_TOP_N = 25
MIN_OPPOSING_WHALES = 2  # below this, an opposing position is noise, not a real conflict
_TIMEFRAME_VARIANTS = [Variant.DAY, Variant.WEEK, Variant.MONTH, Variant.ALL_TIME]


async def _build_top_picks(
    combined_rows: list, settings: Settings, scan_id: int, min_whales: int, score_threshold: float
) -> list[TopPickOut]:
    # Top picks are markets that actually clear KrillBot's own entry bar —
    # not an independently-tuned "best of" cut — so the spotlight genuinely
    # reflects what the bot is trading on, not a separate editorial pick.
    qualifying_rows = [r for r in combined_rows if r.whale_count >= min_whales and r.consensus_score >= score_threshold]

    by_condition: dict[str, list] = {}
    for r in combined_rows:
        by_condition.setdefault(r.condition_id, []).append(r)

    picks: list[TopPickOut] = []
    used_conditions: set[str] = set()

    for row in qualifying_rows:
        if len(picks) >= 3:
            break
        if row.condition_id in used_conditions:
            continue
        used_conditions.add(row.condition_id)

        siblings = by_condition[row.condition_id]
        opposing = max(
            (s for s in siblings if s.id != row.id and s.whale_count >= MIN_OPPOSING_WHALES),
            key=lambda s: s.consensus_score,
            default=None,
        )

        if opposing is None:
            picks.append(TopPickOut(kind="single", single=row))
            continue

        leader, other = (row, opposing) if row.consensus_score >= opposing.consensus_score else (opposing, row)
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

    async with get_session() as session:
        bot_state = await repository.get_or_create_bot_state(session)

    top_picks = await _build_top_picks(
        combined_rows, settings, snapshot.scan_id, int(bot_state.entry_min_whales), float(bot_state.entry_score_threshold)
    )
    most_volume = max(combined_rows, key=lambda r: r.combined_value, default=None)

    by_timeframe = {}
    for variant in _TIMEFRAME_VARIANTS:
        rows = [r for r in snapshot.variants.get(variant_key(variant, DEFAULT_TOP_N), []) if r.is_active]
        by_timeframe[variant.value] = rows[0] if rows else None

    return HighlightsOut(top_picks=top_picks, most_volume=most_volume, by_timeframe=by_timeframe)
