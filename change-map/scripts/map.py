#!/usr/bin/env python3
"""Build a reviewer's map of a change: entry points, how the changed files connect, and the
Drupal <-> Next seam, as Markdown with a Mermaid graph. Deterministic, no model.

Scope (base, --pair, wrong-base guard, exclusions) comes from secperf-review's prepare.collect().
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.expanduser('~/.claude/skills/secperf-review/scripts'))
import prepare  # noqa: E402

MAX_NODES = 45
TEST_FILE = re.compile(r'(^|/)(tests?|__tests__|e2e)/|\.(test|spec)\.[jt]sx?$|Test\.php$')
DOC_FILE = re.compile(r'\.(md|txt)$')
FUNC = re.compile(r'\bfunction\s+(\w+)\s*\(|^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>|'
                  r'^\s*(?:(?:public|protected|private|static|async|readonly)\s+)*(\w+)\s*\([^)]*\)\s*(?::\s*[^{;]+)?\{\s*$')
CONFIG_NOISE = re.compile(r'^\s*(uuid|_core|default_config_hash|langcode|dependencies|module|config|content|status):|^\s*-\s*[a-z_]+\.[a-z_.]+$')
NOT_FUNC = {'if', 'for', 'foreach', 'while', 'switch', 'catch', 'function', 'return', 'array', 'list'}
HEADER = re.compile(r'[\'"`](x-[a-z0-9-]{3,})[\'"`]', re.I)
REGISTRY = re.compile(r'registry\.set\("([^"]+)",\s*dynamic\(\(\)\s*=>\s*import\("\./([^"]+)"\)')
BUNDLE_CONFIG = re.compile(r'(?:node\.type|paragraphs\.paragraphs_type|field\.field\.(?:node|paragraph)|'
                           r'core\.entity_view_display\.(?:node|paragraph)|core\.entity_form_display\.(?:node|paragraph))\.([a-z0-9_]+)')


def git(repo, *a):
    return subprocess.run(['git', '-C', repo, *a], capture_output=True, text=True).stdout


def read(repo, rel, base=None):
    if base:
        return git(repo, 'show', f'{base}:{rel}')
    try:
        return open(os.path.join(repo, rel), errors='ignore').read()
    except OSError:
        return ''


def group_of(rel):
    p = rel.split('/')
    m = re.match(r'(?:docroot/|web/)?modules/custom/([^/]+)', rel)
    if m:
        return f'module {m.group(1)}'
    m = re.match(r'(?:docroot/|web/)?themes/custom/([^/]+)', rel)
    if m:
        return f'theme {m.group(1)}'
    if rel.startswith('config/'):
        return 'config' if p[1] in ('default', 'sync') else f'config {p[2] if len(p) > 3 else p[1]}'
    m = re.match(r'src/themes/[^/]+/templates/(components|layout)/([^/.]+)', rel)
    if m:
        return f'{"component" if m.group(1) == "components" else "layout"} {m.group(2)}'
    m = re.match(r'utils/packages/([^/]+)', rel)
    if m:
        return f'@ffw/{m.group(1)}'
    if rel.startswith('src/pages/api/'):
        return 'API routes'
    if rel.startswith('src/pages/'):
        return 'pages'
    if rel.startswith('src/') and len(p) > 2:
        return f'src/{p[1]}'
    if TEST_FILE.search(rel):
        return 'tests'
    return p[0] if len(p) > 1 else 'root'


def hunk_starts(diff):
    """New-file line of the first changed line in each hunk (old-file line for pure deletions)."""
    out, new, old, pending = [], 0, 0, False
    for line in diff.splitlines():
        m = re.match(r'@@ -(\d+)(?:,\d+)? \+(\d+)', line)
        if m:
            old, new, pending = int(m.group(1)), int(m.group(2)), True
            continue
        if not pending:
            continue
        if line.startswith('+') and not line.startswith('+++'):
            out.append(('new', new))
            pending = False
        elif line.startswith('-') and not line.startswith('---'):
            out.append(('old', old))
            pending = False
        else:
            new += 1
            old += 1
    return out


def enclosing(lines, at):
    for i in range(min(at, len(lines)) - 1, -1, -1):
        m = FUNC.search(lines[i])
        if m:
            name = next(g for g in m.groups() if g)
            if name not in NOT_FUNC:
                return name
    return None


def changed_lines(diff, sign):
    return [l[1:] for l in diff.splitlines() if l.startswith(sign) and not l.startswith(sign * 3)]


def describe(f):
    """Entry points and symbols touched in one file."""
    rel, diff, entries, symbols = f['rel'], f['diff'], [], []
    name = os.path.basename(rel)
    module = re.match(r'([a-z0-9_]+)\.(module|install|theme|post_update\.php|deploy\.php)$', name)
    touched = changed_lines(diff, '+') + changed_lines(diff, '-')
    if name.endswith('.routing.yml'):
        for line in touched:
            m = re.match(r'^([a-z0-9_.]+):\s*$', line)
            if m:
                entries.append(('route', m.group(1)))
            m = re.match(r"^\s+path:\s*'?([^'\s]+)", line)
            if m:
                f['paths'].add(m.group(1))
    elif name.endswith('.services.yml'):
        for line in touched:
            m = re.match(r'^  ([a-z0-9_.]+):\s*$', line)
            if m:
                entries.append(('service', m.group(1)))
    elif rel.startswith('config/') and name.endswith('.yml'):
        entries.append(('config', name[:-4]))
    elif re.search(r'src/pages/api/', rel):
        entries.append(('API route', '/' + re.sub(r'^src/pages/|(/index)?\.[jt]sx?$', '', rel)))
    elif re.search(r'src/pages/', rel) and not name.startswith('_'):
        entries.append(('page', '/' + re.sub(r'^src/pages/|(/index)?\.[jt]sx?$', '', rel)))
    if name.endswith('.info.yml') and f['status'] == 'A':
        entries.append(('new module', name[:-9]))
    if re.match(r'settings(\.[\w-]+)?\.php$|[\w-]+\.settings\.php$', name):
        entries.append(('settings', name))
    for kind, pat in (('controller', '/Controller/'), ('form', '/Form/'), ('plugin', '/Plugin/'),
                      ('event subscriber', '/EventSubscriber/'), ('route subscriber', '/Routing/'),
                      ('drush command', '/Drush/|/Commands/')):
        if re.search(pat, rel) and name.endswith('.php'):
            entries.append((kind, name[:-4]))
    src = (read(f['repo'], rel, f['base']) if f['status'] == 'D' else read(f['repo'], rel)).splitlines()
    old_src = read(f['repo'], rel, f['base']).splitlines() if f['status'] not in ('A', 'U') else []
    if f['status'] == 'A':  # whole file is new: list what it defines
        for line in src:
            m = FUNC.search(line)
            fn = next((g for g in m.groups() if g), None) if m else None
            if fn and fn not in NOT_FUNC and fn not in symbols:
                symbols.append(fn)
    else:
        for side, at in hunk_starts(diff):
            fn = enclosing(old_src if side == 'old' else src, at)
            if fn and fn not in symbols:
                symbols.append(fn)
    if rel.startswith('config/') and name.endswith('.yml'):
        f['details'] = [('+' if l in changed_lines(diff, '+') else '-') + ' ' + re.sub(r"['\"]", '', l.strip())
                        for l in changed_lines(diff, '+') + changed_lines(diff, '-')
                        if l.strip() and not CONFIG_NOISE.search(l)][:6]
    if module:
        mod = module.group(1)
        for fn in symbols:
            if re.match(rf'{mod}_update_\d+$', fn):
                entries.append(('update hook', fn))
            elif name.endswith(('post_update.php', 'deploy.php')):
                entries.append(('deploy hook' if 'deploy' in name else 'post-update', fn))
            elif fn.startswith(mod + '_'):
                entries.append(('hook', 'hook_' + fn[len(mod) + 1:]))
    f['entries'], f['symbols'] = entries, symbols


def config_family(f):
    """user.role.editor.yml -> user.role.*; None for non-config files."""
    name = os.path.basename(f['rel'])
    if not (f['rel'].startswith('config/') and name.endswith('.yml')):
        return None
    parts = name[:-4].split('.')
    return '.'.join(parts[:2]) + '.*' if len(parts) > 2 else None


def node_id(path):
    return 'n' + re.sub(r'[^A-Za-z0-9]', '_', path)


def esc(s):
    return s.replace('"', "'").replace('<', '‹').replace('>', '›')


HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{--fg:#1f2328;--bg:#fff;--muted:#f2f4f7;--line:#d0d7de}
body{font:15px/1.55 -apple-system,system-ui,Segoe UI,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:var(--fg);background:var(--bg)}
code{background:var(--muted);padding:1px 4px;border-radius:4px;font-size:13px}
table{border-collapse:collapse;display:block;overflow-x:auto}td,th{border:1px solid var(--line);padding:4px 8px}
h2{border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:32px}.mermaid{margin:12px 0;overflow-x:auto}
</style>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js" integrity="sha384-/TQbtLCAerC3jgaim+N78RZSDYV7ryeoBCVqTuzRrFec2akfBkHS7ACQ3PQhvMVi" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js" integrity="sha384-+VfUPEb0PdtChMwmBcBmykRMDd+v6D/oFmB3rZM/puCMDYcIvF968OimRh4KQY9a" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js" integrity="sha384-WmdflGW9aGfoBdHc4rRyWzYuAjEmDwMdGdiPNacbwfGKxBW/SO6guzuQ76qjnSlr" crossorigin="anonymous"></script>
</head><body><main id="c"></main>
<script id="md" type="text/markdown">{md}</script>
<script>
// The Markdown quotes code from the reviewed branch: sanitise before it becomes HTML.
document.getElementById('c').innerHTML = DOMPurify.sanitize(marked.parse(document.getElementById('md').textContent));
document.querySelectorAll('code.language-mermaid').forEach(c => {
  const d = document.createElement('div'); d.className = 'mermaid'; d.textContent = c.textContent; c.parentElement.replaceWith(d);
});
mermaid.initialize({startOnLoad: false, securityLevel: 'strict'}); mermaid.run();
</script></body></html>
"""


