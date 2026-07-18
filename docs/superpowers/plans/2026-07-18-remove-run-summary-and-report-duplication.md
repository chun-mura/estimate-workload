# Remove Run Summary and Report Duplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove machine-readable run summaries, duplicated report totals, and the unused worked example while retaining history-backed estimates and actuals.

**Architecture:** `pipeline` ends after writing `.estimate/history.jsonl` and returns its in-memory simulation and analysis data to the skill. The report uses that returned data once in its summary table and never depends on `.estimate/runs/`. The calculator exposes no `run-summary` CLI command or size-boundary contract.

**Tech Stack:** Python 3 standard library, unittest/pytest, Claude Code skills and Markdown documentation.

## Global Constraints

- `.estimate/history.jsonl` remains the only persisted estimate record; do not rewrite existing history.
- Remove `run-summary`, `RUN_SCHEMA_VERSION`, `DEFAULT_SIZE_BOUNDARIES`, `size_boundaries`, and all active `.estimate/runs/` references.
- `pipeline` must retain `run_id`, `tasks`, `traditional`, `ai_assisted`, `analysis`, `simulation`, `trials`, `correlation`, `hours_per_day`, and `warnings`; it must not return `summary`.
- Keep `p50_days` and `p80_days` because the single report summary table uses them.
- The Markdown report contains total values only in `## サマリ`; retain the AI factor table without repeating its totals.
- Delete `skills/estimation-methodology/references/worked-example.md`.
- Remove `.estimate/runs/` only if it exists under this repository root; never delete `.estimate/history.jsonl` or any external path.
- Bump `.claude-plugin/plugin.json` from `0.3.0` to `0.4.0` and add a breaking-removal entry to `CHANGELOG.md`.

---

## File structure

```text
scripts/estimate_calc.py
  Removes run-summary writer/CLI and makes pipeline history-only.
tests/test_estimate_calc.py
  Deletes summary-specific tests and verifies pipeline does not write a runs directory.
skills/new/SKILL.md
  Removes summary payload, recovery rule, size-boundary handling, and summary footer behavior.
skills/new/references/report-template.md
  Keeps a single totals table and removes size/summary-file references.
skills/estimation-methodology/SKILL.md
  Removes run-summary references while preserving report and history rules.
skills/estimation-methodology/references/worked-example.md
  Deleted.
README.md, CHANGELOG.md, .claude-plugin/plugin.json
  Document the history-only storage model and release 0.4.0.
```

### Task 1: Remove the calculator run-summary contract with regression coverage

**Files:**
- Modify: `scripts/estimate_calc.py:1-42, 263-381, 653-805, 845-875`
- Modify: `tests/test_estimate_calc.py:273-543, 803-1068`

**Interfaces:**
- Consumes: the existing `pipeline` payload without `boundaries`.
- Produces: a pipeline result containing `analysis` and `simulation`, but no `summary` key.
- Removes: `cmd_run_summary`, `_validated_totals`, `_merged_size_boundaries`, `RUN_SCHEMA_VERSION`, `DEFAULT_SIZE_BOUNDARIES`, and `PAYLOAD_COMMANDS["run-summary"]`.

- [ ] **Step 1: Replace run-summary tests with failing history-only pipeline tests**

  Delete `TestRunSummary` in full. Replace the summary-persistence assertions in
  `TestPipeline` with these tests:

  ```python
  def test_returns_analysis_and_simulation_without_summary(self):
      analysis = {"mode": "economy", "agents": ["spec-analyzer"]}
      out = ec.cmd_pipeline(self.payload(analysis=analysis))
      self.assertEqual(out["analysis"], analysis)
      self.assertEqual(out["simulation"]["distribution"], "triangular")
      self.assertNotIn("summary", out)

  def test_pipeline_writes_history_without_a_runs_directory(self):
      out = ec.cmd_pipeline(self.payload())
      self.assertEqual(len(self.raw_lines()), 2)
      self.assertFalse(os.path.exists(os.path.join(
          os.path.dirname(self.path), "runs", out["run_id"] + ".json"
      )))

  def test_run_summary_is_not_a_payload_command(self):
      self.assertNotIn("run-summary", ec.PAYLOAD_COMMANDS)
  ```

  Update `test_unseeded_pipeline_run_stays_reproducible` to replay from
  `out["simulation"]`, not from a JSON file. Delete summary-only tests:
  `test_run_summary_records_how_the_simulation_was_run`,
  `test_ai_view_disabled_records_no_ai_seed`,
  `test_ai_view_false_skips_factors_and_uses_traditional_basis`,
  `test_run_summary_failure_is_recoverable`,
  `test_boundaries_pass_through_to_summary`, and
  `test_cli_real_path_writes_history_and_summary`.

