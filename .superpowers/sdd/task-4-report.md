# Task 4 report

Implemented the `/estimate:new` contract updates: `--compare-to <run-id>`, validated `run_context` (including `comparison_key`, scope metadata, hours unit, and `granularity_warnings`), the 30% P50/context reconciliation gate, and optimistic/standard/pessimistic fallback recording. Updated the fixed report template and README usage/legacy-v2 comparison note. Added a contract regression test.

Tests: `python3 -m pytest estimate-workload/tests/test_estimate_new_contract.py -q` (2 passed).

Commit: `fec7b8d feat: reconcile repeated estimates`

Concern: This task updates the skill contract and documentation only; runtime argument parsing and payload validation remain implemented by the calculator/dispatcher tasks.

Review fixes: `--compare-to` now requires a non-empty, non-malformed run-id and rejects missing values, duplicates, and unknown leading options before dispatch. Unresolved comparison guidance now mandates an explicit risk-table row with impact and reconciliation action.

Review tests: `python3 -m pytest estimate-workload/tests/test_estimate_new_contract.py -q` (3 passed).

Fix commit: `1c26387 fix: tighten compare-to contract`
