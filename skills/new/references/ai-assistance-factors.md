# Default AI-assistance factors

Multiplier applied to a task's O/M/P hours to express effort when the developer works with an agentic coding tool. These defaults are heuristics for cold start — once `calibration` returns a learned factor for a category (requires ≥ 3 AI-assisted and ≥ 3 non-assisted completed records), the learned factor wins.

Defaults follow field and enterprise evidence on real work, not lab upper bounds:

- Paradis et al. 2024 (Google RCT, 96 engineers, enterprise-grade task): ≈21% less time (≈0.8), wide confidence interval.
- Cui et al. (Management Science; three field experiments, 4,867 developers): +26% completed tasks (≈0.79).
- METR 2026 update (57 developers, 800+ tasks, agentic tools): −18% (CI −38%..+9%) for returning and −4% (CI −15%..+9%) for new developers (0.82–0.96); METR calls it very weak evidence and likely a lower bound on speedup.
- METR 2025 (16 experienced OSS developers): +19% time (≈1.19).
- Peng et al. 2023 (lab, greenfield HTTP server task): ≈0.44 — an upper bound on gains, not a planning default.
- McKinsey 2023: documentation in about half the time; under 10% savings on high-complexity tasks.

| Category | Default factor | Why |
|---|---|---|
| `docs` | 0.50 | Drafting automates well; review remains (McKinsey documentation ≈ half the time) |
| `test-only` | 0.70 | Test code generates well, but validation and false-positive cost remain |
| `backend-api` | 0.80 | Median of field evidence (Google RCT, Cui et al.) |
| `frontend-ui` | 0.80 | Same field evidence; visual verification stays manual |
| `db-migration` | 0.85 | Writing is fast; validation and rollout care dominate |
| `infra` | 0.90 | Feedback loops are slow and environment-specific |
| `manual-verification` | 1.00 | Human-executed checks; no evidence that AI shortens them |

The factor model is deliberately simple (hours × factor). It captures tool leverage, not skill differences. Present AI-assisted totals as a planning view, not a promise.
