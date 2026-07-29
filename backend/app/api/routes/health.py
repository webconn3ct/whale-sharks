from fastapi import APIRouter

from app.api.schemas import HealthOut
from app.core.cache import cache

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    snapshot = cache.snapshot
    return HealthOut(
        status="ok",
        ready=snapshot is not None,
        last_refresh_at=snapshot.last_refresh_at if snapshot else None,
    )
