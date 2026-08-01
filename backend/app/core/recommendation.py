"""Computes a data-backed "lean" between one or two consensus outcomes, then
phrases it in one sentence. The facts are always computed deterministically
from real snapshot data; Claude phrases those exact facts into readable
prose (never free to invent a number or claim not already in `facts`) and,
when an Anthropic key is configured, can also check live news for the
specific market — the same live-news awareness bot_research.py already
gives KrillBot's own trade entries, now extended to the lean text every
visitor sees, not just the bot's trades.
"""

import logging

from app.api.schemas import ConsensusRowOut
from app.config import Settings

logger = logging.getLogger(__name__)

# Below this whale count, an "opposing" position is noise, not a real
# conflict — shared by both the whale-spotlight matchup builder and the
# per-market lean endpoint so a lean never gets padded out against a
# near-empty position just to sound more substantial.
MIN_OPPOSING_WHALES = 2

SYSTEM_PROMPT = """You write ONE concise, complete sentence of data-backed insight for a Polymarket whale-consensus \
dashboard, given a JSON object of already-computed facts.

Hard rules:
- Use ONLY the numbers and labels given in the facts. Never state a number, name, or claim not present there.
- State facts directly and plainly — no hedging words like "might", "could", "possibly".
- `avg_recent_win_rate` reflects how often these specific whales' own past resolved bets actually won — a real \
accuracy signal, distinct from whale count or leaderboard rank (rank reflects total profit, not hit rate). Whale \
count alone proves nothing about accuracy — treat track record as a genuine, citable factor whenever it's \
present and meaningfully shapes the picture (e.g. a smaller but higher-accuracy group, or a large group with a \
mediocre recent track record — say so plainly).
- If `opposing` is null, summarize the one-sided consensus in `primary` using whichever facts are most \
informative together — whale count, rank quality, AND track record, not whale count alone.
- If `opposing` is present (a two-sided matchup), give a BALANCED, neutral comparison of both sides' real facts \
so the reader can weigh it themselves. Do NOT declare a winner, do NOT use words like "leans", "favors", or \
"the better bet", and do NOT imply one side is recommended over the other. If the whale-count side and the \
track-record side disagree, say that tension plainly instead of resolving it for the reader — e.g. more whales \
on one side but a stronger recent track record on the other.
- Describe what the whale data currently shows, never what will happen — this is NOT a prediction of the \
market's real-world outcome, and must never be phrased as one (no "will win", "is likely to happen", etc.).
- You have live web search available. If there's a clear, current, specific news item about this exact \
market/topic — an injury, a result that already happened, a lineup change, a major reversal — that the whale \
data alone wouldn't show, search for it and weave that into your one sentence alongside the whale facts. Only \
mention news that's genuinely current and specific to this market; don't force a search result in for its own \
sake, don't speculate beyond what you actually found, and never let a news mention slide into predicting the \
outcome — same rule as the whale data itself.
- The sentence must be a real, complete, well-formed sentence on its own — not a sentence fragment, not a \
list of numbers. Keep it tight enough (well under 40 words) that you never have to cut it short.
- Output exactly one sentence, no preamble, no quotation marks."""

# This prompt never changes — a perfect prompt-caching candidate. Cached
# once, every subsequent call (there can be several per scan cycle, one per
# matchup) reuses it instead of re-billing full price each time.
SYSTEM_BLOCKS = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


def _avg_best_rank(row: ConsensusRowOut) -> float | None:
    if not row.holders:
        return None
    return sum(h.best_rank for h in row.holders) / len(row.holders)


def avg_recent_form(row: ConsensusRowOut) -> tuple[float | None, int]:
    """Unweighted average recent-form (shrunk win rate on each holder's own
    last ~10 resolved positions) across holders that have one computed yet.
    Returns (None, 0) rather than 0.0 when nobody has data — a real "no
    signal" distinct from "0% win rate"."""
    values = [h.recent_form for h in row.holders if h.recent_form is not None]
    if not values:
        return None, 0
    return sum(values) / len(values), len(values)


def _outcome_facts(row: ConsensusRowOut) -> dict:
    avg_form, form_sample = avg_recent_form(row)
    return {
        "outcome_label": row.outcome_label,
        "whale_count": row.whale_count,
        "avg_leaderboard_rank": round(r, 1) if (r := _avg_best_rank(row)) is not None else None,
        "combined_value_usd": round(row.combined_value, 2),
        "consensus_score": round(row.consensus_score, 1),
        "avg_recent_win_rate": round(avg_form * 100, 1) if avg_form is not None else None,
        "recent_win_rate_sample_count": form_sample,
    }


def compute_lean_facts(primary: ConsensusRowOut, opposing: ConsensusRowOut | None) -> dict:
    """Pure, deterministic — no LLM involved. Safe to compute on every request."""
    facts: dict = {"market_title": primary.market_title, "primary": _outcome_facts(primary), "opposing": None}
    if opposing is not None:
        facts["opposing"] = _outcome_facts(opposing)
    return facts


def _describe_side(f: dict) -> str:
    rank_part = f", avg rank #{f['avg_leaderboard_rank']:.0f}" if f["avg_leaderboard_rank"] else ""
    form_part = f", {f['avg_recent_win_rate']:.0f}% recent win rate" if f["avg_recent_win_rate"] is not None else ""
    return f"{f['whale_count']} whales{rank_part}{form_part} on {f['outcome_label']}"


def render_template(facts: dict) -> str:
    """Deterministic fallback sentence — used when no ANTHROPIC_API_KEY is configured."""
    p = facts["primary"]
    o = facts["opposing"]
    if o is None:
        return f"{_describe_side(p)}, with no meaningful opposing whale position on this market."

    # Neutral, both-sides-shown — no declared winner, matching the same
    # "let the reader decide" framing as the Claude-phrased version.
    return f"{_describe_side(p)} vs {_describe_side(o)} — data shown for both sides."


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
            max_tokens=1024,
            system=SYSTEM_BLOCKS,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": str(facts)}],
        )
    except Exception:
        logger.exception("recommendation phrasing failed — falling back to template")
        return render_template(facts)
    finally:
        await client.close()

    if response.stop_reason in ("refusal", "max_tokens"):
        # max_tokens here means the sentence got cut off mid-thought — never
        # show a fragment, the deterministic template is always complete.
        return render_template(facts)
    # A web-search turn splits its answer across several separate text
    # blocks interleaved with tool calls (observed: the model drives search
    # via server-side code execution, and the final sentence itself can
    # land split across two or three text blocks) — concatenate all of them
    # in order rather than picking just one, or the result is a fragment.
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text or text[-1] not in ".!?":
        # Any other sign the sentence didn't land clean — same reasoning.
        return render_template(facts)
    return text


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
