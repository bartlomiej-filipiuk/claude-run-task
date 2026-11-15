export const meta = {
  name: 'secperf-review',
  description: 'Security/performance/cache/logic/WCAG review of branch changes: fresh-context finders per stack, refute-by-default verification, optional Fable judgment',
  phases: [
    { title: 'Find', detail: 'Opus stack, logic and seam finders; Sonnet WCAG and infra finders' },
    { title: 'Verify', detail: 'Opus refutes each critical/high/medium finding against the code', model: 'opus' },
    { title: 'Judge', detail: '--deep only: one batched Fable pass', model: 'fable' },
  ],
}

const A = args
const REF = f => `${A.skillDir}/references/${f}.md`
const wantSec = A.only.includes('security')
const wantPerf = A.only.includes('performance') || A.only.includes('cache')
const wantLogic = A.only.includes('logic')
const SEV = ['critical', 'high', 'medium', 'low']
const projectRefs = A.projectRefs || []
const shards = { infra: [], generic: [], ...A.shards }

const FINDING = {
  type: 'object',
  properties: {
    id: { type: 'string', description: 'reference item id (e.g. DSEC-02), or OTHER-<area> for an in-scope issue no item covers' },
    also: { type: 'array', items: { type: 'string' }, description: 'other item ids matching the same code' },
    area: { type: 'string', enum: ['security', 'performance', 'cache', 'logic', 'a11y'] },
    taxonomy: { type: 'string', description: 'OWASP / API / CWE / WCAG id from the item' },
    severity: { type: 'string', enum: SEV },
    file: { type: 'string', description: 'path exactly as given in the changed-files list' },
    line: { type: 'integer' },
    code: { type: 'string', description: 'the exact offending line(s), quoted from the file' },
    path: { type: 'string', description: 'one sentence: source to sink, or what varies the output, or what grows, or which input/state gives the wrong result' },
    why: { type: 'string' },
    fix: { type: 'string', description: 'concrete fix, short snippet if it helps' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  },
  required: ['id', 'area', 'severity', 'file', 'line', 'code', 'path', 'why', 'fix', 'confidence'],
}
const FINDER_OUT = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: FINDING },
    positives: { type: 'array', items: { type: 'string' }, description: 'controls you confirmed are in place on the changed code, one line each with file:line' },
    not_checked: { type: 'array', items: { type: 'string' }, description: 'what you could not check and why' },
  },
  required: ['findings', 'positives', 'not_checked'],
}
const VERIFY_OUT = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          index: { type: 'integer' },
          outcome: { type: 'string', enum: ['confirmed', 'refuted', 'unresolved'] },
          severity: { type: 'string', enum: SEV, description: 'severity after applying severity.md to what you read' },
          evidence: { type: 'string', description: 'quoted code with file:line that confirms or refutes; for unresolved, what is missing' },
        },
        required: ['index', 'outcome', 'severity', 'evidence'],
      },
    },
  },
  required: ['verdicts'],
}
const JUDGE_OUT = {
  type: 'object',
  properties: {
    rulings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          key: { type: 'string' },
          ruling: { type: 'string', enum: ['keep', 'downgrade', 'drop'] },
          severity: { type: 'string', enum: SEV },
          reason: { type: 'string' },
        },
        required: ['key', 'ruling', 'severity', 'reason'],
      },
    },
  },
  required: ['rulings'],
}

const statusText = s => s === 'U' ? 'new, untracked: read the whole file' : s === 'A' ? 'added' : s === 'D' ? 'deleted: read the diff only' : 'modified'
const patchText = p => p.endsWith('.patch') ? ' (a patch the build applies to contrib or core: review the code it adds)' : ''
const fileList = files => files.map(f => `- ${f.path} [${statusText(f.status)}]${patchText(f.path)} diff: git -C ${f.repo || A.repoRoot} diff ${f.base || A.base} -- ${f.rel || f.path}`).join('\n')
// zsh fails on `echo =====` separators (=word is a command lookup) and joined cat output gets truncated.
const READ_NOTE = 'Load each reference, project context and intent file with the Read tool, one file per call (page through a long file with offset/limit until you reach its end). Do not cat several files in one shell command.'

const repos = A.repos || [{ label: '.', root: A.repoRoot, baseLabel: A.baseLabel }]
const header = `Repositories: ${repos.map(r => `${r.label} = ${r.root} (base ${r.baseLabel}${r.branch ? `, branch ${r.branch}` : ''})`).join('; ')}
File paths below are relative to ${A.repoRoot}. Each file lists the exact command that shows its changes.
Versions (from lockfiles): ${JSON.stringify(A.versions)}
Dependency audit output: ${Object.keys(A.audits).length ? JSON.stringify(A.audits) : 'no lockfile changed'}
Areas in scope: ${A.only.join(', ')}`

