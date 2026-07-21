# Final fix report

## 修正内容

- `run_context.unit` を必須化し、値は `hours` のみ許可。SKILL の `/estimate:new` payload 契約と計算器の検証を一致させた。
- `compare-runs` は、同一 run の一部レコードだけに `run_context` または `run_summary` が存在する場合を検出し、`mixed_run_context` / `mixed_run_summary` と詳細件数を返す。欠落値を除外して比較可能と誤判定しない。
- 上記を回帰テストで固定。

## 検証

- `python3 -m pytest tests/test_estimate_calc.py -q` — 105 passed, 32 subtests
- `python3 -m pytest tests -q` — 109 passed, 32 subtests
