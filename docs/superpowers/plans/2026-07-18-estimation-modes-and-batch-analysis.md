# Estimation Modes and Batch Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `/estimate:new` select quality or economy analysis before estimation, run analysis once per invocation, and persist the selected coverage in every new run summary.

**Architecture:** The skill owns command-argument parsing, user interaction, agent dispatch, WBS caveats, and report prose. `estimate_calc.py` stays the sole writer of machine-readable state: it validates an `analysis` provenance object before any history write, returns it from `pipeline`, and persists it in a version-3 run summary. Existing `spec-analyzer` and `code-analyzer` remain unchanged; quality mode runs both once, and economy mode runs only the specification agent.

**Tech Stack:** Claude Code skills and agents, Python 3 standard library, unittest/pytest.

## Global Constraints

- `/estimate:new --mode quality` and `/estimate:new --mode economy` are the only explicit mode forms.
- With no mode flag, ask for a mode before dispatch; do not choose economy implicitly.
- One `/estimate:new` invocation is one batch and makes exactly one `pipeline` call, regardless of the number of WBS leaf tasks.
- Quality mode dispatches the two existing analyzers once each; economy mode dispatches only `estimate:spec-analyzer` once and performs no substitute repository scan.
- Economy-mode reports must state that code impact, coupling, integration points, and test coverage are unverified; those uncertainties widen affected `P` values.
- Persist analysis provenance as `{"mode": "quality|economy", "agents": ["spec-analyzer", ...]}` in both the pipeline result and run summary.
- Run-summary schema changes from `2` to `3`; history schema remains `2`.
- Do not add caching, dependencies, hooks, MCP servers, or changes to estimation mathematics.
- Any change to `scripts/`, `skills/`, or `agents/` bumps `.claude-plugin/plugin.json` and adds a CHANGELOG entry in the same commit.

---

## File structure

```text
scripts/estimate_calc.py
  Validates analysis provenance, passes it through pipeline, and writes it in v3 run summaries.
tests/test_estimate_calc.py
  Regression tests for provenance validation, atomic no-write failures, and v3 persistence.
skills/new/SKILL.md
  Parses the mode flag, asks for omitted selection, dispatches the chosen agents once, and writes mode-aware reports.
skills/new/references/report-template.md
  Requires the mode line and economy caveats in generated reports.
skills/estimation-methodology/SKILL.md
  Defines how economy-mode uncertainty widens P without changing calculation code.
README.md
  Documents mode flags, batching, and run-summary provenance.
.claude-plugin/plugin.json
  Publishes the behavior and schema change as version 0.3.0.
CHANGELOG.md
  Records the new user-visible modes and run-summary schema version.
```

### Task 1: Add validated analysis provenance to the calculation boundary

**Files:**
- Modify: `scripts/estimate_calc.py:35, 232-340, 620-770`
- Modify: `tests/test_estimate_calc.py:360-540, 760-1020`

**Interfaces:**
- Consumes: pipeline payload field `analysis: {mode: str, agents: list[str]}`.
- Produces: `_validated_analysis(payload, command) -> dict`, `RUN_SCHEMA_VERSION = 3`, `cmd_run_summary(...)["analysis"]`, and `cmd_pipeline(...)["analysis"]`.
- Valid modes: `quality`, `economy`.
- Valid agent names: `spec-analyzer`, `code-analyzer`; the list is non-empty, has no duplicates, and contains only valid names. Economy requires exactly `["spec-analyzer"]`; quality accepts either or both successful analyzer names, preserving partial-result handling.

