# estimate — effort estimation plugin for Claude Code

`estimate` turns a spec, an issue, or a short description of upcoming work into
a defensible effort estimate. It decomposes the work into a WBS of leaf tasks,
assigns each an optimistic/most-likely/pessimistic (3-point) range, aggregates
the ranges with Monte Carlo simulation, and anchors both the ranges and the
final numbers against your own team's history via reference-class forecasting.
The result is a P50 (planning) and P80 (commitment) figure — never a single
made-up number.

The estimate gets better the more you use it. After work finishes, you record
actual hours per task; those actuals become anchors and bias-correction data
for the next estimate in the same category. There is no cold-start requirement
to start using it, but accuracy improves once a few similar tasks have real
actuals attached.

## Install

```
/plugin marketplace add chun-mura/estimate-workload
/plugin install estimate@estimate-workload
```

To update later, refresh the marketplace listing and reload:

```
/plugin marketplace update estimate-workload
/reload-plugins
```

New versions are picked up when `version` in `.claude-plugin/plugin.json` is
bumped.

For local development, run Claude Code with the plugin directory mounted
directly — no marketplace needed:

```bash
claude --plugin-dir .
```

## Usage

1. Produce an estimate from a spec, issue, or free-text description:

   ```
   /estimate:new docs/spec.md
   ```

   This reads the input, dispatches spec/code analysis, builds the WBS,
   assigns and corrects 3-point ranges, runs the simulation, writes a report
   under `docs/estimates/`, and prints the `run_id` you'll need next. Every
   report follows one fixed structure
   (`skills/new/references/report-template.md`), so reports are comparable
   run to run.

2. After the work is done, record actual hours against that run:

   ```
   /estimate:record <run_id>
   ```

   This writes actuals back into history and prints a calibration summary
   (estimate vs. actual bias, per-category ratios).

## Data & privacy

The plugin stores project-local data under `.estimate/`. Task estimates and
actuals live in `.estimate/history.jsonl`; each estimate also gets a
machine-readable point-in-time snapshot at `.estimate/runs/<run_id>.json`.
Nothing is sent anywhere else.

`history.jsonl` is one estimated or completed task record per line and is only
written through `append-history` and `update-actual`. Run-summary JSON files
contain the run id, generated time, S/M/L classification and boundaries,
traditional and AI-assisted totals, and the persisted task ids/categories/
expected means. They are written atomically by `run-summary` and are not
regenerated
when `/estimate:record` later stores actuals.

Choose the repository policy that fits your project. Commit both
`.estimate/history.jsonl` and `.estimate/runs/` to share calibration data and
stable machine-readable estimates with the team, or ignore both when estimate
data should remain local. Team members benefit from shared anchors and
corrections only when `history.jsonl` is shared.

Run ids embed a timestamp and slug and are de-duplicated only against the
local history file. If two clones estimate work with the same slug in the same
second, a later git merge can end up with duplicate run ids — rare, but worth
checking for when merging shared history.

## The two effort views

Every report shows two totals, each as P50 and P80, in both hours and
person-days (8 hours/day by default; override with `hours_per_day` in
`.estimate/config.json`):

- **Traditional effort** — the simulated totals as estimated, with no
  adjustment for AI assistance.
- **AI-assisted effort** — the same tasks scaled by a per-category factor
  before simulation. Factors come from your own recorded history once a
  category has at least 3 AI-assisted and 3 non-assisted completed actuals;
  until then, built-in defaults are used. The report states which source each
  factor came from.

**P50** is the median outcome — as likely to be exceeded as not. Use it for
internal planning. **P80** is a more conservative figure that the true effort
should undershoot 80% of the time. Use it for commitments and external quotes.
Neither number is the sum of the "most likely" values — both come out of the
Monte Carlo simulation over the full O/M/P ranges.

## v1 limits

- **Fixed category taxonomy.** Tasks are classified into a small, built-in set
  of categories (see `skills/estimation-methodology/references/category-taxonomy.md`).
  There's no way to add custom categories yet.
- **No hooks, no MCP.** The plugin is skills, an agent-backed workflow, and a
  standalone calculation script — it doesn't register any Claude Code hooks or
  MCP servers.

## Versioning

The plugin follows semver (`.claude-plugin/plugin.json`). History records carry
a `schema_version`; run summaries carry an independent `schema_version` so a
breaking change to one format cannot silently change the other. Readers of
history never rewrite the file and skip records with an unknown
`schema_version`, reporting a warning instead of failing. Records written by
plugin 0.1.x carry `schema_version: 1`, whose `pert` field was computed with a
formula that does not match the simulation model; current readers exclude them
from anchors and calibration rather than mixing incompatible baselines.
Consumers of run summaries must check their schema version before parsing.
