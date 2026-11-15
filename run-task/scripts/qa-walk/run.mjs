// QA walk runner. See README.md.
//   node scripts/qa-walk/run.mjs <steps.mjs> [--lib <helpers.mjs>] [--only proof|regression] [--step S1,S2] [--out <file>]
//   node scripts/qa-walk/run.mjs --table <with.json> <without.json>
//   node scripts/qa-walk/run.mjs --print-qa <steps.mjs>
//   node scripts/qa-walk/run.mjs --print-conditions <steps.mjs>
import * as fs from 'node:fs';
import { createRequire } from 'node:module';
import * as path from 'node:path';
import { pathToFileURL } from 'node:url';

const KINDS = ['proof', 'regression'];
const TEXT_FIELDS = ['id', 'ac', 'title', 'expect'];
// Generic field, then the older name still accepted: where = where the tester acts, surface = where the result shows.
const ALIASED_FIELDS = [['where', 'cms'], ['surface', 'site']];
const field = (s, [name, alias]) => (s[name] !== undefined ? s[name] : s[alias]);

function validate(steps) {
  const errors = [];
  if (!Array.isArray(steps) || !steps.length) return ['the default export must be a non-empty array of steps'];
  const seen = new Set();
  steps.forEach((s, i) => {
    const where = `step ${i + 1}${s && typeof s.id === 'string' ? ` (${s.id})` : ''}`;
    if (!s || typeof s !== 'object') { errors.push(`${where}: not an object`); return; }
    for (const f of TEXT_FIELDS) if (typeof s[f] !== 'string' || !s[f].trim()) errors.push(`${where}: ${f} must be a non-empty string`);
    for (const pair of ALIASED_FIELDS) {
      const v = field(s, pair);
      if (typeof v !== 'string' || !v.trim()) errors.push(`${where}: ${pair[0]} (or ${pair[1]}) must be a non-empty string`);
    }
    if (typeof s.id === 'string') { if (seen.has(s.id)) errors.push(`${where}: duplicate id`); seen.add(s.id); }
    if (!KINDS.includes(s.kind)) errors.push(`${where}: kind must be proof or regression`);
    if (s.kind === 'proof' && (typeof s.withoutChange !== 'string' || !s.withoutChange.trim())) errors.push(`${where}: a proof step needs withoutChange`);
    if (typeof s.run !== 'function') errors.push(`${where}: run must be a function`);
    if (s.restore !== undefined && typeof s.restore !== 'function') errors.push(`${where}: restore must be a function when given`);
  });
  return errors;
}

const WHO = ['tester', 'owner'];
const NOT_WALKED_FIELDS = ['ac', 'who', 'where', 'expect', 'why'];

// Checks we could not do locally: printed for the tester or listed for the owner, never run.
function validateNotWalked(list) {
  if (list === undefined) return [];
  if (!Array.isArray(list)) return ['notWalked must be an array'];
  const errors = [];
  list.forEach((n, i) => {
    const where = `notWalked ${i + 1}`;
    if (!n || typeof n !== 'object') { errors.push(`${where}: not an object`); return; }
    for (const f of NOT_WALKED_FIELDS) if (typeof n[f] !== 'string' || !n[f].trim()) errors.push(`${where}: ${f} must be a non-empty string`);
    if (typeof n.who === 'string' && n.who.trim() && !WHO.includes(n.who)) errors.push(`${where}: who must be tester or owner`);
  });
  return errors;
}

async function load(file) {
  const mod = await import(pathToFileURL(path.resolve(file)).href);
  return { steps: mod.default, intro: mod.intro, notWalked: mod.notWalked };
}

const validateFile = ({ steps, notWalked }) => [...validate(steps), ...validateNotWalked(notWalked)];

function parseArgs(argv) {
  const a = { positional: [] };
  for (let i = 0; i < argv.length; i++) {
    const v = argv[i];
    if (v === '--only' || v === '--step' || v === '--out' || v === '--lib') a[v.slice(2)] = argv[++i];
    else if (v === '--table' || v === '--print-qa' || v === '--print-conditions') a.mode = v.slice(2);
    else a.positional.push(v);
  }
  return a;
}

const summaryLine = (summary, extra = {}) => console.log(JSON.stringify({ ...summary, ...extra }));
const firstLine = (e) => String(e && e.message ? e.message : e).split('\n')[0];

// The project's helper library (--lib or QA_WALK_LIB, resolved against the cwd); none = ctx.lib is null.
async function loadLib(args) {
  const file = args.lib || process.env.QA_WALK_LIB;
  return file ? import(pathToFileURL(path.resolve(file)).href) : null;
}

