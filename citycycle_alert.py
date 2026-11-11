"""CityCycle weekly station-availability alert (decision-support automation).

Pipeline: load -> validate (data gate) -> weekly station metrics -> status rules
-> rebalancing move plan -> feedback corroboration -> facts.json (+ charts).
The numbers are computed here, deterministically. The generative-AI step only
*writes the brief* from facts.json and is then checked by ground_check().

Usage:  python3 citycycle_alert.py --data DATA_DIR --out OUT_DIR [--week 13]
"""
import argparse, json, math, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

CFG = dict(urgent_pct=40.0,    # net outflow >= 40% of docks per week -> restock
           surplus_pct=25.0,   # net inflow  >= 25% of docks per week -> donor / dock-full risk
           trail_weeks=4, am_start=7, am_end=10)

# Reviewed theme table: free-text comment -> (theme, polarity). 18 distinct strings in the file.
THEMES = {
    "no bikes available at my station in the morning": ("No bikes (morning)", "complaint"),
    "hard to find a bike at peak hour": ("No bikes (peak)", "complaint"),
    "docks were all full, couldn't return": ("Docks full", "complaint"),
    "always bikes at Bishan, great": ("Bikes available (Bishan)", "praise"),
    "the app keeps crashing when I unlock": ("App crash", "complaint"),
    "app GPS shows wrong station": ("App GPS", "complaint"),
    "payment failed in the app twice": ("Payment failed", "complaint"),
    "love how easy the app is to use": ("App ease", "praise"),
    "charged twice for one ride": ("Double charge", "complaint"),
    "unexpected late fee": ("Late fee", "complaint"),
    "brakes felt loose": ("Brakes", "complaint"),
    "tyre was flat": ("Flat tyre", "complaint"),
    "seat was wobbly": ("Seat", "complaint"),
    "gears slipping": ("Gears", "complaint"),
    "bike was in great condition": ("Bike condition ok", "praise"),
    "clean and well-maintained bikes": ("Bike condition ok", "praise"),
    "super convenient for my commute": ("Convenience", "praise"),
    "great value membership": ("Value", "praise"),
}
AVAIL_THEMES = {"No bikes (morning)", "No bikes (peak)", "Docks full"}


# ---------------------------------------------------------------- load + gate
def load(data):
    d = Path(data)
    t = pd.read_csv(d / "trips.csv", parse_dates=["start_time", "end_time"])
    s = pd.read_csv(d / "stations.csv")
    f = pd.read_csv(d / "feedback.csv", parse_dates=["date"])
    return t, s, f


def validate(t, s, f):
    """Data-contract gate. FAIL stops the run; WARN is reported to the human."""
    res = []
    def add(name, ok, detail, level="FAIL"):
        res.append(dict(check=name, status="PASS" if ok else level, detail=detail))
    need_t = {"trip_id","start_time","end_time","duration_min","start_station","end_station","user_type","bike_id","distance_km"}
    add("schema: trips columns", need_t <= set(t.columns), sorted(need_t - set(t.columns)))
    add("schema: stations/feedback columns",
        {"station","region","capacity"} <= set(s.columns) and {"feedback_id","date","user_type","category","rating","comment_text"} <= set(f.columns), "")
    add("no nulls (trips, stations, feedback)", int(t.isna().sum().sum() + s.isna().sum().sum() + f.isna().sum().sum()) == 0, "")
    add("trip_id unique", t.trip_id.is_unique, int(t.trip_id.duplicated().sum()))
    add("feedback_id unique", f.feedback_id.is_unique, int(f.feedback_id.duplicated().sum()))
    add("station keys match master", set(t.start_station) | set(t.end_station) <= set(s.station),
        sorted((set(t.start_station) | set(t.end_station)) - set(s.station)))
    mins = (t.end_time - t.start_time).dt.total_seconds() / 60
    add("end after start", bool((mins > 0).all()), int((mins <= 0).sum()))
    add("duration_min equals end-start", bool((abs(mins - t.duration_min) <= 1).all()), int((abs(mins - t.duration_min) > 1).sum()))
    add("duration in 1-180 min; distance > 0", bool(t.duration_min.between(1, 180).all() and (t.distance_km > 0).all()), "")
    add("user_type in {Member, Casual}", set(t.user_type) <= {"Member", "Casual"}, "")
    add("capacity positive", bool((s.capacity > 0).all()), "")
    add("rating in 1-5", bool(f.rating.between(1, 5).all()), "")
    unk = sorted(set(f.comment_text) - set(THEMES))
    add("feedback comments all in reviewed theme table", not unk, unk)
    # ---- WARN-level semantic checks (these do not stop the run)
    b = t.sort_values(["bike_id", "start_time"]).copy()
    b["pe"] = b.groupby("bike_id").end_time.shift(); b["ps"] = b.groupby("bike_id").end_station.shift()
    m = b.dropna(subset=["pe"])
    tele = int((m.start_station != m.ps).sum()); ovl = int((m.start_time < m.pe).sum())
    if len(m):
        add("bike_id forms a coherent location chain", tele / len(m) < 0.05,
            f"{tele} of {len(m)} consecutive trips start somewhere other than the bike's last drop-off ({tele/len(m):.0%}); {ovl} overlap in time -> bike_id not used for location", "WARN")
    else:
        add("bike_id forms a coherent location chain", False, "no bike has two trips: chain cannot be assessed -> bike_id not used for location", "WARN")
    same = float((t.start_station == t.end_station).mean())
    add("same-station round trips", same < 0.02, f"{same:.1%} of trips start and end at one station (kept; they net to zero)", "WARN")
    pol = f.comment_text.map(lambda c: THEMES[c][1]) if not unk else None
    if pol is not None:
        hi = float(((pol == "complaint") & (f.rating >= 4)).sum() / max(1, (pol == "complaint").sum()))
        add("star rating agrees with comment sentiment", hi < 0.10,
            f"{hi:.0%} of complaint comments carry a 4-5 star rating -> ratings not used as a sentiment signal", "WARN")
        av = f[f.category == "Availability"]; pa = av.comment_text.map(lambda c: THEMES[c][1])
        add("'Availability' category contains only complaints", bool((pa == "complaint").all()),
            f"{int((pa=='praise').sum())} of {len(av)} Availability items are praise -> classify by comment, not category", "WARN")
    add("feedback has a station field", False, "free text only; cannot be joined to a station except where Bishan is named", "WARN")
    return res


