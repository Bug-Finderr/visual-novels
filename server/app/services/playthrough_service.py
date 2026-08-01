"""Per-user playthrough resolution."""
from uuid import uuid4

from app.db.queries import playthroughs as pt_queries


def get_or_create(user_id: str, story_id: str) -> dict:
    """Return this user's playthrough for the story, creating a fresh one
    (at the opening, empty alignment) on first play."""
    pt = pt_queries.get(user_id, story_id)
    if pt:
        return pt
    pt_queries.create(str(uuid4()), user_id, story_id)
    return pt_queries.get(user_id, story_id)
