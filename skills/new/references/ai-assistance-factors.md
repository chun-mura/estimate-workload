# Default AI-assistance factors

Multiplier applied to a task's O/M/P hours to express effort when the developer works with an agentic coding tool. These defaults are heuristics for cold start — once `calibration` returns a learned factor for a category (requires ≥ 3 AI-assisted and ≥ 3 non-assisted completed records), the learned factor wins. Without a learned factor, `pipeline` corrects the AI-assisted view directly when the category has ≥ 5 completed AI-assisted records that store the `ai_factor` they were estimated with (ratio = actual ÷ (expected × `ai_factor`); returned as `ai_factor.correction`). The traditional view is corrected only from non-assisted records, so AI-assisted actuals never discount it.

Defaults follow field and enterprise evidence on real work, not lab upper bounds:

- Paradis et al. 2024 (Google RCT, 96 engineers, enterprise-grade task): ≈21% less time (≈0.8), wide confidence interval.
- Cui et al. (Management Science; three field experiments, 4,867 developers): +26% completed tasks (≈0.79). Throughput, converted to time.
- METR 2026 update (57 developers, 800+ tasks, agentic tools): −18% (CI −38%..+9%) for returning and −4% (CI −15%..+9%) for new developers (0.82–0.96); METR calls it very weak evidence and likely a lower bound on speedup.
- METR 2025 (16 experienced OSS developers): +19% time (≈1.19).
- Peng et al. 2023 (lab, greenfield HTTP server task): ≈0.44 — an upper bound on gains, not a planning default.
- McKinsey 2023 (internal lab study, 40+ developers): documenting code functionality in about half the time; under 10% savings on high-complexity tasks.
- Noy & Zhang 2023 (Science; preregistered RCT, 453 professionals, writing tasks): ≈40% less time (≈0.60).
- Test generation: Meta TestGen-LLM (FSE 2024) — 25% of generated tests fail reliability filters; Yuan et al. (FSE 2024) — wrong assertions are common. No study times test writing directly.
- IaC-Eval (NeurIPS 2024): GPT-4 pass@1 19% on Terraform vs 87% on Python. No study times IaC or migration work directly.

| Category | Default factor | Evidence | Why |
|---|---|---|---|
| `docs` | 0.60 | medium | Writing RCT (Noy & Zhang ≈0.60); McKinsey's 0.5 covers code documentation only, while specs, test plans, and test cases also land here |
| `test-only` | 0.70 | weak | Test code generates well, but assertion review and unreliable tests remain |
| `backend-api` | 0.80 | strong | Median of field evidence (Google RCT, Cui et al.) |
| `frontend-ui` | 0.80 | weak | Borrowed from backend field evidence; no frontend-specific study; visual verification stays manual |
| `db-migration` | 0.85 | weak | Writing is fast; validation and rollout care dominate |
| `infra` | 0.90 | weak | Slow, environment-specific feedback; low IaC generation accuracy |
| `manual-verification` | 1.00 | judgment | Human-executed checks; no evidence that AI shortens them |

The factor model is deliberately simple (hours × factor). It captures tool leverage, not skill differences. Present AI-assisted totals as a planning view, not a promise.

## Sensitivity range

While any task uses a default factor without an applied correction, `pipeline` also returns `ai_sensitivity`: the AI-assisted total re-simulated with the optimistic and conservative factors below (same seed; learned factors and tasks with an applied `correction` stay fixed). The values live in `estimate_calc.py` (`AI_SENSITIVITY_FACTORS`) — never pass them in the payload. This table documents them.

| Category | Optimistic | Central (default) | Conservative |
|---|---|---|---|
| `docs` | 0.50 | 0.60 | 0.75 |
| `test-only` | 0.55 | 0.70 | 0.85 |
| `backend-api` | 0.65 | 0.80 | 0.95 |
| `frontend-ui` | 0.70 | 0.80 | 1.00 |
| `db-migration` | 0.75 | 0.85 | 1.00 |
| `infra` | 0.80 | 0.90 | 1.05 |
| `manual-verification` | 1.00 | 1.00 | 1.10 |

- Optimistic: the faster end of field evidence (Cui et al. upper bound ≈0.68, METR 2026 returning-developer CI ≈0.62); McKinsey's code-documentation 0.5 for `docs`. Peng's lab 0.44 is not used.
- Conservative: METR 2026 new developers (≈0.96) for well-evidenced code work; ≥ 1.00 where category evidence is missing, reflecting METR 2025 (≈1.19) and McKinsey's slower juniors. `manual-verification` rises to 1.10 because AI-generated code adds verification volume (judgment, not measured).
