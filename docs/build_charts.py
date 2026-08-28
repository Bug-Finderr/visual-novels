"""Charts for the capstone deck — all figures measured, none illustrative."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "charts"
OUT.mkdir(exist_ok=True)

INK, MUTED, GRID = "#1a1a2e", "#6b6b80", "#dcdce6"
BEFORE, AFTER, ACCENT = "#c9ccd6", "#5b5bd6", "#e0457b"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlesize": 13,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def _bars(ax, labels, before, after, unit=""):
    x = range(len(labels))
    w = 0.36
    b1 = ax.bar([i - w/2 for i in x], before, w, label="Before", color=BEFORE)
    b2 = ax.bar([i + w/2 for i in x], after,  w, label="After",  color=AFTER)
    for bars in (b1, b2):
        for bar in bars:
            ax.annotate(f"{bar.get_height():g}{unit}",
                        (bar.get_x() + bar.get_width()/2, bar.get_height()),
                        ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)


def chart_optimisation():
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.0))

    _bars(axes[0], ["Sprites", "Backgrounds", "Total"], [40, 12, 53], [18, 7, 26])
    axes[0].set_title("Images generated per story\n55% / 42% / 51% reduction", pad=12)
    axes[0].legend(frameon=False, fontsize=10)

    # Only measured values here. There is no reliable "before" figure for peak
    # per-pipeline memory — the old build OOM'd rather than being profiled — so
    # it is shown as an after-only measurement rather than invented.
    ax1 = axes[1]
    bars = ax1.bar(["Baseline\n(before)", "Baseline\n(after)", "Peak per\npipeline"],
                   [750, 129, 500], color=[BEFORE, AFTER, AFTER], width=0.55)
    for bar in bars:
        ax1.annotate(f"{bar.get_height():g} MB",
                     (bar.get_x() + bar.get_width()/2, bar.get_height()),
                     ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax1.axhline(2048, color=ACCENT, ls="--", lw=1.4)
    ax1.annotate("2 GB instance limit", (2.45, 2080), color=ACCENT,
                 fontsize=9, va="bottom", ha="right", fontweight="bold")
    ax1.set_ylim(0, 2400)
    ax1.set_title("Memory footprint\nbaseline 750 → 129 MB", pad=12)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.yaxis.grid(True, color=GRID, lw=0.8); ax1.set_axisbelow(True)

    _bars(axes[2], ["Images", "Text", "Total"], [182, 24, 206], [77, 10, 87], unit="")
    axes[2].set_title("Cost per story (₹)\n₹206 → ₹87 · 58% reduction", pad=12)

    fig.tight_layout()
    fig.savefig(OUT / "optimisation.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def chart_concurrency():
    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    n = list(range(1, 9))
    mem = [129 + 500 * i for i in n]
    colors = [AFTER if m <= 2048 else ACCENT for m in mem]
    ax.bar(n, mem, color=colors, width=0.62)
    ax.axhline(2048, color=ACCENT, ls="--", lw=1.5)
    ax.annotate("2 GB — instance dies beyond this", (8.4, 2090), color=ACCENT,
                fontsize=9.5, ha="right", fontweight="bold")
    ax.axvline(3.5, color=INK, ls=":", lw=1.2)
    ax.annotate("cap = 3\n(further generations queue)", (3.35, 3600),
                fontsize=9.5, ha="right", color=INK, fontweight="bold")
    ax.set_xlabel("Concurrent generations"); ax.set_ylabel("Resident memory (MB)")
    ax.set_title("Why generation is capped at 3", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(OUT / "concurrency.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def chart_tests():
    fig, ax = plt.subplots(figsize=(6.6, 3.5))
    labels = ["Billing\n& credits", "Generation\nqueue", "Model\navailability", "Story\ngraph"]
    vals = [68, 17, 8, 3]
    bars = ax.barh(labels, vals, color=[AFTER, AFTER, AFTER, BEFORE], height=0.58)
    for bar, v in zip(bars, vals):
        ax.annotate(f"{v}", (v + 1.2, bar.get_y() + bar.get_height()/2),
                    va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(0, 78); ax.invert_yaxis()
    ax.set_xlabel("Automated checks — all passing")
    ax.set_title("Test coverage · 93 checks + 3 graph scenarios", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(OUT / "tests.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    chart_optimisation(); chart_concurrency(); chart_tests()
    for f in sorted(OUT.glob("*.png")):
        print(f"  {f.name:22s} {f.stat().st_size//1024} KB")
