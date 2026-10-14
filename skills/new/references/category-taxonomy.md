# Category taxonomy (fixed in v1)

Exactly one category per leaf task. The script rejects anything else.

| Category | Use for | Typical examples |
|---|---|---|
| `backend-api` | Server-side logic, endpoints, services, business rules | REST/GraphQL endpoint, background job, domain service |
| `frontend-ui` | Client-side UI and state | Component, page, form validation, styling |
| `db-migration` | Schema or data changes and their rollout | New table, column change, backfill script |
| `infra` | Build, deploy, environment, observability | CI pipeline, Dockerfile, IaC, monitoring |
| `test-only` | Writing test code not tied to a feature task | Regression suite, e2e scaffold, load test |
| `manual-verification` | Human-executed verification and release checks | Functional verification in an integrated environment, running regression/E2E passes, defect retesting, device or staging checks, post-release smoke checks |
| `docs` | Documentation-only work | README, ADR, runbook, API docs |

Rules of thumb:
- A task spanning two categories is two tasks — split it.
- Choose by the dominant skill the work needs, not by which files change.
- Writing automated tests is `test-only`; executing checks by hand is `manual-verification`.
