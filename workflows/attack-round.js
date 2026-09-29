export const meta = {
  name: 'attack-round',
  description: 'One attack round on a doctrine target: a doctrine:critic per lens, then two refuting verifiers split by lens group',
  whenToUse: 'Launched by /doctrine:attack with args { task, target, lenses: [{key, prompt}], round, commit, root?, plugin }',
  phases: [
    { title: 'Attack', detail: 'one doctrine:critic per lens, attack mode' },
    { title: 'Refute', detail: 'two doctrine:critics in refute mode, one per lens group' },
  ],
}

const task = args && args.task
const interpretation = args && (args.target || args.interpretation)
const plugin = args && args.plugin
const lenses = (args && Array.isArray(args.lenses)) ? args.lenses : []
const round = (args && args.round) || 1
const commit = args && args.commit
const root = args && args.root

if (!task || !interpretation || !commit) {
  throw new Error('attack-round needs args.task, args.target and args.commit')
}
if (!lenses.length) {
  log('No lenses given: nothing attacked')
  return { attacks: [], verdicts: [], summaries: [] }
}

const WHERE = root
  ? `The checkout is ${root}. Work only inside it, and write nothing: this round is read-only.`
  : 'Write nothing: this round is read-only.'

const READ = `The target under attack is ${interpretation} at commit ${commit}. Read that version with ` +
  `\`git show ${commit}:${interpretation}\`, not the working copy, so every critic judges the same text. ` +
  'Read doctrine/profile.md first; the brief and the campaign file it names are what the target answers to' +
  (plugin ? `, and the doctrine rules are at ${plugin}/rules/. ` : '. ') +
  `This is round ${round}. Earlier rounds, if any, are doctrine/research/${task}/attack-<n>.md: do not repeat an ` +
  `attack an earlier round refuted or answered, unless you show the answer failed.`

const ATTACKS = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: 'The lens verdict on the interpretation in one paragraph, with when the evidence was read' },
    attacks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          target: { type: 'string', description: 'File, section and line range attacked' },
          attack: { type: 'string', description: 'What is wrong, stated so it can be checked' },
          kind: { type: 'string', enum: ['omission', 'mechanism', 'unjustified', 'risk', 'contradiction', 'not-checkable', 'wrong-order', 'wrong-fact'] },
          severity: { type: 'string', enum: ['blocking', 'major', 'minor'] },
          evidence: { type: 'string', description: 'file:line citations, commands run with their output, or URLs with the date read' },
          proposed_change: { type: 'string', description: 'The smallest change that answers the attack' },
        },
        required: ['target', 'attack', 'kind', 'severity', 'evidence', 'proposed_change'],
      },
    },
  },
  required: ['summary', 'attacks'],
}

const VERDICTS = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['stands', 'partly', 'refuted', 'duplicate'] },
          severity: { type: 'string', enum: ['blocking', 'major', 'minor'], description: 'The verifier\'s severity, which the record uses' },
          duplicate_of: { type: 'string', description: 'The id this duplicates, or empty' },
          reason: { type: 'string', description: 'What was checked, with citations; for partly, which part stands' },
        },
        required: ['id', 'verdict', 'severity', 'duplicate_of', 'reason'],
      },
    },
  },
  required: ['verdicts'],
}

phase('Attack')
const found = await parallel(lenses.map((lens) => () => agent(
  `Attack mode, lens "${lens.key}".\n\n${WHERE}\n\n${READ}\n\n${lens.prompt}\n\n` +
  'Attack only through this lens. Evidence every attack: a file:line, a command and its output, or a URL and ' +
  'the date read. Grade each blocking, major or minor, and propose the smallest change that answers it. ' +
  'Never propose editing the frozen brief or a recorded decision: an attack on either is ' +
  'recorded as such, with the owner decision it would need.',
  { label: `attack:${lens.key}`, phase: 'Attack', agentType: 'doctrine:critic', schema: ATTACKS },
)))

const summaries = []
const attacks = []
found.forEach((res, i) => {
  const lens = lenses[i]
  if (!res) {
    log(`Lens ${lens.key}: the critic returned nothing; the lens is unattacked this round`)
    summaries.push({ lens: lens.key, summary: 'NOT RUN: the critic returned nothing' })
    return
  }
  summaries.push({ lens: lens.key, summary: res.summary })
  res.attacks.forEach((a, k) => {
    attacks.push(Object.assign({ id: `${task}-${lens.key}-${k + 1}`, lens: lens.key, group: 0 }, a))
  })
})

if (!attacks.length) {
  log('No attacks found: nothing to refute')
  return { attacks: [], verdicts: [], summaries }
}

const half = Math.ceil(lenses.length / 2)
attacks.forEach((a, k) => {
  const li = lenses.findIndex((l) => l.key === a.lens)
  a.group = lenses.length > 1 ? (li < half ? 0 : 1) : (k % 2)
})

const index = attacks.map((a) => `- ${a.id}: ${a.attack.slice(0, 200)}`).join('\n')

phase('Refute')
const judged = await parallel([0, 1].map((g) => () => {
  const mine = attacks.filter((a) => a.group === g)
  if (!mine.length) return Promise.resolve({ verdicts: [] })
  return agent(
    `Refute mode.\n\n${WHERE}\n\n${READ}\n\n` +
    'Try to refute each attack below. Default to refuted when the evidence does not hold up on your own ' +
    'reading: re-read every cited line, re-run every cited command, re-open every cited URL. "partly" means ' +
    'some of it stands; say which part. Mark an attack duplicate when another attack in the full list makes ' +
    'the same point, naming the one kept. Grade the severity yourself.\n\n' +
    `Attacks to judge (${mine.length}):\n${JSON.stringify(mine, null, 2)}\n\n` +
    `The full list, for duplicates only:\n${index}\n\n` +
    'Return one verdict per attack to judge, by id.',
    { label: `refute:group-${g + 1}`, phase: 'Refute', agentType: 'doctrine:critic', schema: VERDICTS },
  )
}))

const verdicts = []
const byId = {}
judged.forEach((res) => { if (res) res.verdicts.forEach((v) => { byId[v.id] = v }) })
attacks.forEach((a) => {
  if (byId[a.id]) {
    verdicts.push(byId[a.id])
  } else {
    verdicts.push({ id: a.id, verdict: 'unjudged', severity: a.severity, duplicate_of: '', reason: 'No verifier returned a verdict for it' })
  }
})
const unjudged = verdicts.filter((v) => v.verdict === 'unjudged').length
if (unjudged) log(`${unjudged} attacks unjudged: the record carries them as standing until a verifier judges them`)

const standing = verdicts.filter((v) => v.verdict === 'stands' || v.verdict === 'partly').length
log(`${attacks.length} attacks, ${standing} standing, ${unjudged} unjudged`)

return { attacks, verdicts, summaries }
