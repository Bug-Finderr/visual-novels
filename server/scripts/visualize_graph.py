"""Visualize the story-generation StateGraph.

Usage (from server/):
    python scripts/visualize_graph.py            # print Mermaid + ASCII
    python scripts/visualize_graph.py --png      # also render a PNG

Outputs:
    docs/diagrams/v2/storygraph.mmd   (Mermaid source — paste into mermaid.live)
    docs/diagrams/v2/png/storygraph-langgraph.png   (with --png)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "unused")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai.storygraph import build_graph  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MMD = REPO / "docs/diagrams/v2/storygraph.mmd"
PNG = REPO / "docs/diagrams/v2/png/storygraph-langgraph.png"


def main():
    graph = build_graph(None).get_graph()

    mermaid = graph.draw_mermaid()
    MMD.parent.mkdir(parents=True, exist_ok=True)
    MMD.write_text(mermaid)
    print("=" * 70)
    print("MERMAID  (saved to", MMD.relative_to(REPO), "— paste into https://mermaid.live)")
    print("=" * 70)
    print(mermaid)

    print("=" * 70)
    print("ASCII")
    print("=" * 70)
    try:
        print(graph.draw_ascii())
    except Exception as exc:  # needs `grandalf`
        print(f"(ASCII unavailable: {exc} — pip install grandalf)")

    if "--png" in sys.argv:
        try:
            PNG.parent.mkdir(parents=True, exist_ok=True)
            PNG.write_bytes(graph.draw_mermaid_png())  # uses mermaid.ink (network)
            print(f"\nPNG written to {PNG.relative_to(REPO)}")
        except Exception as exc:
            print(f"\n(PNG render failed: {exc})")


if __name__ == "__main__":
    main()
