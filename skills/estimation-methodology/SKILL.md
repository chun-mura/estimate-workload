---
description: Estimation methodology reference for the estimate plugin — WBS decomposition rules, 3-point estimation guidance, reference-class anchoring and correction procedure, AI-assisted effort view. Read before producing or recording any estimate.
---

# Estimation Methodology

## Non-negotiable rules

1. **No freehand math.** Every aggregation, percentile, ratio, or correction is
   computed by `${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py`. If the script
   fails, stop and report the error — never substitute your own arithmetic.
2. **No freehand history edits.** `.estimate/history.jsonl` is only ever written
   by the script's `append-history` and `update-actual` subcommands. Never Read
   the raw file to make decisions when a subcommand can answer instead; never
   Write or Edit it.
3. **Show your uncertainty.** Estimates are ranges (P50/P80), never single numbers.
   Every assumption that widened a range is listed in the report.

## WBS decomposition rules

- Decompose each change unit into leaf tasks along the delivery phases it
  actually needs: design, implement, test, review, integrate. Skip phases that
  don't apply; don't pad.
- Leaf tasks should land between roughly 0.5 and 3 person-days (4–24 hours) of
  traditional effort. Split anything larger — large tasks hide unknowns and
  break reference-class matching.
- Every leaf task gets: a verb-first name, one `category` from
  `references/category-taxonomy.md`, and 1–4 lowercase `tags` (technology or
  domain nouns, e.g. `auth`, `rest`, `react`) that future runs can match on.

## 3-point estimation guidance

For each leaf task assign hours as:

- **O (optimistic):** everything goes right — you know the code, no rework,
  no review friction. ~5th percentile.
- **M (most likely):** the single most probable outcome, including normal
  friction (one review round, small surprises).
- **P (pessimistic):** serious-but-plausible trouble — hidden coupling, rework
  after review, environment issues. ~95th percentile. NOT a catastrophe bound.

Write a one-line rationale per task naming the main complexity driver.
When similar past tasks (anchors) are available, state O/M/P **relative to the
anchors' actuals**, not from scratch: "similar task X took 6h against a PERT of
8h" is stronger evidence than intuition.

Unanswered scoping questions do not block the estimate: record each one as an
assumption and widen P for the affected tasks.

## Reference-class procedure

1. Before assigning O/M/P, call `reference-class` with each task's
   category/tags to fetch anchors (similar completed tasks with their
   estimate vs. actual).
2. After assigning O/M/P, call `reference-class` again including `m` and `p`
   to get ratio-based corrections. Use `corrected_m`/`corrected_p` in place of
   your raw values when provided. Anchoring improves the raw estimate;
   correction removes residual bias — do both.
3. If correction is skipped (`insufficient_data`), say so in the report and
   note that ranges are uncorrected.

## Aggregation

Call `simulate` with the final per-task O/M/P. Report the total as:
- **P50** — "as likely over as under"; use for internal planning.
- **P80** — commitment-grade; use for external quotes.
Never present the sum of M values as "the estimate".

## Two effort views

Report BOTH, clearly labeled:
- **Traditional effort:** the simulated totals as-is, in hours and person-days
  (default 8 h/day; honor `.estimate/config.json` `hours_per_day` if present).
- **AI-assisted effort:** per-category multipliers applied to task hours before
  simulation. Use learned factors from `calibration` when a category has them;
  otherwise the defaults in `references/ai-assistance-factors.md`. State which
  source each factor came from.

## Report language

Write the estimation report in the language the user is conversing in.
