from app.db.database import db, row_to_dict, rows_to_list


def insert(session_id: str, scene: dict) -> None:
    params = {
        "is_dynamic": 0,
        "narrative_context": None,
        **scene,
        "session_id": session_id,
    }
    with db() as conn:
        conn.execute(
            """
            INSERT INTO scenes (id, session_id, name, description, narrative_context, is_dynamic)
            VALUES (:id, :session_id, :name, :description, :narrative_context, :is_dynamic)
            """,
            params,
        )


def get_by_session(session_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM scenes WHERE session_id = ?", (session_id,)
        ).fetchall()
    return rows_to_list(rows)


def get_by_id(session_id: str, scene_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM scenes WHERE session_id = ? AND id = ?",
            (session_id, scene_id),
        ).fetchone()
    return row_to_dict(row)


def mark_image_generated(session_id: str, scene_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE scenes SET image_generated = 1 WHERE session_id = ? AND id = ?",
            (session_id, scene_id),
        )
