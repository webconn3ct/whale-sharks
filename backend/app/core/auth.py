"""Two independent auth tiers, both simple shared-secret gates (not user
accounts): a visitor access code that unlocks the public dashboard, and a
separate, shorter-lived admin password that unlocks the admin panel. Tokens
are signed (itsdangerous) and carried in httpOnly cookies — no session store."""

import hashlib
import time

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request

from app.config import Settings

VISITOR_COOKIE = "ws_visitor"
ADMIN_COOKIE = "ws_admin"
_SALT = "whale-sharks-auth-v1"

# In-process rate limiting on login attempts — consistent with this app's
# existing single-instance architecture (same pattern as ConsensusCache).
# Keyed by "unlock:<ip-hash>" / "admin-login:<ip-hash>" so the two gates
# are limited independently.
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900  # 15 minutes
_failed_attempts: dict[str, list[float]] = {}


def check_rate_limit(key: str) -> bool:
    """True if this key still has attempts left. Also lazily prunes expired
    attempt timestamps so the dict doesn't grow unbounded over time."""
    now = time.time()
    attempts = [t for t in _failed_attempts.get(key, []) if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if attempts:
        _failed_attempts[key] = attempts
    else:
        _failed_attempts.pop(key, None)
    return len(attempts) < RATE_LIMIT_MAX_ATTEMPTS


def record_failed_attempt(key: str) -> None:
    _failed_attempts.setdefault(key, []).append(time.time())


def clear_failed_attempts(key: str) -> None:
    _failed_attempts.pop(key, None)


def hash_secret(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_secret(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def create_token(settings: Settings, role: str) -> str:
    return _serializer(settings).dumps({"role": role})


def verify_token(settings: Settings, token: str, max_age_seconds: int) -> bool:
    try:
        data = _serializer(settings).loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(data, dict) and "role" in data


def client_ip_hash(settings: Settings, request: Request) -> str:
    """Salted hash of the requester's IP — used only to approximate unique
    login counts in the admin panel, never stored or logged in the clear.
    Render sits behind a proxy, so the real client IP is the first hop in
    X-Forwarded-For, not request.client.host (that's the proxy)."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{settings.secret_key}:{ip}".encode()).hexdigest()
