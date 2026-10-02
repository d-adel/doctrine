# Workflow runs

How a run is carried out. What to work on, when to stop and when to park is
`DESIGN.md` (Goal hierarchy, Task size, Progression, Lanes, Strategic mode).
These rules govern Packet-size and Decision-size work; a Direct task runs in
the coordinator's own session with only the rules its steps touch. Numbers the
project sets (concurrency, build kit, pitfalls) are in its
`doctrine/profile.md`.

## Rules

- **Concurrency.** Launch against live machine load: check what is already
  running and size the launch to what is free, within the profile's limit on
  build-heavy runs; a run that would saturate the machine beside a running one
  waits for it. One build slot belongs to the milestone lane (`DESIGN.md`,
  Lanes). Two runs never write the same worktree, no run writes the main
  checkout while a packet run uses it, nothing builds or tests during a quiet
  timing, and work that can decide a branch goes before a larger run that
  cannot. Read-only reviews, critics and surveys fan out within the Workflow
  tool's per-workflow limit.
- **Premises at acceptance.** Before a packet is accepted or a round launched,
  each premise of its Accepted Design is checked against the trunk at its
  recorded Base: every caller of each function it changes, every reader of
  each name it changes (the packet's Readers, which the accept trigger greps),
  and every merge since its evidence was taken (the stale marks do the last
  part: `DESIGN.md`, Triggers). A premise that cannot be checked from the repository
  is a Blocker; a false premise amends the packet before the run. Each new
  criterion is shown passable on an arm known to have the property at a
  quantity the measurement resolves, and states its tolerance region; a criterion no arm can meet is repaired before
  registration.
- **Monitors on.** Every campaign measurement runs with every invariant
  monitor the profile names switched on, and reports every violation line as a
  finding, whatever the run was for.
- **Decisive slice first.** Each agent first runs the smallest piece of work
  whose result decides its packet or lane, and stops there if it fails.
  Coverage runs last, and only while the outcome is still open.
- **Stop on evidence.** An agent stops as soon as every criterion has its
  evidence or one decisively fails. Remaining steps are not a reason to
  continue; an open question is.
- **Probe before a full round.** Before a workflow fans out, one agent runs the
  smallest version of the task and confirms the prompt, paths and tools work.
- **Localize before testing one mechanism.** Find where a failure is (file,
  step, row, build by commit and tree) before building an experiment around
  why; prefer the measurement that separates the most supported mechanisms,
  and never test one the record already contradicts.
- **Discovery and confirmation.** A criterion registered before a run is
  settled by that run, unless the run's critic finds a defect in the criterion.
  A verdict drawn from arms, averages or thresholds chosen after the run is
  discovery: it may stop or park a route, and advances one only after a
  registered confirmation. A bar registered after discovery comes from the
  intended property, never from a value the slice observed.
- **Prior art before research.** Before an architecture or research round on a
  problem with substantial prior work, a bounded survey records the established
  methods, their assumptions and evidence, and what stays open; literature is
  not authority, and a rediscovered technique is integrated and compared, not
  re-researched. Ordinary bugs need no survey.
- **Stopping runs.** No time estimates: no expected durations, ranges, time
  boxes or estimate-based timeouts in prompts, packets or reports. An agent
  continues only while it adds evidence toward the verdict. The coordinator
  checks the newest logs on every completion notice, and stops or narrows a
  run whose deciding evidence already exists or that has stopped producing any.
- **Machine time.** Run the smallest slice first (one body, a few steps); make
  progress lines flush, so a killed run still shows how far it got; kill a run
  that has gone silent; skip a level that cannot change the verdict.
- **Never wait in the foreground.** Long commands and workflows run in the
  background; a foreground sleep or blocking watch loop is never how a wait
  happens.
- **Carry forward.** A lane starts from what earlier packets, research and logs
  established and is told where they are; evidence ends with a carry-forward
  note. A fact already recorded with its source is cited, not looked up again.
- **Commit as you go.** Work is committed on its branch as it lands; a result
  that exists only in a working tree or a session is not a result. During an
  active investigation findings are committed as notes, and the ledger, model
  and campaign file change at the next checkpoint in one commit (`DESIGN.md`,
  Records).
- **Timings.** Timings under load are provisional; a number for a verdict is
  measured quiet and back to back, in the build the profile names.
- **Independent decisions.** Where the campaign's Authority delegates a
  Decision, a `doctrine:critic` in decision mode takes it in a fresh context
  with only the brief, the goal hierarchy and the evidence. It asks the
  progression gate first, tests the options rather than adopting them, and
  answers with the choice, its reasons marked fact, inference or hypothesis,
  what would change it, and the one reason each rejected option loses. Its
  answer binds and never by itself licenses a descendant. A strategic
  question goes to a reset, not to a single-issue decision.
- **Route at decision boundaries.** Before choosing consequential next work, after a result, and
  before calling a question or task complete, run `doctrine_check.py route` (`DESIGN.md`,
  Progression, Routing) and follow its route, keeping every `OPEN` obligation it lists. A fast
  route needs only its confirming check: no critic, hypothesis packet or extra agent is added for
  its own sake. A bounded route runs one probe, then records its outcome under the decision's
  lineage; an inconclusive probe goes on by the reasoning path, not a second cheap probe.
- **Critics.** Every result a Decision rests on gets a `doctrine:critic` in
  result mode before the Decision is taken. It recomputes the result from its
  logs; its first question is the progression gate.

## Prompt block

Every lane's prompt carries these blocks, filled in, never rewritten per lane;
the task-specific part goes below them. The profile adds the project's own
block (build kit, code rules, pitfalls).

For every agent that builds or runs:

> Run first the check most likely to decide
> this task: C. Stop as soon as every criterion has its evidence or one
> decisively fails; do no diagnostics or extra measurements beyond the
> criteria, the listed measurements and that decision; mark anything not run.
> A crossing inside a threshold's tolerance region is reported with the
> region, not treated as a defect. Do not open a new question, probe or
> packet: report what you found and stop. Continue only while your steps
> still add evidence toward the verdict.
>
> Run every measurement with the profile's invariant monitors on, and report
> every violation line as a finding, whatever this task is for.
>
> Where to work: TREE on BRANCH (commit BASE). Change nothing outside it. The
> code you change or read: LOCATIONS. Commands: COMMANDS. Earlier logs that
> already answer a run: REUSE. Every log begins with the tree, commit, dirty
> state and exact command. Other lanes run on this machine: kill only a PID you
> started, never a process by its image name.

For every critic and reviewer:

> Read-only. Recompute the result yourself and apply the
> registered outcome or the packet's criteria, reading a marginal crossing
> against the measurement's tolerance region. Then apply the progression gate
> (`DESIGN.md`): does this block the current milestone? Say whether the result
> justifies a repair and what its packet must check; name a next experiment
> only if its answer can change a project-level decision, unblock the
> milestone or prevent a materially incorrect measurement, within its
> investigation budget. For what stays open, say what to park: its bound and
> an objective reopen trigger. Keep raw measurement, derived result,
> interpretation and decision apart. Return your verdict, the disagreements,
> and one short ledger line: observation; bound or status; consequence; next
> decision.
