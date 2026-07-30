"""Thin async client around MLB's free, official statsapi.mlb.com — no
authentication, no rate-limit tier to worry about. Used only for the
cold-favorite veto's recent-form lookup (app/core/mlb_form.py).
"""

import logging
from datetime import UTC, date, datetime, timedelta

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://statsapi.mlb.com/api/v1"
SPORT_ID_MLB = 1

RETRYABLE = retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError))


def _retry():
    return retry(
        retry=RETRYABLE,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        reraise=True,
    )


class MLBTeam:
    __slots__ = ("id", "name", "nickname")

    def __init__(self, id: int, name: str, nickname: str):
        self.id = id
        self.name = name
        self.nickname = nickname


class MLBClient:
    """Owns a shared httpx.AsyncClient; construct once per process, close on shutdown."""

    def __init__(self):
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    @_retry()
    async def list_teams(self) -> list[MLBTeam]:
        resp = await self._http.get("/teams", params={"sportId": SPORT_ID_MLB, "activeStatus": "Yes"})
        resp.raise_for_status()
        return [
            MLBTeam(id=t["id"], name=t["name"], nickname=t["teamName"])
            for t in resp.json().get("teams", [])
            if "id" in t and "name" in t and "teamName" in t
        ]

    @_retry()
    async def recent_results(self, team_id: int, lookback_days: int = 21) -> list[bool]:
        """Most-recent-first win/loss for this team's completed games in the
        lookback window. Empty list if the team has no completed games in
        range (e.g. off-season, or a rain-delayed start of season)."""
        end = datetime.now(UTC).date()
        start = end - timedelta(days=lookback_days)
        resp = await self._http.get(
            "/schedule",
            params={
                "sportId": SPORT_ID_MLB,
                "teamId": team_id,
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
            },
        )
        resp.raise_for_status()
        data = resp.json()

        games: list[tuple[str, bool]] = []
        for day in data.get("dates", []):
            for game in day.get("games", []):
                if game.get("status", {}).get("codedGameState") != "F":  # Final only
                    continue
                is_home = game.get("teams", {}).get("home", {}).get("team", {}).get("id") == team_id
                side = "home" if is_home else "away"
                won = game.get("teams", {}).get(side, {}).get("isWinner")
                if won is None:
                    continue
                games.append((game.get("gameDate", ""), bool(won)))

        games.sort(key=lambda g: g[0], reverse=True)
        return [won for _, won in games]
