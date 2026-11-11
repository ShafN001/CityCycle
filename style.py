"""Shared figure style: soft canvas, white cards, one blue/orange pair, direct labels."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

CANVAS, CARD, EDGE = "#f1f1ee", "#ffffff", "#e2e1dc"
BLUE, ORANGE, NAVY, GREY = "#2a78d6", "#eb6834", "#16324f", "#c4c3bd"
INK, INK2, GRID = "#111111", "#55544f", "#ebeae6"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID})


def canvas(w, h):
    """Figure in inches with a full-bleed drawing layer (coordinates = inches)."""
    fig = plt.figure(figsize=(w, h), dpi=200, facecolor=CANVAS)
    bg = fig.add_axes([0, 0, 1, 1]); bg.set_xlim(0, w); bg.set_ylim(0, h); bg.axis("off")
    return fig, bg


def card(bg, x, y, w, h, r=0.09):
    bg.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=CARD, ec=EDGE, lw=0.8))


def axes_at(fig, W, H, x, y, w, h):
    return fig.add_axes([x / W, y / H, w / W, h / H], facecolor=CARD)


def kpi(bg, x, y, w, h, value, label, color=NAVY):
    card(bg, x, y, w, h)
    bg.text(x + w / 2, y + h * 0.60, value, ha="center", va="center", fontsize=21, fontweight="bold", color=color)
    bg.text(x + w / 2, y + h * 0.20, label, ha="center", va="center", fontsize=7.4, color=INK2)


def heading(bg, x, y, title, sub=None, size=11, gap=0.26):
    bg.text(x, y, title, ha="left", va="top", fontsize=size, fontweight="bold", color=INK)
    if sub: bg.text(x, y - gap, sub, ha="left", va="top", fontsize=size * 0.69, color=INK2)


def clean(ax, left=False, bottom=True):
    for s in ("top", "right", "left", "bottom"): ax.spines[s].set_visible(False)
    if bottom: ax.spines["bottom"].set_visible(True); ax.spines["bottom"].set_color(GRID)
    if left: ax.spines["left"].set_visible(True); ax.spines["left"].set_color(GRID)
    ax.tick_params(length=0)
