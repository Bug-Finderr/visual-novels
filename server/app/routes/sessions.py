from fastapi import APIRouter, HTTPException

from app.models.schemas import SessionCreateRequest, SessionPatchRequest
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201)
def create_session(payload: SessionCreateRequest):
    return session_service.create(payload.model_dump())


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