- [ ] **Step 1: Write failing run-summary and pipeline tests**

  Add these tests to `TestRunSummary` and `TestPipeline` respectively:

  ```python
  def test_persists_validated_analysis_provenance(self):
      analysis = {"mode": "quality", "agents": ["spec-analyzer", "code-analyzer"]}
      out = ec.cmd_run_summary(self.payload(analysis=analysis))
      self.assertEqual(out["schema_version"], 3)
      self.assertEqual(out["analysis"], analysis)

  def test_rejects_invalid_analysis_before_writing_summary(self):
      for analysis in (
          None,
          {"mode": "economy", "agents": ["code-analyzer"]},
          {"mode": "quality", "agents": ["spec-analyzer", "spec-analyzer"]},
          {"mode": "unknown", "agents": ["spec-analyzer"]},
      ):
          with self.subTest(analysis=analysis), self.assertRaises(ec.CalcError):
              ec.cmd_run_summary(self.payload(analysis=analysis))

  def test_returns_and_persists_analysis_provenance(self):
      analysis = {"mode": "economy", "agents": ["spec-analyzer"]}
      out = ec.cmd_pipeline(self.payload(analysis=analysis))
      self.assertEqual(out["analysis"], analysis)
      with open(os.path.join(os.path.dirname(self.path), "runs", out["run_id"] + ".json"),
                encoding="utf-8") as fh:
          self.assertEqual(json.load(fh)["analysis"], analysis)

  def test_rejects_analysis_before_history_write(self):
      with self.assertRaisesRegex(ec.CalcError, "pipeline: 'analysis'"):
          ec.cmd_pipeline(self.payload(analysis={"mode": "economy", "agents": []}))
      self.assertFalse(os.path.exists(self.path))
  ```

  Update every existing `TestRunSummary.payload()` and `TestPipeline.payload()` base payload to include valid quality analysis, so unrelated tests retain a valid contract.

- [ ] **Step 2: Run the focused tests and confirm the red state**

  Run:

  ```bash
  python3 -m pytest tests/test_estimate_calc.py::TestRunSummary tests/test_estimate_calc.py::TestPipeline -v
  ```

  Expected: FAIL because `analysis` is neither required nor persisted and the run schema is still version 2.

- [ ] **Step 3: Implement analysis validation and propagation**

  In `scripts/estimate_calc.py`, define constants next to `RUN_SCHEMA_VERSION`:

  ```python
  RUN_SCHEMA_VERSION = 3
  ANALYSIS_MODES = {"quality", "economy"}
  ANALYSIS_AGENTS = {"spec-analyzer", "code-analyzer"}
  ```

  Add this helper immediately after `_required_string`:

  ```python
  def _validated_analysis(payload, command):
      analysis = payload.get("analysis")
      if not isinstance(analysis, dict):
          raise CalcError(f"{command}: 'analysis' must be an object")
      mode = analysis.get("mode")
      agents = analysis.get("agents")
      if mode not in ANALYSIS_MODES:
          raise CalcError(
              f"{command}: 'analysis.mode' must be one of {sorted(ANALYSIS_MODES)}"
          )
      if not isinstance(agents, list) or not agents:
          raise CalcError(f"{command}: 'analysis.agents' must be a non-empty list")
      if any(agent not in ANALYSIS_AGENTS for agent in agents):
          raise CalcError(
              f"{command}: 'analysis.agents' must contain only "
              f"{sorted(ANALYSIS_AGENTS)}"
          )
      if len(set(agents)) != len(agents):
          raise CalcError(f"{command}: 'analysis.agents' must not contain duplicates")
      if mode == "economy" and agents != ["spec-analyzer"]:
          raise CalcError(
              f"{command}: economy analysis requires ['spec-analyzer']"
          )
      return {"mode": mode, "agents": agents}
  ```

  In `cmd_run_summary`, call `_validated_analysis(payload, "run-summary")` before reading history and insert `"analysis": analysis` beside `"simulation"` in `document`. In `cmd_pipeline`, call `_validated_analysis(payload, "pipeline")` immediately after validating `ai_view`, add it to `summary_payload`, and include it in the returned dictionary. Do not add it to history records.

