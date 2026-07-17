# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
