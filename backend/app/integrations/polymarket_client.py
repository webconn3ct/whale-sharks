"""Thin async client around Polymarket's public data-api and gamma-api.

No authentication is required for any of these endpoints. All verified
against docs.polymarket.com and the live API (July 2026):
  - GET {data_api}/v1/leaderboard
  - GET {data_api}/positions
  - GET {data_api}/closed-positions
  - GET {gamma_api}/markets
"""

import asyncio
import logging
from enum import StrEnum

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings

logger = logging.getLogger(__name__)


class Timeframe(StrEnum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    ALL = "ALL"


class LeaderboardEntry(BaseModel):
    rank: int
    proxy_wallet: str = Field(alias="proxyWallet")
    user_name: str | None = Field(default=None, alias="userName")
    vol: float = 0.0
    pnl: float = 0.0
    profile_image: str | None = Field(default=None, alias="profileImage")
    x_username: str | None = Field(default=None, alias="xUsername")
    verified_badge: bool = Field(default=False, alias="verifiedBadge")

    model_config = {"populate_by_name": True}


class Position(BaseModel):
    """Only fields actually consumed by consensus_engine/repository are kept —
    market title/slug/icon/event_slug/end_date come from a separate Gamma
    metadata fetch instead, and duplicating them here across every trader's
    position in the same market wastes real memory at scan scale."""

    proxy_wallet: str = Field(alias="proxyWallet")
    condition_id: str = Field(alias="conditionId")
    size: float = 0.0
    avg_price: float = Field(default=0.0, alias="avgPrice")
    current_value: float = Field(default=0.0, alias="currentValue")
    cash_pnl: float = Field(default=0.0, alias="cashPnl")
    percent_pnl: float = Field(default=0.0, alias="percentPnl")
    cur_price: float = Field(default=0.0, alias="curPrice")
    outcome: str = ""
    outcome_index: int = Field(default=0, alias="outcomeIndex")

    model_config = {"populate_by_name": True}


class ClosedPosition(BaseModel):
    """A resolved position — realized_pnl > 0 means the trader was right."""

    proxy_wallet: str = Field(alias="proxyWallet")
    condition_id: str = Field(alias="conditionId")
    realized_pnl: float = Field(default=0.0, alias="realizedPnl")
    title: str = ""
    outcome: str = ""
    timestamp: int = 0

    model_config = {"populate_by_name": True}


class MarketMetadata(BaseModel):
    condition_id: str
    title: str = ""
    slug: str = ""
    event_slug: str = ""
    category: str | None = None
    image_url: str | None = None
    end_date: str | None = None
    active: bool = True


RETRYABLE = retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError))


def _retry():
    return retry(
        retry=RETRYABLE,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        reraise=True,
    )


