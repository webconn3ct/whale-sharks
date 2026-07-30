from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.config import Settings, get_settings
from app.core.auth import (
    ADMIN_COOKIE,
    VISITOR_COOKIE,
    check_rate_limit,
    clear_failed_attempts,
    client_ip_hash,
    create_token,
    record_failed_attempt,
    verify_secret,
    verify_token,
)
from app.db import repository
from app.db.session import get_session

router = APIRouter(prefix="/auth")


class UnlockRequest(BaseModel):
    code: str


class AdminLoginRequest(BaseModel):
    password: str


class AuthStatusOut(BaseModel):
    visitor: bool
    admin: bool


def _set_cookie(response: Response, name: str, token: str, max_age_seconds: int, settings: Settings) -> None:
    response.set_cookie(
        key=name,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/unlock")
async def unlock(body: UnlockRequest, request: Request, response: Response, settings: Settings = Depends(get_settings)):
    rate_key = f"unlock:{client_ip_hash(settings, request)}"
    if not check_rate_limit(rate_key):
        raise HTTPException(status_code=429, detail="Too many attempts — try again in a few minutes")
    async with get_session() as session:
        code_valid = await repository.verify_any_access_code(session, body.code)
    if not code_valid:
        record_failed_attempt(rate_key)
        raise HTTPException(status_code=401, detail="Incorrect access code")
    clear_failed_attempts(rate_key)
    token = create_token(settings, role="visitor")
    _set_cookie(response, VISITOR_COOKIE, token, settings.visitor_session_days * 86400, settings)
    async with get_session() as session:
        await repository.record_login_event(session, "visitor", client_ip_hash(settings, request))
    return {"ok": True}


@router.post("/admin-login")
async def admin_login(body: AdminLoginRequest, request: Request, response: Response, settings: Settings = Depends(get_settings)):
    rate_key = f"admin-login:{client_ip_hash(settings, request)}"
    if not check_rate_limit(rate_key):
        raise HTTPException(status_code=429, detail="Too many attempts — try again in a few minutes")
    async with get_session() as session:
        config = await repository.get_app_config(session)
    if config is None or not verify_secret(body.password, config.admin_password_hash):
        record_failed_attempt(rate_key)
        raise HTTPException(status_code=401, detail="Incorrect admin password")
    clear_failed_attempts(rate_key)
    token = create_token(settings, role="admin")
    _set_cookie(response, ADMIN_COOKIE, token, settings.admin_session_hours * 3600, settings)
    # Admin implies visitor access too, so the dashboard behind them unlocks as well.
    visitor_token = create_token(settings, role="visitor")
    _set_cookie(response, VISITOR_COOKIE, visitor_token, settings.visitor_session_days * 86400, settings)
    async with get_session() as session:
        await repository.record_login_event(session, "admin", client_ip_hash(settings, request))
    return {"ok": True}


def _clear_cookie(response: Response, name: str, settings: Settings) -> None:
    # Must match the attributes the cookie was SET with (samesite/secure) —
    # otherwise the browser treats this as a different cookie and the
    # original one never actually gets cleared.
    response.delete_cookie(key=name, path="/", samesite=settings.cookie_samesite, secure=settings.cookie_secure)


@router.post("/admin-logout", dependencies=[Depends(require_admin)])
async def admin_logout(response: Response, settings: Settings = Depends(get_settings)):
    _clear_cookie(response, ADMIN_COOKIE, settings)
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response, settings: Settings = Depends(get_settings)):
    _clear_cookie(response, VISITOR_COOKIE, settings)
    return {"ok": True}


class SignupRequest(BaseModel):
    contact: str = Field(min_length=2, max_length=255)


@router.post("/signup")
async def signup(body: SignupRequest):
    async with get_session() as session:
        await repository.create_signup(session, body.contact.strip())
    return {"ok": True}


@router.get("/status", response_model=AuthStatusOut)
def status(request: Request, settings: Settings = Depends(get_settings)) -> AuthStatusOut:
    visitor_token = request.cookies.get(VISITOR_COOKIE)
    admin_token = request.cookies.get(ADMIN_COOKIE)
    is_admin = bool(admin_token) and verify_token(settings, admin_token, settings.admin_session_hours * 3600)
    is_visitor = is_admin or (
        bool(visitor_token) and verify_token(settings, visitor_token, settings.visitor_session_days * 86400)
    )
    return AuthStatusOut(visitor=is_visitor, admin=is_admin)
