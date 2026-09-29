export const meta = {
  name: 'run-packet',
  description: 'Run one accepted doctrine packet in its worktree: implement, check, at most one repair, then one review per mode',
  whenToUse: 'Launched by /doctrine:run with args { task, packet, worktree, logdir, base, branch, runner, reviews, plugin, prompt_block? }',
  phases: [
    { title: 'Implement', detail: 'doctrine:implementer changes Scope inside the worktree' },
    { title: 'Check', detail: 'doctrine:checker commits and runs the Checks with the profile runner' },
    { title: 'Repair', detail: 'at most one repair implementer, then the checker again' },
    { title: 'Review', detail: 'one doctrine:reviewer pass, every lens, criteria first' },
  ],
}

const task = args && args.task
const packet = args && args.packet
const wt = args && args.worktree
const logdir = args && args.logdir
const base = args && args.base
const branch = args && args.branch
const runner = args && args.runner
const plugin = args && args.plugin
const reviews = (args && Array.isArray(args.reviews) && args.reviews.length)
  ? args.reviews
  : [{ mode: 'criteria', lens: '' }]
const promptBlock = (args && args.prompt_block) || ''

if (!task || !packet || !wt || !logdir || !base || !branch || !runner || !plugin) {
  throw new Error('run-packet needs args.task, packet, worktree, logdir, base, branch, runner and plugin')
}

const WHERE = `The worktree is ${wt}, on branch ${branch}. Work only inside it: every read, edit and command ` +
  `runs there (git -C ${wt}, or cd ${wt} first). Never check out another branch. Read ${wt}/doctrine/profile.md ` +
  `first. The doctrine rules are at ${plugin}/rules/.` +
  (promptBlock ? `\n\nProject block:\n${promptBlock}` : '')

const IMPLEMENTED = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: 'What the change does, for the commit message' },
    files_changed: { type: 'array', items: { type: 'string' } },
    tests: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          test: { type: 'string', description: 'The test or check that holds the criterion' },
        },
        required: ['criterion', 'test'],
      },
    },
    installs: { type: 'array', items: { type: 'string' }, description: 'Each install: tool, version, command, where' },
    blockers: { type: 'array', items: { type: 'string' }, description: 'Anything the packet needs that it does not decide' },
  },
  required: ['summary', 'files_changed', 'tests', 'installs', 'blockers'],
}

const CHECKED = {
  type: 'object',
  properties: {
    branch: { type: 'string', description: `The output of git -C ${wt} rev-parse --abbrev-ref HEAD` },
    branch_ok: { type: 'boolean' },
    commit: { type: 'string', description: 'The commit the Checks ran on, or empty' },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          required: { type: 'boolean' },
          result: { type: 'string', enum: ['pass', 'fail', 'not run'] },
          log: { type: 'string', description: 'Absolute path of the check\'s log' },
          detail: { type: 'string', description: 'For a failure, the failing lines; for not run, what it needs' },
          named_files: { type: 'array', items: { type: 'string' }, description: 'Files the failure names' },
          in_scope: { type: 'boolean', description: 'Whether any named file is in the packet\'s Scope' },
        },
        required: ['name', 'required', 'result', 'log', 'detail', 'named_files', 'in_scope'],
      },
    },
    patch_path: { type: 'string', description: 'Absolute path of diff.patch, or empty' },
  },
  required: ['branch', 'branch_ok', 'commit', 'checks', 'patch_path'],
}

const REVIEWED = {
  type: 'object',
  properties: {
    mode: { type: 'string' },
    criteria: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          status: { type: 'string', enum: ['met', 'not met', 'not shown'] },
          evidence: { type: 'string', description: 'The check, log line or diff hunk that shows it' },
        },
        required: ['criterion', 'status', 'evidence'],
      },
    },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          kind: { type: 'string', enum: ['correctness', 'advisory'] },
          lens: { type: 'string', description: 'The lens the finding comes from: criteria, or a lens the profile names' },
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          detail: { type: 'string' },
        },
        required: ['kind', 'lens', 'file', 'line', 'summary', 'detail'],
      },
    },
  },
  required: ['mode', 'criteria', 'findings'],
}

