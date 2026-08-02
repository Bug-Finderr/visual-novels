"""Auth routes under /api/v1: Google login/callback, logout, and /me."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import service
from app.auth.deps import optional_user
from app.auth.oauth import oauth
from app.config import config
from app.db.base import SessionLocal
from app.logger import logger

router = APIRouter(prefix="/api/v1", tags=["auth"])

_FRONTEND = config.ALLOWED_ORIGINS[0] if config.ALLOWED_ORIGINS else "http://localhost:3000"


@router.get("/auth/google/login")
async def google_login(request: Request):
    if not config.google_oauth_enabled:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    return await oauth.google.authorize_redirect(request, config.GOOGLE_REDIRECT_URI)


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    if not config.google_oauth_enabled:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:  # noqa: BLE001 — surface a friendly redirect, log the detail
        logger.warning("google callback failed: %s", exc)
        return RedirectResponse(f"{_FRONTEND}/?auth=error")

    userinfo = token.get("userinfo") or await oauth.google.userinfo(token=token)
    with SessionLocal() as db:
        user = service.upsert_user_from_google(db, dict(userinfo))
        raw = service.create_session(db, user.id, request.headers.get("user-agent"))
        db.commit()

    resp = RedirectResponse(f"{_FRONTEND}/")
    resp.set_cookie(
        config.SESSION_COOKIE,
        raw,
        max_age=config.SESSION_TTL_DAYS * 86400,
        httponly=True,
        # Dev default: Lax + insecure (http://localhost). In prod set
        # SESSION_COOKIE_SECURE=1, and SameSite=None only when the SPA is on a
        # different site than the API (cross-site XHR needs None+Secure).
        samesite=config.SESSION_COOKIE_SAMESITE,
        secure=config.SESSION_COOKIE_SECURE,
        path="/",
    )
    return resp


@router.post("/auth/logout")
async def logout(request: Request):
    raw = request.cookies.get(config.SESSION_COOKIE)
    if raw:
        with SessionLocal() as db:
            service.revoke_token(db, raw)
            db.commit()
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(config.SESSION_COOKIE, path="/")
    return resp


@router.get("/me")
async def me(user: dict | None = Depends(optional_user)):
    return {"user": user, "googleAuthEnabled": config.google_oauth_enabled}
