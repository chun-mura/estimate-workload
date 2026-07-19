# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code plugin (`estimate`) that produces effort estimates via WBS
decomposition, 3-point (O/M/P) estimation, Monte Carlo simulation, and
reference-class calibration against project history. No hooks, no MCP server
— just skills, agents, and a pure-Python calculation script.

## Commands

```bash
python3 -m pytest tests/        # run the full test suite (96 tests)
claude --plugin-dir .           # mount this plugin locally without the marketplace, for manual testing
```

`.github/workflows/validate.yml` runs on push/PR to `main`: validates
`.claude-plugin/plugin.json` and `marketplace.json` as JSON, then runs the
pytest suite. Running `pytest` locally before committing remains useful for
fast feedback, but CI is now the enforced gate.

## Architecture

### Pipeline: spec/code analysis → WBS → 3-point → reference-class → Monte Carlo

`/estimate:new` (`skills/new/SKILL.md`) orchestrates:

1. **Analysis** — dispatches `agents/spec-analyzer.md` (always) and
   `agents/code-analyzer.md` (quality mode only) as subagents. Each returns
   exactly one JSON block; no prose. Analyzers never estimate hours — they
   only extract WHAT changes (spec-analyzer) and WHERE/HOW HARD (code-analyzer).
2. **WBS** — the skill merges both views into leaf tasks (0.5–3 person-days),
   each tagged with one fixed `category` and free-form `tags`.
3. **3-point + reference-class + simulation** — all arithmetic goes through
   `scripts/estimate_calc.py`, never freehand. The skill calls `reference-class`
   for anchors, then a single `pipeline` call that applies corrections,
   runs the Monte Carlo simulation (triangular distribution, Gaussian-copula
   task correlation), and appends to history — all in one shot, not five
   separate round-trips (this consolidation was a deliberate token-usage fix;
   see CHANGELOG 0.2.0).
4. Report is written to `docs/estimates/` following the fixed structure in
   `skills/new/references/report-template.md` — section order and columns
   never vary between runs, so reports are diffable/comparable.

### `--mode` (quality | economy)

Controls analysis depth, not report structure:
- `quality` — both spec-analyzer and code-analyzer run once each, against the
  whole batch of sources. Code view wins on task difficulty.
- `economy` — spec-analyzer only; code impact is explicitly *not* verified.
  Every code-affecting WBS task gets its raw P widened before pipeline
  correction, and the report carries a fixed risk/assumption block admitting
  the gap. Never substitute an ad-hoc repo scan for the missing code-analyzer
  pass in this mode.

Analyzers are dispatched once per `/estimate:new` invocation (batched across
all sources), never once per WBS task — this is a hard token-budget rule
enforced in the skill instructions, not just a suggestion.

### `--ai-view` / `--no-ai-view`

Whether the report includes a second, AI-assisted effort total (task hours ×
a per-category factor from `skills/estimation-methodology/references/ai-assistance-factors.md`,
overridden by a *learned* factor once a category has ≥3 AI-assisted and ≥3
non-assisted completed records — learned always wins over default; this
happens inside `estimate_calc.py`, not in skill logic).

### `.estimate/history.jsonl` — the only persistent artifact

One JSON record per leaf task, `status: "estimated"` → `"done"` once actuals
are recorded via `/estimate:record`. This file is the single source of truth;
there is no separate machine-readable run-summary file (removed in 0.4.0 —
previously duplicated data that could drift from history).

Writes happen **only** through `estimate_calc.py`'s `append-history` and
`update-actual` subcommands (file locking + atomic rewrite). Skills and
agents must never `Read`/`Write`/`Edit` this file directly to make decisions.

**Schema versioning is load-bearing, not cosmetic.** `SCHEMA_VERSION = 2` in
`scripts/estimate_calc.py`. `read_history()` skips any record whose
`schema_version` isn't in `KNOWN_SCHEMA_VERSIONS` (currently just `{2}`),
with a warning — it never rewrites old records. This exists because v1's
`pert` field was computed with beta-PERT `(o+4m+p)/6`, which does not match
the triangular distribution `cmd_simulate` actually samples from
(`(o+m+p)/3`). Mixing the two bases would silently corrupt calibration
ratios (`actual / pert`), so v1 records are excluded from anchors and
calibration entirely rather than converted.

When you change how `pert` (or any stored field's meaning) is computed, bump
`SCHEMA_VERSION` and add it to `KNOWN_SCHEMA_VERSIONS` — do not reuse an
existing version number for a changed formula.

### `scripts/` vs `skills/` division of responsibility

- `scripts/estimate_calc.py` owns **all** arithmetic, schema validation, ID
  generation, file locking, and the history file format. It is a plain
  argparse CLI: `estimate_calc.py <subcommand> --input <file|->` reads JSON,
  writes JSON to stdout, and on error writes `{"error": ...}` to stderr with
  exit code 1. It has zero knowledge of Claude, prompts, or report formatting.
- `skills/` (`new`, `record`, `estimation-methodology`) own orchestration,
  wording, report structure, and when to ask the user questions. They call
  CALC (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py"`) for
  every number and must stop on any CALC failure rather than falling back to
  freehand math.
- `agents/` (`spec-analyzer`, `code-analyzer`) are read-only subagents that
  extract structured facts; they never estimate hours or touch history.

This split is enforced by convention in the skill/agent prompts, not by
tooling — when editing any of the three, keep arithmetic in `estimate_calc.py`
and keep prompt/orchestration logic out of it.

## v1 constraints

- **Fixed category taxonomy** — exactly six categories
  (`skills/estimation-methodology/references/category-taxonomy.md`):
  `backend-api`, `frontend-ui`, `db-migration`, `infra`, `test-only`, `docs`.
  `estimate_calc.py`'s `CATEGORIES` set rejects anything else. There is no
  mechanism yet for project-specific categories — a task spanning two
  categories must be split into two tasks, not force-fit into one.
- **No hooks, no MCP** — this plugin is skills + agents + a standalone
  calculation script only. Do not add a hook or MCP server without revisiting
  this constraint deliberately; it's a stated v1 boundary, not an oversight.

## Versioning discipline (read before touching scripts/skills/agents)

Any change to `scripts/`, `skills/`, or `agents/` **must**, in the same
commit/PR, bump `version` in `.claude-plugin/plugin.json` and add a
`CHANGELOG.md` entry. Plugin managers compare versions to decide whether to
refetch; a behavior change with an unchanged version is invisible to them.

**This already happened once for real**: from the initial scaffold through
several behavior changes, `version` stayed at `0.1.0`. A cached `0.1.0`
install kept using a point-estimate formula that had already been fixed
upstream, because nothing signaled that a refetch was needed. Treat every
`scripts/skills/agents` diff as incomplete until `plugin.json`'s `version`
and `CHANGELOG.md` are updated alongside it.