const projectNote = projectRefs.length
  ? `\nProject context (read it first; it describes this project's topology and known traps, and it overrides generic assumptions): ${projectRefs.join(', ')}`
  : ''
const intentNote = A.intent
  ? `\nThe task's acceptance criteria / spec: ${A.intent}. Read it first. You get only the intent, not the implementer's reasoning, on purpose: judge the code by what it actually does.`
  : ''

const SCOPE = {
  secperf: 'security (OWASP Top 10 2025, OWASP API Security Top 10 2023), performance that degrades as data or traffic grows, and wrong or missing cache',
  logic: 'logic anomalies: code that produces a wrong result, wrong state or wrong data for a realistic input, or that does something different from its stated intent',
  infra: 'security and cache problems in CI pipelines, container images, web server and edge cache configuration, Terraform and edge function code (CloudFront Functions, Lambda@Edge)',
  a11y: 'light WCAG 2.2 AA accessibility',
  seam: 'the seam between Drupal and Next.js: security, performance, cache and the data contract between both sides',
}

const OUT_OF_SCOPE = {
  secperf: 'coding standards, style, naming, general logic bugs (a separate logic finder covers them), anything phpcs, phpstan, tsc or the repo\'s enabled eslint rules already block.',
  logic: 'security, performance, cache and accessibility (other finders cover them), coding standards, style, naming, refactoring ideas, missing tests on their own, anything phpcs, phpstan, tsc or eslint already block.',
  infra: 'application code (stack finders cover it), coding standards, style.',
  a11y: 'everything except accessibility of the changed markup.',
  seam: 'issues inside one side that do not cross the seam (the per-stack finders cover them), coding standards, style.',
}

const TRACE = {
  secperf: 'Before reporting a security finding, trace it: grep for the callers, the route/permission/config that reaches the code, and any access check, sanitizer or cache metadata added further up. Before reporting a performance finding, say what grows (rows, entities, requests) and at what scale it bites.',
  logic: 'Before reporting, trace it: which inputs and states reach the branch (callers, form values, config, translations, empty and missing data), and what the caller expects back. Name the concrete input or state that produces the wrong result in the "path" field. You may read tests next to the changed code to learn the intended behaviour; a test that asserts the behaviour you call wrong refutes your finding unless the intent says otherwise.',
  infra: 'Before reporting, say what the setting opens or leaks and where (image layer, pipeline log, public response, cache).',
  a11y: 'Before reporting, say which user cannot complete which task on the changed UI.',
  seam: 'Before reporting, show both sides: the Drupal code or config that produces the data or header, and the Next code that consumes it.',
}

const rules = kind => `How to work:
1. Read the reference files listed above in full, and ${A.skillDir}/references/severity.md. Consult ${A.skillDir}/references/versions.md only when an item depends on a version. ${READ_NOTE} If any of these files could not be read in full, add "checklist not read: <file>: <error>" to not_checked.
2. For each changed file, run its diff command and then read the whole file. The diff shows what changed; the file shows whether a control already exists.
3. ${TRACE[kind]}
4. Report a pattern only when the item's "Not a finding when" does not hold for the code you read. When several items match the same line, report the highest-severity one and list the others in "also".
5. Report only issues in or introduced by the changed code. Pre-existing issues in untouched code are out of scope unless the change makes them reachable.
6. Out of scope: ${OUT_OF_SCOPE[kind]}
7. Write findings defensively: which control or condition is missing and how to fix it. Do not write exploit payloads or attack steps.
8. Every finding must quote the exact code from the file, and "file" must be the path exactly as listed above. If you cannot quote it, do not report it.
9. An empty findings list is a valid, good result. Do not pad.
Do not modify any files.`

// Generic shards hold one stack each (prepare.py labels every file); the finder reads that stack's table row.
const stackOf = (group, files) => group === 'generic' ? [...new Set(files.map(f => f.stack || 'unknown'))].join(', ') : group
const stackNote = label => `Stack: ${label}. Apply the stack-neutral items, and use the "${label}" row of the per-stack signals table in each generic reference to recognise the framework's guards, sinks and caches (no row: use the closest language or framework you recognise in the code).`

