"""Ren'Py-style save/load: each row is a snapshot of one playthrough's state.

A save is enough info to drop the player back EXACTLY where they were:
  - current_label / statement_index (which script line they were about to read)
  - current_beat_index / alignment_state / chosen_ending_id (spine progress)
  - current_scene_id (background)
  - visible_characters (which sprites are on stage, with expression + position)

`slot` is optional — `None` for auto-saves, an integer for named slots ("1",
"2"...). `name` is a free-text label the player can give a save.
"""
from __future__ import annotations

import json
from uuid import uuid4

from app.db.database import db, row_to_dict, rows_to_list


def insert(session_id: str, snapshot: dict, *, name: str | None = None, slot: int | None = None) -> str:
    save_id = str(uuid4())
    with db() as conn:
        conn.execute(
            """
            INSERT INTO saves (id, session_id, slot, name, current_label, statement_index,
                current_scene_id, current_beat_index, alignment_state, chosen_ending_id,
                visible_characters)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                save_id, session_id, slot, name,
                snapshot.get("currentLabel") or "Start",
                int(snapshot.get("statementIndex") or 0),
                snapshot.get("currentSceneId"),
                int(snapshot.get("currentBeatIndex") or 0),
                json.dumps(snapshot.get("alignmentState") or {}),
                snapshot.get("chosenEndingId"),
                json.dumps(snapshot.get("visibleCharacters") or []),
            ),
        )
    return save_id


def get(session_id: str, save_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM saves WHERE id = ? AND session_id = ?",
            (save_id, session_id),
        ).fetchone()
    if not row:
        return None
    d = row_to_dict(row)
    d["alignment_state"] = json.loads(d.get("alignment_state") or "{}")
    d["visible_characters"] = json.loads(d.get("visible_characters") or "[]")
    return d


def list_for_session(session_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, slot, name, current_label, statement_index, current_scene_id,
              current_beat_index, chosen_ending_id, created_at
            FROM saves WHERE session_id = ? ORDER BY created_at DESC
            """,
            (session_id,),
        ).fetchall()
    return rows_to_list(rows)


def delete(session_id: str, save_id: str) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM saves WHERE id = ? AND session_id = ?",
            (save_id, session_id),
        )


def upsert_slot(session_id: str, slot: int, snapshot: dict, name: str | None = None) -> str:
    """Named-slot save: replaces any existing save in this slot."""
    with db() as conn:
        conn.execute("DELETE FROM saves WHERE session_id = ? AND slot = ?", (session_id, slot))
    return insert(session_id, snapshot, name=name, slot=slot)