def md_text(s):
    return str(s).replace('<', '&lt;').replace('>', '&gt;').strip()


def seq_text(s):
    return re.sub(r'[;#<>]', ' ', str(s)).replace('"', "'").strip()[:90]


def render_tldr(st, by_sid, label, known):
    """TL;DR on top: short bullets, every flow as numbered steps, the checks the code performs."""
    out = []
    bullets = [md_text(b) for b in (st.get('tldr') or [])[:5] if str(b).strip()]
    flows = [fl for fl in (st.get('flows') or [])[:5] if fl.get('steps')]
    checks = [x for x in (st.get('checks') or [])[:8] if x.get('text')]
    if not (bullets or flows or checks):
        return out
    out += ['## TL;DR', '']
    out += [f'- {b}' for b in bullets]
    if bullets:
        out.append('')

    def who(ref):
        return f"`{os.path.basename(by_sid[ref]['rel'])}`" if ref in by_sid else md_text(ref)

    def files_of(refs):
        refs = [r for r in refs if r in by_sid]
        return ', '.join(f"`{os.path.basename(by_sid[r]['rel'])}`" for r in dict.fromkeys(refs))

    if flows:
        out += ['<details>', f'<summary><strong>Flows, step by step</strong> ({len(flows)} flows, same as the diagrams below)</summary>', '']
        for i, fl in enumerate(flows, 1):
            trigger = f" {md_text(fl['trigger'])}" if fl.get('trigger') else ''
            out.append(f"{i}. **{md_text(fl.get('title', 'Flow'))}.**{trigger}")
            for j, x in enumerate([x for x in fl['steps'][:10] if known(x.get('from')) and known(x.get('to'))], 1):
                actor = who(x['from']) if x['from'] == x['to'] else f"{who(x['from'])} to {who(x['to'])}"
                out.append(f"    {j}. {md_text(x.get('text', ''))} ({actor})")
        out += ['', '</details>', '']
    if checks:
        out += ['**Checks and validations in the code**', '']
        for x in checks:
            where = files_of([r for r in (x.get('nodes') or []) if known(r)])
            out.append(f"- {md_text(x['text'])}{' (' + where + ')' if where else ''}")
        out.append('')
    out += ['*TL;DR, flows and checks are written by a model from the code; they are not verified.*', '']
    return out


