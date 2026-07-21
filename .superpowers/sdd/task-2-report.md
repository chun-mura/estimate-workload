# Task 2 report

## 実装

- `granularity_warnings(tasks)` を追加し、入力タスクの `m` のみを診断。
- `m < 4` を `below_recommended`、`m > 24` を `above_recommended` として入力順に返却。
- `cmd_pipeline()` の結果に `granularity_warnings` を追加。
- 警告は advisory とし、既存の三点見積もり検証、補正、履歴追記を変更しない。

## 検証

- `python3 -m pytest tests/test_estimate_calc.py -k granularity -v`
  - 1 passed
- `python3 -m pytest tests/test_estimate_calc.py -q`
  - 101 passed, 32 subtests passed

## Commit

`5b45b9b feat: report estimate granularity warnings`

## Concern

警告の推奨閾値（4〜24時間）は現行手法のルールに合わせた固定値。将来変更する場合は定数化または実行コンテキストへの保存を検討する。
