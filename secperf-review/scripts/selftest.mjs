// Offline check of review.workflow.js orchestration logic with mocked agents. Run: node scripts/selftest.mjs
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const dir = dirname(dirname(fileURLToPath(import.meta.url)))
const src = readFileSync(join(dir, 'review.workflow.js'), 'utf8')
const [head, body] = src.split('\nconst A = args')
const mod = join(mkdtempSync(join(tmpdir(), 'secperf-')), 'wf.mjs')
writeFileSync(mod, `${head}\nexport async function run(args, agent, pipeline, log, phase) {\nconst A = args${body}\n}\n`)
const { run } = await import(mod)

const f = (id, severity, line, file = 'web/modules/custom/x/src/C.php') =>
  ({ id, area: 'security', severity, file, line, code: 'x', path: 'p', why: 'w', fix: 'f', confidence: 'high' })
const calls = []
const agent = async (prompt, o) => {
  calls.push(o)
  if (o.label === 'find:drupal-1') return { findings: [f('DSEC-01', 'high', 10), f('DSEC-02', 'medium', 10), f('DPERF-05', 'medium', 20), f('DSEC-09', 'low', 30), { ...f('DSEC-03', 'high', 40), code: '' }], positives: ['ok'], not_checked: [] }
  if (o.label === 'find:a11y-1') return null
  if (o.label === 'verify:drupal-1') return { verdicts: [
    { index: 0, outcome: 'confirmed', severity: 'high', evidence: 'e' },
    { index: 1, outcome: 'confirmed', severity: 'medium', evidence: 'e' },
    { index: 2, outcome: 'refuted', severity: 'medium', evidence: 'cached upstream' },
  ] }
  if (o.label === 'judge:fable') return { rulings: [{ key: 'web/modules/custom/x/src/C.php:10', ruling: 'downgrade', severity: 'medium', reason: 'r' }] }
  throw new Error('unexpected agent ' + o.label)
}
const pipeline = (items, ...stages) => Promise.all(items.map(async (it, i) => {
  let v = it
  for (const s of stages) { v = await s(v, it, i); if (v == null) return null }
  return v
}))
const args = { skillDir: dir, repoRoot: '/r', base: 'abc', baseLabel: 'origin/main', notes: [], only: ['a11y', 'cache', 'performance', 'security'],
  deep: true, shards: { drupal: [[{ path: 'a.php', status: 'M', lines: 5 }]], nextjs: [], a11y: [[{ path: 'b.twig', status: 'M', lines: 3 }]] },
  seamFinder: false, decoupledRef: false, manifests: [], infra: ['nginx.conf'], versions: {}, audits: {}, skipped: [] }

const out = await run(args, agent, pipeline, () => {}, () => {})
assert.deepEqual(calls.map(c => c.model), ['opus', 'sonnet', 'opus', 'fable'])
assert.equal(out.findings.length, 1, 'same-line findings collapse into one')
assert.equal(out.findings[0].id, 'DSEC-01')
assert.deepEqual(out.findings[0].also, ['DSEC-02'])
assert.equal(out.findings[0].severity, 'medium', 'Fable downgrade applied')
assert.equal(out.refuted.length, 1)
assert.equal(out.notes_low.length, 1, 'low goes to notes without verification')
assert.ok(out.notChecked.some(n => n.includes('a11y-1')), 'failed finder reported')
assert.ok(out.notChecked.some(n => n.includes('nginx.conf')), 'infra without shards reported as not checked')

// Pair mode: logic finders per stack, seam finder across repos, infra finder, project context and intent in prompts.
const e = (path, repo) => ({ path, rel: path.split('/').slice(1).join('/'), repo, base: 'b1', status: 'M', lines: 5 })
const prompts = {}
const calls2 = []
const agent2 = async (prompt, o) => {
  calls2.push(o)
  prompts[o.label] = prompt
  if (o.label === 'find:logic-nextjs-1') return { findings: [{ ...f('LOG-03', 'high', 7, 'react/src/a.ts'), area: 'logic' }], positives: [], not_checked: [] }
  if (o.label === 'verify:logic-nextjs-1') return { verdicts: [{ index: 0, outcome: 'confirmed', severity: 'medium', evidence: 'e' }] }
  if (o.label.startsWith('find:')) return { findings: [], positives: [], not_checked: [] }
  throw new Error('unexpected agent ' + o.label)
}
const args2 = { skillDir: dir, repoRoot: '/w', base: 'b1', baseLabel: 'drupal: develop + react: develop', notes: [],
  repos: [{ label: 'drupal', root: '/w/drupal', baseLabel: 'develop' }, { label: 'react', root: '/w/react', baseLabel: 'develop' }],
  only: ['a11y', 'cache', 'logic', 'performance', 'security'], deep: false, intent: '/w/tasks/K/spec.md', projectRefs: ['/w/drupal/.claude/secperf/project.md'],
  shards: { drupal: [[e("drupal/x';touch pwned;'.php", '/w/drupal')]], nextjs: [[e('react/src/a.ts', '/w/react')]], a11y: [], infra: [[e('drupal/azure-pipelines.yml', '/w/drupal')]] },
  seamFinder: true, decoupledRef: true, manifests: [], infra: ['drupal/azure-pipelines.yml'], versions: {}, audits: {}, skipped: [] }
