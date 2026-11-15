#!/usr/bin/env python3
"""Collect the review scope for secperf-review and write args.json for the workflow.

Scope = changes on the current branch vs the merge-base with the default branch,
plus staged, unstaged and untracked files. With --pair, the same scope is collected
from a second repo (the other half of a decoupled project). Deterministic facts
(stack, versions, audits) are computed here so the models never re-derive them.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = '.claude/secperf/config.json'
PROJECT_CONTEXT = '.claude/secperf/project.md'

# CI and pipeline files carry secrets and build args: they go to the infra finder, never to EXCLUDE.
CI = re.compile(
    r'(^|/)(azure-pipelines[^/]*\.ya?ml|\.gitlab-ci\.yml|bitbucket-pipelines\.yml|Jenkinsfile)$'
    r'|(^|/)(\.azure|\.github/workflows|\.circleci|\.infrastructure)/'
)
EXCLUDE = re.compile(
    r'(^|/)(vendor|node_modules|\.next|dist|build|out|coverage|\.git)/'
    r'|(^|/)(modules|themes|profiles|libraries)/contrib/'
    r'|(^|/)sites/[^/]+/files/'
    r'|(^|/)next-env\.d\.ts$|(^|/)(tests?|__tests__|e2e|cypress|playwright|test-results|\.ddev|\.lando|\.github|\.gitlab|\.storybook|stories)/'
    r'|\.(test|spec|stories)\.[jt]sx?$|(^|/)\.platform'
    r'|\.min\.(js|css)$|\.map$|\.(png|jpe?g|gif|webp|avif|ico|svg|woff2?|ttf|eot|pdf|zip|gz)$'
)
MANIFESTS = {'composer.json', 'composer.lock', 'package.json', 'package-lock.json',
             'pnpm-lock.yaml', 'yarn.lock', 'bun.lockb'}
# .patch: contrib/core patches the project ships are code it runs.
DRUPAL_EXT = re.compile(r'\.(php|module|install|inc|theme|profile|engine|twig|yml|yaml|patch)$')
FRONT_EXT = re.compile(r'\.(tsx?|jsx?|mjs|cjs)$')
STYLE_EXT = re.compile(r'\.(css|scss|sass|less)$')
A11Y = re.compile(r'\.(twig|tsx|jsx|html|css|scss|sass|less)$|/Form/|\.theme$')
INFRA = re.compile(r'(\.vcl$|nginx|Dockerfile|docker-compose|\.htaccess$|vercel\.json$|netlify\.toml$'
                   r'|\.(tf|tfvars|hcl)$|(^|/)terraform/.*\.[cm]?[jt]s$|(^|/)(lambda-edge|cloudfront[^/]*|edge-functions?)/)')
DRUPAL_YML = re.compile(r'(^|/)(modules|themes|profiles|config|sites|recipes)/')
DRUPAL_CORE = re.compile(r'^(web/|docroot/|html/)?core/')
SEAM_MARKERS = re.compile(r'next-drupal|drupal-jsonapi-params|/jsonapi|jsonapi\.|graphql|revalidate|next_site|simple_oauth|decoupled_router', re.I)
# Source files of other stacks (Laravel, Symfony, Django, FastAPI, Flask, Go, Rust, Rails, JVM, .NET, Elixir,
# Swift) go to the `generic` group when Drupal and Next.js did not claim them. Templates count as source.
GENERIC_EXT = re.compile(r'\.(php|py|go|rs|rb|erb|java|kt|cs|ex|exs|scala|swift|jinja2?|j2)$')
GENERIC_TEMPLATE = re.compile(r'(^|/)templates/(.*/)?[^/]+\.html?$')
# Test files of those stacks that live next to the code (tests/ dirs are already in EXCLUDE).
GENERIC_TEST = re.compile(r'(_test\.(go|py|rb|exs)|(^|/)(test_[^/]*|conftest|tests)\.py|_spec\.rb'
                          r'|(Test|Tests|IT)\.(java|kt|cs|scala|swift))$|(^|/)spec/')
# Code no group claims; reported as "not covered" instead of disappearing into `skipped`.
CODE = re.compile(r'\.(php|py|go|rs|rb|erb|java|kt|kts|cs|ex|exs|scala|swift|[cm]?[jt]sx?|vue|svelte|c|cc|cpp|h|hpp'
                  r'|m|mm|lua|pl|pm|sh|bash|ps1|sql|dart|groovy|clj|hs|ml|fs|erl)$')
LANG_OF = {'php': 'php', 'py': 'python', 'jinja': 'python', 'jinja2': 'python', 'j2': 'python', 'go': 'go',
           'rs': 'rust', 'rb': 'ruby', 'erb': 'ruby', 'java': 'java', 'kt': 'kotlin', 'scala': 'scala',
           'cs': 'csharp', 'ex': 'elixir', 'exs': 'elixir', 'swift': 'swift'}
PY_MANIFESTS = ('pyproject.toml', 'requirements.txt', 'setup.py', 'setup.cfg', 'Pipfile')
LINE_CAP = 1500  # changed lines per finder shard
MAX_COMMITS = 40  # a wider diff almost always means a wrong base


def git(repo, *a, check=True):
    # errors='replace': a diff of a file with invalid UTF-8 must not crash the run.
    r = subprocess.run(['git', '-C', repo, *a], capture_output=True, text=True, errors='replace')
    if check and r.returncode:
        sys.exit(f'git -C {repo} {" ".join(a)} failed: {r.stderr.strip()}')
    return r.stdout.strip()


def load_config(repo):
    try:
        return json.load(open(os.path.join(repo, CONFIG)))
    except FileNotFoundError:
        return {}
    except ValueError as e:
        sys.exit(f'{os.path.join(repo, CONFIG)} is not valid JSON: {e}')


def default_branch(repo):
    ref = git(repo, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD', check=False)
    if ref:
        return ref.replace('refs/remotes/', '')
    for b in ('origin/main', 'origin/master', 'origin/develop', 'main', 'master', 'develop'):
        if git(repo, 'rev-parse', '--verify', '--quiet', b, check=False):
            return b
    return None


def resolve_base(repo, explicit):
    notes = []
    if explicit:
        return git(repo, 'merge-base', 'HEAD', explicit, check=False) or explicit, explicit, notes
    db = default_branch(repo)
    if not db:
        notes.append('No default branch found; reviewing uncommitted changes against HEAD only.')
        return 'HEAD', 'HEAD', notes
    notes.append(f'Base auto-detected as {db}. Set "base" in {CONFIG} or pass --base if that is not the integration branch.')
    mb = git(repo, 'merge-base', 'HEAD', db)
    if mb == git(repo, 'rev-parse', 'HEAD'):
        if git(repo, 'status', '--porcelain'):
            notes.append(f'HEAD has no commits ahead of {db}; reviewing uncommitted changes only.')
            return 'HEAD', 'HEAD', notes
        notes.append(f'HEAD has no commits ahead of {db} and the tree is clean; reviewing the last commit.')
        return 'HEAD~1', 'HEAD~1', notes
    return mb, db, notes


def find_next_roots(root):
    roots = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('node_modules', 'vendor', '.git', '.next', 'core', 'contrib')]
        if dirpath.count(os.sep) - root.count(os.sep) > 3:
            dirnames[:] = []
            continue
        if 'package.json' in filenames:
            try:
                pkg = json.load(open(os.path.join(dirpath, 'package.json')))
            except (OSError, ValueError):
                continue
            deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
            is_app = any(n.startswith('next.config.') for n in filenames) or {'app', 'pages'} & set(dirnames) \
                or any(os.path.isdir(os.path.join(dirpath, 'src', x)) for x in ('app', 'pages'))
            if 'next' in deps and is_app:
                rel = os.path.relpath(dirpath, root)
                roots.append('' if rel == '.' else rel)
    return roots


def lock_version(path, name):
    try:
        data = json.load(open(path))
    except (OSError, ValueError):
        return None
    if 'packages' in data and isinstance(data['packages'], list):  # composer.lock
        for p in data['packages']:
            if p.get('name') == name:
                return p.get('version')
        return None
    pkgs = data.get('packages', {})  # package-lock v2/v3
    entry = pkgs.get(f'node_modules/{name}')
    return entry.get('version') if entry else None


def run_audit(cmd, cwd):
    if not shutil.which(cmd[0]):
        return f'{cmd[0]} not installed, audit not run'
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return f'{" ".join(cmd)} timed out'
    out = (r.stdout or r.stderr).strip()
    try:
        data = json.loads(out)
    except ValueError:
        return out[:4000] or 'no output'
    rows = []
    for pkg, advs in (data.get('advisories') or {}).items():  # composer
        for adv in (advs.values() if isinstance(advs, dict) else advs):
            rows.append(f"{pkg}: {adv.get('title')} [{adv.get('cve') or adv.get('advisoryId')}] affected {adv.get('affectedVersions')}")
    for pkg, v in (data.get('vulnerabilities') or {}).items():  # npm
        titles = [x.get('title') for x in v.get('via', []) if isinstance(x, dict)]
        rows.append(f"{pkg} ({v.get('severity')}): {'; '.join(filter(None, titles)) or 'via ' + ', '.join(map(str, v.get('via', [])))}")
    return '\n'.join(rows)[:4000] if rows else 'no advisories reported'


def excluded_by_glob(f, globs):
    return any(fnmatch.fnmatch(f, g) or fnmatch.fnmatch(f, g.rstrip('/') + '/*') for g in globs)


def _read(path):
    try:
        return open(path, errors='ignore').read().lower()
    except OSError:
        return ''


def framework_at(d, lang):
    """Framework label from the marker files in directory d, or None when d has no marker for lang."""
    has = lambda n: os.path.exists(os.path.join(d, n))
    if lang == 'php' and (has('composer.json') or has('artisan')):
        c = _read(os.path.join(d, 'composer.json'))
        if has('artisan') or 'laravel/framework' in c:
            return 'laravel'
        return 'symfony' if 'symfony/framework-bundle' in c or has('symfony.lock') else 'php'
    if lang in ('python', None):  # None: an .html template, Python or Go decides
        req_dir = os.path.join(d, 'requirements')
        if has('manage.py') or any(has(n) for n in PY_MANIFESTS) or os.path.isdir(req_dir):
            deps = ' '.join([_read(os.path.join(d, n)) for n in PY_MANIFESTS] +
                            [_read(os.path.join(req_dir, n)) for n in (os.listdir(req_dir) if os.path.isdir(req_dir) else [])])
            for fw in ('django', 'fastapi', 'flask'):
                if (fw == 'django' and has('manage.py')) or re.search(rf'\b{fw}\b', deps):
                    return fw
            return 'python'
        if lang is None and has('go.mod'):
            return 'go'
    if lang == 'ruby' and has('Gemfile'):
        return 'rails' if re.search(r'''['"]rails['"]''', _read(os.path.join(d, 'Gemfile'))) else 'ruby'
    if lang in ('java', 'kotlin', 'scala') and any(has(n) for n in ('pom.xml', 'build.gradle', 'build.gradle.kts')):
        return 'java'
    return None


def stack_of(repo, rel, cache):
    """Stack label of a generic file: the nearest marker file up to the repo root, else the language."""
    lang = LANG_OF.get(rel.rsplit('.', 1)[-1].lower())
    if lang in ('php', 'python', 'ruby', 'java', 'kotlin', 'scala', None):
        d = os.path.dirname(rel)
        while True:
            if (d, lang) not in cache:
                cache[(d, lang)] = framework_at(os.path.join(repo, d), lang)
            if cache[(d, lang)]:
                return cache[(d, lang)]
            if not d:
                break
            d = os.path.dirname(d)
    return lang or 'templates'


def collect(repo, base_arg, path, stack, label, force_wide, globs=()):
    """Classify one repo's changes. `label` prefixes display paths in pair mode ('' otherwise)."""
    cfg = load_config(repo)
    base, base_label, notes = resolve_base(repo, base_arg or cfg.get('base'))
    commits = int(git(repo, 'rev-list', '--count', f'{base}..HEAD', check=False) or 0) if base != 'HEAD' else 0
    limit = cfg.get('maxCommits', MAX_COMMITS)
    if commits > limit and not force_wide:
        sys.exit(f'{repo}: {commits} commits between {base_label} and HEAD (limit {limit}). The base is probably wrong '
                 f'(stale remote?). Pass --base <integration branch>, set "base" in {CONFIG}, or --force-wide.')
    extra_exclude = re.compile('|'.join(cfg['exclude'])) if cfg.get('exclude') else None

    status = {}
    for line in git(repo, 'diff', '--name-status', '-M', base).splitlines():
        parts = line.split('\t')
        status[parts[-1]] = parts[0][0]
    for f in git(repo, 'ls-files', '--others', '--exclude-standard').splitlines():
        status[f] = 'U'
    lines = {}
    for line in git(repo, 'diff', '--numstat', base).splitlines():
        add, rem, f = line.split('\t', 2)
        f = re.sub(r'\{[^}]* => ([^}]*)\}', r'\1', f).split(' => ')[-1]
        lines[f] = (int(add) if add.isdigit() else 0) + (int(rem) if rem.isdigit() else 0)
    for f, s in status.items():
        if s == 'U':
            try:
                lines[f] = sum(1 for _ in open(os.path.join(repo, f), errors='ignore'))
            except OSError:
                lines[f] = 0

    if path:
        status = {f: s for f, s in status.items() if f.startswith(path.rstrip('/') + '/') or f == path}

    composer = os.path.join(repo, 'composer.json')
    has_drupal = os.path.exists(composer) and 'drupal/core' in open(composer).read()
    next_roots = find_next_roots(repo)
    in_next = lambda f: any(r == '' or f.startswith(r + '/') for r in next_roots)
    show = lambda f: f'{label}/{f}' if label else f

    groups = {'drupal': [], 'nextjs': [], 'generic': [], 'a11y': [], 'infra': [], 'manifests': []}
    skipped, unclassified, stacks = [], [], {}
    for f, s in sorted(status.items()):
        entry = {'path': show(f), 'rel': f, 'repo': repo, 'base': base, 'status': s, 'lines': lines.get(f, 0)}
        name = os.path.basename(f)
        if (extra_exclude and extra_exclude.search(f)) or excluded_by_glob(f, globs):
            skipped.append(show(f))
            continue
        if name in MANIFESTS:
            groups['manifests'].append(entry)
            continue
        if CI.search(f):
            groups['infra'].append(entry)
            continue
        if EXCLUDE.search(f) or (has_drupal and DRUPAL_CORE.search(f)):
            skipped.append(show(f))
            continue
        if INFRA.search(f):
            groups['infra'].append(entry)
        if in_next(f) and (FRONT_EXT.search(f) or STYLE_EXT.search(f) or name.startswith('next.config') or f.endswith('.env.example')):
            groups['nextjs'].append(entry)
        elif has_drupal and f.endswith(('.yml', '.yaml')) and not DRUPAL_YML.search(f):
            skipped.append(show(f))
        elif has_drupal and (DRUPAL_EXT.search(f) or FRONT_EXT.search(f) or STYLE_EXT.search(f) or name == 'settings.php'):
            groups['drupal'].append(entry)
        elif INFRA.search(f):
            pass  # the infra finder covers it
        elif (GENERIC_EXT.search(f) or GENERIC_TEMPLATE.search(f)) and not GENERIC_TEST.search(f):
            groups['generic'].append({**entry, 'stack': stack_of(repo, f, stacks)})
            if re.search(r'\.(blade\.php|erb|jinja2?|j2)$', f):
                groups['a11y'].append(entry)
        else:
            skipped.append(show(f))
            if CODE.search(f) and not GENERIC_TEST.search(f):
                unclassified.append(show(f))
        if A11Y.search(f):
            groups['a11y'].append(entry)

    if stack:
        other = 'nextjs' if stack == 'drupal' else 'drupal'
        groups[other] = []
        groups['generic'] = []
        keep = {e['path'] for e in groups[stack]}
        groups['a11y'] = [e for e in groups['a11y'] if e['path'] in keep]
    untracked = sorted({e['path'] for g in groups.values() for e in g if e['status'] == 'U'})

    code = [e['rel'] for g in ('drupal', 'nextjs') for e in groups[g]]
    diff_text = git(repo, 'diff', base, '--', *code, check=False) if code else ''
    manifest_text = ''.join(open(os.path.join(repo, r, 'package.json'), errors='ignore').read() for r in next_roots)
    seam_markers = bool(SEAM_MARKERS.search(diff_text) or re.search(r'"next-drupal|drupal-jsonapi-params', manifest_text))

    versions, audits = {}, {}
    tag = lambda r: '/'.join(x for x in (label, r) if x) or '.'
    if has_drupal:
        versions[f'drupal/core{f" ({label})" if label else ""}'] = lock_version(os.path.join(repo, 'composer.lock'), 'drupal/core')
    for r in next_roots:
        lock = os.path.join(repo, r, 'package-lock.json')
        versions[f'next ({tag(r)})'] = lock_version(lock, 'next') or 'see package.json'
        versions[f'react ({tag(r)})'] = lock_version(lock, 'react') or 'see package.json'
    for m in groups['manifests']:
        d, name = os.path.join(repo, os.path.dirname(m['rel'])), os.path.basename(m['rel'])
        key = os.path.dirname(m['path']) or '.'
        if name in ('composer.json', 'composer.lock') and f'composer {key}' not in audits:
            audits[f'composer {key}'] = run_audit(['composer', 'audit', '--locked', '--format=json'], d)
        elif name == 'package-lock.json':
            audits[f'npm {key}'] = run_audit(['npm', 'audit', '--package-lock-only', '--json'], d)
        elif name == 'pnpm-lock.yaml':
            audits[f'pnpm {key}'] = run_audit(['pnpm', 'audit', '--json'], d)
        elif name == 'yarn.lock':
            audits[f'yarn {key}'] = 'yarn audit not run automatically; run it manually if the lockfile change matters'

    ctx = os.path.join(repo, PROJECT_CONTEXT)
    return {
        'repo': {'label': label or os.path.basename(repo), 'root': repo, 'base': base, 'baseLabel': base_label,
                 'branch': git(repo, 'branch', '--show-current', check=False) or 'detached', 'commits': commits},
        'groups': groups, 'skipped': skipped, 'unclassified': unclassified,
        'notes': [f'{label}: {n}' if label else n for n in notes],
        'versions': versions, 'audits': audits, 'seamMarkers': seam_markers, 'untracked': untracked,
        'projectRefs': [ctx] if os.path.exists(ctx) else [],
    }


