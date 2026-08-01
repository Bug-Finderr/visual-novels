"""Owner-scoped story endpoints under /api/v1."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import get_current_user, require_owner
from app.services import session_service

router = APIRouter(prefix="/api/v1", tags=["library"])


@router.get("/library")
def my_library(user: dict = Depends(get_current_user)):
    """The signed-in user's own stories."""
    return {"stories": session_service.list_for_owner(user["id"])}


@router.post("/library/{session_id}/publish")
def publish_story(session_id: str, story: dict = Depends(require_owner)):
    """Make an owned story public so it appears in Explore."""
    if story.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Only a finished story can be published.")
    session_service.set_visibility(session_id, "public")
    return {"visibility": "public"}


@router.post("/library/{session_id}/unpublish")
def unpublish_story(session_id: str, _s: dict = Depends(require_owner)):
    session_service.set_visibility(session_id, "private")
    return {"visibility": "private"}
