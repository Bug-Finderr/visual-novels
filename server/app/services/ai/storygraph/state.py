"""Shared graph state for the multi-agent story generator.

One typed object flows through the whole graph. Nodes return *partial* dicts
of only the channels they touched; LangGraph merges them via each channel's
reducer. Most channels use the default overwrite reducer (a single node owns
the channel and emits the full value). `memory_log` is append-only so the
audit trail accumulates across the Memory-gate revision loop.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class StoryState(TypedDict, total=False):
    # ---- inputs ----
    setup: dict
    continuation: dict | None

    # ---- Overall Plot Agent ----
    worldLore: dict
    plotArc: dict
    plot_endings: list[dict]          # 5-6 story-level endings
    character_briefs: list[dict]      # roster (id, name, role, one-liner)

    # ---- World-building Agent ----
    scenes: list[dict]

    # ---- Character Agent (fans out internally, owns the whole list) ----
    characters: list[dict]

    # ---- Chapter Generator Agent ----
    storySpine: list[dict]            # 10 beats with choices
    chapter_endings: list[dict]       # 5 chapter endings (-> a plot ending)
    openingScript: list[dict]

    # ---- Memory Agent (gate) + control ----
    critique: dict | None
    route: str | None                 # next hop chosen by the gate
    revision_count: int
    memory_log: Annotated[list[dict], operator.add]

    # ---- terminal artifact (assemble node) ----
    final: dict
