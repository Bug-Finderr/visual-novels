"""Cache of pre-generated full-beat statements.

When the spine is pre-rendered at generation time we save each beat's
complete dialogue here. At runtime a /choice or /advance becomes a single
DB lookup (~5 ms) instead of a Flash 2.5 call (~1.5 s).
"""
from __future__ import annotations

import json

from app.db.database import db


def get(session_id: str, beat_index: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT statements FROM beat_expansions WHERE session_id = ? AND beat_index = ?",
            (session_id, beat_index),
        ).fetchone()
    if not row:
        return None
    try:
        return {"statements": json.loads(row["statements"])}
    except Exception:
        return None


def save(session_id: str, beat_index: int, statements: list) -> None:
    payload = json.dumps(statements, ensure_ascii=False)
    with db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO beat_expansions (session_id, beat_index, statements)
            VALUES (?, ?, ?)
            """,
            (session_id, beat_index, payload),
        )


def beat_indices_for_session(session_id: str) -> set[int]:
    with db() as conn:
        rows = conn.execute(
            "SELECT beat_index FROM beat_expansions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    return {r["beat_index"] for r in rows}


def delete_for_session(session_id: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM beat_expansions WHERE session_id = ?", (session_id,))
