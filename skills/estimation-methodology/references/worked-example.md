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
5. One `pipeline` call with the raw O/M/P and per-task `default_factor`:
   it corrects the callback task (ratio_p50 1.2, ratio_p80 1.6 → corrected_m
   12, corrected_p 32), simulates both views over the corrected tasks
   (traditional p50 34 h, p80 46 h; AI-assisted p50 16 h, p80 22 h with
   factor sources), appends 4 history records with status "estimated", and
   writes the run summary.
6. Report: traditional 34–46 h (4.3–5.8 person-days); AI-assisted 16–22 h.
   Assumptions: provider is Google only. Skipped corrections noted where data
   was insufficient.
