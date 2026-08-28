"""Architecture and pipeline diagrams for the capstone deck."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent / "charts"
OUT.mkdir(exist_ok=True)

INK, MUTED, LINE = "#1a1a2e", "#5c5c72", "#c9ccd6"
BLUE, PINK, GREEN, AMBER, GREY = "#5b5bd6", "#e0457b", "#0e9f6e", "#c98a00", "#eef0f6"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK})


def box(ax, x, y, w, h, title, sub=None, fc="white", ec=LINE, tc=INK, lw=1.6, fs=11):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(x + w/2, y + h/2 + (0.10 if sub else 0), title, ha="center", va="center",
            fontsize=fs, fontweight="bold", color=tc, zorder=3)
    if sub:
        ax.text(x + w/2, y + h/2 - 0.16, sub, ha="center", va="center",
                fontsize=fs - 2.4, color=MUTED, zorder=3)


def arrow(ax, p1, p2, color=MUTED, style="-|>", ls="-", lw=1.5, rad=0.0, label=None, lo=(0, 0)):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=13, color=color,
                                 lw=lw, ls=ls, zorder=1,
                                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((p1[0]+p2[0])/2 + lo[0], (p1[1]+p2[1])/2 + lo[1], label, ha="center",
                va="center", fontsize=8.6, color=MUTED, zorder=3,
                bbox=dict(fc="white", ec="none", pad=1.4))


def architecture():
    fig, ax = plt.subplots(figsize=(12.6, 6.4))
    ax.set_xlim(0, 12.6); ax.set_ylim(0, 6.4); ax.axis("off")

    ax.text(0.15, 6.15, "System Architecture", fontsize=15, fontweight="bold")

    box(ax, 0.2, 4.5, 2.3, 1.0, "Browser", "React 18 + Vite", fc="#f5f6fb")
    box(ax, 0.2, 2.9, 2.3, 1.0, "Render Static Site", "SPA + CDN", fc="#f5f6fb")

    # Drawn by hand rather than via box(): the title must sit at the top of the
    # panel, above its own bullet list, not centred through it.
    ax.add_patch(FancyBboxPatch((3.5, 3.4), 3.0, 2.1,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc="white", ec=BLUE, lw=2.2, zorder=2))
    ax.text(5.0, 5.28, "FastAPI backend", ha="center", fontsize=11.5,
            fontweight="bold", color=INK, zorder=3)
    ax.text(5.0, 5.03, "Render · Docker · 2 GB", fontsize=8.4, color=MUTED,
            ha="center", zorder=3)
    for i, (t, c) in enumerate([("Auth · OAuth 2.0", MUTED), ("Billing · credits", PINK),
                                ("Generation · queue", GREEN), ("Gameplay · SSE/WS", MUTED)]):
        ax.text(3.70, 4.66 - i*0.33, "▸ " + t, fontsize=9.2, color=c,
                fontweight="bold", zorder=3)

    box(ax, 3.5, 1.5, 3.0, 1.2, "PostgreSQL", "22 tables · Alembic", fc="#f5f6fb")
    arrow(ax, (5.0, 3.4), (5.0, 2.7))

    box(ax, 7.6, 5.0, 2.6, 0.9, "Gemini 3.x", "story · dialogue · art", fc="white", ec=GREEN)
    box(ax, 7.6, 3.8, 2.6, 0.9, "Silk / Mulberry", "voice synthesis", fc="white", ec=GREEN)
    box(ax, 7.6, 2.6, 2.6, 0.9, "Cashfree", "payments · INR", fc="white", ec=PINK)
    box(ax, 7.6, 1.4, 2.6, 0.9, "Cloud Storage", "sprites · audio", fc="white", ec=AMBER)

    arrow(ax, (2.5, 5.0), (3.5, 4.8), label="HTTPS", lo=(0, .18))
    arrow(ax, (2.5, 3.4), (3.5, 3.9))
    arrow(ax, (6.5, 4.8), (7.6, 5.4))
    arrow(ax, (6.5, 4.4), (7.6, 4.25))
    arrow(ax, (6.5, 3.8), (7.6, 3.05), color=PINK, label="webhook", lo=(.1, -.22))
    arrow(ax, (6.5, 3.5), (7.6, 1.9), color=AMBER)
    arrow(ax, (7.6, 1.75), (2.5, 4.6), color=AMBER, ls="--", rad=-0.28)
    ax.text(0.25, 1.15, "assets served direct to browser", fontsize=8.8, color=AMBER,
            ha="left", fontweight="bold", zorder=3)

    ax.text(6.3, 0.55, "Generated assets bypass the backend entirely — served from the bucket to the browser",
            fontsize=9, color=MUTED, ha="center", style="italic")
    fig.tight_layout(); fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def pipeline():
    fig, ax = plt.subplots(figsize=(12.6, 6.6))
    ax.set_xlim(0, 12.6); ax.set_ylim(0, 6.6); ax.axis("off")
    ax.text(0.15, 6.35, "Generation Pipeline", fontsize=15, fontweight="bold")

    box(ax, 0.2, 5.15, 2.5, 0.85, "POST /generate", "player clicks Weave", fc="#f5f6fb")
    box(ax, 3.3, 5.15, 3.4, 0.85, "Claim slot + debit credit", "one transaction", fc="white", ec=PINK, tc=PINK)
    box(ax, 7.4, 5.15, 2.6, 0.85, "Admission control", "max 3 · else queue", fc="white", ec=GREEN, tc=GREEN)
    arrow(ax, (2.7, 5.57), (3.3, 5.57))
    arrow(ax, (6.7, 5.57), (7.4, 5.57))
    ax.text(5.0, 4.82, "conditional writes — a concurrent double-click loses the race",
            fontsize=8.4, color=PINK, ha="center", style="italic")

    phases = [
        ("A0", "Story bible", "plot · world · cast\n10 beats · 5 endings", GREY),
        ("A1", "Dialogue text", "30 beat variants\n5 ending epilogues", GREY),
        ("→",  "Usage scan", "what does the script\nactually reference?", "#fff4e0"),
        ("B",  "Sprites", "only expressions used\n18 not 40", GREY),
        ("C",  "Backgrounds", "only scenes visited\n7 not 12", GREY),
        ("E",  "Voices", "every cached line\npre-synthesised", GREY),
    ]
    # 6 phases + a terminal box share the row; compute width so nothing collides.
    n_boxes, gap, margin = len(phases) + 1, 0.22, 0.2
    w = (12.6 - 2*margin - gap*(n_boxes - 1)) / n_boxes
    x = margin
    for i, (tag, title, sub, fc) in enumerate(phases):
        ec = AMBER if fc != GREY else LINE
        ax.add_patch(FancyBboxPatch((x, 2.35), w, 1.55,
                                    boxstyle="round,pad=0.02,rounding_size=0.06",
                                    fc=fc, ec=ec, lw=2.0 if fc != GREY else 1.5, zorder=2))
        ax.text(x + w/2, 3.62, tag, ha="center", fontsize=9, fontweight="bold",
                color=AMBER if fc != GREY else MUTED)
        ax.text(x + w/2, 3.28, title, ha="center", fontsize=11, fontweight="bold")
        ax.text(x + w/2, 2.78, sub, ha="center", fontsize=8.6, color=MUTED, linespacing=1.5)
        if i:
            arrow(ax, (x - gap - 0.02, 3.12), (x - 0.02, 3.12))
        x += w + gap

    box(ax, x, 2.35, w, 1.55, "status", "ready · playable", fc="white", ec=GREEN, tc=GREEN)
    arrow(ax, (x - gap - 0.02, 3.12), (x - 0.02, 3.12))

    ax.add_patch(FancyBboxPatch((3.2, 1.30), 6.2, 0.62,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc="#fff4e0", ec=AMBER, lw=1.6, zorder=2))
    ax.text(6.3, 1.61, "Text is generated BEFORE images — that is what makes the scan possible",
            ha="center", fontsize=9.6, color="#8a5d00", fontweight="bold", zorder=3)
    arrow(ax, (4.55, 2.33), (5.4, 1.95), color=AMBER, rad=0.25)
    ax.text(6.3, 0.75, "Result: 26 images instead of 53 — 51% fewer, with nothing lost that a player sees",
            fontsize=10, color=INK, ha="center", fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "pipeline.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    architecture(); pipeline()
    for f in ("architecture.png", "pipeline.png"):
        print(f"  {f:20s} {(OUT/f).stat().st_size//1024} KB")
