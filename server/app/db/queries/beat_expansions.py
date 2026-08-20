"""Cache of pre-generated full-beat statements with per-choice variants.

Each beat has up to 3 variants — one per `alignmentTag` from the PREVIOUS
beat's choices. So when the player picks choice X (tag T) in beat N, the
runtime looks up the beat N+1 variant for T and the next scene actually
reacts to the choice they just made.

Schema PK = (session_id, beat_index, source_choice_tag). Empty string ''
is the default tag — used as a fall-back when the variant the player
needs isn't cached (e.g. live cache-miss recovery, or `/advance` from
the opening before any choice has been made).
"""
from __future__ import annotations

import json

from app.db.database import db


def get(session_id: str, beat_index: int, source_choice_tag: str = "") -> dict | None:
    with db() as conn:
        row = conn.execute(
            """
            SELECT statements
            FROM beat_expansions
            WHERE session_id = ? AND beat_index = ? AND source_choice_tag = ?
            """,
            (session_id, beat_index, source_choice_tag or ""),
        ).fetchone()
    if not row:
        return None
    try:
        return {"statements": json.loads(row["statements"])}
    except Exception:
        return None


def get_any(session_id: str, beat_index: int) -> dict | None:
    """Return ANY cached variant for this beat — used when the player's
    specific choice tag wasn't pre-rendered (rare; usually means the
    pre-gen pool hit an error on that variant)."""
    with db() as conn:
        row = conn.execute(
            """
            SELECT statements
            FROM beat_expansions
            WHERE session_id = ? AND beat_index = ?
            ORDER BY (source_choice_tag = '') DESC, source_choice_tag ASC
            LIMIT 1
            """,
            (session_id, beat_index),
        ).fetchone()
    if not row:
        return None
    try:
        return {"statements": json.loads(row["statements"])}
    except Exception:
        return None


def save(
    session_id: str,
    beat_index: int,
    source_choice_tag: str,
    statements: list,
) -> None:
    payload = json.dumps(statements, ensure_ascii=False)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO beat_expansions
                (session_id, beat_index, source_choice_tag, statements)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (session_id, beat_index, source_choice_tag)
            DO UPDATE SET statements = EXCLUDED.statements
            """,
            (session_id, beat_index, source_choice_tag or "", payload),
        )


def all_statements_for_session(session_id: str) -> list[list[dict]]:
    """Every cached variant's statements list for this session — used to scan
    for which (character, expression) pairs and scenes a story actually uses,
    so image generation can skip anything no beat ever calls for."""
    with db() as conn:
        rows = conn.execute(
            "SELECT statements FROM beat_expansions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["statements"]))
        except Exception:
            continue
    return out


def variants_for_session(session_id: str) -> set[tuple[int, str]]:
    """Return {(beat_index, source_choice_tag)} for everything cached so far."""
    with db() as conn:
        rows = conn.execute(
            "SELECT beat_index, source_choice_tag FROM beat_expansions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    return {(r["beat_index"], r["source_choice_tag"] or "") for r in rows}


def beat_indices_for_session(session_id: str) -> set[int]:
    """Return the set of beat indices that have AT LEAST one variant cached.
    Kept for backwards compat with callers that only care 'is this beat done?'."""
    return {bi for (bi, _) in variants_for_session(session_id)}


def delete_for_session(session_id: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM beat_expansions WHERE session_id = ?", (session_id,))
