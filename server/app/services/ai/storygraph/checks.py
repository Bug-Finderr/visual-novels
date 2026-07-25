"""Programmatic gate + repair for the story graph.

`validate()` is the cheap, deterministic core of the Memory Agent — it catches
the structural failures (missing refs, wrong counts, unreachable endings) that
matter most and names which node to re-run. `build_contract()` assembles the
final dict in the exact shape the existing pipeline (`save_story_data` /
`generate_world`) consumes, repairing any residue so a bounded number of
revisions still yields a runnable story.
"""
from __future__ import annotations

from typing import Any

# Stages, earliest first — the gate routes a rejection to the earliest
# offending stage so upstream fixes flow down.
_STAGE_ORDER = {"world": 0, "characters": 1, "chapter": 2}


def validate(state: dict) -> dict:
    """Return {ok, route, issues}. route is the earliest stage to re-run."""
    scenes = state.get("scenes") or []
    chars = state.get("characters") or []
    spine = state.get("storySpine") or []
    endings = state.get("chapter_endings") or []
    opening = state.get("openingScript") or []

    scene_ids = {s.get("id") for s in scenes if s.get("id")}
    char_ids = {c.get("id") for c in chars if c.get("id")}
    ending_tags = {e.get("alignmentTag") for e in endings if e.get("alignmentTag")}

    issues: list[tuple[str, str]] = []

    if len(scene_ids) < 6:
        issues.append(("world", f"only {len(scene_ids)} scenes; need 8-14"))
    for s in scenes:
        if s.get("id") and (not s.get("name") or not s.get("description")):
            issues.append(("world", f"scene {s.get('id')} missing name/description"))
    if len(char_ids) < 3:
        issues.append(("characters", f"only {len(char_ids)} characters; need 3-5"))

    if len(endings) != 5:
        issues.append(("chapter", f"{len(endings)} chapter endings; need exactly 5"))
    if len(ending_tags) < len([e for e in endings if e.get("alignmentTag")]) or "" in ending_tags:
        issues.append(("chapter", "chapter endings have duplicate or empty alignmentTags"))
    for e in endings:
        if e.get("finalSceneId") not in scene_ids:
            issues.append(("chapter", f"ending {e.get('id')} finalSceneId not in scenes"))

    if len(spine) != 10:
        issues.append(("chapter", f"{len(spine)} beats; need exactly 10"))

    covered: set[str] = set()
    for b in spine:
        if b.get("sceneId") not in scene_ids:
            issues.append(("chapter", f"beat {b.get('id')} sceneId invalid"))
        for cid in b.get("castIds") or []:
            if cid not in char_ids:
                issues.append(("chapter", f"beat {b.get('id')} castId {cid} invalid"))
        chs = b.get("choices") or []
        if len(chs) != 3:
            issues.append(("chapter", f"beat {b.get('id')} has {len(chs)} choices; need 3"))
        for ch in chs:
            tag = ch.get("alignmentTag")
            if tag not in ending_tags:
                issues.append(("chapter", f"beat {b.get('id')} choice tag '{tag}' is not an ending tag"))
            else:
                covered.add(tag)

    unreachable = {t for t in ending_tags if t} - covered
    if unreachable:
        issues.append(("chapter", f"endings unreachable by any choice: {sorted(unreachable)}"))

    if len(opening) < 4:
        issues.append(("chapter", "openingScript too short (need >= 4 statements)"))

    route = None
    if issues:
        route = min((stage for stage, _ in issues), key=lambda s: _STAGE_ORDER.get(s, 9))

    return {
        "ok": not issues,
        "route": route,
        "issues": [f"[{stage}] {msg}" for stage, msg in issues],
    }


