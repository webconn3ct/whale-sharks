from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import ConsensusRowOut, ConsensusSnapshot, variant_key
from app.core.consensus_engine import TOP_N_OPTIONS, Variant

router = APIRouter(dependencies=[Depends(require_visitor)])


def _validated_top_n(top_n: int = Query(default=25)) -> int:
    if top_n not in TOP_N_OPTIONS:
        raise HTTPException(status_code=400, detail=f"top_n must be one of {TOP_N_OPTIONS}")
    return top_n


@router.get("/consensus", response_model=list[ConsensusRowOut])
def list_consensus(
    snapshot: ConsensusSnapshot = Depends(get_ready_snapshot),
    timeframe: Variant = Query(default=Variant.COMBINED),
    top_n: int = Depends(_validated_top_n),
    status: Literal["active", "finished", "all"] = Query(default="active"),
    category: str | None = None,
    min_whales: int = Query(default=0, ge=0),
    min_value: float = Query(default=0, ge=0),
    search: str | None = None,
) -> list[ConsensusRowOut]:
    rows = snapshot.variants.get(variant_key(timeframe, top_n), [])

    if status == "active":
        rows = [r for r in rows if r.is_active]
    elif status == "finished":
        rows = [r for r in rows if not r.is_active]
    if category:
        rows = [r for r in rows if r.category == category]
    if min_whales:
        rows = [r for r in rows if r.whale_count >= min_whales]
    if min_value:
        rows = [r for r in rows if r.combined_value >= min_value]
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in r.market_title.lower()]

    return rows


@router.get("/consensus/{row_id}", response_model=ConsensusRowOut)
def get_consensus_detail(
    row_id: str,
    snapshot: ConsensusSnapshot = Depends(get_ready_snapshot),
    timeframe: Variant = Query(default=Variant.COMBINED),
    top_n: int = Depends(_validated_top_n),
) -> ConsensusRowOut:
    rows = snapshot.variants.get(variant_key(timeframe, top_n), [])
    for row in rows:
        if row.id == row_id:
            return row
    raise HTTPException(status_code=404, detail="Consensus position not found")


@router.get("/categories", response_model=list[str])
def list_categories(snapshot: ConsensusSnapshot = Depends(get_ready_snapshot)) -> list[str]:
    return snapshot.categories()


@router.get("/top-n-options", response_model=list[int])
def list_top_n_options() -> list[int]:
    return list(TOP_N_OPTIONS)
