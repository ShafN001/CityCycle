"""Framework and architecture diagrams used in the report.

    python3 -I diagrams.py OUT_DIR [EDA_JSON]

fig0_workflow.png     the weekly workflow with gates G1-G6 and verification layers L1-L3
fig_hsaaf.png         H-SAAF nine-step loop mapped to what was produced at each step
fig_bbd.png           Build - Break - Defend: what was built, what attacked it, what held
fig_governance.png    four governance lenses -> one memo
fig_eda_demand.png    EDA: when members and casual riders depart; where morning departures start
Colour: grey = code, blue = generative AI, orange = human decision. Gates carry a dark edge.
"""
import json, sys, textwrap
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BLUE, ORANGE, SURF, INK, INK2, GREYF, GRID = "#2a78d6", "#eb6834", "#fcfcfb", "#0b0b0b", "#52514e", "#eeede9", "#d0cfc9"
FILL = {"code": GREYF, "ai": "#dbe8f8", "human": "#fbe0d4"}
EDGE = {"code": INK2, "ai": BLUE, "human": ORANGE}
plt.rcParams.update({"font.family": "DejaVu Sans"})


def box(ax, x, y, w, h, title, sub, kind="code", gate=False, tfs=7.0, sfs=6.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.1", fc=FILL[kind],
                                ec=INK if gate else EDGE[kind], lw=2.4 if gate else 1.3))
    ax.text(x + w / 2, y + h * 0.70, title, ha="center", va="center", fontsize=tfs, fontweight="bold", color=INK)
    ax.text(x + w / 2, y + h * 0.31, sub, ha="center", va="center", fontsize=sfs, color=INK2, linespacing=1.15)


def canvas(w, h, xl, yl):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    ax.set_xlim(0, xl); ax.set_ylim(0, yl); ax.axis("off"); fig.patch.set_facecolor(SURF)
    return fig, ax


def arrow(ax, a, b, **kw):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="->", color=INK2, lw=1, **kw))


# ------------------------------------------------------------------ fig0
def workflow(out):
    fig, ax = canvas(8.6, 4.5, 100, 57)
    W, H = 15, 14
    xs = [1 + i * 16.6 for i in range(6)]
    r1, r2 = 33, 9
    row1 = [("1 Ingest", "trips, stations,\nfeedback + hashes", "code", False),
            ("2 EDA profile", "demand shape,\nweeks, bike_id", "code", False),
            ("G1 Data gate", "L1 · 13 stop checks\n+ 5 warnings", "code", True),
            ("3 Metrics, rules", "net flow % of docks\n4-wk mean vs 40%", "code", False),
            ("4 Move plan", "donors to\nreceivers", "code", False),
            ("G3 Verify", "L2 · conservation,\nindependent check", "code", True)]
    row2 = [("G2 Leakage", "L3 · look-ahead,\nsplit, baselines", "code", True),
            ("G5 Drift", "L3 · PSI, KS, volume\nvs reference", "code", True),
            ("5 Feedback", "reviewed theme\ntable (lookup)", "ai", False),
            ("6 Brief", "GenAI drafts from\nfacts.json only", "ai", False),
            ("G4 Grounding", "L2 · numbers, table\nrows, moves", "code", True),
            ("G6 Approve", "named ops lead\n→ publish + log", "human", True)]
    for (t, s, k, g), x in zip(row1, xs): box(ax, x, r1, W, H, t, s, k, g)
    for (t, s, k, g), x in zip(row2, xs): box(ax, x, r2, W, H, t, s, k, g)
    for i in range(5):
        arrow(ax, (xs[i] + W + 0.3, r1 + H / 2), (xs[i + 1] - 0.3, r1 + H / 2))
        arrow(ax, (xs[i] + W + 0.3, r2 + H / 2), (xs[i + 1] - 0.3, r2 + H / 2))
    ym = (r1 + r2 + H) / 2
    ax.plot([xs[5] + W / 2, xs[5] + W / 2, xs[0] + W / 2], [r1 - 0.3, ym, ym], color=INK2, lw=1)
    arrow(ax, (xs[0] + W / 2, ym), (xs[0] + W / 2, r2 + H + 0.3))
    ax.text(0, 54.5, "Weekly trigger: Monday 08:00. G1-G3 STOP the run. G4 retries, then a human writes the brief. G5 and G6 HOLD for the ops lead.",
            fontsize=6.6, color=INK2, va="center")
    ax.text(0, 2.6, "Grey = code · Blue = generative AI (classifies and drafts; never computes) · Orange = human decision · Dark edge = gate",
            fontsize=6.6, color=INK2)
    ax.text(0, 0.0, "Nothing is dispatched by the system. Every run writes run_log.json (evidence per step) and input hashes.", fontsize=6.6, color=INK2)
    fig.savefig(out / "fig0_workflow.png", bbox_inches="tight", facecolor=SURF)