def complete_weeks(t):
    first, last = t.start_time.min().normalize(), t.start_time.max().normalize()
    wk = t.start_time.dt.isocalendar()
    keys = sorted({(int(y), int(w)) for y, w in zip(wk.year, wk.week)})
    out = []
    for y, w in keys:
        mon = pd.Timestamp.fromisocalendar(y, w, 1)
        if mon >= first and mon + pd.Timedelta(days=6) <= last:
            out.append((y, w))
    return out


# ---------------------------------------------------------------- metrics
def weekly_pct(t, s, weeks):
    t = t.copy()
    iso = t.start_time.dt.isocalendar(); t["wk"] = iso.week.astype(int)
    ws = [w for _, w in weeks]
    dep = t.groupby(["wk", "start_station"]).size().unstack(fill_value=0).reindex(index=ws, columns=s.station, fill_value=0)
    arr = t.groupby(["wk", "end_station"]).size().unstack(fill_value=0).reindex(index=ws, columns=s.station, fill_value=0)
    net_out = dep - arr                                    # + = station is losing bikes
    pct = net_out.div(s.set_index("station").capacity, axis=1) * 100
    return dep, arr, net_out, pct


def classify(this_pct, trail_mean, c=CFG):
    if trail_mean >= c["urgent_pct"]: return "RESTOCK - urgent"
    if this_pct >= c["urgent_pct"]: return "WATCH - low bikes"
    if trail_mean <= -c["surplus_pct"]: return "SURPLUS - donor / dock-full risk"
    if this_pct <= -c["surplus_pct"]: return "WATCH - dock-full"
    return "OK"


