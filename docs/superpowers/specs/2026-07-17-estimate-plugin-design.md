# Design: `estimate` — Claude Code Plugin for Scientifically-Grounded Effort Estimation

## Goal

A public Claude Code plugin that estimates software development effort from flexible inputs
(design docs, issues, free-text requirements) plus optional codebase analysis, using
WBS decomposition + 3-point estimation with Monte Carlo aggregation + reference-class
anchoring/correction from accumulated actuals. Works with zero data on first run;
accuracy improves as the user records actuals. Outputs both traditional human effort
and AI-assisted effort.

Decided constraints:
- Public plugin, English prompts/README; estimation reports follow the conversation language.
- Plugin name: `estimate` (commands: `/estimate:new`, `/estimate:record`).
- Approach A: 1 main command + 1 record command + 2 subagents + 1 methodology skill. No hooks/MCP in v1.
- History accumulation built in (local file, per-project).

## Components

```
estimate-workload/                  (repo root = plugin root)
├── .claude-plugin/
│   └── plugin.json                 # name: "estimate", semver version
├── commands/
│   ├── new.md                      # /estimate:new — run an estimation
│   └── record.md                   # /estimate:record — record actuals afterward
├── agents/
│   ├── spec-analyzer.md            # requirements/spec → structured change units
│   └── code-analyzer.md            # read-only codebase impact/complexity analysis
├── skills/
│   └── estimation-methodology/
│       ├── SKILL.md                # core method: WBS rules, 3-point guidance, reference-class procedure
│       └── references/             # worked examples, AI-assistance factor table, category taxonomy
├── scripts/
│   └── estimate_calc.py            # stdlib-only: ALL statistics AND ALL history.jsonl I/O
└── README.md
```

### Single choke point principle

The model does no freehand statistical arithmetic AND no freehand editing of
`.estimate/history.jsonl`. Both go exclusively through `estimate_calc.py`.
Commands and agents are forbidden (stated in their prompts) from touching the
history file directly. This centralizes schema validation, ID generation,
locking, and version handling in one tested place.

### estimate_calc.py CLI contract

`python3 estimate_calc.py <subcommand> --input <file|-> [flags]` — JSON in (arg or stdin),
JSON out (stdout), non-zero exit + error JSON on stderr on failure.

Subcommands:
- `simulate` — Monte Carlo aggregation: sample each task from a triangular (O, M, P)
  distribution, sum across tasks over N trials (default 10,000, seedable for tests),
  return per-task PERT mean (stored convenience value) plus total distribution
  percentiles (P50/P80, plus min/max of trials). Replaces the classic PERT normal
  approximation, which understates skew for small task counts.
- `reference-class` — given candidate tasks + history file path, return (a) the most
  similar completed tasks (same category first, ranked by tag overlap; estimate/actual
  pairs, for few-shot anchoring) and (b) the
  actual/estimate ratio distribution with corrected M/P values (or
  `{"skipped": "insufficient_data"}` when fewer than 5 similar records; similar-task
  list may still be returned when non-empty).
- `calibration` — estimate-vs-actual summary and running bias from history.
- `append-history` — validate against schema, stamp `schema_version` + `run_id` +
  task ids, append via single O_APPEND write.
- `update-actual` — validate actual hours (reject non-numeric/zero/negative),
  lock, write temp file, atomic rename.

All history reads also go through the script, which distinguishes JSON parse errors
from schema violations (both skipped with a warning listing line numbers) and reads
known older `schema_version` records tolerantly (unknown fields ignored).

### Subagent output contracts

Each agent's definition file specifies its output as a fenced JSON block:

- `spec-analyzer` → `{change_units: [{name, description, dependencies[], acceptance_criteria[], uncertainty_notes[]}], out_of_scope[], open_questions[]}`
- `code-analyzer` → `{affected_areas: [{path, change_type, complexity: low|mid|high, test_coverage: none|partial|good, notes}], integration_points[], repo_signals: {size, language, test_setup}}`

`new.md`'s merge step consumes exactly these schemas. On overlap (spec `dependencies`
vs code `integration_points`), the spec view defines WHAT changes; the code view
defines WHERE and HOW HARD — code-analyzer output takes precedence for difficulty.

## Flow: /estimate:new

1. **Intake**: accept any mix of file paths, pasted text, or short descriptions as args.
   Read provided docs. Unreadable or nonexistent paths: notify the user, treat as
   not-provided, and feed the gap into step 2.
2. **Gap check**: if critical info is missing (scope boundary, definition of done,
   non-functional constraints), ask up to ~5 questions via AskUserQuestion. Unanswered
   gaps become recorded assumptions and widen the pessimistic bound.
3. **Parallel analysis**: dispatch both subagents in parallel:
   - `spec-analyzer`: extract change units per its output contract.
   - `code-analyzer`: given the change description, analyze impact per its contract.
     Skipped for greenfield projects.
   If an agent fails (error, timeout, unparseable output — distinct from intentional
   skip), proceed with the other's output, record the failure in the report's
   risks/assumptions, and lower stated confidence.