class PolymarketClient:
    """Owns a shared httpx.AsyncClient; construct once per process, close on shutdown."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._http = httpx.AsyncClient(timeout=15.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    # Polymarket caps a single /v1/leaderboard request's `limit` at 50.
    _LEADERBOARD_PAGE_SIZE = 50

    @_retry()
    async def _fetch_leaderboard_page(self, timeframe: Timeframe, limit: int, offset: int) -> list[LeaderboardEntry]:
        resp = await self._http.get(
            f"{self._settings.polymarket_data_api_base}/v1/leaderboard",
            params={"timePeriod": timeframe.value, "orderBy": "PNL", "limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        return [LeaderboardEntry.model_validate(row) for row in resp.json()]

    async def fetch_leaderboard(self, timeframe: Timeframe, limit: int | None = None) -> list[LeaderboardEntry]:
        """Fetch the top `limit` traders for a leaderboard, paginating in
        50-row pages (the API's per-request cap) until `limit` is reached."""
        limit = limit or self._settings.leaderboard_size
        entries: list[LeaderboardEntry] = []
        offset = 0
        while len(entries) < limit:
            take = min(self._LEADERBOARD_PAGE_SIZE, limit - len(entries))
            page = await self._fetch_leaderboard_page(timeframe, take, offset)
            entries.extend(page)
            if len(page) < take:
                break  # leaderboard has fewer entries than requested
            offset += take
        return entries

    @_retry()
    async def _fetch_positions_one(self, wallet: str) -> list[Position]:
        resp = await self._http.get(
            f"{self._settings.polymarket_data_api_base}/positions",
            params={
                "user": wallet,
                "sizeThreshold": self._settings.min_position_value,
                "limit": 500,
                "sortBy": "CURRENT",
                "sortDirection": "DESC",
            },
        )
        resp.raise_for_status()
        return [Position.model_validate(row) for row in resp.json()]

    async def fetch_positions_for_wallets(self, wallets: list[str]) -> dict[str, list[Position]]:
        """Fetch positions for many wallets concurrently.

        A single wallet's fetch failing (after retries) is logged and excluded
        from the result rather than aborting the whole batch — scan_service
        decides whether the overall failure rate is acceptable.
        """
        semaphore = asyncio.Semaphore(self._settings.position_fetch_concurrency)

        async def _bounded(wallet: str) -> tuple[str, list[Position] | None]:
            async with semaphore:
                try:
                    return wallet, await self._fetch_positions_one(wallet)
                except httpx.HTTPError as exc:
                    logger.warning("positions fetch failed for %s: %s", wallet, exc)
                    return wallet, None

        results = await asyncio.gather(*(_bounded(w) for w in wallets))
        return {wallet: positions for wallet, positions in results if positions is not None}

    # Max allowed by /closed-positions; enough to compute a stable win rate
    # while keeping the per-trader payload small.
    CLOSED_POSITIONS_LIMIT = 50

    @_retry()
    async def _fetch_closed_positions_one(self, wallet: str) -> list[ClosedPosition]:
        resp = await self._http.get(
            f"{self._settings.polymarket_data_api_base}/closed-positions",
            params={
                "user": wallet,
                "limit": self.CLOSED_POSITIONS_LIMIT,
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC",
            },
        )
        resp.raise_for_status()
        return [ClosedPosition.model_validate(row) for row in resp.json()]

    async def fetch_closed_positions_for_wallets(self, wallets: list[str]) -> dict[str, list[ClosedPosition]]:
        """Same bounded-concurrency, best-effort pattern as fetch_positions_for_wallets —
        a wallet with no resolved history yet (or a failed fetch) is just absent
        from the result; callers treat that as "no track record data available"."""
        semaphore = asyncio.Semaphore(self._settings.position_fetch_concurrency)

        async def _bounded(wallet: str) -> tuple[str, list[ClosedPosition] | None]:
            async with semaphore:
                try:
                    return wallet, await self._fetch_closed_positions_one(wallet)
                except httpx.HTTPError as exc:
                    logger.warning("closed-positions fetch failed for %s: %s", wallet, exc)
                    return wallet, None

        results = await asyncio.gather(*(_bounded(w) for w in wallets))
        return {wallet: positions for wallet, positions in results if positions is not None}

    @_retry()
    async def _fetch_market_metadata_batch(self, condition_ids: list[str]) -> dict[str, MarketMetadata]:
        resp = await self._http.get(
            f"{self._settings.polymarket_gamma_api_base}/markets",
            # include_tag=true is required to get `tags` back — despite docs.polymarket.com
            # showing a flat `category` field, live /markets responses don't have one;
            # the closest equivalent is the first (broadest) tag's label.
            params={"condition_ids": condition_ids, "limit": len(condition_ids), "include_tag": "true"},
        )
        resp.raise_for_status()
        out: dict[str, MarketMetadata] = {}
        for row in resp.json():
            condition_id = row.get("conditionId")
            if not condition_id:
                continue
            tags = row.get("tags") or []
            out[condition_id] = MarketMetadata(
                condition_id=condition_id,
                title=row.get("question") or row.get("title") or "",
                slug=row.get("slug") or "",
                event_slug=(row.get("events") or [{}])[0].get("slug", "") if row.get("events") else "",
                category=tags[0].get("label") if tags else None,
                image_url=row.get("image") or row.get("icon"),
                end_date=row.get("endDate"),
                active=bool(row.get("active", True)) and not bool(row.get("closed", False)),
            )
        return out

    async def fetch_market_metadata(self, condition_ids: list[str]) -> dict[str, MarketMetadata]:
        """Batch-fetch market metadata from Gamma for markets not yet cached / stale.

        Chunked — Gamma's /markets accepts repeated condition_ids query params,
        but a scan can touch thousands of distinct markets and a single request
        with that many params blows past the URL length limit.
        """
        if not condition_ids:
            return {}
        batch_size = self._settings.gamma_batch_size
        batches = [condition_ids[i : i + batch_size] for i in range(0, len(condition_ids), batch_size)]
        semaphore = asyncio.Semaphore(self._settings.position_fetch_concurrency)

        async def _bounded(batch: list[str]) -> dict[str, MarketMetadata]:
            async with semaphore:
                try:
                    return await self._fetch_market_metadata_batch(batch)
                except httpx.HTTPError as exc:
                    logger.warning("gamma metadata batch fetch failed for %d markets: %s", len(batch), exc)
                    return {}

        results = await asyncio.gather(*(_bounded(b) for b in batches))
        merged: dict[str, MarketMetadata] = {}
        for r in results:
            merged.update(r)
        return merged
