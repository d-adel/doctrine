---
description: Merge a Ready doctrine packet into the trunk after re-running its Checks on the merged tree
argument-hint: <task>
---

# /doctrine:merge

Arguments: `$ARGUMENTS`, the task name. The plugin is at `${CLAUDE_PLUGIN_ROOT}`. `$ROOT` is the
main checkout, `$WT` is `$ROOT/.claude/worktrees/<task>`.

## Before acting

Read `doctrine/profile.md` (Branches, Checks, Reviews). Work in the main checkout on the trunk.

## Refuse when

- The packet on its branch is not `Ready for review`.
- The trunk does not contain the packet's recorded trunk Base.

## Steps

1. **Worktree.** Use `$WT`; when it is gone, `git worktree add "$WT" <packet branch>`. Refuse to
   go on unless it is on the packet branch.
2. **Merge the trunk into the branch**, `--no-ff`.
   - Record `PRE`, the branch head before the merge.
   - Resolve a conflict only in the packet's Scope. Any other conflict: abort, and the packet goes
     to Needs Investigation (step 5).
3. **Re-run the Checks** on the merged branch with the profile's runner, into the log directory's
   `merge/`. A failure, or a required line not run, sends the packet to Needs Investigation. This
   re-check is the merge gate.
4. **Second opinion, only when the merge brought code the review never saw.**
   - `D` is `git -C "$WT" diff --name-only PRE HEAD`, the files step 2 changed on the branch,
     minus the records paths the profile names.
   - **Spawn `doctrine:critic`** in independent mode on the merged branch against the trunk, reading
     only inside `$WT`, with the plugin root, when either holds:
     - `D` has a path under the packet's Scope: a named file, or a directory that holds one;
     - step 2 resolved a conflict.
   - A correctness finding it confirms sends the packet to Needs Investigation. Advisory findings
     go into Evidence.
   - **Otherwise spawn no critic,** and write into Evidence: "no second opinion: the trunk merge
     changed only <D, or nothing>, none under Scope, with no conflict". The step-3 re-check is the
     gate.
5. **When a re-check fails**, keep the failure: Status `Needs Investigation, <date>`, the logs'
   header lines, results and findings in Evidence; commit on the branch. On the trunk, the
   campaign file's In flight, Next with the smallest investigation, and a blocker entry. Do not
   merge.
6. **Merge into the trunk**: `git merge --no-ff --no-commit <packet branch>`, then in the same
   commit:
   - the packet's Status `Merged, <date>` with the re-check results;
   - the campaign file: the targets it moves with their evidence, In flight, Next;
   - the stale marks: `python "${CLAUDE_PLUGIN_ROOT}/scripts/doctrine_check.py" merge <task> --base <trunk head before the merge>
     --head <packet branch> --apply`. It tags `stale=<sha>` on every ledger row resting on a path
     the packet changed, and on every row resting on those. List them under Next as rows to
     re-verify before anything cites them.

   The message says what the packet does. Push as the profile says.
7. **Clean up**: `git worktree remove "$WT"`. Keep the branch.
