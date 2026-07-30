"""Cold-favorite veto, MLB slice.

Same bounded-gate contract as bot_research.py: the whale-consensus signal
is what makes a market a candidate at all. This gate only fires for
candidates that already cleared that bar, and its only power is to
DOWNSIZE — never veto outright, never independently create a trade —
when the specific team the bot is about to back is on a validated cold
recent-form streak the whale-rank data can't see (whale leaderboard rank
reflects a trader's historical skill, not whether their team happens to
be playing badly this week).

Threshold is not a guess — it's the exact cutoff validated in
research/sports-signals/scripts/baseball_factors.py against a real,
chronological train/holdout split on 2000-2025 Retrosheet game logs:
teams with recent_form < 0.3 (won fewer than 3 of their last 10 games)
won only 42.5% of their holdout games, vs a 53.1% baseline home-win rate
in the same window. That's a real, out-of-sample effect — but a much
smaller one than tennis's (36% -> 47.6%), so this only ever downsizes,
never vetoes, unlike a clear red-flag news finding.

Zero Anthropic API calls — this is pure structured data plus a numeric
threshold check.
"""

import logging
import re
from datetime import UTC, datetime, timedelta

import httpx

from app.integrations.mlb_client import MLBClient, MLBTeam

logger = logging.getLogger(__name__)

COLD_THRESHOLD = 0.3
LOOKBACK_GAMES = 10
MIN_GAMES_FOR_SIGNAL = 5  # matches the validated study's min_periods=5

_TEAM_CACHE_TTL = timedelta(hours=24)
_FORM_CACHE_TTL = timedelta(hours=3)

_team_cache: list[MLBTeam] = []
_team_cache_at: datetime | None = None
_form_cache: dict[int, tuple[datetime, list[bool]]] = {}


async def _get_teams(client: MLBClient) -> list[MLBTeam]:
    global _team_cache, _team_cache_at
    now = datetime.now(UTC)
    if _team_cache and _team_cache_at and now - _team_cache_at < _TEAM_CACHE_TTL:
        return _team_cache
    try:
        teams = await client.list_teams()
    except httpx.HTTPError:
        logger.warning("MLB team list fetch failed — cold-favorite gate unavailable this cycle")
        return _team_cache  # serve stale if we have any, else empty (gate no-ops)
    _team_cache = teams
    _team_cache_at = now
    return teams


async def _get_recent_form(client: MLBClient, team_id: int) -> list[bool]:
    now = datetime.now(UTC)
    cached = _form_cache.get(team_id)
    if cached and now - cached[0] < _FORM_CACHE_TTL:
        return cached[1]
    try:
        results = await client.recent_results(team_id)
    except httpx.HTTPError:
        logger.warning("MLB recent-results fetch failed for team %s", team_id)
        return cached[1] if cached else []
    _form_cache[team_id] = (now, results)
    return results


def _match_team(text: str, teams: list[MLBTeam]) -> MLBTeam | None:
    if not text:
        return None
    lowered = text.lower()
    # Longest nickname first — avoids a short nickname shadowing a more
    # specific one that also appears in the text (not currently a real
    # collision in MLB's 30 nicknames, but cheap to guard against).
    for team in sorted(teams, key=lambda t: -len(t.nickname)):
        if re.search(r"\b" + re.escape(team.nickname.lower()) + r"\b", lowered):
            return team
    return None


def _resolve_candidate_team(market_title: str, outcome_label: str, teams: list[MLBTeam]) -> MLBTeam | None:
    # "Team A vs. Team B" style market — outcome_label names the team directly.
    direct = _match_team(outcome_label, teams)
    if direct:
        return direct
    # "Will the Yankees win?" style market — outcome_label is Yes/No, team is
    # only in the title. Only resolve on "Yes": betting "No" backs the
    # opponent, and applying this team's cold form to that bet would be
    # backwards, so we conservatively no-op rather than guess.
    if outcome_label.strip().lower() == "yes":
        return _match_team(market_title, teams)
    return None


async def cold_favorite_gate(
    client: MLBClient, market_title: str, outcome_label: str, category: str | None
) -> dict | None:
    """Returns None if this isn't a matchable MLB market, data is
    unavailable, or the team isn't cold. Returns {"verdict": "downsize",
    "reasoning": str} only when the candidate team is on a validated cold
    streak — this gate can never veto outright."""
    if category != "Sports":
        return None

    teams = await _get_teams(client)
    if not teams:
        return None

    team = _resolve_candidate_team(market_title, outcome_label, teams)
    if team is None:
        return None

    results = await _get_recent_form(client, team.id)
    last_n = results[:LOOKBACK_GAMES]
    if len(last_n) < MIN_GAMES_FOR_SIGNAL:
        return None  # too early in the season / not enough completed games yet

    win_rate = sum(last_n) / len(last_n)
    if win_rate >= COLD_THRESHOLD:
        return None

    wins = sum(last_n)
    return {
        "verdict": "downsize",
        "reasoning": (
            f"MLB cold-favorite check: {team.name} have won only {wins}/{len(last_n)} "
            f"({win_rate:.0%}) of their last {len(last_n)} games. Backtested holdout data shows "
            f"teams in this spot win ~42.5% of the time vs a ~53% baseline — a real but modest "
            f"effect, so downsizing rather than vetoing the whale signal outright."
        ),
    }
