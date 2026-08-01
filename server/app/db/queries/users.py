"""User lookups for public profiles."""
from app.db.database import db, row_to_dict


def get_by_username(username: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, avatar_url, bio, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row_to_dict(row)
