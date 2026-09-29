---
description: Audit one layer when its lineage trigger fires, and decide a class-level design instead of another serial fix
argument-hint: <lineage key>
---

# /doctrine:audit

Arguments: `$ARGUMENTS`, a lineage key (`layer:`, `regime:`, `invariant:` or `criterion:`). The
plugin is at `${CLAUDE_PLUGIN_ROOT}`.

The trigger fired: the profile's threshold of related failures in this lineage, or one
foundational finding (DESIGN.md, Triggers). Until this audit's row exists, no packet, run or
decision in the lineage proceeds. Say so to the owner in one line, with the failures that
tripped it.

## Before acting

Read `doctrine/profile.md` (Invariant monitors, Limits), the campaign file's milestone and every
ledger row in the lineage (`python "${CLAUDE_PLUGIN_ROOT}/scripts/doctrine_check.py" lineage`).

## Steps

1. **Census.** Run the milestone's workload on this layer with every invariant monitor on,
   instrumented to show the layer's paths: exits, caps, fallbacks, and the regime observables.
   This is Direct-size, under `workflow-rules.md` (Machine time).
2. **Refine.** Run the same census once at a refined step or resolution. A result that does not
   converge under refinement belongs to the class this audit is looking for.
3. **The class.** List every defect the census and the refined run show together, with the
   rows already in the lineage. Record each one not yet in the ledger, tagged into the lineage.
   Name what they share: the assumption, reference or mechanism behind them.
4. **One Decision** on a class-level design, under the campaign's Authority (`/doctrine:decide`
   where it is delegated). The Decision restores the invariant or assumption for the whole
   class, not one mechanism, and states the packet that carries it and that packet's
   invariant criterion. If the layer cannot meet the milestone's regime, the Decision is a
   reset (`/doctrine:reset`).
5. **Record** the audit as one ledger row, `kind=audit; state=done; lineage=<key>;
   covers=<every row and task:<name> it explains>`, with the census, the refined run and the
   Decision as its evidence. Commit it with the Decision.
