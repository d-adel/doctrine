# Judgment calls

Doctrine has three kinds of decision:
- decisions a script can make, which stay code (`scripts/doctrine_check.py`, DESIGN.md Triggers);
- open decisions that need reasoning;
- recurring judgment calls in between: not decidable by rule, but with a small, fixed set of
  answers.

This file lists that middle kind. A project may hand them to a fast probabilistic layer, named in
its profile (Judgment layer), which returns a label and a confidence. Anything uncertain or
consequential goes to the reasoning agent. With no layer named, the reasoning agent takes every
call and nothing here changes behaviour.

## Contract

- **Input:** the judgment's id and the inputs listed below, as text. **Output:** one label from
  the judgment's set, and a confidence in [0, 1].
- **Facts, not interpretations.** The state a layer reads is raw observation and mechanically
  derived facts: the row's measurement, the tags, what rests on what, check results. It is never
  an agent's interpretation or advocacy. A decision model follows persuasive text in its state
  and keeps a high confidence while doing so (Check Point's study of Jev: injected paragraphs
  flipped 59% of verdicts at high confidence). An agent describing its own finding as minor must
  not be what decides whether it is foundational.
- **Shadow first.** A judgment starts in shadow mode, and its threshold comes from measurement,
  not from the defaults below:
  - The layer answers beside the reasoning agent, which still decides.
  - Both answers are recorded.
  - Accuracy is measured by probability band.
  - The threshold is then set from the cost of a wrong action.

  A model's confidence reflects the shape of its distribution, not measured accuracy, until this
  calibration shows otherwise. The thresholds in the table are starting points for that
  measurement.
- **Escalation:** the call goes to the reasoning agent (the coordinator, or the role that owns the
  fixed point) when any of these holds:
  - the confidence is below the judgment's threshold;
  - the label is in the judgment's escalate-always set;
  - the label contradicts deterministic evidence (a tag, a check result, a script `BLOCK`);
  - the output is not one of the judgment's labels.
- **Never overrides:** the layer never overrides or clears a script `BLOCK`, never writes an
  acceptance, merge or Decision, and never clears a `stale` tag. It proposes; the fixed point
  records.
- **Records:** a tag the layer wrote carries `judged-by=fast; confidence=<c>`. A tag the reasoning
  agent wrote or confirmed carries `judged-by=reasoning`.
- **Calibration:** at each reprioritization, the reasoning agent re-judges a sample of the layer's
  accepted calls, at least 10 or all if fewer. If its agreement on a judgment falls below 90%, that
  judgment's threshold rises by 0.05, or the judgment returns to the reasoning agent. Every
  disagreement found is corrected in the ledger.

- **Small, semantic, literal.**
  - The state holds only what the judgment reads: the row, not the ledger; the hunk, not the
    diff. Unrelated detail lowers a decision model's accuracy.
  - Numeric comparisons, counts and dates stay in code, and reach the model as their results.
  - Instructions say exactly what is asked, without negations stacked on negations.
  - A threshold set for one question type does not carry over to another.

## Mapping to a typed decision model

For a model with typed primitives, such as TypeSafe's Jev (one call carries the state and a map of
questions, answered in parallel):
- a Choice returns one option with per-option probabilities and a confidence, up to 255 options;
- a Score returns a level on an ordered rubric;
- a Noul returns the probability that a statement is true.

Each judgment below maps to one Choice, except where the Mapping column says otherwise. A
multi-label judgment becomes one Choice per dimension, or one Noul per candidate. Questions about
the same record go in one call.

## The judgments

| Id | When | Inputs (facts only) | Labels | Mapping | Start threshold | Escalate always |
|---|---|---|---|---|---|---|
| J1 lineage | a defect row or a supersession is recorded | the row's observation, the ledger's existing lineage keys by dimension, the packet's lineage | per dimension: an existing key, or `new-key` | one Choice per dimension (layer, regime, invariant) | 0.85 | `new-key` |
| J2 foundational | any finding is recorded | the observation; the rows that rest on what it touches (from `rests-on`) | `foundational`, `not-foundational` | Noul | 0.8 | `foundational` (it forces an audit) |
| J3 size | a task is named (Task size) | the task statement, the files it may touch | `direct`, `packet`, `decision` | Choice | 0.8 | `decision` |
| J4 oracle | `/doctrine:prepare` writes a criterion; the reviewer reads it | the criterion, its check, the declared oracle | `spec`, `exact`, `analytic`, `invariant`, `reference`, `relative`, `regression` | Choice | 0.8 | a label differing from the declared one |
| J5 finding class | the reviewer writes a finding | the finding's observation, the criterion it touches | `correctness`, `advisory` | Choice | 0.9 | `correctness` |
| J6 gate | a result is recorded (Progression) | the measured result, the milestone, the lineage counts, open parks | `repair`, `park`, `experiment`, `stop`, `strategic` | Choice | 0.85 | `strategic`; `repair` of a foundational row; `park` without a measured bound |
| J7 trigger form | a park is recorded | the park's reopen trigger, its regime tags | `regime-observable`, `downstream-symptom`, `not-objective` | Choice | 0.8 | `not-objective` |
| J8 authority | a choice is made | the choice, the campaign's Authority | `coordinator`, `delegated`, `owner` | Choice | 0.9 | `delegated`, `owner` |
| J9 stale order | `/doctrine:merge` marks rows stale | each stale row, the merge's diff | `likely-affected`, `likely-unaffected` | Choice, one question per row in one call | 0.7 | none: the label only orders re-verification; it never clears a tag |
| J10 park watch | a result is recorded | the result's experiment and result cells; one park's `Observes:` sentence per request | per park: `relevant`, `unrelated` | Noul, one request per park | 0.8 | `relevant` |
| J11 duplicate | a defect or result is recorded | the new row; up to 40 earlier defects sharing a lineage key or untagged (a defect), or the campaign's rejected hypotheses (a result), ranked by shared words | an earlier row's id, or `none` | Choice | 0.85 | anything but `none` |

