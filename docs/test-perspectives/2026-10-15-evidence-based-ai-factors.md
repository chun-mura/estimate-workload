# テスト観点: AI既定係数の改定と manual-verification カテゴリの追加

対象: `feat/evidence-based-ai-factors` の未コミット差分

- `scripts/estimate_calc.py` の `CATEGORIES` に `manual-verification` を追加した。このカテゴリは `schema_error`、`cmd_append_history`、`cmd_reference_class`、`cmd_pipeline` の4か所で検証に使われる。
- `skills/new/references/ai-assistance-factors.md` の既定係数を改定した。
- `skills/new/references/category-taxonomy.md` と `skills/new/SKILL.md` で、QA活動のカテゴリの分類を変えた。

## 1. 正常系

| 観点 | 優先度 | 状態 |
| --- | --- | --- |
| `pipeline` が `manual-verification` のタスクを受け付け、`ai_factor` が `{"factor": 1.0, "source": "default"}` になる | must | カバー済み（`test_manual_verification_category_is_accepted`）。この経路で `reference-class` のカテゴリ検証も通る |
| `append-history` で書いた `manual-verification` のレコードを `read_history` が有効なレコードとして読み戻す。`schema_error` で `unknown category` として除外され、警告だけを出して消えることがない | must | カバー済み（`test_manual_verification_records_round_trip_through_history`） |
| `manual-verification` の完了実績が、AIありとAIなしでそれぞれ3件以上あると、`calibration` が学習した係数を返し、`pipeline` で既定値より優先される | should | 未カバー。仕組み自体は `test_learned_factor_wins_over_default` が他のカテゴリでカバー済み |
| `reference-class` が `manual-verification` の完了実績だけを母集団にして補正する（他のカテゴリの実績が混ざらない） | could | 仕組みは `test_other_categories_excluded` で他のカテゴリについてカバー済み |

## 2. 境界値

| 観点 | 優先度 | フラグ | 状態 |
| --- | --- | --- | --- |
| カテゴリ集合の有効クラス（7つ）と無効クラス（未知の文字列、大文字違いの `Manual-Verification`、空文字） | should | ECP適用 | 未知の文字列はカバー済み（`test_rejects_unknown_category` ×2）。大文字違いと空文字は未カバー |
| `default_factor` = 1.0（係数がちょうど1）を受け付け、AI支援の合計が従来型とシミュレーションの誤差の範囲で一致する | could | BVA適用 | 受け付けることはカバー済み。合計が一致することは未カバー（2つのビューは seed が別なので、許容差の設定が必要） |

## 3. 異常系

| 観点 | 優先度 | 状態 |
| --- | --- | --- |
| `ai_view: true` で `manual-verification` のタスクに `default_factor` が無いと、履歴に書く前に失敗する | could | 仕組みは `test_missing_default_factor_fails_before_any_write` で他のカテゴリについてカバー済み |

## 4. 状態遷移

該当なし（この変更は順序依存や並行実行の挙動を変えない）。

## 5. 回帰

| 観点 | 優先度 | 状態 |
| --- | --- | --- |
| 既存6カテゴリの v2・v3 の履歴レコードが、これまでどおり読める | must | カバー済み（`TestReadHistory` 一式。`CATEGORIES` は要素を足しただけ） |
| 未知のカテゴリは、これまでどおり拒否される | must | カバー済み（`test_rejects_unknown_category` ×2） |
| SKILL の QA 既定4活動の文言（契約テストが固定している文字列）が残っている | must | カバー済み（`test_qa_is_default_and_can_only_be_explicitly_excluded`） |
| 係数の説明ファイルとカテゴリ定義のカテゴリの集合が、`CATEGORIES` と一致する | must | カバー済み（`test_every_category_has_a_default_factor_and_taxonomy_row`） |
| 既定係数の値が改定案どおりである | must | カバー済み（`test_default_factors_follow_field_evidence`） |
| SKILL が QA の実施作業を `manual-verification` に、テスト計画を `docs` に振り分けている | must | カバー済み（`test_qa_execution_is_manual_verification`） |
| 既存の `test-only` の実績（テストコードの作成と人の検証作業が混在）から学習した係数が、新しい分類の意味とずれる | could | テストでは検出できない。CHANGELOG とリリースノートに注記する |

## 6. フレームワーク結合

| 観点 | 優先度 | 状態 |
| --- | --- | --- |
| JSON ファイルの書き込みと読み込みの境界を、mock を使わない実経路で確かめる。一時ファイルに対して `cmd_pipeline` を実行し、`manual-verification` を含む run を書く。続けて同じファイルで `cmd_reference_class`（または `read_history`）を実行し、警告なしで読める | must | カバー済み（`test_manual_verification_records_round_trip_through_history`） |

## まとめ

- must 観点はすべてカバー済み。`manual-verification` のレコードが履歴の書き込みと読み込みを通り抜けることは、`test_manual_verification_records_round_trip_through_history` で確かめている。
- 具体的なテストケースへの導出は `/stdd:test-design` に委ねる。
- 負荷・性能テストはこの観点の対象外。必要なら別に計画する。