def build_contract(state: dict) -> dict:
    """Assemble + repair into the dict shape generate_world() returns."""
    world = dict(state.get("worldLore") or {})
    world.setdefault("name", "Untitled World")
    world.setdefault("description", "")
    world.setdefault("rules", [])
    world.setdefault("history", "")

    plot = dict(state.get("plotArc") or {})
    plot.setdefault("premise", world.get("description", "")[:160] or "An untold story.")
    plot.setdefault("themes", [])
    # Stash the story-level endings on plotArc so they persist (plotArc is
    # saved to the DB) without touching the schema.
    plot["plotEndings"] = state.get("plot_endings") or plot.get("plotEndings") or []

    # ---- characters: must have id + name ----
    chars = [dict(c) for c in (state.get("characters") or []) if c.get("id") and c.get("name")]
    char_ids = {c["id"] for c in chars}

    # ---- scenes: guarantee at least one + the NOT NULL fields the DB needs ----
    scenes = [dict(s) for s in (state.get("scenes") or []) if s.get("id")]
    if not scenes:
        scenes = [{"id": "scene_default", "name": "Unknown Place",
                   "description": "A nondescript location.", "narrativeContext": ""}]
    for s in scenes:
        # save_story_data subscripts scene["name"]/["description"] and the DB
        # columns are NOT NULL — a Flash response that omits either would crash
        # the pipeline, so backfill here (the monolith relied on prompt rules).
        s.setdefault("name", str(s.get("id")).replace("_", " ").title())
        if not s.get("name"):
            s["name"] = str(s.get("id")).replace("_", " ").title()
        s.setdefault("description", "")
        if s.get("description") is None:
            s["description"] = ""
        s.setdefault("narrativeContext", "")
    scene_id_set = {s["id"] for s in scenes}
    default_scene = scenes[0]["id"]

    # ---- endings: valid tags + finalSceneId ----
    endings = [dict(e) for e in (state.get("chapter_endings") or [])]
    seen_tags: set[str] = set()
    for i, e in enumerate(endings):
        tag = (e.get("alignmentTag") or "").strip()
        if not tag or tag in seen_tags:
            tag = f"path_{i}"
        seen_tags.add(tag)
        e["alignmentTag"] = tag
        if e.get("finalSceneId") not in scene_id_set:
            e["finalSceneId"] = default_scene
        e.setdefault("id", f"ending_{i}")
        e.setdefault("name", tag.replace("_", " ").title())
        e.setdefault("summary", "")
        e.setdefault("tone", "bittersweet")
        e.setdefault("epilogueOutline", e.get("summary", ""))
    ending_tags = [e["alignmentTag"] for e in endings] or ["path_0"]

    # ---- spine: index, valid refs, exactly 3 valid choices ----
    fixed_spine: list[dict] = []
    for i, b in enumerate(state.get("storySpine") or []):
        b = dict(b)
        b["index"] = i
        if b.get("sceneId") not in scene_id_set:
            b["sceneId"] = default_scene
        b["castIds"] = [c for c in (b.get("castIds") or []) if c in char_ids]
        chs = [dict(c) for c in (b.get("choices") or [])]
        for c in chs:
            if c.get("alignmentTag") not in ending_tags:
                c["alignmentTag"] = ending_tags[i % len(ending_tags)]
            c.setdefault("consequence", "")
            try:
                c["magnitude"] = max(1, min(3, int(c.get("magnitude", 1))))
            except (TypeError, ValueError):
                c["magnitude"] = 1
        while len(chs) < 3:
            tag = ending_tags[len(chs) % len(ending_tags)]
            chs.append({"text": "Continue.", "consequence": "",
                        "alignmentTag": tag, "magnitude": 1})
        b["choices"] = chs[:3]
        b.setdefault("id", f"beat_{i}")
        b.setdefault("title", f"Beat {i + 1}")
        b.setdefault("outline", "")
        b.setdefault("narrativeGoal", "")
        fixed_spine.append(b)

    # ---- opening: never empty ----
    opening = list(state.get("openingScript") or [])
    if not opening:
        opening = [{"type": "narration", "text": plot.get("premise", "The story begins.")}]

    return {
        "worldLore": world,
        "plotArc": plot,
        "characters": chars,
        "scenes": scenes,
        "storySpine": fixed_spine,
        "endings": endings,
        "openingScript": opening,
    }
