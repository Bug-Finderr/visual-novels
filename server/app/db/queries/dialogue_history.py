from app.db.database import db, rows_to_list


def insert(session_id: str, role: str, content: str, label_context: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO dialogue_history (session_id, role, content, label_context)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, label_context),
        )


def get_recent(session_id: str, limit: int = 50) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT role, content, label_context, created_at
            FROM dialogue_history
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return list(reversed(rows_to_list(rows)))


def get_all(session_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT role, content, label_context, created_at
            FROM dialogue_history
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return rows_to_list(rows)


def delete_by_session(session_id: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM dialogue_history WHERE session_id = ?", (session_id,))
