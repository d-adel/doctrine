---
description: Attack an interpretation or packet through independent critic lenses, verify each attack, and revise the target
argument-hint: <task> [lens keys]
---

# /doctrine:attack

Arguments: `$ARGUMENTS`: the task, then optional lens keys. The plugin is at
`${CLAUDE_PLUGIN_ROOT}`.

## Before acting

Read `doctrine/profile.md` and the campaign file's goal hierarchy and Authority. Refuse when
`doctrine/interpretations/<task>.md` does not exist.

## Steps

1. **Round.** `n` is one more than the number of `doctrine/research/<task>/attack-*.md` files.
2. **Lenses.** Size the round to the task: two lenses for a small task, up to five for a large
   one. Use the keys given; otherwise choose from:
   - `fidelity`: the target against the brief, the goal hierarchy and the entries it cites;
   - `checkable`: every claim has a check, a venue and a violating fixture;
   - `authority`: no decision is presented as made when nobody made it, and every stop is one the
     Authority allows;
   - `mechanics`: the files, commands, tools and versions it relies on work as written;
   - `progress`: it moves the milestone or bottleneck it names, and is not a descendant of an
     unrelated result;
   - any lens the profile adds.
   Each lens is `{key, prompt}`; the prompt says what it attacks, the files in view and the
   standard it judges against.
3. **Commit first**, so the critics read a commit: `commit` is `git rev-parse HEAD`.
4. **Launch.** Call the Workflow tool with name `doctrine:attack-round` and args `{task, target:
   "doctrine/interpretations/<task>.md", lenses, round: n, commit, root: <absolute checkout path>,
   plugin: "${CLAUDE_PLUGIN_ROOT}"}`. It returns `{attacks, verdicts, summaries}`.
5. **Write the round record**, `doctrine/research/<task>/attack-<n>.md`, from the result alone: the
   lenses, commit and run id; the counts (attacks, duplicates, refuted, standing, unjudged,
   standing by severity, the verifier's); per lens its summary, then per attack its target,
   attack, evidence, proposal and verdict. An unjudged attack is carried as standing.
6. **Revise the target.** Answer each standing attack with the smallest change, or say in the
   interpretation why it is not taken; bump its version line. Never edit a recorded decision or
   the frozen brief, and never answer an attack by loosening a check or a target.
7. **After round 3**, an attack still standing becomes a blocker entry: an experiment or a packet
   of its own, added to Next.
8. **Commit** the record, the interpretation and the campaign file's state in one commit.
