// Visual audit: loads pages at a viewport matrix and measures layout faults per container
// (each direct child of <main>, plus <header> and <footer>). Writes <out>/<tag>.json and
// <out>/shots/<tag>/<page>-<w>x<h>.png. See README.md.
//
// node scripts/visual-audit/audit.mjs --url=http://localhost:3000 --tag=branch \
//   --config=<task>/visual/visual.json --out=<task>/visual [--vp=375x812,1280x800] [--pages=id,id] [--sha=abc123]
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';

// Playwright from the project in the current directory, or VISUAL_AUDIT_PLAYWRIGHT (module name or path).
const requireFromCwd = createRequire(join(process.cwd(), 'noop.js'));
let chromium;
for (const name of process.env.VISUAL_AUDIT_PLAYWRIGHT ? [process.env.VISUAL_AUDIT_PLAYWRIGHT] : ['playwright', '@playwright/test']) {
  try { ({ chromium } = requireFromCwd(name)); break; } catch (e) { if (e.code !== 'MODULE_NOT_FOUND') throw e; }
}
if (!chromium) {
  console.error(`visual-audit: playwright not found from ${process.cwd()}; run it from a project with 'playwright' or '@playwright/test' installed, or set VISUAL_AUDIT_PLAYWRIGHT to the module path`);
  process.exit(2);
}

const args = Object.fromEntries(process.argv.slice(2).map((a) => a.replace(/^--/, '').split(/=(.*)/s).slice(0, 2)));
for (const k of ['url', 'tag', 'config', 'out']) if (!args[k]) throw new Error(`missing --${k}`);
const config = JSON.parse(readFileSync(args.config, 'utf8'));
const DEFAULT_VP = '375x812,768x1024,1024x1366,1280x800,1440x900,1920x1080';
const viewports = (args.vp || config.viewports?.join(',') || DEFAULT_VP).split(',').map((v) => v.split('x').map(Number));
const only = args.pages?.split(',');
const pages = config.pages.filter((p) => !only || only.includes(p.id));
const shotsDir = join(args.out, 'shots', args.tag);
mkdirSync(shotsDir, { recursive: true });

// Optional visual.json keys: URL globs to abort (consent banners, captchas, tag managers) and cookies set for --url.
const BLOCKED = config.blockUrls || [];
const COOKIES = config.cookies || [];