function implement(extra, label, ph) {
  return agent(
    `${WHERE}\n\nImplement the accepted packet below for task ${task}. Change only its Scope, matching the ` +
    'surrounding code and the conventions the profile lists. Add the tests its Criteria need; show one failing ' +
    'before the change only when the profile or the packet asks for it. Run first the check most likely to decide ' +
    'the packet. Record every install. Do not commit, push or merge: the checker commits. Anything the packet does not decide goes in blockers, not ' +
    `into the code.${extra}\n\n--- PACKET ---\n${packet}\n--- END PACKET ---`,
    { label, phase: ph, agentType: 'doctrine:implementer', schema: IMPLEMENTED },
  )
}

function check(dir, summary, label, ph) {
  return agent(
    `${WHERE} The one exception is ${dir}, where you write logs and the patch.\n\n` +
    `1. Assert that \`git -C ${wt} rev-parse --abbrev-ref HEAD\` prints ${branch}. If it does not, stop: ` +
    'return branch_ok false with the branch you saw, no commit, no checks and no patch.\n' +
    `2. Commit the implementer's work on ${branch}: \`git -C ${wt} add -A\`, then a commit whose message ` +
    `describes what the change does. The implementer reported: ${summary}\n` +
    `3. Run the Checks in order from inside ${wt} with the profile's runner: ${runner.split('LOGDIR').join(dir)}. ` +
    'Report every line the runner lists, with its log. A line marked "not run" is reported as not run, never ' +
    'as a pass. Then run every other Check the packet lists, as the packet writes it, each with its own log. ' +
    'A Check that needs a quiet machine (a timing, a cost or a budget) is reported as not run with the reason ' +
    '"quiet window"; the coordinator runs it. A Check you cannot run as written is reported as not run with ' +
    'what it needs. For each failure, list the files it names and whether any is in the packet\'s Scope. ' +
    'Then search every log you wrote for each violation line the profile\'s Invariant monitors section names; ' +
    'each match is a failed Check named "invariant: <name>", with the matching lines as its detail.\n' +
    `4. Write \`git -C ${wt} diff ${base}..HEAD\` to ${dir}/diff.patch and return that path.\n\n` +
    'You edit no file, except temporary instrumentation, a temporary cherry-pick or a temporary patch a ' +
    'Check names, in this worktree or the one the Check names, kept uncommitted and reverted before you ' +
    `return, leaving every tree exactly as you found it.\n\n--- PACKET ---\n${packet}\n--- END PACKET ---`,
    { label, phase: ph, agentType: 'doctrine:checker', schema: CHECKED },
  )
}

function failed(c) {
  return !c || !c.branch_ok ? [] : c.checks.filter((x) => x.result === 'fail')
}

phase('Implement')
const implemented = await implement('', 'implement', 'Implement')
if (!implemented) log('The implementer returned nothing; the checker still records the tree as it stands')

phase('Check')
let checked = await check(logdir, implemented ? implemented.summary : 'nothing (the implementer returned no report)', 'check', 'Check')
const first = checked
let repaired = null

if (!checked || !checked.branch_ok) {
  const why = checked ? `the worktree is on ${checked.branch}, not ${branch}` : 'the checker returned nothing'
  log(`${why}: no review, Needs Investigation`)
  return {
    status: 'Needs Investigation',
    reasons: [why],
    checks: checked ? checked.checks : [],
    reviews: [],
    implemented,
    first_check: first,
    repaired: null,
    patch_path: '',
  }
}

const scoped = failed(checked).filter((x) => x.in_scope)
if (scoped.length) {
  phase('Repair')
  log(`${scoped.length} failed Checks name scoped files: one repair`)
  const failures = scoped.map((x) => `- ${x.name}: ${x.detail} (log ${x.log}; files ${x.named_files.join(', ')})`).join('\n')
  repaired = await implement(
    `\n\nThis is the one repair. The first attempt is committed. These Checks failed, naming files in Scope:\n${failures}\n` +
    'Read each log. Repair only what a failure shows is wrong; if the test or an assumption is what is wrong, say ' +
    'so in blockers instead of changing the check.',
    'repair', 'Repair',
  )
  if (repaired && Array.isArray(repaired.files_changed) && repaired.files_changed.length === 0) {
    log('The repair changed no file: the first check stands, and no second check runs on an unchanged tree')
  } else {
    const again = await check(`${logdir}/repair`, repaired ? repaired.summary : 'nothing (the repair returned no report)', 'check again', 'Repair')
    if (again) checked = again
    else log('The second check returned nothing; the first check stands')
  }
} else if (failed(checked).length) {
  log('Checks failed outside Scope: no repair')
}

