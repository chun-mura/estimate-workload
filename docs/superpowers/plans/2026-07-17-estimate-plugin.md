# `estimate` Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the public Claude Code plugin `estimate`: WBS decomposition + 3-point estimation with Monte Carlo aggregation + reference-class anchoring/correction from per-project accumulated actuals.

**Architecture:** Two user-invoked skills (`/estimate:new`, `/estimate:record`) orchestrate two read-only analysis agents and one stdlib-only Python script. The script (`scripts/estimate_calc.py`) is the single choke point for ALL statistics and ALL `.estimate/history.jsonl` I/O — prompts never do arithmetic or touch the history file directly. A methodology skill holds the estimation knowledge (WBS rules, 3-point guidance, category taxonomy, AI-assistance factors).

**Tech Stack:** Claude Code plugin (skills/agents layout), Python 3 stdlib only (argparse, json, random, statistics, os, tempfile), unittest.

**Spec:** `docs/superpowers/specs/2026-07-17-estimate-plugin-design.md` (approved 2026-07-17).

## Global Constraints

- Python stdlib only — no pip installs, no third-party imports.
- All plugin content (skills, agents, README) in English. Estimation reports follow the conversation language (instruction inside skills).
- Prompts must never do freehand arithmetic or freehand edits of `.estimate/history.jsonl`; every computation and history read/write goes through `estimate_calc.py`.
- History schema: `schema_version: 1`. Effort unit: hours.
- Fixed category taxonomy in v1: `backend-api`, `frontend-ui`, `db-migration`, `infra`, `test-only`, `docs`.
- Reference-class correction requires ≥ 5 similar completed records; otherwise skipped with notice (anchors may still be returned).
- Monte Carlo: triangular distribution per task, default 10,000 trials, seedable.
- `.estimate/config.json` supports `hours_per_day` only in v1.
- Plugin name `estimate`; user-invoked skills are `skills/new/SKILL.md` and `skills/record/SKILL.md` (NOT the legacy `commands/` layout).
- Only `plugin.json` goes inside `.claude-plugin/`; all component directories at plugin root.
- Commit after every task. Commit messages in English, explaining the why.

## File Structure

```
estimate-workload/                  (repo root = plugin root)
├── .claude-plugin/plugin.json      # manifest (Task 1)
├── scripts/estimate_calc.py        # all math + history I/O (Tasks 2–6)
├── tests/test_estimate_calc.py     # unittest suite (Tasks 2–6)
├── skills/
│   ├── estimation-methodology/
│   │   ├── SKILL.md                # method reference (Task 7)
│   │   └── references/
│   │       ├── category-taxonomy.md        (Task 7)
│   │       ├── ai-assistance-factors.md    (Task 7)
│   │       └── worked-example.md           (Task 7)
│   ├── new/SKILL.md                # /estimate:new orchestration (Task 9)
│   └── record/SKILL.md             # /estimate:record flow (Task 10)
├── agents/
│   ├── spec-analyzer.md            # (Task 8)
│   └── code-analyzer.md            # (Task 8)
└── README.md                       # (Task 11)
```

---

### Task 1: Plugin scaffold

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `README.md` (stub — completed in Task 11)

**Interfaces:**
- Produces: plugin namespace `estimate`; all later skills/agents load under it.

- [ ] **Step 1: Create the manifest**

`.claude-plugin/plugin.json`:

```json
{
  "name": "estimate",
  "description": "Scientifically-grounded effort estimation: WBS decomposition, 3-point estimates with Monte Carlo aggregation, and reference-class calibration that improves as you record actuals.",
  "version": "0.1.0",
  "author": {
    "name": "Kohki Nakamura"
  },
  "license": "MIT"
}
```

- [ ] **Step 2: Create README stub**

`README.md`:

```markdown
# estimate — effort estimation plugin for Claude Code

Work in progress. See `docs/superpowers/specs/2026-07-17-estimate-plugin-design.md`.
```

- [ ] **Step 3: Validate**

Run: `claude plugin validate .`
Expected: exit 0, reports the plugin manifest is valid.

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin README.md
git commit -m "feat: scaffold estimate plugin manifest"
```

---

### Task 2: estimate_calc.py — CLI skeleton, percentile helper, `simulate`

**Files:**
- Create: `scripts/estimate_calc.py`
- Create: `tests/test_estimate_calc.py`

**Interfaces:**
- Produces (used by all later tasks):
  - `class CalcError(Exception)` — all validation/user errors.
  - `percentile(values: list[float], q: float) -> float` — linear interpolation.
  - `pert_mean(o, m, p) -> float` — `(o + 4m + p) / 6`, rounded 2 decimals.
  - `validate_three_point(task: dict, label: str) -> None` — raises `CalcError` unless `o`,`m`,`p` are non-negative finite numbers (bools rejected) with `o <= m <= p`.
  - `cmd_simulate(payload: dict) -> dict`.
  - `main(argv)` — subcommand dispatch; payload subcommands take `--input <file|->` (JSON), result JSON on stdout; on `CalcError` prints `{"error": ...}` to stderr and exits 1.
- CLI: `python3 scripts/estimate_calc.py simulate --input -` with payload `{"tasks": [{"name": str, "o": num, "m": num, "p": num, "factor"?: num}], "trials"?: int, "seed"?: int}` → `{"tasks": [{"name", "pert"}], "total": {"mean", "p50", "p80", "min", "max"}, "trials"}`. Optional `factor` (positive number, default 1) scales that task's o/m/p before simulation and before its reported `pert` — this is how the AI-assisted view is computed without freehand math.

- [ ] **Step 1: Write the failing tests**

`tests/test_estimate_calc.py`:

```python
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import estimate_calc as ec


class TestPercentile(unittest.TestCase):
    def test_median_odd(self):
        self.assertEqual(ec.percentile([3, 1, 2], 50), 2)

    def test_interpolates(self):
        self.assertEqual(ec.percentile([1, 2, 3, 4], 50), 2.5)

    def test_p80(self):
        self.assertAlmostEqual(ec.percentile([1, 2, 3, 4, 5], 80), 4.2)

    def test_empty_raises(self):
        with self.assertRaises(ec.CalcError):
            ec.percentile([], 50)


