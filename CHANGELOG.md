# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Fixed
- Reports produced by `/estimate:new` now follow one fixed structure
  (`skills/new/references/report-template.md`): section order, heading text,
  and WBS table columns no longer vary run to run, which previously made
  reports impossible to compare or parse
- The WBS 履歴ID column must carry the full task id from `pipeline` verbatim;
  abbreviated ids (`01`, `-01`, slug-only) silently broke
  `/estimate:record`, which feeds the column straight to `update-actual --id`
- `/estimate:new` must not write a report when `pipeline` returned no
  `run_id`, closing a path where a report could be produced with hand-computed
  totals and a `.estimate/runs/` path that does not exist

### Changed
- Cut per-run token usage of `/estimate:new`: the post-WBS flow (correction,
  both simulations, history append, run summary) is now one `pipeline` call
  from a single payload file instead of five calls each re-serializing the
  task list; requirement documents are read only by the spec-analyzer, not
  also by the main context (gap-check questions moved after analysis);
  the chat output is a compact summary pointing at the report file; and
  methodology references are loaded conditionally
- Compact `reference-class` anchors to task/pert/actual/ai_assisted/tags and
  lower the default `max_anchors` from 5 to 3
- Pin both analysis agents to `model: sonnet` and constrain the
  code-analyzer to targeted reads within the change's blast radius
- Store the point estimate as the triangular mean `(o+m+p)/3` so it matches
  the distribution the Monte Carlo simulation samples; the old beta-PERT
  formula made calibration misreport bias on skewed ranges. History
  `schema_version` bumped to 2; v1 records are excluded from anchors and
  calibration with a warning (the file is never rewritten)
- Apply the same ratio correction to `corrected_o` as to `corrected_m`
  (still capped to stay below it) instead of only capping the raw value
- Prefer tag-matched records for reference-class correction ratios and
  report the population used as `basis`
- Document O/P as the hard bounds of the sampled range rather than
  percentiles, matching the triangular distribution

### Added
- `pipeline` subcommand running reference-class correction, traditional and
  AI-assisted simulation (learned factors override the supplied
  `default_factor`), history append, and run summary in one invocation;
  a run-summary failure is returned as `summary.error` instead of failing
  the call since history is already written
- `hours_per_day` input to `simulate` (validated, default 8) with
  `p50_days`/`p80_days` in the output, so person-day conversion goes through
  the calculation script instead of freehand division
- `low_sample: true` flag on corrections, calibration output, and learned
  AI-assistance factors backed by fewer than 10 records
- Validation of `min_records`/`max_anchors` in `reference-class`
- README notes on updating the plugin and on run-id collisions when merging
  shared history files
- Marketplace-level description so `claude plugin validate --strict` passes

### Removed
- Dead `output_dir` payload key from `run-summary`; the summary always lands
  in the history file's sibling `runs/` directory

## [0.1.0] - 2026-07-17

### Added
- Correlation modeling for common-cause risk in estimates
- Machine-readable estimate summary persistence
- AI-assisted effort view confirmation at estimate intake
- Monte Carlo simulation subcommand with percentile helper
- Append-history subcommand with tolerant history reader
- Update-actual subcommand with locking and atomic rewrite
- Reference-class subcommand for anchors and ratio correction
- Calibration and distribute subcommands
- Estimation methodology skill with taxonomy and AI factors
- `spec-analyzer` and `code-analyzer` agents with JSON output contracts
- `/estimate:new` orchestration skill
- `/estimate:record` skill for actuals and calibration
- Plugin marketplace manifest
- MIT license

### Changed
- Migrated from legacy `commands/` directory to `skills/` layout

### Fixed
- Run summary output path constrained to prevent path escape
- Largest-remainder allocation in `distribute` to prevent negative shares
- Final-review findings: `corrected_o` invariant, `ai_assisted` KeyError, append lock, error-JSON catch-all
