# Work order: weekly station availability alert (H-SAAF step 1, Frame)
1. Goal and intended user: tell the Head of Operations every Monday which stations are persistently short of bikes or docks and where bikes could move from. Decision: which bikes to move this week.
2. Inputs and definitions: trips, stations, feedback files. Net outflow = departures minus arrivals per station per complete ISO week, as % of dock capacity. RESTOCK = 4-week mean at or above 40% of docks; SURPLUS = at or below -25%. Feedback themes come from a reviewed table.
3. Output and format: one-page brief (priority table, proposed moves, what feedback corroborates, warnings, open decisions) labelled DRAFT until approved; facts.json; run_log.json.
4. Acceptance criteria: gates G1-G6 pass (see src/gates.py); independent recomputation matches; every number, table row and move in the brief matches facts.json; named approver.
5. Limits and approvals: read-only data access; no dispatch; no personal data sent to the model; Head of Operations approves; stop and ask on any ambiguous definition.
Risk tier: medium. Verification layers: L1-L3 every run; adversarial attacks (break_tests.py) on every code change. Skipped layer: none.