class TestSimulate(unittest.TestCase):
    def payload(self, **over):
        base = {
            "tasks": [
                {"name": "a", "o": 4, "m": 8, "p": 16},
                {"name": "b", "o": 2, "m": 3, "p": 10},
            ],
            "trials": 2000,
            "seed": 42,
        }
        base.update(over)
        return base

    def test_pert_means(self):
        out = ec.cmd_simulate(self.payload())
        self.assertEqual(out["tasks"][0]["pert"], 8.67)
        self.assertEqual(out["tasks"][1]["pert"], 4.0)

    def test_seed_deterministic(self):
        a = ec.cmd_simulate(self.payload())
        b = ec.cmd_simulate(self.payload())
        self.assertEqual(a["total"], b["total"])

    def test_percentile_ordering_and_bounds(self):
        t = ec.cmd_simulate(self.payload())["total"]
        self.assertLessEqual(t["p50"], t["p80"])
        self.assertGreaterEqual(t["min"], 4 + 2)
        self.assertLessEqual(t["max"], 16 + 10)

    def test_degenerate_point_estimate(self):
        out = ec.cmd_simulate(
            {"tasks": [{"name": "x", "o": 5, "m": 5, "p": 5}], "trials": 10, "seed": 1}
        )
        self.assertEqual(out["total"]["p50"], 5)
        self.assertEqual(out["total"]["p80"], 5)

    def test_rejects_o_greater_than_m(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": [{"name": "x", "o": 9, "m": 8, "p": 16}]})

    def test_rejects_bool_and_negative(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": [{"name": "x", "o": True, "m": 8, "p": 16}]})
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": [{"name": "x", "o": -1, "m": 8, "p": 16}]})

    def test_rejects_empty_tasks(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": []})

    def test_factor_scales_task(self):
        out = ec.cmd_simulate(
            {"tasks": [{"name": "x", "o": 4, "m": 8, "p": 16, "factor": 0.5}],
             "trials": 200, "seed": 7}
        )
        self.assertEqual(out["tasks"][0]["pert"], 4.33)
        self.assertLessEqual(out["total"]["max"], 8)

    def test_rejects_bad_factor(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate(
                {"tasks": [{"name": "x", "o": 4, "m": 8, "p": 16, "factor": 0}]}
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'estimate_calc'`.

- [ ] **Step 3: Write the implementation**

`scripts/estimate_calc.py`:

```python
#!/usr/bin/env python3
"""All statistics and history-file I/O for the estimate plugin.

Skills and agents must never do arithmetic or edit .estimate/history.jsonl
directly; this script is the single choke point for math, schema
validation, ID generation, locking, and version handling.

Contract: `estimate_calc.py <subcommand> --input <file|->` reads a JSON
payload, writes a JSON result to stdout, and on error writes
{"error": "..."} to stderr and exits 1. `update-actual` takes flags
instead of a payload.
"""
import argparse
import json
import math
import os
import random
import statistics
import sys

SCHEMA_VERSION = 1
KNOWN_SCHEMA_VERSIONS = {1}
CATEGORIES = {"backend-api", "frontend-ui", "db-migration", "infra", "test-only", "docs"}
DEFAULT_TRIALS = 10_000


class CalcError(Exception):
    """User-facing validation or state error."""


def percentile(values, q):
    """Linear-interpolated percentile of values, q in [0, 100]."""
    if not values:
        raise CalcError("percentile of empty list")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def pert_mean(o, m, p):
    return round((o + 4 * m + p) / 6.0, 2)


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_three_point(task, label):
    for key in ("o", "m", "p"):
        v = task.get(key)
        if not _is_number(v) or v < 0:
            raise CalcError(f"{label}: '{key}' must be a non-negative finite number")
    if not task["o"] <= task["m"] <= task["p"]:
        raise CalcError(f"{label}: requires o <= m <= p")


def cmd_simulate(payload):
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("simulate: 'tasks' must be a non-empty list")
    scaled = []
    for i, t in enumerate(tasks):
        validate_three_point(t, f"tasks[{i}]")
        factor = t.get("factor", 1)
        if not _is_number(factor) or factor <= 0:
            raise CalcError(f"tasks[{i}]: 'factor' must be a positive number")
        scaled.append(
            {"name": t.get("name", ""), "o": t["o"] * factor,
             "m": t["m"] * factor, "p": t["p"] * factor}
        )
    trials = payload.get("trials", DEFAULT_TRIALS)
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise CalcError("simulate: 'trials' must be a positive integer")
    rng = random.Random(payload.get("seed"))
    totals = []
    for _ in range(trials):
        total = 0.0
        for t in scaled:
            if t["o"] == t["p"]:
                total += t["o"]
            else:
                total += rng.triangular(t["o"], t["p"], t["m"])
        totals.append(total)
    return {
        "tasks": [
            {"name": t["name"], "pert": pert_mean(t["o"], t["m"], t["p"])}
            for t in scaled
        ],
        "total": {
            "mean": round(statistics.fmean(totals), 2),
            "p50": round(percentile(totals, 50), 2),
            "p80": round(percentile(totals, 80), 2),
            "min": round(min(totals), 2),
            "max": round(max(totals), 2),
        },
        "trials": trials,
    }


def _load_payload(spec):
    if spec == "-":
        return json.load(sys.stdin)
    with open(spec, encoding="utf-8") as fh:
        return json.load(fh)


PAYLOAD_COMMANDS = {
    "simulate": cmd_simulate,
}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="estimate_calc")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in PAYLOAD_COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("--input", default="-", help="JSON payload file, or - for stdin")
    args = parser.parse_args(argv)
    try:
        result = PAYLOAD_COMMANDS[args.cmd](_load_payload(args.input))
    except CalcError as exc:
        json.dump({"error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    except json.JSONDecodeError as exc:
        json.dump({"error": f"invalid JSON payload: {exc}"}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover tests -v`
Expected: all PASS.

- [ ] **Step 5: Smoke-test the CLI**

Run: `echo '{"tasks":[{"name":"a","o":4,"m":8,"p":16}],"trials":100,"seed":1}' | python3 scripts/estimate_calc.py simulate --input -`
Expected: one-line JSON with `"pert": 8.67` and a `"total"` object.

- [ ] **Step 6: Commit**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: Monte Carlo simulate subcommand with percentile helper"
```

---

### Task 3: History reader + `append-history`

**Files:**
- Modify: `scripts/estimate_calc.py`
- Modify: `tests/test_estimate_calc.py`

**Interfaces:**
- Consumes: `CalcError`, `pert_mean`, `validate_three_point`, `_is_number`, `KNOWN_SCHEMA_VERSIONS`, `CATEGORIES`, `PAYLOAD_COMMANDS`.
- Produces:
  - `read_history(path) -> tuple[list[dict], list[dict]]` — (valid records, warnings). Missing file → `([], [])`. Each warning: `{"line": int, "kind": "parse_error"|"schema_violation", "detail": str}`. Distinguishes JSON parse failures from schema violations; skips records with unknown (future) `schema_version` as schema violations; ignores unknown extra fields.
  - `schema_error(rec: dict) -> str | None` — None when valid.
  - `cmd_append_history(payload) -> dict` — payload `{"history_path": str, "slug": str, "tasks": [{"task": str, "category": str, "tags": [str], "o": num, "m": num, "p": num}]}` → `{"run_id": str, "appended": int}`. Stamps `schema_version`, `run_id` (`YYYYMMDDTHHMMSS-<slug>`, de-duplicated against existing run_ids with `-2`, `-3`… suffix), sequential ids `<run_id>-NN`, `date`, computed `pert`, `actual: null`, `ai_assisted: null`, `status: "estimated"`. Single `O_APPEND` write.
- History record schema (one JSONL line): `schema_version` int; `run_id`, `id`, `date`, `task` non-empty str; `category` in CATEGORIES; `tags` list of str; `o`,`m`,`p` valid 3-point; `pert` number; `actual` null or positive number; `ai_assisted` null or bool; `status` in {"estimated","done"}.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_estimate_calc.py`:

```python
class HistoryBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, ".estimate", "history.jsonl")
        self.addCleanup(self.dir.cleanup)

    def append(self, slug="feat", tasks=None):
        tasks = tasks or [
            {"task": "Add endpoint", "category": "backend-api", "tags": ["auth"],
             "o": 4, "m": 8, "p": 16},
        ]
        return ec.cmd_append_history(
            {"history_path": self.path, "slug": slug, "tasks": tasks}
        )

    def raw_lines(self):
        with open(self.path, encoding="utf-8") as fh:
            return [l for l in fh.read().splitlines() if l.strip()]


class TestAppendHistory(HistoryBase):
    def test_appends_stamped_records(self):
        out = self.append()
        self.assertEqual(out["appended"], 1)
        rec = json.loads(self.raw_lines()[0])
        self.assertEqual(rec["schema_version"], 1)
        self.assertEqual(rec["run_id"], out["run_id"])
        self.assertEqual(rec["id"], out["run_id"] + "-01")
        self.assertEqual(rec["status"], "estimated")
        self.assertIsNone(rec["actual"])
        self.assertIsNone(rec["ai_assisted"])
        self.assertEqual(rec["pert"], 8.67)

    def test_same_second_reruns_get_distinct_run_ids(self):
        a = self.append()
        b = self.append()
        self.assertNotEqual(a["run_id"], b["run_id"])
        ids = [json.loads(l)["id"] for l in self.raw_lines()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rejects_unknown_category(self):
        with self.assertRaises(ec.CalcError):
            self.append(tasks=[{"task": "x", "category": "nope", "tags": [],
                                "o": 1, "m": 2, "p": 3}])

    def test_rejects_bad_three_point(self):
        with self.assertRaises(ec.CalcError):
            self.append(tasks=[{"task": "x", "category": "docs", "tags": [],
                                "o": 5, "m": 2, "p": 3}])


class TestReadHistory(HistoryBase):
    def test_missing_file_is_empty_not_error(self):
        records, warnings = ec.read_history(self.path)
        self.assertEqual(records, [])
        self.assertEqual(warnings, [])

    def test_distinguishes_parse_and_schema_warnings(self):
        self.append()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
            fh.write(json.dumps({"schema_version": 1, "id": "x"}) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 1)
        kinds = sorted(w["kind"] for w in warnings)
        self.assertEqual(kinds, ["parse_error", "schema_violation"])

    def test_future_schema_version_skipped_with_warning(self):
        self.append()
        rec = json.loads(self.raw_lines()[0])
        rec["schema_version"] = 999
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 1)
        self.assertEqual(warnings[0]["kind"], "schema_violation")

    def test_unknown_extra_fields_tolerated(self):
        self.append()
        rec = json.loads(self.raw_lines()[0])
        rec["id"] = rec["id"] + "-extra"
        rec["future_field"] = {"x": 1}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 2)
        self.assertEqual(warnings, [])
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m unittest discover tests -v`
Expected: new tests FAIL with `AttributeError: module 'estimate_calc' has no attribute 'cmd_append_history'` (and `read_history`); Task 2 tests still PASS.

- [ ] **Step 3: Write the implementation**

Add to `scripts/estimate_calc.py` (after `cmd_simulate`; also add `from datetime import datetime` to the imports):

```python
def schema_error(rec):
    if not isinstance(rec, dict):
        return "record is not an object"
    sv = rec.get("schema_version")
    if sv not in KNOWN_SCHEMA_VERSIONS:
        return f"unknown schema_version: {sv!r}"
    for key in ("run_id", "id", "date", "task"):
        if not isinstance(rec.get(key), str) or not rec[key]:
            return f"'{key}' must be a non-empty string"
    if rec.get("category") not in CATEGORIES:
        return f"unknown category: {rec.get('category')!r}"
    tags = rec.get("tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        return "'tags' must be a list of strings"
    try:
        validate_three_point(rec, "record")
    except CalcError as exc:
        return str(exc)
    if not _is_number(rec.get("pert")):
        return "'pert' must be a number"
    actual = rec.get("actual")
    if actual is not None and (not _is_number(actual) or actual <= 0):
        return "'actual' must be null or a positive number"
    ai = rec.get("ai_assisted")
    if ai is not None and not isinstance(ai, bool):
        return "'ai_assisted' must be null or a boolean"
    if rec.get("status") not in ("estimated", "done"):
        return f"unknown status: {rec.get('status')!r}"
    return None


def read_history(path):
    """Return (valid_records, warnings); missing file means no history yet."""
    records, warnings = [], []
    if not os.path.exists(path):
        return records, warnings
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(
                    {"line": lineno, "kind": "parse_error", "detail": str(exc)}
                )
                continue
            err = schema_error(rec)
            if err:
                warnings.append(
                    {"line": lineno, "kind": "schema_violation", "detail": err}
                )
                continue
            records.append(rec)
    return records, warnings


def _existing_run_ids(path):
    run_ids = set()
    if not os.path.exists(path):
        return run_ids
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("run_id"), str):
                run_ids.add(rec["run_id"])
    return run_ids


def cmd_append_history(payload):
    path = payload.get("history_path")
    if not isinstance(path, str) or not path:
        raise CalcError("append-history: 'history_path' is required")
    slug = payload.get("slug")
    if not isinstance(slug, str) or not slug or not all(
        c.isalnum() or c == "-" for c in slug.lower()
    ):
        raise CalcError("append-history: 'slug' must be alphanumeric/hyphens")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("append-history: 'tasks' must be a non-empty list")
    for i, t in enumerate(tasks):
        label = f"tasks[{i}]"
        if not isinstance(t.get("task"), str) or not t["task"]:
            raise CalcError(f"{label}: 'task' must be a non-empty string")
        if t.get("category") not in CATEGORIES:
            raise CalcError(
                f"{label}: category {t.get('category')!r} not in {sorted(CATEGORIES)}"
            )
        tags = t.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
            raise CalcError(f"{label}: 'tags' must be a list of strings")
        validate_three_point(t, label)

    now = datetime.now()
    base = now.strftime("%Y%m%dT%H%M%S") + "-" + slug.lower()
    existing = _existing_run_ids(path)
    run_id, n = base, 2
    while run_id in existing:
        run_id = f"{base}-{n}"
        n += 1

    lines = []
    for i, t in enumerate(tasks, 1):
        rec = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "id": f"{run_id}-{i:02d}",
            "date": now.strftime("%Y-%m-%d"),
            "task": t["task"],
            "category": t["category"],
            "tags": t.get("tags", []),
            "o": t["o"],
            "m": t["m"],
            "p": t["p"],
            "pert": pert_mean(t["o"], t["m"], t["p"]),
            "actual": None,
            "ai_assisted": None,
            "status": "estimated",
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = ("\n".join(lines) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return {"run_id": run_id, "appended": len(lines)}
```

Register it in `PAYLOAD_COMMANDS`:

```python
PAYLOAD_COMMANDS = {
    "simulate": cmd_simulate,
    "append-history": cmd_append_history,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: append-history subcommand and tolerant history reader"
```

---

### Task 4: `update-actual`

**Files:**
- Modify: `scripts/estimate_calc.py`
- Modify: `tests/test_estimate_calc.py`

**Interfaces:**
- Consumes: `read_history` record shape, `CalcError`, `_is_number`.
- Produces:
  - `cmd_update_actual(history_path, task_id, actual, ai_assisted, lock_timeout=5.0) -> dict` → `{"updated": <record>}`. Validates `actual` is a positive finite number; sets `actual`, `ai_assisted` (bool), `status: "done"` on the matching `id`. Locking: `<history_path>.lock` created `O_CREAT|O_EXCL`, 0.1 s retry until timeout, then `CalcError`. Rewrite: temp file in same directory + `os.replace`; all non-matching lines (including corrupt ones) preserved byte-for-byte.
  - CLI: `python3 scripts/estimate_calc.py update-actual --history-path <p> --id <task-id> --actual <hours> --ai-assisted true|false`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_estimate_calc.py`:

```python
class TestUpdateActual(HistoryBase):
    def test_updates_matching_record(self):
        out = self.append()
        task_id = out["run_id"] + "-01"
        res = ec.cmd_update_actual(self.path, task_id, 6.5, True)
        self.assertEqual(res["updated"]["actual"], 6.5)
        self.assertIs(res["updated"]["ai_assisted"], True)
        self.assertEqual(res["updated"]["status"], "done")
        rec = json.loads(self.raw_lines()[0])
        self.assertEqual(rec["actual"], 6.5)

    def test_rejects_nonpositive_actual(self):
        out = self.append()
        task_id = out["run_id"] + "-01"
        for bad in (0, -3):
            with self.assertRaises(ec.CalcError):
                ec.cmd_update_actual(self.path, task_id, bad, False)

    def test_unknown_id_errors(self):
        self.append()
        with self.assertRaises(ec.CalcError):
            ec.cmd_update_actual(self.path, "nope-01", 5, False)

    def test_preserves_corrupt_lines_verbatim(self):
        out = self.append()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("{corrupt line\n")
        ec.cmd_update_actual(self.path, out["run_id"] + "-01", 5, False)
        self.assertIn("{corrupt line", self.raw_lines())

    def test_lock_contention_fails_fast(self):
        out = self.append()
        lock = self.path + ".lock"
        open(lock, "w").close()
        try:
            with self.assertRaises(ec.CalcError):
                ec.cmd_update_actual(
                    self.path, out["run_id"] + "-01", 5, False, lock_timeout=0.2
                )
        finally:
            os.remove(lock)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m unittest discover tests -v`
Expected: new tests FAIL with `AttributeError` on `cmd_update_actual`; earlier tests PASS.

- [ ] **Step 3: Write the implementation**

Add to `scripts/estimate_calc.py` (also add `import tempfile` and `import time` to the imports):

```python
def _acquire_lock(path, timeout):
    lock = path + ".lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise CalcError(
                    f"could not acquire {lock}; is another update running? "
                    "Remove the file if it is stale."
                )
            time.sleep(0.1)


def cmd_update_actual(history_path, task_id, actual, ai_assisted, lock_timeout=5.0):
    if not _is_number(actual) or actual <= 0:
        raise CalcError("update-actual: --actual must be a positive number of hours")
    if not os.path.exists(history_path):
        raise CalcError(f"update-actual: no history file at {history_path}")
    lock = _acquire_lock(history_path, lock_timeout)
    try:
        with open(history_path, encoding="utf-8") as fh:
            raw = fh.readlines()
        out_lines, updated = [], None
        for line in raw:
            rec = None
            stripped = line.strip()
            if stripped:
                try:
                    rec = json.loads(stripped)
                except json.JSONDecodeError:
                    rec = None
            if isinstance(rec, dict) and rec.get("id") == task_id:
                rec["actual"] = actual
                rec["ai_assisted"] = bool(ai_assisted)
                rec["status"] = "done"
                out_lines.append(json.dumps(rec, ensure_ascii=False) + "\n")
                updated = rec
            else:
                out_lines.append(line)
        if updated is None:
            raise CalcError(f"update-actual: no record with id {task_id!r}")
        dir_ = os.path.dirname(os.path.abspath(history_path))
        fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".history-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.writelines(out_lines)
            os.replace(tmp, history_path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return {"updated": updated}
    finally:
        os.remove(lock)
```

Extend `main()` — add the flag-based subparser before `parser.parse_args`, and dispatch:

```python
    p = sub.add_parser("update-actual")
    p.add_argument("--history-path", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--actual", type=float, required=True)
    p.add_argument("--ai-assisted", choices=["true", "false"], required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "update-actual":
            result = cmd_update_actual(
                args.history_path, args.id, args.actual, args.ai_assisted == "true"
            )
        else:
            result = PAYLOAD_COMMANDS[args.cmd](_load_payload(args.input))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: update-actual subcommand with lock and atomic rewrite"
```

---

### Task 5: `reference-class`

**Files:**
- Modify: `scripts/estimate_calc.py`
- Modify: `tests/test_estimate_calc.py`

**Interfaces:**
- Consumes: `read_history`, `percentile`, `CalcError`, `CATEGORIES`, `PAYLOAD_COMMANDS`.
- Produces: `cmd_reference_class(payload) -> dict`.
  - Payload: `{"history_path": str, "tasks": [{"name": str, "category": str, "tags": [str], "m"?: num, "p"?: num}], "min_records"?: int (default 5), "max_anchors"?: int (default 5)}`.
  - Per task result: `{"name", "anchors": [{"task","o","m","p","pert","actual","ai_assisted","tags"}], "correction"}`.
  - Similarity: completed records (`status=="done"`, `actual>0`, `pert>0`) in the same category, ranked by tag-overlap count desc (ties: newest `date` first).
  - `correction` when ≥ min_records same-category completed records: `{"count", "ratio_p50", "ratio_p80"}` from `actual/pert` ratios, plus `"corrected_m"`/`"corrected_p"` (`m*ratio_p50`, `p*ratio_p80`) only when the task provided `m`/`p`. Otherwise `{"skipped": "insufficient_data", "count": n}`. Anchors returned regardless.
  - Top level: `{"tasks": [...], "warnings": <read_history warnings>}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_estimate_calc.py`:

```python
def _done_record(i, category="backend-api", tags=(), pert=10.0, actual=10.0,
                 ai=False, date="2026-06-01"):
    return {
        "schema_version": 1, "run_id": f"r{i}", "id": f"r{i}-01", "date": date,
        "task": f"past task {i}", "category": category, "tags": list(tags),
        "o": pert * 0.5, "m": pert, "p": pert * 2, "pert": pert,
        "actual": actual, "ai_assisted": ai, "status": "done",
    }


class TestReferenceClass(HistoryBase):
    def write_done(self, records):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def test_insufficient_data_skips_correction_but_returns_anchors(self):
        self.write_done([_done_record(i, tags=["auth"]) for i in range(3)])
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": ["auth"]}],
        })
        entry = out["tasks"][0]
        self.assertEqual(entry["correction"], {"skipped": "insufficient_data", "count": 3})
        self.assertEqual(len(entry["anchors"]), 3)

    def test_correction_uses_ratio_percentiles(self):
        # actual/pert ratios: 1.0, 1.0, 1.0, 2.0, 2.0 -> p50 = 1.0
        recs = [_done_record(i, actual=10.0) for i in range(3)]
        recs += [_done_record(i + 3, actual=20.0) for i in range(2)]
        self.write_done(recs)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": [],
                       "m": 8, "p": 16}],
        })
        corr = out["tasks"][0]["correction"]
        self.assertEqual(corr["count"], 5)
        self.assertEqual(corr["ratio_p50"], 1.0)
        self.assertEqual(corr["corrected_m"], 8.0)
        self.assertEqual(corr["corrected_p"], round(16 * corr["ratio_p80"], 2))

    def test_anchors_ranked_by_tag_overlap(self):
        self.write_done([
            _done_record(1, tags=["auth", "rest"]),
            _done_record(2, tags=["ui"]),
            _done_record(3, tags=["auth"]),
        ])
        out = ec.cmd_reference_class({
            "history_path": self.path, "max_anchors": 2,
            "tasks": [{"name": "t", "category": "backend-api",
                       "tags": ["auth", "rest"]}],
        })
        anchors = out["tasks"][0]["anchors"]
        self.assertEqual(len(anchors), 2)
        self.assertEqual(anchors[0]["task"], "past task 1")

    def test_other_categories_excluded(self):
        self.write_done([_done_record(1, category="docs")])
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": []}],
        })
        self.assertEqual(out["tasks"][0]["anchors"], [])
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m unittest discover tests -v`
Expected: new tests FAIL with `AttributeError` on `cmd_reference_class`.

- [ ] **Step 3: Write the implementation**

Add to `scripts/estimate_calc.py`:

```python
def cmd_reference_class(payload):
    path = payload.get("history_path")
    if not isinstance(path, str) or not path:
        raise CalcError("reference-class: 'history_path' is required")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("reference-class: 'tasks' must be a non-empty list")
    min_records = payload.get("min_records", 5)
    max_anchors = payload.get("max_anchors", 5)
    records, warnings = read_history(path)
    done = [
        r for r in records
        if r["status"] == "done" and _is_number(r.get("actual"))
        and r["actual"] > 0 and r["pert"] > 0
    ]
    results = []
    for i, t in enumerate(tasks):
        if t.get("category") not in CATEGORIES:
            raise CalcError(
                f"reference-class: tasks[{i}] category {t.get('category')!r} unknown"
            )
        tags = set(t.get("tags") or [])
        same_cat = [r for r in done if r["category"] == t["category"]]
        ranked = sorted(
            same_cat,
            key=lambda r: (len(tags & set(r["tags"])), r["date"]),
            reverse=True,
        )
        anchors = [
            {k: r[k] for k in ("task", "o", "m", "p", "pert", "actual",
                               "ai_assisted", "tags")}
            for r in ranked[:max_anchors]
        ]
        entry = {"name": t.get("name", ""), "anchors": anchors}
        ratios = [r["actual"] / r["pert"] for r in same_cat]
        if len(ratios) < min_records:
            entry["correction"] = {"skipped": "insufficient_data", "count": len(ratios)}
        else:
            r50 = percentile(ratios, 50)
            r80 = percentile(ratios, 80)
            correction = {
                "count": len(ratios),
                "ratio_p50": round(r50, 2),
                "ratio_p80": round(r80, 2),
            }
            if _is_number(t.get("m")):
                correction["corrected_m"] = round(t["m"] * r50, 2)
            if _is_number(t.get("p")):
                correction["corrected_p"] = round(t["p"] * r80, 2)
            entry["correction"] = correction
        results.append(entry)
    return {"tasks": results, "warnings": warnings}
```

Register in `PAYLOAD_COMMANDS`: `"reference-class": cmd_reference_class,`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: reference-class subcommand for anchors and ratio correction"
```

---

### Task 6: `calibration` + `distribute`

**Files:**
- Modify: `scripts/estimate_calc.py`
- Modify: `tests/test_estimate_calc.py`

**Interfaces:**
- Consumes: `read_history`, `percentile`, `_is_number`, `PAYLOAD_COMMANDS`.
- Produces: `cmd_calibration(payload) -> dict`. Payload: `{"history_path": str}`.
  - No completed records → `{"skipped": "no_completed_records", "warnings": [...]}`.
  - Else `{"count", "ratio_p50", "ratio_mean", "bias", "by_category": {cat: {"count", "ratio_p50"}}, "ai_assistance_factors": {cat: {"factor", "ai_count", "human_count"}}, "warnings"}`.
  - `bias`: `"underestimating"` if overall ratio_p50 > 1.05, `"overestimating"` if < 0.95, else `"well_calibrated"`.
  - `ai_assistance_factors[cat]` only when the category has ≥ 3 done records with `ai_assisted: true` AND ≥ 3 with `ai_assisted: false`; `factor = round(p50(ai ratios) / p50(human ratios), 2)`.
- Also produces: `cmd_distribute(payload) -> dict` — splits a run-total actual across tasks proportionally to their PERT means, so `/estimate:record` never does freehand division. Payload: `{"total": num, "tasks": [{"id": str, "pert": num}]}` → `{"shares": [{"id", "actual"}]}`. Shares in 0.1 h units via largest-remainder allocation (floor each proportional share, hand leftover units to largest fractional remainders) so every share is >= 0 and the sum equals `round(total, 1)` exactly. `total` must be positive; every `pert` must be > 0. (Amended from remainder-on-last during execution: that rule could produce a negative final share; user approved the change.)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_estimate_calc.py`:

```python
class TestCalibration(TestReferenceClass):
    def test_no_completed_records(self):
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["skipped"], "no_completed_records")

    def test_bias_detection(self):
        self.write_done([_done_record(i, actual=15.0) for i in range(4)])  # ratio 1.5
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["count"], 4)
        self.assertEqual(out["ratio_p50"], 1.5)
        self.assertEqual(out["bias"], "underestimating")
        self.assertEqual(out["by_category"]["backend-api"]["count"], 4)

    def test_ai_factor_requires_three_of_each(self):
        recs = [_done_record(i, actual=5.0, ai=True) for i in range(3)]      # 0.5
        recs += [_done_record(i + 3, actual=10.0, ai=False) for i in range(3)]  # 1.0
        self.write_done(recs)
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(
            out["ai_assistance_factors"]["backend-api"]["factor"], 0.5
        )

    def test_ai_factor_absent_when_sparse(self):
        recs = [_done_record(1, ai=True), _done_record(2, ai=False)]
        self.write_done(recs)
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["ai_assistance_factors"], {})


class TestDistribute(unittest.TestCase):
    def test_proportional_split_sums_to_total(self):
        out = ec.cmd_distribute({
            "total": 10,
            "tasks": [{"id": "a", "pert": 2.0}, {"id": "b", "pert": 6.0},
                      {"id": "c", "pert": 2.0}],
        })
        shares = {s["id"]: s["actual"] for s in out["shares"]}
        self.assertEqual(shares, {"a": 2.0, "b": 6.0, "c": 2.0})
        self.assertAlmostEqual(sum(shares.values()), 10)

    def test_rounding_remainder_lands_on_last(self):
        out = ec.cmd_distribute({
            "total": 10,
            "tasks": [{"id": "a", "pert": 1.0}, {"id": "b", "pert": 1.0},
                      {"id": "c", "pert": 1.0}],
        })
        self.assertAlmostEqual(sum(s["actual"] for s in out["shares"]), 10)

    def test_rejects_nonpositive_total_or_pert(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_distribute({"total": 0, "tasks": [{"id": "a", "pert": 1}]})
        with self.assertRaises(ec.CalcError):
            ec.cmd_distribute({"total": 5, "tasks": [{"id": "a", "pert": 0}]})
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m unittest discover tests -v`
Expected: new tests FAIL with `AttributeError` on `cmd_calibration`.

- [ ] **Step 3: Write the implementation**

Add to `scripts/estimate_calc.py`:

```python
def cmd_calibration(payload):
    path = payload.get("history_path")
    if not isinstance(path, str) or not path:
        raise CalcError("calibration: 'history_path' is required")
    records, warnings = read_history(path)
    done = [
        r for r in records
        if r["status"] == "done" and _is_number(r.get("actual"))
        and r["actual"] > 0 and r["pert"] > 0
    ]
    if not done:
        return {"skipped": "no_completed_records", "warnings": warnings}
    ratios = [r["actual"] / r["pert"] for r in done]
    p50 = percentile(ratios, 50)
    if p50 > 1.05:
        bias = "underestimating"
    elif p50 < 0.95:
        bias = "overestimating"
    else:
        bias = "well_calibrated"
    by_cat = {}
    for r in done:
        by_cat.setdefault(r["category"], []).append(r["actual"] / r["pert"])
    ai_factors = {}
    for cat in by_cat:
        ai = [r["actual"] / r["pert"] for r in done
              if r["category"] == cat and r["ai_assisted"] is True]
        human = [r["actual"] / r["pert"] for r in done
                 if r["category"] == cat and r["ai_assisted"] is False]
        if len(ai) >= 3 and len(human) >= 3:
            ai_factors[cat] = {
                "factor": round(percentile(ai, 50) / percentile(human, 50), 2),
                "ai_count": len(ai),
                "human_count": len(human),
            }
    return {
        "count": len(done),
        "ratio_p50": round(p50, 2),
        "ratio_mean": round(statistics.fmean(ratios), 2),
        "bias": bias,
        "by_category": {
            c: {"count": len(v), "ratio_p50": round(percentile(v, 50), 2)}
            for c, v in sorted(by_cat.items())
        },
        "ai_assistance_factors": ai_factors,
        "warnings": warnings,
    }
```

Also add `cmd_distribute`:

```python
def cmd_distribute(payload):
    total = payload.get("total")
    if not _is_number(total) or total <= 0:
        raise CalcError("distribute: 'total' must be a positive number")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("distribute: 'tasks' must be a non-empty list")
    for i, t in enumerate(tasks):
        if not isinstance(t.get("id"), str) or not t["id"]:
            raise CalcError(f"distribute: tasks[{i}] needs a non-empty 'id'")
        if not _is_number(t.get("pert")) or t["pert"] <= 0:
            raise CalcError(f"distribute: tasks[{i}] 'pert' must be > 0")
    pert_sum = sum(t["pert"] for t in tasks)
    shares = []
    allocated = 0.0
    for t in tasks[:-1]:
        share = round(total * t["pert"] / pert_sum, 1)
        shares.append({"id": t["id"], "actual": share})
        allocated += share
    shares.append({"id": tasks[-1]["id"], "actual": round(total - allocated, 1)})
    return {"shares": shares}
```

Register both in `PAYLOAD_COMMANDS`: `"calibration": cmd_calibration,` and `"distribute": cmd_distribute,`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover tests -v`
Expected: all PASS (note: `TestCalibration` inherits `write_done` from `TestReferenceClass`, so the parent's tests run twice — harmless).

- [ ] **Step 5: Commit**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: calibration and distribute subcommands"
```

---

### Task 7: Methodology skill

**Files:**
- Create: `skills/estimation-methodology/SKILL.md`
- Create: `skills/estimation-methodology/references/category-taxonomy.md`
- Create: `skills/estimation-methodology/references/ai-assistance-factors.md`
- Create: `skills/estimation-methodology/references/worked-example.md`

**Interfaces:**
- Produces: methodology text that `skills/new/SKILL.md` and `skills/record/SKILL.md` (Tasks 9–10) tell the model to read via `${CLAUDE_PLUGIN_ROOT}/skills/estimation-methodology/`.

- [ ] **Step 1: Write SKILL.md**

`skills/estimation-methodology/SKILL.md`:

```markdown
---
description: Estimation methodology reference for the estimate plugin — WBS decomposition rules, 3-point estimation guidance, reference-class anchoring and correction procedure, AI-assisted effort view. Read before producing or recording any estimate.
---

# Estimation Methodology

## Non-negotiable rules

1. **No freehand math.** Every aggregation, percentile, ratio, or correction is
   computed by `${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py`. If the script
   fails, stop and report the error — never substitute your own arithmetic.
2. **No freehand history edits.** `.estimate/history.jsonl` is only ever written
   by the script's `append-history` and `update-actual` subcommands. Never Read
   the raw file to make decisions when a subcommand can answer instead; never
   Write or Edit it.
3. **Show your uncertainty.** Estimates are ranges (P50/P80), never single numbers.
   Every assumption that widened a range is listed in the report.

## WBS decomposition rules

- Decompose each change unit into leaf tasks along the delivery phases it
  actually needs: design, implement, test, review, integrate. Skip phases that
  don't apply; don't pad.
- Leaf tasks should land between roughly 0.5 and 3 person-days (4–24 hours) of
  traditional effort. Split anything larger — large tasks hide unknowns and
  break reference-class matching.
- Every leaf task gets: a verb-first name, one `category` from
  `references/category-taxonomy.md`, and 1–4 lowercase `tags` (technology or
  domain nouns, e.g. `auth`, `rest`, `react`) that future runs can match on.

## 3-point estimation guidance

For each leaf task assign hours as:

- **O (optimistic):** everything goes right — you know the code, no rework,
  no review friction. ~5th percentile.
- **M (most likely):** the single most probable outcome, including normal
  friction (one review round, small surprises).
- **P (pessimistic):** serious-but-plausible trouble — hidden coupling, rework
  after review, environment issues. ~95th percentile. NOT a catastrophe bound.

Write a one-line rationale per task naming the main complexity driver.
When similar past tasks (anchors) are available, state O/M/P **relative to the
anchors' actuals**, not from scratch: "similar task X took 6h against a PERT of
8h" is stronger evidence than intuition.

Unanswered scoping questions do not block the estimate: record each one as an
assumption and widen P for the affected tasks.

## Reference-class procedure

1. Before assigning O/M/P, call `reference-class` with each task's
   category/tags to fetch anchors (similar completed tasks with their
   estimate vs. actual).
2. After assigning O/M/P, call `reference-class` again including `m` and `p`
   to get ratio-based corrections. Use `corrected_m`/`corrected_p` in place of
   your raw values when provided. Anchoring improves the raw estimate;
   correction removes residual bias — do both.
3. If correction is skipped (`insufficient_data`), say so in the report and
   note that ranges are uncorrected.

## Aggregation

Call `simulate` with the final per-task O/M/P. Report the total as:
- **P50** — "as likely over as under"; use for internal planning.
- **P80** — commitment-grade; use for external quotes.
Never present the sum of M values as "the estimate".

## Two effort views

Report BOTH, clearly labeled:
- **Traditional effort:** the simulated totals as-is, in hours and person-days
  (default 8 h/day; honor `.estimate/config.json` `hours_per_day` if present).
- **AI-assisted effort:** per-category multipliers applied to task hours before
  simulation. Use learned factors from `calibration` when a category has them;
  otherwise the defaults in `references/ai-assistance-factors.md`. State which
  source each factor came from.

## Report language

Write the estimation report in the language the user is conversing in.
```

- [ ] **Step 2: Write category-taxonomy.md**

`skills/estimation-methodology/references/category-taxonomy.md`:

```markdown
# Category taxonomy (fixed in v1)

Exactly one category per leaf task. The script rejects anything else.

| Category | Use for | Typical examples |
|---|---|---|
| `backend-api` | Server-side logic, endpoints, services, business rules | REST/GraphQL endpoint, background job, domain service |
| `frontend-ui` | Client-side UI and state | Component, page, form validation, styling |
| `db-migration` | Schema or data changes and their rollout | New table, column change, backfill script |
| `infra` | Build, deploy, environment, observability | CI pipeline, Dockerfile, IaC, monitoring |
| `test-only` | Test work not tied to a feature task | Regression suite, e2e scaffold, load test |
| `docs` | Documentation-only work | README, ADR, runbook, API docs |

Rules of thumb:
- A task spanning two categories is two tasks — split it.
- Choose by the dominant skill the work needs, not by which files change.
```

- [ ] **Step 3: Write ai-assistance-factors.md**

`skills/estimation-methodology/references/ai-assistance-factors.md`:

```markdown
# Default AI-assistance factors

Multiplier applied to a task's O/M/P hours to express effort when the developer
works with an agentic coding tool (Claude Code or similar). These defaults are
heuristics for cold start — once `calibration` returns a learned factor for a
category (requires ≥ 3 AI-assisted and ≥ 3 non-assisted completed records),
the learned factor wins.

| Category | Default factor | Why |
|---|---|---|
| `backend-api` | 0.45 | Well-specified CRUD/endpoint work automates well; review remains |
| `frontend-ui` | 0.55 | Generation is fast but visual verification stays manual |
| `db-migration` | 0.65 | Writing is fast; validation and rollout care dominate |
| `infra` | 0.70 | Feedback loops are slow and environment-specific |
| `test-only` | 0.40 | Test generation is a strong AI use case |
| `docs` | 0.35 | Drafting automates almost entirely; review remains |

The factor model is deliberately simple (hours × factor). It captures tool
leverage, not skill differences. Present AI-assisted totals as a planning view,
not a promise.
```

- [ ] **Step 4: Write worked-example.md**

`skills/estimation-methodology/references/worked-example.md`:

```markdown
# Worked example (abridged)

Input: "Add OAuth login to our Express app" + repo with existing session auth.

1. spec-analyzer returns one change unit: OAuth login (depends: session
   middleware; acceptance: login via Google, existing sessions unaffected).
2. code-analyzer returns: `src/auth/*` complexity mid, test coverage partial;
   integration point: session store.
3. WBS (leaf tasks):
   - "Implement OAuth callback endpoint" — backend-api, tags [auth, oauth]
   - "Wire provider config + secrets handling" — infra, tags [auth, config]
   - "Add login button + redirect flow" — frontend-ui, tags [auth]
   - "Integration tests for login flows" — test-only, tags [auth]
4. First reference-class call (category/tags only) returns anchors, e.g. a past
   backend-api [auth] task: pert 8 h → actual 11 h. Estimate the callback task
   relative to that: O=6, M=10, P=20.
5. Second reference-class call (with m, p) returns ratio_p50 1.2, ratio_p80 1.6
   → corrected_m 12, corrected_p 32. Use corrected values.
6. simulate over all corrected tasks → total p50 34 h, p80 46 h.
7. Report: traditional 34–46 h (4.3–5.8 person-days); AI-assisted view applies
   factors (0.45 backend, …) → p50 16 h, p80 22 h. Assumptions: provider is
   Google only. Skipped corrections noted where data was insufficient.
8. append-history writes 4 records with status "estimated".
```

- [ ] **Step 5: Validate and commit**

Run: `claude plugin validate .`
Expected: exit 0.

```bash
git add skills/estimation-methodology
git commit -m "feat: estimation methodology skill with taxonomy and AI factors"
```

---

### Task 8: Analysis agents

**Files:**
- Create: `agents/spec-analyzer.md`
- Create: `agents/code-analyzer.md`

**Interfaces:**
- Produces: agents invokable as `estimate:spec-analyzer` / `estimate:code-analyzer` (plugin-namespaced) from `/estimate:new`. Their fenced-JSON output contracts are consumed verbatim by Task 9's merge step.

- [ ] **Step 1: Write spec-analyzer.md**

`agents/spec-analyzer.md`:

```markdown
---
name: spec-analyzer
description: Extracts structured change units from requirements input (design docs, issues, free text) for effort estimation. Read-only analysis; returns a single JSON block.
tools: Read, Glob, Grep
---

You are a requirements analyst for effort estimation. You receive requirement
sources (file paths and/or pasted text). Read everything provided in full.

Extract WHAT has to change. Do not estimate hours, do not propose solutions,
do not invent scope that is not stated or clearly implied.

Return EXACTLY ONE fenced JSON block, no prose after it:

```json
{
  "change_units": [
    {
      "name": "short verb-first name",
      "description": "1-3 sentences of what changes and why",
      "dependencies": ["other change-unit names or external systems"],
      "acceptance_criteria": ["verifiable outcomes stated or implied"],
      "uncertainty_notes": ["ambiguities in the source affecting this unit"]
    }
  ],
  "out_of_scope": ["things the source explicitly excludes"],
  "open_questions": ["questions the requester must answer; empty if none"]
}
```

Rules:
- Every ambiguity goes into `uncertainty_notes` or `open_questions` — never
  resolve one silently.
- If a provided path cannot be read, list that in `open_questions` and continue
  with the rest.
- Change units should be independently deliverable slices, not phases.
```

- [ ] **Step 2: Write code-analyzer.md**

`agents/code-analyzer.md`:

```markdown
---
name: code-analyzer
description: Read-only codebase impact analysis for effort estimation — affected areas, complexity signals, test coverage, integration points. Returns a single JSON block.
tools: Read, Glob, Grep, Bash
---

You are a codebase analyst for effort estimation. You receive a change
description. Investigate the CURRENT repository (read-only — never modify
anything; use Bash only for read-only commands like `git log`, `wc -l`,
`ls`).

Assess WHERE the change lands and HOW HARD it is. Do not estimate hours.

Return EXACTLY ONE fenced JSON block, no prose after it:

```json
{
  "affected_areas": [
    {
      "path": "src/relative/path or glob",
      "change_type": "modify|extend|create|delete",
      "complexity": "low|mid|high",
      "test_coverage": "none|partial|good",
      "notes": "1-2 sentences: coupling, hotspots, gotchas"
    }
  ],
  "integration_points": ["external services, shared modules, contracts touched"],
  "repo_signals": {
    "size": "approx LOC or file count of affected scope",
    "language": "primary language(s)",
    "test_setup": "how tests are run here, or 'none found'"
  }
}
```

Rules:
- `complexity` reflects change difficulty in context (coupling, clarity,
  blast radius), not code size alone.
- If the repository is missing or empty, return empty `affected_areas` and say
  so in `repo_signals.size`.
- Base every claim on files you actually read — no guesses from names alone.
```

- [ ] **Step 3: Validate and commit**

Run: `claude plugin validate .`
Expected: exit 0.

```bash
git add agents
git commit -m "feat: spec-analyzer and code-analyzer agents with JSON output contracts"
```

---

### Task 9: `/estimate:new` skill

**Files:**
- Create: `skills/new/SKILL.md`

**Interfaces:**
- Consumes: agents from Task 8 (their JSON contracts), methodology skill from Task 7, script subcommands from Tasks 2–5 (`reference-class`, `simulate`, `append-history`).
- Produces: report at `docs/estimates/YYYY-MM-DD-<slug>.md`; history lines with status `estimated`; `run_id` surfaced to the user for later `/estimate:record`.

- [ ] **Step 1: Write SKILL.md**

`skills/new/SKILL.md`:

```markdown
---
description: Produce a scientifically-grounded effort estimate (WBS + 3-point + Monte Carlo + reference-class calibration) from any mix of design docs, issues, or free-text requirements, plus codebase analysis. Use when the user asks to estimate effort, workload, or delivery time for described work.
argument-hint: [file paths and/or a description of the work to estimate]
---

# /estimate:new

First read `${CLAUDE_PLUGIN_ROOT}/skills/estimation-methodology/SKILL.md` and its
`references/` files, and follow them exactly. CALC below means
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py"`. The history file is
`.estimate/history.jsonl` in the current project. If any CALC call fails, stop
and report its stderr — no freehand fallback.

Input: $ARGUMENTS (any mix of paths, pasted text, or a short description).

## Steps

1. **Intake.** Read every provided document. For each unreadable or missing
   path: tell the user, treat it as not provided, and carry the gap into
   step 2.
2. **Gap check.** If critical information is missing (scope boundary,
   definition of done, non-functional constraints), ask AT MOST 5 questions
   with the AskUserQuestion tool. Record every unanswered gap as an assumption;
   assumptions widen P in step 5.
3. **Parallel analysis.** In ONE message dispatch both agents:
   - `estimate:spec-analyzer` with all requirement sources.
   - `estimate:code-analyzer` with the change description — SKIP for
     greenfield (no repo/code).
   If an agent fails (error, timeout, output not matching its JSON contract),
   continue with the other's output, record the failure under Risks, and lower
   the stated confidence. Never silently proceed.
4. **WBS.** Merge per the methodology: spec view defines WHAT, code view
   defines WHERE/HOW HARD (code view wins on difficulty). Produce leaf tasks
   (0.5–3 person-days) each with category (fixed taxonomy) and tags.
5. **Anchored 3-point estimates.** Call CALC `reference-class` (tasks with
   name/category/tags only) to fetch anchors. Assign O/M/P per task per the
   methodology, anchored when anchors exist, with a one-line rationale.
6. **Correction.** Call CALC `reference-class` again, now including each
   task's `m` and `p`. Where it returns `corrected_m`/`corrected_p`, use them.
   Where skipped, note "uncorrected (insufficient data: N similar records)".
7. **Aggregate.** Call CALC `simulate` with the final O/M/P values
   (default trials). Then build the AI-assisted view: call CALC `simulate`
   again with the same tasks plus a per-task `"factor"` — the category's
   learned factor (from CALC `calibration`) when available, else the default
   from the methodology references. The script does the scaling; never
   multiply hours yourself.
8. **Persist — history FIRST, report second.**
   1. CALC `append-history` with slug (kebab-case from the work's name) and
      the final tasks. Keep the returned `run_id` and ids.
   2. Write the report to `docs/estimates/YYYY-MM-DD-<slug>.md`. If writing
      fails, print the full report in chat instead — history is already saved.
9. **Report.** In the conversation language. Must contain:
   - WBS table: task, history id, category, O/M/P, PERT mean (from
     `simulate`), rationale. (`/estimate:record` reads ids and PERT means
     back from this table — keep the columns.)
   - Traditional totals: P50 and P80 in hours AND person-days (8 h/day unless
     `.estimate/config.json` sets `hours_per_day`).
   - AI-assisted totals: P50/P80, with each factor's source (learned/default).
   - Assumptions, Risks (including any agent failure), Out of scope.
   - Calibration note: which corrections applied, which were skipped.
   - Footer: "Record actuals when done: `/estimate:record <run_id>`".
   The history file is authoritative; the report is a point-in-time snapshot
   and is never edited afterward.
```

- [ ] **Step 2: Validate and commit**

Run: `claude plugin validate .`
Expected: exit 0.

```bash
git add skills/new
git commit -m "feat: /estimate:new orchestration skill"
```

---

### Task 10: `/estimate:record` skill

**Files:**
- Create: `skills/record/SKILL.md`

**Interfaces:**
- Consumes: `update-actual` (Task 4), `calibration` and `distribute` (Task 6); history entries and the report footer (`run_id`) created by Task 9.
- Produces: history records flipped to `status: "done"`; calibration summary shown to user.

- [ ] **Step 1: Write SKILL.md**

`skills/record/SKILL.md`:

```markdown
---
description: Record actual hours against a previous /estimate:new run and show calibration (estimate vs actual bias). Use when the user reports completed work, actual time spent, or asks to log actuals.
argument-hint: [run_id (optional) — the id printed by /estimate:new]
---

# /estimate:record

CALC means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/estimate_calc.py"`. History
is `.estimate/history.jsonl` in the current project. Never read, parse, or
edit that file directly — writes happen only through CALC `update-actual`,
and splits only through CALC `distribute`. If a CALC call fails, stop and
report its stderr.

Input: $ARGUMENTS (optionally a run_id).

## Steps

1. **Identify the run.** Use the run_id from $ARGUMENTS. If absent, ask the
   user for it — it is printed in the footer of the estimate report under
   `docs/estimates/` (the user can also paste the report path; read the
   report file, not the history file, to find the run_id and task ids).
2. **Collect actuals.** For the run's tasks (ids `<run_id>-01`, `-02`, …, as
   listed in the report): ask the user for actual hours per task. If they only
   know the run total, call CALC `distribute` with the total and the tasks'
   `id`/`pert` values from the report, show the proposed split, and let the
   user adjust before writing. Also ask whether the work was AI-assisted
   (one answer per task, or one for the whole run).
3. **Write.** For each task: CALC `update-actual --history-path
   .estimate/history.jsonl --id <task-id> --actual <hours> --ai-assisted
   true|false`. Report each success or failure as it happens; an unknown id
   error usually means a typo in the run_id.
4. **Calibrate.** CALC `calibration` and present, in the conversation
   language: overall bias (under/over-estimating), ratio_p50, per-category
   ratios, and any learned AI-assistance factors now active. Encourage
   recording actuals every run — corrections activate at 5 similar completed
   records per category.
```

- [ ] **Step 2: Validate and commit**

Run: `claude plugin validate .`
Expected: exit 0.

```bash
git add skills/record
git commit -m "feat: /estimate:record skill for actuals and calibration"
```

---

### Task 11: README, full validation, dogfood

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the full README**

`README.md` — replace the stub with: what the plugin does (2 paragraphs:
method = WBS + 3-point + Monte Carlo + reference-class; improves with recorded
actuals), install (`/plugin marketplace add <repo>` once published; local dev
via `claude --plugin-dir .`), usage (`/estimate:new docs/spec.md`, then
`/estimate:record <run_id>`), data & privacy (everything stays in
`.estimate/history.jsonl` in your repo; commit it to share team calibration),
the two effort views and what P50/P80 mean, v1 limits (fixed taxonomy, no
hooks/MCP), versioning note (semver; history `schema_version` is
forward-compatible read). Keep it under 120 lines.

- [ ] **Step 2: Run the whole test suite**

Run: `python3 -m unittest discover tests -v`
Expected: all PASS.

- [ ] **Step 3: Validate the plugin**

Run: `claude plugin validate .`
Expected: exit 0, no warnings about structure.

- [ ] **Step 4: Dogfood end-to-end**

```bash
claude --plugin-dir . 
```
In the session:
1. `/estimate:new add a --json flag to estimate_calc.py that pretty-prints output`
2. Verify: report file created under `docs/estimates/`, `.estimate/history.jsonl` has `estimated` lines with run_id/ids, totals show P50/P80 + both views.
3. `/estimate:record <run_id>` with made-up actuals; verify records flip to `done` and a calibration summary prints.
4. Corrupt one history line manually, rerun `/estimate:new something small`; verify the warning surfaces and nothing crashes.

Expected: all four checks pass. Fix anything that fails before committing.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: complete README with install, usage, and data notes"
```

---

## Verification (whole plan)

1. `python3 -m unittest discover tests -v` — every subcommand's math, I/O,
   locking, validation, and tolerant reading is covered and green.
2. `claude plugin validate .` — plugin structure valid.
3. Dogfood scenario from Task 11 Step 4 — the real user journey works
   end-to-end including error surfacing.
4. `git log --oneline` — one commit per task, messages explain the why.
