# テスト観点: シミュレーション再現条件の記録

対象: `scripts/estimate_calc.py` の未コミット差分
- `cmd_simulate`: seed の解決・検証、`distribution`/`seed` の返却
- `_validated_totals`: `p50_days`/`p80_days` の通し
- `cmd_run_summary`: `simulation` ブロックの検証と永続化、`RUN_SCHEMA_VERSION` 2 への更新
- `cmd_pipeline`: 両ビューの seed を `simulation` として run summary へ受け渡し

背景: seed 未指定の実行が run summary から再現できず、P80 の根拠を再検証できなかった。

---

## 1. 正常系

| # | 観点 | 優先度 | 状態 |
|---|---|---|---|
| 1.1 | seed 明示時、その値が `simulate` の返り値に echo される | must | カバー済み `test_echoes_the_caller_supplied_seed` |
| 1.2 | seed 未指定時、int の seed が生成され返る。同 seed の再実行で totals が一致 | must | カバー済み `test_generates_and_reports_a_seed_when_none_given` |
| 1.3 | `simulate` が実際にサンプリングした分布名 `triangular` を返す | must | カバー済み `test_reports_the_model_it_sampled` |
| 1.4 | `pipeline` の run summary に distribution/trials/correlation/hours_per_day/両 seed が入る | must | カバー済み `test_run_summary_records_how_the_simulation_was_run` |
| 1.5 | seed 未指定の `pipeline` 実行を run summary の値だけで replay し P50/P80 が一致 | must | カバー済み `test_unseeded_pipeline_run_stays_reproducible` |
| 1.6 | run summary が `p50_days`/`p80_days` を保持 | must | カバー済み `test_persists_person_days_when_supplied` |
| 1.7 | **`pipeline` の返り値自体が distribution と両 seed を含む** | **must** | **未カバー — 欠陥あり (下記参照)** |

### 1.7 の欠陥

`report-template.md` は 見積もり手法 セクションに distribution / trials / seed の記載を要求するが、
`/estimate:new` が読むのは `pipeline` の返り値であって run summary ファイルではない。
現在の `cmd_pipeline` は `trials`/`correlation`/`hours_per_day` しか返さず、
`distribution` と seed を返さない。このままではスキルがテンプレートを埋められず、
「値を捏造しない」というテンプレートの hard rule と正面から衝突する。
→ `cmd_pipeline` の返り値に `simulation` ブロックを含める必要がある。

## 2. 境界値 (BVA/ECP)

| # | 観点 | 優先度 | 状態 |
|---|---|---|---|
| 2.1 | seed = 0 (falsy な有効値)。`if seed is None` で分岐しているため 0 は生成に流れず採用されること | must (BVA) | 未カバー |
| 2.2 | seed = 負の整数。`random.Random` は受理するが意図的に許すか | should (ECP) | 未カバー |
| 2.3 | seed = `2**63 - 1` / それ以上の巨大整数 | could (BVA) | 未カバー |
| 2.4 | `p50_days` = 0 (境界の有効値)。`value is None` での skip 判定なので 0 が落ちないこと | must (BVA) | 未カバー |
| 2.5 | `simulation` = `{}` (空 dict)。`is not None` 判定のため空でも保存される | should (ECP) | 未カバー |

2.1 と 2.4 は「falsy な有効値」を None 判定と取り違える典型で、
どちらも実装が `is None` を使っているため現状は正しいが、リグレッションを縛る価値が高い。

## 3. 異常系

| # | 観点 | 優先度 | 状態 |
|---|---|---|---|
| 3.1 | seed が str / float / bool → `CalcError` | must (ECP) | カバー済み `test_rejects_non_integer_seed` (str/bool)。**float 未カバー** |
| 3.2 | `simulation` が非 object (str/list/数値) → `CalcError` | must (ECP) | カバー済み `test_rejects_non_object_simulation` (str のみ) |
| 3.3 | `p50_days` が負 / NaN / bool → `CalcError` | should (ECP) | 未カバー |
| 3.4 | run summary 書き込み失敗時、`pipeline` が `summary.error` に落ちて history は残る | must | カバー済み `test_run_summary_failure_is_recoverable` |

## 4. 状態遷移・冪等性

| # | 観点 | 優先度 | 状態 |
|---|---|---|---|
| 4.1 | 同一 payload の `pipeline` 2 回実行で、seed 未指定なら別 seed・別 totals になる (独立性) | should | 未カバー |
| 4.2 | traditional と ai_assisted が別 seed を持ち、両者の乱数列が独立であること | should | 未カバー |
| 4.3 | run summary の書き込みが atomic (既存の性質を壊していないか) | should | カバー済み (既存 run-summary テスト) |

4.2 は設計判断の明文化が目的。同一 seed にすると両ビューが完全相関し
「同じ幸運/不運の下での比較」になる。現状は独立。どちらが正しいかは
仕様として固定し、テストで縛るべき。

## 5. 回帰

| # | 観点 | 優先度 | 状態 |
|---|---|---|---|
| 5.1 | **`seed` に float を渡す既存呼び出しが新たに失敗する** | **must** | 未カバー |
| 5.2 | `RUN_SCHEMA_VERSION` 1 → 2 により、既存 run summary を読む消費者が壊れないか | must | カバー済み `test_writes_default_document_and_reads_tasks_from_history` (定数参照に変更) |
| 5.3 | `cmd_simulate` の返り値にキーが 2 つ増えたことで、返り値全体を等値比較する既存テスト/呼び出しが壊れないか | must | 全 111 テスト green で確認済み |
| 5.4 | `simulation` 未指定の `run-summary` 直接呼び出しでキーが増えない (後方互換) | must | カバー済み `test_simulation_block_is_absent_when_not_supplied` |
| 5.5 | history の `schema_version` は 2 のまま変更されていないこと (run summary 側だけの bump) | must | 未カバー |

5.1 は Python の `random.Random(42.0)` が従来通っていたため、実質的な API の締め付け。
意図的なら許容だが、テストで意図を明示すべき。

## 6. フレームワーク結合

| # | 観点 | 優先度 | 状態 |
|---|---|---|---|
| 6.1 | **mock なしで `pipeline` → run summary JSON をファイルに実書き込みし、読み戻して replay が一致すること** | **must** | カバー済み `test_unseeded_pipeline_run_stays_reproducible` (実ファイル経由) |
| 6.2 | `simulation` ブロックが JSON シリアライズ可能 (巨大 int が桁落ちしないこと) | must | 未カバー |

6.2 は実質的なリスク。seed は最大 `2**63` 近い整数で、JSON の数値としては
仕様上問題ないが、この JSON を JavaScript で読む消費者は
`Number.MAX_SAFE_INTEGER` (2**53) を超えて精度を失う。
seed を文字列で持つか、生成上限を `2**53` 未満にするかの判断が必要。

## 7. セキュリティ

対象外。この変更は信頼境界に触れない (外部入力・認証認可・秘密情報・公開エンドポイントのいずれにも関与せず、
seed は暗号用途ではなく再現性のためのもの)。

---

## must の最小構成

安全網として最低限必要なのは以下:

1. 1.7 — `pipeline` 返り値に distribution と両 seed を含める (**実装欠陥の修正を伴う**)
2. 2.1 — seed = 0 が採用される
3. 2.4 — `p50_days` = 0 が保持される
4. 3.1 — seed が float で拒否される (5.1 の意図明示を兼ねる)
5. 6.2 — seed の JSON round-trip で値が変わらない
6. 5.5 — history の schema_version が 2 のまま

負荷・性能テストはコミット単位の観点に馴染まないため本書のスコープ外 (必要なら別途計画する)。