# ------------------------------------------------------------------ H-SAAF
def hsaaf(out):
    fig, ax = canvas(8.4, 3.9, 102, 50)
    phases = [("SET UP", ["Frame", "Decompose", "Contextualise"]),
              ("DO", ["Delegate", "Execute", "VERIFY"]),
              ("CLOSE", ["Integrate", "Govern", "Communicate"])]
    made = [["work_order.md: decision = rebalance\nbikes weekly; metric = net outflow\n% of docks; risk tier = medium",
             "six gated steps, each with an\ninput, a 'done' and a check",
             "data contract, theme table, thresholds,\nbrief prompt: written down, versioned"],
            ["GenAI writes code and drafts the brief;\nthe analyst decides what to delegate\n(AI-use log, Appendix A)",
             "workflow.py runs the steps;\nEDA, rules, move plan, backtest",
             "G1-G5 across L1-L3; break_tests.py\nadds adversarial attacks; independent\nrecomputation"],
            ["brief + charts released only\nthrough G6; run_log.json kept",
             "G6 named approver; governance\nmemo; monitoring scorecard",
             "one-page brief for the ops lead;\nlimits stated, not hidden"]]
    w, h = 30, 11.5
    for j, (ph, names) in enumerate(phases):
        y0 = 36 - j * 14.2
        ax.text(0, y0 + h / 2, ph, rotation=90, ha="center", va="center", fontsize=7, fontweight="bold", color=INK2)
        for i, nm in enumerate(names):
            n = j * 3 + i + 1; x = 4 + i * 32
            ver = nm == "VERIFY"
            ax.add_patch(FancyBboxPatch((x, y0), w, h, boxstyle="round,pad=0.2,rounding_size=1.0", fc="#fbe0d4" if ver else GREYF,
                                        ec=ORANGE if ver else INK2, lw=2 if ver else 1.2))
            ax.text(x + 1.2, y0 + h - 2.0, f"{n} · {nm}", fontsize=7.6, fontweight="bold", va="center", color=INK)
            ax.text(x + 1.2, y0 + 4.3, made[j][i], fontsize=5.7, va="center", color=INK2, linespacing=1.2)
    ax.text(0, 49, "H-SAAF nine-step loop → what this workflow produced at each step. Verify is the heart: trust scales with verification, not polish.",
            fontsize=6.6, color=INK2, va="center")
    fig.savefig(out / "fig_hsaaf.png", bbox_inches="tight", facecolor=SURF)