def render_stories(st, files, edges):
    """Model-written stories, kept honest: every step must name graph node ids (or a plain actor);
    a step between two files is solid only when the graph has a reference between them."""
    by_sid = {f['sid']: f for f in files}
    by_path = {f['path']: f['sid'] for f in files}
    linked = {(by_path[s], by_path[t]) for s, t, _ in edges} | {(by_path[t], by_path[s]) for s, t, _ in edges}
    labels = {k: v for k, v in (st.get('labels') or {}).items() if k in by_sid}
    warn, out = [], []
    label = lambda sid: labels.get(sid) or os.path.basename(by_sid[sid]['rel'])
    is_actor = lambda ref: isinstance(ref, str) and not re.fullmatch(r'F\d+', ref) and 0 < len(ref) <= 30

    def known(ref):
        if ref in by_sid or is_actor(ref):
            return True
        warn.append(f'model referenced `{ref}`, which is not a changed file in this map; step dropped')
        return False

    out += render_tldr(st, by_sid, label, known)
    if st.get('summary'):
        out += ['## What this change does', '', md_text(st['summary']), '']
    order = [x for x in (st.get('review_order') or [])[:5] if known(x.get('node'))]
    order = [x for x in order if x['node'] in by_sid]
    if order:
        out += ['## Start the review here', '']
        out += [f"{i}. **{md_text(label(x['node']))}**: `{by_sid[x['node']]['path']}`. {md_text(x.get('why', ''))}" for i, x in enumerate(order, 1)]
        out.append('')
    flows = (st.get('flows') or [])[:5]
    if flows:
        out += ['## Flows', '', 'Each flow is one thing that happens at runtime or at deploy. Solid arrow: the code of one file '
                'references the other directly. Dotted arrow: the step is read from the code by the model, with no direct '
                'reference between the two files (check it). Boxes show the plain-words role and the file.', '']
    for fl in flows:
        steps = [x for x in (fl.get('steps') or [])[:10] if known(x.get('from')) and known(x.get('to'))]
        if not steps:
            continue
        out += [f"### {md_text(fl.get('title', 'Flow'))}", '']
        if fl.get('trigger'):
            out += [f"*{md_text(fl['trigger'])}*", '']
        ids = {}

        def pid(ref):
            if ref not in ids:
                ids[ref] = f'P{len(ids) + 1}'
            return ids[ref]

        for x in steps:
            pid(x['from']), pid(x['to'])
        solid = lambda x: not (x['from'] in by_sid and x['to'] in by_sid) or (x['from'], x['to']) in linked or x['from'] == x['to']
        if fl.get('kind') == 'sequence':
            m = ['```mermaid', 'sequenceDiagram']
            for ref, p in ids.items():
                if ref in by_sid:
                    m.append(f"  participant {p} as {seq_text(label(ref))}<br/>{seq_text(os.path.basename(by_sid[ref]['rel']))}")
                else:
                    m.append(f'  actor {p} as {seq_text(ref)}')
            for x in steps:
                m.append(f"  {ids[x['from']]}{'->>' if solid(x) else '-->>'}{ids[x['to']]}: {seq_text(x.get('text', ''))}")
        else:
            m = ['```mermaid', 'flowchart LR']
            for ref, p in ids.items():
                if ref in by_sid:
                    m.append(f'  {p}["{esc(label(ref))}<br/><small>{esc(os.path.basename(by_sid[ref]["rel"]))}</small>"]')
                else:
                    m.append(f'  {p}(["{esc(ref)}"])')
            for x in steps:
                txt = esc(seq_text(x.get('text', '')))
                m.append(f"  {ids[x['from']]} {'-->' if solid(x) else '-.->'}{'|' + txt + '|' if txt else ''} {ids[x['to']]}")
        out += m + ['```', '']
        if fl.get('note'):
            out += [md_text(fl['note']), '']
    for key, title in (('settings', 'Settings that ship with this change'), ('deploy', 'Deploy and environment')):
        items = [x for x in (st.get(key) or []) if x.get('text')]
        if items:
            out += [f'## {title}', '']
            for x in items:
                refs = [r for r in (x.get('nodes') or []) if known(r) and r in by_sid]
                files_txt = ', '.join(f"`{os.path.basename(by_sid[r]['rel'])}`" for r in refs[:6])
                out.append(f"- {md_text(x['text'])}{' (' + files_txt + ')' if files_txt else ''}")
            out.append('')
    return out, warn


