// Splits audit findings into regression (branch only), pre-existing (both) and fixed (base only),
// minus visual.json "ignore", and builds one montage per page (rows = viewports, columns = base | branch).
// node scripts/visual-audit/compare.mjs <task>/visual [--branch=branch] [--base=base]
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const [dir, ...rest] = process.argv.slice(2);
const opt = Object.fromEntries(rest.map((a) => a.replace(/^--/, '').split('=')));
const branchTag = opt.branch || 'branch', baseTag = opt.base || 'base';
const read = (tag) => JSON.parse(readFileSync(join(dir, `${tag}.json`), 'utf8'));
const config = JSON.parse(readFileSync(join(dir, 'visual.json'), 'utf8'));
const branch = read(branchTag);
const base = existsSync(join(dir, `${baseTag}.json`)) ? read(baseTag) : null;

const ignored = (f) => (config.ignore || []).some((i) => (i.fingerprint && f.fingerprint === i.fingerprint) || (i.selector && f.selector === i.selector && (!i.kind || i.kind === f.kind)));
const flat = (run) => run.results.flatMap((r) => r.findings.map((f) => ({ ...f, page: r.page, vp: r.vp }))).filter((f) => !ignored(f));
const b = flat(branch), a = base ? flat(base) : [];
const inBase = new Set(a.map((f) => f.fingerprint)), inBranch = new Set(b.map((f) => f.fingerprint));
const diff = {
  meta: { branch: branch.meta, base: base?.meta || null },
  regression: b.filter((f) => !inBase.has(f.fingerprint)),
  preexisting: base ? b.filter((f) => inBase.has(f.fingerprint)) : [],
  fixed: a.filter((f) => !inBranch.has(f.fingerprint)),
};
if (!base) diff.note = 'no baseline: every finding is listed as regression until a base run classifies it';
writeFileSync(join(dir, 'diff.json'), JSON.stringify(diff, null, 1));

// Montages: cell = top of the page, 480 px wide, max 900 px tall. Skipped when ffmpeg is not installed.
const hasFfmpeg = !spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' }).error;
if (!hasFfmpeg) console.error('visual-audit: ffmpeg not found, montages skipped (diff.json is written)');
const montageDir = join(dir, 'montage');
if (hasFfmpeg) mkdirSync(montageDir, { recursive: true });
const CELL_W = 480, CELL_H = 900;
for (const page of hasFfmpeg ? [...new Set(branch.results.map((r) => r.page))] : []) {
  const vps = branch.results.filter((r) => r.page === page).map((r) => r.vp);
  const inputs = [], rows = [];
  for (const vp of vps) {
    const cols = [];
    for (const tag of base ? [baseTag, branchTag] : [branchTag]) {
      const file = join(dir, 'shots', tag, `${page}-${vp}.png`);
      if (!existsSync(file)) continue;
      inputs.push('-i', file);
      cols.push(inputs.length / 2 - 1);
    }
    if (cols.length) rows.push({ vp, cols });
  }
  // Three viewports per image keeps a montage readable when a reviewer opens it.
  for (let chunk = 0; chunk * 3 < rows.length; chunk++) {
  const part = rows.slice(chunk * 3, chunk * 3 + 3);
  const parts = [], rowLabels = [];
  part.forEach((row, ri) => {
    row.cols.forEach((idx, ci) => parts.push(`[${idx}]scale=${CELL_W}:-1,crop=${CELL_W}:'min(ih,${CELL_H})':0:0,pad=${CELL_W + 8}:${CELL_H}:4:0:0x222222[c${ri}_${ci}]`));
    const cells = row.cols.map((_, ci) => `[c${ri}_${ci}]`).join('');
    parts.push(row.cols.length > 1 ? `${cells}hstack=${row.cols.length}[r${ri}]` : `${cells}copy[r${ri}]`);
    rowLabels.push(`[r${ri}]`);
  });
  parts.push(rowLabels.length > 1 ? `${rowLabels.join('')}vstack=${rowLabels.length}[out]` : `${rowLabels[0]}copy[out]`);
  const out = join(montageDir, `${page}-${chunk + 1}.png`);
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', ...inputs, '-filter_complex', parts.join(';'), '-map', '[out]', '-frames:v', '1', out]);
  writeFileSync(join(montageDir, `${page}-${chunk + 1}.txt`), `rows (top to bottom): ${part.map((r) => r.vp).join(', ')}\ncolumns: ${base ? `${baseTag} | ${branchTag}` : branchTag}\n`);
  }
}
console.log(`regression ${diff.regression.length}, pre-existing ${diff.preexisting.length}, fixed ${diff.fixed.length}${base ? '' : ' (no baseline)'}`);
for (const f of diff.regression.slice(0, 15)) console.log(`  R ${f.page}@${f.vp} ${f.kind} ${f.selector} ${f.detail}`);
