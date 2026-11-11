"""Independent re-computation of key results: openpyxl + collections only (no pandas, no pipeline code), from the XLSX copy."""
import json, sys, datetime as dt
from collections import Counter, defaultdict
from openpyxl import load_workbook
DATA = sys.argv[1] if len(sys.argv) > 1 else 'data'
FACTS = sys.argv[2] if len(sys.argv) > 2 else 'out/facts.json'
WEEK = int(sys.argv[3]) if len(sys.argv) > 3 else 13
wb = load_workbook(DATA + '/data.xlsx', read_only=True, data_only=True)
def rows(n):
    it = wb[n].iter_rows(values_only=True); h = next(it); return [dict(zip(h, r)) for r in it]
T, S, F = rows('trips'), rows('stations'), rows('feedback')
cap = {r['station']: r['capacity'] for r in S}
def p(x): return x if isinstance(x, dt.datetime) else dt.datetime.fromisoformat(str(x))
dep, arr = defaultdict(Counter), defaultdict(Counter)
am_hub = am_all = 0; wk_trips = 0
facts = json.load(open(FACTS))
hubs = [r['station'] for r in facts['stations'] if r['status'].startswith('RESTOCK')]
for r in T:
    s = p(r['start_time']); w = s.isocalendar()[1]
    dep[w][r['start_station']] += 1; arr[w][r['end_station']] += 1
    if w == WEEK:
        wk_trips += 1
        if 7 <= s.hour < 10:
            am_all += 1; am_hub += r['start_station'] in hubs
def pct(w, st): return (dep[w][st] - arr[w][st]) / cap[st] * 100
ok = True
def chk(name, a, b, tol=0.06):
    global ok; good = abs(a - b) <= tol; ok &= good; print(('PASS' if good else 'FAIL'), name, round(a, 2), round(b, 2))
chk('total trips', len(T), facts['quarter']['trips'], 0)
chk('week13 trips', wk_trips, facts['week']['trips'], 0)
chk('AM-peak share from urgent stations (%)', am_hub / am_all * 100, facts['week']['am_peak_share_from_urgent_stations_pct'])
for r in facts['stations']:
    st = r['station']
    chk(f'{st} wk{WEEK} net outflow', dep[WEEK][st] - arr[WEEK][st], r['net_outflow'], 0)
    chk(f'{st} 4wk mean %', sum(pct(w, st) for w in range(WEEK - 3, WEEK + 1)) / 4, r['net_pct_4wk_mean'])
chk(f'net flows sum to zero (wk{WEEK})', sum(dep[WEEK][s] - arr[WEEK][s] for s in cap), 0, 0)
need_t, cap_t = sum(facts['restock_need_bikes_per_week'].values()), sum(facts['donor_capacity_bikes_per_week'].values())
chk('donor capacity covers restock need (need, min(need, capacity))', need_t, min(need_t, cap_t), 0)
chk('bikes moved == need', sum(m['bikes'] for m in facts['moves']), sum(facts['restock_need_bikes_per_week'].values()), 0)
# feedback
comp = Counter(r['comment_text'] for r in F)
fb = facts['feedback']
chk('morning no-bikes', comp['no bikes available at my station in the morning'], fb['morning_no_bikes'], 0)
chk('peak no-bikes', comp['hard to find a bike at peak hour'], fb['peak_no_bikes'], 0)
chk('docks full', comp["docks were all full, couldn't return"], fb['docks_full'], 0)
chk('Bishan praise', comp['always bikes at Bishan, great'], fb['bishan_praise'], 0)
chk('Availability items', sum(r['category'] == 'Availability' for r in F), fb['availability_category_items'], 0)
# rule B backtest, re-implemented
hit = flg = act = 0
for i, w in enumerate(range(5, 13)):   # need 4 trailing weeks (2-5 .. 9-12), outcome in w+1
    for st in cap:
        f = sum(pct(x, st) for x in range(w - 3, w + 1)) / 4 >= 40
        n = pct(w + 1, st) >= 40
        flg += f; act += n; hit += f and n
chk('backtest precision (rule B)', hit / flg, facts['backtest']['B_4wk_mean']['precision'], 0.006)
chk('backtest recall (rule B)', hit / act, facts['backtest']['B_4wk_mean']['recall'], 0.006)

# ---- baselines and held-out score (monitor.json), recomputed from the raw rows
import os
MON = sys.argv[4] if len(sys.argv) > 4 else None
if MON and os.path.exists(MON):
    mon = json.load(open(MON)); b = mon['baselines']; sp = mon['selection_split']
    ws = list(range(2, 14))
    P = {w: {st: pct(w, st) for st in cap} for w in ws}
    def score(idxw, flag):
        tp = fl = ac = 0
        for w in idxw:
            for st in cap:
                f_, o = flag(w, st), P[w + 1][st] >= 40
                tp += f_ and o; fl += f_; ac += o
        return tp, fl, ac
    ev = list(range(5, 13))
    tp, fl, ac = score(ev, lambda w, st: P[w][st] >= 40)
    chk('persistence precision', tp / fl, b['persistence']['precision'], 0.006)
    chk('base rate (chance precision)', ac / (len(ev) * len(cap)), b['base_rate'], 0.006)
    mean4 = lambda w, st: sum(P[x][st] for x in range(w - 3, w + 1)) / 4 >= 40
    frozen_set = {st for st in cap if sum(P[x][st] for x in range(2, 6)) / 4 >= 40}
    tp, fl, ac = score(range(9, 13), lambda w, st: st in frozen_set)
    chk('frozen-list precision', tp / fl, b['frozen_list']['precision'], 0.006)
    tp, fl, ac = score([w for w in range(5, 13) if w + 1 > 8 and w > 7], mean4)
    chk('held-out precision (rule chosen on weeks<=8, scored on outcome weeks 9-13)', tp / fl, sp['held_out']['precision'], 0.006)
    chk('held-out flags', fl, sp['held_out']['flagged'], 0)
print('\nALL INDEPENDENT CHECKS PASS' if ok else '\nSOME CHECKS FAILED')