def method_code(f, call, limit=18):
    """The body of the function a step calls, from the file after the change, with the lines this change added
    marked. Read by the script, not the model: what the viewer shows next to a step is the real code."""
    names = re.findall(r'([A-Za-z_$][\w$]*)\s*(?:\(|$)', call or '')
    if not names or f['status'] == 'D':
        return None
    name = names[-1]
    try:
        src = read(f['repo'], f['rel']).splitlines()
    except Exception:
        return None
    start = next((i for i, l in enumerate(src) if (m := FUNC.search(l)) and name in [g for g in m.groups() if g]), None)
    if start is None:
        return None
    end, depth, opened = min(len(src) - 1, start + 200), 0, False
    for i in range(start, min(len(src), start + 200)):
        depth += src[i].count('{') - src[i].count('}')
        opened = opened or '{' in src[i]
        if opened and depth <= 0:
            end = i
            break
    added, new = set(), None
    for line in f['diff'].splitlines():
        m = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)', line)
        if m:
            new = int(m.group(1))
        elif new is not None and line.startswith('+') and not line.startswith('+++'):
            added.add(new)
            new += 1
        elif new is not None and not line.startswith('-'):
            new += 1
    whole = f['status'] in ('A', 'U')
    rows = [{'n': i + 1, 'text': src[i].rstrip()[:160], 'changed': whole or (i + 1) in added} for i in range(start, end + 1)]
    if len(rows) > limit:  # keep the signature and the window around the first changed line
        first = next((k for k, r in enumerate(rows) if r['changed']), 0)
        lo = max(1, min(first - 3, len(rows) - (limit - 1)))
        rows = rows[:1] + [{'n': 0, 'text': '…', 'changed': False}] * (lo > 1) + rows[lo:lo + limit - 2]
    return {'name': name, 'line': start + 1, 'lines': rows, 'changed': whole or any(r['changed'] for r in rows), 'new': whole}


def flow_export(st, files, edges):
    """The map as data for viewers (the Herdr task window): an overview, and per flow its participants with role,
    file and repo, and its steps with the call they make, an explanation, the called code and whether the graph backs
    the step. Same honesty rules as render_stories: unknown ids are dropped."""
    by_sid = {f['sid']: f for f in files}
    by_path = {f['path']: f['sid'] for f in files}
    linked = {(by_path[s], by_path[t]) for s, t, _ in edges} | {(by_path[t], by_path[s]) for s, t, _ in edges}
    labels = {k: v for k, v in (st.get('labels') or {}).items() if k in by_sid}
    roles = {k: v for k, v in (st.get('roles') or {}).items() if k in by_sid}
    is_actor = lambda ref: isinstance(ref, str) and not re.fullmatch(r'F\d+', ref) and 0 < len(ref) <= 30
    name = lambda r: labels.get(r) or os.path.basename(by_sid[r]['rel'])
    files_of = lambda refs: [by_sid[r]['rel'] for r in (refs or []) if r in by_sid]
    flows = []
    for fl in (st.get('flows') or [])[:5]:
        steps = [x for x in (fl.get('steps') or [])[:10] if all(r in by_sid or is_actor(r) for r in (x.get('from'), x.get('to')))]
        if not steps:
            continue
        refs = list(dict.fromkeys(r for x in steps for r in (x['from'], x['to'])))
        parts = [{'id': r, 'name': r, 'actor': True} if r not in by_sid else
                 {'id': r, 'name': name(r), 'role': roles.get(r, ''), 'actor': False,
                  'file': by_sid[r]['rel'], 'repo': by_sid[r]['repoLabel'], 'group': by_sid[r]['group'],
                  'status': by_sid[r]['status'], 'symbols': by_sid[r]['symbols'][:12]} for r in refs]
        flows.append({'title': fl.get('title', 'Flow'), 'trigger': fl.get('trigger', ''), 'kind': fl.get('kind', 'flow'),
                      'summary': fl.get('summary', ''), 'note': fl.get('note', ''), 'participants': parts,
                      'steps': [{'from': x['from'], 'to': x['to'], 'text': x.get('text', ''), 'call': (x.get('call') or '')[:80],
                                 'detail': x.get('detail', ''),
                                 'code': method_code(by_sid[x['to']], x.get('call')) if x['to'] in by_sid else None,
                                 'solid': not (x['from'] in by_sid and x['to'] in by_sid) or (x['from'], x['to']) in linked
                                 or x['from'] == x['to']} for x in steps]})
    return {'version': 2, 'summary': st.get('summary', ''), 'tldr': st.get('tldr') or [],
            'checks': [{'text': x.get('text', ''), 'files': files_of(x.get('nodes'))} for x in st.get('checks') or [] if x.get('text')],
            'review_order': [{'file': by_sid[x['node']]['rel'], 'name': name(x['node']), 'why': x.get('why', '')}
                             for x in st.get('review_order') or [] if x.get('node') in by_sid],
            'settings': [{'text': x.get('text', ''), 'files': files_of(x.get('nodes'))} for x in st.get('settings') or [] if x.get('text')],
            'deploy': [{'text': x.get('text', ''), 'files': files_of(x.get('nodes'))} for x in st.get('deploy') or [] if x.get('text')],
            'flows': flows}


def task_range(repo, key, branch):
    """(base, head, how, notes) for a task: its PR merge(s) or own commits on `branch`, else a
    feature branch named after it. None when the repo has no trace of the task."""
    pat = rf'{re.escape(key)}([^0-9]|$)'
    log = lambda *a: [l.split(' ', 1) for l in git(repo, 'log', branch, '--first-parent', '-E', *a, '--format=%H %s').splitlines()]
    merges, own, notes = log('--merges', f'--grep={pat}'), log('--no-merges', f'--grep=^{pat}'), []
    if merges:
        head, base, how = merges[0][0], git(repo, 'rev-parse', merges[-1][0] + '^1').strip(), f'{len(merges)} merge(s) on {branch}'
    elif own:
        head, base, how = own[0][0], git(repo, 'rev-parse', own[-1][0] + '^').strip(), f'{len(own)} commit(s) on {branch}'
    else:
        branches = [b for b in git(repo, 'branch', '--sort=-committerdate', '--format=%(refname:short)').split() if re.search(pat, b)]
        if not branches:
            return None
        head, base = git(repo, 'rev-parse', branches[0]).strip(), git(repo, 'merge-base', branch, branches[0]).strip()
        how = f'branch {branches[0]}, not merged into {branch}'
        if len(branches) > 1:
            notes.append(f'other branches named after {key}: {", ".join(branches[1:])}')
    foreign = [l for l in git(repo, 'log', '--first-parent', '--format=%h %s', f'{base}..{head}').splitlines() if not re.search(pat, l)]
    only = None
    if foreign:
        # Keep the map to files the task's own merges/commits touched; shared files may still carry foreign edits.
        own_shas = [m[0] for m in (merges or own)]
        only = set()
        for sha in own_shas:
            parent = f'{sha}^1' if merges else f'{sha}^'
            only |= set(git(repo, 'diff', '--name-only', parent, sha).splitlines())
        notes.append(f'{len(foreign)} commit(s) of other work inside the range ('
                     + '; '.join(foreign[:3]) + (' …' if len(foreign) > 3 else '')
                     + f'); map limited to the {len(only)} files the task itself changed')
    return base, head, how, notes, only


