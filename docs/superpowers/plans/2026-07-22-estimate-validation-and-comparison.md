# Estimate Validation and Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 見積もり入力の粒度異常を診断し、実行コンテキストを履歴化して、同一案件の再見積もりを安全に比較・照合できるようにする。

**Architecture:** `.estimate/history.jsonl` を唯一の永続先に保ち、v3の各タスクレコードへ同じ `run_context` と計算器生成の `run_summary` を保存する。計算器は警告と比較結果を構造化して返し、`/estimate:new` は照合ゲートと固定レポートへ反映する。v2は読み取り・実績記録・校正対象として維持する。

**Tech Stack:** Python 3標準ライブラリ、unittest、Markdown skill契約、JSONL。

## Global Constraints

- O/M/Pの単位は時間であり、人日は計算器出力だけを使う。
- Mが4h未満または24h超は警告であり、見積もりを拒否・補正しない。
- 履歴の書き込みは `estimate_calc.py` だけが行う。
- v2レコードを破棄・変換せず、v3を追加で受理する。
- スキル・スクリプト・エージェントを変更するコミットでは、プラグインバージョンとCHANGELOGを同時に更新する。

---

### Task 1: v3履歴コンテキストを定義・検証する

**Files:**
- Modify: `scripts/estimate_calc.py:24-190, 300-355, 526-649`
- Modify: `tests/test_estimate_calc.py:207-285, 570-770`

**Interfaces:**
- Produces: `validate_run_context(value) -> dict`
- Produces: v3 history record field `run_context: dict`
- Produces: v3 history record field `run_summary: dict`
- Consumes: `pipeline` payload field `run_context`

- [ ] **Step 1: 失敗テストを書く**

```python
def test_pipeline_rejects_invalid_v3_run_context_before_history_write(self):
    with self.assertRaisesRegex(ec.CalcError, "run_context.*comparison_key"):
        ec.cmd_pipeline(self.payload(run_context={}))
    self.assertFalse(os.path.exists(self.path))

def test_read_history_accepts_existing_v2_and_valid_v3_records(self):
    self.append()
    ec.cmd_pipeline(self.payload(run_context=VALID_CONTEXT))
    records, warnings = ec.read_history(self.path)
    self.assertEqual(len(records), 3)
    self.assertEqual(warnings, [])
    self.assertEqual(records[-1]["schema_version"], 3)
```

- [ ] **Step 2: 失敗を確認する**

Run: `python3 -m pytest tests/test_estimate_calc.py -k 'run_context or existing_v2' -v`  
Expected: FAIL（`run_context` が未検証・未保存）。

- [ ] **Step 3: 最小実装を追加する**

`SCHEMA_VERSION = 3`、`KNOWN_SCHEMA_VERSIONS = {2, 3}` とし、`validate_run_context()` を追加する。必須キーは `comparison_key`、`qa_included`、`ai_view`、`analysis_mode`、`hours_per_day`、`correlation`、`sources`、`scope`、`exclusions`、`dependencies`、`assumptions`。非空キー、bool、有限数、文字列配列を検証し、余分なキーは拒否する。

`schema_error()` はv3にだけcontextとsummaryを要求する。`cmd_pipeline()` は計算前にcontextを検証し、従来型シミュレーション後に `traditional` と `simulation` からsummaryを生成する。`cmd_append_history()` が各v3行へ同じcontextとsummaryを保存する。v2の`append-history`は変更しない。

- [ ] **Step 4: テストを通す**

Run: `python3 -m pytest tests/test_estimate_calc.py -k 'run_context or existing_v2' -v`  
Expected: PASS。