- [ ] **Step 4: Run focused tests and then the complete calculator suite**

  Run:

  ```bash
  python3 -m pytest tests/test_estimate_calc.py::TestRunSummary tests/test_estimate_calc.py::TestPipeline -v
  python3 -m pytest tests/
  ```

  Expected: all focused and full-suite tests pass; history-schema tests still assert `{2}`, while summaries assert `3`.

- [ ] **Step 5: Commit the calculation contract**

  ```bash
  git add scripts/estimate_calc.py tests/test_estimate_calc.py
  git commit -m "feat: record estimate analysis provenance"
  ```

### Task 2: Make `/estimate:new` select and enforce analysis modes

**Files:**
- Modify: `skills/new/SKILL.md:6-96`
- Modify: `skills/estimation-methodology/SKILL.md:18-43, 104-112`
- Modify: `skills/new/references/report-template.md:54-105`

**Interfaces:**
- Consumes: optional leading arguments `--mode quality` or `--mode economy` and all remaining requirement sources.
- Produces: exactly one validated `analysis` object in the pipeline payload and a report method line naming the mode.
- Quality pipeline value: `{"mode": "quality", "agents": ["spec-analyzer", "code-analyzer"]}` when both succeed; omit only the failed analyzer from that list when partial-result handling applies.
- Economy pipeline value: `{"mode": "economy", "agents": ["spec-analyzer"]}`.

- [ ] **Step 1: Write the command contract before changing orchestration**

  At the top of `skills/new/SKILL.md`, directly below `Input:`, add this exact contract:

  ```markdown
  Mode: optionally begin $ARGUMENTS with exactly `--mode quality` or
  `--mode economy`; remove that pair before treating the remaining arguments as
  sources. More than one `--mode`, a missing value, or any other value is an
  input error: stop before intake, agent dispatch, or CALC. With no mode flag,
  obtain a mode choice in step 2; do not select a mode by default.
  ```

- [ ] **Step 2: Replace intake and analysis steps with the mode-aware flow**

  Replace steps 1–4 in `skills/new/SKILL.md` with instructions that do all of
  the following in this order:

  1. Validate/remove the optional mode pair, then check all remaining paths
     exist without reading their contents.
  2. When no explicit mode exists, make one `AskUserQuestion` call that asks
     both (a) `quality` versus `economy`, and (b) whether to include the
     AI-assisted view. If mode remains unanswered, stop and request the mode;
     AI-view non-response retains the existing default of included.
  3. For `quality`, dispatch `estimate:spec-analyzer` and
     `estimate:code-analyzer` in one message, once each, with the full batch
     sources. For `economy`, dispatch only `estimate:spec-analyzer` once with
     those sources and explicitly prohibit any codebase scan.
  4. Record only successful analyzer names in `analysis.agents`. In quality
     mode, preserve the current partial-result/Risks behavior if one analyzer
     fails. In economy mode, stop if `spec-analyzer` fails.
  5. Perform the current gap check after the selected analysis. In economy
     mode, add the fixed code-impact assumption and risk for every existing
     code task and widen its raw `P` before pipeline correction.

- [ ] **Step 3: Pass provenance once and make reporting unambiguous**

  In the Step 7 pipeline payload instructions, require:

  ```markdown
  - `analysis`: `{ "mode": "quality", "agents": ["spec-analyzer",
    "code-analyzer"] }` when both quality analyzers succeed, or the same
    object with only the successful quality analyzer; economy always uses
    `{ "mode": "economy", "agents": ["spec-analyzer"] }`. Do not invent
    agent names. This is required even when a quality-mode analyzer failed and
    the result is partial.
  ```

  In Step 8, require that `## 見積もり手法` contains either
  `- 解析モード: quality` or `- 解析モード: economy`, copied from
  `pipeline.analysis.mode`. For economy reports, require these exact Japanese entries in the designated
  sections:

  ```markdown
  ## 前提条件
  - 実装複雑度はリポジトリ影響分析なしで見積もった。

  ## リスク
  | リスク | 影響 | 対応 |
  |---|---|---|
  | 隠れた結合・統合点・既存テスト範囲が未検証 | 工数がPを超過する可能性 | 実装前にコード影響分析を実施する |
  ```

  Add the mode placeholder and the same economy-only section rules to
  `skills/new/references/report-template.md`, immediately after the existing
  task-correlation line and in the Section notes. Add an `## Analysis mode`
  subsection to `skills/estimation-methodology/SKILL.md` stating that economy
  mode must widen `P` for code-affecting work and cannot claim code coverage
  or coupling evidence.

