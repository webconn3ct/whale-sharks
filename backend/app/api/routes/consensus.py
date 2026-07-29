from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_ready_snapshot, require_visitor
from app.api.schemas import ConsensusRowOut, ConsensusSnapshot, LeanOut, PaginatedConsensusOut, variant_key
from app.config import Settings, get_settings
from app.core.consensus_engine import TOP_N_OPTIONS, Variant
from app.core.recommendation import MIN_OPPOSING_WHALES, compute_lean_facts, get_reasoning

router = APIRouter(dependencies=[Depends(require_visitor)])

PAGE_SIZE = 100


def _validated_top_n(top_n: int = Query(default=25)) -> int:
    if top_n not in TOP_N_OPTIONS:
        raise HTTPException(status_code=400, detail=f"top_n must be one of {TOP_N_OPTIONS}")
    return top_n


def _matches_search(title: str, search: str) -> bool:
    """Keyword/phrase search: every word in `search` must appear somewhere in
    the title (case-insensitive, any order) — an exact phrase still matches
    since its words are a subset of that check, but multi-word keyword
    queries (e.g. "election senate") also match titles containing both words
    in a different order."""
    title_lower = title.lower()
    return all(word in title_lower for word in search.lower().split())


@router.get("/consensus", response_model=PaginatedConsensusOut)
def list_consensus(
    snapshot: ConsensusSnapshot = Depends(get_ready_snapshot),
    timeframe: Variant = Query(default=Variant.COMBINED),
    top_n: int = Depends(_validated_top_n),
    status: Literal["active", "finished", "all"] = Query(default="active"),
    category: str | None = None,
    min_whales: int = Query(default=0, ge=0),
    min_value: float = Query(default=0, ge=0),
    search: str | None = None,
    page: int = Query(default=1, ge=1),
) -> PaginatedConsensusOut:
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
    if search and search.strip():
        rows = [r for r in rows if _matches_search(r.market_title, search.strip())]

    total_items = len(rows)
    total_pages = max(1, -(-total_items // PAGE_SIZE))  # ceil div
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_items = rows[start : start + PAGE_SIZE]

    return PaginatedConsensusOut(
        items=page_items, page=page, page_size=PAGE_SIZE, total_items=total_items, total_pages=total_pages
    )


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


@router.get("/consensus/{row_id}/lean", response_model=LeanOut)
async def get_consensus_lean(
    row_id: str,
    snapshot: ConsensusSnapshot = Depends(get_ready_snapshot),
    settings: Settings = Depends(get_settings),
    timeframe: Variant = Query(default=Variant.COMBINED),
    top_n: int = Depends(_validated_top_n),
) -> LeanOut:
    rows = snapshot.variants.get(variant_key(timeframe, top_n), [])
    row = next((r for r in rows if r.id == row_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Consensus position not found")

    opposing = max(
        (r for r in rows if r.condition_id == row.condition_id and r.id != row.id and r.whale_count >= MIN_OPPOSING_WHALES),
        key=lambda r: r.consensus_score,
        default=None,
    )

    facts = compute_lean_facts(row, opposing)
    reasoning = await get_reasoning(settings, snapshot.scan_id, f"lean:{row.id}:{opposing.id if opposing else 'none'}", facts)
    return LeanOut(facts=facts, reasoning=reasoning)


@router.get("/categories", response_model=list[str])
def list_categories(snapshot: ConsensusSnapshot = Depends(get_ready_snapshot)) -> list[str]:
    return snapshot.categories()


@router.get("/top-n-options", response_model=list[int])
def list_top_n_options() -> list[int]:
    return list(TOP_N_OPTIONS)