def scopes(a, root):
    """collect() per repo; in --task mode on detached worktrees at the task's head."""
    repos = [(root, a.path)] + ([(prepare.git(os.path.abspath(a.pair), 'rev-parse', '--show-toplevel'), None)] if a.pair else [])
    if a.committed and not a.task:
        # Committed state only: collect on detached worktrees, so uncommitted and untracked files stay out.
        tmp, worktrees, parts = tempfile.mkdtemp(prefix='change-map-'), [], []
        display = os.path.commonpath([r for r, _ in repos])
        for i, (r, pth) in enumerate(repos):
            head = git(r, 'rev-parse', a.committed if i == 0 else 'HEAD').strip()
            wt = os.path.join(tmp, os.path.basename(r))
            git(r, 'worktree', 'add', '--detach', '-q', wt, head)
            worktrees.append((r, wt))
            p = prepare.collect(wt, a.base, pth, None, os.path.relpath(r, display) if a.pair else '', a.force_wide)
            branch = git(r, 'rev-parse', '--abbrev-ref', 'HEAD').strip() if i == 0 and a.committed == 'HEAD' else a.committed
            p['repo'].update(real=r, head=head, branch=f'{branch} @ {head[:9]} (committed)')
            parts.append(p)
        return parts, worktrees, []
    if not a.task:
        display = os.path.commonpath([r for r, _ in repos])
        parts = [prepare.collect(r, a.base, pth, None, os.path.relpath(r, display) if a.pair else '', a.force_wide)
                 for r, pth in repos]
        for p, (r, _) in zip(parts, repos):
            p['repo'].update(real=r, head=None)
        return parts, [], []
    tmp, worktrees, ranges, found = tempfile.mkdtemp(prefix='change-map-'), [], [], []
    for r, pth in repos:
        rng = task_range(r, a.task, a.branch)
        if not rng:
            ranges.append(f'{os.path.basename(r)}: no merge, commit or branch for {a.task}')
            continue
        base, head, how, notes, only = rng
        wt = os.path.join(tmp, os.path.basename(r))
        git(r, 'worktree', 'add', '--detach', '-q', wt, head)
        worktrees.append((r, wt))
        found.append((wt, base, pth, head, how, only, r))
        ranges += [f'{os.path.basename(r)}: {how}, `{base[:9]}..{head[:9]}`'] + [f'{os.path.basename(r)}: {n}' for n in notes]
    parts = []
    for wt, base, pth, head, how, only, real in found:
        p = prepare.collect(wt, base, pth, None, os.path.basename(wt) if len(found) > 1 else '', True)
        p['only'] = only
        p['repo'].update(branch=f'{a.task} @ {head[:9]}', baseLabel=base[:9], label=os.path.basename(wt), real=real, head=head)
        parts.append(p)
    return parts, worktrees, ranges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base')
    ap.add_argument('--pair')
    ap.add_argument('--path')
    ap.add_argument('--force-wide', action='store_true')
    ap.add_argument('--title', default='Change map')
    ap.add_argument('--committed', nargs='?', const='HEAD', metavar='REF',
                    help='map only committed changes up to REF (default HEAD); uncommitted and untracked files are left out')
    ap.add_argument('--task', help='map a finished task by its key (PR merge or own commits on --branch, else its feature branch)')
    ap.add_argument('--branch', default='develop', help='integration branch searched in --task mode')
    ap.add_argument('--svg', action='store_true', help='also render the graph to <out>.svg with mmdc')
    ap.add_argument('--json', help='write the graph (short node ids, diff commands) for the stories pass')
    ap.add_argument('--stories', help='stories JSON from the model pass; validated against the graph and rendered on top')
    ap.add_argument('--html', action='store_true', help='also write <out>.html (renders Markdown + Mermaid in a browser)')
    ap.add_argument('--out', required=True, help='output .md file')
    a = ap.parse_args()

    root = prepare.git(os.getcwd(), 'rev-parse', '--show-toplevel')
    parts, worktrees, ranges = scopes(a, root)
    try:
        render(a, parts, ranges)
    finally:
        for repo, wt in worktrees:
            git(repo, 'worktree', 'remove', '--force', wt)


