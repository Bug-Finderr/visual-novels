"""Graph nodes — one function per agent.

Each node reads the shared StoryState and returns a partial update. LLM calls
go through `llm.gen_json` (module-qualified for test patching). The Character
Agent fans out internally with a thread pool (matching the codebase's
concurrency style) and owns the whole `characters` channel.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import config
from app.logger import logger

from . import checks, llm, prompts

_models = config.models


# ---------------------------------------------------------------------------
# 1. Overall Plot Agent (Flash)
# ---------------------------------------------------------------------------

def plot_node(state: dict) -> dict:
    # Flash (thinking on) — every node runs on Flash for cost/latency.
    data = llm.gen_json(
        prompts.plot_prompt(state["setup"], state.get("continuation")),
        model=_models.dialogue_flash, temperature=0.95, max_output_tokens=16384,
    )
    briefs = data.get("characterBriefs") or []
    plot_endings = data.get("plotEndings") or []
    logger.info("PLOT agent: %d endings, %d character briefs",
                len(plot_endings), len(briefs))
    return {
        "worldLore": data.get("worldLore") or {},
        "plotArc": data.get("plotArc") or {},
        "plot_endings": plot_endings,
        "character_briefs": briefs,
    }


# ---------------------------------------------------------------------------
# 2. World-building Agent (Flash)
# ---------------------------------------------------------------------------

def world_node(state: dict) -> dict:
    data = llm.gen_json(
        prompts.world_prompt(state),
        model=_models.dialogue_flash, temperature=0.9, max_output_tokens=8192,
    )
    scenes = data.get("scenes") or []
    logger.info("WORLD agent: %d scenes", len(scenes))
    return {"scenes": scenes}


# ---------------------------------------------------------------------------
# 3. Character Agent (Flash, fan-out ×N)
# ---------------------------------------------------------------------------

def _one_character(brief: dict, world: dict, plot: dict, setup: dict) -> dict | None:
    char = llm.gen_json(
        prompts.character_prompt(brief, world, plot, setup),
        model=_models.dialogue_flash, temperature=0.9, max_output_tokens=2048, fast=True,
    )
    if not isinstance(char, dict):
        return None
    # Keep id/gender locked to the brief so downstream refs stay valid.
    char["id"] = brief.get("id") or char.get("id")
    char.setdefault("name", brief.get("name"))
    if brief.get("gender"):
        char["gender"] = brief["gender"]
    char.setdefault("role", brief.get("role"))
    return char if char.get("id") else None


def characters_node(state: dict) -> dict:
    briefs = state.get("character_briefs") or []
    world = state.get("worldLore") or {}
    plot = state.get("plotArc") or {}
    setup = state["setup"]
    out: list[dict] = []
    if briefs:
        with ThreadPoolExecutor(max_workers=min(5, len(briefs))) as pool:
            futures = {
                pool.submit(_one_character, b, world, plot, setup): b for b in briefs
            }
            for fut in as_completed(futures):
                brief = futures[fut]
                try:
                    char = fut.result()
                    if char:
                        out.append(char)
                except Exception as exc:
                    logger.warning("CHARACTER agent failed for %s: %s",
                                   brief.get("id"), exc)
    logger.info("CHARACTER agent: %d/%d characters built", len(out), len(briefs))
    return {"characters": out}


# ---------------------------------------------------------------------------
# 4. Chapter Generator Agent (Flash)
# ---------------------------------------------------------------------------

def chapter_node(state: dict) -> dict:
    # Generous budget: a 10-beat spine + 5 endings + opening is large, and
    # Flash's thinking tokens count against this cap, so leave headroom to
    # avoid MAX_TOKENS truncation of the JSON.
    data = llm.gen_json(
        prompts.chapter_prompt(state, feedback=state.get("critique")),
        model=_models.dialogue_flash, temperature=0.9, max_output_tokens=49152,
    )
    spine = data.get("storySpine") or []
    endings = data.get("endings") or []
    logger.info("CHAPTER agent: %d beats, %d endings", len(spine), len(endings))
    return {
        "storySpine": spine,
        "chapter_endings": endings,
        "openingScript": data.get("openingScript") or [],
    }


# ---------------------------------------------------------------------------
# 5. Memory Agent (gate)
# ---------------------------------------------------------------------------

def memory_node(state: dict) -> dict:
    report = checks.validate(state)
    rev = int(state.get("revision_count", 0))
    issues = list(report["issues"])
    route = "approved"

    if not report["ok"] and rev < config.STORYGRAPH_MAX_REVISIONS:
        route = report["route"] or "chapter"
    elif report["ok"] and config.STORYGRAPH_LLM_CRITIC and rev < config.STORYGRAPH_MAX_REVISIONS:
        # Structure is sound — optional semantic pass. Advisory only and bounded
        # by STORYGRAPH_MAX_REVISIONS, so it can request at most that many
        # regenerations (routed to world/characters/chapter), never an infinite loop.
        try:
            note = llm.gen_json(
                prompts.memory_prompt(state),
                model=_models.dialogue_flash, temperature=0.4,
                max_output_tokens=800, fast=True,
            )
            concerns = note.get("concerns") or []
            if note.get("revise") and note.get("route") in {"world", "characters", "chapter"}:
                route = note["route"]
                issues += [f"[semantic] {c}" for c in concerns]
        except Exception as exc:
            logger.warning("MEMORY semantic critic failed: %s", exc)

    entry = {"revision": rev, "ok": report["ok"], "route": route, "issues": issues}
    logger.info("MEMORY gate rev=%d ok=%s route=%s issues=%d",
                rev, report["ok"], route, len(issues))
    return {
        "route": route,
        "critique": {"issues": issues, "route": route},
        "revision_count": rev + 1,
        "memory_log": [entry],
    }


def route_after_memory(state: dict) -> str:
    return state.get("route") or "approved"


# ---------------------------------------------------------------------------
# 6. Assemble (pure)
# ---------------------------------------------------------------------------

def assemble_node(state: dict) -> dict:
    story = checks.build_contract(state)
    logger.info(
        "ASSEMBLE: world=%s, %d chars, %d scenes, %d beats, %d endings",
        (story["worldLore"].get("name")), len(story["characters"]),
        len(story["scenes"]), len(story["storySpine"]), len(story["endings"]),
    )
    return {"final": story}
