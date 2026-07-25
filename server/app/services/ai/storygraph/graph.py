"""Graph wiring + public entrypoint.

    START → plot → world → characters → chapter → memory ─┬─ approved → assemble → END
                              ▲           ▲                │
                  world/characters ◄──────┴── chapter ◄────┘  (Memory-gate revision loop)

State is checkpointed to SQLite (thread_id = session_id) so every super-step is
snapshotted — useful as an audit/debug trail and the substrate for resume.
(The current entrypoint runs the graph to completion in one invoke; a crash
mid-run is retried by the pipeline, not yet auto-resumed from the checkpoint.)
Falls back to no checkpointer if the sqlite saver is unavailable.
"""
from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, START, StateGraph

from app.config import config
from app.logger import logger

from . import nodes
from .state import StoryState

_RECURSION_LIMIT = 60


def build_graph(checkpointer=None):
    g = StateGraph(StoryState)
    g.add_node("plot", nodes.plot_node)
    g.add_node("world", nodes.world_node)
    g.add_node("characters", nodes.characters_node)
    g.add_node("chapter", nodes.chapter_node)
    g.add_node("memory", nodes.memory_node)
    g.add_node("assemble", nodes.assemble_node)

    g.add_edge(START, "plot")
    g.add_edge("plot", "world")
    g.add_edge("world", "characters")
    g.add_edge("characters", "chapter")
    g.add_edge("chapter", "memory")
    # Every value route_after_memory can return MUST be a key here, or LangGraph
    # raises KeyError mid-run. The gate routes to the earliest offending stage:
    # world, characters, or chapter (see checks._STAGE_ORDER). "plot" is never
    # emitted, so it is intentionally absent.
    g.add_conditional_edges(
        "memory",
        nodes.route_after_memory,
        {
            "approved": "assemble",
            "world": "world",
            "characters": "characters",
            "chapter": "chapter",
        },
    )
    g.add_edge("assemble", END)
    return g.compile(checkpointer=checkpointer)


def _checkpointer_cm():
    """Context manager yielding a checkpointer (SQLite if possible, else None).

    Uses an explicit connection with a 30s busy_timeout so concurrent sessions
    sharing one checkpoints.db wait out WAL lock contention instead of erroring
    with 'database is locked' (the sqlite default wait is only ~5s).
    """
    try:
        import sqlite3
        from contextlib import contextmanager

        from langgraph.checkpoint.sqlite import SqliteSaver

        Path(config.DATA_DIR).mkdir(parents=True, exist_ok=True)
        db_path = str(Path(config.DATA_DIR) / "storygraph_checkpoints.db")

        @contextmanager
        def _cm():
            conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA busy_timeout=30000")
            try:
                yield SqliteSaver(conn)
            finally:
                conn.close()

        return _cm()
    except Exception as exc:  # missing extra, locked db, etc.
        logger.warning("storygraph: SQLite checkpointer unavailable (%s)", exc)
        from contextlib import nullcontext

        return nullcontext(None)


def run_story_graph(setup: dict, *, continuation: dict | None = None,
                    session_id: str | None = None) -> dict:
    """Run the multi-agent graph and return the legacy story contract dict."""
    init: StoryState = {
        "setup": setup,
        "continuation": continuation,
        "characters": [],
        "revision_count": 0,
        "memory_log": [],
        "critique": None,
    }
    run_cfg = {
        "configurable": {"thread_id": session_id or "adhoc"},
        "recursion_limit": _RECURSION_LIMIT,
    }
    logger.info("storygraph: starting run (session=%s, continuation=%s)",
                session_id, bool(continuation))
    with _checkpointer_cm() as checkpointer:
        graph = build_graph(checkpointer)
        final_state = graph.invoke(init, config=run_cfg)

    story = final_state.get("final")
    if not story:
        raise ValueError("storygraph produced no final story")
    return story
