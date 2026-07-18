# テスト観点: `pipeline` サブコマンド追加 / `reference-class` アンカー圧縮

対象: `scripts/estimate_calc.py` の `cmd_pipeline` 新設、`cmd_reference_class` の
`max_anchors` デフォルト変更とアンカーのフィールド圧縮 (コミット `a0e4f0f`)。

## 1. 正常系

- **コールドスタート (履歴なし) で全フロー成功** — 補正スキップ・デフォルト factor・
  history/summary 永続化まで一括で成立する。カバー済み
  (`test_cold_start_runs_whole_flow`)。
- **補正が適用されるケース (十分な done レコードあり)** — corrected_o/m/p が
  raw 値を置き換えて history と summary の両方に反映される。カバー済み
  (`test_applies_reference_class_correction`)。
- **学習済み AI factor が default_factor を上書きする** — `low_sample` の伝播も
  含む。カバー済み (`test_learned_factor_wins_over_default`)。
- **`ai_view: false`** — AI シミュレーションをスキップし `ai_assisted: null`、
  summary の basis が traditional になる。カバー済み
  (`test_ai_view_false_skips_factors_and_uses_traditional_basis`)。
- **`correlation`/`hours_per_day`/`boundaries` の透過** — カバー済み
  (`test_simulation_params_pass_through`, `test_boundaries_pass_through_to_summary`)。

## 2. 境界値

- **`tasks` が空リスト** — ECP適用 (無効同値クラス)。`pipeline: 'tasks' must be
  a non-empty list` で拒否されることを未検証。**must**
  (他コマンドと違い pipeline 自前のチェック文言があるため、専用テストが必要)。
- **1タスクのみ / 多数タスク (10件超)** — BVA適用。処理ループ (correction→sim→
  append→summary の zip 整合) が要素数に依存しないことの確認。**should**。
- **`tags` 省略 (キー自体がない)** — ECP適用。`t.get("tags", [])` のフォールバック
  経路。**should**。
- **`min_records` 境界 (ちょうど5件 vs 4件)** — 既存 `TestReferenceClass` でカバー済み
  (pipeline はそのロジックを再利用するのみ)。カバー済み。
- **`max_anchors` デフォルト変更 (5→3) の回帰確認** — `reference-class` を3件超の
  同カテゴリ・タグ一致レコードで呼び、返るアンカー数が3件に切り詰められることを
  直接検証する既存テストがない (`test_anchors_ranked_by_tag_overlap` は
  `max_anchors=2` を明示指定しており、デフォルト値の回帰は拾えない)。**must**。
- **アンカーのフィールド圧縮 (`o`/`m`/`p` が anchors に含まれないこと)** — 圧縮後の
  キー集合を明示的に assert するテストがない。**must**
  (呼び出し側や将来の変更が誤って `o`/`m`/`p` を復活・別フィールド追加した際に
  気づけない)。

## 3. 異常系

- **`ai_view: true` だが一部タスクに `default_factor` 欠落** — 書き込み前に
  fail することを検証。カバー済み
  (`test_missing_default_factor_fails_before_any_write`)。
- **未知カテゴリ** — カバー済み (`test_rejects_unknown_category`)。
- **`ai_view` が非 bool (例: 文字列 "true")** — 型チェック分岐が未検証。**must**
  (validate 順序の先頭にあり、ここが壊れると後続の全処理が無駄になる)。
- **raw の `o > m` など三点値不正 (補正前)** — pipeline 内で
  `validate_three_point` を呼んでいるが、pipeline 経由でこの経路を直接叩く
  テストがない (simulate/append-history 単体では検証済みだが pipeline の
  「補正前に即エラー」順序は別物)。**must**。
- **`history_path`/`slug` 欠落・空文字列** — `_required_string` 経由のエラーだが
  pipeline から呼んだ場合の文言・タイミング (書き込み前に失敗すること) は
  未検証。**should**。
- **`run-summary` 失敗時の回復動作** — カバー済み
  (`test_run_summary_failure_is_recoverable`)。
- **`reference-class`/`calibration`/`append-history` 内部でのロック競合
  (同時実行)** — pipeline 経由でのロックタイムアウト伝播は未検証。**could**
  (下位コマンドの単体テストで挙動自体は担保済みのため優先度は低い)。

## 4. 状態遷移

- **検証失敗時に一切ディスクに書き込まれない (原子性)** — カバー済み
  (`test_missing_default_factor_fails_before_any_write` — ただしこれは
  `default_factor` 欠落のケースのみ。三点値不正や未知カテゴリでも同様に
  「書き込みなし」まで assert しているのは `test_rejects_unknown_category` では
  未確認)。**should** (`test_rejects_unknown_category` に history ファイル
  未作成の assert を追加)。
- **`run_id` が history の全レコードで一貫し、summary にも同じ `run_id` が
  使われる** — カバー済み (`test_cold_start_runs_whole_flow`)。
- **同一 slug での連続呼び出しが別 run_id になる (冪等でないことの意図的確認)** —
  `cmd_append_history` 側で既にカバー済み
  (`test_same_second_reruns_get_distinct_run_ids`)。pipeline 経由の再テストは
  不要。カバー済み。

## 5. 回帰

- **`reference-class` を単体で呼ぶ既存フロー (SKILL.md 旧手順や他ツール連携)
  への影響** — `max_anchors` デフォルト変更とフィールド圧縮は
  `cmd_reference_class` の戻り値を直接消費する既存呼び出し全てに影響する
  破壊的変更。呼び出し側 (`skills/new/SKILL.md`) は本コミットと対で更新済みだが、
  スクリプト単体のテストとしてデフォルト値変更を明示するテストが必要 (上記
  境界値の項目と同一)。**must**。
- **`calibration` の `ai_assistance_factors` を pipeline が読む際、
  カテゴリキーが存在しない場合に default にフォールバックすること** —
  カバー済み (`test_learned_factor_wins_over_default` で docs カテゴリが
  default のまま出ることを確認)。

## 6. フレームワーク結合

- **CLI 実経路 (`main(["pipeline", "--input", <file>])` 経由の呼び出し)** —
  既存の `TestPipeline` は全て `ec.cmd_pipeline(dict)` を直接呼んでおり、
  argparse → `_load_payload` → `PAYLOAD_COMMANDS` 経由の実経路を一度も
  通していない。`run-summary` には `test_cli_echoes_the_persisted_document`
  という同種の実経路テストが既にあり、pipeline だけ抜けている状態。
  **must** (mockレスの実経路テスト — スキルが実際に叩くのはこの経路であり、
  argparse 登録漏れやJSON読み込み周りの結合バグはここでしか検出できない)。
- **`PAYLOAD_COMMANDS` への登録確認** — カバー済み
  (`test_is_registered_as_payload_command`)。

## スコープ外

負荷・性能テスト (`trials` を大きくした場合の実行時間など) はコミット単位の
観点に馴染まないため対象外。必要なら別途性能検証を計画する。

---

## must 観点まとめ (最低限の安全網)

1. `tasks` 空リストが拒否される
2. `max_anchors` のデフォルトが3件になっている (フィールド圧縮も含め回帰確認)
3. `ai_view` が非 bool のとき拒否される
4. raw の `o/m/p` が不正 (`o > m` 等) のとき pipeline 経由で拒否される
5. CLI 実経路 (`main(["pipeline", ...])`) を通した mock レステスト
