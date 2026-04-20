import json

from app.db.database import db, row_to_dict, rows_to_list

_ALLOWED_PATCH_FIELDS = {"title", "status", "current_scene_id", "current_label"}


def create(session: dict) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, title, status, setup_genre, setup_art_style, setup_setting,
                setup_protagonist_name, setup_protagonist_personality, setup_tone, setup_premise)
            VALUES (:id, :title, :status, :setup_genre, :setup_art_style, :setup_setting,
                :setup_protagonist_name, :setup_protagonist_personality, :setup_tone, :setup_premise)
            """,
            session,
        )


def get_all() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, status, setup_genre, setup_art_style, setup_tone,
              created_at, updated_at, last_played_at
            FROM sessions ORDER BY updated_at DESC
            """
        ).fetchall()
    return rows_to_list(rows)


def get_by_id(session_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row_to_dict(row)


def update_status(session_id: str, status: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, session_id),
        )


def save_story_data(session_id: str, world_lore, plot_arc) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET world_lore = ?, plot_arc = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(world_lore), json.dumps(plot_arc), session_id),
        )


def update_current_scene(session_id: str, scene_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET current_scene_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (scene_id, session_id),
        )


def update_current_label(session_id: str, label: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET current_label = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (label, session_id),
        )


def update_last_played(session_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET last_played_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )


def delete(session_id: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def patch(session_id: str, fields: dict) -> None:
    updates = {k: v for k, v in fields.items() if k in _ALLOWED_PATCH_FIELDS}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    params = {**updates, "id": session_id}
    with db() as conn:
        conn.execute(
            f"UPDATE sessions SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            params,
        )
