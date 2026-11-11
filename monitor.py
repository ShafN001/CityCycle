"""Leakage audit, baselines and drift monitor for the CityCycle availability alert.

Seminar mapping (weeks 2-4):
  * Leakage taxonomy (four faces): target/proxy, look-ahead, label-conditional,
    train-test contamination  -> leakage_audit()
  * "Build baselines before anything clever"; "a baseline is a leak detector"  -> baselines()
  * L3 distributional layer: PSI / KS drift                                    -> drift_report()

The 'model' here is a rule (4-week mean net outflow >= 40% of docks). Its 'label' is
"net outflow >= 40% of docks in the NEXT complete week". All checks are deterministic.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citycycle_alert as core

U = core.CFG["urgent_pct"]
TW = core.CFG["trail_weeks"]

# ------------------------------------------------------------------ thresholds (reviewed by ops lead)
MONITOR = dict(
    psi_watch=0.10, psi_drift=0.25,       # standard PSI bands: <0.10 stable, 0.10-0.25 watch, >0.25 drift
    volume_band_pct=20.0,                  # weekly trips within +/-20% of reference mean (silent-truncation guard)
    member_share_pp=10.0,                  # member share may move at most 10 percentage points
    ks_alpha=0.01,                         # trip-duration KS test
    leak_suspect=0.95,                     # a single simple rule scoring >= 0.95 precision is a leakage warning
    precision_floor=0.50,                  # rolling flag precision below this for 4 weeks -> review thresholds
    ref_first_weeks=8,                     # reference window = first 8 complete weeks
)


# ================================================================== baselines + honest backtest
def _flags(pct, i, rule):
    """Flags using ONLY weeks <= i (index into pct rows)."""
    if rule == "single_week":
        return pct.iloc[i] >= U
    if rule == "mean4":
        return pct.iloc[max(0, i - TW + 1): i + 1].mean() >= U
    raise ValueError(rule)


def _score(pct, idxs, flagger):
    """Precision/recall of flags(i) against outcome at i+1. Asserts no look-ahead."""
    tp = fl = act = 0
    for i in idxs:
        flags = flagger(i)
        outcome = pct.iloc[i + 1] >= U           # the future week
        assert i + 1 < len(pct), "outcome week must exist"
        tp += int((flags & outcome).sum()); fl += int(flags.sum()); act += int(outcome.sum())
    return dict(flagged=fl, hits=tp, actual=act,
                precision=round(tp / fl, 2) if fl else None, recall=round(tp / act, 2) if act else None)


def baselines(t, s, weeks):
    """Rules vs naive baselines on the same station-weeks. Returns dict of results.

    chance          flag at random with probability = base rate (precision = base rate)
    never_flag      most-frequent-class baseline: flags nothing (recall 0) - the floor
    persistence     last week's single-week breach carries over (the obvious naive rule)
    frozen_list     flag the stations that breached in the first 4 weeks, forever (no weekly updating)
    mean4 (ours)    4-week mean >= 40% of docks
    """
    ws = [w for _, w in weeks]
    _, _, _, pct = core.weekly_pct(t, s, weeks)
    n = len(ws)
    idx = list(range(TW - 1, n - 1))                           # weeks with a full 4-week trail and a next week
    n_cells = len(idx) * pct.shape[1]
    actual = sum(int((pct.iloc[i + 1] >= U).sum()) for i in idx)
    base = actual / n_cells
    frozen = (pct.iloc[:TW].mean() >= U)                       # learned from the first 4 weeks only
    res = dict(
        eval_weeks=[ws[i] for i in idx], station_weeks=n_cells, base_rate=round(base, 2),
        chance=dict(precision=round(base, 2), recall=round(base, 2)),
        never_flag=dict(precision=None, recall=0.0),
        persistence=_score(pct, idx, lambda i: _flags(pct, i, "single_week")),
        frozen_list=_score(pct, idx[TW:], lambda i: frozen),   # scored only after the 4 weeks used to build it
        mean4=_score(pct, idx, lambda i: _flags(pct, i, "mean4")),
        # like-for-like: our rule scored on exactly the weeks the frozen list is scored on
        mean4_same_weeks_as_frozen=_score(pct, idx[TW:], lambda i: _flags(pct, i, "mean4")),
        persistence_same_weeks_as_frozen=_score(pct, idx[TW:], lambda i: _flags(pct, i, "single_week")),
    )
    res["lift_over_chance"] = round(res["mean4"]["precision"] / base, 1)
    return res


def selection_split(t, s, weeks, cut=None):
    """Train/test contamination guard: pick the rule on early weeks only, score it on later weeks.

    The report's headline precision (68%) was computed on all 12 weeks after comparing two rules
    on the same data - that is selection on the test set. This re-scores honestly."""
    ws = [w for _, w in weeks]
    cut = cut or ws[len(ws) // 2]                 # median complete week (week 8 for weeks 2-13)
    _, _, _, pct = core.weekly_pct(t, s, weeks)
    n = len(ws)
    idx_all = list(range(TW - 1, n - 1))
    train = [i for i in idx_all if ws[i + 1] <= cut]           # outcomes inside weeks <= cut
    test = [i for i in idx_all if ws[i] > cut - 1 and ws[i + 1] > cut]
    sc = {r: _score(pct, train, lambda i, r=r: _flags(pct, i, r)) for r in ("single_week", "mean4")}
    chosen = max(sc, key=lambda r: (sc[r]["precision"] or 0))
    held = _score(pct, test, lambda i: _flags(pct, i, chosen))
    return dict(train_outcome_weeks=[ws[i + 1] for i in train], test_outcome_weeks=[ws[i + 1] for i in test],
                train_scores=sc, chosen_on_train=chosen, held_out=held,
                disjoint=not (set(train) & set(test)))


# ================================================================== leakage audit
def leakage_audit(t, s, f, weeks, target):
    """Four faces of leakage, each as a permanent test. Returns evidence dict for gate G2."""
    ws = [w for _, w in weeks]
    ev = {}
    # 1. LOOK-AHEAD: status for week `target` must not change if every later trip is deleted.
    y = [yy for yy, w in weeks if w == target][0]
    wk_end = pd.Timestamp.fromisocalendar(y, target, 7) + pd.Timedelta(days=1)
    t_cut = t[t.start_time < wk_end]
    full, _ = core.station_table(t, s, weeks, target)
    cut, _ = core.station_table(t_cut, s, [wy for wy in weeks if wy[1] <= target], target)
    same = full.drop(columns=["rank"]).reset_index(drop=True).equals(cut.drop(columns=["rank"]).reset_index(drop=True))
    ev["look_ahead_status_unchanged_when_future_deleted"] = bool(same)
    ev["latest_trip_used_after_week_end"] = bool((t_cut.start_time >= wk_end).any())
    # 2. TARGET / PROXY: no single simple rule may look 'too good'.
    b = baselines(t, s, weeks)
    ev["best_rule_precision"] = b["mean4"]["precision"]
    ev["persistence_precision"] = b["persistence"]["precision"]
    ev["leak_suspect_threshold"] = MONITOR["leak_suspect"]
    # 3. LABEL-CONDITIONAL: no missingness patterns (the data has no nulls; confirm per column)
    ev["null_cells_trips_feedback"] = int(t.isna().sum().sum() + f.isna().sum().sum())
    # 4. TRAIN-TEST CONTAMINATION: duplicates + rule chosen on early weeks, scored on later weeks
    ev["duplicate_trip_ids"] = int(t.trip_id.duplicated().sum())
    ev["duplicate_rows"] = int(t.duplicated().sum())
    sp = selection_split(t, s, weeks)
    ev["selection_split_disjoint"] = sp["disjoint"]
    ev["rule_chosen_on_early_weeks"] = sp["chosen_on_train"]
    ev["held_out_precision"] = sp["held_out"]["precision"]
    ev["held_out_flagged"] = sp["held_out"]["flagged"]
    ev["held_out_beats_chance"] = bool(sp["held_out"]["precision"] is not None and sp["held_out"]["precision"] > b["base_rate"])
    # 5. FEATURE ALLOW-LIST: the rule may read only these columns.
    ev["allowed_columns"] = ["start_time", "start_station", "end_station", "capacity"]
    return ev, b, sp


# ================================================================== drift
def psi(ref, cur, bins):
    """Population Stability Index over fixed bins (add epsilon so empty bins do not explode)."""
    r, _ = np.histogram(ref, bins=bins); c, _ = np.histogram(cur, bins=bins)
    r = (r + 0.5) / (r.sum() + 0.5 * len(r)); c = (c + 0.5) / (c.sum() + 0.5 * len(c))
    return float(np.sum((c - r) * np.log(c / r)))


def psi_counts(ref_counts, cur_counts):
    keys = sorted(set(ref_counts) | set(cur_counts))
    r = np.array([ref_counts.get(k, 0) for k in keys], float) + 0.5
    c = np.array([cur_counts.get(k, 0) for k in keys], float) + 0.5
    r /= r.sum(); c /= c.sum()
    return float(np.sum((c - r) * np.log(c / r)))


NET_BINS = [-1e9, -50, -25, 0, 25, 40, 60, 1e9]       # net outflow % of docks, aligned with the rules


def drift_report(t, s, f, weeks, target, ref_n=None):
    """Compare the target week with a reference window of earlier complete weeks.

    Returns list of metric rows (name, value, watch, drift, status). Status in {OK, WATCH, DRIFT}.
    The reference never includes the target week (no contamination of the monitor itself)."""
    ws = [w for _, w in weeks]
    ref_n = ref_n or MONITOR["ref_first_weeks"]
    ref_w = [w for w in ws if w < target][:ref_n]
    assert ref_w and target not in ref_w
    t = t.copy(); t["wk"] = t.start_time.dt.isocalendar().week.astype(int); t["hr"] = t.start_time.dt.hour
    R, C = t[t.wk.isin(ref_w)], t[t.wk == target]
    _, _, _, pct = core.weekly_pct(t, s, weeks)
    rows = []

    def add(name, value, watch, drift, unit="", higher_bad=True):
        st = "DRIFT" if (value > drift if higher_bad else value < drift) else "WATCH" if (value > watch if higher_bad else value < watch) else "OK"
        rows.append(dict(metric=name, value=round(float(value), 3), watch=watch, drift=drift, unit=unit, status=st))

    # volume (silent truncation / outage guard)
    ref_mean = R.groupby("wk").size().mean()
    dev = abs(len(C) - ref_mean) / ref_mean * 100
    add("weekly trips deviation from reference mean", dev, MONITOR["volume_band_pct"] / 2, MONITOR["volume_band_pct"], "%")
    # member share
    ms = abs((C.user_type == "Member").mean() - (R.user_type == "Member").mean()) * 100
    add("member share shift", ms, MONITOR["member_share_pp"] / 2, MONITOR["member_share_pp"], "pp")
    # hour-of-day mix, station mix, net-flow distribution (PSI)
    add("PSI hour-of-day departures", psi(R.hr, C.hr, np.arange(0, 25)), MONITOR["psi_watch"], MONITOR["psi_drift"])
    add("PSI start-station mix", psi_counts(R.start_station.value_counts().to_dict(), C.start_station.value_counts().to_dict()),
        MONITOR["psi_watch"], MONITOR["psi_drift"])
    # A single week has only 20 station values, so its PSI is noise (null range 0.01-0.72 on the
    # reference weeks). Use the trailing 4 weeks (80 values) against the reference pool instead.
    ref_net = pct.loc[ref_w].values.ravel()
    trail = [w for w in ws if w <= target][-TW:]
    cur_net = pct.loc[trail].values.ravel()
    add("PSI station net-outflow % (trailing 4 wks)", psi(ref_net, cur_net, NET_BINS), MONITOR["psi_watch"], MONITOR["psi_drift"])
    # trip duration (KS)
    ks = ks_2samp(R.duration_min, C.duration_min)
    rows.append(dict(metric="KS trip duration (p-value)", value=round(float(ks.pvalue), 3), watch=0.05, drift=MONITOR["ks_alpha"], unit="p",
                     status="DRIFT" if ks.pvalue < MONITOR["ks_alpha"] else "WATCH" if ks.pvalue < 0.05 else "OK"))
    # feedback vocabulary (prompt-injection / new-input guard): unseen strings
    unk = sorted(set(f.comment_text) - set(core.THEMES))
    rows.append(dict(metric="unrecognised feedback strings", value=len(unk), watch=0, drift=0, unit="count",
                     status="DRIFT" if unk else "OK"))
    return rows, ref_w


def noise_floor(t, s, f, weeks):
    """How much PSI/volume wiggle is normal? Score each reference week against the other reference weeks."""
    ws = [w for _, w in weeks][: MONITOR["ref_first_weeks"]]
    t = t.copy(); t["wk"] = t.start_time.dt.isocalendar().week.astype(int)
    out = []
    for w in ws:
        R, C = t[t.wk.isin([x for x in ws if x != w])], t[t.wk == w]
        out.append(dict(week=w, psi_station_mix=psi_counts(R.start_station.value_counts().to_dict(), C.start_station.value_counts().to_dict())))
    return dict(max_psi_station_mix=round(max(o["psi_station_mix"] for o in out), 3),
                mean_psi_station_mix=round(float(np.mean([o["psi_station_mix"] for o in out])), 3))


# ================================================================== rolling scorecard
def rolling_flag_precision(t, s, weeks, upto):
    """Precision of last week's RESTOCK flags against this week's outcome (the 'did the alert hold?' signal)."""
    ws = [w for _, w in weeks]; _, _, _, pct = core.weekly_pct(t, s, weeks)
    i = ws.index(upto)
    if i < TW: return None
    flags = _flags(pct, i - 1, "mean4"); outcome = pct.iloc[i] >= U
    return dict(week=upto, flagged=int(flags.sum()), still_over=int((flags & outcome).sum()),
                precision=round(float((flags & outcome).sum() / flags.sum()), 2) if flags.sum() else None)
