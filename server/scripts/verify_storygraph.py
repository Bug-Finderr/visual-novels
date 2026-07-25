"""End-to-end verification of the multi-agent story graph with a MOCKED LLM.

Runs the real LangGraph wiring (plot → world → characters → chapter → memory
→ assemble) but swaps `llm.gen_json` for canned responses, so no Gemini quota
is spent. Exercises:
  1. happy-path assembly → valid story contract
  2. the Memory-gate revision loop (first chapter output is broken)
  3. build_contract repair on deliberately broken state
  4. generate_world dispatch when STORYGEN_ENGINE=graph

Run:  cd server && python scripts/verify_storygraph.py
"""
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("STORYGEN_ENGINE", "graph")
os.environ.setdefault("GEMINI_API_KEY", "unused-mock-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai.storygraph import llm  # noqa: E402
from app.services.ai.storygraph import checks, graph as sg_graph  # noqa: E402

# --------------------------------------------------------------------------
# canned model output
# --------------------------------------------------------------------------
SCENES = [
    {"id": f"scene_{i}", "name": f"Scene {i}",
     "description": "x" * 50, "narrativeContext": "ctx"}
    for i in range(8)
]
ENDING_TAGS = [f"et{i}" for i in range(5)]
CHAR_IDS = ["char_a", "char_b", "char_c"]

PLOT = {
    "worldLore": {"name": "Aetheria", "description": "A floating world.",
                  "rules": ["gravity is optional"], "history": "long ago..."},
    "plotArc": {"premise": "Find the anchor.", "dramaticQuestion": "Will it hold?",
                "themes": ["belonging"], "arcSummary": "rise, fall, choose."},
    "plotEndings": [
        {"id": f"plot_{i}", "name": f"Plot {i}", "alignmentTag": f"pe{i}",
         "summary": "s", "tone": "bittersweet"} for i in range(5)
    ],
    "characterBriefs": [
        {"id": cid, "name": cid.title(), "gender": "female",
         "role": "ally", "oneLine": "a hook"} for cid in CHAR_IDS
    ],
}

WORLD = {"scenes": SCENES}


def make_char(brief: dict) -> dict:
    return {
        "id": brief.get("id"), "name": brief.get("name"), "age": "20",
        "gender": brief.get("gender"), "role": brief.get("role"),
        "personality": "kind", "appearance": "detailed " * 10,
        "backstory": "born", "relationshipToProtagonist": "friend",
        "speechStyle": "casual", "quirks": ["hums"], "color": "#AABBCC",
        "voiceCaption": "A warm young woman with a clear voice.",
    }


def _good_beats():
    beats = []
    for i in range(10):
        tags = [ENDING_TAGS[i % 5], ENDING_TAGS[(i + 1) % 5], ENDING_TAGS[(i + 2) % 5]]
        beats.append({
            "id": f"beat_{i}", "index": i, "title": f"Beat {i}",
            "outline": "stuff happens", "sceneId": f"scene_{i % 8}",
            "castIds": ["char_a", "char_b"], "narrativeGoal": "advance",
            "choices": [
                {"text": f"choice {j}", "consequence": "hint",
                 "alignmentTag": tags[j], "magnitude": j + 1}
                for j in range(3)
            ],
        })
    return beats


CHAPTER_GOOD = {
    "storySpine": _good_beats(),
    "endings": [
        {"id": f"ending_{i}", "name": f"End {i}", "alignmentTag": ENDING_TAGS[i],
         "summary": "s", "tone": "tragic", "finalSceneId": "scene_0",
         "epilogueOutline": "fin", "plotEndingId": f"plot_{i}"}
        for i in range(5)
    ],
    "openingScript": [{"type": "narration", "text": f"line {i}"} for i in range(12)],
}

# First chapter attempt is broken: 8 beats, bogus choice tags -> gate rejects.
CHAPTER_BROKEN = {
    "storySpine": [
        {"id": f"beat_{i}", "index": i, "title": "t", "outline": "o",
         "sceneId": "scene_0", "castIds": ["char_a"], "narrativeGoal": "g",
         "choices": [{"text": "c", "consequence": "h",
                      "alignmentTag": "WRONG", "magnitude": 1}]}
        for i in range(8)
    ],
    "endings": CHAPTER_GOOD["endings"],
    "openingScript": [{"type": "narration", "text": "x"}],
}

_chapter_calls = {"n": 0}


def fake_gen_json(prompt, *, model, **kw):
    if "OVERALL PLOT AGENT" in prompt:
        return PLOT
    if "WORLD-BUILDING AGENT" in prompt:
        return WORLD
    if "CHARACTER AGENT" in prompt:
        m = re.search(r"BRIEF: (\{.*\})", prompt)
        return make_char(json.loads(m.group(1)) if m else {})
    if "CHAPTER GENERATOR AGENT" in prompt:
        _chapter_calls["n"] += 1
        return CHAPTER_BROKEN if _chapter_calls["n"] == 1 else CHAPTER_GOOD
    if "MEMORY AGENT" in prompt:
        return {"revise": False, "route": "chapter", "concerns": []}
    raise AssertionError(f"unexpected prompt banner: {prompt[:60]!r}")


llm.gen_json = fake_gen_json


# --------------------------------------------------------------------------
# assertions
# --------------------------------------------------------------------------
def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def assert_valid_contract(story: dict):
    scene_ids = {s["id"] for s in story["scenes"]}
    char_ids = {c["id"] for c in story["characters"]}
    ending_tags = {e["alignmentTag"] for e in story["endings"]}
    _assert(len(story["storySpine"]) == 10, "spine has exactly 10 beats")
    _assert(len(story["endings"]) == 5, "exactly 5 chapter endings")
    _assert(len(ending_tags) == 5, "5 distinct ending tags")
    covered = set()
    for b in story["storySpine"]:
        _assert(b["sceneId"] in scene_ids, f"beat {b['id']} sceneId resolves")
        _assert(len(b["choices"]) == 3, f"beat {b['id']} has 3 choices")
        for c in b["choices"]:
            _assert(c["alignmentTag"] in ending_tags, "choice tag is a real ending tag")
            covered.add(c["alignmentTag"])
            _assert(set(b["castIds"]) <= char_ids, "castIds resolve")
    _assert(covered == ending_tags, "every ending reachable by some choice")
    for e in story["endings"]:
        _assert(e["finalSceneId"] in scene_ids, f"ending {e['id']} finalSceneId resolves")
    _assert(len(story["openingScript"]) >= 4, "openingScript present")
    _assert(story["worldLore"].get("name"), "worldLore has a name")
    _assert("plotEndings" in story["plotArc"], "plot endings stashed on plotArc")


def main():
    print("\n[1] full graph run (with a forced revision loop)")
    g = sg_graph.build_graph(None)
    final_state = g.invoke(
        {"setup": {"genre": "fantasy", "artStyle": "anime", "setting": "sky",
                   "protagonistName": "Rin", "protagonistPersonality": "brave",
                   "tone": "hopeful"},
         "continuation": None, "characters": [], "revision_count": 0,
         "memory_log": [], "critique": None},
        config={"recursion_limit": 60},
    )
    story = final_state["final"]
    _assert(_chapter_calls["n"] == 2, "chapter agent ran twice (gate forced a revision)")
    _assert(len(final_state["memory_log"]) == 2, "memory_log recorded both gate passes")
    _assert(final_state["memory_log"][0]["ok"] is False, "first gate pass rejected")
    _assert(final_state["memory_log"][1]["ok"] is True, "second gate pass approved")
    assert_valid_contract(story)

    print("\n[2] build_contract repair on broken state")
    broken = {
        "worldLore": {}, "plotArc": {}, "plot_endings": [],
        # s2 has NO name/description — the blocker that crashed save_story_data.
        "scenes": [{"id": "s1", "name": "S1", "description": "d"}, {"id": "s2"}],
        "characters": [{"id": "c1", "name": "C1"}],
        "chapter_endings": [{"id": "e1", "alignmentTag": "", "finalSceneId": "ghost"}],
        "storySpine": [{"id": "b", "sceneId": "ghost", "castIds": ["nobody"], "choices": []}],
        "openingScript": [],
    }
    repaired = checks.build_contract(broken)
    s2 = next(s for s in repaired["scenes"] if s["id"] == "s2")
    _assert(s2.get("name"), "nameless scene backfilled name (NOT NULL invariant)")
    _assert("description" in s2 and s2["description"] is not None, "scene description backfilled")
    _assert(repaired["endings"][0]["finalSceneId"] == "s1", "bad finalSceneId repaired to a real scene")
    _assert(repaired["endings"][0]["alignmentTag"], "empty ending tag repaired")
    _assert(len(repaired["storySpine"][0]["choices"]) == 3, "missing choices padded to 3")
    _assert(repaired["storySpine"][0]["sceneId"] == "s1", "ghost sceneId repaired")
    _assert(repaired["storySpine"][0]["castIds"] == [], "unknown castId dropped")
    _assert(repaired["openingScript"], "empty opening backfilled")

    print("\n[2b] gate routing to 'characters' must not KeyError (blocker #2/#3)")
    def fake_low_chars(prompt, *, model, **kw):
        if "OVERALL PLOT AGENT" in prompt:
            return PLOT
        if "WORLD-BUILDING AGENT" in prompt:
            return WORLD
        if "CHARACTER AGENT" in prompt:
            m = re.search(r"BRIEF: (\{.*\})", prompt)
            brief = json.loads(m.group(1)) if m else {}
            # Only char_a yields a valid dict; the others return garbage so the
            # node drops them -> <3 characters -> gate routes to 'characters'.
            return make_char(brief) if brief.get("id") == "char_a" else []
        if "CHAPTER GENERATOR AGENT" in prompt:
            return CHAPTER_GOOD
        if "MEMORY AGENT" in prompt:
            return {"revise": False, "route": "chapter", "concerns": []}
        raise AssertionError("bad banner")

    llm.gen_json = fake_low_chars
    try:
        g2 = sg_graph.build_graph(None)
        st = g2.invoke(
            {"setup": {"genre": "x", "artStyle": "x", "setting": "x",
                       "protagonistName": "P", "protagonistPersonality": "p", "tone": "t"},
             "continuation": None, "characters": [], "revision_count": 0,
             "memory_log": [], "critique": None},
            config={"recursion_limit": 60},
        )
        routes = [e["route"] for e in st["memory_log"]]
        _assert("characters" in routes, "gate emitted route='characters' (the crash trigger)")
        _assert(st.get("final"), "graph completed via the 'characters' edge without KeyError")
    finally:
        llm.gen_json = fake_gen_json  # restore for later sections

    print("\n[3] generate_world dispatch routes to the graph engine")
    from app.config import config
    _assert(config.STORYGEN_ENGINE == "graph", "STORYGEN_ENGINE=graph picked up")
    _chapter_calls["n"] = 0  # reset; graph will run again via dispatch
    from app.services.ai import story_generator
    story2 = story_generator.generate_world(
        {"genre": "fantasy", "artStyle": "anime", "setting": "sky",
         "protagonistName": "Rin", "protagonistPersonality": "brave", "tone": "hopeful"},
        session_id="verify-session",
    )
    _assert(story2.get("__engine__") == "graph", "engine marker tags the graph path (for per-session persistence)")
    assert_valid_contract(story2)

    print("\nALL CHECKS PASSED ✅")


if __name__ == "__main__":
    main()