# ------------------------------------------------------------------ Build-Break-Defend
def bbd(out, n_ok=13, n_all=13):
    fig, ax = canvas(8.4, 4.4, 100, 54)
    cols = [("BUILD", "Use the agent to create the first useful version", GREYF, INK2,
             ["Pipeline: ingest → EDA → rules → move plan", "13 stop checks + 5 warnings (data contract)",
              "Backtest: flag in week w, outcome in w+1", "Brief drafted by GenAI from facts.json only", "Grounding check on numbers"]),
            ("BREAK", "Attack with bad data, edge cases and misuse", "#fbe0d4", ORANGE,
             ["B1-B3 duplicate id, typo station, zero-length trip", "B4 prompt-injection text in feedback",
              "B5 / B11 silent truncation, member collapse", "B6-B8 wrong numbers, swapped rows, re-routed moves",
              "B9 tampered plan · B10 look-ahead leak · B12-B13 no approver, gates skipped"]),
            ("DEFEND", "Keep only what survives evidence and tests", "#dbe8f8", BLUE,
             [f"{n_ok}/{n_all} attacks caught by a named gate", "B5: G1 is blind to silent truncation → G5 volume check covers it",
              "B7: number check is blind to swapped rows → row-level check covers it", "Backtest 68% was selected in-sample →\nre-scored on held-out weeks: 65%",
              "Frozen list matches the weekly rule →\nvalue is persistence, not prediction"])]
    for i, (hd, sub, fc, ec, items) in enumerate(cols):
        x = 1 + i * 33
        ax.add_patch(FancyBboxPatch((x, 3), 31, 44, boxstyle="round,pad=0.2,rounding_size=1.2", fc=fc, ec=ec, lw=1.6))
        ax.text(x + 1.8, 44, f"{i + 1} · {hd}", fontsize=9.5, fontweight="bold", va="center", color=INK)
        ax.text(x + 1.8, 40.2, sub, fontsize=5.8, va="center", color=INK2, style="italic")
        for k, it in enumerate(items):
            ax.text(x + 1.8, 34.5 - k * 6.6, "• " + "\n  ".join(textwrap.wrap(it.replace("\n", " "), 40)), fontsize=5.9, va="center", color=INK, linespacing=1.2)
        if i < 2: arrow(ax, (x + 31.4, 25), (x + 32.8, 25))
    ax.text(0, 52.5, "Build · Break · Defend: the attacks exposed two single-gate blind spots (each now has a second gate) and corrected one claim.",
            fontsize=6.6, color=INK2, va="center")
    fig.savefig(out / "fig_bbd.png", bbox_inches="tight", facecolor=SURF)


# ------------------------------------------------------------------ governance lenses
def governance(out):
    fig, ax = canvas(8.4, 3.5, 100, 42)
    L = [("NIST AI RMF + GenAI", "HOW TO GOVERN",
          "Govern · Map · Measure · Manage\nGenAI risk named: confabulation"),
         ("IMDA Model AI Governance", "WHAT TO OPERATIONALISE",
          "Internal governance, human\ninvolvement, operations, stakeholders"),
         ("EU AI Act", "WHAT MAY BE REQUIRED",
          "Classify the use: internal decision\nsupport, no person-level decisions"),
         ("OWASP LLM Top 10", "WHAT CAN GO WRONG",
          "LLM01 prompt injection\nLLM06 excessive agency\nLLM09 misinformation")]
    for i, (t, q, s) in enumerate(L):
        x = 1 + i * 24.7
        ax.add_patch(FancyBboxPatch((x, 19), 23, 17, boxstyle="round,pad=0.2,rounding_size=1.0", fc=GREYF, ec=INK2, lw=1.2))
        ax.text(x + 11.5, 33, t, ha="center", va="center", fontsize=6.8, fontweight="bold", color=INK)
        ax.text(x + 11.5, 29.2, q, ha="center", va="center", fontsize=5.6, color=BLUE, fontweight="bold")
        ax.text(x + 11.5, 23.2, s, ha="center", va="center", fontsize=5.5, color=INK2, linespacing=1.2)
        arrow(ax, (x + 11.5, 18.6), (50, 12.3))
    ax.add_patch(FancyBboxPatch((14, 3), 72, 9, boxstyle="round,pad=0.2,rounding_size=1.0", fc="#fbe0d4", ec=ORANGE, lw=1.6))
    ax.text(50, 9.3, "ONE-PAGE GOVERNANCE MEMO", ha="center", va="center", fontsize=8, fontweight="bold", color=INK)
    ax.text(50, 5.6, "Purpose · Risk class · Ownership · Controls · Evidence · Monitoring · Accountability",
            ha="center", va="center", fontsize=6.2, color=INK2)
    ax.text(0, 40.5, "Four lenses, one memo: synthesis, not framework shopping.", fontsize=6.6, color=INK2, va="center")
    fig.savefig(out / "fig_governance.png", bbox_inches="tight", facecolor=SURF)


