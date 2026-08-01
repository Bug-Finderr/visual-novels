import json
import time
from typing import Any

from app.db.database import db


# Sentinel that marks choice-target labels (the body of every `jump <label>`
# entry inside a Choice). The runtime never actually walks these labels —
# clicking a choice fires the API call which replaces the current label —
# so any content is purely defensive. Keeping it as a SENTINEL lets the TTS
# / backfill paths recognize and skip it instead of treating it as narration.
CHOICE_TARGET_SENTINEL = "__choice_target_placeholder__"


def _convert_single(stmt: dict) -> Any:
    t = stmt.get("type")
    if t == "narration":
        return stmt.get("text", "")
    if t == "dialogue":
        expr = stmt.get("expression") or "neutral"
        # Gemini sometimes emits a null speaker when the protagonist is speaking
        # (against our prompt rule). Fall back to the "player" pseudo-id which
        # the frontend maps to the configured protagonist name.
        speaker = stmt.get("speaker") or "player"
        return f"{speaker}:{expr} {stmt.get('text', '')}"
    if t == "scene_change":
        return f"show scene {stmt['sceneId']} with fadeIn"
    if t == "show_character":
        expr = stmt.get("expression") or "neutral"
        pos = stmt.get("position") or "center"
        return f"show character {stmt['characterId']} {expr} at {pos} with fadeIn"
    if t == "hide_character":
        return f"hide character {stmt['characterId']} with fadeOut"
    return None


def _build_choice_statement(choices: list[dict], parent_label: str) -> tuple[dict, dict]:
    choice_obj: dict = {"Choice": {}}
    choice_labels: dict = {}
    for i, choice in enumerate(choices):
        label_name = f"{parent_label}_choice_{i}"
        choice_obj["Choice"][label_name] = {
            "Text": choice["text"],
            "Do": f"jump {label_name}",
            "_consequence": choice.get("consequence", ""),
            # Alignment metadata flows to the client so it can be echoed back
            # in the /choice request and applied to alignment_state server-side.
            "_alignmentTag": choice.get("alignmentTag", ""),
            "_magnitude": int(choice.get("magnitude") or 1),
        }
        choice_labels[label_name] = [CHOICE_TARGET_SENTINEL]
    return choice_obj, choice_labels


def _convert_statement_array(stmt_array: list[dict], parent_label: str) -> tuple[list, dict]:
    statements: list = []
    extra_labels: dict = {}
    for stmt in stmt_array:
        if stmt.get("type") == "choice" or (stmt.get("choices") and len(stmt["choices"]) > 0):
            choices = stmt.get("choices") or []
            choice_stmt, choice_labels = _build_choice_statement(choices, parent_label)
            statements.append(choice_stmt)
            extra_labels.update(choice_labels)
        else:
            converted = _convert_single(stmt)
            if converted is not None:
                statements.append(converted)
    return statements, extra_labels


def build_initial_script(story_data: dict) -> dict:
    """Convert the openingScript into the 'Start' label AND append beat 0's
    pre-baked choices so the player gets agency at the end of the opening
    without an extra /advance LLM round-trip. The first /choice click then
    fetches beat 1 from the cache instantly.
    """
    script: dict = {}
    start_statements, extra_labels = _convert_statement_array(
        story_data["openingScript"], "Start"
    )

    spine = story_data.get("storySpine") or []
    beat0_choices = (spine[0].get("choices") if spine else None) or []
    if beat0_choices:
        choice_stmt, choice_labels = _build_choice_statement(beat0_choices, "Start")
        start_statements.append(choice_stmt)
        extra_labels.update(choice_labels)

    script["Start"] = start_statements
    script.update(extra_labels)
    return script


def build_runtime_label(ai_output: dict, label_prefix: str = "dynamic") -> dict:
    label_name = f"{label_prefix}_{int(time.time() * 1000)}"
    statements, extra_labels = _convert_statement_array(
        ai_output.get("statements") or [], label_name
    )

    if ai_output.get("choices"):
        choice_stmt, choice_labels = _build_choice_statement(ai_output["choices"], label_name)
        statements.append(choice_stmt)
        extra_labels.update(choice_labels)

    return {"labelName": label_name, "statements": statements, "extraLabels": extra_labels}


def save_label(session_id: str, label_name: str, statements: list) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO script_labels (session_id, label_name, statements)
            VALUES (?, ?, ?)
            ON CONFLICT (session_id, label_name)
            DO UPDATE SET statements = EXCLUDED.statements
            """,
            (session_id, label_name, json.dumps(statements)),
        )


def load_script(session_id: str) -> dict:
    with db() as conn:
        rows = conn.execute(
            "SELECT label_name, statements FROM script_labels WHERE session_id = ? ORDER BY sort_order",
            (session_id,),
        ).fetchall()
    return {row["label_name"]: json.loads(row["statements"]) for row in rows}
