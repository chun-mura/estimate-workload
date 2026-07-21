---
description: Produce a scientifically-grounded effort estimate (WBS + 3-point + Monte Carlo + reference-class calibration) from any mix of design docs, issues, or free-text requirements, plus codebase analysis. Use when the user asks to estimate effort, workload, or delivery time for described work.
argument-hint: [--mode quality|economy] [--ai-view|--no-ai-view] [--no-qa] [--id <design-id>] [file paths and/or a description]
---

# /estimate:new

First read `${CLAUDE_PLUGIN_ROOT}/skills/new/references/methodology.md` and
its sibling `category-taxonomy.md`, and follow them exactly. Read
`references/ai-assistance-factors.md` only after step 2 confirms the
AI-assisted view is included. CALC below means
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py"`. The history file is
`.estimate/history.jsonl` in the current project. If any CALC call fails, stop
and report its stderr — no freehand fallback.

Input: $ARGUMENTS (any mix of paths, pasted text, or a short description).

Examples:
- `/estimate:new --mode quality --ai-view docs/spec.md` skips both intake choices.
- `/estimate:new --no-ai-view docs/spec.md` asks only for the mode.
- `/estimate:new --no-qa docs/spec.md` excludes the default QA effort.
- `/estimate:new --id a-ar-001 docs/spec.md` writes a report whose filename
  includes `a-ar-001`.
- `/estimate:new docs/spec.md` keeps the existing mode-and-AI-view question.

Options: before sources, accept `--mode quality|economy`, `--ai-view`,
`--no-ai-view`, `--no-qa`, and `--id <design-id>` in any order. Remove all
recognized options before treating the remainder as sources. Each option may
appear at most once; `--ai-view` and `--no-ai-view` are mutually exclusive.
`--mode quality --ai-view --no-qa --id a-ar-001` is valid. `design-id` must match
`<letters>-<letters>-<three digits or 統合>`, such as `a-ar-001` or
`a-da-統合`; normalize it to lowercase. A missing or invalid `--mode` or
`--id` value, any duplicate (including `--no-qa`) or conflicting option, or an unknown leading
`--...` option is an input error: stop before intake, agent dispatch, or
CALC. Resolve `qa_included` to `false` only when `--no-qa` appears; otherwise
resolve it to `true`. QA is included by default. No other option excludes QA.
With no mode flag, obtain a mode choice in step 2; do not select a mode by
default.

## Steps

1. **Mode-aware intake.** Validate and remove all leading options exactly as
   the Options contract requires, resolving `mode` to `quality`, `economy`, or
   unspecified, `ai_view` to `true`, `false`, or unspecified, `qa_included`
   to `true` unless `--no-qa` was supplied, and `report_id` to the explicit
   normalized ID or unspecified. Then check every remaining provided path
   exists and is readable (a single `ls` is enough), without reading its
   contents. Do NOT read document contents into this context — the
   spec-analyzer reads them in full in step 3; reading them twice wastes
   context. For each unreadable or missing path: tell the user, treat it as
   not provided, and carry the gap into step 4. If `report_id` is unspecified,
   derive it from readable source filenames that begin with
   `<design-id>_`, using the same ID format as the Options contract. If one
   distinct ID is found, normalize and use it. If no ID is found, ask the user
   for one; if multiple distinct IDs are found, ask the user to choose one.
   Do not create a report until `report_id` is resolved.
2. **Mode and AI view.** Ask about AI view only when `ai_view` is unspecified.
   When both `mode` and `ai_view` are unspecified, make exactly one
   AskUserQuestion call that asks both the `quality` versus `economy` mode and
   whether to include the AI-assisted effort view. When only `mode` is
   unspecified, ask only for the mode. When only `ai_view` is unspecified,
   ask only whether to include the AI-assisted effort view. If the mode is
   unanswered, stop and request it; do not choose a default. If an asked
   AI-view answer is unanswered, include it (the existing default behavior).
   When `ai_view` is `true`, read `references/ai-assistance-factors.md` now.
3. **Selected analysis.** Dispatch analyzers once per estimate invocation,
   with the full batch of requirement sources; never dispatch an analyzer in a
   loop over WBS tasks.
   - For `quality`, dispatch `estimate:spec-analyzer` and
     `estimate:code-analyzer` in ONE message, once each.
   - For `economy`, dispatch only `estimate:spec-analyzer` once, and
     explicitly prohibit any codebase scan or ad-hoc repository scan.
   Record only successful analyzer names in `analysis.agents`. In `quality`
   mode, if an agent fails (error, timeout, or output not matching its JSON
   contract), continue with the other output, record the failure under Risks,
   and lower the stated confidence. Never silently proceed. In `economy` mode,
   stop if `spec-analyzer` fails. In `quality` mode, stop if both analyzers
   fail because no valid non-empty `analysis.agents` provenance can be sent to
   the pipeline.
4. **Gap check.** After the selected analysis, use the agents'
   `open_questions` and uncertainty notes plus any intake gaps: if critical
   information is missing (scope boundary, definition of done, non-functional
   constraints), ask AT MOST 5 questions in one AskUserQuestion call. Skip
   this step entirely when nothing critical is missing. Record every
   unanswered gap as an assumption; assumptions widen P in step 6. In
   `economy` mode, collect the fixed general code-impact caveat; apply it to
   the code-affecting WBS tasks only after identifying them in step 5.
