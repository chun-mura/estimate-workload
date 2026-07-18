# Design: estimation modes and batch analysis

Date: 2026-07-18
Status: approved for planning

## Goal

Let a requester choose the analysis-cost/accuracy trade-off before
`/estimate:new` starts, while preventing a list of related tasks from
duplicating the same specification and repository analysis.

## Non-goals

- Do not change the three-point estimation, reference-class correction,
  simulation, history, or run-summary calculations.
- Do not add a cache in this change. A cache needs an explicit source and Git
  revision invalidation policy and is not needed to remove the largest
  duplication first.
- Do not silently select a cheaper mode when the requester did not choose one.

## User interface

`/estimate:new` accepts an optional mode flag before its existing sources:

```text
/estimate:new --mode quality <paths and/or description>
/estimate:new --mode economy <paths and/or description>
```

When the flag is omitted, the intake question presents these two choices
together with the existing AI-assisted-view choice:

| Display label | Stored mode | Promise |
|---|---|---|
| 精度優先 | `quality` | Run both requirement and codebase analysis once over the full input. |
| 節約優先 | `economy` | Run requirement analysis once; do not inspect the repository. |

An explicit mode flag wins over the intake answer. Invalid or duplicated mode
flags stop the estimate with an actionable error. The user can still decline
the AI-assisted view independently.

## Batch boundary

One `/estimate:new` invocation is one estimation batch. All provided sources
and all change descriptions in that invocation are analysed once, and the
normal WBS step creates all resulting leaf tasks in one pipeline payload.

The plugin must not dispatch an analysis agent once per WBS leaf task. A user
who invokes `/estimate:new` fifteen separate times still creates fifteen
batches; the command documentation must show that related tasks should be
passed in one invocation.

## Analysis modes

### `quality`

Dispatch the existing `estimate:spec-analyzer` and `estimate:code-analyzer`
once, in parallel, with the complete batch input. Merge their structured
results using the current rules: the specification view defines what changes;
the code view determines where it lands and its implementation difficulty.

This keeps the current evidence sources, but changes their unit of work from a
leaf task to an entire estimate batch. For fifteen related tasks it has two
analysis-agent invocations rather than up to thirty.

### `economy`

Dispatch `estimate:spec-analyzer` once with the complete batch input. Do not
dispatch `estimate:code-analyzer` and do not replace it with an ad-hoc local
repository scan.

The WBS is based on requirements only. For every leaf task that could be
affected by existing code, record these two statements:

- assumption: implementation complexity is estimated without repository
  impact analysis;
- risk: hidden coupling, integration points, and existing test coverage are
  unverified.

Those uncertainties widen the task's pessimistic (`P`) value under the
existing methodology. The generated report must state that `economy` mode was
used; it must not imply that code impact was analysed.

## Persisted provenance

Add an `analysis` object to the pipeline result and the machine-readable run
summary:

```json
{
  "mode": "quality",
  "agents": ["spec-analyzer", "code-analyzer"]
}
```

For `economy`, `agents` contains only `spec-analyzer`. This is descriptive
provenance, not an input to mathematical calculations. The run-summary schema
version is increased because consumers need to distinguish older summaries
that do not state analysis coverage.

The Markdown report includes one line in `## 見積もり手法` naming the selected
mode. In `economy` mode, its risks and assumptions sections carry the required
code-analysis caveats above.

## Data flow

```text
sources + --mode
       |
       +-- quality --> spec-analyzer --+
       |                               +--> WBS --> pipeline --> report + run summary
       |               code-analyzer --+
       |
       +-- economy --> spec-analyzer ------> WBS --> pipeline --> report + run summary
```

The pipeline remains the sole writer of history and run summaries. It receives
the selected mode and completed agent names as provenance; it never runs an
agent itself.

## Error handling

- If either selected `quality` agent fails or violates its JSON contract,
  continue with the available result exactly as today, mark the agent failure
  in Risks, and lower confidence. Do not rerun it automatically.
- If the selected `economy` specification agent fails, stop: there is no
  reliable requirement basis for a WBS.
- An invalid mode stops before any agent dispatch or history write.
- Existing recoverable run-summary failure behavior is unchanged.

## Verification

- Skill-level scenarios: omitted mode prompts once; each explicit mode skips
  that prompt; invalid and duplicate flags fail before dispatch.
- `quality` dispatches exactly the two existing agents once per invocation.
- `economy` dispatches exactly `spec-analyzer` once and never
  `code-analyzer`.
- A multi-task input produces one pipeline invocation and one run id, with
  multiple WBS/history task records.
- Pipeline and run-summary tests cover analysis provenance, including an older
  summary reader rejecting or safely handling the new schema version.
- Generated economy reports contain the mode line and required assumption/risk
  statements; quality reports state their mode without those caveats.

## Attack review

- **Dependency failure:** analysis-agent failures preserve the current
  quality-mode partial-result rule; economy stops because its only evidence
  source is unavailable.
- **Scale:** the number of agent dispatches is constant per batch (two or one),
  rather than growing with WBS leaf count. Very large source documents still
  cost context once, so document chunking is deferred rather than hidden.
- **Rollback:** mode provenance is additive. Disabling the feature only
  removes the mode choice; past history and existing calculation fields remain
  valid. A run-summary schema bump makes incompatible consumers fail visibly.
- **Premise:** batching helps only when related tasks share sources. Separate
  invocations cannot be deduplicated without caching, which is deliberately
  deferred.
