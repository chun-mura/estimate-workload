# Test Perspectives: run-summary nullable ai_assisted (traditional_p80 fallback)

対象: `scripts/estimate_calc.py` — `_validated_totals` の `allow_null` 追加と
`cmd_run_summary` の basis フォールバック (commit 4d0ebc5)

## 1. 正常系

- [must] `ai_assisted` がオブジェクト → `size.basis == "ai_assisted_p80"`、ラベルは ai_assisted p80 基準 — **カバー済み** (`test_writes_default_document_and_reads_tasks_from_history`)
- [must] `ai_assisted: null` → `size.basis == "traditional_p80"`、ラベルは traditional p80 基準、ドキュメントに `ai_assisted: null` が永続化 — **カバー済み** (`test_null_ai_assisted_uses_traditional_p80_basis`)
- [should] `ai_assisted` キー自体を省略 → null と同じ扱い (`payload.get` が None を返す経路)

## 2. 境界値

- [should] `ai_assisted: null` 時、traditional p80 が S/M/L 境界値ちょうど (4.0 / 16.0) でラベルが inclusive に判定される (BVA適用)。既存の inclusive 境界テストは ai_assisted 経路のみ
- 有効/無効クラス: `ai_assisted` は {オブジェクト, null} が有効、{文字列, 配列, 数値, 真偽値} が無効 (ECP適用) → 異常系参照

## 3. 異常系

- [must] `traditional: null` → 引き続き CalcError (`allow_null` デフォルト False の退行ガード)
- [should] `ai_assisted` が文字列・配列など null でもオブジェクトでもない型 → CalcError、メッセージが "must be null or an object"
- [could] メッセージ文言: `traditional` 側は従来どおり "must be an object" のまま
- カバー済み: `ai_assisted` オブジェクト内の負値・bool → CalcError (`test_rejects_missing_or_invalid_totals`)

## 4. 状態遷移

- [could] `ai_assisted: null` で run-summary を再実行 → 同一パスに冪等に上書き (atomic write は変更対象外のため優先度低)

## 5. 回帰

- [must] `ai_assisted` オブジェクト指定時の既存ドキュメント形状 (schema_version 1、basis 文字列、tasks 抽出) が不変 — **カバー済み** (`test_writes_default_document_and_reads_tasks_from_history`)
- [should] CLI 実経路 (`main(["run-summary", ...])`) が null payload でも rc=0 — 既存 CLI テストは非 null のみ

## 6. フレームワーク結合

- CLI エントリポイント経由の実経路 (mockレス) は既存 `main(["run-summary", "--input", ...])` テストで実行済み — **カバー済み**

## 7. セキュリティ

該当なし (信頼境界に触れない内部計算スクリプトの変更のため、この分類は出力しない)

---

未カバーの must: 「`traditional: null` → CalcError」の1本のみ。
負荷・性能テストはスコープ外 (必要なら別途計画する)。
