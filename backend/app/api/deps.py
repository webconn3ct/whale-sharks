from fastapi import Depends, HTTPException, Request, Response

from app.api.schemas import ConsensusSnapshot
from app.config import Settings, get_settings
from app.core.auth import ADMIN_COOKIE, VISITOR_COOKIE, verify_token
from app.core.cache import cache


def get_ready_snapshot(response: Response) -> ConsensusSnapshot:
    snapshot = cache.snapshot
    if snapshot is None:
        response.headers["Retry-After"] = "10"
        raise HTTPException(status_code=503, detail="Initial scan still in progress — retry shortly")
    return snapshot


def require_visitor(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Gate for the public dashboard — either a visitor session or an admin
    session (admins can always see what visitors see) satisfies this."""
    visitor_token = request.cookies.get(VISITOR_COOKIE)
    admin_token = request.cookies.get(ADMIN_COOKIE)
    if visitor_token and verify_token(settings, visitor_token, settings.visitor_session_days * 86400):
        return
    if admin_token and verify_token(settings, admin_token, settings.admin_session_hours * 3600):
        return
    raise HTTPException(status_code=401, detail="Locked — enter the access code")


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    admin_token = request.cookies.get(ADMIN_COOKIE)
    if admin_token and verify_token(settings, admin_token, settings.admin_session_hours * 3600):
        return
    raise HTTPException(status_code=401, detail="Admin login required")
