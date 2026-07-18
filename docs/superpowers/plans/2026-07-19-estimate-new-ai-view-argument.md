# `estimate:new` AI支援表示オプション Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/estimate:new` の呼び出し時に、AI支援を考慮した見積もり表示の有無を引数で明示できるようにする。

**Architecture:** スキル文書内の先頭オプション解析契約を、既存の `--mode` 単独仕様から `--mode` とAI表示オプションの順不同な組み合わせへ拡張する。明示指定は intake の対話確認より優先し、未指定時の既存対話フローと、後続の `pipeline` 処理は維持する。

**Tech Stack:** Claude Code plugin skill Markdown、Python `unittest`（回帰確認のみ）。

## Global Constraints

- 先頭オプションは `--mode quality|economy`、`--ai-view`、`--no-ai-view` のみを受け付ける。
- `--mode` とAI表示オプションは順不同で併用できる。
- `--ai-view` / `--no-ai-view` の重複・併用、未知の先頭オプション、無効なモードは intake 前に停止する。
- AI表示が未指定のときだけ、既存の対話確認を行う。
- AI表示を含める場合だけ `ai-assistance-factors.md` を読む。
- Python計算ロジック、`pipeline` ペイロード形式、レポート形式、`estimate:record` は変更しない。
- スキル動作を変更するため、`.claude-plugin/plugin.json` のバージョンを `0.4.0` から `0.5.0` に上げ、CHANGELOGへ同じ変更を記録する。

---

### Task 1: AI表示オプション契約と利用文書を更新する

**Files:**
- Modify: `skills/new/SKILL.md:1-42`
- Modify: `README.md:43-52`
- Modify: `CHANGELOG.md:7-25`
- Modify: `.claude-plugin/plugin.json:4`
- Test: `tests/test_estimate_calc.py`

**Interfaces:**
- Consumes: `$ARGUMENTS` に含まれる先頭オプションと既存の `--mode` 契約。
- Produces: `mode`（`quality` / `economy` / 未指定）と `ai_view`（true / false / 未指定）の検証済み状態。未指定の `ai_view` だけがステップ2の質問対象となる。

- [ ] **Step 1: スキル契約の期待結果を文書化する**

`skills/new/SKILL.md` の `argument-hint` と Input の直後に、次の利用例と期待結果を記載する。

```markdown
Examples:
- `/estimate:new --mode quality --ai-view docs/spec.md` skips both intake choices.
- `/estimate:new --no-ai-view docs/spec.md` asks only for the mode.
- `/estimate:new docs/spec.md` keeps the existing mode-and-AI-view question.
```

併せて、`--mode quality --ai-view` が有効で、`--ai-view --no-ai-view` が intake 前の入力エラーになることを、契約文で明記する。

- [ ] **Step 2: 期待する契約が既存文書にはないことを確認する**

Run:

```bash
rg -n -- '--ai-view|--no-ai-view' skills/new/SKILL.md README.md CHANGELOG.md
```

Expected: exit 1。新しい引数名はまだ文書化されていない。

- [ ] **Step 3: 最小限のスキル文書変更を実装する**

`skills/new/SKILL.md` を次の契約に置き換える。

```markdown
Options: before sources, accept `--mode quality|economy`, `--ai-view`, and
`--no-ai-view` in any order. Remove all recognized options before treating
the remainder as sources. Each option may appear at most once; `--ai-view`
and `--no-ai-view` are mutually exclusive. A missing or invalid `--mode`
value, any duplicate or conflicting option, or an unknown leading `--...`
option is an input error: stop before intake, agent dispatch, or CALC.
```

ステップ1は全オプションを検証・除去するように更新する。ステップ2は、`ai_view` が未指定の場合のみ質問し、モードも未指定ならモードとAI表示を一回で質問するように更新する。`ai_view` が `true` なら係数参照を読み、`false` なら `pipeline` に既存どおり `ai_view: false` を渡す。

- [ ] **Step 4: README、CHANGELOG、バージョンを更新する**

`README.md` の Usage に次の例を追加する。

```text
/estimate:new --mode quality --ai-view docs/spec.md docs/tasks.md
/estimate:new --mode economy --no-ai-view docs/spec.md docs/tasks.md
```

`CHANGELOG.md` の `[Unreleased]` に `### Added` として、AI支援表示を
`--ai-view` / `--no-ai-view` で明示できることを1項目追加する。
`.claude-plugin/plugin.json` の `version` を `0.5.0` に変更する。

- [ ] **Step 5: 契約記述を検証する**

Run:

```bash
rg -n -- '--ai-view|--no-ai-view|0\.5\.0' skills/new/SKILL.md README.md CHANGELOG.md .claude-plugin/plugin.json
python3 -m unittest discover tests -v
git diff --check
```

Expected: 引数名がスキル・README・CHANGELOGに、`0.5.0` がマニフェストに存在する。ユニットテストはすべて成功し、`git diff --check` は出力なしで終了する。

- [ ] **Step 6: コミットする**

```bash
git add skills/new/SKILL.md README.md CHANGELOG.md .claude-plugin/plugin.json
git commit -m "feat: add AI view options to new estimates"
```
