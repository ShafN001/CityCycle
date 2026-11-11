"""Charts for the CityCycle weekly alert. Usage: python3 charts.py DATA_DIR OUT_DIR [week]"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Patch
sys.path.insert(0, str(Path(__file__).parent))
import citycycle_alert as ca

from style import *
SURF = CARD
from matplotlib.patches import Patch, Rectangle


def fig1(tab, out, wk, facts=None):
    W, H = 8.2, 6.0
    d = tab.sort_values("net_pct_4wk_mean")
    n_r = int(sum(s.startswith("RESTOCK") for s in tab.status)); n_s = int(sum(s.startswith("SURPLUS") for s in tab.status))
    fig, bg = canvas(W, H)
    kw, kh, ky = (W - 0.4 - 0.3) / 3, 0.85, H - 0.2 - 0.85
    kp = [(str(n_r), "stations to restock", ORANGE), (str(n_s), "donor stations", BLUE)]
    if facts: kp.append((str(facts["total_bikes_to_move"]), f"bikes to move per week ({len(facts['moves'])} moves)", NAVY))
    for i, (v, l, c) in enumerate(kp): kpi(bg, 0.2 + i * (kw + 0.15), ky, kw, kh, v, l, c)
    cy, ch = 0.2, ky - 0.15 - 0.2
    card(bg, 0.2, cy, W - 0.4, ch)
    heading(bg, 0.45, cy + ch - 0.2, f"Station pressure, ISO week {wk}",
            f"Bars: 4-week mean net outflow as % of dock capacity. Circles: week {wk} alone.")
    for i, (c, l) in enumerate([(ORANGE, "Restock"), (BLUE, "Surplus / donor"), (GREY, "OK or watch")]):
        bg.add_patch(Rectangle((4.55 + i * 1.18, cy + ch - 0.33), 0.12, 0.12, fc=c, ec="none")); bg.text(4.72 + i * 1.18, cy + ch - 0.27, l, va="center", fontsize=7.4, color=INK2)
    ax = axes_at(fig, W, H, 2.15, cy + 0.55, W - 2.15 - 1.15, ch - 1.55); clean(ax)
    col = [ORANGE if s.startswith("RESTOCK") else BLUE if s.startswith("SURPLUS") else GREY for s in d.status]
    y = np.arange(len(d))
    ax.barh(y, d.net_pct_4wk_mean, color=col, height=0.58)
    ax.scatter(d.net_pct_this_week, y, s=26, facecolor="white", edgecolor=INK, linewidth=1.1, zorder=3)
    ax.axvline(0, color=INK2, lw=0.8)
    for x_, lab in [(ca.CFG["urgent_pct"], f"restock \u2265 {ca.CFG['urgent_pct']:.0f}%"), (-ca.CFG["surplus_pct"], f"surplus \u2264 \u2212{ca.CFG['surplus_pct']:.0f}%")]:
        ax.axvline(x_, color=INK2, lw=0.8, ls=(0, (3, 3)), alpha=0.8)
        ax.text(x_, len(d) - 0.35, lab, ha="center", va="bottom", fontsize=7, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels(d.station, fontsize=8.2); ax.set_ylim(-0.6, len(d) - 0.2)
    ax.set_xlim(-85, 115); ax.tick_params(axis="x", labelsize=7.5)
    ax.xaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.set_xlabel("Net outflow, % of dock capacity per week (departures minus arrivals)", fontsize=7.8, labelpad=6)
    tr = ax.get_yaxis_transform()
    ax.text(1.04, len(d) - 0.35, "4-wk mean", transform=tr, ha="left", va="bottom", fontsize=7.2, color=INK2)
    for yi, v in zip(y, d.net_pct_4wk_mean):
        ax.text(1.04, yi, f"{v:.0f}%", transform=tr, va="center", ha="left", fontsize=8, fontweight="bold", color=INK, clip_on=False)
    fig.savefig(out / "fig1_station_pressure.png", facecolor=CANVAS); plt.close(fig)


def fig2(t, s, weeks, tab, out):
    _, _, _, pct = ca.weekly_pct(t, s, weeks)
    order = tab.sort_values("net_pct_4wk_mean", ascending=False).station.tolist()
    m = pct[order].T
    W, H = 8.2, 6.0
    fig, bg = canvas(W, H); card(bg, 0.2, 0.2, W - 0.4, H - 0.4)
    heading(bg, 0.45, H - 0.38, "The same stations drain week after week",
            "Weekly net outflow, % of dock capacity. Orange: losing bikes; blue: gaining bikes (capped at \u00b1100%).")
    ax = axes_at(fig, W, H, 2.15, 0.95, W - 2.15 - 1.2, H - 2.0)
    cmap = LinearSegmentedColormap.from_list("div", [BLUE, "#eeeeea", ORANGE])
    im = ax.imshow(m.values, aspect="auto", cmap=cmap, norm=TwoSlopeNorm(vcenter=0, vmin=-100, vmax=100))
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=8.2)
    ax.set_xticks(range(m.shape[1])); ax.set_xticklabels([f"W{c}" for c in m.columns], fontsize=7.5)
    ax.xaxis.tick_top(); ax.tick_params(length=0)
    ax.set_xticks(np.arange(-.5, m.shape[1]), minor=True); ax.set_yticks(np.arange(-.5, len(order)), minor=True)
    ax.grid(which="minor", color="white", lw=2); ax.tick_params(which="minor", length=0)
    for sp in ax.spines.values(): sp.set_visible(False)
    flags = (m >= ca.CFG["urgent_pct"]).sum(axis=1)
    tr = ax.get_yaxis_transform()
    ax.text(1.03, -0.95, f"weeks \u2265 {ca.CFG['urgent_pct']:.0f}%", transform=tr, ha="left", va="bottom", fontsize=7.2, color=INK2)
    for i, k in enumerate(flags.values):
        ax.text(1.03, i, f"{k}/{m.shape[1]}", transform=tr, va="center", ha="left", fontsize=8, fontweight="bold" if k >= 7 else "normal", color=INK if k >= 7 else INK2)
    cax = fig.add_axes([2.15 / W, 0.42 / H, 3.0 / W, 0.11 / H])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal"); cb.outline.set_visible(False)
    cb.set_ticks([-100, -50, 0, 50, 100]); cb.ax.tick_params(labelsize=7, length=0)
    fig.savefig(out / "fig2_weekly_heatmap.png", facecolor=CANVAS); plt.close(fig)


def fig3(fb, out):
    items = [("No bikes in the morning", fb["morning_no_bikes"], ORANGE), ("Hard to find a bike at peak", fb["peak_no_bikes"], ORANGE),
             ("Docks full, could not return", fb["docks_full"], ORANGE), ("'Always bikes at Bishan, great'", fb["bishan_praise"], BLUE)]
    fig, ax = plt.subplots(figsize=(8.2, 2.9), dpi=200)
    y = np.arange(len(items))[::-1]
    ax.barh(y, [i[1] for i in items], color=[i[2] for i in items], height=0.55, edgecolor=SURF, linewidth=2)
    ax.set_yticks(y); ax.set_yticklabels([i[0] for i in items], fontsize=9)
    for yi, i in zip(y, items): ax.text(i[1] + 0.5, yi, str(i[1]), va="center", fontsize=9)
    ax.set_xlim(0, 33); ax.set_xlabel("Number of feedback items (quarter)", fontsize=9)
    ax.set_title(f"'Availability' feedback: {fb['availability_complaints']} complaints, {fb['availability_praise']} praise (of {fb['availability_category_items']})", loc="left", fontsize=11, fontweight="bold", pad=10)
    ax.legend(handles=[Patch(color=ORANGE, label="Complaint"), Patch(color=BLUE, label="Praise")], loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2, fontsize=8, frameon=False)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.grid(axis="x", color=GRID, lw=0.6); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(out / "fig3_feedback_availability.png"); plt.close(fig)


if __name__ == "__main__":
    data, out = sys.argv[1], Path(sys.argv[2]); wk = int(sys.argv[3]) if len(sys.argv) > 3 else None
    t, s, f, weeks, tab, facts = ca.run(data, out, wk)
    w = facts["week"]["iso_week"]
    fig1(tab, out, w, facts); fig2(t, s, weeks, tab, out); fig3(facts["feedback"], out)
    print("charts written for week", w)
