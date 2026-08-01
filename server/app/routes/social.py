"""Social endpoints under /api/v1: story detail + likes / ratings / comments."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, optional_user, require_readable
from app.db.queries import follows as follow_queries
from app.db.queries import sessions as session_queries
from app.db.queries import social as social_queries
from app.db.queries import users as user_queries

router = APIRouter(prefix="/api/v1", tags=["social"])


class RateReq(BaseModel):
    score: int = Field(ge=1, le=5)


class CommentReq(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parentId: str | None = None


def card_public(card: dict) -> dict:
    """Serialize a story card (author + counts), hiding owner-only internals."""
    rc = int(card.get("rating_count") or 0)
    rs = int(card.get("rating_sum") or 0)
    return {
        "id": card["id"],
        "title": card["title"],
        "status": card["status"],
        "setup_genre": card.get("setup_genre"),
        "setup_tone": card.get("setup_tone"),
        "chapter_number": card.get("chapter_number"),
        "visibility": card.get("visibility"),
        "created_at": card.get("created_at"),
        "updated_at": card.get("updated_at"),
        "published_at": card.get("published_at"),
        "likeCount": int(card.get("like_count") or 0),
        "commentCount": int(card.get("comment_count") or 0),
        "playCount": int(card.get("play_count") or 0),
        "ratingCount": rc,
        "ratingAvg": round(rs / rc, 2) if rc else None,
        "setting": card.get("setup_setting"),
        "premise": card.get("setup_premise"),
        "author": {
            "id": card.get("author_id"),
            "username": card.get("author_username"),
            "displayName": card.get("author_name"),
            "avatarUrl": card.get("author_avatar"),
        },
    }


@router.get("/stories/{session_id}")
def story_detail(
    session_id: str,
    _s: dict = Depends(require_readable),
    user: dict | None = Depends(optional_user),
):
    card = session_queries.get_card(session_id)
    if not card:
        raise HTTPException(status_code=404, detail="Not found")
    out = card_public(card)
    out["me"] = (
        social_queries.my_reactions(user["id"], session_id)
        if user else {"liked": False, "myRating": None}
    )
    return out


@router.post("/stories/{session_id}/like")
def like_story(session_id: str, user: dict = Depends(get_current_user), _s: dict = Depends(require_readable)):
    social_queries.like(user["id"], session_id)
    return {"liked": True}


@router.delete("/stories/{session_id}/like")
def unlike_story(session_id: str, user: dict = Depends(get_current_user), _s: dict = Depends(require_readable)):
    social_queries.unlike(user["id"], session_id)
    return {"liked": False}


@router.post("/stories/{session_id}/rate")
def rate_story(session_id: str, payload: RateReq, user: dict = Depends(get_current_user), _s: dict = Depends(require_readable)):
    social_queries.rate(user["id"], session_id, payload.score)
    return {"myRating": payload.score}


@router.get("/stories/{session_id}/comments")
def list_comments(session_id: str, _s: dict = Depends(require_readable)):
    rows = social_queries.list_comments(session_id)
    return [
        {
            "id": r["id"],
            "parentId": r.get("parent_comment_id"),
            "body": "" if r.get("deleted_at") else r["body"],
            "deleted": bool(r.get("deleted_at")),
            "createdAt": r.get("created_at"),
            "author": {
                "id": r["user_id"],
                "username": r["username"],
                "displayName": r.get("display_name"),
                "avatarUrl": r.get("avatar_url"),
            },
        }
        for r in rows
    ]


@router.post("/stories/{session_id}/comments")
def add_comment(session_id: str, payload: CommentReq, user: dict = Depends(get_current_user), _s: dict = Depends(require_readable)):
    cid = uuid.uuid4().hex
    social_queries.add_comment(cid, session_id, user["id"], payload.body.strip(), payload.parentId)
    return {"id": cid}


@router.delete("/stories/{session_id}/comments/{comment_id}")
def delete_comment(session_id: str, comment_id: str, user: dict = Depends(get_current_user), _s: dict = Depends(require_readable)):
    if not social_queries.delete_comment(comment_id, user["id"]):
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"deleted": comment_id}


# --- Creator profiles + follow graph -------------------------------------
@router.get("/users/{username}")
def user_profile(username: str, viewer: dict | None = Depends(optional_user)):
    u = user_queries.get_by_username(username)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    c = follow_queries.counts(u["id"])
    stories = session_queries.get_public_by_owner(u["id"])
    return {
        "id": u["id"],
        "username": u["username"],
        "displayName": u.get("display_name"),
        "avatarUrl": u.get("avatar_url"),
        "bio": u.get("bio"),
        "createdAt": u.get("created_at"),
        "followers": c["followers"],
        "following": c["following"],
        "storyCount": len(stories),
        "isMe": bool(viewer and viewer["id"] == u["id"]),
        "isFollowing": bool(viewer and not (viewer["id"] == u["id"])
                            and follow_queries.is_following(viewer["id"], u["id"])),
        "stories": stories,
    }


@router.post("/users/{username}/follow")
def follow_user(username: str, user: dict = Depends(get_current_user)):
    u = user_queries.get_by_username(username)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")
    follow_queries.follow(user["id"], u["id"])
    return {"isFollowing": True, "followers": follow_queries.counts(u["id"])["followers"]}


@router.delete("/users/{username}/follow")
def unfollow_user(username: str, user: dict = Depends(get_current_user)):
    u = user_queries.get_by_username(username)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    follow_queries.unfollow(user["id"], u["id"])
    return {"isFollowing": False, "followers": follow_queries.counts(u["id"])["followers"]}


@router.get("/feed")
def following_feed(user: dict = Depends(get_current_user)):
    """Published stories from the creators the current user follows."""
    ids = follow_queries.following_ids(user["id"])
    return session_queries.get_public_from_owners(ids)
