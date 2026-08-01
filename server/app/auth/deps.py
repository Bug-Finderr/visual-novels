"""FastAPI auth dependencies. `optional_user` reads the opaque session cookie
and returns the public user dict (or None); `get_current_user` requires it."""
from fastapi import Depends, HTTPException, Request

from app.auth import service
from app.config import config
from app.db.base import SessionLocal


def optional_user(request: Request) -> dict | None:
    raw = request.cookies.get(config.SESSION_COOKIE)
    if not raw:
        return None
    with SessionLocal() as db:
        return service.user_public(service.get_user_for_token(db, raw))


def get_current_user(user: dict | None = Depends(optional_user)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