def render(a, parts, ranges):
    pair_mode = len(parts) > 1

    files, docs, skipped = [], 0, 0
    for p in parts:
        repo, base, label = p['repo']['root'], p['repo']['base'], p['repo']['label'] if pair_mode else ''
        seen = {e['rel']: e for g in ('drupal', 'nextjs', 'infra') for e in p['groups'][g]}
        name_status = {l.split('\t')[-1]: l[0] for l in git(repo, 'diff', '--name-status', '-M', base).splitlines() if l}
        for rel in git(repo, 'diff', '--name-only', base).splitlines() + git(repo, 'ls-files', '--others', '--exclude-standard').splitlines():
            if rel in seen or not TEST_FILE.search(rel) or DOC_FILE.search(rel):
                continue
            seen[rel] = {'rel': rel, 'status': name_status.get(rel, 'U')}
        docs += sum(1 for s in p['skipped'] if DOC_FILE.search(s))
        skipped += sum(1 for s in p['skipped'] if not DOC_FILE.search(s))
        numstat = {}
        for line in git(repo, 'diff', '--numstat', '-M', base).splitlines():
            add, rem, f = line.split('\t', 2)
            f = re.sub(r'\{[^}]* => ([^}]*)\}', r'\1', f).split(' => ')[-1]
            numstat[f] = (int(add) if add.isdigit() else 0, int(rem) if rem.isdigit() else 0)
        if p.get('only') is not None:
            seen = {k: v for k, v in seen.items() if k in p['only']}
        for rel, e in sorted(seen.items()):
            status = e['status']
            if status == 'U':
                text = read(repo, rel)
                diff = '@@ -0,0 +1 @@\n' + '\n'.join('+' + l for l in text.splitlines())
                add, rem = len(text.splitlines()), 0
            else:
                diff = git(repo, 'diff', '--diff-algorithm=patience', '-M', '-U0', base, '--', rel)
                add, rem = numstat.get(rel, (0, 0))
            f = {'repo': repo, 'repoLabel': p['repo']['label'], 'rel': rel, 'path': f'{label}/{rel}' if label else rel,
                 'base': base, 'status': 'A' if status == 'U' else status, 'add': add, 'rem': rem, 'diff': diff,
                 'group': ('tests' if TEST_FILE.search(rel) else group_of(rel)), 'test': bool(TEST_FILE.search(rel)),
                 'paths': set(), 'details': []}
            describe(f)
            f['text'] = read(repo, rel, base) if f['status'] == 'D' else read(repo, rel)
            files.append(f)

    # Edges between changed files.
    edges = set()
    by_path = {f['path']: f for f in files}
    php = {}
    for f in files:
        if f['rel'].endswith('.php'):
            ns = re.search(r'^namespace\s+([\w\\]+);', f['text'], re.M)
            cls = re.search(r'^(?:final\s+|abstract\s+)*(?:class|interface|trait|enum)\s+(\w+)', f['text'], re.M)
            if ns and cls:
                php[f'{ns.group(1)}\\{cls.group(1)}'] = f
    services = {}
    for f in files:
        if f['rel'].endswith('.services.yml'):
            for sid, body in re.findall(r'^  ([a-z0-9_.]+):\s*\n((?:    .*\n?)*)', f['text'], re.M):
                services[sid] = f
                m = re.search(r'class:\s*\\?([\w\\]+)', body)
                if m and m.group(1) in php:
                    edges.add((f['path'], php[m.group(1)]['path'], 'service class'))
    for f in files:
        for fqcn, target in php.items():
            if target is f:
                continue
            short = fqcn.split('\\')[-1]
            if fqcn in f['text'] or fqcn.replace('\\', '\\\\') in f['text'] or (
                    f['rel'].endswith('.yml') and re.search(rf'\\?{re.escape(fqcn)}::', f['text'])):
                edges.add((f['path'], target['path'], 'test' if f['test'] else 'uses'))
            elif f['test'] and re.search(rf'\b{short}\b', f['text']) and target['repo'] == f['repo']:
                edges.add((f['path'], target['path'], 'test'))
        for sid, target in services.items():
            if target is not f and re.search(rf"@{re.escape(sid)}\b|service\(['\"]{re.escape(sid)}['\"]\)|get\(['\"]{re.escape(sid)}['\"]\)", f['text']):
                edges.add((f['path'], target['path'], 'DI'))
    # Config that enables or depends on a changed module points at that module.
    mods = {}
    for f in files:
        m = re.match(r'module (\S+)$', f['group'])
        if m and (m.group(1) not in mods or f['rel'].endswith('.info.yml')):
            mods[m.group(1)] = f
    for f in files:
        if f['rel'].startswith('config/'):
            for mod, target in mods.items():
                if re.search(rf'^\s*(-\s*{mod}|{mod}:)\s*(\d+)?\s*$', f['text'], re.M):
                    edges.add((f['path'], target['path'], 'config'))
    # Config naming another changed config by id as a scalar value (encryption_key: tfa_encryption_key).
    cfg = [f for f in files if f['rel'].startswith('config/') and f['rel'].endswith('.yml')]
    for g in cfg:
        cid = os.path.basename(g['rel'])[:-4].split('.')[-1]
        if len(cid) < 3:
            continue
        for f in cfg:
            if f is not g and re.search(rf"^\s*[a-z_]+:\s*['\"]?{re.escape(cid)}['\"]?\s*$", f['text'], re.M):
                edges.add((f['path'], g['path'], 'config ref'))
    edges -= {(s, t, 'uses') for s, t, l in set(edges) if l == 'service class'}
    ts = [f for f in files if re.search(r'\.[jt]sx?$', f['rel'])]
    ts_index = {}
    for f in ts:
        stem = re.sub(r'(/index)?\.[jt]sx?$', '', f['rel'])
        ts_index[(f['repo'], stem)] = f
    for f in ts:
        for spec in re.findall(r'(?:from\s+|import\(\s*|require\(\s*)["\']([^"\']+)["\']', f['text']):
            if spec.startswith('~/'):
                stem = 'src/' + spec[2:]
            elif spec.startswith('.'):
                stem = os.path.normpath(os.path.join(os.path.dirname(f['rel']), spec))
            elif spec.startswith('@ffw/'):
                stem = 'utils/packages/' + spec[5:] + '/src/index'
            else:
                continue
            stem = re.sub(r'\.[jt]sx?$', '', stem)
            target = ts_index.get((f['repo'], stem)) or ts_index.get((f['repo'], stem + '/index'))
            if target and target is not f:
                edges.add((f['path'], target['path'], 'test' if f['test'] else 'imports'))

    # Drupal <-> Next seam: registry keys vs bundles, x- headers, route paths.
    seam = []
    registry = {}
    for p in parts:
        reg = read(p['repo']['root'], 'src/themes/default/registry.js')
        for key, target in REGISTRY.findall(reg):
            registry['src/themes/default/' + target] = key
    bundles = {}
    for f in files:
        for b in BUNDLE_CONFIG.findall(os.path.basename(f['rel'])):
            bundles.setdefault(b, []).append(f)
    for f in files:
        for comp, key in registry.items():
            if f['rel'].startswith(comp + '/') or re.sub(r'(/index)?\.[jt]sx?$', '', f['rel']) == comp:
                b = key.split('--')[0].replace('-', '_')
                for d in bundles.get(b, []):
                    edges.add((d['path'], f['path'], f'seam: bundle {b}'))
                    seam.append(('bundle', b, d['path'], f['path']))
    headers = {}
    for f in files:
        for h in set(x.lower() for x in HEADER.findall('\n'.join(changed_lines(f['diff'], '+') + changed_lines(f['diff'], '-')))):
            headers.setdefault(h, []).append(f)
    for h, fs in headers.items():
        sides = {f['repoLabel'] for f in fs}
        if len(sides) > 1:
            for x in fs:
                for y in fs:
                    if x['repoLabel'] < y['repoLabel']:
                        edges.add((x['path'], y['path'], f'seam: {h}'))
                        seam.append(('header', h, x['path'], y['path']))
    for f in files:
        for route in f['paths']:
            for g in files:
                if g['repoLabel'] != f['repoLabel'] and route in g['text'] and len(route) > 4:
                    edges.add((f['path'], g['path'], f'seam: {route}'))
                    seam.append(('route', route, f['path'], g['path']))

    for i, f in enumerate(sorted(files, key=lambda x: x['path']), 1):
        f['sid'] = f'F{i}'
    real = {p['repo']['root']: p['repo'] for p in parts}
    if a.json:
        def cmds(f):
            r = real[f['repo']]
            if r.get('head'):
                return (shlex.join(['git', '-C', r['real'], 'diff', f['base'], r['head'], '--', f['rel']]),
                        shlex.join(['git', '-C', r['real'], 'show', f"{r['head']}:{f['rel']}"]))
            return (shlex.join(['git', '-C', r['real'], 'diff', f['base'], '--', f['rel']]),
                    shlex.join(['cat', os.path.join(r['real'], f['rel'])]))
        by = {f['path']: f['sid'] for f in files}
        json.dump({'title': a.title, 'ranges': ranges,
                   'nodes': [{'id': f['sid'], 'path': f['path'], 'group': f['group'], 'status': f['status'], 'add': f['add'],
                              'rem': f['rem'], 'test': f['test'], 'entries': f['entries'], 'symbols': f['symbols'][:15],
                              'config_changes': f['details'], 'diff_cmd': cmds(f)[0], 'show_cmd': cmds(f)[1]} for f in files],
                   'edges': [{'from': by[s], 'to': by[t], 'label': l} for s, t, l in sorted(edges)],
                   'seam': [{'kind': k, 'key': key, 'from': by[x], 'to': by[y]} for k, key, x, y in sorted(set(seam))]},
                  open(a.json, 'w'), indent=1)
    story_lines, story_warn = render_stories(json.load(open(a.stories)), files, edges) if a.stories else ([], [])

    # Render.
    total_add, total_rem = sum(f['add'] for f in files), sum(f['rem'] for f in files)
    repo_line = '; '.join(f"{p['repo']['label']} `{p['repo']['branch']}` vs `{p['repo']['baseLabel']}`" for p in parts)
    out = [f'# {a.title}', '']
    if ranges:
        out += ['Range: ' + ' · '.join(ranges), '']
    out += [f'{repo_line}. {len(files)} code/config/test files, +{total_add} / -{total_rem} lines'
           f'{f"; {docs} doc files and {skipped} other files not shown" if docs or skipped else ""}.', '']
    out += story_lines

    # Three or more config files of one family (user.role.*, field.field.*) render as one node.
    fam = {}
    for f in files:
        k = config_family(f)
        if k:
            fam.setdefault((f['repoLabel'], f['group'], k), []).append(f)
    fam = {k: v for k, v in fam.items() if len(v) >= 3}
    fam_of = {f['path']: k for k, v in fam.items() for f in v}
    collapse = len(files) - sum(len(v) - 1 for v in fam.values()) > MAX_NODES
    mer = ['```mermaid', 'flowchart LR']
    if collapse:
        groups = {}
        for f in files:
            groups.setdefault((f['repoLabel'], f['group']), []).append(f)
        gid = {k: 'g' + re.sub(r'[^A-Za-z0-9]', '_', '_'.join(k)) for k in groups}
        for repo in sorted({k[0] for k in groups}):
            mer.append(f'  subgraph {re.sub(r"[^A-Za-z0-9]", "_", repo)}["{esc(repo)}"]')
            for k, fs in sorted(groups.items()):
                if k[0] == repo:
                    mer.append(f'    {gid[k]}["{esc(k[1])}<br/>{len(fs)} files, +{sum(x["add"] for x in fs)} -{sum(x["rem"] for x in fs)}"]')
            mer.append('  end')
        agg = {}
        for s, t, lbl in edges:
            ks, kt = (by_path[s]['repoLabel'], by_path[s]['group']), (by_path[t]['repoLabel'], by_path[t]['group'])
            if ks != kt:
                agg.setdefault((gid[ks], gid[kt]), set()).add(lbl.split(':')[0])
        for (s, t), lbls in sorted(agg.items()):
            mer.append(f'  {s} -->|{esc(", ".join(sorted(lbls)))}| {t}')
    else:
        for repo in sorted({f['repoLabel'] for f in files}):
            if pair_mode:
                mer.append(f'  subgraph {re.sub(r"[^A-Za-z0-9]", "_", repo)}["{esc(repo)}"]')
            for grp in sorted({f['group'] for f in files if f['repoLabel'] == repo}):
                mer.append(f'    subgraph {node_id(repo + grp)}["{esc(grp)}"]')
                for k, fs in fam.items():
                    if k[0] == repo and k[1] == grp:
                        mer.append(f'      {node_id(repo + k[2])}["{esc(k[2])} ×{len(fs)}<br/>+{sum(x["add"] for x in fs)} -{sum(x["rem"] for x in fs)}<br/>config"]')
                for f in files:
                    if f['repoLabel'] == repo and f['group'] == grp and f['path'] not in fam_of:
                        tags = ', '.join(dict.fromkeys(k for k, _ in f['entries']))
                        mark = {'A': 'new ', 'D': 'deleted '}.get(f['status'], '')
                        mer.append(f'      {node_id(f["path"])}["{esc(os.path.basename(f["rel"]))}<br/>{mark}+{f["add"]} -{f["rem"]}'
                                   f'{"<br/>" + esc(tags) if tags else ""}"]')
                mer.append('    end')
            if pair_mode:
                mer.append('  end')
        nid = lambda p: node_id(fam_of[p][0] + fam_of[p][2]) if p in fam_of else node_id(p)
        for s, t, lbl in sorted({(nid(s), nid(t), l) for s, t, l in edges if nid(s) != nid(t)}):
            arrow = '-.->' if lbl == 'test' else '==>' if lbl.startswith('seam') else '-->'
            mer.append(f'  {s} {arrow}|{esc(lbl)}| {t}')
        mer.append('  classDef added stroke:#2e7d32,stroke-width:2px')
        mer.append('  classDef deleted stroke:#c62828,stroke-width:2px,stroke-dasharray:4')
        mer.append('  classDef entry stroke-width:3px')
        for f in (x for x in files if x['path'] not in fam_of):
            cls = 'added' if f['status'] == 'A' else 'deleted' if f['status'] == 'D' else 'entry' if f['entries'] else None
            if cls:
                mer.append(f'  class {node_id(f["path"])} {cls}')
    mer.append('```')
    fm_at = len(out) + 3
    out += ['## File map', '', 'Solid arrow: code reference or DI; thick: Drupal-Next seam; dotted: test. Green border: new file, red dashed: deleted, thick: entry point.'
            + (' Collapsed to areas because the change has more than %d files.' % MAX_NODES if collapse else ''), ''] + mer + ['']

    entries = [(k, n, f['path'], f['status']) for f in files if f['path'] not in fam_of for k, n in f['entries']]
    for (repo, grp, k), fs in fam.items():
        st = ''.join(sorted({x['status'] for x in fs}))
        entries.append(('config', f'{k} ({len(fs)} files)', f'{os.path.dirname(fs[0]["path"])}/', st))
    if entries:
        out += ['## Entry points touched', '', '| kind | name | file | status |', '|---|---|---|---|']
        out += [f'| {k} | `{n}` | `{p}` | {s} |' for k, n, p, s in sorted(set(entries))] + ['']
    if seam:
        out += ['## Drupal - Next seam', '']
        out += [f'- {kind} `{key}`: `{s}` ↔ `{t}`' for kind, key, s, t in sorted(set(seam))] + ['']
    out += ['## Files by area', '']
    for repo in sorted({f['repoLabel'] for f in files}):
        for grp in sorted({f['group'] for f in files if f['repoLabel'] == repo}):
            out.append(f'**{repo + " / " if pair_mode else ""}{grp}**')
            for f in files:
                if f['repoLabel'] == repo and f['group'] == grp:
                    sym = f' — {", ".join(f["symbols"][:8])}{" …" if len(f["symbols"]) > 8 else ""}' if f['symbols'] else ''
                    out.append(f'- `{f["rel"]}` ({f["status"]}, +{f["add"]} -{f["rem"]}){sym}')
                    out += [f'  - `{d}`' for d in f['details']]
            out.append('')

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    svg = None
    if a.svg and files:
        if shutil.which('mmdc'):
            svg = os.path.splitext(os.path.abspath(a.out))[0] + '.svg'
            src = svg[:-4] + '.mmd'
            open(src, 'w').write('\n'.join(mer[1:-1]))
            r = subprocess.run(['mmdc', '-i', src, '-o', svg, '-b', 'white'], capture_output=True, text=True)
            os.remove(src)
            if r.returncode:
                print(f'mmdc failed: {r.stderr.strip()[-500:]}', file=sys.stderr)
                svg = None
            else:
                i = out.index('```', fm_at) + 1
                out.insert(i, f'\n![graph]({os.path.basename(svg)})')
        else:
            print('mmdc not installed (npm i -g @mermaid-js/mermaid-cli); SVG skipped', file=sys.stderr)
    if story_warn:
        out += ['## Notes on the flows', ''] + [f'- {w}' for w in story_warn] + ['']
    open(a.out, 'w').write('\n'.join(out))
    flow = None
    if a.stories:
        flow = os.path.join(os.path.dirname(os.path.abspath(a.out)), 'flow.json')
        open(flow, 'w').write(json.dumps(flow_export(json.load(open(a.stories)), files, edges), indent=1, ensure_ascii=False))
    html = None
    if a.html:
        html = os.path.splitext(os.path.abspath(a.out))[0] + '.html'
        md = re.sub(r'</(script)', r'<\\/\1', '\n'.join(l for l in out if not l.startswith('\n![graph]')), flags=re.I)
        open(html, 'w').write(HTML.replace('{title}', esc(a.title)).replace('{md}', md))
    print(json.dumps({'out': os.path.abspath(a.out), 'svg': svg, 'html': html, 'flow': flow, 'flow_warnings': story_warn, 'ranges': ranges, 'files': len(files), 'edges': len(edges), 'seam': len(set(seam)),
                      'entries': len(set(entries)), 'collapsed': collapse,
                      'notes': [n for p in parts for n in p['notes']]}, indent=1))


if __name__ == '__main__':
    main()