const out2 = await run(args2, agent2, pipeline, () => {}, () => {})
assert.deepEqual(out2.finders.map(j => j.key), ['drupal-1', 'logic-drupal-1', 'nextjs-1', 'logic-nextjs-1', 'seam', 'infra-1'])
assert.equal(calls2.find(c => c.label === 'find:infra-1').model, 'sonnet')
assert.ok(prompts['find:logic-drupal-1'].includes('/w/tasks/K/spec.md'), 'logic finder gets the intent')
assert.ok(!prompts['find:drupal-1'].includes('/w/tasks/K/spec.md'), 'secperf finder does not get the intent')
assert.ok(prompts['find:seam'].includes('LOG-05'), 'seam finder checks the data contract when logic is in scope')
assert.ok(Object.values(prompts).every(p => p.includes('project.md')), 'every agent gets the project context')
assert.ok(prompts['find:nextjs-1'].includes("git -C '/w/react' diff 'b1' -- 'src/a.ts'"), 'per-repo diff command, quoted')
assert.ok(prompts['find:drupal-1'].includes("-- 'x'\\''"+";touch pwned;'\\''.php'"), 'a quote in a file name cannot end the quoting')
assert.ok(prompts['verify:logic-nextjs-1'].includes('For logic findings'), 'logic verifier rule')
assert.ok(prompts['find:drupal-1'].includes('checklist not read'), 'finder reports an unreadable checklist')
assert.ok(Object.values(prompts).every(p => p.includes('one file per call')), 'every agent loads references with Read')
assert.ok(!out2.notChecked.some(n => n.includes('infra files not reviewed')), 'infra reviewed by its finder')
assert.equal(out2.findings.length, 1)
assert.equal(out2.findings[0].severity, 'medium', 'verifier re-grade applied')

// Generic shards: one stack per shard, generic references plus logic, no decoupled ref, stack in prompt and output.
const prompts3 = {}
const agent3 = async (prompt, o) => {
  prompts3[o.label] = prompt
  if (o.label.startsWith('find:')) return { findings: [], positives: [], not_checked: [] }
  throw new Error('unexpected agent ' + o.label)
}
const g = (path, stack) => ({ path, rel: path, repo: '/l', base: 'b', status: 'M', lines: 5, stack })
const args3 = { skillDir: dir, repoRoot: '/l', base: 'b', baseLabel: 'main', notes: [], only: ['cache', 'logic', 'performance', 'security'],
  deep: false, shards: { drupal: [], nextjs: [], generic: [[g('app/Http/Controllers/PostController.php', 'laravel')], [g('svc/main.go', 'go')]], a11y: [], infra: [] },
  seamFinder: false, decoupledRef: true, manifests: [], infra: [], versions: {}, audits: {}, skipped: ['bin/deploy.sh'], unclassified: ['bin/deploy.sh'] }
const out3 = await run(args3, agent3, pipeline, () => {}, () => {})
assert.deepEqual(out3.finders.map(j => j.key), ['generic-1', 'logic-generic-1', 'generic-2', 'logic-generic-2'])
assert.deepEqual(out3.finders.map(j => j.stack), ['laravel', 'laravel', 'go', 'go'], 'stack label per shard')
assert.deepEqual(out3.finders[0].refs, ['generic-security', 'generic-perf-cache'], 'generic refs, no decoupled ref')
assert.ok(prompts3['find:generic-1'].includes('"laravel" row of the per-stack signals table'), 'finder told which table row to use')
assert.ok(prompts3['find:logic-generic-2'].includes('Stack: go.'), 'logic finder gets the stack label')
assert.ok(out3.notChecked.some(n => n.includes('bin/deploy.sh')), 'unclassified code reported as not checked')
assert.ok(!Object.values(prompts).some(p => p.includes('per-stack signals table')), 'drupal/next prompts unchanged')
console.log('selftest OK')