def station_table(t, s, weeks, target_week):
    ws = [w for _, w in weeks]
    dep, arr, net_out, pct = weekly_pct(t, s, weeks)
    i = ws.index(target_week); trail = ws[max(0, i - CFG["trail_weeks"] + 1): i + 1]
    t2 = t.copy(); t2["wk"] = t2.start_time.dt.isocalendar().week.astype(int); t2["hr"] = t2.start_time.dt.hour
    wk = t2[t2.wk == target_week]
    am = wk[(wk.hr >= CFG["am_start"]) & (wk.hr < CFG["am_end"])].groupby("start_station").size()
    cap = s.set_index("station").capacity
    rows = []
    for st in s.station:
        tm = float(pct.loc[trail, st].mean()); tw = float(pct.loc[target_week, st])
        rows.append(dict(station=st, region=s.set_index("station").region[st], capacity=int(cap[st]),
                         departures=int(dep.loc[target_week, st]), arrivals=int(arr.loc[target_week, st]),
                         net_outflow=int(net_out.loc[target_week, st]), net_pct_this_week=round(tw, 1),
                         net_pct_4wk_mean=round(tm, 1),
                         net_bikes_per_week_4wk=round(float(net_out.loc[trail, st].mean()), 1),
                         weeks_over_urgent_of_4=int((pct.loc[trail, st] >= CFG["urgent_pct"]).sum()),
                         am_peak_departures=int(am.get(st, 0)), status=classify(tw, tm)))
    df = pd.DataFrame(rows).sort_values("net_pct_4wk_mean", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df, trail


def move_plan(tab):
    """Greedy plan. Receivers = RESTOCK stations (need = 4-wk mean net outflow, bikes/week).
    Donors = stations with a net inflow: tier 1 = SURPLUS-status, tier 2 = any other station with >=1 bike/week net inflow."""
    need = {r.station: max(0, round(r.net_bikes_per_week_4wk)) for r in tab.itertuples() if r.status.startswith("RESTOCK")}
    give, tier = {}, {}
    for r in tab.itertuples():
        g = max(0, round(-r.net_bikes_per_week_4wk))
        if r.status.startswith("SURPLUS") and g > 0: give[r.station] = g; tier[r.station] = 1
        elif g >= 1 and not r.status.startswith("RESTOCK"): give[r.station] = g; tier[r.station] = 2
    donor_capacity = dict(give)
    moves = []
    for to, n in sorted(need.items(), key=lambda x: -x[1]):
        for frm in sorted(give, key=lambda k: (tier[k], -give[k])):
            q = min(n, give[frm])
            if q > 0: moves.append(dict(from_station=frm, to_station=to, bikes=int(q), donor_tier=tier[frm])); give[frm] -= q; n -= q
            if n == 0: break
        if n > 0: moves.append(dict(from_station="(no donor left - escalate)", to_station=to, bikes=int(n), donor_tier=0))
    return moves, need, donor_capacity


def feedback_summary(f, wk_start, wk_end):
    f = f.copy(); f["theme"] = f.comment_text.map(lambda c: THEMES[c][0]); f["polarity"] = f.comment_text.map(lambda c: THEMES[c][1])
    q = f.theme.value_counts().to_dict()
    inwk = f[(f.date >= wk_start) & (f.date <= wk_end)]
    comp = f[f.polarity == "complaint"]
    av = f[f.category == "Availability"]
    return dict(total=int(len(f)),
                availability_category_items=int(len(av)),
                availability_complaints=int(av.theme.isin(AVAIL_THEMES).sum()),
                availability_praise=int((av.polarity == "praise").sum()),
                morning_no_bikes=int((f.theme == "No bikes (morning)").sum()),
                peak_no_bikes=int((f.theme == "No bikes (peak)").sum()),
                docks_full=int((f.theme == "Docks full").sum()),
                bishan_praise=int((f.theme == "Bikes available (Bishan)").sum()),
                complaints_total=int(len(comp)),
                complaints_rated_4_5=int((comp.rating >= 4).sum()),
                top_complaint_themes={k: int(v) for k, v in comp.theme.value_counts().head(5).items()},
                items_in_target_week=int(len(inwk)),
                availability_items_in_target_week=int(inwk.category.eq("Availability").sum()),
                by_category_polarity={c: {p: int(n) for p, n in g.polarity.value_counts().items()} for c, g in f.groupby("category")},
                theme_counts={k: int(v) for k, v in q.items()})


def backtest(t, s, weeks):
    """Does a rule applied in week w predict net outflow >= urgent in week w+1?"""
    ws = [w for _, w in weeks]; _, _, _, pct = weekly_pct(t, s, weeks)
    out = {"A_single_week": [0, 0, 0], "B_4wk_mean": [0, 0, 0]}   # tp, flagged, actual
    for i in range(CFG["trail_weeks"] - 1, len(ws) - 1):
        nxt = pct.iloc[i + 1] >= CFG["urgent_pct"]
        rules = {"A_single_week": pct.iloc[i] >= CFG["urgent_pct"],
                 "B_4wk_mean": pct.iloc[i - CFG["trail_weeks"] + 1: i + 1].mean() >= CFG["urgent_pct"]}
        for k, fl in rules.items():
            out[k][0] += int((fl & nxt).sum()); out[k][1] += int(fl.sum()); out[k][2] += int(nxt.sum())
    return {k: dict(precision=round(v[0] / v[1], 2) if v[1] else None, recall=round(v[0] / v[2], 2) if v[2] else None,
                    flagged=v[1], hits=v[0], actual=v[2]) for k, v in out.items()}


# ---------------------------------------------------------------- narrative grounding gate
def flatten_numbers(obj, acc=None):
    acc = set() if acc is None else acc
    if isinstance(obj, dict):
        for v in obj.values(): flatten_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj: flatten_numbers(v, acc)
    elif isinstance(obj, bool): pass
    elif isinstance(obj, (int, float)):
        x = float(obj)
        for v in (x, abs(x), round(x), round(abs(x)), round(x, 1), round(abs(x), 1)): acc.add(round(v, 1))
    elif isinstance(obj, str):
        for n in re.findall(r"\d+(?:\.\d+)?", obj): acc.add(round(float(n), 1))
    return acc


def ground_check(text, facts, extra_ok=()):
    allowed = flatten_numbers(facts) | {round(float(x), 1) for x in extra_ok}
    bad = []
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)", text):
        v = round(float(m.group(1)), 1)
        if v not in allowed: bad.append(m.group(1))
    return sorted(set(bad))