// Chromium from the lib when it exports chromium(), else Playwright resolved from the cwd.
function chromium(lib) {
  if (lib && typeof lib.chromium === 'function') return lib.chromium();
  const req = createRequire(path.join(process.cwd(), 'noop.js'));
  for (const name of ['playwright', '@playwright/test']) {
    try { return req(name).chromium; } catch (e) { if (e.code !== 'MODULE_NOT_FOUND') throw e; }
  }
  throw new Error(`browser(): no lib exporting chromium() and no playwright installed under ${process.cwd()}`);
}

async function run(args) {
  const file = args.positional[0];
  const fail = (msg) => { console.error(`qa-walk: ${msg}`); summaryLine({ pass: 0, fail: 0, error: 0 }, { invalid: msg }); return 2; };
  if (!file) return fail('usage: run.mjs <steps.mjs> [--lib <helpers.mjs>] [--only proof|regression] [--step S1,S2] [--out <file>]');
  let loaded;
  try { loaded = await load(file); } catch (e) { return fail(`cannot load ${file}: ${firstLine(e)}`); }
  const { steps } = loaded;
  const errors = validateFile(loaded);
  if (errors.length) return fail(errors.join('; '));
  if (args.only !== undefined && !KINDS.includes(args.only)) return fail('--only must be proof or regression');
  let selected = steps.filter((s) => !args.only || s.kind === args.only);
  if (args.step !== undefined) {
    const ids = args.step.split(',').map((x) => x.trim()).filter(Boolean);
    const unknown = ids.filter((id) => !steps.some((s) => s.id === id));
    if (!ids.length || unknown.length) return fail(`--step: unknown id(s) ${unknown.join(',') || '(none given)'}`);
    selected = selected.filter((s) => ids.includes(s.id));
  }
  if (!selected.length) return fail('no step selected');
  let lib;
  try { lib = await loadLib(args); } catch (e) { return fail(`cannot load lib ${args.lib || process.env.QA_WALK_LIB}: ${firstLine(e)}`); }

  const out = path.resolve(args.out || path.join(path.dirname(path.resolve(file)), 'result.json'));
  const outDir = path.join(path.dirname(out), path.basename(out, '.json'));
  let browserPromise = null;
  const ctx = {
    lib,
    outDir,
    browser: () => (browserPromise ??= chromium(lib).launch()),
    shot: async (page, name, options = {}) => {
      fs.mkdirSync(outDir, { recursive: true });
      await page.screenshot({ path: path.join(outDir, `${name}.png`), ...options });
    },
  };

  // A signal (revert-check stops a run with SIGTERM) must not leave a step's changes behind.
  let current = null;
  let restoring = false;
  let stopAfterRestore = false;
  const onSignal = (sig) => {
    if (restoring) { stopAfterRestore = true; return; }
    const step = current;
    current = null;
    console.error(`qa-walk: ${sig}, restoring ${step ? step.id : 'nothing'}`);
    Promise.resolve(step && step.restore ? step.restore(ctx) : null)
      .catch((e) => console.error(`qa-walk: restore of ${step.id} failed: ${firstLine(e)}`))
      .finally(() => process.exit(2));
  };
  process.on('SIGINT', onSignal);
  process.on('SIGTERM', onSignal);

  const records = [];
  for (const step of selected) {
    const started = Date.now();
    const rec = { id: step.id, ac: step.ac, kind: step.kind, title: step.title, result: 'error', observed: '', ms: 0 };
    console.error(`qa-walk: ${step.id} ${step.title}`);
    current = step;
    try {
      const r = await step.run(ctx);
      if (!r || typeof r.pass !== 'boolean' || typeof r.observed !== 'string') throw new Error('run() must return { pass: boolean, observed: string }');
      rec.result = r.pass ? 'pass' : 'fail';
      rec.observed = r.observed;
    } catch (e) {
      rec.result = 'error';
      rec.observed = firstLine(e);
    }
    if (current === step) {
      current = null;
      if (step.restore) {
        restoring = true;
        try { await step.restore(ctx); } catch (e) {
          // State left behind outweighs whatever the step saw.
          rec.result = 'error';
          rec.observed = `restore failed: ${firstLine(e)}; run: ${rec.observed}`;
        }
        restoring = false;
        if (stopAfterRestore) { console.error(`qa-walk: stopped by a signal after restoring ${step.id}`); process.exit(2); }
      }
    } else {
      // A signal arrived during run() and the handler restores and exits.
      await new Promise(() => {});
    }
    rec.ms = Date.now() - started;
    records.push(rec);
    console.error(`qa-walk: ${step.id} ${rec.result}: ${rec.observed}`);
  }
  if (browserPromise) await (await browserPromise).close().catch(() => {});

  const summary = { pass: 0, fail: 0, error: 0 };
  for (const r of records) summary[r.result]++;
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, `${JSON.stringify({ steps: records, summary }, null, 2)}\n`);
  summaryLine(summary);
  return summary.error ? 2 : summary.fail ? 1 : 0;
}

