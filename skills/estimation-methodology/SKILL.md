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
  no review friction. The simulation never samples below O: it is the hard
  floor of the range, not a long-shot best case.
- **M (most likely):** the single most probable outcome, including normal
  friction (one review round, small surprises).
- **P (pessimistic):** serious-but-plausible trouble — hidden coupling, rework
  after review, environment issues. The simulation never samples above P, so
  set it wide enough to cover serious trouble. Still NOT a catastrophe bound:
  record catastrophic scenarios as risks, not in P.

Write a one-line rationale per task naming the main complexity driver.
When similar past tasks (anchors) are available, state O/M/P **relative to the
anchors' actuals**, not from scratch: "similar task X took 6h against an
expected 8h" is stronger evidence than intuition.

Unanswered scoping questions do not block the estimate: record each one as an
assumption and widen P for the affected tasks.

## Reference-class procedure

1. Before assigning O/M/P, call `reference-class` with each task's
   category/tags to fetch anchors (similar completed tasks with their
   estimate vs. actual).
2. After assigning raw O/M/P, the `pipeline` command applies ratio-based
   corrections automatically and returns the corrected values — report those,
   never your raw ones, when a correction applied. Anchoring improves the raw
   estimate; correction removes residual bias — do both.
3. If correction is skipped (`insufficient_data`), say so in the report and
   note that ranges are uncorrected.
4. Each correction states its `basis` (`category_and_tags` when enough
   tag-matched records exist, else `category`) and carries `low_sample: true`
   when backed by fewer than 10 records. Surface both in the report: a
   low-sample correction is indicative, not authoritative.

## Aggregation

The `pipeline` command simulates over the final (corrected) per-task O/M/P.
Report the total as:
- **P50** — "as likely over as under"; use for internal planning.
- **P80** — commitment-grade; use for external quotes.
Never present the sum of M values as "the estimate".

## Task correlation

Project tasks share common-cause delays such as specification churn and
environment failures, so simulations use positive task correlation rather
than assuming independence. CALC models this with a one-factor Gaussian
copula: `rho = 0` is independent task risk and `rho = 1` is fully shared risk.
The default is `rho = 0.3`; values around `0.2`–`0.5` are a practical range for
common project risk. Every report states the resolved correlation assumption.

## Two effort views

Report BOTH, clearly labeled (unless the user declined the AI-assisted view
at intake — then report only the traditional view and say the AI-assisted
view was skipped at the user's request):
- **Traditional effort:** the simulated totals as-is, in hours and person-days.
  Pass `hours_per_day` from `.estimate/config.json` (if present) to `pipeline`
  and report the returned `p50_days`/`p80_days` — never divide hours yourself.
- **AI-assisted effort:** per-category multipliers applied to task hours before
  simulation. Supply each task's `default_factor` from
  `references/ai-assistance-factors.md`; `pipeline` replaces it with the
  learned factor when the category has one, and reports each factor's
  `source`. State that source in the report.

## Report format

The report structure is fixed, not chosen per run: section order, heading
text, and table columns come from
`${CLAUDE_PLUGIN_ROOT}/skills/new/references/report-template.md`. Headings are
Japanese; prose inside each section is Japanese too. Identifiers stay as the
script emits them — category names, `run_id`, and task ids are never
translated or shortened.

A task's 履歴ID in the report is the full id returned by `pipeline`
(`<run_id>-NN`), written verbatim. `/estimate:record` passes that string
straight to `update-actual --id`, so an abbreviated id makes the run
impossible to record actuals against.