function finderJobs() {
  const jobs = []
  for (const stack of ['drupal', 'nextjs', 'generic']) {
    const refs = []
    if (wantSec) refs.push(`${stack}-security`)
    if (wantPerf) refs.push(`${stack}-perf-cache`)
    if (A.decoupledRef && !A.seamFinder && stack !== 'generic') refs.push('decoupled')
    shards[stack].forEach((files, i) => {
      const label = stackOf(stack, files)
      const generic = stack === 'generic'
      if (refs.length) jobs.push({ key: `${stack}-${i + 1}`, kind: 'secperf', stack: label, files, refs, model: 'opus', effort: 'high', extra: generic ? stackNote(label) : undefined })
      if (wantLogic) jobs.push({ key: `logic-${stack}-${i + 1}`, kind: 'logic', stack: label, files, refs: ['logic'], model: 'opus', effort: 'high', intent: true, extra: generic ? `Stack: ${label}.` : undefined })
    })
  }
  if (A.seamFinder) {
    const files = [...shards.drupal.flat(), ...shards.nextjs.flat()]
    jobs.push({ key: 'seam', kind: 'seam', files, refs: ['decoupled', ...(wantLogic ? ['logic'] : [])], model: 'opus', effort: 'high', intent: wantLogic,
      extra: `Focus only on the seam between Drupal and Next.js: what Drupal exposes to the frontend, how Next fetches, caches and revalidates it, preview and webhook secrets.${wantLogic ? ' Also check the data contract: field names, null and empty shapes, arrays vs single values, language and URL formats that one side produces and the other side reads (LOG-05).' : ''} The per-stack finders cover the rest.` })
  }
  if (wantSec || wantPerf) {
    shards.infra.forEach((files, i) => jobs.push({ key: `infra-${i + 1}`, kind: 'infra', files, refs: ['infra'], model: 'sonnet', effort: 'medium',
      extra: 'Look only at CI pipelines, container images, web server and edge cache config, Terraform and edge function code. Think the problem through before you answer.' }))
  }
  if (A.only.includes('a11y')) {
    shards.a11y.forEach((files, i) => jobs.push({ key: `a11y-${i + 1}`, kind: 'a11y', files, refs: ['wcag'], model: 'sonnet', effort: 'medium',
      extra: 'Look only at the markup, templates, Form API elements and styles the change adds or modifies. Think the problem through before you answer.' }))
  }
  return jobs
}

const jobs = finderJobs()
const notChecked = []
if (A.infra.length && !jobs.some(j => j.kind === 'infra')) notChecked.push(`infra files not reviewed (security/performance/cache not in scope): ${A.infra.join(', ')}`)
if ((A.unclassified || []).length) notChecked.push(`code files outside every stack shard, not reviewed: ${A.unclassified.join(', ')}`)
log(`${jobs.length} finder(s): ${jobs.map(j => j.key).join(', ') || 'none'}`)

const results = await pipeline(
  jobs,
  job => agent(`You are reviewing code changes for ${SCOPE[job.kind]}. You have a fresh context on purpose: you did not write this code and you know nothing about how it was planned. A tech lead reads your output right after the coding work is done, so every false positive costs a developer's attention.

${header}

Reference files for this review (read them first): ${job.refs.map(REF).join(', ')}${projectNote}${job.intent ? intentNote : ''}
${job.extra || ''}

Changed files in your scope:
${fileList(job.files)}

${rules(job.kind)}`,
    { label: `find:${job.key}`, phase: 'Find', schema: FINDER_OUT, model: job.model, effort: job.effort })
    .then(out => {
      if (!out) notChecked.push(`finder ${job.key} returned nothing (error or refusal); its files were not reviewed for ${job.kind}`)
      return out
    }),
  (out, job) => {
    if (!out) return null
    const valid = out.findings.filter(f => f.code && f.code.trim() && f.file)
    const toVerify = valid.filter(f => f.severity !== 'low')
    const low = valid.filter(f => f.severity === 'low').map(f => ({ ...f, status: 'unverified', finder: job.key }))
    if (!toVerify.length) return { job, out, verified: [], low }
    const logicRule = job.kind === 'logic' || job.kind === 'seam'
      ? `\n- For logic findings: refuted means you found the guard, the caller constraint, the test or the stated intent that makes the behaviour correct or the input unreachable. Confirmed means you can name the input or state and show, from the code, the wrong result it produces.`
      : ''
    return agent(`You are checking findings from a code review of ${SCOPE[job.kind]}. Another reviewer produced them, and you have a fresh context: you know nothing about how the code was planned. Your default is to refute: a finding survives only if the code proves it.

${header}

Reference files: ${job.refs.map(REF).join(', ')}, and ${A.skillDir}/references/severity.md. Read the item for each finding id, especially its "Not a finding when" traps. ${READ_NOTE}${projectNote}${job.intent ? intentNote : ''}

For each finding, open the file and the surrounding code (callers, routing, permissions, config, parent render arrays, layout components, tests) and decide:
- refuted: you found the code that makes it a non-issue (an access check, a sanitizer, cache metadata further up, a trap condition). Quote it with file:line. "Probably fine" is not a refutation.
- confirmed: the code shows the problem is real and reachable. Quote the proof. Re-grade severity with severity.md.
- unresolved: the evidence needed is outside what you can read. Say what is missing.${logicRule}
Do not modify any files. Write defensively, no exploit steps.

Changed files (with the command that shows each diff):
${fileList(job.files)}

Findings (index is the position in this list):
${JSON.stringify(toVerify.map((f, index) => ({ index, ...f })))}`,
      { label: `verify:${job.key}`, phase: 'Verify', schema: VERIFY_OUT, model: 'opus', effort: A.deep ? 'high' : 'medium' })
      .then(v => {
        const byIndex = new Map((v?.verdicts || []).map(x => [x.index, x]))
        const verified = toVerify.map((f, i) => {
          const x = byIndex.get(i)
          if (!x) return { ...f, status: 'unverified', finder: job.key, evidence: 'verifier returned no verdict (error or refusal)' }
          return { ...f, status: x.outcome, severity: x.severity, evidence: x.evidence, finder: job.key }
        })
        return { job, out, verified, low }
      })
  },
)

