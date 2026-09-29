export const meta = {
  name: 'research-lanes',
  description: 'Research one question: doctrine:researcher lanes from primary sources, then a result critic',
  whenToUse: 'Launched by /doctrine:research with args { question, lanes: [{key, prompt}], topic, root?, plugin? }',
  phases: [
    { title: 'Lanes', detail: 'one doctrine:researcher per lane, primary sources only' },
    { title: 'Critic', detail: 'one doctrine:critic recomputes the result' },
  ],
}

const question = args && args.question
const lanes = (args && Array.isArray(args.lanes)) ? args.lanes : []
const topic = args && args.topic
const root = args && args.root

if (!question || !topic) {
  throw new Error('research-lanes needs args.question and args.topic')
}
if (!lanes.length) {
  log('No lanes given: nothing researched')
  return { lanes: [], critic: null }
}

const dir = root ? `${root}/doctrine/research/${topic}` : `doctrine/research/${topic}`
const WHERE = root
  ? `The checkout is ${root}. Work only inside it. Write only into ${dir}/.`
  : `Write only into ${dir}/.`

const FIGURES = {
  type: 'object',
  properties: {
    answer: { type: 'string', description: 'The lane\'s answer to its part of the question, in a few sentences' },
    figures: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'What the figure measures, with its unit' },
          value: { type: 'string' },
          kind: { type: 'string', enum: ['evidence', 'derived', 'assumption'], description: 'evidence: read at a primary source; derived: computed from other figures; assumption: neither' },
          basis: { type: 'string', description: 'evidence: the quoted passage; derived: the formula and the figures it uses; assumption: why it is assumed' },
          source: { type: 'string', description: 'The primary source URL, or the file:line, or empty for an assumption' },
          date: { type: 'string', description: 'The date the source was read, YYYY-MM-DD' },
        },
        required: ['name', 'value', 'kind', 'basis', 'source', 'date'],
      },
    },
    blocked: {
      type: 'array',
      description: 'Pages that could not be read, reported as blocked rather than guessed around',
      items: {
        type: 'object',
        properties: {
          url: { type: 'string' },
          reason: { type: 'string', description: 'The status or error seen, and the date' },
        },
        required: ['url', 'reason'],
      },
    },
    notes_path: { type: 'string', description: 'The lane\'s notes file under the topic directory' },
  },
  required: ['answer', 'figures', 'blocked', 'notes_path'],
}

const CRITIQUE = {
  type: 'object',
  properties: {
    justifies_repair: { type: 'boolean', description: 'Whether the result justifies a repair or a decision, as it stands' },
    repair_must_check: { type: 'array', items: { type: 'string' }, description: 'What a packet built on this result must check' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          lane: { type: 'string' },
          figure: { type: 'string', description: 'The figure\'s name, or empty for a lane-wide finding' },
          problem: { type: 'string', description: 'What does not hold: a source that does not say it, a derivation that does not recompute, an assumption presented as evidence, a secondary source' },
          correction: { type: 'string' },
        },
        required: ['lane', 'figure', 'problem', 'correction'],
      },
    },
    recomputed: { type: 'string', description: 'Each derived figure recomputed, with the result' },
    next_experiment: { type: 'string', description: 'The smallest next experiment or reading, stated only after the repair question' },
  },
  required: ['justifies_repair', 'repair_must_check', 'findings', 'recomputed', 'next_experiment'],
}

phase('Lanes')
const results = await parallel(lanes.map((lane) => () => agent(
  `Research lane "${lane.key}" on the question: ${question}\n\n${WHERE}\n\n${lane.prompt}\n\n` +
  'Primary sources only: the authority, the standard, the maintainer, the vendor\'s own pricing or documentation page. ' +
  'Never a summary site or a search result. Every figure carries its URL and the date you read it. A page ' +
  'that refuses you (403, a login, a captcha) goes in blocked; never fill its figure from elsewhere. Label ' +
  'each figure evidence, derived or assumption, honestly: a figure you did not read is not evidence. ' +
  `Write your notes to ${dir}/${lane.key}.md and return its path.`,
  { label: `lane:${lane.key}`, phase: 'Lanes', agentType: 'doctrine:researcher', schema: FIGURES },
)))

const laneResults = lanes.map((lane, i) => (results[i]
  ? Object.assign({ key: lane.key }, results[i])
  : { key: lane.key, answer: 'NOT RUN: the researcher returned nothing', figures: [], blocked: [], notes_path: '' }))
laneResults.filter((r) => !r.figures.length).forEach((r) => log(`Lane ${r.key}: no figures`))

phase('Critic')
const critic = await agent(
  `Result mode. Critic for the question: ${question}\n\n${WHERE} As critic you write nothing.\n\n` +
  `The lanes' results:\n${JSON.stringify(laneResults, null, 2)}\n\n` +
  'Recompute every derived figure from the figures it names. Re-open a sample of evidence sources and ' +
  'check each says what is claimed, including every figure the answer turns on. Flag an assumption ' +
  'presented as evidence, a secondary source, a missing date, and a blocked page that was guessed ' +
  'around. Say first whether the result justifies a repair or a decision and what that packet must ' +
  'check; only then the smallest next experiment.',
  { label: 'critic', phase: 'Critic', agentType: 'doctrine:critic', schema: CRITIQUE },
)
if (!critic) log('The critic returned nothing: the result has no critic and nothing may depend on it yet')

return { lanes: laneResults, critic }
