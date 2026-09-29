---
description: Prepare a Draft doctrine packet from a task's interpretation, with the scout and test scout in parallel
argument-hint: <task>
---

# /doctrine:prepare

Arguments: `$ARGUMENTS`, the task name. The plugin is at `${CLAUDE_PLUGIN_ROOT}`.

## Before acting

1. Read `doctrine/profile.md`, `${CLAUDE_PLUGIN_ROOT}/rules/DESIGN.md` (Task size, Task packets)
   and the goal hierarchy and Authority in the campaign file the profile names.
2. Name the task's size in one line. A Direct task gets no packet: say so and stop.
   Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/doctrine_check.py" cites doctrine/interpretations/<task>.md`. A `BLOCK` (an audit due in a
   lineage the task touches, or a stale citation) is cured first, by `/doctrine:audit` or by
   re-verifying the row. A task that repairs a failure names its `decision:<slug>` in Lineage, so its
   probe and repair budgets follow it (`DESIGN.md`, Progression, Routing).
3. Work in the main checkout on the profile's trunk. Never check out a protected branch.
4. A refusal is not a stop: say what is wrong, fix its cause through the flow, and continue.

## Refuse when

- `doctrine/interpretations/<task>.md` does not exist.
- The interpretation names no milestone or bottleneck it moves.
- `doctrine/tasks/<task>.md` exists with any status but Draft; an accepted packet is frozen and a
  follow-up is a new task.

## Steps

1. **Read** the interpretation and its latest attack record, the conventions the profile lists,
   `doctrine/blocking.md` and `${CLAUDE_PLUGIN_ROOT}/templates/TASK_TEMPLATE.md`.
2. **Base commits.** Fetch the profile's upstream if it names one; record the trunk head and the
   upstream head.
3. **Scouts.** Spawn `doctrine:scout` and `doctrine:test-scout` in one message so they run in
   parallel. Each prompt gives the task, the interpretation's path, the Base commits, the
   absolute path of this checkout and the plugin root, and says the scout writes nothing.
4. **Write the packet**, `doctrine/tasks/<task>.md`, from the template, Status `Draft, <date>`.
   Every section is filled:
   - Goal, Area, Serves from the interpretation; Moves from the goal hierarchy; Size.
   - Base from step 2; Branch from the profile's packet-branch pattern.
   - Scope: named files, as narrow as the Criteria need.
   - Readers: every name the design changes, with the string that finds it, from the scout's
     report. Every file the string finds at the Base is in Scope, or declared "not affected:" with
     its reason.
   - Spawn Plan: each step's expected duration from earlier run records, naming the run.
   - Accepted Design: each decision either engineering the coordinator decides under the brief,
     or an owner decision the campaign file records with the decider's words, cited.
   - Criteria: each names the Check that holds it.
   - Checks: every line of `doctrine/blocking.md`, verbatim with its venue, then the focused
     lines the test scout found.
   - Blockers: each owner decision the design needs that nobody has made, each missing test
     layer, each premise that cannot be checked.
5. **Route each Blocker.** An owner decision goes to the owner, or to `/doctrine:decide` when the
   Authority delegates it, with the work that continues without it. A missing layer or an open
   technical question is an experiment or a packet of its own. Never present a technical
   hypothesis as an owner choice.
6. **Commit** the packet with the campaign file's state in one commit, and push as the profile
   says.
