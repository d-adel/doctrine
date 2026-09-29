---
description: Run an independent architecture reset from a fact sheet, with varied starting perspectives and no consensus
argument-hint: <reset name>
---

# /doctrine:reset

Arguments: `$ARGUMENTS`, the reset's name (default: today's date). The plugin is at
`${CLAUDE_PLUGIN_ROOT}`.

## Before acting

Read `${CLAUDE_PLUGIN_ROOT}/rules/DESIGN.md` (Strategic mode) and the campaign file's goal
hierarchy. Say in one line that the campaign is entering strategic mode, which trigger fired, and
what is and is not decided.

## Steps

1. **Fact sheet.** Write `doctrine/reset/<name>-facts.md` from
   `${CLAUDE_PLUGIN_ROOT}/templates/reset-facts.md`: the product goal and target in numbers, the
   hard constraints, the current architecture as facts checked against the code, and raw
   measurements stage by stage. No explanations, fixes, recommendations or favoured precedent from
   the record; precedent only when the owner asks for it.
2. **Perspectives.** Four by default, deliberately varied (for example: shipped products at this
   scale; the domain's first principles; the hardware; the budget from first principles). Vary the
   model across perspectives where more than one is available.
3. **Commit** the fact sheet, so every perspective reads the same commit.
4. **Launch.** Call the Workflow tool with name `doctrine:reset-panel` and args `{facts:
   "doctrine/reset/<name>-facts.md", perspectives: [{key, lens, model?}], root: <absolute checkout
   path>, plugin: "${CLAUDE_PLUGIN_ROOT}"}`.
5. **Record** every answer verbatim in `doctrine/reset/<name>-candidates.md`, with a first
   paragraph saying how independent the perspectives were (models, shared inputs).
6. **Report** to the owner in a few lines: where they agree, where they disagree, the premise they
   share, and the cheapest experiment that could falsify it. The choice between candidates is a
   Decision; it is not made here.
7. **Commit** the candidates and one ledger line.