- [ ] **Step 4: Review the skill as executable instructions**

  Run:

  ```bash
  rg -n -- "--mode|quality|economy|analysis\.agents|リポジトリ影響分析なし|隠れた結合" \
    skills/new/SKILL.md \
    skills/new/references/report-template.md \
    skills/estimation-methodology/SKILL.md
  ```

  Expected: the search finds the explicit forms, no-default rule, one-time
  dispatch rules, pipeline provenance, and both required economy caveats.

  Manually inspect the steps to confirm the agent dispatch block appears once
  and that it has one quality branch and one economy branch; no loop over WBS
  tasks may dispatch an analyzer.

- [ ] **Step 5: Commit the orchestration contract**

  ```bash
  git add skills/new/SKILL.md skills/new/references/report-template.md \
    skills/estimation-methodology/SKILL.md
  git commit -m "feat: add quality and economy estimate modes"
  ```

### Task 3: Publish the new interface and verify the release asset set

**Files:**
- Modify: `README.md:31-58, 65-98`
- Modify: `.claude-plugin/plugin.json:4`
- Modify: `CHANGELOG.md:7-17`

**Interfaces:**
- Consumes: the released mode names (`quality`, `economy`) and run-summary schema version 3.
- Produces: documented batch invocation examples and plugin version `0.3.0`.

- [ ] **Step 1: Document mode-aware batch usage**

  Replace the single estimate example in `README.md` with these examples and
  prose explaining that one invocation is one batch:

  ```markdown
  /estimate:new --mode quality docs/spec.md docs/tasks.md
  /estimate:new --mode economy docs/spec.md docs/tasks.md
  ```

  State that quality runs requirement and repository analysis once for the
  full batch, while economy runs requirement analysis only and marks code
  impact as unverified. State that passing fifteen related tasks in one
  invocation avoids repeating shared analysis; fifteen independent commands
  remain fifteen batches. Add `analysis.mode` and `analysis.agents` to the
  run-summary field description and state that schema version 3 introduced
  them.

- [ ] **Step 2: Update release metadata**

  Change `.claude-plugin/plugin.json` from `"version": "0.2.0"` to
  `"version": "0.3.0"`. Under `## [Unreleased]` in `CHANGELOG.md`, add:

  ```markdown
  ### Added
  - `/estimate:new` now offers `quality` and `economy` analysis modes. Both
    analyse a related task batch once; quality uses the specification and
    codebase analyzers, while economy uses only the specification analyzer and
    records mandatory code-impact caveats.
  - Run-summary schema version 3 records `analysis.mode` and
    `analysis.agents`, making the evidence coverage of every new estimate
    machine-readable.
  ```

- [ ] **Step 3: Run release checks**

  Run:

  ```bash
  python3 -m pytest tests/
  git diff --check
  rg -n '"version": "0\.3\.0"|RUN_SCHEMA_VERSION = 3|schema version 3|--mode quality|--mode economy' \
    .claude-plugin/plugin.json scripts/estimate_calc.py README.md CHANGELOG.md
  git status --short
  ```

  Expected: the complete suite passes, the diff has no whitespace errors, all
  release markers are present, and the status lists only the intended source,
  test, documentation, and metadata changes.

- [ ] **Step 4: Commit the release documentation and metadata**

  ```bash
  git add README.md .claude-plugin/plugin.json CHANGELOG.md
  git commit -m "docs: document estimation analysis modes"
  ```