- [ ] **Step 2: Run the focused tests and confirm the red state**

  Run:

  ```bash
  python3 -m pytest tests/test_estimate_calc.py::TestPipeline -v
  ```

  Expected: FAIL because pipeline still writes a summary, returns `summary`,
  and registers `run-summary`.

- [ ] **Step 3: Remove summary code and simplify pipeline**

  In `scripts/estimate_calc.py`:

  1. Remove `RUN_SCHEMA_VERSION` and `DEFAULT_SIZE_BOUNDARIES` from the
     constants, and remove `tempfile` and `datetime` imports if no remaining
     code uses them.
  2. Delete `_validated_totals`, `_merged_size_boundaries`, and
     `cmd_run_summary` completely.
  3. Change `cmd_pipeline`'s docstring to state that history is the only
     persisted output. After creating `simulation`, delete `summary_payload`,
     its `boundaries` handling, the `try/except CalcError` block, and the
     `summary` return member.
  4. Remove `"run-summary": cmd_run_summary` from `PAYLOAD_COMMANDS`.

  The resulting return tail must be:

  ```python
  return {
      "run_id": run_id,
      "tasks": out_tasks,
      "traditional": traditional["total"],
      "ai_assisted": ai_assisted["total"] if ai_assisted else None,
      "analysis": analysis,
      "trials": traditional["trials"],
      "correlation": traditional["correlation"],
      "hours_per_day": traditional["hours_per_day"],
      "simulation": simulation,
      "warnings": ref["warnings"],
  }
  ```

- [ ] **Step 4: Run focused and complete tests**

  Run:

  ```bash
  python3 -m pytest tests/test_estimate_calc.py::TestPipeline -v
  python3 -m pytest tests/
  ```

  Expected: all tests pass; no test creates a `runs` directory.

- [ ] **Step 5: Commit calculator removal**

  ```bash
  git add scripts/estimate_calc.py tests/test_estimate_calc.py
  git commit -m "refactor: remove run summary persistence"
  ```

### Task 2: Remove summary-driven skill and report behavior

**Files:**
- Modify: `skills/new/SKILL.md:8-141`
- Modify: `skills/new/references/report-template.md:13-124`
- Modify: `skills/estimation-methodology/SKILL.md:1-120`
- Delete: `skills/estimation-methodology/references/worked-example.md`

**Interfaces:**
- Consumes: the history-only pipeline result from Task 1.
- Produces: a Markdown report with one totals table, a method line built from
  `pipeline.simulation`, and a footer containing only `/estimate:record`.

- [ ] **Step 1: Remove run-summary instructions from `/estimate:new`**

  In `skills/new/SKILL.md`, make these exact contract changes:

  - Remove the `worked-example.md` sentence from the initial reads.
  - Remove the recoverable run-summary exception from the CALC failure rule.
  - Remove `size_boundaries` from the Step 7 payload.
  - Replace “writes the run summary” with “appends history” in the pipeline
    description.
  - Delete all `summary` success/error conditions from Steps 7 and 8,
    including the machine-readable footer instruction.
  - Require simulation reproduction values directly from
    `pipeline.simulation`, not a summary file.

- [ ] **Step 2: Reduce the fixed report template to one totals table**

  In `skills/new/references/report-template.md`:

  - Delete the header line beginning `- **規模**:`.
  - Keep the existing four-row `## サマリ` table as the only place for P50/P80
    totals.
  - Delete the total tables under `## 従来型見積もり` and `## AI支援見積もり`.
  - Keep `## AI支援見積もり` with only the category/factor/source table, and
    retain its declined-view rule.
  - Replace the method bullet’s “run summary” reference with
    `pipeline`’s returned `simulation` values.
  - Delete the machine-readable footer row and remove the Section note that
    requires repeated totals.

