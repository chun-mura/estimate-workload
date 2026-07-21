# Default QA effort inclusion design

## Goal

Ensure every new estimate includes applicable QA effort unless the caller
explicitly opts out.

## Interface

- Add `--no-qa` to `/estimate:new`.
- QA is included by default. `--no-qa` excludes it for work whose QA is
  separately budgeted or explicitly out of scope.
- `--no-qa` is independent of `--mode` and the AI-assisted-view options.

## WBS behavior

When QA is enabled, the WBS must contain applicable `test-only` leaf tasks for:

1. Test planning and test-case preparation.
2. Functional verification in an integrated environment.
3. Integration, E2E, and regression testing.
4. Defect verification and retesting.

The estimator may combine or split these tasks to keep each leaf task within
the existing 0.5--3 person-day WBS rule. Unit tests and in-development checks
remain part of the implementation tasks and must not be counted again as QA.

## Reporting

- The report records that QA is included and lists the QA scope.
- With `--no-qa`, the report records QA as excluded and lists it under excluded
  work so the estimate's boundary is auditable.

## Validation

Tests cover option parsing and report/WBS requirements for both the default and
the explicit opt-out path. README and skill documentation describe the default
and the `--no-qa` exception.