- [ ] **Step 5: コミットする**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: persist estimate run context"
```

### Task 2: 粒度診断をpipeline出力へ追加する

**Files:**
- Modify: `scripts/estimate_calc.py:80-100, 526-649`
- Modify: `tests/test_estimate_calc.py:570-770`

**Interfaces:**
- Produces: `granularity_warnings: list[dict]` in `cmd_pipeline()` result
- Warning shape: `{"task": str, "field": "m", "value": number, "kind": "below_recommended"|"above_recommended"}`

- [ ] **Step 1: 境界値テストを書く**

```python
def test_pipeline_returns_granularity_warning_without_blocking_history_write(self):
    tasks = [small_task(m=3), normal_task(m=4), normal_task(m=24), large_task(m=25)]
    out = ec.cmd_pipeline(self.payload(tasks=with_factors(tasks), run_context=VALID_CONTEXT))
    self.assertEqual([w["kind"] for w in out["granularity_warnings"]],
                     ["below_recommended", "above_recommended"])
    self.assertEqual(len(self.raw_lines()), 4)
```

- [ ] **Step 2: 失敗を確認する**

Run: `python3 -m pytest tests/test_estimate_calc.py -k granularity -v`  
Expected: FAIL（出力キーがない）。

- [ ] **Step 3: 最小実装を追加する**

`granularity_warnings(tasks)` を追加し、各入力タスクのMだけを検査して、`m < 4` と `m > 24` を入力順で返す。`cmd_pipeline()` の戻り値へ追加する。既存の `validate_three_point()`、補正、履歴追記の順序は変更しない。

- [ ] **Step 4: テストを通す**

Run: `python3 -m pytest tests/test_estimate_calc.py -k granularity -v`  
Expected: PASS。

- [ ] **Step 5: コミットする**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: report estimate granularity warnings"
```

### Task 3: `compare-runs` サブコマンドを実装する

**Files:**
- Modify: `scripts/estimate_calc.py:400-525, 692-730`
- Modify: `tests/test_estimate_calc.py:770-980`

**Interfaces:**
- Produces: `cmd_compare_runs(payload) -> dict`
- Payload: `{"history_path": str, "baseline_run_id": str, "candidate_run_id": str}`
- Result: `comparable`, `reason`, `context_diff`, `task_count`, `category_counts`, `m_summary`, `granularity_warning_count`, `totals`

- [ ] **Step 1: 比較の失敗・成功テストを書く**

```python
def test_compare_runs_reports_same_key_context_and_totals(self):
    baseline = ec.cmd_pipeline(self.payload(slug="base", run_context=VALID_CONTEXT))
    candidate = ec.cmd_pipeline(self.payload(slug="candidate", run_context=VALID_CONTEXT))
    out = ec.cmd_compare_runs({"history_path": self.path,
                               "baseline_run_id": baseline["run_id"],
                               "candidate_run_id": candidate["run_id"]})
    self.assertTrue(out["comparable"])
    self.assertEqual(out["context_diff"], {})

def test_compare_runs_marks_v2_or_different_key_not_comparable(self):
    legacy = self.append()
    candidate = ec.cmd_pipeline(self.payload(slug="candidate", run_context=VALID_CONTEXT))
    out = ec.cmd_compare_runs({"history_path": self.path,
                               "baseline_run_id": legacy["run_id"],
                               "candidate_run_id": candidate["run_id"]})
    self.assertFalse(out["comparable"])
    self.assertEqual(out["reason"], "missing_run_context")
```

- [ ] **Step 2: 失敗を確認する**

Run: `python3 -m pytest tests/test_estimate_calc.py -k compare_runs -v`  
Expected: FAIL（関数・CLI未登録）。

- [ ] **Step 3: 比較実装を追加する**

`read_history()`から二つのrunを収集し、contextとsummaryがrun内で一意であることを確認する。比較可能な場合だけ、summaryのP50/P80、タスクのO/M/P・期待値合計、カテゴリ別件数、Mのmin/median/max、粒度警告件数、contextの項目別差分を返す。タスク名の意味的同一性は判定しない。

`PAYLOAD_COMMANDS`に`"compare-runs": cmd_compare_runs`を追加する。

- [ ] **Step 4: テストを通す**

Run: `python3 -m pytest tests/test_estimate_calc.py -k compare_runs -v`  
Expected: PASS。

