"""Owner-scoped story endpoints under /api/v1."""
from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.services import session_service

router = APIRouter(prefix="/api/v1", tags=["library"])


@router.get("/library")
def my_library(user: dict = Depends(get_current_user)):
    """The signed-in user's own stories."""
    return {"stories": session_service.list_for_owner(user["id"])}
