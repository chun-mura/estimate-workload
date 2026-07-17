# Design: v2 — Monte Carlo task correlation + machine-readable run summary

Date: 2026-07-17
Status: draft
Scope: two independent features, implemented in order ① → ② as separate commits/PRs.

## Background

Design-review feedback on v0.1.0 identified two gaps:

1. `cmd_simulate` samples each task's Triangular distribution independently.
   Real-world delays share common causes (spec churn, environment issues), so
   task durations are positively correlated; assuming independence understates
   total variance and biases P80 optimistic.
2. The estimate output is human-readable only. aidd-autopilot's triage phase
   decides an S/M/L size label via subjective LLM judgment; a machine-readable
   run summary (run_id, P50/P80, size label + boundaries) would let it use
   quantitative estimates instead.

Cold start (empty history) stays as-is for v2: corrections already skip
gracefully with an explicit "insufficient data" note (YAGNI).

## Decisions (user-confirmed)

- Both features designed now; implementation split into two commits/PRs (① first).
- S/M/L label basis: **AI-assisted P80** (autopilot's executor is a Claude
  agent). Both traditional and AI-assisted P50/P80 still appear in the JSON.
- Default boundaries: **S ≤ 4 h, M ≤ 16 h, L above** (AI-assisted P80 hours),
  overridable via `.estimate/config.json`.
- Correlation default **ρ = 0.3**, overridable via `.estimate/config.json`
  and per-call payload. (Defaults live in the script; the skill only passes
  overrides.)

## ① Task correlation in Monte Carlo

### Approach: one-factor Gaussian copula (chosen)

Per trial, draw a common factor `Z ~ N(0,1)`. Per task, draw idiosyncratic
`ε_i ~ N(0,1)` and set:

```
z_i = sqrt(ρ)·Z + sqrt(1−ρ)·ε_i
u_i = Φ(z_i)                      # standard normal CDF via math.erf
x_i = TriangularInvCDF(u_i; o, m, p)   # closed form
```

Marginals remain exactly Triangular(o, m, p); ρ controls pairwise correlation
of the underlying normals. ρ = 0 reproduces independence; ρ = 1 is fully
comonotonic. stdlib-only (`math.erf`, `math.sqrt`).

Rejected alternatives:
- **Common risk multiplier** (one global factor scaling all tasks per trial):
  easy to explain but inflates the mean, not just the spread, and conflates
  correlation with extra variance.
- **Blended uniforms** (`u_i = w·u_common + (1−w)·u_i`): distorts the marginal
  distributions; statistically unsound.

### Changes

`scripts/estimate_calc.py`:
- `cmd_simulate` accepts optional `correlation` (default 0.3). Validation:
  finite number in [0, 1], else `CalcError`.
- Replace `rng.triangular(...)` sampling with the copula scheme above.
  Degenerate tasks (`o == p`) stay constant, as today.
- Add `TriangularInvCDF` helper: with `Fc = (m−o)/(p−o)`,
  `u < Fc → o + sqrt(u·(p−o)·(m−o))`, else `p − sqrt((1−u)·(p−o)·(p−m))`.
- Result JSON gains `"correlation": ρ` for transparency.

`skills/new/SKILL.md`:
- Step 7: if `.estimate/config.json` sets `correlation`, pass it to `simulate`
  (both calls). Report's legend/method note must state the correlation
  assumption ("tasks correlated at ρ = X via common-cause factor").

`skills/estimation-methodology/SKILL.md`:
- Short section: why correlation, what ρ means, default 0.3
  (common-cause delays; typical project-risk practice range 0.2–0.5).

`tests/test_estimate_calc.py`:
- Existing seed-based expectations updated (RNG stream changes even at ρ = 0).
- New: mean approximately invariant in ρ; P80 strictly wider at ρ = 0.9 than
  ρ = 0; marginal sanity (single task: ρ has no effect); validation errors
  for ρ out of range; degenerate task unaffected.

### Behavior change

`simulate` output changes for the same seed (new RNG stream) and P80 rises for
multi-task runs (intended — that is the fix). Single-task totals are unchanged
in distribution.

## ② Machine-readable run summary JSON

### Output file

