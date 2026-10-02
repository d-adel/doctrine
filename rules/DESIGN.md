# Doctrine

Doctrine is a planning and evidence contract for building toward a goal with
agents. It exists to move a project toward its goal with the least wasted work,
and is itself held to that test (Records, process overhead). This plugin holds
the machinery: these rules, `workflow-rules.md`, the templates, the commands,
the agents and the workflows. Each project holds its state and its specifics:

- `doctrine/profile.md`: the owner, who decides, the branches, how to build
  and check, the review lenses, the Never list, the conventions every role
  reads, and concurrency (`templates/profile.md`).
- `doctrine/campaign.md`: the goal hierarchy and the campaign's Authority.
- `doctrine/ledger.md`: current decision-relevant state.
- `doctrine/blocking.md`: the checks every packet runs.
- `doctrine/tasks/`, `doctrine/interpretations/`, `doctrine/sources/`,
  `doctrine/research/`, `doctrine/reset/`, evidence and logs.

Where a project's profile and these rules disagree, the profile governs that
project and says so; a profile does not weaken a check a merge needs.

## Goal hierarchy

Every campaign defines, in order, at the top of its campaign file:

1. Product goal
2. Current measurable milestone
3. Current bottleneck
4. Active packets

A lower layer may not silently redefine a higher one.

Every packet states which milestone or bottleneck it is expected to move (its
Moves section). A packet that moves neither is parked by default.

Progress is movement in product-relevant capability, or understanding that
changes a major decision. Commit count, closed issues, experiments, ledger
size, defects found and documentation are activity metrics, used only to
diagnose the process.

## The model

The ledger is evidence; the model is what the campaign believes now, and every decision reads
the model, not the ledger. The profile names it (`Model:`). It holds, in this order:

1. **Goal**: one table, a row per term of the milestone: target, measured now, gap, source.
2. **Scoreboard**: the run that measures every Goal term at once on the reference machine, and
   where its history lives. It runs after every change to the trunk that touches code.
3. **Cost model**: what each part of the target costs at the milestone's scale, measured.
4. **Routes**: one table: each candidate route to the milestone, its bound at the milestone's
   scale (arithmetic on measured costs), and its status (open, chosen, falsified with the
   number that falsified it).
5. **Beliefs**: established, falsified, and open; each open belief names the experiment that
   settles it.
6. **Next**: the actions, ranked by the gap they close times how cheaply they close it; each
   names the Goal term it moves (`moves: <term>`).

Rules, each checked by `doctrine_check.py` (Triggers):

- **Every result updates the model.** A commit that adds an experiment or decision row to the
  ledger changes the model in the same commit: the belief it tested, the cost it measured, the
  route it bounded. A result that changes nothing says so in the model.
- **Bound before build.** A packet names its Route. A route without a bound at the milestone's
  scale gets its bound measured first, by the cheapest experiment that can produce it; a
  falsified route takes no packet until a reset records a new route.
- **Predict, then measure.** A packet's Moves carries `Predicts: <Goal term>: <now> -> <after>`.
  The scoreboard after the merge is its verdict; a miss updates the model like any result.
- **The plan is never empty.** When Next is empty, producing it from the model is the next
  action, before any other work. Idle machines with only filler queued are the same signal.
- **Pace is a requirement.** A loop that waits on slow checks, repeats runs on unchanged inputs
  or measures stand-ins instead of the Goal is a defect in the process, repaired like one.

## Modes

- Local mode solves or measures a well-defined problem inside the accepted
  architecture. Most work runs here.
- Strategic mode questions whether the decomposition, architecture, target or
  assumptions still fit. It runs at reprioritization and whenever a reset
  trigger fires.

An agent in local mode does not make a strategic decision silently: it names
the question and stops. When a campaign, a reset or a mode starts or restarts,
the coordinator says so in one line, with what triggered it and what is and is
not decided.

## Task size

Process scales with what a task can break. Before starting, the coordinator
names the size in one line and picks the smallest that fits; it moves up only
when the work shows it has to.

- **Direct.** A measurement, probe, lookup, prototype on a branch or document
  change, or a small change inside an accepted design that merges no product
  code. Do it in the coordinator's own session, report the result, record it
  as one ledger line and keep the log it rests on. No packet, critic or brief.
- **Packet.** Product or test code that merges into the trunk under an
  accepted design: a packet, its checks and its reviews (Task packets). A
  critic only when a Decision rests on its result.
