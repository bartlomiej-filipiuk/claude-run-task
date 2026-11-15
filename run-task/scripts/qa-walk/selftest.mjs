// Offline self-test of run.mjs: temp steps files with fake run() functions, no browser, no app stack.
//   node scripts/qa-walk/selftest.mjs
import { spawnSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const RUN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'run.mjs');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'qa-walk-selftest-'));
const marks = path.join(tmp, 'restored.log');
let passed = 0;
const failures = [];

function check(name, ok, detail = '') {
  if (ok) passed++;
  else failures.push(`${name}${detail ? `: ${detail}` : ''}`);
}

// A step whose run outcome is 'pass', 'fail' or 'throw' and whose restore appends its id to restored.log.
function step(id, outcome, extra = {}) {
  const body = outcome === 'throw' ? "throw new Error('boom here\\nsecond line')" : `return { pass: ${outcome === 'pass'}, observed: 'saw ${outcome}' }`;
  return `{ id: '${id}', ac: 'AC${id}', kind: '${extra.kind || 'proof'}', title: 'Title ${id}', cms: 'CMS text ${id}', site: 'Site text ${id}', `
    + `expect: '${extra.expect || 'Expect same'}', ${extra.noWithout ? '' : `withoutChange: 'pop-up ${id}', `}`
    + `run: async () => { ${body} }, restore: async () => { fs.appendFileSync(${JSON.stringify(marks)}, '${id}\\n'); } }`;
}

let n = 0;
function stepsFile(src) {
  const f = path.join(tmp, `steps${++n}.mjs`);
  fs.writeFileSync(f, `import * as fs from 'node:fs';\nexport const intro = 'Intro text';\nexport default ${src};\n`);
  return f;
}

function run(...args) {
  fs.rmSync(marks, { force: true });
  const r = spawnSync(process.execPath, [RUN, ...args], { encoding: 'utf-8', timeout: 30_000, env: { ...process.env, QA_WALK_LIB: '' } });
  const lines = r.stdout.trim().split('\n');
  const restored = fs.existsSync(marks) ? fs.readFileSync(marks, 'utf-8').trim().split('\n').filter(Boolean) : [];
  return { code: r.status, stdout: r.stdout, last: lines[lines.length - 1], restored };
}

const readOut = (f) => JSON.parse(fs.readFileSync(f, 'utf-8'));

// All pass.
let f = stepsFile(`[${step('S1', 'pass')}, ${step('S2', 'pass', { kind: 'regression', noWithout: true, expect: 'Looks normal' })}]`);
let r = run(f);
check('all pass: exit 0', r.code === 0, `exit ${r.code}`);
check('all pass: summary line', r.last === '{"pass":2,"fail":0,"error":0}', r.last);
check('all pass: restore after pass', r.restored.join() === 'S1,S2', r.restored.join());
let res = readOut(path.join(tmp, 'result.json'));
check('result file: default path and records', res.steps.length === 2 && res.summary.pass === 2);
const rec = res.steps[0];
check('result file: record fields', rec.id === 'S1' && rec.ac === 'ACS1' && rec.kind === 'proof' && rec.title === 'Title S1'
  && rec.result === 'pass' && rec.observed === 'saw pass' && typeof rec.ms === 'number', JSON.stringify(rec));

// One fail.
f = stepsFile(`[${step('S1', 'pass')}, ${step('S2', 'fail')}]`);
r = run(f, '--out', path.join(tmp, 'fail.json'));
check('one fail: exit 1', r.code === 1, `exit ${r.code}`);
check('one fail: restore after fail', r.restored.join() === 'S1,S2', r.restored.join());
res = readOut(path.join(tmp, 'fail.json'));
check('one fail: --out written, result fail', res.steps[1].result === 'fail' && res.summary.fail === 1);

