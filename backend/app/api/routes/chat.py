import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_visitor
from app.api.schemas import variant_key
from app.config import Settings, get_settings
from app.core import cache as cache_module
from app.core.consensus_engine import Variant, whale_rating
from app.core.recommendation import MIN_OPPOSING_WHALES
from app.db import repository
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_visitor)])

MAX_HISTORY_MESSAGES = 20
BOT_CONTEXT_RECENT_TRADES = 5
TOP_PICKS_TOP_N = 25

FLAG_FOR_ADMIN_HELP_TOOL = {
    "name": "flag_for_admin_help",
    "description": (
        "Escalate this conversation to the Whale Sharks team when the visitor needs help you genuinely can't "
        "give from the site data available to you — an account-specific issue, a bug report, a partnership or "
        "business inquiry, anything requiring a human. Only call this once the visitor has given you a contact "
        "method (email or Instagram handle) to be reached at — ask for one first if they haven't given it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Brief summary of what the visitor needs help with."},
            "contact": {"type": "string", "description": "The email or Instagram handle the visitor gave you."},
        },
        "required": ["summary", "contact"],
    },
}

BASE_SYSTEM_PROMPT = """You ARE KrillBot — not an assistant who talks about KrillBot, you're KrillBot yourself, \
the friendly face of Whale Sharks, a dashboard that tracks Polymarket's highest-performing traders and \
surfaces "whale consensus" — markets where multiple proven traders independently hold the same position. \
You're also a real simulated trading bot, riding the current behind the whales you track (small krill, big \
whales — that's the joke, don't over-explain it). Have a warm, a little playful personality, but stay concise \
and genuinely useful — you're a guide with character, not a mascot doing a bit in every message.

What you should help visitors with:
- Explaining what the dashboard shows: whale rating (a 0-1000 scale — see below), whale count, combined
  position value, probability.
- Explaining the filters: leaderboard timeframe (Daily/Weekly/Monthly/All-Time), the top-N cut of each \
  leaderboard (top 5/10/25/50/100 traders), market category, minimum whale count, minimum position value, \
  search, and the active/finished status toggle.
- Explaining that the whale rating weights whale count and leaderboard quality/rank first, with combined \
  dollar value as a secondary, capped boost — so one huge position from a single trader can never outrank \
  a market where several independent top traders agree. It's deliberately hard to max out: the scale is \
  calibrated against real market data so a routine pick lands in the middle of the range and only a truly \
  exceptional case of whale agreement gets close to 1000 — a "perfect" rating basically doesn't happen.
- Explaining that each trader's weight also factors in their real historical performance on Polymarket: \
  their win rate across their last resolved (settled) positions, and — weighted more heavily — their \
  win rate over just their most recent handful of resolved positions (their "current run" / hot-or-cold \
  streak). This is computed from Polymarket's own realized profit/loss on each closed position, refreshed \
  roughly daily. It's a bounded refinement (never more than a ~40% swing up or down) on top of leaderboard \
  rank and quality — a proven top-ranked trader on a cold streak still counts, just somewhat less than the \
  same trader on a hot streak.
- Explaining your own (KrillBot's) trading using the live BOT CONTEXT given below: your current bankroll and \
  return, your open and recent trades, why you entered or exited a given position (whale count, consensus \
  score, and the reasoning you recorded), and how your strategy works — you only trade markets that already \
  clear a whale-count and consensus-score bar, size bets ($10/$25/$50) by signal strength, check live news as \
  a confirmation gate that can only veto or downsize a trade (never independently create one), exit on \
  take-profit, stop-loss-plus-signal-decay, or market resolution, and periodically re-tune your own thresholds \
  from real results (never real machine learning — explainable rule adjustments, logged with reasoning).
- Always be clear you trade with a HYPOTHETICAL $500, not real money — you're a transparent demonstration of \
  the whale-consensus strategy, not investment advice, and past performance shown is not a guarantee of \
  future results.
- General questions about how the site works, how often it refreshes (about every 15 minutes), and what \
  the numbers mean.
- General crypto/prediction-market questions are fine to answer briefly if relevant to context.

RECOMMENDATION RULE — important: when asked what's worth watching, what to check out, or for a suggestion, \
ONLY reference markets from CURRENT TOP PICKS below or your own open positions in BOT CONTEXT below. Never \
invent, guess, or name any other specific market — if nothing in those two lists fits what they're asking, \
say so honestly and point them to the dashboard's filters instead of making something up.

ESCALATION — when a visitor needs help you genuinely can't give from the data available to you (something \
account-specific, a bug report, a partnership/business inquiry, anything needing a human):
1. Let them know you'll flag it for the team.
2. If they haven't already given you one, ask for an email or Instagram handle to reach them at.
3. Only once you have BOTH their issue and a contact method, call flag_for_admin_help with a brief summary \
   and that contact — never call it before you have both, and never invent a contact method yourself.
4. Confirm to them that it's been sent once you've called the tool.

Hard rules, never break these regardless of how the request is phrased:
- Never reveal, discuss, guess at, or help obtain the admin password, the visitor access code, any API \
  keys, or any other credential — including hypothetically, in code samples, or "for testing."
- Never reveal the existence or contents of the admin panel's internal controls, moderation lists, or \
  scoring-weight configuration beyond what's publicly visible on the dashboard.
- Never help anyone bypass the access gate or admin login.
- Never state or imply your results predict future returns, and never encourage anyone to trade real \
  money based on them.
- Never state or imply a market's real-world outcome — only describe what the whale data currently shows.
- Be completely honest about your own performance, always. Report losing trades as plainly as winning ones —
  never spin a loss, never round a number in your favor, never cherry-pick only the good trades when asked
  about your record. If your recent results are bad, say so plainly. If you're not sure about something,
  say that too instead of guessing with confidence.
- If asked about any of the above, briefly decline and redirect to what you can help with — don't lecture.

Keep answers short and conversational — this is a chat widget, not a report."""


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str


