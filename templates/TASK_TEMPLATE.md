# <task>

The packet for `<task>`, written by `/doctrine:prepare` from this template. Once Accepted it is
frozen: only Status and Evidence change. Every section is filled; a placeholder left in
<angle brackets> makes `/doctrine:accept` refuse. Sections the profile marks optional may read
"None" with the reason.

## Status

<Draft | Accepted | Ready for review | Needs Investigation | Merged>, <date>

## Goal

<One paragraph: what is true when this packet is done, stated as observable behaviour.>

Interpretation: `doctrine/interpretations/<task>.md`.

## Moves

<The milestone or bottleneck from the campaign's goal hierarchy this packet moves, and by how
much. A packet that moves neither is parked.>

## Size

<Packet | Decision>, and why it is not Direct.

## Area

<one of the areas the profile lists>

## Serves

- <goal, register or requirement id from the campaign file>: <how this packet serves it>

## Lineage

<Comma-separated keys naming what this packet's failures would count against: `layer:<name>`,
`regime:<name>`, `invariant:<name>`, `criterion:<task>/<id>`, and `decision:<slug>` for the decision it
works on, which routing's budgets follow across renamed tasks. `/doctrine:accept` counts related
failures per key (DESIGN.md, Triggers).>

## Repairs

<The ledger rows this packet repairs, or None. A repaired row tagged `invariant:<name>` needs a
criterion whose oracle is that invariant over the regime.>

## Supersedes

<The packet this one replaces, or None. A supersession counts as a failure in this packet's
lineage.>

## Accepted Design

<The design, as decisions. Each decision says who made it:>
- <decision>: under the brief (<brief path>, <section>).
- <decision>: <owner decision id>, <decider>, <date>, recorded in the campaign file.

## Accepted by

<The coordinator under the brief, <date>, brief commit <sha>> or <handle>, <date>, <channel>

## Base

- Trunk `<trunk>`: <sha>
- <upstream the profile names, if any>: <sha>

## Branch

`<packet branch>`, worktree `.claude/worktrees/<task>`.

## Scope

- `<path>`: <what changes>

Out of scope: <what this packet does not touch>.

## Readers

<Every name this packet changes that another file can read: a response field, a message string, a
function, an export, a file path, a setting or a context key. Or None, when it changes no such
name. One bullet each, the exact string that finds it, in backticks:>

- `<fixed string>`
- `<fixed string>`, not affected: `<path>`, `<path>` (<why each cannot be affected>)

<Choose the string the readers must contain, not a common word: `.remaining`, not `remaining`.
The accept trigger runs `git grep -l -F` for each string at the packet's trunk Base, leaving out
`doctrine/`. Every file it finds must be in Scope, or named after "not affected:" with the reason
(DESIGN.md, Triggers). A reader in neither is a premise the packet missed.>

## Spawn Plan

| Step | Agent | Input | Expected duration |
|---|---|---|---|
| 1 | `doctrine:implementer` | this packet, the worktree path | <n-m min, from wf_<id>> |
| 2 | `doctrine:checker` | the worktree path, the log directory, Base | <n-m min> |
| 3 | repair, at most one | the checker's failures in Scope | <n-m min> |
| 4 | `doctrine:reviewer`, one per review mode the profile names | `diff.patch`, the checker's evidence | <n-m min> |

## Checks

Every line of `doctrine/blocking.md`, copied with its venue, then the focused checks this packet
adds.

| Name | Command | Venue | From |
|---|---|---|---|
| <name> | `<command>` | <venue> | `blocking.md` |
| <name> | `<command>` | <venue> | focused |

## Criteria

| Id | Behaviour | Check | Oracle |
|---|---|---|---|
| C1 | <observable behaviour, and the violating fixture it fails on> | <check name from Checks> | <oracle> |

Oracle, what the check's verdict is judged against (DESIGN.md, Triggers), one or more of:
- `spec`: the stated observable is its own truth (ordinary behaviour);
- `exact:<what>` or `analytic:<what>`: a closed form or independent exact computation;
- `invariant:<name>`: a conservation or consistency law, over the regime;
- `reference:<ledger id>`: a reference whose row is `validated-in` the milestone's regimes;
- `relative; shares=<what both arms share>; covered-by=<criterion or ledger id>`: a comparison
  between two arms, with the check that covers what they share;
- `regression`: equal to a recorded baseline.

An exclusion or admission rule adds `excludes=<rule>; floor=<largest share excluded before the
check is inconclusive>`.

## Kept green

<Parity or regression specs this packet must not break, with their frozen hashes; or None, with
the reason.>

## Spend

<None. | item, vendor, plan, cost, and the decision that approves it.>

## Installs

<None. | tool, version, how installed.>

## Blockers

<None. | each blocker, and what would clear it. A packet with a blocker is not accepted.>

## Evidence

Written by `/doctrine:run`. Empty until then.

- Log directory: <path>
- Per check: <name>: <pass | fail | not run: needs <tool>>, <log file>. Each log names the tree,
  commit, dirty state, command and venue.
- Per criterion: <id>: <met | not met | not shown>, <check and log line>
- Reviews: <mode>: <findings, correctness or advisory>
- Repair: <none | what was repaired, and why>
- Carry-forward: <what the next packet reuses, and what it need not rediscover>