4. **WBS construction**: the command merges both outputs into a task breakdown
   (per change unit: design/implement/test/review/integrate). Leaf tasks sized
   ~0.5–3 person-days; split anything larger. The command assigns each leaf task
   a `category` from the skill's fixed taxonomy and free-form `tags`.
   (Task `id`s and `run_id` are stamped later by `append-history`.)
5. **3-point estimates with few-shot anchoring**: first call `reference-class` to
   fetch similar completed tasks from `.estimate/history.jsonl`; present their
   estimate/actual pairs as anchors while assigning O/M/P hours per leaf task, with
   a one-line rationale each (LLM estimation research shows few-shot examples of
   similar past work improve accuracy). No similar tasks → estimate unanchored.
6. **Reference-class correction**: apply the ratio-based M/P correction from the same
   `reference-class` output. Skipped with a notice if insufficient data (fewer than
   5 similar records). Anchoring (step 5) and correction are complementary: anchors
   improve the raw estimate, the ratio distribution corrects residual bias.
7. **Aggregation**: via `simulate` subcommand (Monte Carlo over triangular
   distributions; report P50/P80 totals).
8. **AI-assisted view**: apply per-category AI-assistance factors — skill defaults,
   replaced by history-learned factors (via `calibration`) once enough `ai_assisted`
   actuals exist. No user-configurable factors in v1.
9. **Output** (history first, report second):
   1. `append-history`: one line per leaf task, status `estimated`.
   2. Write report to `docs/estimates/YYYY-MM-DD-<slug>.md`. If report writing fails,
      output the report content in chat as fallback — history is already safe.
   - Report contents: WBS table with 3-point values **and each task's history `id`**,
     Monte Carlo totals (P50/P80), both effort views, assumptions, risks,
     out-of-scope. History.jsonl is the authoritative record; the report is a
     point-in-time snapshot and is not updated by `/estimate:record`.

## Flow: /estimate:record

1. Read history via the script; list entries with status `estimated` grouped by `run_id`.
2. User supplies actual hours (per task, or total to be distributed proportionally)
   and whether the work was AI-assisted.
3. `update-actual` per task: validates input, sets `actual`, `ai_assisted`, status `done`.
4. Show a calibration summary (estimate vs actual ratio, running bias) via `calibration`.

## Data format: .estimate/history.jsonl

One line per WBS leaf task:

```json
{"schema_version":1,"run_id":"20260716T2130-oauth","id":"20260716T2130-oauth-01","date":"2026-07-16","task":"Add OAuth login endpoint","category":"backend-api","tags":["auth","rest"],"o":4,"m":8,"p":16,"pert":8.7,"actual":null,"ai_assisted":null,"status":"estimated"}
```

- Unit: hours. `run_id` = timestamp + slug (unique across same-day reruns); task `id` =
  `run_id` + sequence. Both generated by `append-history`.
- No `project` field: the file lives in the project, so placement identifies the project.
- Category taxonomy fixed in v1, defined in the methodology skill (e.g. backend-api,
  frontend-ui, db-migration, infra, test-only, docs). No custom categories in v1.
- Per-project file (git-shareable with the team; productivity differs per project).
  Global cross-project aggregation is a v2 candidate.
- Optional `.estimate/config.json`: hours-per-day only in v1.

## Error handling

- No history file → skip correction, state so in the report, keep wider P.
- Corrupt or schema-violating JSONL lines → script skips with a warning listing
  line numbers (parse errors and schema violations reported distinctly).
- Concurrent write safety: `append-history` uses a single O_APPEND write;
  `update-actual` uses lock + temp file + atomic rename.
- No codebase / not a repo → spec-only estimation; note reduced confidence.
- Subagent failure → proceed with remaining output + risk note + lowered confidence
  (see flow step 3).
- Script failure → abort with the error rather than falling back to freehand arithmetic
  or freehand file editing.
- Invalid actuals input → script rejects before write; command prompts re-entry.

## Distribution

- `plugin.json` carries a semver `version`; bump on every release. History schema
  changes bump `schema_version` with a tolerant reader path.
- Install via marketplace (`/plugin marketplace add <repo>`); users can pin/roll back
  by git tag since the repo root is the plugin root.

## Testing / verification

- `claude plugin validate .` passes.
- `estimate_calc.py` gets real unit tests (pure functions + file I/O paths, stdlib
  unittest): Monte Carlo simulation (seeded, deterministic percentile assertions),
  per-task PERT means, reference-class similarity and ratios, append/update atomicity,
  validation rejections, tolerant reading of old schema versions and corrupt lines.
- Dogfood scenario: run `/estimate:new` against a sample requirement on a real repo,
  verify report + history entries; run `/estimate:record`, verify calibration output.

## Out of scope (v1)

- Hooks (re-estimation triggers), MCP server (external ticket/DB integration),
  COCOMO/COSMIC/Function Point modes, regression/Bayesian model beyond ratio-based
  reference-class correction, global cross-project history, custom categories,
  user-configurable AI-assistance factors.