// Runs in the page. Returns findings with a structural selector (tag:nth-of-type path from the
// container), because styled-components class hashes change whenever a component file changes.
function measure() {
  const vw = innerWidth;
  const findings = [];
  const path = (el, root) => {
    const parts = [];
    for (let e = el; e && e !== root; e = e.parentElement) {
      const sib = [...(e.parentElement?.children || [])].filter((s) => s.tagName === e.tagName);
      parts.unshift(`${e.tagName.toLowerCase()}${sib.length > 1 ? `:${sib.indexOf(e) + 1}` : ''}`);
    }
    return parts.join('>') || el.tagName.toLowerCase();
  };
  const desc = (el) => `<${el.tagName.toLowerCase()} class="${String(el.className?.baseVal ?? el.className).slice(0, 50)}">`;
  const visible = (el) => el.checkVisibility?.({ opacityProperty: true, visibilityProperty: true }) ?? true;
  const add = (kind, ci, el, root, detail) => findings.push({ kind, container: ci, selector: el ? path(el, root) : '', detail });

  const docW = document.documentElement.scrollWidth;
  if (docW > vw + 1) add('page-overflow-x', -1, null, null, `${docW} > ${vw}`);

  const main = document.querySelector('main');
  // Sections: unwrap single-child wrappers and stacks of full-width blocks (page wrappers, spacing
  // wrappers) up to six levels, so a container is a real section, not the whole page.
  // Ignore 1 px skip-link targets; a stack is static/relative blocks placed one under another
  // (absolute children are layers of one section, e.g. a hero's media and text).
  const kids = (el) => [...el.children].filter((k) => { const r = k.getBoundingClientRect(); return visible(k) && r.height > 1 && r.width > 1; });
  const isStack = (k, w) => k.length > 1 && k.every((c, i) => {
    const r = c.getBoundingClientRect();
    return r.width >= w * 0.9 && !/absolute|fixed/.test(getComputedStyle(c).position) && (i === 0 || r.top >= k[i - 1].getBoundingClientRect().bottom - 1);
  });
  let sections = main ? [main] : [];
  for (let depth = 0; depth < 6; depth++) {
    sections = sections.flatMap((s) => {
      const k = kids(s), w = s.getBoundingClientRect().width;
      return (k.length === 1 && !/absolute|fixed/.test(getComputedStyle(k[0]).position)) || isStack(k, w) ? k : [s];
    });
  }
  const containers = [document.querySelector('header'), ...sections, document.querySelector('footer')]
    .filter((c, i, a) => c && a.indexOf(c) === i && visible(c) && c.getBoundingClientRect().height > 0);
  const header = document.querySelector('header');
  const headerBottom = header ? header.getBoundingClientRect().bottom : 0;

  containers.forEach((c, ci) => {
    const cr = c.getBoundingClientRect();
    for (const el of c.querySelectorAll('*')) {
      if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
      if (!visible(el)) continue;
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed') continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      // Anything inside a clipping box within the container is clipped on purpose (object-fit, sliders).
      let clipped = false;
      for (let a = el.parentElement; a && a !== c.parentElement; a = a.parentElement) {
        const o = getComputedStyle(a);
        if (/(hidden|clip)/.test(o.overflow + o.overflowX + o.overflowY)) { clipped = true; break; }
        if (a === c) break;
      }
      if (!clipped) {
        const h = r.right > cr.right + 1 || r.left < cr.left - 1 || r.right > vw + 1;
        const v = r.top < cr.top - 1 || r.bottom > cr.bottom + 1;
        if (h || v) add(h ? 'outside-container-x' : 'outside-container-y', ci, el, c, `${desc(el)} ${Math.round(r.left)},${Math.round(r.top)}..${Math.round(r.right)},${Math.round(r.bottom)} vs ${Math.round(cr.left)},${Math.round(cr.top)}..${Math.round(cr.right)},${Math.round(cr.bottom)}`);
      }
      // Only text that is actually cut off; visible overflow is caught by the container check.
      if (/^(H[1-6]|P|A|BUTTON|LI)$/.test(el.tagName) && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1 && cs.overflowX !== 'visible') {
        add('text-clipped', ci, el, c, `${desc(el)} ${el.scrollWidth} > ${el.clientWidth}`);
      }
    }
    // Text and controls must be on top where they are drawn.
    for (const el of c.querySelectorAll('h1, h2, h3, a, button')) {
      if (!visible(el)) continue;
      const r0 = el.getBoundingClientRect();
      if (!r0.width || !r0.height || el.closest('[aria-hidden="true"]')) continue;
      el.scrollIntoView({ block: 'center', behavior: 'instant' });
      const r = el.getBoundingClientRect();
      const x = r.left + Math.min(r.width / 2, 40), y = r.top + r.height / 2;
      if (x < 0 || x > vw || y < 0 || y > innerHeight) continue;
      const top = document.elementFromPoint(x, y);
      if (top && !el.contains(top) && !top.contains(el) && !top.closest('header') ) {
        const ts = getComputedStyle(top);
        add('covered', ci, el, c, `${desc(el)} under ${desc(top)} bg=${ts.backgroundColor} opacity=${ts.opacity}`);
      }
    }
    window.scrollTo(0, 0);
  });

  // Consecutive sections must not overlap.
  const blocks = sections.filter((b) => getComputedStyle(b).position !== 'absolute');
  for (let i = 1; i < blocks.length; i++) {
    const a = blocks[i - 1].getBoundingClientRect(), b = blocks[i].getBoundingClientRect();
    if (a.bottom > b.top + 1) findings.push({ kind: 'sections-overlap', container: containers.indexOf(blocks[i]), selector: path(blocks[i], main), detail: `${Math.round(a.bottom - b.top)} px` });
  }
  // The first heading in <main> must not start under the site header.
  const h = main && [...main.querySelectorAll('h1, h2')].find((x) => visible(x) && x.getBoundingClientRect().height > 0);
  if (h && header && h.getBoundingClientRect().top < headerBottom - 1) {
    findings.push({ kind: 'heading-under-header', container: containers.findIndex((c) => c.contains(h)), selector: path(h, main), detail: `heading top ${Math.round(h.getBoundingClientRect().top)} < header bottom ${Math.round(headerBottom)}` });
  }
  return findings;
}

const browser = await chromium.launch();
const results = [];
for (const p of pages) {
  for (const [w, hgt] of viewports) {
    const ctx = await browser.newContext({ viewport: { width: w, height: hgt }, isMobile: w < 768, hasTouch: w <= 1024, reducedMotion: 'reduce', serviceWorkers: 'block', ignoreHTTPSErrors: true });
    if (COOKIES.length) await ctx.addCookies(COOKIES.map((c) => ({ url: args.url, ...c })));
    for (const b of BLOCKED) await ctx.route(b, (r) => r.abort());
    const page = await ctx.newPage();
    let findings = [];
    try {
      await page.goto(args.url + p.path, { waitUntil: 'load', timeout: 90000 });
      await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
      await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}' });
      await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += innerHeight) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 100)); } scrollTo(0, 0); });
      await page.waitForTimeout(3500);
      findings = await page.evaluate(measure);
      const full = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.screenshot({ path: join(shotsDir, `${p.id}-${w}x${hgt}.png`), fullPage: true, clip: full > 6000 ? { x: 0, y: 0, width: w, height: 6000 } : undefined, animations: 'disabled' });
    } catch (e) {
      findings = [{ kind: 'load-error', container: -1, selector: '', detail: String(e.message).split('\n')[0] }];
    }
    for (const f of findings) f.fingerprint = `${f.kind}|${p.id}|${w}x${hgt}|${f.container}|${f.selector}`;
    results.push({ page: p.id, path: p.path, vp: `${w}x${hgt}`, findings });
    console.log(`${args.tag} ${p.id} ${w}x${hgt}: ${findings.length} finding(s)${findings.length ? '\n  ' + findings.slice(0, 5).map((f) => `${f.kind} ${f.selector} ${f.detail}`).join('\n  ') : ''}`);
    await ctx.close();
  }
}
await browser.close();
writeFileSync(join(args.out, `${args.tag}.json`), JSON.stringify({ meta: { url: args.url, tag: args.tag, sha: args.sha || null, viewports: viewports.map((v) => v.join('x')), at: new Date().toISOString() }, results }, null, 1));
