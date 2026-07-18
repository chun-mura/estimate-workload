---
description: Produce a scientifically-grounded effort estimate (WBS + 3-point + Monte Carlo + reference-class calibration) from any mix of design docs, issues, or free-text requirements, plus codebase analysis. Use when the user asks to estimate effort, workload, or delivery time for described work.
argument-hint: [file paths and/or a description of the work to estimate]
---

# /estimate:new

First read `${CLAUDE_PLUGIN_ROOT}/skills/estimation-methodology/SKILL.md` and
its `references/category-taxonomy.md`, and follow them exactly. Read
`references/ai-assistance-factors.md` only after step 2 confirms the
AI-assisted view is included; `references/worked-example.md` is optional and
normally skipped. CALC below means
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py"`. The history file is
`.estimate/history.jsonl` in the current project. If any CALC call fails, stop
and report its stderr — no freehand fallback — except for the recoverable
run-summary failure inside `pipeline` described in step 7.

Input: $ARGUMENTS (any mix of paths, pasted text, or a short description).

## Steps

1. **Intake.** Check every provided path exists and is readable (a single `ls`
   is enough). Do NOT read document contents into this context — the
   spec-analyzer reads them in full in step 3; reading them twice wastes
   context. For each unreadable or missing path: tell the user, treat it as
   not provided, and carry the gap into step 4.
2. **AI view.** ALWAYS ask, with the AskUserQuestion tool, whether to include
   the AI-assisted effort view (unless the request already states it
   explicitly). If the question goes unanswered, include the view (current
   default behavior). When the view is included, read
   `references/ai-assistance-factors.md` now.
3. **Parallel analysis.** In ONE message dispatch both agents:
   - `estimate:spec-analyzer` with all requirement sources.
   - `estimate:code-analyzer` with the change description — SKIP for
     greenfield (no repo/code).
   If an agent fails (error, timeout, output not matching its JSON contract),
   continue with the other's output, record the failure under Risks, and lower
   the stated confidence. Never silently proceed.
4. **Gap check.** From the agents' `open_questions` and uncertainty notes plus
   any intake gaps: if critical information is missing (scope boundary,
   definition of done, non-functional constraints), ask AT MOST 5 questions in
   one AskUserQuestion call. Skip this step entirely when nothing critical is
   missing. Record every unanswered gap as an assumption; assumptions widen P
   in step 6.
5. **WBS.** Merge per the methodology: spec view defines WHAT, code view
   defines WHERE/HOW HARD (code view wins on difficulty). Produce leaf tasks
   (0.5–3 person-days) each with category (fixed taxonomy) and tags.
6. **Anchored 3-point estimates.** Call CALC `reference-class` (tasks with
   name/category/tags only) to fetch anchors. Assign raw O/M/P per task per
   the methodology, anchored when anchors exist, with a one-line rationale.
7. **Pipeline.** Write ONE payload file (to the scratchpad or a temp path) and
   call CALC `pipeline --input <file>` — a single call that applies
   reference-class corrections, simulates both views, appends history, and
   writes the run summary. Never re-serialize the task list into separate
   per-step calls. Payload:
   - `history_path: ".estimate/history.jsonl"`, `slug` (kebab-case from the
     work's name), and `tasks` — each with `task`, `category`, `tags`, raw
     `o`/`m`/`p`, and `default_factor` (the category's default from
     `references/ai-assistance-factors.md`) when the AI view is included.
   - `ai_view: false` when the user declined the view in step 2 (then
     `default_factor` is not needed).
   - `correlation` and `hours_per_day` from `.estimate/config.json` if
     present, and `size_boundaries` from the same file as `boundaries`;
     otherwise omit each so CALC owns the defaults (`0.3`, `8`, S/M/L).
   The result contains the `run_id` (task ids are `<run_id>-01`, `-02`, … in
   input order), per-task corrected `o`/`m`/`p`/`pert` with each correction's
   `basis`/`low_sample` (or its skip reason), per-task `ai_factor` with its
   `source` (learned factors win over `default_factor` inside CALC — never
   multiply hours yourself), both totals, and the resolved `correlation`.
   If the returned `summary` is `{"error": ...}`, history is already
   authoritative: report the error, omit the summary footer in step 8, and
   continue. Any other failure: stop and report stderr.
8. **Report file.** Write the full report to
   `docs/estimates/YYYY-MM-DD-<slug>.md`, in the conversation language. If
   writing fails, print this full report in chat instead — history is already
   saved. Must contain:
   - WBS table: task, history id, category, O/M/P, expected mean (the `pert`
     value from `pipeline`), rationale. (`/estimate:record` reads ids and
     expected means back from this table — keep the columns.)
   - Legend: one line defining P50 ("as likely over as under; use for internal
     planning") and P80 ("commitment-grade; use for external quotes").
   - Method note: "tasks correlated at rho = X via common-cause factor",
     using the `correlation` returned by `pipeline`.
   - Traditional totals: P50 and P80 in hours AND person-days, using the
     returned `p50_days`/`p80_days` — never divide hours yourself.
   - AI-assisted totals: P50/P80, with each factor's source (learned/default).
     When declined in step 2, replace this section with one line: "AI-assisted
     view: skipped at the user's request."
   - Assumptions, Risks (including any agent failure), Out of scope.
   - Calibration note: which corrections applied (with each one's `basis` and
     a caveat when `low_sample` is set), which were skipped.
   - Footer, only when `summary` succeeded: "Machine-readable summary:
     `.estimate/runs/<run_id>.json`".
   - Footer: "Record actuals when done: `/estimate:record <run_id>`".
   The history file is authoritative; the report is a point-in-time snapshot
   and is never edited afterward.
9. **Chat summary.** Do NOT repeat the full report in chat. Give a compact
   summary: both totals (P50/P80, hours and person-days), the correlation
   note, the P50/P80 legend, the top assumptions and risks, a one-line
   calibration note, the report path, and the `/estimate:record <run_id>`
   footer. Point to the report file for the full WBS table.
