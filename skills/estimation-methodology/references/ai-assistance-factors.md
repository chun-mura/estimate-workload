# Default AI-assistance factors

Multiplier applied to a task's O/M/P hours to express effort when the developer
works with an agentic coding tool (Claude Code or similar). These defaults are
heuristics for cold start — once `calibration` returns a learned factor for a
category (requires ≥ 3 AI-assisted and ≥ 3 non-assisted completed records),
the learned factor wins.

| Category | Default factor | Why |
|---|---|---|
| `backend-api` | 0.45 | Well-specified CRUD/endpoint work automates well; review remains |
| `frontend-ui` | 0.55 | Generation is fast but visual verification stays manual |
| `db-migration` | 0.65 | Writing is fast; validation and rollout care dominate |
| `infra` | 0.70 | Feedback loops are slow and environment-specific |
| `test-only` | 0.40 | Test generation is a strong AI use case |
| `docs` | 0.35 | Drafting automates almost entirely; review remains |

The factor model is deliberately simple (hours × factor). It captures tool
leverage, not skill differences. Present AI-assisted totals as a planning view,
not a promise.
