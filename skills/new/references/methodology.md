# Estimation Methodology

## Non-negotiable rules

1. **No freehand math.** Every aggregation, percentile, ratio, or correction is computed by `${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py`. If the script fails, stop and report the error — never substitute your own arithmetic.
2. **No freehand history edits.** `.estimate/history.jsonl` is only ever written by the script's `append-history` and `update-actual` subcommands. Never Read the raw file to make decisions when a subcommand can answer instead; never Write or Edit it.
3. **Show your uncertainty.** Estimates are ranges (P50/P80), never single numbers. Every assumption that widened a range is listed in the report.

## WBS and 3-point estimates

- Decompose only into applicable delivery phases; leaf tasks are roughly 0.5–3 person-days (4–24 hours). Split larger tasks.
- Every task has a concise Japanese verb-first name, one category from `category-taxonomy.md`, and 1–4 lowercase tags. Keep useful technical identifiers unchanged.
- **O:** known path with no rework; hard lower bound. **M:** most probable outcome including normal friction. **P:** serious-but-plausible trouble; hard upper bound, not a catastrophe bound.
- Give each task a one-line complexity rationale. Anchor O/M/P to similar actuals when available. Unanswered scope gaps become assumptions and widen P.

## Analysis and reference class

`quality` uses both requirement and codebase analyses; `economy` uses requirements only and must not substitute a codebase scan. Widen raw P for every code-affecting economy task and do not claim evidence of repository impact.

Before O/M/P, call `reference-class` with category/tags. `pipeline` applies ratio corrections; report corrected values when a correction applies, otherwise state `insufficient_data`. Surface each correction's `basis` and `low_sample` status.

## Aggregation and views

`pipeline` simulates corrected O/M/P. **P50** is for internal planning; **P80** is commitment-grade. Never present summed M values as the estimate. Report the resolved task correlation (default `rho = 0.3`).

Unless declined by the user, report traditional and AI-assisted views. Pass `hours_per_day` to `pipeline` and use its returned day values. For the AI-assisted view, pass the category `default_factor` from `ai-assistance-factors.md`; `pipeline` uses a learned factor when available and returns its source.

## Report format

Follow `${CLAUDE_PLUGIN_ROOT}/skills/new/references/report-template.md` exactly. Headings and prose are Japanese. Write full task IDs verbatim because `/estimate:record` passes them directly to CALC.
