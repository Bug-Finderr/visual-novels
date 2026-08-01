"""Account + session logic on top of the SQLAlchemy models.

Auth model: Google Authorization-Code flow → we mint our OWN opaque session
token, store it hashed in `auth_sessions`, and hand the raw value to the
browser as an HttpOnly cookie (server-revocable). Google tokens never reach
the client.
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import config
from app.db import models


def _now() -> datetime:
    return datetime.utcnow()


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _slug(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())[:20]


def _unique_username(db: Session, email: str | None, name: str | None) -> str:
    base = _slug((email or "").split("@")[0]) or _slug(name) or "user"
    username = base
    i = 0
    while db.execute(select(models.User).where(models.User.username == username)).scalar_one_or_none():
        i += 1
        username = f"{base}{i}"
    return username


def upsert_user_from_google(db: Session, userinfo: dict) -> models.User:
    """Find-or-create the user for a Google identity. Links by provider 'sub';
    falls back to matching an existing account by verified email."""
    sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name") or userinfo.get("given_name")
    picture = userinfo.get("picture")

    identity = db.execute(
        select(models.OAuthIdentity).where(
            models.OAuthIdentity.provider == "google",
            models.OAuthIdentity.provider_user_id == sub,
        )
    ).scalar_one_or_none()

    if identity:
        user = db.get(models.User, identity.user_id)
    else:
        user = None
        if email:
            user = db.execute(
                select(models.User).where(models.User.email == email)
            ).scalar_one_or_none()
        if user is None:
            user = models.User(
                email=email,
                username=_unique_username(db, email, name),
                display_name=name,
                avatar_url=picture,
            )
            db.add(user)
            db.flush()
        db.add(models.OAuthIdentity(
            user_id=user.id, provider="google", provider_user_id=sub, email=email,
        ))

    user.last_seen_at = _now()
    if picture and not user.avatar_url:
        user.avatar_url = picture
    db.flush()
    return user


def create_session(db: Session, user_id: str, user_agent: str | None) -> str:
    """Create an auth session; return the RAW token (stored only hashed)."""
    raw = secrets.token_urlsafe(32)
    db.add(models.AuthSession(
        user_id=user_id,
        token_hash=_hash(raw),
        expires_at=_now() + timedelta(days=config.SESSION_TTL_DAYS),
        user_agent=(user_agent or "")[:400],
    ))
    db.flush()
    return raw


def get_user_for_token(db: Session, raw_token: str | None) -> models.User | None:
    if not raw_token:
        return None
    sess = db.execute(
        select(models.AuthSession).where(models.AuthSession.token_hash == _hash(raw_token))
    ).scalar_one_or_none()
    if sess is None or sess.revoked_at is not None or sess.expires_at < _now():
        return None
    return db.get(models.User, sess.user_id)


def revoke_token(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    sess = db.execute(
        select(models.AuthSession).where(models.AuthSession.token_hash == _hash(raw_token))
    ).scalar_one_or_none()
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = _now()


def user_public(user: models.User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "displayName": user.display_name,
        "avatarUrl": user.avatar_url,
        "bio": user.bio,
        "createdAt": user.created_at.isoformat() if user.created_at else None,
    }
