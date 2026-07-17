---
description: Produce a scientifically-grounded effort estimate (WBS + 3-point + Monte Carlo + reference-class calibration) from any mix of design docs, issues, or free-text requirements, plus codebase analysis. Use when the user asks to estimate effort, workload, or delivery time for described work.
argument-hint: [file paths and/or a description of the work to estimate]
---

# /estimate:new

First read `${CLAUDE_PLUGIN_ROOT}/skills/estimation-methodology/SKILL.md` and its
`references/` files, and follow them exactly. CALC below means
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py"`. The history file is
`.estimate/history.jsonl` in the current project. If any CALC call fails, stop
and report its stderr — no freehand fallback.

Input: $ARGUMENTS (any mix of paths, pasted text, or a short description).

## Steps

1. **Intake.** Read every provided document. For each unreadable or missing
   path: tell the user, treat it as not provided, and carry the gap into
   step 2.
2. **Gap check.** If critical information is missing (scope boundary,
   definition of done, non-functional constraints), ask AT MOST 5 questions
   with the AskUserQuestion tool. Record every unanswered gap as an assumption;
   assumptions widen P in step 5.
3. **Parallel analysis.** In ONE message dispatch both agents:
   - `estimate:spec-analyzer` with all requirement sources.
   - `estimate:code-analyzer` with the change description — SKIP for
     greenfield (no repo/code).
   If an agent fails (error, timeout, output not matching its JSON contract),
   continue with the other's output, record the failure under Risks, and lower
   the stated confidence. Never silently proceed.
4. **WBS.** Merge per the methodology: spec view defines WHAT, code view
   defines WHERE/HOW HARD (code view wins on difficulty). Produce leaf tasks
   (0.5–3 person-days) each with category (fixed taxonomy) and tags.
5. **Anchored 3-point estimates.** Call CALC `reference-class` (tasks with
   name/category/tags only) to fetch anchors. Assign O/M/P per task per the
   methodology, anchored when anchors exist, with a one-line rationale.
6. **Correction.** Call CALC `reference-class` again, now including each
   task's `o`, `m`, and `p`. Where it returns corrected values
   (`corrected_o`/`corrected_m`/`corrected_p`), use them.
   Where skipped, note "uncorrected (insufficient data: N similar records)".
7. **Aggregate.** Build the CALC `simulate` payload with the final O/M/P
   values. If `.estimate/config.json` contains `correlation`, add that value
   to the payload; otherwise omit it so CALC owns the `0.3` default. Then build
   the AI-assisted view: call CALC `simulate` again with the same correlation
   override behavior and tasks plus a per-task `"factor"` — the category's
   learned factor (from CALC `calibration`) when available, else the default
   from the methodology references. The script does the scaling; never
   multiply hours yourself. Use the returned `correlation` from both calls
   and stop with a CALC error if the returned values differ.
8. **Persist — history FIRST, report second.**
   1. CALC `append-history` with slug (kebab-case from the work's name) and
      the final tasks. Keep the returned `run_id` and ids.
   2. Write the report to `docs/estimates/YYYY-MM-DD-<slug>.md`. If writing
      fails, print the full report in chat instead — history is already saved.
9. **Report.** In the conversation language. Must contain:
   - WBS table: task, history id, category, O/M/P, PERT mean (from
     `simulate`), rationale. (`/estimate:record` reads ids and PERT means
     back from this table — keep the columns.)
   - Legend: one line defining P50 ("as likely over as under; use for internal
     planning") and P80 ("commitment-grade; use for external quotes").
   - Method note: "tasks correlated at rho = X via common-cause factor",
     using the correlation value returned by CALC `simulate`.
   - Traditional totals: P50 and P80 in hours AND person-days (8 h/day unless
     `.estimate/config.json` sets `hours_per_day`).
   - AI-assisted totals: P50/P80, with each factor's source (learned/default).
   - Assumptions, Risks (including any agent failure), Out of scope.
   - Calibration note: which corrections applied, which were skipped.
   - Footer: "Record actuals when done: `/estimate:record <run_id>`".
   The history file is authoritative; the report is a point-in-time snapshot
   and is never edited afterward.
