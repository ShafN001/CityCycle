# CityCycle weekly station availability alert

Decision-support workflow: finds stations that persistently run short of bikes (or fill up) and proposes bike moves. Code computes every number; generative AI only classifies feedback by lookup and drafts the brief from facts.json; six gates decide whether a run may continue; a named human approves.

Reproduce: `pip install -r requirements.txt`, add the data (see data/README.md), run `./run_all.sh`.

| Path | What it is |
|---|---|
| docs/work_order.md | Frame: goal, inputs, output, acceptance, limits |
| docs/governance_memo.md | One-page memo (NIST, IMDA, EU AI Act, OWASP) |
| docs/ai_use_log.md | AI-use log: task, prompt, output, verification, judgement |
| prompts/ | Build prompt and brief-drafting prompt |
| src/citycycle_alert.py | Data contract (13 stop checks, 5 warnings), metrics, status rules, move plan, backtest, grounding check |
| src/eda.py | Exploratory data analysis; reproduces every EDA figure in the report |
| src/gates.py | Gate specification (criteria, layer, decider, failure path) and evaluator |
| src/monitor.py | Leakage audit, baselines, held-out split, PSI/KS drift, noise floor, rolling precision |
| src/workflow.py | Orchestrator: ingest, EDA, G1, rules, G3, G2, G5, brief, G4, G6, publish, run_log.json |
| tests/test_workflow.py | Smoke, golden-value and unit tests (pytest); hand-computed fixture plus verified week-13 values |
| src/break_tests.py | 13 attacks and a clean control; each attack must be stopped by a named gate |
| src/verify_independent.py | Recomputes key results from the workbook without the pipeline |
| src/charts.py, src/diagrams.py, src/style.py | Figures (shared style in style.py) |
| outputs_wk13/, outputs_wk8/ | Results for ISO weeks 13 and 8 |

Known limits: one quarter of data; no stock or revenue data; the bike_id column cannot be used to track bikes; feedback has no station field; a frozen list performs as well as the weekly rule on the available weeks.