- **Decision.** A choice of architecture, product behaviour or target, or any
  other owner decision under the campaign's Authority: the owner, or an
  independent decision agent where the Authority delegates it, after a reset
  (Strategic mode) when the question is strategic, with a critic on the
  results it rests on.

Size never waives a check a merge needs. A Direct task that turns up a design
choice stops and names it; the choice is a Decision.

## Progression

After every meaningful result, the gate:

- What changed?
- What is now bounded or known?
- Does this block the current milestone, or invalidate evidence it relies on?
  (Evidence a merge invalidates is marked stale mechanically: Triggers.)
- Does continuing have a plausible effect on the project goal?
- Is there a cheaper or more direct next action?

An issue that neither blocks the milestone nor invalidates evidence it relies
on is parked with its best known bound; one that does is repaired. A confirmed
result that justifies a repair leads to the repair, not to another experiment.

**No descendant chains.** A result does not by itself license another packet
or experiment; every descendant passes the gate on its own. Discovering another
question is not a reason for another round. The budget below is counted by
lineage (Triggers), so a new ledger id does not restart it.

**Investigation budget.** A question gets two rounds by default (a round is an
experiment, a probe, or a decision on one); a third needs a stated reason that
it can change a project-level decision, unblock the milestone, or prevent a
materially incorrect measurement. Remaining uncertainty alone is not a reason.
Across questions, related failures in one lineage force a layer audit
(Triggers). The budget never shortens a packet's own checks.

**Routing.** At a decision boundary (before choosing consequential next work, after a result, and
before declaring a question or task complete; not before every read, command or edit) the
coordinator runs `scripts/doctrine_check.py route`. It separates two things: the permitted next
action, and the obligations the parent task or investigation still carries. A cheap action may go
ahead while a failed criterion, a required review and the packet's own checks stay open; completing
an investigation branch accepts nothing. Hard facts decide the route: the diff, the profile, the
ledger's rows, stale marks and due audits, and the packet. Missing or unknown facts never count as
safe, and a small or reversible diff is not by itself mechanical.

| Route | When | What follows |
|---|---|---|
| fast | an authorized, local action with an established cause (`--cause`, a diagnostic log or a live ledger row) and a formatting- or rename-only diff outside the profile's never-fast paths | the action and the smallest check that covers it; no hypothesis packet, second model or extra agent only because an action happened |
| bounded | one concrete uncertainty with bounded consequences, and the decision's probe budget unspent | one probe, stating the decision, its alternatives and how each outcome changes the next action; recorded `kind=probe; lineage=decision:<slug>; outcome=decisive or inconclusive` |
| doctrine | new architecture or semantics, a failed accepted criterion, unexpected behaviour, evidence that may invalidate earlier results, uncertain dependencies, a spent probe budget, any change a number, operator, literal, test, prose or never-fast path makes | the existing investigation and review obligations, unchanged |
| reset | a reset trigger (Strategic mode), or the decision's repair budget spent: the profile's count (default 2) of `kind=repair; outcome=failed` rows with no new discriminating evidence since the last reset | the configured reset or independent decision with a compact fact brief, before a third attempt; its row `kind=reset; changed=hypothesis, strategy, scope or rationale`; a reset that changes nothing clears nothing |

Budgets follow the decision's lineage key, `decision:<slug>`, across sessions, branches, renamed
tasks and delegated work, so a new id never replenishes them. A decisive probe or result ends
optional work on its question (`answered`); the task's remaining obligations continue. A delayed
answer is applied only with `--expect-state`: the route's fingerprint of the ledger, profile,
packet, HEAD and working-tree diff, so a gate that changed meanwhile refuses it. With `--log` each
transition leaves one line in `doctrine/logs/routing.log`. Changing a tolerance, an expected result,
a baseline, a threshold, an authorization condition or a termination rule is never mechanical,
however small the diff. The profile's Routing lines set the never-fast paths, the consequential
terms and both budgets; `Routing: off` turns routing off and leaves everything else, the judgment
layer included, as it was.

**Decision-quality evidence.** An experiment needs the precision the next
decision needs, not perfect knowledge. Once the competing explanations or
implementations are separated enough to choose the next action, it stops.
"Unknown within this range, and the range does not affect the current
decision" is an acceptable end.