const done = results.filter(Boolean)
const all = done.flatMap(r => [...r.verified, ...r.low])

// One finding per file:line across finders; keep the most severe, fold the rest into "also".
const rank = f => SEV.indexOf(f.severity)
const byLine = new Map()
for (const f of all.filter(f => f.status !== 'refuted').sort((a, b) => rank(a) - rank(b))) {
  const key = `${f.file}:${f.line}`
  const seen = byLine.get(key)
  if (seen) seen.also = [...new Set([...(seen.also || []), f.id, ...(f.also || [])])]
  else byLine.set(key, { ...f, key })
}
let kept = [...byLine.values()]

if (A.deep) {
  const serious = kept.filter(f => ['critical', 'high'].includes(f.severity))
  if (serious.length) {
    phase('Judge')
    const j = await agent(`You are the final judge for a code review of security, performance, cache, logic and accessibility findings. Each finding below was reported by one reviewer and checked by a second one against the code (status and evidence included). Rule on each: keep, downgrade (give the new severity), or drop. Drop only with a concrete reason from the evidence or the code. Open files under ${A.repoRoot} when the evidence is not enough. Grade with ${A.skillDir}/references/severity.md. Be direct and brief. Please remove all mannered prose. Do not modify files.

${header}${projectNote}${intentNote}

Findings:
${JSON.stringify(serious.map(f => ({ key: f.key, id: f.id, area: f.area, severity: f.severity, status: f.status, file: f.file, line: f.line, code: f.code, path: f.path, why: f.why, evidence: f.evidence })))}`,
      { label: 'judge:fable', phase: 'Judge', schema: JUDGE_OUT, model: 'fable', effort: 'medium' })
    if (!j) notChecked.push('Fable judgment did not return (error or refusal); critical/high findings are shown as verified by Opus only')
    const rulings = new Map((j?.rulings || []).map(r => [r.key, r]))
    kept = kept.flatMap(f => {
      const r = rulings.get(f.key)
      if (!r) return [f]
      if (r.ruling === 'drop') return []
      return [{ ...f, severity: r.severity, judge: r.reason }]
    })
  }
}

const order = f => rank(f) * 10 + ['confirmed', 'unverified', 'unresolved'].indexOf(f.status)
kept.sort((a, b) => order(a) - order(b))

return {
  base: A.baseLabel,
  repos,
  intent: A.intent || null,
  projectRefs,
  notes: A.notes,
  versions: A.versions,
  audits: A.audits,
  finders: jobs.map(j => ({ key: j.key, kind: j.kind, stack: j.stack, model: j.model, files: j.files.length, refs: j.refs })),
  findings: kept.filter(f => f.status !== 'unresolved' && f.severity !== 'low'),
  disputed: kept.filter(f => f.status === 'unresolved'),
  notes_low: kept.filter(f => f.status !== 'unresolved' && f.severity === 'low'),
  refuted: all.filter(f => f.status === 'refuted').map(f => ({ id: f.id, file: f.file, line: f.line, evidence: f.evidence })),
  positives: done.flatMap(r => r.out.positives),
  notChecked: [...notChecked, ...done.flatMap(r => r.out.not_checked)],
  skippedFiles: A.skipped.length,
  manifests: A.manifests,
  infra: A.infra,
}