def shard(entries):
    out, cur, n = [], [], 0
    for e in sorted(entries, key=lambda e: e['path']):
        if cur and n + e['lines'] > LINE_CAP:
            out.append(cur)
            cur, n = [], 0
        cur.append(e)
        n += e['lines']
    return out + ([cur] if cur else [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', help='diff base; applied to both repos with --pair (overrides config "base")')
    ap.add_argument('--only', default='security,performance,cache,logic,a11y')
    ap.add_argument('--stack', choices=['drupal', 'nextjs'])
    ap.add_argument('--deep', action='store_true')
    ap.add_argument('--path', help='limit the primary repo review to files under this path')
    ap.add_argument('--pair', help='second repo of a decoupled project (e.g. ../react); enables the seam finder across both')
    ap.add_argument('--intent', help='file with the acceptance criteria or spec (not the plan); read by the logic finder')
    ap.add_argument('--force-wide', action='store_true', help=f'allow more than {MAX_COMMITS} commits in the diff')
    ap.add_argument('--exclude', action='append', default=[], metavar='GLOB',
                    help='repo-relative glob to leave out (a directory name excludes everything under it); repeatable')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    root = git(os.getcwd(), 'rev-parse', '--show-toplevel')
    os.makedirs(a.out, exist_ok=True)
    intent = os.path.abspath(a.intent) if a.intent else None
    if intent and not os.path.isfile(intent):
        sys.exit(f'--intent file not found: {intent}')

    parts = []
    if a.pair:
        pair = git(os.path.abspath(a.pair), 'rev-parse', '--show-toplevel')
        if pair == root:
            sys.exit('--pair points at the same repo')
        display_root = os.path.commonpath([root, pair])
        parts.append(collect(root, a.base, a.path, a.stack, os.path.relpath(root, display_root), a.force_wide, a.exclude))
        parts.append(collect(pair, a.base, None, a.stack, os.path.relpath(pair, display_root), a.force_wide, a.exclude))
    else:
        display_root = root
        parts.append(collect(root, a.base, a.path, a.stack, '', a.force_wide, a.exclude))

    groups = {g: [e for p in parts for e in p['groups'][g]] for g in parts[0]['groups']}

    alias = {'perf': 'performance', 'wcag': 'a11y'}
    only = {alias.get(x.strip(), x.strip()) for x in a.only.split(',') if x.strip()}
    if 'a11y' not in only:
        groups['a11y'] = []
    if not only & {'security', 'performance', 'cache'}:
        groups['infra'] = []

    seam_markers = any(p['seamMarkers'] for p in parts) or bool(a.pair)
    seam_finder = bool(groups['drupal'] and groups['nextjs']) and bool(only & {'security', 'performance', 'cache', 'logic'})
    primary = parts[0]['repo']

    args = {
        'skillDir': SKILL_DIR,
        'repoRoot': display_root,
        'repos': [p['repo'] for p in parts],
        'outDir': os.path.abspath(a.out),
        'base': primary['base'],
        'baseLabel': ' + '.join(f"{p['repo']['label']}: {p['repo']['baseLabel']}" for p in parts) if a.pair else primary['baseLabel'],
        'notes': [n for p in parts for n in p['notes']],
        'only': sorted(only),
        'deep': a.deep,
        'intent': intent,
        'projectRefs': [r for p in parts for r in p['projectRefs']],
        'shards': {
            'drupal': shard(groups['drupal']),
            'nextjs': shard(groups['nextjs']),
            # One stack per generic shard, so each finder reads one row of the per-stack signals table.
            'generic': [s for st in sorted({e['stack'] for e in groups['generic']})
                        for s in shard([e for e in groups['generic'] if e['stack'] == st])],
            'a11y': shard(groups['a11y']),
            'infra': shard(groups['infra']),
        },
        'seamFinder': seam_finder,
        'decoupledRef': seam_markers,
        'manifests': [m['path'] for m in groups['manifests']],
        'infra': [m['path'] for m in groups['infra']],
        'versions': {k: v for p in parts for k, v in p['versions'].items()},
        'audits': {k: v for p in parts for k, v in p['audits'].items()},
        'skipped': [s for p in parts for s in p['skipped']],
        'unclassified': [s for p in parts for s in p['unclassified']],
        'stats': {g: len(v) for g, v in groups.items()},
    }
    sh = args['shards']
    stacks = {**{f'{g}-{i + 1}': g for g in ('drupal', 'nextjs') for i in range(len(sh[g]))},
              **{f'generic-{i + 1}': s[0]['stack'] for i, s in enumerate(sh['generic'])}}
    path = os.path.join(a.out, 'args.json')
    json.dump(args, open(path, 'w'), indent=1)
    print(json.dumps({'argsFile': path, 'base': args['baseLabel'], 'repos': args['repos'], 'notes': args['notes'],
                      'stats': args['stats'], 'shards': {k: len(v) for k, v in args['shards'].items()}, 'stacks': stacks,
                      'notCovered': args['unclassified'],
                      'seamFinder': seam_finder, 'decoupledRef': seam_markers, 'intent': intent,
                      'projectRefs': args['projectRefs'], 'versions': args['versions'],
                      'audits': list(args['audits']), 'skipped': len(args['skipped'])}, indent=1))
    # Workflow only loads a scriptPath from a readable directory; ~/.claude/skills is not one.
    script = os.path.join(args['outDir'], 'review.workflow.js')
    shutil.copyfile(os.path.join(SKILL_DIR, 'review.workflow.js'), script)
    untracked = [u for p in parts for u in p['untracked']]
    print(f"untracked included: {', '.join(untracked) or 'none'}")
    print(f'workflow: {script}')


if __name__ == '__main__':
    main()
