# Doctrine profile: <project>

The project's specifics for the doctrine plugin. Every command and agent reads this file first.
Where it and the plugin's rules disagree, this file governs this project and says so; it never
weakens a check a merge needs.

## Owner and deciders

- Owner: <name, handle>
- Deciders for owner decisions: <handles, and how a decision is recorded>
- Delegated decisions: <which Decisions an independent decision agent takes, where it runs (a local
  `doctrine:critic` in decision mode, or a cloud session), or none>

## Records

- Brief: <path, or none>
- Campaign file: `doctrine/campaign.md`
- Ledger: <path>
- Registers the packets cite: <ids and where they are defined, or none>
- Ledger kinds: <prefix=kind pairs beyond C=defect, E=result, D=decision, A=audit, O=reference, or none>
- Lineage audit threshold: <related failures in one lineage that force an audit; default 3>
- Escalations: <`doctrine/escalations/`, and which decisions reach it, or none>
- Person actions: <`doctrine/person-actions.md`, or none>

## Routing

- Routing: <on (the default) or off; off leaves the existing workflow and turns off only routing>
- Routing never fast: <path globs where no change is mechanical, for example `src/auth/*`, or none>
- Routing reset after: <unsuccessful repair cycles on one decision before a reset; default 2>
- Routing probe budget: <inconclusive bounded probes per decision before the reasoning path; default 1>
- Routing consequential words: <a regular expression of terms that make a changed code line consequential, or the default>

## Judgment layer

<The fast probabilistic layer that takes the calls in the plugin's `rules/judgments.md`, for
example TypeSafe's Jev; how it is invoked (a command or tool taking a judgment id and its inputs,
returning a label and a confidence); each judgment's mode, shadow or live, with the calibration
record that moved it to live; and any threshold this project raises. Or none: the reasoning agent
takes every call.>

## Invariant monitors

The laws the product must keep (the brief's correctness targets), each with how its monitor is
switched on and what a violation prints. Every campaign measurement runs with every monitor on.

- <invariant name>: switch <flag or env>; violation line `<marker>`; shown firing by <test or run>

## Branches

- Trunk: <branch packets are cut from and merged into>
- Packet branch: <pattern, for example `campaign/<task>` or `<task>`>
- Protected: <branches never checked out, committed to or pushed, or none>
- Upstream to absorb before a run: <for example origin/main, or none>
- Push: <what is pushed and when, or "never">

## Provision

<Commands that make a fresh packet worktree ready, and what must never be run while doing it.>

## Checks

- Runner: <command that runs every blocking line in order into a log directory>
- One line: <command that runs a single line>
- Build kit: <commands agents build and run through, if any>
- Logs: <where run logs go>

## Reviews

- Modes: <criteria, and any others, for example security>
- <mode> lens: <what the reviewer checks in that mode>
- Always flag: <project items every review flags>

## Conventions every role reads

- <files and skills: CLAUDE.md, an idioms list, style rules>

## Never

- <actions no agent takes in this project>

## Guard

<what `doctrine/guard/` refuses, for whom, and how it is tested; or none>

## Limits

- Build-heavy runs at once: <n>
- Heavy lane worst case: <minutes>
- Quiet timings: <build and machine state a performance number comes from>

## Prompt block

<The project's block pasted below the plugin's prompt blocks: code rules, build rules, known
pitfalls. The pitfalls list grows the day a lane hits a new trap.>
