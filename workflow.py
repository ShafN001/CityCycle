"""Orchestrator: the CityCycle weekly availability workflow, end to end, with gates.

    python3 -I workflow.py --data DATA --out OUT [--week 13] [--brief brief.md] [--approved-by NAME]

H-SAAF mapping (week 2):  Frame -> work_order.md | Decompose -> the steps below | Contextualise -> config + THEMES
  Delegate/Execute -> agents (functions) + the drafting prompt | VERIFY -> G1..G5 | Integrate -> publish
  Govern -> G6 + governance_memo.md | Communicate -> the brief.

The code computes every number. The generative-AI step only drafts the brief from facts.json
(see prompts/brief_prompt.md), is checked by G4, and is never published without G6.
"""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citycycle_alert as core
import eda, monitor, gates
from gates import gate, log, GateStop


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def evidence_verification(tab, moves, need, give):
    moved = sum(m["bikes"] for m in moves if not m["from_station"].startswith("("))
    unmet = sum(m["bikes"] for m in moves if m["from_station"].startswith("("))
    used = {}
    for m in moves:
        if not m["from_station"].startswith("("): used[m["from_station"]] = used.get(m["from_station"], 0) + m["bikes"]
    restock = [r.station for r in tab.itertuples() if r.status.startswith("RESTOCK")]
    receivers = {m["to_station"] for m in moves}
    return dict(net_sum=int(tab.net_outflow.sum()), need_total=int(sum(need.values())), moved=int(moved), unmet=int(unmet),
                donor_overdrawn=sum(1 for k, v in used.items() if v > give.get(k, 0)),
                restock_without_move=len([s for s in restock if s not in receivers]))


