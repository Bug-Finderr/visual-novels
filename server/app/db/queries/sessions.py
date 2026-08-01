import json

from app.db.database import db, row_to_dict, rows_to_list

_ALLOWED_PATCH_FIELDS = {"title", "status", "current_scene_id", "current_label"}


def save_spine(
    session_id: str,
    *,
    story_spine: list,
    endings: list,
) -> None:
    """Persist the pre-generated story spine + ending catalogue.
    alignment_state is seeded with 0 for every ending id so the dialogue engine
    can simply add weights without first-touch initialization.
    """
    seed = {e["id"]: 0 for e in endings if e.get("id")}
    with db() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET story_spine = ?, endings = ?, alignment_state = ?,
                current_beat_index = 0, chosen_ending_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(story_spine), json.dumps(endings),
             json.dumps(seed), session_id),
        )


def update_alignment(session_id: str, alignment_state: dict) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET alignment_state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(alignment_state), session_id),
        )


def advance_beat(session_id: str, new_index: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET current_beat_index = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_index, session_id),
        )


def set_chosen_ending(session_id: str, ending_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET chosen_ending_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (ending_id, session_id),
        )


def create(session: dict) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, title, status, setup_genre, setup_art_style, setup_setting,
                setup_protagonist_name, setup_protagonist_personality, setup_tone, setup_premise, owner_id)
            VALUES (:id, :title, :status, :setup_genre, :setup_art_style, :setup_setting,
                :setup_protagonist_name, :setup_protagonist_personality, :setup_tone, :setup_premise, :owner_id)
            """,
            session,
        )


def set_chapter_parent(session_id: str, parent_id: str, chapter_number: int) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET parent_session_id = ?, chapter_number = ?
            WHERE id = ?
            """,
            (parent_id, chapter_number, session_id),
        )


def get_all() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, status, setup_genre, setup_art_style, setup_tone,
              created_at, updated_at, last_played_at,
              parent_session_id, chapter_number
            FROM sessions ORDER BY updated_at DESC
            """
        ).fetchall()
    return rows_to_list(rows)


# Card columns shared by the public feed + story detail (joins the author).
_CARD_COLS = """
    s.id, s.title, s.status, s.setup_genre, s.setup_art_style, s.setup_tone,
    s.created_at, s.updated_at, s.published_at, s.chapter_number, s.visibility,
    s.like_count, s.comment_count, s.play_count, s.rating_sum, s.rating_count,
    u.username AS author_username, u.display_name AS author_name,
    u.avatar_url AS author_avatar, s.owner_id AS author_id
"""

_PUBLIC_SORTS = {
    "new": "s.published_at DESC NULLS LAST, s.updated_at DESC",
    "top": "s.like_count DESC, s.updated_at DESC",
    "rated": "(CASE WHEN s.rating_count > 0 THEN CAST(s.rating_sum AS float) / s.rating_count ELSE 0 END) DESC, s.rating_count DESC",
    "played": "s.play_count DESC, s.updated_at DESC",
}


def get_public(sort: str = "new", limit: int = 60) -> list[dict]:
    order = _PUBLIC_SORTS.get(sort, _PUBLIC_SORTS["new"])
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT {_CARD_COLS}
            FROM sessions s LEFT JOIN users u ON u.id = s.owner_id
            WHERE s.visibility = 'public'
            ORDER BY {order}
            LIMIT {int(limit)}
            """
        ).fetchall()
    return rows_to_list(rows)


def get_card(session_id: str) -> dict | None:
    """A single story's card-level metadata + author + counts (for detail)."""
    with db() as conn:
        row = conn.execute(
            f"""
            SELECT {_CARD_COLS}, s.setup_setting, s.setup_premise, s.world_lore
            FROM sessions s LEFT JOIN users u ON u.id = s.owner_id
            WHERE s.id = ?
            """,
            (session_id,),
        ).fetchone()
    return row_to_dict(row)


def get_for_owner(owner_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, status, setup_genre, setup_art_style, setup_tone,
              created_at, updated_at, last_played_at,
              parent_session_id, chapter_number, visibility, published_at,
              like_count, comment_count, play_count, rating_sum, rating_count
            FROM sessions WHERE owner_id = ? ORDER BY updated_at DESC
            """,
            (owner_id,),
        ).fetchall()
    return rows_to_list(rows)


def set_visibility(session_id: str, visibility: str) -> None:
    """Publish ('public') or unpublish ('private'/'unlisted') a story."""
    with db() as conn:
        if visibility == "public":
            conn.execute(
                """
                UPDATE sessions
                SET visibility = ?, published_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (visibility, session_id),
            )
        else:
            conn.execute(
                """
                UPDATE sessions
                SET visibility = ?, published_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (visibility, session_id),
            )


def count_ownerless() -> int:
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE owner_id IS NULL").fetchone()
    return int(row["n"]) if row else 0


def claim_ownerless(owner_id: str) -> int:
    """Assign every unowned story to `owner_id`. Returns how many were claimed."""
    n = count_ownerless()
    if n:
        with db() as conn:
            conn.execute("UPDATE sessions SET owner_id = ? WHERE owner_id IS NULL", (owner_id,))
    return n


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


def update_engine(session_id: str, engine: str) -> None:
    """Record which story-generation engine actually produced this session."""
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET storygen_engine = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (engine, session_id),
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
