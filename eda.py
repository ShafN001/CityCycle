"""Exploratory data analysis for the CityCycle availability workflow (H-SAAF step 5, Execute).

Every number quoted in the report's EDA / data-quality sections is produced here, so a
reader can reproduce it:  python3 -I eda.py DATA_DIR OUT_DIR [week]

EDA is a *profiling* step: it proposes findings, a human decides what they mean (week 3).
Output: eda_report.json plus printed tables.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citycycle_alert as core


def profile(t, s, f, weeks, hubs):
    ws = [w for _, w in weeks]
    t = t.copy()
    t["wk"] = t.start_time.dt.isocalendar().week.astype(int)
    t["hr"] = t.start_time.dt.hour
    t["dow"] = t.start_time.dt.dayofweek
    days = (t.start_time.max().normalize() - t.start_time.min().normalize()).days + 1
    am = t[(t.hr >= core.CFG["am_start"]) & (t.hr < core.CFG["am_end"])]
    we = t.dow >= 5

    def net(df, st):  # departures minus arrivals for a station set
        return int(df.start_station.isin(st).sum() - df.end_station.isin(st).sum())

    # ---- bike_id continuity (used by the data gate WARN check; shown here as evidence)
    b = t.sort_values(["bike_id", "start_time"]).copy()
    b["pe"] = b.groupby("bike_id").end_time.shift(); b["ps"] = b.groupby("bike_id").end_station.shift()
    m = b.dropna(subset=["pe"])

    # ---- completeness of ISO weeks
    days_per_wk = t.groupby("wk").start_time.agg(lambda x: x.dt.date.nunique()).to_dict()

    fb = f.copy()
    fb["theme"] = fb.comment_text.map(lambda c: core.THEMES.get(c, ("UNKNOWN", "unknown"))[0])
    fb["pol"] = fb.comment_text.map(lambda c: core.THEMES.get(c, ("UNKNOWN", "unknown"))[1])
    comp = fb[fb.pol == "complaint"]

    hourly = t.groupby(["hr", "user_type"]).size().unstack(fill_value=0)
    return dict(
        overview=dict(trips=len(t), first=str(t.start_time.min().date()), last=str(t.start_time.max().date()),
                      stations=len(s), feedback_items=len(f), calendar_days=days,
                      trips_per_day=round(len(t) / days, 1),
                      member_share_pct=round(float((t.user_type == "Member").mean() * 100), 1),
                      mean_duration_min=round(float(t.duration_min.mean()), 1),
                      mean_distance_km=round(float(t.distance_km.mean()), 2),
                      weekend_trip_share_pct=round(float(we.mean() * 100), 1),
                      same_station_trips=int((t.start_station == t.end_station).sum()),
                      same_station_pct=round(float((t.start_station == t.end_station).mean() * 100), 1)),
        weeks=dict(days_per_iso_week=days_per_wk, complete_weeks=ws,
                   partial_weeks=[w for w, d in days_per_wk.items() if w not in ws],
                   trips_per_complete_week={int(k): int(v) for k, v in t[t.wk.isin(ws)].groupby("wk").size().items()}),
        demand_shape=dict(am_peak_trips=len(am),
                          am_member_share_pct=round(float((am.user_type == "Member").mean() * 100), 1),
                          hub_stations=hubs,
                          am_share_from_hubs_pct_quarter=round(float(am.start_station.isin(hubs).mean() * 100), 1),
                          hub_share_of_all_trips_pct=round(float(t.start_station.isin(hubs).mean() * 100), 1),
                          hourly_departures={int(h): {k: int(v) for k, v in r.items()} for h, r in hourly.iterrows()}),
        hub_net_outflow=dict(members=net(t[t.user_type == "Member"], hubs), casual=net(t[t.user_type == "Casual"], hubs),
                             weekday=net(t[~we], hubs), weekend=net(t[we], hubs)),
        bike_id=dict(consecutive_pairs=len(m), start_elsewhere=int((m.start_station != m.ps).sum()),
                     overlap_in_time=int((m.start_time < m.pe).sum()), distinct_bikes=int(t.bike_id.nunique())),
        stations=dict(capacity_total=int(s.capacity.sum()), regions=s.groupby("region").station.apply(list).to_dict()),
        feedback=dict(by_category=fb.category.value_counts().to_dict(),
                      by_category_polarity={c: {p: int(n) for p, n in g.pol.value_counts().items()} for c, g in fb.groupby("category")},
                      distinct_comment_strings=int(fb.comment_text.nunique()),
                      unknown_strings=sorted(set(fb.comment_text) - set(core.THEMES)),
                      complaints=len(comp), complaints_rated_4_5=int((comp.rating >= 4).sum()),
                      complaint_share_rated_4_5_pct=round(float((comp.rating >= 4).mean() * 100), 1)),
    )


def main(data, out, week=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    t, s, f = core.load(data)
    weeks = core.complete_weeks(t); ws = [w for _, w in weeks]
    target = week or ws[-1]
    tab, _ = core.station_table(t, s, weeks, target)
    hubs = tab[tab.status.str.startswith("RESTOCK")].station.tolist()
    rep = profile(t, s, f, weeks, hubs)
    (out / "eda_report.json").write_text(json.dumps(rep, indent=1, default=str))
    o, d = rep["overview"], rep["demand_shape"]
    print(f"[EDA] {o['trips']} trips {o['first']}..{o['last']} | {o['stations']} stations | {o['feedback_items']} feedback")
    print(f"[EDA] trips/day={o['trips_per_day']} members={o['member_share_pct']}% mean trip={o['mean_duration_min']} min")
    print(f"[EDA] ISO weeks complete={rep['weeks']['complete_weeks']} partial={rep['weeks']['partial_weeks']}")
    print(f"[EDA] 7-10am: {d['am_member_share_pct']}% members; {d['am_share_from_hubs_pct_quarter']}% of departures start at the 6 hub stations")
    print(f"[EDA] hub net outflow: {rep['hub_net_outflow']}")
    print(f"[EDA] bike_id: {rep['bike_id']}")
    print(f"[EDA] feedback: {rep['feedback']['complaints_rated_4_5']} of {rep['feedback']['complaints']} complaints rated 4-5 stars")
    return rep


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
