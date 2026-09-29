# Campaign: <name>

The running record of the campaign. The brief is <path>. This file holds the goal hierarchy,
the Authority, decisions and state; packets hold the detail, the ledger holds findings.

## Goal hierarchy

1. **Product goal**: <the brief's goal, verbatim>
2. **Current milestone**: <measurable, with its target numbers; who set it>
   - Id: <M-...>
   - Regime: <regime:<name>, ... the workload's regimes, from its regime map>
   - Regime map: <ledger id of the regime-map result, or pending>
   - Oracles: <reference:<ledger id>, invariant:<name>, ... what the targets are judged against>
3. **Current bottleneck**: <measured, with the measurement's id>
4. **Active packets**: <or: see the ledger; each lists what it moves>

## Authority

- The coordinator decides: <routine investigation, experiment design, implementation choices>
- Owner decisions: <changing intended behaviour, accepting a known limitation, choosing between
  materially different architectures, redefining the target, removing a capability>
- Delegated: <owner decisions an independent decision agent takes, or none>

## Decisions

| Date | Decision | Decider | Words |
|---|---|---|---|

## Target status

| Target | Status | Evidence |
|---|---|---|
