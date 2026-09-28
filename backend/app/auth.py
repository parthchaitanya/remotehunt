"""Single-user login for deployed instances.

Enabled when APP_PASSWORD is set. Sessions are HMAC-signed, HttpOnly cookies. Every /api route except
health, login and the Google OAuth callback (protected by its own state parameter) requires a session.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import get_settings

COOKIE = "rh_session"
OPEN_PATHS = {"/api/health", "/api/auth/login", "/api/auth/me", "/api/auth/logout", "/api/gmail/auth/callback"}
_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()
router = APIRouter(prefix="/api/auth", tags=["auth"])


def enabled() -> bool:
    return bool(get_settings().app_password)


def _secret() -> bytes:
    s = get_settings()
    base = s.session_secret or s.fernet_key or s.app_password
    return hashlib.sha256(("remotehunt-session:" + base).encode()).digest()


def make_token(ttl_days: int) -> str:
    expires = int(time.time()) + ttl_days * 86400
    nonce = secrets.token_hex(8)
    payload = f"{expires}.{nonce}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def valid_token(token: str | None) -> bool:
    if not token or token.count(".") != 2:
        return False
    expires, nonce, sig = token.split(".")
    good = hmac.new(_secret(), f"{expires}.{nonce}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good) and expires.isdigit() and int(expires) > time.time()


def is_authenticated(request: Request) -> bool:
    return not enabled() or valid_token(request.cookies.get(COOKIE))


async def middleware(request: Request, call_next):
    path = request.url.path
    if enabled() and path.startswith("/api") and path not in OPEN_PATHS and not is_authenticated(request):
        return JSONResponse({"detail": "Login required"}, status_code=401)
    return await call_next(request)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _lock:
        recent = [t for t in _attempts.get(ip, []) if now - t < 300]
        _attempts[ip] = recent
        return len(recent) >= 5


def _record_failure(ip: str) -> None:
    with _lock:
        _attempts.setdefault(ip, []).append(time.time())


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    s = get_settings()
    if not enabled():
        return {"authenticated": True, "auth_enabled": False}
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if _rate_limited(ip):
        raise HTTPException(429, "Too many attempts. Try again in 5 minutes.")
    if not hmac.compare_digest(body.password.encode(), s.app_password.encode()):
        _record_failure(ip)
        time.sleep(1)
        raise HTTPException(401, "Wrong password")
    https = s.frontend_url.startswith("https://")
    response.set_cookie(COOKIE, make_token(s.session_days), max_age=s.session_days * 86400, httponly=True,
                        secure=https, samesite="lax", path="/")
    return {"authenticated": True, "auth_enabled": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}


@router.get("/me")
def me(request: Request):
    return {"authenticated": is_authenticated(request), "auth_enabled": enabled(),
            "demo": get_settings().demo_mode}