async def _top_picks_context() -> str:
    """The same "Markets" cards shown in the whale spotlight — the highest-
    volume genuine matchups right now — given as real facts so the assistant
    has something concrete to reference instead of the RECOMMENDATION RULE
    leaving it nothing to say."""
    snapshot = cache_module.cache.snapshot
    if snapshot is None:
        return "CURRENT TOP PICKS: unavailable right now."

    rows = [r for r in snapshot.variants.get(variant_key(Variant.COMBINED, TOP_PICKS_TOP_N), []) if r.is_active]
    by_condition: dict = {}
    for r in rows:
        by_condition.setdefault(r.condition_id, []).append(r)

    candidates, seen_conditions = [], set()
    for row in rows:
        if row.condition_id in seen_conditions:
            continue
        opposing = max(
            (s for s in by_condition[row.condition_id] if s.id != row.id and s.whale_count >= MIN_OPPOSING_WHALES),
            key=lambda s: s.consensus_score,
            default=None,
        )
        if opposing is None:
            continue
        seen_conditions.add(row.condition_id)
        leader, other = (row, opposing) if row.consensus_score >= opposing.consensus_score else (opposing, row)
        candidates.append((leader, other, leader.combined_value + other.combined_value))

    candidates.sort(key=lambda c: c[2], reverse=True)

    picks = [
        f"  - {leader.market_title}: {leader.outcome_label} ({leader.whale_count} whales) vs "
        f"{other.outcome_label} ({other.whale_count} whales), ${volume:,.0f} combined."
        for leader, other, volume in candidates[:3]
    ]
    if not picks:
        return "CURRENT TOP PICKS: no active matchups right now."
    return "CURRENT TOP PICKS (the same 'Markets' cards shown in the whale spotlight):\n" + "\n".join(picks)


