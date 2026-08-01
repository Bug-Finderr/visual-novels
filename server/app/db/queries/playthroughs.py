"""Per-user play state for a story.

Splits the mutable playthrough progress (which beat, alignment weights, chosen
ending, current label/scene) off the shared, immutable `sessions` (Story) row,
so multiple users can play the same published story independently.
"""
import json

from app.db.database import db, row_to_dict


def get(user_id: str, story_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM playthroughs WHERE user_id = ? AND story_id = ?",
            (user_id, story_id),
        ).fetchone()
    return row_to_dict(row)


def get_by_id(playthrough_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM playthroughs WHERE id = ?", (playthrough_id,)
        ).fetchone()
    return row_to_dict(row)


def create(playthrough_id: str, user_id: str, story_id: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO playthroughs (id, user_id, story_id, current_label, alignment_state)
            VALUES (:id, :user_id, :story_id, 'Start', '{}')
            ON CONFLICT (user_id, story_id) DO NOTHING
            """,
            {"id": playthrough_id, "user_id": user_id, "story_id": story_id},
        )


def update_alignment(playthrough_id: str, alignment_state: dict) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE playthroughs SET alignment_state = ?, last_played_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(alignment_state), playthrough_id),
        )


def advance_beat(playthrough_id: str, beat_index: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE playthroughs SET current_beat_index = ?, last_played_at = CURRENT_TIMESTAMP WHERE id = ?",
            (beat_index, playthrough_id),
        )


def set_chosen_ending(playthrough_id: str, ending_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE playthroughs SET chosen_ending_id = ? WHERE id = ?",
            (ending_id, playthrough_id),
        )


def update_current_label(playthrough_id: str, label: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE playthroughs SET current_label = ?, last_played_at = CURRENT_TIMESTAMP WHERE id = ?",
            (label, playthrough_id),
        )


def update_current_scene(playthrough_id: str, scene_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE playthroughs SET current_scene_id = ? WHERE id = ?",
            (scene_id, playthrough_id),
        )


def restart(playthrough_id: str) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE playthroughs
            SET current_label = 'Start', statement_index = 0, current_beat_index = 0,
                alignment_state = '{}', chosen_ending_id = NULL,
                current_scene_id = NULL, last_played_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (playthrough_id,),
        )
