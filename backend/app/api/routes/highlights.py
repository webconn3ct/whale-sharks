from fastapi import APIRouter, Depends

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import ConsensusSnapshot, HighlightsOut, variant_key
from app.core.consensus_engine import Variant

router = APIRouter(dependencies=[Depends(require_visitor)])

DEFAULT_TOP_N = 25
_TIMEFRAME_VARIANTS = [Variant.DAY, Variant.WEEK, Variant.MONTH, Variant.ALL_TIME]


@router.get("/highlights", response_model=HighlightsOut)
def get_highlights(snapshot: ConsensusSnapshot = Depends(get_ready_snapshot)) -> HighlightsOut:
    combined_rows = [r for r in snapshot.variants.get(variant_key(Variant.COMBINED, DEFAULT_TOP_N), []) if r.is_active]

    top_picks = combined_rows[:3]  # already sorted by consensus_score desc
    most_volume = max(combined_rows, key=lambda r: r.combined_value, default=None)

    by_timeframe = {}
    for variant in _TIMEFRAME_VARIANTS:
        rows = [r for r in snapshot.variants.get(variant_key(variant, DEFAULT_TOP_N), []) if r.is_active]
        by_timeframe[variant.value] = rows[0] if rows else None

    return HighlightsOut(top_picks=top_picks, most_volume=most_volume, by_timeframe=by_timeframe)
