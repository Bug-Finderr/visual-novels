"""Follow graph."""
from app.db.database import db


def follow(follower_id: str, followee_id: str) -> None:
    if follower_id == followee_id:
        return
    with db() as conn:
        conn.execute(
            "INSERT INTO follows (follower_id, followee_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (follower_id, followee_id),
        )


def unfollow(follower_id: str, followee_id: str) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM follows WHERE follower_id = ? AND followee_id = ?",
            (follower_id, followee_id),
        )


def is_following(follower_id: str, followee_id: str) -> bool:
    with db() as conn:
        return bool(conn.execute(
            "SELECT 1 FROM follows WHERE follower_id = ? AND followee_id = ?",
            (follower_id, followee_id),
        ).fetchone())


def counts(user_id: str) -> dict:
    with db() as conn:
        followers = conn.execute(
            "SELECT COUNT(*) AS n FROM follows WHERE followee_id = ?", (user_id,)
        ).fetchone()["n"]
        following = conn.execute(
            "SELECT COUNT(*) AS n FROM follows WHERE follower_id = ?", (user_id,)
        ).fetchone()["n"]
    return {"followers": int(followers), "following": int(following)}


def following_ids(user_id: str) -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT followee_id FROM follows WHERE follower_id = ?", (user_id,)
        ).fetchall()
    return [r["followee_id"] for r in rows]
