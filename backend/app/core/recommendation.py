"""Computes a data-backed "lean" between one or two consensus outcomes, then
phrases it in one sentence. The facts are always computed deterministically
from real snapshot data; when an Anthropic key is configured, Claude is used
only to phrase those exact facts into readable prose — it is never given
room to invent a number or claim that isn't already in `facts`.
"""

import logging

from app.api.schemas import ConsensusRowOut
from app.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You write ONE concise sentence of trading insight for a Polymarket whale-consensus \
dashboard, given a JSON object of already-computed facts.

Hard rules:
- Use ONLY the numbers and labels given in the facts. Never state a number, name, or claim not present there.
- State the lean directly and plainly — no hedging words like "might", "could", "possibly".
- If `opposing` is null, just summarize the strength of the one-sided consensus in `primary` — do not imply \
a comparison that doesn't exist.
- If `opposing` is present, explain which side the data favors and the single clearest reason why \
(whale count, leaderboard rank quality, or score gap — whichever is most lopsided).
- Describe what the whale data currently shows, never what will happen — this is NOT a prediction of the \
market's real-world outcome, and must never be phrased as one (no "will win", "is likely to happen", etc.).
- Output exactly one sentence, no preamble, no quotation marks."""


def _avg_best_rank(row: ConsensusRowOut) -> float | None:
    if not row.holders:
        return None
    return sum(h.best_rank for h in row.holders) / len(row.holders)


def _outcome_facts(row: ConsensusRowOut) -> dict:
    return {
        "outcome_label": row.outcome_label,
        "whale_count": row.whale_count,
        "avg_leaderboard_rank": round(r, 1) if (r := _avg_best_rank(row)) is not None else None,
        "combined_value_usd": round(row.combined_value, 2),
        "consensus_score": round(row.consensus_score, 1),
    }


def compute_lean_facts(primary: ConsensusRowOut, opposing: ConsensusRowOut | None) -> dict:
    """Pure, deterministic — no LLM involved. Safe to compute on every request."""
    facts: dict = {"market_title": primary.market_title, "primary": _outcome_facts(primary), "opposing": None}
    if opposing is not None:
        facts["opposing"] = _outcome_facts(opposing)
        facts["leader_outcome"] = (
            primary.outcome_label if primary.consensus_score >= opposing.consensus_score else opposing.outcome_label
        )
    else:
        facts["leader_outcome"] = primary.outcome_label
    return facts


def render_template(facts: dict) -> str:
    """Deterministic fallback sentence — used when no ANTHROPIC_API_KEY is configured."""
    p = facts["primary"]
    o = facts["opposing"]
    if o is None:
        rank_part = f" (avg leaderboard rank #{p['avg_leaderboard_rank']:.0f})" if p["avg_leaderboard_rank"] else ""
        return f"{p['whale_count']} whales are backing {p['outcome_label']}{rank_part} with no meaningful opposing whale position on this market."

    leader, other = (p, o) if facts["leader_outcome"] == p["outcome_label"] else (o, p)
    leader_rank = f", avg rank #{leader['avg_leaderboard_rank']:.0f}" if leader["avg_leaderboard_rank"] else ""
    other_rank = f", avg rank #{other['avg_leaderboard_rank']:.0f}" if other["avg_leaderboard_rank"] else ""
    return (
        f"Leans {leader['outcome_label']} — {leader['whale_count']} whales{leader_rank} "
        f"vs {other['whale_count']} whales{other_rank} on {other['outcome_label']}."
    )


async def phrase_reasoning(settings: Settings, facts: dict) -> str:
    if not settings.anthropic_api_key:
        return render_template(facts)

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return render_template(facts)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-opus-5",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": str(facts)}],
        )
    except Exception:
        logger.exception("recommendation phrasing failed — falling back to template")
        return render_template(facts)
    finally:
        await client.close()

    if response.stop_reason == "refusal":
        return render_template(facts)
    text = next((block.text for block in response.content if block.type == "text"), "")
    return text.strip() or render_template(facts)


# In-process cache, keyed by scan_id so it's invalidated automatically every
# scan cycle (~15 min) — avoids a live Claude call on every poll/click for
# data that hasn't changed since the last scan.
_cache: dict[str, str] = {}
_cache_scan_id: int | None = None


async def get_reasoning(settings: Settings, scan_id: int, cache_key: str, facts: dict) -> str:
    global _cache, _cache_scan_id
    if _cache_scan_id != scan_id:
        _cache = {}
        _cache_scan_id = scan_id
    if cache_key not in _cache:
        _cache[cache_key] = await phrase_reasoning(settings, facts)
    return _cache[cache_key]
