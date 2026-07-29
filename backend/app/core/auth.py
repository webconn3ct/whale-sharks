"""Two independent auth tiers, both simple shared-secret gates (not user
accounts): a visitor access code that unlocks the public dashboard, and a
separate, shorter-lived admin password that unlocks the admin panel. Tokens
are signed (itsdangerous) and carried in httpOnly cookies — no session store."""

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings

VISITOR_COOKIE = "ws_visitor"
ADMIN_COOKIE = "ws_admin"
_SALT = "whale-sharks-auth-v1"


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
