"""Multi-agent (LangGraph) story generator.

Drop-in alternative to the monolithic `story_generator.generate_world` Pro
call: a team of specialized agents (plot → world → characters → chapter) gated
by a Memory Agent, producing the same story-contract dict so the rest of the
generation pipeline is unchanged. Enabled via STORYGEN_ENGINE=graph.
"""
from .graph import build_graph, run_story_graph

__all__ = ["build_graph", "run_story_graph"]