5. **WBS.** Merge per the methodology: in `quality`, the spec view defines
   WHAT and the code view defines WHERE/HOW HARD (the code view wins on
   difficulty); in `economy`, use the spec view with the code-impact
   assumptions from step 4. Produce leaf tasks (0.5–3 person-days) with
   concise Japanese verb-first task names, category (fixed taxonomy), and
   tags. Technical identifiers such as API, framework, file, and schema names
   may remain in English. When `qa_included` is true, add applicable
   `test-only` leaf tasks for Test planning and test-case preparation;
   Functional verification in an integrated environment; Integration, E2E, and regression testing; and Defect verification and retesting. Split or
   combine these QA tasks as needed to preserve the 0.5–3 person-day rule.
   Unit tests and in-development checks remain part of implementation tasks
   and must not be counted again as QA. When `qa_included` is false, do not
   add these QA tasks. In `economy` mode, identify the
   code-affecting leaf tasks now and attach the fixed code-impact assumption
   and risk to them for the step 8 report.
6. **Anchored 3-point estimates.** Call CALC `reference-class` (tasks with
   name/category/tags only) to fetch anchors. Assign raw O/M/P per task per
   the methodology, anchored when anchors exist, with a one-line rationale. In
   `economy` mode, for every code-affecting WBS task, widen its raw P for the
   unverified code impact before pipeline correction.
7. **Pipeline.** Write ONE payload file (to the scratchpad or a temp path) and
   call CALC `pipeline --input <file>` — a single call that applies
   reference-class corrections, simulates both views, and appends history.
   Never re-serialize the task list into separate
   per-step calls. Payload:
   - `history_path: ".estimate/history.jsonl"`, `slug` (kebab-case from the
     work's name), and `tasks` — each with `task`, `category`, `tags`, raw
     `o`/`m`/`p`, and `default_factor` (the category's default from
     `references/ai-assistance-factors.md`) when `ai_view` is `true`.
   - `ai_view: false` when `ai_view` is `false` (then
     `default_factor` is not needed).
   - `analysis`: `{ "mode": "quality", "agents": ["spec-analyzer",
     "code-analyzer"] }` when both quality analyzers succeed, or the same
     object with only the successful quality analyzer; economy always uses
     `{ "mode": "economy", "agents": ["spec-analyzer"] }`. Do not invent
     agent names. This is required even when a quality-mode analyzer failed and
     the result is partial.
   - `correlation` and `hours_per_day` from `.estimate/config.json` if
     present; otherwise omit each so CALC owns the defaults (`0.3`, `8`).
   The result contains the `run_id` (task ids are `<run_id>-01`, `-02`, … in
   input order), per-task corrected `o`/`m`/`p`/`pert` with each correction's
   `basis`/`low_sample` (or its skip reason), per-task `ai_factor` with its
   `source` (learned factors win over `default_factor` inside CALC — never
   multiply hours yourself), both totals, the resolved `correlation`, and a
   `simulation` block (`distribution`, `trials`, `correlation`,
   `hours_per_day`, `traditional_seed`, `ai_assisted_seed`) that the report
   quotes as the run's reproduction conditions.
   Any failure: stop and report stderr.
8. **Report file.** Read
   `${CLAUDE_PLUGIN_ROOT}/skills/new/references/report-template.md` and follow
   it exactly — its section order, heading text, and table columns are fixed, so
   that every run produces a structurally identical report. Write to
   `docs/estimates/YYYY-MM-DD-<report_id>-<report_slug>.md`. `report_slug` is
   the kebab-case work name after removing a leading copy of `report_id`, so
   the ID appears exactly once in the filename. If removing the ID leaves no
   name, use only `YYYY-MM-DD-<report_id>.md`. If writing fails, print the
   full report in chat instead — history is already saved.
   Before writing, confirm every number and id in the report came from the
   `pipeline` result of step 7: totals from `traditional`/`ai_assisted`
   (including `p50_days`/`p80_days` — never divide hours yourself), per-task
   `pert`, and the full task ids used verbatim in the 履歴ID column.
   Never compute, round, or invent any of them. The report's reproduction
   values come directly from `pipeline.simulation`. If `pipeline` did not
   return a `run_id`, do NOT write a report at all — report the failure and stop.
   In `## 見積もり手法`, include exactly `- 解析モード: quality` or
   `- 解析モード: economy`, copied from `pipeline.analysis.mode`. For an
   `economy` report, include these exact entries in their designated sections:

   When `qa_included` is true, `## 前提条件` must state that QA is included by
   default and list Test planning and test-case preparation; Functional
   verification in an integrated environment; Integration, E2E, and regression testing; and Defect verification and retesting. When `qa_included` is false,
   `## スコープ外` must state that `--no-qa` excluded those same four QA
   activities.

   Read `references/economy-report-boilerplate.md` and copy its exact blocks
   into the designated report sections.
   The history file is authoritative; the report is a point-in-time snapshot
   and is never edited afterward.
9. **Chat summary.** Do NOT repeat the full report in chat. Give a compact
   summary: both totals (P50/P80, hours and person-days), the correlation
   note, the P50/P80 legend, the top assumptions and risks, a one-line
   calibration note, the report path, and the `/estimate:record <run_id>`
   footer. Point to the report file for the full WBS table.
