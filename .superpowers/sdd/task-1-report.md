# Task 1 Report: Default QA contract RED test

## Scope completed

- Added `tests/test_estimate_new_contract.py` only.
- Kept `skills/new/SKILL.md` and all other production files unchanged.
- The test reads the `/estimate:new` skill contract and requires:
  - `--no-qa`;
  - default QA inclusion;
  - the four required QA activities;
  - the implementation-versus-QA no-double-counting boundary.

## TDD RED evidence

Command run:

```sh
python3 -m pytest tests/test_estimate_new_contract.py -v
```

Result: expected failure, `1 failed`.

The first failing assertion is that `--no-qa` is absent from
`skills/new/SKILL.md`. This demonstrates that the test detects the currently
missing Task 2 contract. No GREEN implementation was attempted, by design.

## Validation

- `git diff --check` completed without whitespace errors before commit.
- Test result intentionally remains RED until Task 2 updates the skill contract.

## Commit

- `d1b72a8 test: define default QA estimate contract`

## Handoff / concern

Task 2 must add each asserted phrase verbatim (or update this contract test
with an approved equivalent wording) and then rerun the targeted test to make
it GREEN. An unrelated untracked plan file existed before this task and was
not staged or modified: `docs/superpowers/plans/2026-07-21-default-qa-effort-inclusion.md`.

## Review fix: exact QA option contract

- Updated `tests/test_estimate_new_contract.py` so it extracts complete
  command-line options, then requires the QA-related option set to equal only
  `{"--no-qa"}`. This detects both `--qa` and aliases such as
  `--exclude-qa`.
- Command run: `python3 -m pytest tests/test_estimate_new_contract.py -v`
- Result: expected RED failure (`1 failed`), because the skill currently has
  no `--no-qa` option. No production files were changed.

## Re-review fix: explicit QA exclusion contract

- Replaced the QA-option name-pattern regular expression in
  `tests/test_estimate_new_contract.py` with explicit contract assertions for
  `--no-qa` and `No other option excludes QA.`.
- This makes the skill declare that `--no-qa` is the sole QA-exclusion option,
  without guessing or enumerating possible aliases.
- Command run: `python3 -m pytest tests/test_estimate_new_contract.py -v`
- Result: expected RED failure (`1 failed`) at the missing `--no-qa` assertion.
  No production files were changed.
