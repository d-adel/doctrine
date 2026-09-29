---
description: Have an independent critic take a Decision the campaign's Authority delegates, from the brief and the evidence only
argument-hint: <decision name>
---

# /doctrine:decide

Arguments: `$ARGUMENTS`, the decision's name. The plugin is at `${CLAUDE_PLUGIN_ROOT}`.

## Before acting

Read `doctrine/profile.md` (Owner and deciders) and the campaign file's Authority. Refuse unless
the Authority delegates this kind of Decision; otherwise the question goes to the owner, stated in
a few lines with the options and the evidence.

## Steps

1. **Brief.** Write `doctrine/decisions/<name>.md`: the question; the goal hierarchy; the options,
   each stated neutrally; the evidence by path and commit; what the decision unblocks. No
   recommendation.
2. **Critics first.** Every result the Decision rests on has a result critic's report; run
   `doctrine:critic` in result mode on any that has none.
   - `python "${CLAUDE_PLUGIN_ROOT}/scripts/doctrine_check.py" cites doctrine/decisions/<name>.md` must print no `BLOCK`: a stale result is
     re-verified before the Decision rests on it.
   - A Decision in a lineage due for an audit is the audit's Decision (`/doctrine:audit`), or it
     waits.
   - `python "${CLAUDE_PLUGIN_ROOT}/scripts/doctrine_check.py" route --action investigate --decision <slug>`
     must print no `BLOCK`: a question already answered ends, and a reset due goes to
     `/doctrine:reset` or the configured independent decision first.
3. **Commit** the brief.
4. **Decide** where the profile's Delegated decisions say. Locally: spawn `doctrine:critic` in
   decision mode with the brief's path, the commit and the plugin root, and nothing else. In a
   cloud session, which loads no plugin: make the brief self-contained (the goal, the rules it
   applies and the answer format written into it), push it, and launch the session the way the
   profile names, answering on its own branch.
5. **Record** its answer verbatim under the brief, and the decision in the campaign file's
   Decisions (decider: independent decision agent, delegated by the Authority), with one ledger
   line. The answer binds; it never by itself licenses a descendant.
6. **Commit** both, and tell the owner the decision in one or two lines.
