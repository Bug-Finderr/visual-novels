from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import optional_user
from app.models.schemas import SessionCreateRequest, SessionPatchRequest
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201)
def create_session(payload: SessionCreateRequest, user: dict | None = Depends(optional_user)):
    return session_service.create(payload.model_dump(), owner_id=(user["id"] if user else None))


@router.get("")
def list_sessions():
    return session_service.get_all()


@router.get("/{session_id}")
def get_session(session_id: str):
    session = session_service.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}")
def delete_session(session_id: str):
    session = session_service.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session_service.delete(session_id)
    return {"ok": True}


@router.patch("/{session_id}")
def patch_session(session_id: str, payload: SessionPatchRequest):
    session = session_service.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session_service.patch(session_id, payload.model_dump(exclude_none=True))
    return {"ok": True}


@router.get("/{session_id}/characters")
def get_characters(session_id: str):
    return session_service.get_characters(session_id)


@router.get("/{session_id}/scenes")
def get_scenes(session_id: str):
    return session_service.get_scenes(session_id)


@router.post("/{session_id}/continue", status_code=201)
def continue_to_next_chapter(session_id: str):
    """Spawn a child session continuing from this one's chosen ending.

    Requires the parent to have a chosen_ending_id (the player must have
    actually reached an ending). The child has the same setup + parent
    linkage; its generation pipeline detects the parent and runs the
    continuation world-build prompt instead of a fresh one.
    """
    parent = session_service.get_by_id(session_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent session not found")
    if not parent.get("chosen_ending_id"):
        raise HTTPException(
            status_code=400,
            detail="Cannot continue — the previous chapter hasn't reached an ending yet.",
        )
    child = session_service.create_continuation(parent)
    return child
