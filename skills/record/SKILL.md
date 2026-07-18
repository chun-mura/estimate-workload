---
description: Record actual hours against a previous /estimate:new run and show calibration (estimate vs actual bias). Use when the user reports completed work, actual time spent, or asks to log actuals.
argument-hint: [run_id (optional) — the id printed by /estimate:new]
---

# /estimate:record

CALC means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py"`. History
is `.estimate/history.jsonl` in the current project. Never read, parse, or
edit that file directly — writes happen only through CALC `update-actual`,
and splits only through CALC `distribute`. If a CALC call fails, stop and
report its stderr.

Input: $ARGUMENTS (optionally a run_id).

## Steps

1. **Identify the run.** Use the run_id from $ARGUMENTS. If absent, ask the
   user for it — it is printed in the footer of the estimate report under
   `docs/estimates/` (the user can also paste the report path; read the
   report file, not the history file, to find the run_id and task ids).
2. **Collect actuals.** For the run's tasks (ids `<run_id>-01`, `-02`, …, as
   listed in the report): ask the user for actual hours per task. If they only
   know the run total, call CALC `distribute` with the total and the tasks'
   `id`/`pert` values from the report, show the proposed split, and let the
   user adjust before writing. Also ask whether the work was AI-assisted
   (one answer per task, or one for the whole run).
3. **Write.** For each task: CALC `update-actual --history-path
   .estimate/history.jsonl --id <task-id> --actual <hours> --ai-assisted
   true|false`. Report each success or failure as it happens; an unknown id
   error usually means a typo in the run_id.
4. **Calibrate.** CALC `calibration` and present, in the conversation
   language: overall bias (under/over-estimating), ratio_p50, per-category
   ratios, and any learned AI-assistance factors now active. Where the output
   carries `low_sample: true`, say the figure is indicative only. Encourage
   recording actuals every run — corrections activate at 5 similar completed
   records per category and firm up around 10.
