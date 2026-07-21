# Default AI-assistance factors

Multiplier applied to a task's O/M/P hours to express effort when the developer works with an agentic coding tool. These defaults are heuristics for cold start — once `calibration` returns a learned factor for a category (requires ≥ 3 AI-assisted and ≥ 3 non-assisted completed records), the learned factor wins.

Defaults sit between lab upper bounds (e.g. Peng et al. 2023 Copilot RCT ≈0.44 remaining time on a greenfield HTTP task) and more conservative field/RCT evidence (Cui et al. 2024 ≈+26% throughput ≈0.79; METR 2025 experienced-OSS slowdown). Relative ordering follows McKinsey 2023 task-type gradients (docs/new code gain more than high-complexity or validation-heavy work).

| Category | Default factor | Why |
|---|---|---|
| `docs` | 0.50 | Drafting automates well; review remains (≈McKinsey 45–50% time savings) |
| `test-only` | 0.50 | Strong generation use case; validation and false-positive cost remain |
| `backend-api` | 0.55 | Well-specified CRUD/endpoint work; between lab upper bound and field averages |
| `frontend-ui` | 0.60 | Generation is fast but visual verification stays manual |
| `db-migration` | 0.75 | Writing is fast; validation and rollout care dominate |
| `infra` | 0.80 | Feedback loops are slow and environment-specific |

The factor model is deliberately simple (hours × factor). It captures tool leverage, not skill differences. Present AI-assisted totals as a planning view, not a promise.
