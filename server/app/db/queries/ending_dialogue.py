"""Cache of pre-generated ending dialogue.

Each session has 5 candidate endings; this table stores the full epilogue
statements for each one so the final-beat runtime path is a DB lookup
keyed by the chosen ending id, rather than a live LLM call.
"""
from __future__ import annotations

import json

from app.db.database import db


def get(session_id: str, ending_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT statements FROM ending_dialogue WHERE session_id = ? AND ending_id = ?",
            (session_id, ending_id),
        ).fetchone()
    if not row:
        return None
    try:
        return {"statements": json.loads(row["statements"])}
    except Exception:
        return None


def save(session_id: str, ending_id: str, statements: list) -> None:
    payload = json.dumps(statements, ensure_ascii=False)
    with db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO ending_dialogue (session_id, ending_id, statements)
            VALUES (?, ?, ?)
            """,
            (session_id, ending_id, payload),
        )


def ending_ids_for_session(session_id: str) -> set[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT ending_id FROM ending_dialogue WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    return {r["ending_id"] for r in rows}


def delete_for_session(session_id: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM ending_dialogue WHERE session_id = ?", (session_id,))
