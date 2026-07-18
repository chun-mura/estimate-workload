# Design: remove run summaries and duplicate estimate output

Date: 2026-07-18
Status: approved for implementation planning

## Goal

Remove three low-value assets from the estimate plugin:

1. machine-readable run summaries under `.estimate/runs/`;
2. duplicated totals in the Markdown estimate report;
3. the optional, normally skipped `worked-example.md` reference.

The canonical persisted estimate data becomes `.estimate/history.jsonl`.

## Scope

### Remove run summaries

- Delete the `run-summary` CLI command, its validation helpers, size-label
  configuration, schema version constant, atomic JSON writer, and tests.
- `pipeline` still validates `analysis`, runs correction/simulation, and
  appends history. It no longer creates, returns, or recovers from a
  `summary` object.
- Remove `size_boundaries` from the skill payload contract. The `size` field
  disappears from the Markdown report because it had no source without the
  summary.
- Keep simulation metadata and `analysis` in the pipeline return so the report
  can state its method and mode without rereading persisted data.
- Keep history schema version 2. No history records are rewritten.

### Remove report duplication

The Markdown report keeps a single summary table containing the traditional
and, when selected, AI-assisted P50/P80 totals in hours and person-days. It
removes the separate `## 従来型見積もり` and `## AI支援見積もり` total tables.

The AI-assisted section remains only as a compact per-category factor table.
The report method section records the returned simulation values directly;
it no longer refers to a run-summary file. The footer retains only the
`/estimate:record` instruction.

### Delete the optional example

Delete `skills/estimation-methodology/references/worked-example.md` and every
reference to it. No replacement is needed because the active skill explicitly
marked it optional and normally skipped.

### Delete existing generated summary data

After code and documentation changes pass tests, remove the exact existing
directory `.estimate/runs/` in this repository if it exists. Do not delete
`.estimate/history.jsonl`, `.estimate/`, or any summary directory outside this
repository. Report whether the directory existed and was removed.

## Compatibility and release

- Existing `.estimate/runs/*.json` files become unsupported and are deleted
  only in this repository at the user's explicit request.
- No migration is required because the history JSONL remains the authoritative
  record and `/estimate:record` obtains its task IDs from the Markdown report.
- This is a breaking removal for consumers of run summaries, so update the
  plugin version from `0.3.0` to `0.4.0` and document it in `CHANGELOG.md`.

## Non-goals

- Do not remove history, reference-class correction, calibration, simulation,
  analysis modes, person-day values, or `/estimate:record`.
- Do not delete historical planning/specification documents under `docs/`.
- Do not add a replacement machine-readable format.

## Verification

- Tests prove `pipeline` appends history and returns simulation/analysis data
  without writing a `runs/` directory or returning `summary`.
- CLI registration tests prove `run-summary` is absent.
- Report-template checks prove total values appear only in the summary table,
  no size line or machine-summary footer remains, and AI factors remain.
- Full suite: `python3 -m pytest tests/`.
- Search verifies active source, skills, README, and tests contain no
  `run-summary`, `.estimate/runs`, `RUN_SCHEMA_VERSION`, `size_boundaries`, or
  `worked-example` references.