- [ ] **Step 5: コミットする**

```bash
git add scripts/estimate_calc.py tests/test_estimate_calc.py
git commit -m "feat: compare estimate runs"
```

### Task 4: `/estimate:new` の入力契約・照合ゲート・固定レポートを更新する

**Files:**
- Modify: `skills/new/SKILL.md:15-173`
- Modify: `skills/new/references/report-template.md:45-110`
- Modify: `tests/test_estimate_new_contract.py:1-30`
- Modify: `README.md:37-130`

**Interfaces:**
- Adds command option: `--compare-to <run-id>`
- Pipeline payload always includes validated `run_context`
- Comparison threshold: absolute P50 difference `>= 30%`

- [ ] **Step 1: スキル契約テストを書く**

```python
def test_skill_requires_hour_units_context_and_reconciliation_gate(self):
    text = SKILL.read_text(encoding="utf-8")
    for required in ("--compare-to", "comparison_key", "granularity_warnings",
                     "O/M/P の単位は時間", "30%", "楽観・標準・悲観"):
        self.assertIn(required, text)
```

- [ ] **Step 2: 失敗を確認する**

Run: `python3 -m pytest tests/test_estimate_new_contract.py -v`  
Expected: FAIL（新契約が未記載）。

- [ ] **Step 3: オーケストレーション契約を記述する**

`--compare-to`を既存オプションと同じ厳格な引数解析へ追加する。Step 1で`comparison_key`を明示IDとスコープ名から決め、Step 4でscope/exclusions/dependencies/assumptions/sourcesを収集し、Step 7のpipeline payloadへ渡す。比較対象指定時はpipeline後に`compare-runs`を一度呼ぶ。

差が30%以上または`context_diff`非空なら、レポート前にスコープ・前提・WBS対応を確認する。未解消なら、固定見出しを追加せず`## 前提条件`と`## リスク`へ楽観・標準・悲観の採用値と理由を記載する。テンプレートは時間単位、粒度警告、比較結果を既存セクション内へ記載する。READMEには`--compare-to`使用例とv2が比較不能である旨を追記する。

- [ ] **Step 4: 契約テストを通す**

Run: `python3 -m pytest tests/test_estimate_new_contract.py -v`  
Expected: PASS。

- [ ] **Step 5: コミットする**

```bash
git add skills/new/SKILL.md skills/new/references/report-template.md tests/test_estimate_new_contract.py README.md
git commit -m "feat: reconcile repeated estimates"
```

### Task 5: リリース整合性と回帰を完了する

**Files:**
- Modify: `.claude-plugin/plugin.json:4`
- Modify: `CHANGELOG.md:7-14`
- Modify: `tests/test_estimate_new_contract.py:1-50`
- Verify: `tests/test_estimate_calc.py`

**Interfaces:**
- Produces: plugin version `0.10.0`

- [ ] **Step 1: バージョン契約テストを書く**

`tests/test_estimate_new_contract.py`に、`plugin.json`が`0.10.0`であり、CHANGELOGに`0.10.0`、粒度診断、比較、v3履歴が記載されることを検証する。

- [ ] **Step 2: 失敗を確認する**

Run: `python3 -m pytest tests/test_estimate_new_contract.py -v`  
Expected: FAIL（バージョンと履歴が未更新）。

- [ ] **Step 3: リリースメタデータを更新する**

`plugin.json`を`0.10.0`に更新する。CHANGELOGの`[Unreleased]`に、粒度警告、v3 `run_context`、`compare-runs`、`--compare-to`、30%照合ゲート、v2後方互換を記載する。

- [ ] **Step 4: 全検証を実行する**

Run: `python3 -m pytest tests/ -v`  
Expected: PASS。

Run: `git diff --check`  
Expected: 出力なし。

- [ ] **Step 5: コミットする**

```bash
git add .claude-plugin/plugin.json CHANGELOG.md tests/test_estimate_new_contract.py
git commit -m "chore: release estimate validation safeguards"
```