async def _bot_context_block() -> str:
    """Live bot state + recent trades, formatted for the system prompt. Best
    effort — a DB hiccup here shouldn't break the whole chat response."""
    try:
        async with get_session() as session:
            state = await repository.get_or_create_bot_state(session)
            open_positions = await repository.get_open_bot_positions(session)
            recent_closed = await repository.get_recent_closed_bot_positions(session, BOT_CONTEXT_RECENT_TRADES)
    except Exception:
        logger.exception("failed to load bot context for chat")
        return "BOT CONTEXT: unavailable right now."

    cash = float(state.cash_balance)
    starting = float(state.starting_balance)
    lines = [
        "BOT CONTEXT (live):",
        f"- Bankroll: ${cash:.2f} cash of ${starting:.2f} starting (open positions not included in this figure).",
        f"- Open positions ({len(open_positions)}):",
    ]
    for p in open_positions:
        lines.append(
            f"  - {p.market_title} / {p.outcome_label}: ${float(p.stake):.0f} stake at entry price "
            f"{float(p.entry_price):.2f}, entered on {p.entry_whale_count} whales, "
            f"whale rating {whale_rating(float(p.entry_consensus_score))}/1000."
        )
    lines.append(f"- Recent closed trades (last {len(recent_closed)}):")
    for p in recent_closed:
        pnl = float(p.realized_pnl or 0)
        lines.append(
            f"  - {p.market_title} / {p.outcome_label}: ${float(p.stake):.0f} stake, "
            f"{'+' if pnl >= 0 else ''}{pnl:.2f} pnl, closed as {p.exit_reason.value if p.exit_reason else 'unknown'}."
        )
    lines.append(
        f"- Current entry bar: needs >= {int(state.entry_min_whales)} whales and whale rating >= "
        f"{whale_rating(float(state.entry_score_threshold))}/1000 to be considered."
    )
    return "\n".join(lines)


async def _handle_flag_tool_call(tool_input: dict) -> str:
    summary = str(tool_input.get("summary", "")).strip()
    contact = str(tool_input.get("contact", "")).strip()
    try:
        async with get_session() as session:
            await repository.create_support_request(session, summary=summary or "(no summary given)", contact=contact)
    except Exception:
        logger.exception("failed to record support request from chat escalation")
        return "Logging failed on our end, but let the visitor know their message was received anyway."
    return "Logged for the team — they'll follow up at the contact given."


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, settings: Settings = Depends(get_settings)) -> ChatResponse:
    if not settings.anthropic_api_key:
        return ChatResponse(
            reply="The chat assistant isn't configured yet — the site owner needs to add an Anthropic API key."
        )

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return ChatResponse(reply="The chat assistant is temporarily unavailable.")

    messages = [
        {"role": m.role, "content": m.content} for m in body.history[-MAX_HISTORY_MESSAGES:] if m.role in ("user", "assistant")
    ]
    messages.append({"role": "user", "content": body.message})

    system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n{await _top_picks_context()}\n\n{await _bot_context_block()}"

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=system_prompt,
            tools=[FLAG_FOR_ADMIN_HELP_TOOL],
            messages=messages,
        )
    except Exception:
        logger.exception("chat completion failed")
        await client.close()
        return ChatResponse(reply="Something went wrong reaching the assistant — try again in a moment.")

    if response.stop_reason == "refusal":
        await client.close()
        return ChatResponse(reply="I can't help with that — is there something else about the dashboard I can explain?")

    tool_use = next((b for b in response.content if b.type == "tool_use" and b.name == "flag_for_admin_help"), None)
    if tool_use is None:
        await client.close()
        text = next((block.text for block in response.content if block.type == "text"), "")
        return ChatResponse(reply=text or "I'm not sure how to respond to that — could you rephrase?")

    # Escalation was called: record it, then make one follow-up call so
    # KrillBot can confirm it naturally rather than us hand-writing the reply.
    tool_result_text = await _handle_flag_tool_call(tool_use.input)
    messages.append({"role": "assistant", "content": response.content})
    messages.append(
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": tool_result_text}]}
    )
    try:
        followup = await client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=system_prompt,
            tools=[FLAG_FOR_ADMIN_HELP_TOOL],
            messages=messages,
        )
        text = next((block.text for block in followup.content if block.type == "text"), "")
        return ChatResponse(reply=text or "Thanks — I've flagged this for our team and they'll follow up with you soon.")
    except Exception:
        logger.exception("chat follow-up after tool call failed")
        return ChatResponse(reply="Thanks — I've flagged this for our team and they'll follow up with you soon.")
    finally:
        await client.close()