# ------------------------------------------------------------------ EDA
def eda_fig(out, eda_json):
    """Two cards (a) hourly demand, (b) hub concentration. Split at 61.6% so the report can crop each card."""
    import sys; sys.path.insert(0, str(Path(__file__).parent))
    import style as st
    import numpy as np
    r = json.load(open(eda_json)); h = r["demand_shape"]["hourly_departures"]; d = r["demand_shape"]
    hrs = sorted(int(k) for k in h)
    mem = [h[str(k)].get("Member", 0) for k in hrs]; cas = [h[str(k)].get("Casual", 0) for k in hrs]
    W, H = 8.4, 2.93; cut = 0.61585 * W; g = 0.1
    fig, bg = st.canvas(W, H)
    st.card(bg, 0.12, 0.12, cut - g - 0.12, H - 0.24); st.card(bg, cut + g, 0.12, W - 0.12 - cut - g, H - 0.24)
    st.heading(bg, 0.34, H - 0.26, "(a) Departures by hour and user type", "Members peak at commute hours; casual riders at midday", size=8.6, gap=0.2)
    ax = st.axes_at(fig, W, H, 0.85, 0.55, cut - g - 0.12 - 0.95, H - 1.55); st.clean(ax)
    ax.axvspan(7, 10, color="#efeee9", lw=0); ax.text(8.5, max(mem) * 1.02, "7\u201310am", ha="center", va="bottom", fontsize=7, color=st.INK2)
    ax.plot(hrs, mem, color=st.BLUE, lw=2.2); ax.plot(hrs, cas, color=st.ORANGE, lw=2.2)
    im, ic = mem.index(max(mem)), cas.index(max(cas))
    ax.text(hrs[im] + 0.45, mem[im], "Members", color=st.BLUE, fontsize=8, fontweight="bold", va="center")
    ax.text(hrs[ic] + 0.45, cas[ic] + 55, "Casual", color=st.ORANGE, fontsize=8, fontweight="bold", va="center")
    ax.yaxis.grid(True, color=st.GRID, lw=0.8); ax.set_axisbelow(True); ax.set_ylim(0, max(mem) * 1.18)
    ax.set_xlabel("hour of departure", fontsize=7.4, labelpad=3); ax.tick_params(labelsize=7.4)
    st.heading(bg, cut + g + 0.2, H - 0.26, "(b) Six hub stations", "Share of departures from the hubs", size=8.6, gap=0.2)
    ax2 = st.axes_at(fig, W, H, cut + g + 0.45, 0.45, W - 0.12 - cut - g - 0.9, H - 1.45); st.clean(ax2)
    vals = [d["hub_share_of_all_trips_pct"], d["am_share_from_hubs_pct_quarter"]]
    ax2.bar([0, 1], vals, color=[st.GREY, st.ORANGE], width=0.5)
    for x, v in zip([0, 1], vals): ax2.text(x, v + 3, f"{v:.1f}%", ha="center", fontsize=11, fontweight="bold", color=st.INK)
    ax2.set_xticks([0, 1]); ax2.set_xticklabels(["all trips", "7\u201310am\ndepartures"], fontsize=7.6)
    ax2.set_ylim(0, 108); ax2.set_yticks([])
    fig.savefig(out / "fig_eda_demand.png", facecolor=st.CANVAS)


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    workflow(out); hsaaf(out); bbd(out); governance(out)
    if len(sys.argv) > 2: eda_fig(out, sys.argv[2])
    print("diagrams written to", out)