- [ ] **Step 3: Align methodology and delete the unused example**

  In `skills/estimation-methodology/SKILL.md`, remove every assertion that
  a run summary is written or read. Keep the requirement to use returned
  `p50_days`/`p80_days` values and the full task ID in the Markdown report.
  Delete `skills/estimation-methodology/references/worked-example.md` using
  an `apply_patch` delete operation.

- [ ] **Step 4: Verify the active prompt contract**

  Run:

  ```bash
  rg -n "run-summary|run summary|size_boundaries|Machine-readable summary|worked-example|.estimate/runs" \
    skills/new skills/estimation-methodology
  ```

  Expected: no matches. Then run:

  ```bash
  rg -n "## サマリ|## 従来型見積もり|## AI支援見積もり|P50|P80" \
    skills/new/references/report-template.md
  ```

  Expected: totals occur in `## サマリ` only; `## AI支援見積もり` contains only
  factor information.

- [ ] **Step 5: Commit skill and template simplification**

  ```bash
  git add skills/new/SKILL.md skills/new/references/report-template.md \
    skills/estimation-methodology/SKILL.md \
    skills/estimation-methodology/references/worked-example.md
  git commit -m "refactor: simplify estimate report output"
  ```

### Task 3: Update released documentation and delete generated summaries safely

**Files:**
- Modify: `README.md:46-160`
- Modify: `CHANGELOG.md:7-30`
- Modify: `.claude-plugin/plugin.json:4`
- Delete if present: `.estimate/runs/`

**Interfaces:**
- Produces: plugin version `0.4.0` and documentation that names
  `.estimate/history.jsonl` as the sole persisted estimate data.

- [ ] **Step 1: Update user-facing storage documentation**

  In `README.md`, remove all references to run-summary files, run-summary
  schema versions, S/M/L labels, summary replay, and committing
  `.estimate/runs/`. State that history JSONL stores tasks and actuals, that
  the command returns simulation metadata for the current report, and that
  `.estimate/history.jsonl` is the only persistent estimate artifact.

- [ ] **Step 2: Publish the breaking removal**

  Change `.claude-plugin/plugin.json` to:

  ```json
  "version": "0.4.0"
  ```

  Add this under `## [Unreleased]` in `CHANGELOG.md`:

  ```markdown
  ### Removed
  - Machine-readable run-summary JSON files, their size classification, and
    the `run-summary` calculator command. `.estimate/history.jsonl` is now the
    sole persisted estimate artifact.
  - Duplicate traditional and AI-assisted total tables from estimate reports;
    totals appear once in the summary table.
  - The optional, normally skipped worked example reference.
  ```

- [ ] **Step 3: Resolve and delete only the approved generated-data target**

  Run:

  ```bash
  if test -d .estimate/runs; then find .estimate/runs -maxdepth 1 -type f -print; else printf 'no .estimate/runs directory\n'; fi
  ```

  If the directory is absent, record that nothing was deleted. If it exists,
  remove exactly `.estimate/runs` with `rm -rf .estimate/runs` after confirming
  its printed contents are the expected generated JSON files. Do not remove
  `.estimate`, `.estimate/history.jsonl`, or any path outside this repository.

- [ ] **Step 4: Run release verification**

  Run:

  ```bash
  python3 -m pytest tests/
  git diff --check
  rg -n "run-summary|run summary|RUN_SCHEMA_VERSION|DEFAULT_SIZE_BOUNDARIES|size_boundaries|worked-example|.estimate/runs" \
    README.md CHANGELOG.md skills scripts tests .claude-plugin
  git status --short
  ```

  Expected: tests pass, the diff has no whitespace errors, active sources have
  no removed-contract references, and status lists only intended changes.

- [ ] **Step 5: Commit removal release assets**

  ```bash
  git add README.md CHANGELOG.md .claude-plugin/plugin.json
  git commit -m "docs: document history-only estimate storage"
  ```
