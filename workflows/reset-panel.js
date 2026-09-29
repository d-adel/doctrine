export const meta = {
  name: 'reset-panel',
  description: 'Independent architecture reset: one doctrine:critic in reset mode per starting perspective, from a fact sheet only, no consensus',
  whenToUse: 'Launched by /doctrine:reset with args { facts, perspectives: [{key, lens, model?}], root, plugin }',
  phases: [{ title: 'Reset', detail: 'one independent session per perspective' }],
}

const facts = args && args.facts
const perspectives = (args && Array.isArray(args.perspectives)) ? args.perspectives : []
const root = args && args.root
const plugin = args && args.plugin

if (!facts || !root) {
  throw new Error('reset-panel needs args.facts and args.root')
}
if (!perspectives.length) {
  log('No perspectives given: nothing reset')
  return []
}

const ANSWER = {
  type: 'object',
  properties: {
    from_scratch: { type: 'string', description: 'The architecture you would choose from scratch, concrete, with where each stage runs' },
    choose_current_again: { type: 'string', enum: ['yes', 'partly', 'no'] },
    choose_current_again_why: { type: 'string' },
    keep: { type: 'array', items: { type: 'string' } },
    test: { type: 'array', items: { type: 'string' } },
    change: { type: 'array', items: { type: 'string' } },
    discard: { type: 'array', items: { type: 'string' } },
    cost: {
      type: 'object',
      properties: {
        demonstrated: { type: 'string', description: 'What your design has already shown somewhere, with the source; or none' },
        credible: { type: 'string', description: 'A projection built stage by stage, each improvement applied only to the stages it affects' },
        optimistic: { type: 'string', description: 'The theoretical floor, stage by stage' },
      },
      required: ['demonstrated', 'credible', 'optimistic'],
    },
    meets_target: { type: 'string', description: 'Whether the credible case meets the target, and if only in part, what decides the part' },
    falsification: {
      type: 'object',
      properties: {
        prediction: { type: 'string' },
        supporting_result: { type: 'string' },
        falsifying_result: { type: 'string' },
        cheapest_experiment: { type: 'string', description: 'Concrete, runnable in this repository, with its expected cost' },
      },
      required: ['prediction', 'supporting_result', 'falsifying_result', 'cheapest_experiment'],
    },
    biggest_risk: { type: 'string' },
  },
  required: ['from_scratch', 'choose_current_again', 'choose_current_again_why', 'keep', 'test', 'change', 'discard', 'cost', 'meets_target', 'falsification', 'biggest_risk'],
}

const BASE = `Reset mode. You are one of several independent perspectives on whether this project is trapped in a ` +
  `local solution basin. Others answer from other starting points; you will not see their answers and nobody ` +
  `needs to agree.\n\nThe checkout is ${root}. Read ${root}/${facts} first: the goal, the hard constraints, the ` +
  `current architecture as facts and the raw measurements. You may read code to check a fact. Do not read the ` +
  `ledger, the campaign file, packets, interpretations, research, sources or earlier reset answers: they carry ` +
  `the current trajectory, which you must not inherit. Mark what is fact, inference or hypothesis. Edit no file.` +
  (plugin ? `\n\nThe reset procedure is in ${plugin}/rules/DESIGN.md, Strategic mode.` : '')

phase('Reset')
const answers = await parallel(perspectives.map((p) => () => agent(
  `${BASE}\n\nYour starting perspective: ${p.lens}`,
  Object.assign(
    { label: `reset:${p.key}`, phase: 'Reset', agentType: 'doctrine:critic', schema: ANSWER },
    p.model ? { model: p.model } : {},
  ),
).then((r) => r && Object.assign({ perspective: p.key, model: p.model || 'session' }, r))))

const got = answers.filter(Boolean)
if (got.length < perspectives.length) log(`${perspectives.length - got.length} perspectives returned nothing`)
return got