# ---------------------------------------------------------------- main
def run(data, out, week=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    t, s, f = load(data)
    gate = validate(t, s, f)
    fails = [g for g in gate if g["status"] == "FAIL"]
    if fails:
        print("DATA GATE FAILED - stopping:", json.dumps(fails, indent=1)); sys.exit(1)
    weeks = complete_weeks(t); ws = [w for _, w in weeks]
    target = week or ws[-1]
    assert target in ws, f"week {target} is not a complete week; choose from {ws}"
    tab, trail = station_table(t, s, weeks, target)
    moves, need, give = move_plan(tab)
    y = [yy for yy, w in weeks if w == target][0]
    wk_start = pd.Timestamp.fromisocalendar(y, target, 1); wk_end = pd.Timestamp.fromisocalendar(y, target, 7)
    t["wk"] = t.start_time.dt.isocalendar().week.astype(int)
    tw = t[t.wk == target]
    hr = tw.start_time.dt.hour
    am_all = tw[(hr >= CFG["am_start"]) & (hr < CFG["am_end"])]
    hubs = tab[tab.status.str.startswith("RESTOCK")].station.tolist()
    facts = dict(
        week=dict(iso_week=int(target), start=str(wk_start.date()), end=str(wk_end.date()), trailing_weeks=trail,
                  trips=int(len(tw)), member_share_pct=round(float((tw.user_type == "Member").mean() * 100), 1),
                  am_peak_trips=int(len(am_all)),
                  am_peak_share_from_urgent_stations_pct=round(float(am_all.start_station.isin(hubs).mean() * 100), 1) if len(am_all) else None),
        thresholds=CFG, data_gate=gate, stations=tab.to_dict("records"),
        restock_need_bikes_per_week=need, donor_capacity_bikes_per_week=give, moves=moves,
        total_bikes_to_move=int(sum(m["bikes"] for m in moves if not m["from_station"].startswith("("))),
        bikes_from_tier1_donors=int(sum(m["bikes"] for m in moves if m["donor_tier"] == 1)),
        bikes_from_tier2_donors=int(sum(m["bikes"] for m in moves if m["donor_tier"] == 2)),
        unmet_bikes=int(sum(m["bikes"] for m in moves if m["donor_tier"] == 0)),
        feedback=feedback_summary(f, wk_start, wk_end), backtest=backtest(t, s, weeks),
        quarter=dict(trips=int(len(t)), complete_weeks=len(weeks), first=str(t.start_time.min().date()), last=str(t.start_time.max().date())))
    (out / "facts.json").write_text(json.dumps(facts, indent=1, default=str))
    tab.to_csv(out / f"station_priority_wk{target}.csv", index=False)
    pd.DataFrame(moves).to_csv(out / f"moves_wk{target}.csv", index=False)
    pd.DataFrame(gate).to_csv(out / "data_gate_report.csv", index=False)
    return t, s, f, weeks, tab, facts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--week", type=int); a = ap.parse_args()
    _, _, _, _, tab, facts = run(a.data, a.out, a.week)
    print(tab[["rank","station","capacity","net_outflow","net_pct_this_week","net_pct_4wk_mean","weeks_over_urgent_of_4","status"]].to_string(index=False))
    print("moves:", facts["moves"]); print("backtest:", facts["backtest"])
    print("gate:", [(g["check"], g["status"]) for g in facts["data_gate"] if g["status"] != "PASS"])