// One throw: error with the first line only, beats a fail.
f = stepsFile(`[${step('S1', 'fail')}, ${step('S2', 'throw')}]`);
r = run(f, '--out', path.join(tmp, 'throw.json'));
check('one throw: exit 2', r.code === 2, `exit ${r.code}`);
check('one throw: restore after throw', r.restored.join() === 'S1,S2', r.restored.join());
res = readOut(path.join(tmp, 'throw.json'));
check('one throw: error, first line', res.steps[1].result === 'error' && res.steps[1].observed === 'boom here', JSON.stringify(res.steps[1]));
check('one throw: summary', JSON.stringify(res.summary) === '{"pass":0,"fail":1,"error":1}', JSON.stringify(res.summary));

// Restore that throws turns the step into an error.
f = stepsFile(`[{ id: 'S1', ac: '1', kind: 'proof', title: 't', cms: 'c', site: 's', expect: 'e', withoutChange: 'w', run: async () => ({ pass: true, observed: 'ok' }), restore: async () => { throw new Error('cannot restore'); } }]`);
r = run(f, '--out', path.join(tmp, 'restore.json'));
check('restore throws: exit 2 and error', r.code === 2 && readOut(path.join(tmp, 'restore.json')).steps[0].result === 'error', `exit ${r.code}`);

// Invalid files: each rule, nothing runs.
const valid = (over) => `{ id: 'S1', ac: '1', kind: 'proof', title: 't', cms: 'c', site: 's', expect: 'e', withoutChange: 'w', run: async () => { fs.appendFileSync(${JSON.stringify(marks)}, 'ran\\n'); return { pass: true, observed: '' }; }${over} }`;
const invalid = {
  'duplicate id': `[${valid('')}, ${valid('')}]`,
  'bad kind': `[${valid(", kind: 'other'")}]`,
  'empty cms': `[${valid(", cms: '  '")}]`,
  'missing expect': `[${valid(', expect: undefined')}]`,
  'proof without withoutChange': `[${valid(', withoutChange: undefined')}]`,
  'run not a function': `[${valid(", run: 'nope'")}]`,
  'empty array': '[]',
  'not an array': '{}',
};
for (const [name, src] of Object.entries(invalid)) {
  r = run(stepsFile(src));
  check(`invalid (${name}): exit 2, nothing ran`, r.code === 2 && r.restored.length === 0, `exit ${r.code}, ran ${r.restored.join()}`);
}
r = run(stepsFile(`[${valid(", kind: 'regression', withoutChange: undefined")}]`), '--out', path.join(tmp, 'reg.json'));
check('regression step needs no withoutChange', r.code === 0, `exit ${r.code}`);

// Filters.
f = stepsFile(`[${step('S1', 'pass')}, ${step('S2', 'fail', { kind: 'regression' })}, ${step('S3', 'pass')}]`);
r = run(f, '--only', 'proof', '--out', path.join(tmp, 'only.json'));
check('--only proof', r.code === 0 && r.restored.join() === 'S1,S3', `exit ${r.code}, ${r.restored.join()}`);
r = run(f, '--only', 'regression', '--out', path.join(tmp, 'only2.json'));
check('--only regression', r.code === 1 && r.restored.join() === 'S2', `exit ${r.code}, ${r.restored.join()}`);
r = run(f, '--step', 'S3,S1', '--out', path.join(tmp, 'step.json'));
check('--step', r.code === 0 && readOut(path.join(tmp, 'step.json')).steps.map((s) => s.id).join() === 'S1,S3', `exit ${r.code}`);
r = run(f, '--step', 'S9');
check('--step unknown id: exit 2', r.code === 2, `exit ${r.code}`);
r = run(f, '--only', 'regression', '--step', 'S1');
check('filters select nothing: exit 2', r.code === 2, `exit ${r.code}`);
r = run(f, '--only', 'other');
check('--only bad value: exit 2', r.code === 2, `exit ${r.code}`);

