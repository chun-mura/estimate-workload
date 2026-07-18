# Worked example (abridged)

Input: "Add OAuth login to our Express app" + repo with existing session auth.

1. spec-analyzer returns one change unit: OAuth login (depends: session
   middleware; acceptance: login via Google, existing sessions unaffected).
2. code-analyzer returns: `src/auth/*` complexity mid, test coverage partial;
   integration point: session store.
3. WBS (leaf tasks):
   - "Implement OAuth callback endpoint" — backend-api, tags [auth, oauth]
   - "Wire provider config + secrets handling" — infra, tags [auth, config]
   - "Add login button + redirect flow" — frontend-ui, tags [auth]
   - "Integration tests for login flows" — test-only, tags [auth]
4. First reference-class call (category/tags only) returns anchors, e.g. a past
   backend-api [auth] task: expected 8 h → actual 11 h. Estimate the callback
   task relative to that: O=6, M=10, P=20.
5. Second reference-class call (with m, p) returns ratio_p50 1.2, ratio_p80 1.6
   → corrected_m 12, corrected_p 32. Use corrected values.
6. simulate over all corrected tasks → total p50 34 h, p80 46 h.
7. Report: traditional 34–46 h (4.3–5.8 person-days); AI-assisted view applies
   factors (0.45 backend, …) → p50 16 h, p80 22 h. Assumptions: provider is
   Google only. Skipped corrections noted where data was insufficient.
8. append-history writes 4 records with status "estimated".
