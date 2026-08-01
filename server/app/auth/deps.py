"""FastAPI auth dependencies.

- `optional_user` / `get_current_user`: identity from the session cookie.
- `require_owner` / `require_readable`: story-level authorization. Not-owner
  access to a private story returns 404 (never reveal that it exists).
"""
from fastapi import Depends, HTTPException, Request

from app.auth import service
from app.config import config
from app.db.base import SessionLocal
from app.db.queries import sessions as session_queries


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


def _load_session(session_id: str) -> dict:
    session = session_queries.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def require_owner(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    """The caller must be signed in AND own the story. Returns the raw row."""
    session = _load_session(session_id)
    if session.get("owner_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def require_readable(session_id: str, user: dict | None = Depends(optional_user)) -> dict:
    """Readable if the caller owns the story or it is public."""
    session = _load_session(session_id)
    is_owner = bool(user) and session.get("owner_id") == user["id"]
    if not (is_owner or session.get("visibility") == "public"):
        raise HTTPException(status_code=404, detail="Session not found")
    return session