phase('Review')
const evidence = JSON.stringify({ checks: checked.checks, commit: checked.commit, implemented, repaired }, null, 2)
// One reviewer, one pass, every lens (rules/DESIGN.md, Task packets 4): criteria first, then each other lens.
const lenses = reviews.filter((r) => r.mode !== 'criteria')
const lensText = lenses.map((r) => `- ${r.mode}: ${r.lens || 'the lens the profile gives for it'}`).join('\n')
const single = await agent(
  `${WHERE} You read only; you change nothing.\n\n` +
  'Review in one pass, criteria first. Account for every Criterion in the packet: met, not met, or not shown, each with the ' +
  'check, log line or hunk that shows it. A criterion met only against a mock or stub of the component under test is not met. ' +
  'A criterion whose only Check is a quiet-window Check the checker left to the coordinator is "not shown", and says so. ' +
  'Read each criterion\'s Oracle: a relative one is met only as far as its covered-by check also passed, and one whose ' +
  'evidence rests on the arms it compares, or on a reference the packet does not name, is a correctness finding. ' +
  'Read a marginal numerical crossing against the check\'s tolerance region. Then review the diff under each of these lenses, ' +
  `tagging every finding with its lens (use "criteria" for findings from the criteria pass):\n${lensText || '- (no other lens)'}\n\n` +
  `Read the diff at ${checked.patch_path} and the checker's evidence below. Findings are correctness or advisory.\n\n` +
  `--- EVIDENCE ---\n${evidence}\n--- END EVIDENCE ---\n\n--- PACKET ---\n${packet}\n--- END PACKET ---`,
  { label: 'review', phase: 'Review', agentType: 'doctrine:reviewer', schema: REVIEWED },
)
const done = [single ? { ...single, mode: 'criteria+' + lenses.map((r) => r.mode).join('+') } : { mode: 'review', criteria: [], findings: [], missing: true }]

const reasons = []
const quiet = []
if (!checked.branch_ok) reasons.push(`after the repair the worktree is on ${checked.branch}, not ${branch}`)
if (!implemented) reasons.push('the implementer returned nothing')
if (!checked.checks.length) reasons.push('no Check ran: an empty run is never a pass')
if (!checked.patch_path) reasons.push('no diff.patch was written')
checked.checks.filter((x) => x.result === 'fail').forEach((x) => reasons.push(`check failed: ${x.name}`))
checked.checks.filter((x) => x.required && x.result === 'not run').forEach((x) => (/quiet window/i.test(x.detail) ? quiet : reasons).push(`required check not run: ${x.name}`))
done.filter((r) => r.missing).forEach((r) => reasons.push(`the ${r.mode} review returned nothing`))
done.forEach((r) => r.findings.filter((f) => f.kind === 'correctness').forEach((f) => reasons.push(`${f.lens || r.mode} correctness finding: ${f.file}:${f.line} ${f.summary}`)))
const crit = done[0]
if (crit && !crit.missing) {
  if (!crit.criteria.length) reasons.push('the criteria review accounted for no Criterion')
  crit.criteria.filter((c) => c.status !== 'met' && !/quiet/i.test(c.evidence)).forEach((c) => reasons.push(`criterion ${c.status}: ${c.criterion}`))
}
if (implemented && implemented.blockers.length) implemented.blockers.forEach((b) => reasons.push(`implementer blocker: ${b}`))
if (repaired && repaired.blockers.length) repaired.blockers.forEach((b) => reasons.push(`repair blocker: ${b}`))

const status = reasons.length ? 'Needs Investigation' : (quiet.length ? 'Ready for review, quiet checks pending' : 'Ready for review')
log(`${status}${reasons.length ? `: ${reasons.length} reasons` : ''}`)

return {
  status,
  reasons,
  quiet_pending: quiet,
  checks: checked.checks,
  reviews: done,
  implemented,
  first_check: first,
  repaired,
  patch_path: checked.patch_path,
}
