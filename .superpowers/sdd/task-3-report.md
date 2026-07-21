# Task 3 report

Implemented `cmd_compare_runs(payload)` and registered the `compare-runs` CLI command.
It loads both runs from history, rejects missing/legacy or inconsistent context, and reports context differences, per-run task/category/M statistics, granularity warning counts, and persisted traditional totals.

Tests: `python3 -m pytest estimate-workload/tests/test_estimate_calc.py -k compare_runs -q` (2 passed).

Commit: `feat: compare estimate runs`

Concern: comparable is currently false when contexts differ; callers can still inspect the complete diff and statistics returned.

Review fixes: totals now include persisted task sums for `o`, `m`, `p`, and `pert`; missing and non-unique context/summary are reported with distinct reasons and details.
