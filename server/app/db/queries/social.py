"""Likes / ratings / comments, with the sessions denormalized counters kept in
sync in the SAME transaction as each mutation."""
from app.db.database import db, rows_to_list


def like(user_id: str, session_id: str) -> bool:
    """Returns True if newly liked (count changed)."""
    with db() as conn:
        if conn.execute(
            "SELECT 1 FROM likes WHERE user_id = ? AND session_id = ?", (user_id, session_id)
        ).fetchone():
            return False
        conn.execute(
            "INSERT INTO likes (user_id, session_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (user_id, session_id),
        )
        conn.execute("UPDATE sessions SET like_count = like_count + 1 WHERE id = ?", (session_id,))
        return True


def unlike(user_id: str, session_id: str) -> bool:
    with db() as conn:
        if not conn.execute(
            "SELECT 1 FROM likes WHERE user_id = ? AND session_id = ?", (user_id, session_id)
        ).fetchone():
            return False
        conn.execute("DELETE FROM likes WHERE user_id = ? AND session_id = ?", (user_id, session_id))
        conn.execute(
            "UPDATE sessions SET like_count = GREATEST(like_count - 1, 0) WHERE id = ?", (session_id,)
        )
        return True


def rate(user_id: str, session_id: str, score: int) -> None:
    score = max(1, min(5, int(score)))
    with db() as conn:
        row = conn.execute(
            "SELECT score FROM ratings WHERE user_id = ? AND session_id = ?", (user_id, session_id)
        ).fetchone()
        if row:
            old = int(row["score"])
            conn.execute(
                "UPDATE ratings SET score = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND session_id = ?",
                (score, user_id, session_id),
            )
            conn.execute("UPDATE sessions SET rating_sum = rating_sum + ? WHERE id = ?", (score - old, session_id))
        else:
            conn.execute(
                "INSERT INTO ratings (user_id, session_id, score) VALUES (?, ?, ?)",
                (user_id, session_id, score),
            )
            conn.execute(
                "UPDATE sessions SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE id = ?",
                (score, session_id),
            )


def my_reactions(user_id: str, session_id: str) -> dict:
    with db() as conn:
        liked = conn.execute(
            "SELECT 1 FROM likes WHERE user_id = ? AND session_id = ?", (user_id, session_id)
        ).fetchone()
        r = conn.execute(
            "SELECT score FROM ratings WHERE user_id = ? AND session_id = ?", (user_id, session_id)
        ).fetchone()
    return {"liked": bool(liked), "myRating": (int(r["score"]) if r else None)}


def add_comment(comment_id: str, session_id: str, user_id: str, body: str,
                parent_id: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO comments (id, session_id, user_id, parent_comment_id, body)
            VALUES (?, ?, ?, ?, ?)
            """,
            (comment_id, session_id, user_id, parent_id, body),
        )
        conn.execute("UPDATE sessions SET comment_count = comment_count + 1 WHERE id = ?", (session_id,))


def delete_comment(comment_id: str, user_id: str) -> bool:
    """Soft-delete the caller's own comment. Returns True if it was theirs."""
    with db() as conn:
        row = conn.execute(
            "SELECT session_id FROM comments WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (comment_id, user_id),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE comments SET deleted_at = CURRENT_TIMESTAMP, body = '' WHERE id = ?", (comment_id,)
        )
        conn.execute(
            "UPDATE sessions SET comment_count = GREATEST(comment_count - 1, 0) WHERE id = ?",
            (row["session_id"],),
        )
        return True


def list_comments(session_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.parent_comment_id, c.body, c.created_at, c.deleted_at,
              c.user_id, u.username, u.display_name, u.avatar_url
            FROM comments c JOIN users u ON u.id = c.user_id
            WHERE c.session_id = ? ORDER BY c.created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return rows_to_list(rows)


def increment_play_count(session_id: str) -> None:
    with db() as conn:
        conn.execute("UPDATE sessions SET play_count = play_count + 1 WHERE id = ?", (session_id,))
