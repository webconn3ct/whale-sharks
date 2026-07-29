"""News-research confirmation gate for the mini whale bot's entry decisions.

This is a GATE, not a driver: the whale-consensus signal (whale count,
leaderboard quality, track record) is what makes a market a candidate at all
— that's the signal already validated by backtest_signal.py. This module
only gets called for candidates that already cleared that quantitative bar,
and its only power is to VETO or DOWNSIZE based on current news the whale
data can't see yet (an injury, a scandal, a result that already happened).
It can never independently create a trade.

Bounded cost by construction: one Claude + web_search call per cycle, only
when there's an actual best candidate to check.
"""

import json
import logging

from app.config import Settings

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM_PROMPT = """You are a risk-check for a small trading bot that follows Polymarket whale \
consensus. You will be given a specific market and the quantitative whale signal that already qualified it \
as a candidate trade. Your ONLY job is a live news check: search for current, relevant news about this \
specific market/topic, and decide whether that news changes the picture.

Rules:
- The quantitative whale signal is already trustworthy on its own — your job is to catch a clear RED FLAG \
  the whale data can't see yet (breaking news, an injury, a scandal, a result that already happened, a major \
  reversal), not to second-guess a sound signal with vague concerns.
- Default to "confirm" unless you find a genuinely clear, current, specific reason not to.
- Use "downsize" for a moderate but not disqualifying concern, "veto" only for a clear red flag.
- Be concrete: your reasoning should cite what you found. If you found nothing relevant, say so and confirm."""

RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["confirm", "downsize", "veto"]},
        "reasoning": {"type": "string"},
    },
    "required": ["verdict", "reasoning"],
    "additionalProperties": False,
}

DEFAULT_VERDICT = {"verdict": "confirm", "reasoning": "News research unavailable — proceeding on whale signal alone."}


async def research_gate(
    settings: Settings,
    market_title: str,
    outcome_label: str,
    category: str | None,
    whale_count: int,
    consensus_score: float,
) -> dict:
    """Returns {"verdict": "confirm"|"downsize"|"veto", "reasoning": str}.
    Fails open to "confirm" on any error, missing key, or malformed output —
    this is a confirmation gate, not a hard dependency."""
    if not settings.anthropic_api_key:
        return DEFAULT_VERDICT

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return DEFAULT_VERDICT

    prompt = (
        f"Market: {market_title}\n"
        f"Candidate outcome: {outcome_label}\n"
        f"Category: {category or 'unknown'}\n"
        f"Whale signal: {whale_count} independent top-ranked traders, consensus score {consensus_score:.0f}\n\n"
        "Search for current news relevant to this market and give your verdict."
    )

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=RESEARCH_SYSTEM_PROMPT,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            output_config={"format": {"type": "json_schema", "schema": RESEARCH_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception("bot research gate failed — defaulting to confirm")
        return DEFAULT_VERDICT
    finally:
        await client.close()

    if response.stop_reason == "refusal":
        return DEFAULT_VERDICT

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        if data.get("verdict") in ("confirm", "downsize", "veto"):
            return {"verdict": data["verdict"], "reasoning": data.get("reasoning", "")}
    except (json.JSONDecodeError, AttributeError):
        pass
    return DEFAULT_VERDICT
