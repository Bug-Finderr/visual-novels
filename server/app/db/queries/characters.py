import json

from app.db.database import db, row_to_dict, rows_to_list


def insert(session_id: str, character: dict) -> None:
    params = {
        "color": "#FFFFFF",
        "is_dynamic": 0,
        "backstory": None,
        "relationship": None,
        "speech_style": None,
        "voice_caption": None,
        **character,
        "session_id": session_id,
        "quirks": json.dumps(character.get("quirks") or []),
    }
    with db() as conn:
        conn.execute(
            """
            INSERT INTO characters (id, session_id, name, color, role, personality, appearance,
                backstory, relationship, speech_style, quirks, is_dynamic, voice_caption)
            VALUES (:id, :session_id, :name, :color, :role, :personality, :appearance,
                :backstory, :relationship, :speech_style, :quirks, :is_dynamic, :voice_caption)
            """,
            params,
        )


def get_by_session(session_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM characters WHERE session_id = ?", (session_id,)
        ).fetchall()
    return rows_to_list(rows)


def get_by_id(session_id: str, character_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM characters WHERE session_id = ? AND id = ?",
            (session_id, character_id),
        ).fetchone()
    return row_to_dict(row)


def mark_sprites_generated(session_id: str, character_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE characters SET sprites_generated = 1 WHERE session_id = ? AND id = ?",
            (session_id, character_id),
        )
