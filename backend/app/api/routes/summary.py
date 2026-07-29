from fastapi import APIRouter, Depends

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import ConsensusSnapshot, SummaryOut, variant_key
from app.core.consensus_engine import Variant

router = APIRouter(dependencies=[Depends(require_visitor)])


@router.get("/summary", response_model=SummaryOut)
def get_summary(snapshot: ConsensusSnapshot = Depends(get_ready_snapshot)) -> SummaryOut:
    default_rows = snapshot.variants.get(variant_key(Variant.COMBINED, 25), [])
    active_count = sum(1 for r in default_rows if r.is_active)
    return SummaryOut(
        tracked_traders=snapshot.tracked_traders,
        active_positions=snapshot.active_positions,
        consensus_markets=active_count,
        total_whale_exposure=snapshot.total_whale_exposure,
        last_refresh_at=snapshot.last_refresh_at,
    )
