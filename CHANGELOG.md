# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Changed
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
