"""Save / Load / Restart routes — per-user playthrough checkpoints.

Saves and restart operate on the CALLER's own playthrough of the story, so a
player of a public story never touches the author's content or another player's
progress. The client builds a SaveSnapshot from its in-game state and POSTs it;
on load it reads it back to rebuild the stage. Restart resets the caller's
playthrough to the opening (shared cached beats/audio are untouched).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, require_readable
from app.db.queries import playthroughs as pt_queries
from app.db.queries import saves as save_queries
from app.services import playthrough_service

router = APIRouter(prefix="/api/v1/sessions", tags=["saves"])


class VisibleChar(BaseModel):
    id: str
    expression: str | None = "neutral"
    position: str | None = "center"


class SaveSnapshot(BaseModel):
    currentLabel: str
    statementIndex: int = 0
    currentSceneId: str | None = None
    currentBeatIndex: int = 0
    alignmentState: dict[str, int] = Field(default_factory=dict)
    chosenEndingId: str | None = None
    visibleCharacters: list[VisibleChar] = Field(default_factory=list)


class CreateSaveRequest(BaseModel):
    name: str | None = None
    slot: int | None = None
    snapshot: SaveSnapshot


@router.post("/{session_id}/saves")
def create_save(
    session_id: str,
    payload: CreateSaveRequest,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    snap = payload.snapshot.model_dump()
    if payload.slot is not None:
        save_id = save_queries.upsert_slot(session_id, user["id"], payload.slot, snap, name=payload.name)
    else:
        save_id = save_queries.insert(session_id, user["id"], snap, name=payload.name)
    return {"id": save_id, "slot": payload.slot, "name": payload.name}


@router.get("/{session_id}/saves")
def list_saves(
    session_id: str,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    return save_queries.list_for_session(session_id, user["id"])


@router.get("/{session_id}/saves/{save_id}")
def load_save(
    session_id: str,
    save_id: str,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    save = save_queries.get(session_id, user["id"], save_id)
    if not save:
        raise HTTPException(status_code=404, detail="Save not found")
    return save


@router.delete("/{session_id}/saves/{save_id}")
def delete_save(
    session_id: str,
    save_id: str,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    save_queries.delete(session_id, user["id"], save_id)
    return {"deleted": save_id}


@router.post("/{session_id}/restart")
def restart_session(
    session_id: str,
    user: dict = Depends(get_current_user),
    _s: dict = Depends(require_readable),
):
    """Reset THIS user's playthrough to the opening. Shared story content and
    the cached beats/audio are left intact, so other players and the cache are
    unaffected."""
    pt = playthrough_service.get_or_create(user["id"], session_id)
    pt_queries.restart(pt["id"])
    return {"status": "restarted", "sessionId": session_id}