def run_workflow(data, out, week=None, brief=None, approved_by=None, skip_gates=False, history=True):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    gates.LOG.clear()
    open_holds = []
    # ---- 1 Ingest (data agent)
    t, s, f = core.load(data)
    log("1_ingest", dict(trips=len(t), stations=len(s), feedback=len(f),
                         sha_trips=sha(Path(data) / "trips.csv"), sha_stations=sha(Path(data) / "stations.csv"),
                         sha_feedback=sha(Path(data) / "feedback.csv")))
    # ---- 2 EDA (profiling proposes; humans interpret)
    weeks = core.complete_weeks(t); ws = [w for _, w in weeks]
    target = week or ws[-1]
    assert target in ws, f"week {target} is not a complete week; choose from {ws}"
    tab0, _ = core.station_table(t, s, weeks, target)
    hubs = tab0[tab0.status.str.startswith("RESTOCK")].station.tolist()
    rep = eda.profile(t, s, f, weeks, hubs)
    (out / "eda_report.json").write_text(json.dumps(rep, indent=1, default=str))
    log("2_eda", dict(trips_per_day=rep["overview"]["trips_per_day"], member_share_pct=rep["overview"]["member_share_pct"],
                      partial_weeks=rep["weeks"]["partial_weeks"], complete_weeks=len(ws),
                      am_share_from_hubs_pct=rep["demand_shape"]["am_share_from_hubs_pct_quarter"]))
    # ---- 3 G1 data contract (13 stop checks + 5 warnings)
    res = core.validate(t, s, f)
    fails = [g for g in res if g["status"] == "FAIL"]; warns = [g for g in res if g["status"] == "WARN"]
    gate("G1_data_contract", dict(fails=len(fails), unknown_strings=rep["feedback"]["unknown_strings"], warns=len(warns)), skip_gates)
    log("3_warnings", dict(n_warn=len(warns), notable_notes=[w["check"] for w in warns]))
    # ---- 4 metrics, status rules, move plan, feedback (code)
    t, s, f, weeks, tab, facts = core.run(data, out, target)
    moves, need, give = core.move_plan(tab)
    log("4_rules_and_moves", dict(restock=int(tab.status.str.startswith("RESTOCK").sum()),
                                  surplus=int(tab.status.str.startswith("SURPLUS").sum()), bikes_to_move=facts["total_bikes_to_move"]))
    # ---- 5 monitor evidence first (written to monitor.json so independent verification can check it)
    ev2, base, split = monitor.leakage_audit(t, s, f, weeks, target)
    # ---- 7 G5 drift (L3) + rolling precision
    drows, ref_w = monitor.drift_report(t, s, f, weeks, target)
    floor = monitor.noise_floor(t, s, f, weeks)
    roll = monitor.rolling_flag_precision(t, s, weeks, target)
    n_drift = sum(r["status"] == "DRIFT" for r in drows); n_watch = sum(r["status"] == "WATCH" for r in drows)
    mon = dict(week=target, leakage=ev2, baselines=base, selection_split=split, drift=drows, drift_reference_weeks=ref_w,
               noise_floor=floor, rolling_flag_precision=roll, thresholds=monitor.MONITOR)
    (out / "monitor.json").write_text(json.dumps(mon, indent=1, default=str))
    pd.DataFrame(drows).to_csv(out / f"drift_wk{target}.csv", index=False)
    # ---- 6 gates in order: G3 verification (L2), G2 leakage (L3), G5 drift (L3)
    ev3 = evidence_verification(tab, moves, need, give)
    xlsx = Path(data) / "data.xlsx"
    if xlsx.exists():
        monitor_json = out / "monitor.json"
        p = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve().parent / "verify_independent.py"),
                            str(data), str(out / "facts.json"), str(target)] + ([str(monitor_json)] if monitor_json.exists() else []),
                           capture_output=True, text=True)
        (out / "verify_independent.txt").write_text(p.stdout)
        ev3["independent_pass"] = "ALL INDEPENDENT CHECKS PASS" in p.stdout
        ev3["independent_checks"] = p.stdout.count("PASS ") - p.stdout.count("ALL INDEPENDENT")
    gate("G3_verification", ev3, skip_gates)
    gate("G2_leakage_baselines", ev2, skip_gates)
    g5 = gate("G5_drift", dict(n_drift=n_drift), skip_gates)
    if not g5["passed"]: open_holds.append("G5_drift")
    log("7_monitor", dict(reference_weeks=f"{ref_w[0]}-{ref_w[-1]}", n_drift=n_drift, n_watch=n_watch,
                          flag_precision_last_week=(roll or {}).get("precision"), notable_notes=[r["metric"] for r in drows if r["status"] != "OK"]))
    if history:   # weekly scorecard history, one row per week 4..target (computed on data up to that week only)
        rows = []
        for w in [x for x in ws if x >= ws[monitor.TW]]:
            if w > target: break
            d, _ = monitor.drift_report(t, s, f, weeks, w); r = monitor.rolling_flag_precision(t, s, weeks, w) or {}
            rows.append(dict(week=w, drift=sum(x["status"] == "DRIFT" for x in d), watch=sum(x["status"] == "WATCH" for x in d),
                             flagged_last_week=r.get("flagged"), still_over=r.get("still_over"), flag_precision=r.get("precision")))
        pd.DataFrame(rows).to_csv(out / "scorecard_history.csv", index=False)
    # ---- 8 Brief (generative AI drafts from facts.json only)
    prompt = (Path(__file__).resolve().parent.parent / "prompts" / "brief_prompt.md")
    if brief is None or not Path(brief).exists():
        log("8_brief", dict(status="AWAITING_BRIEF", instruction="give prompts/brief_prompt.md + facts.json to the model, save the draft, rerun with --brief"))
        gates.write_log(out / "run_log.json", dict(week=target, status="AWAITING_BRIEF", skip_gates=skip_gates)); return "AWAITING_BRIEF"
    text = Path(brief).read_text()
    # ---- 9 G4 grounding (numbers, rows and moves)
    bad = core.ground_check(text, facts)
    tm, mm = gates.table_and_move_checks(text, facts)
    g4 = gate("G4_grounding", dict(ungrounded_numbers=bad, table_mismatches=tm, move_mismatches=mm,
                                   draft_label="DRAFT - requires ops-lead approval" in text), skip_gates)
    if not g4["passed"]: open_holds.append("G4_grounding")
    # ---- 10 G6 human approval -> publish
    g6 = gate("G6_human_approval", dict(approved_by=approved_by, open_holds=open_holds), skip_gates)
    status = "PUBLISHED" if g6["passed"] and not skip_gates else "HELD_FOR_APPROVAL"
    if status == "PUBLISHED":
        stamp = f"**APPROVED by {approved_by}** (week {target}). Drift watch items: {n_watch}.\n\n"
        (out / f"published_brief_wk{target}.md").write_text(stamp + text)
    log("10_publish", dict(status=status, approved_by=approved_by or "(none)", open_holds=",".join(open_holds) or "none"))
    gates.write_log(out / "run_log.json", dict(week=target, status=status, skip_gates=skip_gates,
                                               verification="UNVERIFIED" if skip_gates else "gates evaluated"))
    return status


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--week", type=int); ap.add_argument("--brief"); ap.add_argument("--approved-by")
    ap.add_argument("--skip-gates", action="store_true", help="NOT for production: stamps the run UNVERIFIED")
    a = ap.parse_args()
    try:
        st = run_workflow(a.data, a.out, a.week, a.brief, a.approved_by, a.skip_gates)
        print("\nRUN STATUS:", st)
    except GateStop as e:
        gates.write_log(Path(a.out) / "run_log.json", dict(status="STOPPED", reason=str(e)))
        print("\nRUN STOPPED:", e); sys.exit(2)