**Tolerances and numerical floors.** Every threshold carries an uncertainty or
tolerance region suited to its measurement: noise, precision, run-to-run
variance, the reference's own spread. A threshold is not set below the
measurement's own floor; the floor is measured or derived before the threshold
is registered. A marginal crossing inside that region does not escalate on its
own; before it is treated as a defect, it is shown materially distinguishable
from the test's own uncertainty.

**Observable impact first.** Failures with an externally observable
consequence rank first: instability, corruption, wrong user-visible behaviour,
inability to complete the target workload, substantial performance loss. A
purely internal discrepancy without demonstrated external impact ranks below
them, unless it invalidates an important benchmark or is a known precursor of
failure.

**Parking** records, in the ledger's short form (Records):

- the issue, stated accurately, as a known defect or an unknown;
- its bound: the known downstream impact, labelled measured or derived;
- its reopen trigger: an observable, its threshold and where it is observed,
  stated so that someone other than its author can tell whether it fired. "If
  it matters later" is not a trigger.

A parked issue stays open in the ledger with its bound. A bound concerns what
the product is meant to support, not what today's callers happen to do:
"nothing reaches it today" bounds nothing. A park names the regimes it lives
in and the regimes its bound was measured in (tags `regime`, `bound-in`); a
reopen trigger is an observable of the regime, not a downstream symptom. Every
result is checked against the parked triggers it can touch, and a fired
trigger reopens its entry. A park whose regime overlaps the current
milestone's, with a bound not measured there, blocks that milestone's packets
until it is re-bounded there or reopened (Triggers).

Parking decides where more investigation has value. It never waives, weakens
or defers an acceptance criterion or a check; never hides a failure; never
parks what an accepted criterion or a merge depends on; never declares correct
what is not. It defers work; it does not accept a limitation, which stays an
owner decision.

**Reprioritization** is triggered by evidence, not by the calendar: a new
scoreboard measurement, a milestone reached, missed or changed, an
optimization missing its expected bound, an architectural finding, several
completed packets, a change in the assumed bottleneck. It re-ranks the whole
open set against the goal hierarchy and reviews every parked entry.

## Lanes

At least one active lane always works directly on the current bottleneck or
milestone. Diagnostic, cleanup, validation and accuracy work may not hold every
lane indefinitely.

## Strategic mode

**Feasibility gate.** Before a long optimization campaign, estimate whether the
current architecture has a credible path to the target: measure cost stage by
stage; apply each projected improvement only to the stages it affects; keep
demonstrated, credible projected and optimistic theoretical improvement
separate. If even the optimistic case materially misses the requirement, local
tuning stops and an architectural investigation opens.

**Reset triggers.** A reset tests whether the project is trapped in a local
solution basin. It runs when one or more hold: many packets improve internals
without moving the project metric; the milestone stays unchanged after
substantial work; reaching the target needs several unverified improvements
stacked; the investigation machinery grows faster than the implementation;
evidence suggests an unfavourable scaling floor; a layer audit (Triggers)
concludes the layer cannot meet the milestone's regime. Successive fixes
exposing deeper fixes in one layer is no longer a judgment: it is the lineage
trigger, which forces the audit first. A reset questions the architecture; it
does not abandon it.

**Reset procedure** (`/doctrine:reset`). Independent agents get the product
goal, the hard constraints, the current architecture as facts and raw
measurements, and nothing else: no ledger, issue ordering, accepted
explanations, proposed fixes, earlier recommendations or favoured precedent.
Several sessions start from deliberately varied perspectives; none sees
another's answer; no consensus is required. Each answers: what would you
choose from scratch; would you choose the current architecture again; what
would you keep, test, change or discard; what is the cheapest experiment that
could falsify your proposal. The candidates, the current architecture scored
as one of them, go side by side to one Decision.

**Agreement.** Agents agreeing is not independent evidence when they share a
model, context or assumptions. It counts as strong evidence only when their
reasoning paths, sources or starting assumptions were meaningfully
independent. Important disagreement is preserved, not merged.

**Falsification first.** A substantial proposal states what it predicts, what
measurement would support it, what result would falsify it, and the cheapest
experiment that could produce that result. Experiments that eliminate large
regions of the design space come first.

## Triggers

Rules that used to depend on someone noticing are checked by
`scripts/doctrine_check.py` at fixed points. It reads the profile, the campaign
file's milestone, the packets and the ledger's Tags column
(`templates/ledger.md`), prints `BLOCK` and `WARN` lines, and exits nonzero on a
`BLOCK`. A `BLOCK` refuses the command that ran it; nobody overrides it by
judgment. The cure is the action it names. Repairing a wrong tag counts as such
an action, provided it is recorded.

