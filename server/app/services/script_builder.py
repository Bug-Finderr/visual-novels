import json
import time
from typing import Any

from app.db.database import db


def _convert_single(stmt: dict) -> Any:
    t = stmt.get("type")
    if t == "narration":
        return stmt.get("text", "")
    if t == "dialogue":
        expr = stmt.get("expression") or "neutral"
        return f"{stmt['speaker']}:{expr} {stmt.get('text', '')}"
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
        }
        choice_labels[label_name] = ["Waiting for AI to continue the story..."]
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
    script: dict = {}
    start_statements, extra_labels = _convert_statement_array(
        story_data["openingScript"], "Start"
    )
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
            INSERT OR REPLACE INTO script_labels (session_id, label_name, statements)
            VALUES (?, ?, ?)
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