// --table: the four proof cases plus a regression step.
const rows = (list) => JSON.stringify({ steps: list.map(([id, kind, result]) => ({ id, ac: `AC${id}`, kind, title: `T${id}`, result, observed: '', ms: 0 })) });
const withF = path.join(tmp, 'with.json');
const withoutF = path.join(tmp, 'without.json');
fs.writeFileSync(withF, rows([['P1', 'proof', 'pass'], ['P2', 'proof', 'pass'], ['P3', 'proof', 'pass'], ['P4', 'proof', 'fail'], ['R1', 'regression', 'pass']]));
fs.writeFileSync(withoutF, rows([['P1', 'proof', 'fail'], ['P2', 'proof', 'pass'], ['P3', 'proof', 'error'], ['P4', 'proof', 'fail']]));
r = run('--table', withF, withoutF);
const row = (id) => r.stdout.split('\n').find((l) => l.startsWith(`| ${id} `)) || '';
check('--table header', r.stdout.startsWith('| step | AC | kind | with the change | without the change | proves |'));
check('--table proves yes', row('P1').endsWith('| yes |'), row('P1'));
check('--table passes without', row('P2').endsWith('| no: passes without the change |'), row('P2'));
check('--table error without', row('P3').endsWith('| no: error without the change |'), row('P3'));
check('--table fails with', row('P4').endsWith('| no: fails with the change |'), row('P4'));
check('--table regression n/a', row('R1').endsWith('| n/a |'), row('R1'));
check('--table: exit 1 when a proof does not prove', r.code === 1, `exit ${r.code}`);
fs.writeFileSync(withF, rows([['P1', 'proof', 'pass'], ['R1', 'regression', 'pass']]));
fs.writeFileSync(withoutF, rows([['P1', 'proof', 'fail']]));
r = run('--table', withF, withoutF);
check('--table: exit 0 when all prove', r.code === 0, `exit ${r.code}`);
fs.writeFileSync(withF, rows([['P1', 'proof', 'pass'], ['R1', 'regression', 'fail']]));
r = run('--table', withF, withoutF);
check('--table: exit 1 when a regression fails', r.code === 1, `exit ${r.code}`);

// Generic where/surface fields: valid on their own, printed like cms/site; a step with neither is invalid.
const generic = (over) => `{ id: 'G1', ac: '1', kind: 'proof', title: 't', where: 'Run the CLI', surface: 'stdout', expect: 'e', withoutChange: 'w', run: async () => ({ pass: true, observed: '' })${over} }`;
f = stepsFile(`[${generic('')}]`);
r = run('--print-qa', f);
check('where/surface: --print-qa', r.code === 0 && r.stdout.includes('1. Run the CLI → stdout') && r.stdout.includes('**Expected result**'), r.stdout);
r = run(stepsFile(`[${generic(', where: undefined')}]`), '--out', path.join(tmp, 'gen.json'));
check('where/surface: neither where nor cms is invalid', r.code === 2 && r.last.includes('where (or cms)'), r.last);

// --lib: the project's helpers reach ctx.lib; without --lib ctx.lib is null; a missing lib file is exit 2.
const libFile = path.join(tmp, 'helpers.mjs');
fs.writeFileSync(libFile, "export const answer = () => 42;\n");
const libStep = `[{ id: 'L1', ac: '1', kind: 'regression', title: 't', where: 'w', surface: 's', expect: 'e', run: async (ctx) => ({ pass: true, observed: String(ctx.lib && ctx.lib.answer()) }) }]`;
f = stepsFile(libStep);
r = run(f, '--lib', libFile, '--out', path.join(tmp, 'lib.json'));
check('--lib: helpers in ctx.lib', r.code === 0 && readOut(path.join(tmp, 'lib.json')).steps[0].observed === '42', `exit ${r.code}`);
r = run(f, '--out', path.join(tmp, 'nolib.json'));
check('no --lib: ctx.lib is null', r.code === 0 && readOut(path.join(tmp, 'nolib.json')).steps[0].observed === 'null', `exit ${r.code}`);
r = run(f, '--lib', path.join(tmp, 'missing.mjs'));
check('--lib missing file: exit 2', r.code === 2 && r.last.includes('cannot load lib'), r.last);

