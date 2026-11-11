#!/usr/bin/env bash
# Reproduce every number and figure in the report. Put trips.csv, stations.csv, feedback.csv, data.xlsx in ./data first.
set -e
mkdir -p outputs_wk13
python3 -m pytest -q tests | tee outputs_wk13/pytest_output.txt                                  # smoke, golden and unit tests (L2)
python3 -I src/workflow.py --data data --out outputs_wk13 --brief outputs_wk13/brief_wk13.md   # G1-G6, EDA, leakage, drift, independent check
python3 -I src/workflow.py --data data --out outputs_wk8 --week 8                              # rerun for another week, no code change
python3 -I src/charts.py data outputs_wk13 13                                                  # figures 1-3
python3 -I src/diagrams.py outputs_wk13 outputs_wk13/eda_report.json                           # workflow, H-SAAF, build-break-defend, governance, EDA figure
python3 -I src/break_tests.py data outputs_wk13/brief_wk13.md outputs_wk13/break_tests_result.json | tee outputs_wk13/break_tests_output.txt
# To approve and publish: add  --approved-by "Name"  to the first command.
