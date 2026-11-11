# Governance memo: CityCycle weekly station availability alert

To: Head of Operations. Version 1 (week-13 run). Lenses: NIST AI RMF + GenAI profile, IMDA Model AI Governance Framework, EU AI Act (reference), OWASP LLM Top 10.

## 1 What it is for?

- The system ranks our 20 stations each week by how many more bikes leave than arrive, and suggests bike moves.
- It may not dispatch bikes, set prices, assess staff or use rider-level data.

*Lens: NIST Map*

## 2 What could go wrong?

- It is decision support: moderate impact, low cost and reversible (bikes can be moved back by van).
- EU AI Act (reference only): minimal risk, as no decision is about a person; re-check with counsel if used for staffing or pricing.
- Main risks:
- A wrong number from the AI because of hallucination;
- Bad data unnoticed;
- The method is weaker than it looks, since a fixed list does as well;
- It favours weekday commuter stations (members' net outflow 949 against -35 for casual riders), so weekend and casual areas may be overlooked;
- Trip times and bike IDs could identify riders (PDPA);
- Text hidden in feedback tries to instruct the AI (prompt injection);
- People over-trust it or give it too much power.

*Lens: NIST · EU · OWASP*

## 3 Who is responsible; where people stay in?

- The Head of Operations approves each brief.
- The operations analyst owns the code, thresholds and comment themes.
- A PDPA lead handles any privacy incident.
- Humans stay in the loop for:
- Thresholds and themes (business judgement);
- Warnings and odd patterns (morning departures from business-area stations;
- The data cannot confirm direction);
- Borderline stations (about one flag in three does not persist);
- Dispatch (it costs money, and the system sees pressure, not causes);
- And new kinds of feedback text (untested).

*Lens: NIST Govern · IMDA*

## 4 Safeguards

- The data check stops the run on 13 kinds of failure.
- The AI sees only summary results, never trip rows or feedback text; comments are matched against a reviewed list, so injected text stops the run.
- Every number, table row and move in the brief is checked against the results.
- Access is read-only, with no power to dispatch.
- Counts below 5 are hidden before sharing outside operations.
- No AI training on our inputs.

*Lens: IMDA · OWASP*

## 5 Evidence

- 25 automated tests pass and 58 independent recalculations match.
- 13 of 13 attacks were caught, and a clean run publishes.
- The rule never uses future data.
- Flags held up 68% of the time (65% on weeks held back) against 21% by chance and 58% for “same as last week”.
- Limits: one quarter of data, no stock or revenue data, and a fixed list does as well.

*Lens: NIST Measure · EU*

## 6 How we will watch it?

- Each week check:
- Has the pattern changed (trips up or down 20%, member share moving 10 points, shifts in station mix, unseen feedback text)?
- Of last week's flags, how many held?
- Review if under 50% for four weeks.
- How often does the Head of Operations override?
- Review if above one in three.
- Each quarter: rerun the comparisons and leakage tests; seasons are untested.

*Lens: NIST Manage · IMDA*

## 7 If it fails

- The analyst switches the alert off and the team returns to the manual checklist.
- The Head of Operations decides when to relaunch.
- The analyst keeps the AI-use log as the work happens.

*Lens: All four*

Recommendation: approve for weekly use with human approval retained; review thresholds, baselines and drift limits at quarter end.
