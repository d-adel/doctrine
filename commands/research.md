---
description: Answer a research question from primary sources in parallel lanes, with a critic on the result
argument-hint: <question>
---

# /doctrine:research

Arguments: `$ARGUMENTS`, the question. The plugin is at `${CLAUDE_PLUGIN_ROOT}`.

## Before acting

Read `doctrine/profile.md`. Name the size: a lookup one search or one fetch answers is Direct and
is done in this session, with no workflow. Research that needs lanes is for a question a Decision
or a packet rests on.

## Steps

1. **Topic.** A short kebab-case slug. When `doctrine/research/<topic>/` exists, read it first and
   carry it forward; lanes start from what is established.
2. **Prior art.** When the question has substantial prior work, the first lane is a bounded survey
   of established methods, their assumptions and evidence, and what stays open.
3. **Lanes.** Two to five, each a different way into the question. Each is `{key, prompt}`; its
   prompt names the part of the question it answers, the primary sources to start from (found by
   searching) and the figures wanted with units.
4. **Launch.** Call the Workflow tool with name `doctrine:research-lanes` and args `{question,
   lanes, topic, root: <absolute checkout path>, plugin: "${CLAUDE_PLUGIN_ROOT}"}`. It returns
   `{lanes, critic}`.
5. **Write the result**, `doctrine/research/<topic>/result-<n>.md`: the question, date and run id;
   each lane's answer and notes file; a figures table (name, value, kind, basis, source URL, date
   read); blocked pages as blocked; the critic's verdict. A figure the critic refutes is marked,
   never dropped. When the critic returned nothing, nothing may depend on the result yet.
6. **Sources.** For each source a conclusion turns on, save the passage relied on, with its URL
   and date read, to `doctrine/sources/<topic>-<slug>.md`.
7. **Commit** the result, notes, sources and the campaign file's state in one commit.
