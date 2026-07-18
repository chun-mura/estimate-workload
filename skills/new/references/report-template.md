# Report template (canonical)

The estimate report has a FIXED structure. Reproduce the section order, the
heading text, and the WBS table columns below **verbatim** — do not translate,
renumber, merge, split, reorder, or add top-level sections. Only the content
inside each section is written freely (in Japanese).

Rationale: reports are compared across runs and parsed by `/estimate:record`.
A run-to-run difference in structure is a defect, not a style choice.

## Hard rules

1. **履歴ID must be the full task id from `pipeline`, copied verbatim** —
   e.g. `20260718T140458-e-ar-007-jido-henshin-fukusei-01`. Never abbreviate
   it to `01`, `-01`, or a slug-only form: `/estimate:record` feeds this
   string straight to `update-actual --id`, and a shortened id fails there.
2. **One number per column.** Do not merge O/M/P into a single `O/M/P` cell,
   and do not append units to cell values — the unit is in the column header.
3. **Never invent a run_id or a `.estimate/runs/` path.** Both come from the
   `pipeline` result. If `pipeline` did not return a `run_id`, there is no
   report to write — stop and report the failure instead.
4. Every `<placeholder>` below is replaced by a value returned by `pipeline`
   or written by you; no placeholder survives into the output.
5. The 見積もり手法 section states the reproduction conditions
   (`distribution`, `trials`, seed) from the `simulation` block of the run
   summary, so a reader can re-derive the percentiles rather than trust them.

## Template

```markdown
# 工数見積もり: <対象の名称>

- **run_id**: `<run_id>`
- **作成日**: <YYYY-MM-DD>
- **規模**: <size.label>（<size.basis>）

## サマリ

| 観点 | P50 | P80 |
|---|---|---|
| 従来型（時間） | <p50>h | <p80>h |
| 従来型（人日） | <p50_days>人日 | <p80_days>人日 |
| AI支援（時間） | <p50>h | <p80>h |
| AI支援（人日） | <p50_days>人日 | <p80_days>人日 |

<2〜4行で、何を見積もったか・結論・最大の不確実要因>

## WBS（作業分解）

| # | タスク | 履歴ID | カテゴリ | O (h) | M (h) | P (h) | 期待値 (h) | 根拠 |
|---|---|---|---|---|---|---|---|---|
| 1 | <verb-first task name> | `<run_id>-01` | <category> | <o> | <m> | <p> | <pert> | <complexity driver, one line> |

## 見積もり手法

- **P50**: 超過と不足が同確率。社内計画に使う
- **P80**: コミット水準。社外見積もりに使う
- タスク相関 rho = <correlation>（common-cause factor によるモンテカルロ）
- 解析モード: <pipeline.analysis.mode>
- O/M/P は <corrected: 参照クラス補正後 / uncorrected: 補正なしの生値> の値
- 分布 <distribution> / 試行 <trials> 回 / seed <traditional_seed>（再現条件は
  run summary の `simulation` に記録）

## 従来型見積もり

| 指標 | 時間 | 人日 |
|---|---|---|
| P50 | <p50>h | <p50_days>人日 |
| P80 | <p80>h | <p80_days>人日 |

## AI支援見積もり

| 指標 | 時間 | 人日 |
|---|---|---|
| P50 | <p50>h | <p50_days>人日 |
| P80 | <p80>h | <p80_days>人日 |

| カテゴリ | 係数 | 出典 |
|---|---|---|
| <category> | <ai_factor> | <learned / default> |

## 前提条件

- <未回答の論点を前提として1件1行。各行が P を広げた理由になっていること>

## リスク

| リスク | 影響 | 対応 |
|---|---|---|
| <risk> | <impact> | <mitigation> |

エージェント失敗・CALC の部分失敗があれば、必ずここに1行で記録する。

## スコープ外

- <この見積もりに含めていない作業>

## キャリブレーション

- 補正が適用されたタスク: <basis を明記。low_sample のものは「参考値」と注記>
- 補正がスキップされたタスク: <理由（insufficient_data 等）>

## フッター

- Machine-readable summary: `.estimate/runs/<run_id>.json`
- 実績記録: 完了後に `/estimate:record <run_id>` を実行
```

## Section notes

- **サマリ / 従来型 / AI支援** intentionally repeat the totals: the summary is
  the at-a-glance view, the two view sections carry the per-view detail
  (factor sources, day conversion). Keep both.
- When the user declined the AI-assisted view at intake, keep the
  `## AI支援見積もり` heading and replace its body with the single line
  `ユーザーの依頼により省略。` — and drop the AI rows from `## サマリ`.
- Copy `pipeline.analysis.mode` into `## 見積もり手法` as
  `- 解析モード: quality` or `- 解析モード: economy`. For `economy` only, add
  this exact line to `## 前提条件`:
  `- 実装複雑度はリポジトリ影響分析なしで見積もった。`
  Also add this exact row to the `## リスク` table:
  `| 隠れた結合・統合点・既存テスト範囲が未検証 | 工数がPを超過する可能性 | 実装前にコード影響分析を実施する |`.
- `## リスク` and `## スコープ外` are never omitted. If there is nothing to
  write, state `該当なし` rather than deleting the section.