// --print-qa: every cms text, grouped expect, regression section; nothing runs.
f = stepsFile(`[${step('S1', 'pass')}, ${step('S2', 'pass')}, ${step('S3', 'pass', { expect: 'Other' })}, ${step('S4', 'pass', { kind: 'regression', expect: 'Looks normal' })}]`);
r = run('--print-qa', f);
check('--print-qa: exit 0, nothing ran', r.code === 0 && r.restored.length === 0, `exit ${r.code}`);
check('--print-qa: every cms text', ['S1', 'S2', 'S3', 'S4'].every((id) => r.stdout.includes(`CMS text ${id}`)), r.stdout);
check('--print-qa: numbered cms → site', r.stdout.includes('1. CMS text S1 → Site text S1'), r.stdout);
check('--print-qa: identical expect grouped', r.stdout.includes('- Steps 1, 2: Expect same') && r.stdout.includes('- Step 3: Other'), r.stdout);
check('--print-qa: regression section', /Looks the same as before[\s\S]*4\. CMS text S4 → Site text S4: Looks normal/.test(r.stdout), r.stdout);
check('--print-qa: intro', r.stdout.startsWith('Intro text'), r.stdout);

// notWalked: validation, --print-qa block, --print-conditions.
const nw = (over = '') => `{ ac: 'AC2', who: 'tester', where: 'dev, page X', expect: 'looks fine', why: 'not served locally'${over} }`;
const withNotWalked = (list) => {
  const file = stepsFile(`[${step('S1', 'pass')}, ${step('S2', 'pass', { kind: 'regression', expect: 'Looks normal' })}]`);
  fs.appendFileSync(file, `export const notWalked = ${list};\n`);
  return file;
};
for (const [name, list] of Object.entries({ 'missing field': `[${nw(', why: undefined')}]`, 'wrong who': `[${nw(", who: 'pm'")}]`, 'not an array': `${nw()}` })) {
  const file = withNotWalked(list);
  r = run(file, '--out', path.join(tmp, 'nw.json'));
  check(`notWalked invalid (${name}): run exit 2, nothing ran`, r.code === 2 && r.restored.length === 0, `exit ${r.code}`);
  check(`notWalked invalid (${name}): --print-qa exit 2`, run('--print-qa', file).code === 2);
  check(`notWalked invalid (${name}): --print-conditions exit 2`, run('--print-conditions', file).code === 2);
}
r = run(withNotWalked('[]'), '--out', path.join(tmp, 'nw-empty.json'));
check('notWalked empty: run exit 0', r.code === 0, `exit ${r.code}`);
f = withNotWalked(`[${nw(", where: 'dev, tester place', expect: 'tester sees'")}, ${nw(", who: 'owner', where: 'local, owner place', expect: 'owner sees', why: 'old dump'")}]`);
r = run('--print-qa', f);
check('--print-qa: tester block numbered after the regression steps',
  /Looks the same as before[\s\S]*2\. CMS text S2[\s\S]*\*\*Also check on dev\*\* \(we could not check these locally\)\n3\. dev, tester place: tester sees/.test(r.stdout), r.stdout);
check('--print-qa: owner entry absent', !r.stdout.includes('owner place'), r.stdout);
r = run('--print-qa', withNotWalked(`[${nw(", who: 'owner'")}]`));
check('--print-qa: no block with owner entries only', r.code === 0 && !r.stdout.includes('Also check on dev'), r.stdout);
r = run('--print-conditions', f);
check('--print-conditions: table with tester and owner', r.code === 0
  && r.stdout.startsWith('| what | who | where | what they should see | why not walked |')
  && r.stdout.includes('| AC2 | tester | dev, tester place | tester sees | not served locally |')
  && r.stdout.includes('| AC2 | owner | local, owner place | owner sees | old dump |'), r.stdout);
r = run('--print-conditions', stepsFile(`[${step('S1', 'pass')}]`));
check('--print-conditions: none', r.code === 0 && r.stdout.trim() === 'No conditions from the walk.', r.stdout);
check('--print-conditions: nothing ran', r.restored.length === 0);

fs.rmSync(tmp, { recursive: true, force: true });
const total = passed + failures.length;
for (const x of failures) console.log(`FAIL ${x}`);
console.log(`${passed}/${total}`);
process.exit(failures.length ? 1 : 0);
