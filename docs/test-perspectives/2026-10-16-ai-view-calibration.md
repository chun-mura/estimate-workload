# テスト観点: AIを使った実績で AI支援の見積もりを補正する

対象: `feat/ai-view-calibration` の未コミット差分（`scripts/estimate_calc.py` の `schema_error`・`cmd_append_history`・`cmd_reference_class`・`_ai_view_correction`・`cmd_pipeline`）

## 1. 正常系

| 観点 | 優先度 | 状態 |
|---|---|---|
| `append-history` が `ai_factor` を保存し、ないタスクにはキーを作らない | must | カバー済み（`test_stores_ai_factor_when_given`） |
| `pipeline`（AI支援あり）が使った係数を履歴に残す。AI支援なしでは残さない | must | カバー済み（`test_history_records_the_ai_factor_used`・`test_history_omits_ai_factor_without_ai_view`） |
| AIを使った実績が5件以上あると、AI支援の O/M は比率の中央値、P は80パーセンタイルで補正され、従来型は変わらない | must | O/M はカバー済み（`test_ai_actuals_correct_the_ai_view_directly`）。ただし比率がすべて同じ値で、P に中央値を掛けても通る → 追加済み（`test_ai_view_correction_uses_p80_ratio_for_p`） |
| 従来型の補正とアンカーから `ai_assisted: true` を外し、`false` と未設定は使う | must | カバー済み（`test_ai_assisted_actuals_are_excluded_from_anchors_and_correction`） |

## 2. 境界値

| 観点 | 優先度 | 状態 |
|---|---|---|
| AIを使った実績 4件 / 5件（BVA適用） | must | カバー済み（`test_ai_view_correction_needs_five_ai_actuals`・`test_ai_actuals_correct_the_ai_view_directly`） |
| 10件で `low_sample` が付かない（BVA適用） | should | 追加済み |
| タグ一致が5件未満ならカテゴリ全体を使う（`basis: category`）（ECP適用） | should | 追加済み |
| 他カテゴリの AI実績は母集団に入らない（ECP適用） | could | 未追加（`_pool` と従来型の既存テストで同じ絞り込みを確認済み） |
| `ai_factor` の値: 正の数 / 0 / 負 / 文字列 / bool / null（ECP・BVA適用） | must | カバー済み（`test_rejects_invalid_ai_factor`・`test_schema_checks_ai_factor_only_when_present`） |

## 3. 異常系

| 観点 | 優先度 | 状態 |
|---|---|---|
| 不正な `ai_factor` を持つ履歴行は読み飛ばされ、ゼロ除算にならない | must | カバー済み（スキーマが 0 を拒否。`test_schema_checks_ai_factor_only_when_present`） |
| `ai_factor` のない AI実績・AIなしの実績は AI支援の補正に使わない | must | カバー済み（`test_ai_actuals_without_recorded_factor_are_ignored`・`test_human_actuals_do_not_feed_the_ai_view_correction`） |
| 不正な `ai_factor` のとき履歴を書かない | must | カバー済み（`test_rejects_invalid_ai_factor` がファイル不在を確認） |

## 4. 状態遷移

| 観点 | 優先度 | 状態 |
|---|---|---|
| `pipeline` → `update-actual`（AIあり）→ 次の `pipeline` で補正が効く（`update-actual` が `ai_factor` を消さない） | must | 追加済み（`test_recorded_actuals_feed_the_next_ai_view`） |
| 学習済みの係数があるカテゴリでは補正しない | must | カバー済み（`test_learned_factor_is_not_corrected_again`） |

## 5. 回帰

| 観点 | 優先度 | 状態 |
|---|---|---|
| 補正したタスクは感度の幅で固定。全タスクが補正済みなら `ai_sensitivity` は null | must | カバー済み（`test_corrected_task_stays_fixed_in_sensitivity`・`test_ai_sensitivity_is_null_when_every_default_task_is_corrected`） |
| 既存の v2/v3 履歴がそのまま読める | must | カバー済み（`test_read_history_accepts_existing_v2_and_valid_v3_records` ほか既存テスト） |
| 学習済み係数・既定係数の既存の出力形（`correction` なし）が変わらない | must | カバー済み（`test_cold_start_runs_whole_flow`・`test_learned_factor_wins_over_default`） |

## レビューで足した観点（2026-10-16、autonomous-review）

| 観点 | 優先度 | 状態 |
|---|---|---|
| 比率は丸めずに掛ける（表示だけ2桁） | must | 追加済み（`test_ai_view_correction_applies_unrounded_ratios`） |
| 期待値 × 係数が0に下位あふれするレコードでゼロ除算しない（BVA適用） | should | 追加済み（`test_ai_view_correction_ignores_underflowing_denominators`） |
| 従来型の補正で外した AI実績の件数を返す | must | 追加済み（`test_only_ai_assisted_actuals_leave_traditional_uncorrected`・`test_applied_correction_reports_excluded_ai_assisted`） |
| AI支援の補正を見送った理由（件数・係数のない件数）を返し、感度の幅では固定しない | must | 追加済み（`test_ai_view_correction_needs_five_ai_actuals`・`test_ai_actuals_without_recorded_factor_are_ignored`・`test_ai_view_skip_marker_keeps_task_in_sensitivity`） |

## 6. フレームワーク結合

| 観点 | 優先度 | 状態 |
|---|---|---|
| 履歴 JSONL の書き込み → 読み込みの実経路（mock なし）で `ai_factor` が往復する | must | 4 の追加テストで実ファイルを通して確認する |

セキュリティ: 信頼境界に触れない（ローカルの履歴ファイルの計算のみ）ため対象外。

負荷・性能テストはスコープ外（必要なら別途計画する）。