## Running it

`scripts/judge.py` is the client for a typed decision model on TypeSafe's API. The key is read from
`TYPESAFE_API_KEY`: the environment, or the user environment on Windows; never a file. The
questions come from `rules/judgments.json`. Each dimension's vocabulary is in the project's
`doctrine/judgments.json`. Every call is appended to `doctrine/judgments.jsonl`.

- `judge.py ask <J> <row> [--reasoning <label>]`: one judgment on one ledger row, logged.
- `judge.py tag <row>`: J1, writing each confident dimension's key with `judged-by=fast` and handing
  the rest to the reasoning agent.
- `judge.py backfill <J>`: every tagged row, scored against its tags, for calibration.
- `judge.py calibrate [<J>]`: agreement by confidence band and a proposed live threshold.
- `judge.py watch <result>`: J10 over every parked row with an `Observes:` sentence, one request
  per park.
- `judge.py dupe <row>`: J11 against earlier defects or the rejected hypotheses.

Reasoning labels for calibration live in the project's `doctrine/judgment-labels.json`, by
judgment; `watch`, `dupe` and `backfill` log them beside Jev's answer.

A judgment's mode, shadow or live, and the calibration record that moved it are in the project's
profile (Judgment layer).

## Calibration so far

- **J1 lineage (one project, 2026-09-26):** 39 answers against reasoning tags, 23 of 24 agreeing at
  confidence 0.70 or higher. The one disagreement was a tagging error the model caught. Live at
  0.85.
- **J7 trigger form (the same project):** 16 of 16 labelled triggers, all 10 at 0.85 or higher agreeing. Live
  at 0.85.
- **J2 foundational (the same project):** failed twice, with the row alone and with the dependency facts
  added. It missed 5 of 7 foundational findings. Whether a finding undercuts what other results
  rest on is reasoning over relations between records, not a bounded read of one record, so J2
  stays with the reasoning agent. A project may re-calibrate it; it starts in shadow.
- **J10 park watch (the same project):** shadow, after two designs failed and one following the model's
  documented weak spots worked. Asked whether a result "measures the quantity the trigger names",
  all parks in one request, it found none of 7 relevant parks on 27 labelled pairs; one park per
  request, relevant parks sat at p 0.47-0.55 under false positives at 0.68-0.81. Both designs broke
  the documented rules: literal reading (a trigger in campaign terms like "Step 1's transitions"),
  indirection (find the trigger's quantity, then look for it), and distracting state. The working
  design gives each park an `Observes:` sentence, written once by reasoning, that states literally
  what a result must report, and asks one direct question per park: "Does `result` report on
  <observable>?". On the same pairs 12 of 12 answers at confidence 0.70 or higher agreed, the two
  relevant parks at 0.91 and 0.92; every miss was below 0.70 and escalates. Read the model's
  jaggedness page before designing a judgment, and redesign against it before calling one failed.
- **J11 duplicate (the same project):** shadow. 5 of 6 labelled rows agreed: it named both known
  rediscoveries (at 0.90 and 0.70) and answered none on four new defects at 0.33-0.66; its one miss
  was at 0.39 and escalated. Every match escalates, so it
  saves work only once `none` is trusted at a measured confidence.

## Not judgment calls

These stay with the reasoning agent, because their answer is open or its consequence too large:
- a design, an architecture, a reset;
- a mechanism attributed to a result;
- a threshold or tolerance registered for a criterion;
- whether a reference is validated;
- the text of a Decision.

These stay code, because a rule decides them:
- lineage counts and audit due;
- oracle syntax;
- stale propagation;
- park overlap with a milestone;
- registration order (discovery against confirmation);
- a crossing inside a registered tolerance region.