| Fixed point | Runs | Blocks on |
|---|---|---|
| `/doctrine:milestone` (a milestone set or changed) | `milestone` | no Id or Regime; an unvalidated milestone oracle; no regime map; a park overlapping the regime |
| `/doctrine:accept` | `accept <task>` | no lineage; a criterion without an oracle, or a reference not validated in the milestone's regimes; a relative comparison without `shares=` and `covered-by=`; an exclusion without `floor=`; a repair without its invariant criterion; a stale citation; an audit due in the packet's lineage; no Readers section, or a reader of a changed name outside Scope and not declared unaffected; for a packet moving the milestone, every milestone block; a reset due on a `decision:` key it names; with a Model in the profile, no Route, a Route not in the model, a falsified route, a route without a bound, or no `Predicts:` naming a Goal term |
| Every commit (the project's guard) | `model --staged` | a ledger result without a model update; an empty Next; a Next item naming no term it moves |
| `/doctrine:prepare`, `/doctrine:run`, `/doctrine:decide` | `triggers [--task]` | an audit due in the lineage they touch; a reset due on a `decision:` key the packet names |
| A decision boundary (Progression, Routing) | `route --action <mechanical, probe, repair, investigate, complete>` | an audit due in the decision's or packet's lineage; a spent probe budget; a question already answered; a reset due; a route applied after its state changed |
| `/doctrine:merge`, after the gate | `merge --apply` | nothing: it marks stale every row resting on a changed path, and every row resting on those |
| The checker, on every log | the profile's invariant markers | a violation line is a failed check |

**Oracle validity.** A criterion names what its verdict is judged against
(`templates/TASK_TEMPLATE.md`, Oracle). A reference is a ledger row that is
validated in named regimes (`validated-in`): shown right there by a
conservation law, an analytic case or convergence under refinement. A
criterion or milestone target resting on a reference not validated in the
milestone's regimes is refused. Validating the reference is then the first
packet.

**Invariant monitors and invariant-first repairs.** The profile names each
invariant the product must keep, how its monitor is switched on, its violation
line, and the run that shows it firing. Every campaign measurement runs with
the monitors on. A violation is a finding whatever the run was for, recorded
with `lineage=invariant:<name>`. A packet that repairs a row carrying an
invariant lineage has a criterion whose oracle is that invariant over the
regime, so a second mechanism breaking the same law fails the same packet.

**Blind spots and coverage floors.** A comparison between two arms is
`relative`. It names what both arms share, which it cannot see, and the check
that covers the shared part. Without that check, the claim stays relative and
cannot stand for an absolute one. An exclusion or admission rule carries the
largest share it may exclude before the check is inconclusive.

**Lineage audit.** Every defect row and every packet names its lineage: the
layer, regime, invariant and criterion its failures count against. Related
failures accumulate per lineage key, from:
- defect rows;
- supersessions (a `## Supersedes` packet);
- any row tagged `severity=foundational`.

A key is due for an audit at the profile's threshold (default 3), or at once
on a foundational finding: one that invalidates a reference, an oracle or a
premise that other results rest on. While an audit is due, no packet, run or
decision in that lineage proceeds except the audit (`/doctrine:audit`). The
audit is one bounded study of the layer:
- a census of the milestone workload with the monitors on;
- the same census at a refined step or resolution;
- the class of defects both show, listed together;
- one Decision on a class-level design.

The audit's row, `kind=audit; covers=...`, clears the rows it explains from
the counts.

**Regime map.** A milestone declares its Id, the regimes its workload reaches,
its oracles and its regime map. The map is a result row tagged
`regime-map=<id>`, and it has three parts:
- the workload run once with the monitors on, and once refined, when the
  workload exists; derived from the milestone's definition, and labelled so,
  when it does not;
- the envelope the workload reaches;
- the envelope the tests cover.

Each gap becomes a coverage item or a park with a bound measured there. No
packet moving the milestone is accepted before the map exists.

**Evidence dependencies.** A result, decision or reference row names what its
truth rests on (`rests-on`: paths or ledger ids). A merge that changes one
marks the row stale, and marks every row resting on a stale row. A stale row
cannot be cited by a packet or a decision until it is re-verified, at which
point its tag is removed with the new evidence.

**Judgment calls.** Between the checks that are code and the decisions that
need reasoning sit recurring calls with a small, fixed set of answers:
- lineage assignment;
- whether a finding is foundational;
- task size;
- oracle kind;
- finding class;
- the gate label;
- trigger form;
- authority routing;
- stale order.

`rules/judgments.md` lists them with their labels, confidence thresholds and
escalate-always labels. A profile may hand them to a fast probabilistic layer
(Judgment layer). It proposes; anything below threshold, consequential, or in
conflict with a check goes to the reasoning agent. It never overrides a
`BLOCK`. Its accepted calls are sampled for calibration at each
reprioritization.

## Records

Every record separates raw measurement, derived result, interpretation and
decision. An interpretation does not become a fact because later agents
inherit it.

The ledger holds current decision-relevant state, one short entry per item:
observation; bound or status; consequence; next decision, if any; and the Tags
column the triggers read (`templates/ledger.md`). Histories, traces and
abandoned investigations live in separate records. No agent should need the
full history to find the next action.

Process overhead: the rough share of work spent on the product, experiments,
doctrine and bookkeeping is tracked at reprioritization. When process
maintenance becomes a substantial fraction, for instance more than half of a
day's commits, without better decisions or progress, the process is
simplified, here in the plugin when the cause is general.

An owner decision the campaign cannot take is an escalation: one file per
decision in `doctrine/escalations/` (`templates/escalation.md`), raised when its
input is ready, committed and pushed, with the owner notified where a channel
exists. An unplanned stop is raised only when every stop condition in the
brief holds. An attack still standing after three rounds is a blocker entry,
not an escalation. The answer is recorded in `campaign.md` with the decider's
words, the date and the channel.

What only a person can do (an account, hardware, a payment, text that cannot
be fetched) is batched in `doctrine/person-actions.md`
(`templates/person-actions.md`): one list, each item with why, the steps and
what shows it is done, so one request covers every open item.

`doctrine/sources/` holds curated external excerpts with URL and date read;
an accepted task names the sources that constrained its design, and the
coordinator gives those excerpts to the implementer and reviewer.

## Task packets

For Packet-size and Decision-size work.

1. The owner and the coordinator agree an interpretation in
   `doctrine/interpretations/<task>.md`. `/doctrine:attack` may test it first.
2. `/doctrine:prepare <task>` sends the scout and the test scout through it and
   writes `doctrine/tasks/<task>.md` as a Draft from `templates/TASK_TEMPLATE.md`.
3. `/doctrine:accept <task>` validates it and changes only its Status and
   Accepted by. Acceptance freezes the packet: changing its goal, design,
   scope, check or criterion needs a follow-up or superseding task.
4. `/doctrine:run <task>` runs, in the packet's own worktree and branch:
   - the implementer;
   - the checker;
   - at most one scoped repair;
   - one review, a single reviewer pass that carries every lens the profile
     names, criteria first.
5. The task ends `Ready for review` only when every check passes and the
   review establishes every criterion without a correctness finding;
   otherwise `Needs Investigation`. The checker runs every Check the packet
   lists, not only the runner's lines, except a Check that needs a quiet
   machine (a timing, a cost, a budget), which the coordinator runs in a quiet
   window. A run whose only open items are those checks ends `Ready for review,
   quiet checks pending`, and the packet is merged only after they pass.
6. `/doctrine:merge <task>` merges a Ready packet into the trunk after
   re-running its checks on the merged tree.
   - The re-check is the merge gate.
   - An independent critic adds a second opinion only when merging the trunk
     into the branch brought code the review never saw. That is, it changed a
     file under the packet's Scope paths (records excepted), or it needed a
     conflict resolved.

**Why one review and a conditional critic.** Separate review agents per lens
read the same diff twice. A critic after a merge that brought only records, or
the owner's untouched paths, re-reads code the review already judged. Both
cost time without a finding the other steps miss. The second opinion stays
where it earns its cost: code that met other code at the merge.

Who accepts is the campaign's Authority: the coordinator accepts packets
written under the brief; an owner decision is recorded with the decider's
words before a packet rests on it.

A packet contains: Status; Goal (observable behaviour); Moves; Size; Area;
Serves; Lineage; Repairs; Supersedes; Accepted Design (only decisions made,
cited); Accepted by; Base; Branch; Scope (narrow paths); Readers (every name
it changes, with the string that finds its readers); Spawn Plan; Checks
(every `blocking.md` line plus focused checks); Criteria (one observable
behaviour per check, each with its Oracle); Blockers; Evidence.

`/doctrine:accept` refuses a packet with placeholders, a nonempty Blockers, no
Moves, a wide Scope, a reader of a changed name outside Scope, a Check that
differs from `blocking.md`, a criterion that names no Check, an Accepted
Design holding a decision nobody made, or any
`BLOCK` from the accept trigger (Triggers). No editing agent starts from a
draft.

## Agent roles

| Agent | Permission | Purpose |
| --- | --- | --- |
| `doctrine:scout` | Read only | Controlling code, patterns, narrow Scope, decisions needed |
| `doctrine:test-scout` | Read only | Each criterion's check, layer, violating fixture, pre-change failure |
| `doctrine:implementer` | Scoped edits | Implement the accepted packet in its worktree; never commits |
| `doctrine:checker` | Commit and run | Commit the work, run the Checks in order, write the diff |
| `doctrine:reviewer` | Read only | Account for every criterion, then findings under every lens the profile names, in one pass |
| `doctrine:critic` | Read only | Attack, refute, result critic, independent review, decision |
| `doctrine:researcher` | Writes research | One research question from primary sources |

The coordinator never runs concurrent editing agents on one worktree. A failed
check naming scoped files gets one repair; a second failure, a scope escape,
missing criterion evidence or a correctness finding ends `Needs
Investigation`.

## Repository checks

Momentum weighs as much as correctness. A gate runs what this change can make
fail, in parallel, fastest first; exhaustive coverage runs where it cannot stall
the next step, and still has an owner when it fails.

`doctrine/blocking.md` is written by hand and defines the checks every packet
runs, each with its command and venue; the profile names the runner. Focused
checks select real tests and fail when the selected test is absent. A new test
asserts the violating fixture its criterion names; it is not shown failing
before it passes (dropped 2026-09-25: the cost outweighed the defects it
caught). "Not run" is never a pass. A check result is evidence for the tree it
ran on, not a certificate for later edits or another machine.

Checks run in two tiers. A blocking line tagged
`[tier: background]` runs in the background tier; every other line runs in the
quick tier, the gate one waits for. The profile names both commands and
whether the tiers may overlap on one machine. A packet is Ready only when both
tiers passed at its commit; a background failure sends it back to its branch.
A line tagged `[reuse: <input>, ...]` may report an earlier pass when its
command and every named input are unchanged; it is tagged only when it names
every input it reads, since a missing one reuses a stale pass. No line is
removed or weakened to fit a tier.

A line runs at a packet's gate only when the packet's diff reaches it. Reach
is computed from the build's dependency graph (every module the line's
binaries link, its test sources, its data), never from judgment about what a
change probably affects; a project whose runner cannot compute it tags lines
`[reach: <path>, ...]` from that graph, and an untagged line always runs. A
diff of records paths only reaches nothing. Every line, reached or not, runs
on the trunk in the background at most once a day and only after a change that
touches code: the trunk sweep. A line protects a route or a belief of the model
(`[protects: <route or belief>]`); when that route is falsified the line leaves
the gate with it, and returns only if the route does. A sweep
failure stops merges that reach the failing line until it is green again; the
newest merge since the last green sweep that reaches it is repaired or
reverted first. Lines that share no state run in parallel; a line that needs
the machine to itself (a timing, a GPU window, a thread count) says so.

A project may enforce its Never list with a guard. The
project keeps it in `doctrine/guard/`: `claude-hook.sh` (a PreToolUse hook: exit
0 allows, exit 2 refuses with the reason on stderr), `githooks/<hook>` for any
git hook, and `fixtures/allow-*.json` and `fixtures/refuse-*.json` (hook input
and the exit it must give). The plugin's `guard/install.sh`, run from the
project root, copies the guard outside the tracked tree (`~/.doctrine-guard/`),
points `core.hooksPath` there, chains each hook to the repository's own
`.githooks/<hook>`, and registers the Claude hook in the untracked
`.claude/settings.local.json` so any failure refuses. `guard/test.sh` runs the
fixtures, then the project's `doctrine/guard/test-githooks.sh` if there is one.
The Claude hook is the early warning; the git hooks enforce. A refusal is the
answer, not an obstacle: fix the cause, never bypass a hook.

## Improving doctrine

A process failure whose cause is general is repaired in this plugin, so every
project that uses it benefits; one whose cause is a project's specifics is
repaired in that project's profile. Git history keeps what each change
replaced.
