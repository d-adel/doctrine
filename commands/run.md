---
description: Run an Accepted doctrine packet in its own worktree and branch, record Evidence and Status
argument-hint: <task>
---

# /doctrine:run

Arguments: `$ARGUMENTS`, the task name. The plugin is at `${CLAUDE_PLUGIN_ROOT}`. Below, `$ROOT` is
the main checkout (`git rev-parse --show-toplevel`) and `$WT` is `$ROOT/.claude/worktrees/<task>`.

## Before acting

Read `doctrine/profile.md` in full and `${CLAUDE_PLUGIN_ROOT}/rules/workflow-rules.md`. Work in
the main checkout on the profile's trunk. Check what is already running on the machine against
the profile's Limits before launching.

## Refuse when

- `doctrine/tasks/<task>.md` on the trunk is not Accepted.
- `$WT` or the packet branch already exists, unless it is this packet's interrupted run (the packet
  on that branch still Accepted with no Evidence): then reuse the worktree and go on from step 4.
- A guard the profile requires is not installed.
- `python "${CLAUDE_PLUGIN_ROOT}/scripts/doctrine_check.py" triggers --task <task>` prints a `BLOCK`: an audit came due in the packet's lineage
  after it was accepted, a reset came due on a `decision:` key it names, or a heartbeat or a route
  review is due (`DESIGN.md`, Progression). Run the audit, the reset or the review, or record the
  heartbeat, first; the packet waits.
- A failed check or a review finding sends the next action through `route` (`DESIGN.md`,
  Progression, Routing); an amendment on the fast route still gets the packet's gate before merge.

## Steps

1. **Absorb the upstream**, when the profile names one and it is not an ancestor of the trunk:
   merge it with `--no-ff`, resolving conflicts by the profile's rules; when that does not settle
   it, abort, record a blocker entry, refuse this run and continue with other work. Record the
   merge and what it invalidates in the campaign file in the same commit.
2. **In flight.** Record `<task>: running` in the campaign file; commit; push as the profile says.
3. **Worktree.** `git worktree add "$WT" -b <packet branch> <trunk>`. Record
   `BASE=$(git rev-parse <trunk>)`. Refuse to go on unless the worktree is on the packet branch.
4. **Provision** the worktree with the profile's Provision commands, never with anything it
   forbids.
5. **Launch.** `$LOGDIR` is the profile's log location for `<task>`. Call the Workflow tool with
   name `doctrine:run-packet` and args, as a JSON object:
   `{task, packet: <the full text of $WT/doctrine/tasks/<task>.md>, worktree: "$WT", logdir:
   "$LOGDIR", base: "$BASE", branch: <packet branch>, runner: <the profile's runner command,
   with the log directory as LOGDIR>, reviews: [{mode, lens}, ...] from the profile's Reviews,
   criteria first, plugin: "${CLAUDE_PLUGIN_ROOT}", prompt_block: <the profile's Prompt block>}`.
   The workflow gives every lens to one reviewer, in one pass. It returns
   `{status, reasons, checks, reviews, ...}`, where `reviews` holds that one review, its findings
   tagged by lens.
6. **Record** in `$WT/doctrine/tasks/<task>.md`, in the template's form: Status as returned
   (never raised by hand), and Evidence: the log directory, the workflow run id, `$BASE` and each
   commit, each Check's result and venue with its log's header lines ("not run" stays "not
   run"), the tests, each criterion with its check and log line,
   every review's findings, the repair, the reasons, installs, and carry-forward. Commit on the
   packet branch; push as the profile says.
7. **Trunk state.** In one commit on the trunk: In flight `<task>: <status>`; Next: the merge,
   or for Needs Investigation the smallest investigation that tells the implementation, the
   test, the model and an assumption apart, with a blocker entry saying where the failure is
   preserved; installs.

The worktree stays until the merge.
