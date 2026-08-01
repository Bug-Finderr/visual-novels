"""Owner-scoped story endpoints under /api/v1."""
from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.services import session_service

router = APIRouter(prefix="/api/v1", tags=["library"])


@router.get("/library")
def my_library(user: dict = Depends(get_current_user)):
    """The signed-in user's own stories, plus a count of legacy unowned ones
    they can claim."""
    return {
        "stories": session_service.list_for_owner(user["id"]),
        "ownerlessCount": session_service.ownerless_count(),
    }


@router.post("/library/claim")
def claim_legacy(user: dict = Depends(get_current_user)):
    """Assign all currently-unowned stories to the signed-in user."""
    return {"claimed": session_service.claim_ownerless(user["id"])}
