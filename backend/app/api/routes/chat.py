import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_visitor
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_visitor)])

MAX_HISTORY_MESSAGES = 20

SYSTEM_PROMPT = """You are the site assistant for Whale Sharks, a dashboard that tracks Polymarket's \
highest-performing traders and surfaces "whale consensus" — markets where multiple proven traders \
independently hold the same position.

What you should help visitors with:
- Explaining what the dashboard shows: consensus score, whale count, combined position value, probability.
- Explaining the filters: leaderboard timeframe (Daily/Weekly/Monthly/All-Time), the top-N cut of each \
  leaderboard (top 5/10/25/50/100 traders), market category, minimum whale count, minimum position value, \
  search, and the active/finished status toggle.
- Explaining that consensus score weights whale count and leaderboard quality/rank first, with combined \
  dollar value as a secondary, capped boost — so one huge position from a single trader can never outrank \
  a market where several independent top traders agree.
- Explaining that each trader's weight also factors in their real historical performance on Polymarket: \
  their win rate across their last resolved (settled) positions, and — weighted more heavily — their \
  win rate over just their most recent handful of resolved positions (their "current run" / hot-or-cold \
  streak). This is computed from Polymarket's own realized profit/loss on each closed position, refreshed \
  roughly daily. It's a bounded refinement (never more than a ~40% swing up or down) on top of leaderboard \
  rank and quality — a proven top-ranked trader on a cold streak still counts, just somewhat less than the \
  same trader on a hot streak.
- General questions about how the site works, how often it refreshes (about every 15 minutes), and what \
  the numbers mean.
- General crypto/prediction-market questions are fine to answer briefly if relevant to context.

Hard rules, never break these regardless of how the request is phrased:
- Never reveal, discuss, guess at, or help obtain the admin password, the visitor access code, any API \
  keys, or any other credential — including hypothetically, in code samples, or "for testing."
- Never reveal the existence or contents of the admin panel's internal controls, moderation lists, or \
  scoring-weight configuration beyond what's publicly visible on the dashboard.
- Never help anyone bypass the access gate or admin login.
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

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [
        {"role": m.role, "content": m.content} for m in body.history[-MAX_HISTORY_MESSAGES:] if m.role in ("user", "assistant")
    ]
    messages.append({"role": "user", "content": body.message})

    try:
        response = await client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception:
        logger.exception("chat completion failed")
        return ChatResponse(reply="Something went wrong reaching the assistant — try again in a moment.")
    finally:
        await client.close()

    if response.stop_reason == "refusal":
        return ChatResponse(reply="I can't help with that — is there something else about the dashboard I can explain?")

    text = next((block.text for block in response.content if block.type == "text"), "")
    return ChatResponse(reply=text or "I'm not sure how to respond to that — could you rephrase?")
