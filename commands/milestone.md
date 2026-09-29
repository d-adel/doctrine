---
description: Set or change the campaign's current milestone, map its regime, and clear the parks and oracles it overlaps
argument-hint: <milestone id> [what changed]
---

# /doctrine:milestone

Arguments: `$ARGUMENTS`. The first word is the milestone's Id. The plugin is at
`${CLAUDE_PLUGIN_ROOT}`.

This is the fixed point where a milestone is set or changed (DESIGN.md, Triggers). No packet
moving the milestone is accepted until it ends with no `BLOCK`.

## Before acting

Read `doctrine/profile.md` (Records, Invariant monitors, Limits) and the campaign file's goal
hierarchy and Authority. A new milestone, or a changed target, regime or oracle, is an owner
decision unless the Authority delegates it; record the decider's words.

## Steps

1. **Declare it** under the campaign file's Current milestone:
   - `Id`;
   - `Regime`: the `regime:<name>` keys its workload reaches, first as expected, then corrected by
     step 2;
   - `Oracles`: what its targets are judged against, as `reference:<ledger id>`,
     `invariant:<name>` or `exact:<what>`.
2. **Map the regime.** One Direct-size lane, run under `workflow-rules.md` (Machine time):
   - Run the milestone's workload once with every invariant monitor on, and once at a refined
     step or resolution. If the workload does not exist yet, derive the regime from the
     milestone's definition and label it derived.
   - Record the envelope the workload reaches: the observables that name each regime, the
     monitor violations, and the refined run's differences.
   - Record the envelope the existing tests cover.
   - Record it as one result row tagged `kind=result; regime-map=<id>; rests-on=<the paths and
     rows it ran on>`, and name that row in `Regime map`.
   - Each monitor violation becomes a defect row with its `invariant:` lineage.
   - Each gap between the workload and the tests becomes a coverage item or a park whose bound
     is measured in the workload.
3. **Oracles.** Each `reference:` oracle must be a row `validated-in` every regime of the
   milestone. One that is not is validated as the milestone's first packet: a conservation
   check, an analytic case, or refinement convergence in those regimes.
4. **Parks.** Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/doctrine_check.py" milestone`. For every
   `park-domain` line, either re-bound the park in the milestone's regime (a measurement, then
   add the regime to `bound-in`) or reopen it (`state=open`).
5. **Repeat** step 4 until it prints no `BLOCK`, then commit the campaign file and the ledger in
   one commit, and tell the owner in one line what the map found.
