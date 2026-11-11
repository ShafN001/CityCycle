"""Gate specifications and the gate() evaluator (seminar pattern: criteria + failure_path + evidence log).

A gate does not mean "the step finished". It means "the step produced evidence that satisfies
the criteria". Each gate states (a) criteria, (b) its verification layer L1-L4, (c) who decides
(auto or human) and (d) what happens on failure. No gate is silently skippable: skip_gates=True
is recorded in the log and the run is stamped UNVERIFIED.
"""
import re, json, datetime as dt

LOG = []


def log(step, evidence):
    LOG.append({"step": step, "evidence": evidence})
    brief = ", ".join(f"{k}={v}" for k, v in evidence.items() if k != "notable_notes" and not isinstance(v, (list, dict)))
    print(f"[{step}] {brief}")


class GateStop(Exception):
    """Raised when a STOP gate fails: nothing downstream may run."""


GATES = {
    "G1_data_contract": dict(
        layer="L1 lexical", decider="auto", on_fail="stop",
        criteria={
            "no FAIL-level contract check (schema, nulls, keys, time logic, ranges)": lambda e: e["fails"] == 0,
            "every feedback string is in the reviewed theme table": lambda e: not e["unknown_strings"],
        },
        failure_path="STOP. Nothing downstream runs. Analyst fixes the source or the contract. "
                     "Unrecognised feedback text is routed to a human and is never passed to the model."),
    "G2_leakage_baselines": dict(
        layer="L3 distributional", decider="auto", on_fail="stop",
        criteria={
            "look-ahead: status unchanged when all later trips are deleted": lambda e: e["look_ahead_status_unchanged_when_future_deleted"],
            "no trip after the week-end was read": lambda e: not e["latest_trip_used_after_week_end"],
            "no duplicate trip ids or rows (train-test contamination)": lambda e: e["duplicate_trip_ids"] == 0 and e["duplicate_rows"] == 0,
            "rule chosen on early weeks, scored on disjoint later weeks": lambda e: e["selection_split_disjoint"],
            "no single rule looks too good (precision below the leakage-suspect level)": lambda e: e["best_rule_precision"] < e["leak_suspect_threshold"],
            "held-out precision beats chance (when the held-out weeks raise any flag)": lambda e: (not e["held_out_flagged"]) or e["held_out_beats_chance"],
        },
        failure_path="STOP. Do not quote the backtest. Investigate the join, feature or split that leaks "
                     "before any precision figure is reported."),
    "G3_verification": dict(
        layer="L2 behavioural", decider="auto", on_fail="stop",
        criteria={
            "net flows across all stations sum to zero": lambda e: e["net_sum"] == 0,
            "bikes needed = bikes moved + unmet (conservation)": lambda e: e["need_total"] == e["moved"] + e["unmet"],
            "no donor gives more than its capacity": lambda e: e["donor_overdrawn"] == 0,
            "every RESTOCK station has a receiving move": lambda e: e["restock_without_move"] == 0,
            "independent recomputation matches (verify_independent.py)": lambda e: e.get("independent_pass", True),
        },
        failure_path="STOP. Recompute independently from the raw file; do not generate a brief from facts that fail."),
    "G4_grounding": dict(
        layer="L2 behavioural", decider="auto", on_fail="retry_then_human",
        criteria={
            "every number in the brief exists in facts.json": lambda e: not e["ungrounded_numbers"],
            "every priority-table row matches the station table exactly": lambda e: not e["table_mismatches"],
            "every proposed move matches the move plan exactly": lambda e: not e["move_mismatches"],
            "brief is labelled DRAFT - requires ops-lead approval": lambda e: e["draft_label"],
        },
        failure_path="Return the brief to the drafter with the mismatches (max 2 retries); then a human writes it. "
                     "A brief that fails is never shown to the ops lead as final."),
    "G5_drift": dict(
        layer="L3 distributional", decider="human", on_fail="human",
        criteria={
            "no drift metric in DRIFT (PSI > 0.25, volume +/-20%, member share +/-10pp, KS p<0.01, unseen strings)": lambda e: e["n_drift"] == 0,
        },
        failure_path="HOLD for the ops lead: decide whether the pattern changed (re-baseline thresholds and theme table) "
                     "or the data broke (stop and fix). WATCH items are reported in the brief header."),
    "G6_human_approval": dict(
        layer="human", decider="human", on_fail="hold",
        criteria={
            "an accountable approver is named": lambda e: bool(e["approved_by"]),
            "no unresolved gate hold": lambda e: not e["open_holds"],
        },
        failure_path="HOLD. Nothing is published or dispatched. The system never moves a bike."),
}


def gate(name, evidence, skip_gates=False):
    """Evaluate criteria against evidence; log; follow the failure path."""
    spec = GATES[name]
    if skip_gates:
        log(name, {"result": "SKIPPED", "warning": "skip_gates=True -> run is UNVERIFIED"})
        return dict(gate=name, passed=False, skipped=True, failed=[])
    failed = [c for c, fn in spec["criteria"].items() if not fn(evidence)]
    passed = not failed
    log(name, {"layer": spec["layer"], "decider": spec["decider"], "result": "PASS" if passed else "FAIL", "failed": failed,
               "on_fail": spec["on_fail"] if not passed else "", "failure_path": spec["failure_path"] if not passed else ""})
    if not passed and spec["on_fail"] == "stop":
        raise GateStop(f"{name}: " + "; ".join(failed) + f" -> {spec['failure_path']}")
    return dict(gate=name, passed=passed, skipped=False, failed=failed, on_fail=spec["on_fail"])


# --------------------------------------------------------------------- brief checks used by G4
def table_and_move_checks(text, facts):
    """Row-level checks: a number can exist in facts yet sit against the wrong station. Compare rows exactly."""
    by = {r["station"]: r for r in facts["stations"]}
    mism = []
    for ln in text.splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and len(cells) == 6 and cells[0].isdigit():
            rank, st, docks, mean, wk, status = cells
            r = by.get(st)
            if r is None:
                mism.append(f"unknown station {st}"); continue
            exp = (str(r["rank"]), str(r["capacity"]), f"{r['net_pct_4wk_mean']}", f"{r['net_pct_this_week']}", r["status"].split()[0])
            got = (rank, docks, mean, wk, status.split()[0])
            if exp != got: mism.append(f"{st}: brief {got} vs facts {exp}")
    shown = set(re.findall(r"(?:(?<=: )|(?<=, ))([A-Z][\w\- ]+?) to ([A-Za-z][\w\- ]+?) \((\d+)\)", text))
    plan = {(m["from_station"], m["to_station"], str(m["bikes"])) for m in facts["moves"] if not m["from_station"].startswith("(")}
    move_mism = sorted([f"in brief, not in plan: {m}" for m in shown - plan] + [f"in plan, not in brief: {m}" for m in plan - shown])
    return mism, move_mism


def write_log(path, extra=None):
    out = {"written_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "steps": LOG}
    if extra: out.update(extra)
    with open(path, "w") as fh: json.dump(out, fh, indent=1, default=str)
