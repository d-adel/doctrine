# Ledger

Current decision-relevant state, one short row per item (DESIGN.md, Records). The last column,
Tags, is read by `scripts/doctrine_check.py`, so the triggers in DESIGN.md (Triggers) fire
without anyone having to notice. A row without tags is still valid, but the triggers cannot see it.

| ID | Observation | Status and bound | Consequence and next decision | Tags |
|---|---|---|---|---|
| C-1 | <what was observed> | <open, parked, resolved; its bound> | <what it blocks; next decision> | kind=defect; state=open; lineage=layer:<x>, invariant:<y> |

The ID prefix gives the kind by default: C defect, E result, D decision, A audit, O reference. A
profile maps other prefixes (Ledger kinds).

Tags are `key=value` pairs separated by `;`, with comma-separated values:

| Key | Values | Read by |
|---|---|---|
| `kind` | defect, result, decision, reference, audit; and probe, repair, reset for a decision's lineage | every trigger; overrides the prefix |
| `state` | open, parked, resolved, closed, superseded, done | lineage counts, park checks |
| `lineage` | `layer:<name>`, `regime:<name>`, `invariant:<name>`, `criterion:<task>/<id>`, `decision:<slug>` | the lineage audit trigger; routing counts a decision's probes and repairs by its `decision:` key |
| `severity` | foundational: the finding invalidates a foundational assumption or reference | an immediate audit of its lineages |
| `rests-on` | repository paths or ledger ids the row's truth depends on | stale marking at merge |
| `stale` | the commit that invalidated it; written by `/doctrine:merge` | accept and decide refuse to cite it |
| `regime` | the regimes a defect or park lives in | the park-domain check |
| `bound-in` | the regimes or milestone ids a park's bound was measured in | the park-domain check |
| `validated-in` | the regimes a reference was shown right in | the oracle check |
| `regime-map` | the milestone id a result maps | the regime-map check |
| `covers` | for an audit: the rows and `task:<name>` supersessions it explains | clears them from lineage counts |
| `outcome` | for a probe: decisive, inconclusive; for a repair: fixed, failed, informative (failed, but with new discriminating evidence) | routing's probe and repair budgets |
| `changed` | for a reset: hypothesis, strategy, scope or rationale, what the reset changed | a reset with none clears nothing |
| `judged-by`, `confidence` | `fast` with its confidence, or `reasoning`: who set a judged tag (`rules/judgments.md`) | calibration at reprioritization |

A stale row is re-verified by re-running or re-reading what it rests on. Its `stale=` tag is then
removed in the same commit as the result, or the row is superseded.
