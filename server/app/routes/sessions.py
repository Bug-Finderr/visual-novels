from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import get_current_user, require_owner, require_readable
from app.models.schemas import SessionCreateRequest, SessionPatchRequest
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201)
def create_session(payload: SessionCreateRequest, user: dict = Depends(get_current_user)):
    return session_service.create(payload.model_dump(), owner_id=user["id"])


@router.get("")
def list_sessions():
    # Public feed only. A user's own stories come from GET /api/v1/library.
    return session_service.list_public()


@router.get("/{session_id}")
def get_session(session_id: str, _s: dict = Depends(require_readable)):
    return session_service.get_by_id(session_id)


@router.delete("/{session_id}")
def delete_session(session_id: str, _s: dict = Depends(require_owner)):
    session_service.delete(session_id)
    return {"ok": True}


@router.patch("/{session_id}")
def patch_session(
    session_id: str, payload: SessionPatchRequest, _s: dict = Depends(require_owner)
):
    session_service.patch(session_id, payload.model_dump(exclude_none=True))
    return {"ok": True}


@router.get("/{session_id}/characters")
def get_characters(session_id: str, _s: dict = Depends(require_readable)):
    return session_service.get_characters(session_id)


@router.get("/{session_id}/scenes")
def get_scenes(session_id: str, _s: dict = Depends(require_readable)):
    return session_service.get_scenes(session_id)


@router.post("/{session_id}/continue", status_code=201)
def continue_to_next_chapter(session_id: str, parent: dict = Depends(require_owner)):
    """Spawn a child session continuing from this one's chosen ending. The child
    inherits the owner. Requires the parent to have reached an ending."""
    if not parent.get("chosen_ending_id"):
        raise HTTPException(
            status_code=400,
            detail="Cannot continue — the previous chapter hasn't reached an ending yet.",
        )
    return session_service.create_continuation(parent)