`.estimate/runs/<run_id>.json`, written by a new CALC subcommand (keeps the
choke-point rule: label math, task data, and file format live in the script,
not skills). The file is a point-in-time snapshot: `/estimate:record` does not
regenerate it, mirroring the markdown report's snapshot rule. Repo policy is
the user's choice, same as `history.jsonl` (README documents both together).

```json
{
  "schema_version": 1,
  "run_id": "20260717T093000-example-slug",
  "generated_at": "2026-07-17T09:30:00",
  "size": {
    "label": "M",
    "basis": "ai_assisted_p80",
    "boundaries": {"s_max_hours": 4, "m_max_hours": 16}
  },
  "traditional": {"mean": 20.5, "p50": 20.1, "p80": 24.3},
  "ai_assisted": {"mean": 10.0, "p50": 9.8, "p80": 12.0},
  "tasks": [
    {"id": "20260717T093000-example-slug-01", "task": "...",
     "category": "backend-api", "pert": 6.0}
  ]
}
```

`schema_version` is independent of the history schema version and uses its
own constant (`RUN_SCHEMA_VERSION`), so a future history schema bump cannot
silently bump the run schema. Label rule: `p80 ≤ s_max → S`, `p80 ≤ m_max →
M`, else `L` (boundaries inclusive). `tasks[].pert` is the value persisted by
`append-history` (traditional PERT, no AI factor) — see below.

### Changes

`scripts/estimate_calc.py`:
- New subcommand `run-summary` with the standard `--input` payload contract:
  `{run_id, history_path, output_dir (default ".estimate/runs"), boundaries?,
  traditional: {mean,p50,p80}, ai_assisted: {mean,p50,p80}}`. The `tasks`
  array is NOT passed in: the script reads it back itself via `read_history()`
  filtered by `run_id` (single source of truth; no duplicate hand-off of task
  data through the skill, and the task `id`s come from the persisted records).
  `CalcError` if the run_id has no records.
- Validates all numbers/strings, computes the label from `ai_assisted.p80`,
  and writes the file atomically: `os.makedirs(output_dir, exist_ok=True)`
  first (as in `append-history`; `update-actual` omits this only because its
  target directory is guaranteed to pre-exist), then tempfile + `os.replace`.
  Echoes the document to stdout.
- Boundaries: payload (from `.estimate/config.json` `size_boundaries`, passed
  by the skill when present) overrides defaults per key; a missing key falls
  back to its default, then the merged pair is validated (`s_max < m_max`,
  both positive finite, else `CalcError`).
- Module docstring: mention `.estimate/runs/` as the second script-owned
  output alongside `history.jsonl`.

`skills/new/SKILL.md`:
- Step 8 gains sub-step 3: call CALC `run-summary` with the run_id, history
  path, and the two `simulate` totals. Report footer additionally names the
  JSON path ("machine-readable summary: `.estimate/runs/<run_id>.json`").
- Explicit exception to the "any CALC failure → stop" rule: if `run-summary`
  fails after `append-history` succeeded, report its stderr, OMIT the JSON
  path footer line, and continue to step 9 (history is authoritative and
  already saved).
- Fix existing dangling reference at line 50: `append-history` returns only
  `{run_id, appended}`, not `ids` — reword to "Keep the returned `run_id`;
  task ids are `<run_id>-01`, `-02`, … in input order."

`tests/test_estimate_calc.py`:
- Label boundary cases (4.0 → S, 4.1 → M, 16.0 → M, 16.1 → L); custom and
  partial (one-key) boundaries; file written and parseable, `.estimate/runs/`
  created when absent; tasks read back from history match the run; validation
  errors (missing totals, `s_max >= m_max`, unknown run_id).

### Consumer (out of scope)

aidd-autopilot's triage reading this JSON is a separate change in that repo.
This design only guarantees a stable schema (`schema_version` bumps on
breaking change).

## Error handling

- Both new code paths raise `CalcError` with actionable messages; skills
  already stop-and-report on CALC failure (no freehand fallback).
- `run-summary` failure after `append-history` succeeded: history is
  authoritative and already saved; the skill reports the error and still
  writes the markdown report (mirrors the existing "history FIRST" rule).

## Testing

`python3 -m pytest tests/` — all existing tests green (with updated seed
expectations) plus the new cases above.