function verdict(kind, w, wo) {
  if (kind === 'regression') return 'n/a';
  if (!w || w.result !== 'pass') return 'no: fails with the change';
  if (!wo) return 'no: not run without the change';
  if (wo.result === 'pass') return 'no: passes without the change';
  if (wo.result === 'error') return 'no: error without the change';
  return 'yes';
}

function table(args) {
  const [withFile, withoutFile] = args.positional;
  if (!withFile || !withoutFile) { console.error('usage: run.mjs --table <with.json> <without.json>'); return 2; }
  const read = (f) => new Map(JSON.parse(fs.readFileSync(f, 'utf-8')).steps.map((s) => [s.id, s]));
  const w = read(withFile);
  const wo = read(withoutFile);
  const ids = [...w.keys(), ...[...wo.keys()].filter((id) => !w.has(id))];
  const cell = (s) => (s ? s.result : 'not run');
  const esc = (t) => String(t).replace(/\|/g, '\\|');
  let ok = true;
  const lines = ['| step | AC | kind | with the change | without the change | proves |', '|---|---|---|---|---|---|'];
  for (const id of ids) {
    const a = w.get(id);
    const b = wo.get(id);
    const meta = a || b;
    const v = verdict(meta.kind, a, b);
    if (meta.kind === 'proof' ? v !== 'yes' : !a || a.result !== 'pass') ok = false;
    lines.push(`| ${esc(id)} ${esc(meta.title)} | ${esc(meta.ac)} | ${meta.kind} | ${cell(a)} | ${cell(b)} | ${v} |`);
  }
  console.log(lines.join('\n'));
  return ok ? 0 : 1;
}

async function printQa(args) {
  const file = args.positional[0];
  if (!file) { console.error('usage: run.mjs --print-qa <steps.mjs>'); return 2; }
  const loaded = await load(file);
  const { steps, intro } = loaded;
  const errors = validateFile(loaded);
  if (errors.length) { console.error(`qa-walk: ${errors.join('; ')}`); return 2; }
  const proof = steps.filter((s) => s.kind === 'proof');
  const regression = steps.filter((s) => s.kind === 'regression');
  const out = [];
  if (intro) out.push(intro.trim(), '');
  out.push('**Where to do it → where to look**');
  const [whereOf, surfaceOf] = ALIASED_FIELDS.map((pair) => (s) => field(s, pair));
  proof.forEach((s, i) => out.push(`${i + 1}. ${whereOf(s)} → ${surfaceOf(s)}`));
  out.push('', '**Expected result**');
  const groups = new Map();
  proof.forEach((s, i) => { if (!groups.has(s.expect)) groups.set(s.expect, []); groups.get(s.expect).push(i + 1); });
  for (const [expect, nums] of groups) out.push(`- ${nums.length === proof.length ? 'Every step above' : `Step${nums.length > 1 ? 's' : ''} ${nums.join(', ')}`}: ${expect}`);
  if (regression.length) {
    out.push('', '**Looks the same as before** (nothing to paste)');
    regression.forEach((s, i) => out.push(`${proof.length + i + 1}. ${whereOf(s)} → ${surfaceOf(s)}: ${s.expect}`));
  }
  const tester = (loaded.notWalked || []).filter((n) => n.who === 'tester');
  if (tester.length) {
    out.push('', '**Also check on dev** (we could not check these locally)');
    tester.forEach((n, i) => out.push(`${steps.length + i + 1}. ${n.where}: ${n.expect}`));
  }
  console.log(out.join('\n'));
  return 0;
}

async function printConditions(args) {
  const file = args.positional[0];
  if (!file) { console.error('usage: run.mjs --print-conditions <steps.mjs>'); return 2; }
  const loaded = await load(file);
  const errors = validateFile(loaded);
  if (errors.length) { console.error(`qa-walk: ${errors.join('; ')}`); return 2; }
  const list = loaded.notWalked || [];
  if (!list.length) { console.log('No conditions from the walk.'); return 0; }
  const esc = (t) => String(t).replace(/\|/g, '\\|');
  const lines = ['| what | who | where | what they should see | why not walked |', '|---|---|---|---|---|'];
  for (const n of list) lines.push(`| ${esc(n.ac)} | ${n.who} | ${esc(n.where)} | ${esc(n.expect)} | ${esc(n.why)} |`);
  console.log(lines.join('\n'));
  return 0;
}

const args = parseArgs(process.argv.slice(2));
const modes = { table, 'print-qa': printQa, 'print-conditions': printConditions };
const code = await (modes[args.mode] || run)(args);
process.exit(code);
