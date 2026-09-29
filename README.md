# doctrine

Doctrine is a Claude Code plugin for running long engineering work with agents without losing
track of what is true. It turns a goal into small, checked steps: every change is a packet with a
frozen design and criteria, every claim rests on a check that ran, and every decision records who
made it and what it rests on. Agents implement, check and review; the plugin keeps them honest.

It was built while developing a real-time physics engine, where a week of agent work can easily
produce a lot of activity and very little progress. Doctrine is the answer to that: progress is
measured against the goal, not against commits.

## What it does

- **Goal hierarchy.** A campaign names its product goal, its current measurable milestone, its
  bottleneck and its active packets. A packet that moves neither the milestone nor the bottleneck
  is parked.
- **Task sizes.** Direct work (a probe, a measurement) needs no ceremony; a packet (code that
  merges) gets checks and one review; a decision (architecture, product behaviour) gets an
  independent decider.
- **Packets.** A packet holds its goal, the design decisions and who made them, a narrow scope,
  the readers of every name it changes, its checks and its criteria, each with an oracle. It is
  frozen once accepted; failures are amended in place and recorded.
- **Checks that bite.** Every criterion names a check and a violating fixture. Thresholds carry a
  measured floor. "Not run" is never a pass.
- **Triggers.** `scripts/doctrine_check.py` refuses what used to depend on someone noticing: an
  audit due after repeated failures in one layer, a reference used outside the regimes it was
  validated in, a stale citation, a reader of a changed name outside scope.
- **Progression.** After every result: what changed, what is bounded, does it block the milestone,
  is there a cheaper next action. Issues that block nothing are parked with a bound and a reopen
  trigger instead of chased.
- **Strategic resets.** When fixes keep exposing deeper fixes, independent agents get the goal and
  the raw facts, nothing else, and propose from scratch.
- **Invariant monitors.** A project names the laws its product must keep (energy, momentum,
  whatever applies); campaign runs keep the monitors on, and a violation is a failed check.

The full contract is `rules/DESIGN.md`; run mechanics are in `rules/workflow-rules.md`.

## Requirements

- Claude Code with plugins and the Workflow tool.
- Python 3.9 or newer (standard library only) for the trigger checker.
- Git.
- Optional: a fast judgment layer for bounded calls (`rules/judgments.md`); the plugin ships a
  client for TypeSafe's API (`scripts/judge.py`, needs `TYPESAFE_API_KEY`). Without one, the
  reasoning agent takes every call.

## Install

    claude plugin marketplace add d-adel/doctrine
    claude plugin install doctrine@doctrine --scope project

The repository is its own marketplace. The plugin has no fixed version: each commit is a version.

## Set up a project

1. Copy `templates/profile.md` to your project's `doctrine/profile.md` and fill it in: the owner and
   who decides, how to build and check, the review lenses, the things agents must never do.
2. Create `doctrine/blocking.md` with the checks every packet runs.
3. Start a campaign from `templates/campaign.md` and a ledger from `templates/ledger.md` when the
   work is larger than a single task.
4. List the plugin checkout in `permissions.additionalDirectories` in your project's
   `.claude/settings.json` so agents can read `rules/`, and pre-approve the workflows if you like:
   `Workflow(doctrine:run-packet)`, `Workflow(doctrine:attack-round)`,
   `Workflow(doctrine:research-lanes)`, `Workflow(doctrine:reset-panel)`.
5. Optional: install a guard for your Never list with `guard/install.sh` (a Claude hook plus git
   hooks; see `rules/DESIGN.md`, Repository checks).

## Commands and agents

| Command | Does |
|---|---|
| `/doctrine:prepare <task>` | turns an agreed interpretation into a Draft packet, with a code scout and a test scout |
| `/doctrine:attack <task>` | attacks an interpretation or packet through independent critic lenses, then verifies each attack |
| `/doctrine:accept <task>` | validates a Draft and freezes it |
| `/doctrine:run <task>` | implements, checks, repairs at most once and reviews an accepted packet in its own worktree |
| `/doctrine:merge <task>` | merges a Ready packet after re-running its checks on the merged tree |
| `/doctrine:decide` | has an independent agent take a decision the owner delegates |
| `/doctrine:audit <lineage>` | studies a layer whose failures keep recurring and decides a class-level design |
| `/doctrine:milestone` | sets or changes the milestone and maps its regimes |
| `/doctrine:research` | answers a question from primary sources in parallel lanes, with a critic |
| `/doctrine:reset` | runs an independent architecture reset from a fact sheet |
| `/doctrine:finish` | closes a campaign with an independent done audit |

Agents: `scout`, `test-scout`, `implementer`, `checker`, `reviewer`, `critic` (attack, refute,
result, independent, decision and reset modes) and `researcher`.

## Repository

| Path | Holds |
|---|---|
| `rules/` | the contract, run mechanics, the judgment calls |
| `templates/` | packet, profile, campaign, ledger, reset facts, escalation, person actions |
| `commands/`, `agents/`, `workflows/` | the plugin's commands, agents and workflow scripts |
| `scripts/doctrine_check.py` | the triggers and routing |
| `scripts/judge.py` | the optional judgment-layer client |
| `scripts/post-commit` | optional hook that updates local projects listed in `scripts/projects.txt` (untracked) |
| `guard/` | a project guard's installer and test |
| `tests/` | the checker's tests: `python -m unittest discover -s tests` |

## License

MIT. See `LICENSE`.
