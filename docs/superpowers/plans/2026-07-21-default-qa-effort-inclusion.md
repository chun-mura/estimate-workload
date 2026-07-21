# Default QA Effort Inclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Include applicable QA effort in every `/estimate:new` WBS unless the caller explicitly supplies `--no-qa`.

**Architecture:** The orchestration skill owns the new option and WBS policy; it adds explicit `test-only` QA leaf tasks before the existing calculator pipeline runs. The fixed report template records whether QA was included or excluded without changing its top-level structure. A lightweight contract test prevents the prompt-based interface from losing the default or opt-out behavior.

**Tech Stack:** Claude Code skill Markdown, Python `unittest`, pytest, JSON plugin manifest.

## Global Constraints

- QA includes test planning/case preparation, integrated-environment functional verification, integration/E2E/regression testing, and defect verification/retesting.
- Unit tests and in-development checks stay in implementation tasks and are never counted again as QA.
- `--no-qa` is the only opt-out; it is independent of `--mode` and `--ai-view` / `--no-ai-view`.
- QA leaf tasks use the existing `test-only` category and remain within the existing 0.5--3 person-day WBS guidance.
- Keep the fixed report section order and headings unchanged.
- Bump the plugin version and document the behavior in `CHANGELOG.md` whenever `skills/new/SKILL.md` changes.

---

### Task 1: Lock the QA option contract with an automated test

**Files:**
- Create: `tests/test_estimate_new_contract.py`
- Test: `tests/test_estimate_new_contract.py`

**Interfaces:**
- Consumes: `skills/new/SKILL.md` as the command contract.
- Produces: a regression test that requires default QA inclusion, the `--no-qa` option, the four QA activities, and a no-double-counting rule.

- [ ] **Step 1: Write the failing test**

```python
import pathlib
import unittest

SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "new" / "SKILL.md"

class TestEstimateNewQaContract(unittest.TestCase):
    def test_qa_is_default_and_can_only_be_explicitly_excluded(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("--no-qa", text)
        self.assertIn("QA is included by default", text)
        self.assertIn("Test planning and test-case preparation", text)
        self.assertIn("Functional verification in an integrated environment", text)
        self.assertIn("Integration, E2E, and regression testing", text)
        self.assertIn("Defect verification and retesting", text)
        self.assertIn("Unit tests and in-development checks remain part of implementation tasks", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_estimate_new_contract.py -v`  
Expected: FAIL because `--no-qa` and the QA policy text are absent from `skills/new/SKILL.md`.

- [ ] **Step 3: Keep production files unchanged**

Do not modify `skills/new/SKILL.md` in this task; the failure must prove the test detects the missing contract.

- [ ] **Step 4: Commit the red test**

Run: `git add tests/test_estimate_new_contract.py && git commit -m "test: define default QA estimate contract"`

### Task 2: Add default QA WBS behavior and explicit opt-out

**Files:**
- Modify: `skills/new/SKILL.md:3-35`
- Modify: `skills/new/SKILL.md:50-105`
- Modify: `skills/new/SKILL.md:130-150`
- Test: `tests/test_estimate_new_contract.py`

**Interfaces:**
- Consumes: the `--no-qa` command argument and the user-approved QA scope.
- Produces: `qa_included: true|false` orchestration state, `test-only` QA WBS tasks when true, and QA scope reporting instructions.

- [ ] **Step 1: Extend option resolution**

Add `--no-qa` to the front matter `argument-hint`, examples, and Options contract. Resolve `qa_included` as false only when `--no-qa` appears; otherwise resolve it as true. Reject duplicate `--no-qa`, and remove it before source intake.

- [ ] **Step 2: Add mandatory default QA leaf tasks**

In the WBS step, require applicable `test-only` tasks for: test planning and test-case preparation; functional verification in an integrated environment; integration, E2E, and regression testing; and defect verification and retesting. Require splitting or combining to preserve the existing 0.5--3 person-day rule. Add: `Unit tests and in-development checks remain part of implementation tasks and must not be counted again as QA.` When `qa_included` is false, prohibit adding these QA tasks.

- [ ] **Step 3: Add QA boundary reporting**

In the report-file step, require `## 前提条件` to state the default QA inclusion and list all four activities when `qa_included` is true. Require `## スコープ外` to state that `--no-qa` excluded the same activities when false.

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/test_estimate_new_contract.py -v`  
Expected: PASS with one passing test.

- [ ] **Step 5: Commit the behavior change**

Run: `git add skills/new/SKILL.md tests/test_estimate_new_contract.py && git commit -m "feat: include QA effort by default"`

### Task 3: Synchronize user documentation, template guidance, and release metadata

**Files:**
- Modify: `README.md:40-85`
- Modify: `skills/new/references/report-template.md:70-110`
- Modify: `.claude-plugin/plugin.json:4`
- Modify: `CHANGELOG.md:7-9`
- Test: `tests/test_estimate_new_contract.py`

**Interfaces:**
- Consumes: `qa_included` behavior from `skills/new/SKILL.md`.
- Produces: documented default and opt-out, fixed-template section guidance, plugin version `0.9.0`, and an Unreleased changelog entry.

- [ ] **Step 1: Update README**

Add `--no-qa` to the usage syntax. State that QA is included by default, enumerate the four activities, state that unit tests/development checks are not duplicated, and document `--no-qa` for separately budgeted or out-of-scope QA.

- [ ] **Step 2: Update template guidance**

Under `report-template.md` Section notes, direct reports to use `## 前提条件` for included QA and `## スコープ外` for explicit `--no-qa` exclusion. Do not add or rename top-level headings.

- [ ] **Step 3: Bump release metadata**

Change `.claude-plugin/plugin.json` from `0.8.1` to `0.9.0`. Under `## [Unreleased]` in `CHANGELOG.md`, add a `### 追加` entry describing default QA inclusion and `--no-qa`.

- [ ] **Step 4: Run full verification**

Run: `python3 -m pytest tests/ && jq -e . .claude-plugin/plugin.json > /dev/null && git diff --check`  
Expected: all tests pass, `jq` exits 0, and the whitespace check is silent.

- [ ] **Step 5: Commit documentation and metadata**

Run: `git add README.md skills/new/references/report-template.md .claude-plugin/plugin.json CHANGELOG.md && git commit -m "docs: document default QA estimate scope"`

## Final verification

- [ ] Run `python3 -m pytest tests/` and confirm every test passes.
- [ ] Run `jq -e . .claude-plugin/plugin.json > /dev/null` and confirm exit code 0.
- [ ] Run `git diff --check` and confirm no whitespace errors.
- [ ] Inspect `git status --short` and confirm no unintended files are staged or modified.
