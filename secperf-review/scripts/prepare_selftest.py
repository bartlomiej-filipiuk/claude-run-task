#!/usr/bin/env python3
"""Offline check of prepare.py on a throwaway git repo. Run: python3 scripts/prepare_selftest.py"""
import json
import os
import subprocess
import sys
import tempfile

PREPARE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prepare.py')
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(cwd, *cmd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


with tempfile.TemporaryDirectory() as tmp:
    repo, out = os.path.join(tmp, 'repo'), os.path.join(tmp, 'out')
    os.makedirs(repo)
    sh(repo, 'git', 'init', '-q')
    sh(repo, 'git', 'config', 'user.email', 't@example.com')
    sh(repo, 'git', 'config', 'user.name', 't')
    write(repo, 'composer.json', '{"require": {"drupal/core": "^10"}}')
    write(repo, 'README.md', 'x\n')
    sh(repo, 'git', 'add', '-A')
    sh(repo, 'git', 'commit', '-qm', 'init')

    write(repo, 'terraform/main.tf', 'resource "aws_s3_bucket" "b" {}\n')
    write(repo, 'terraform/modules/viewer-response/data/functions/viewer-response/main.js', 'function handler(e) { return e }\n')
    write(repo, 'patches/token/fix.patch', '--- a/x.php\n+++ b/x.php\n')
    write(repo, 'docroot/modules/custom/m/m.module', '<?php\n')
    write(repo, 'scripts-tmp/audit.php', '<?php\n')
    write(repo, 'reports/run1/index.php', '<?php\n')

    r = subprocess.run([sys.executable, PREPARE, '--base', 'HEAD', '--out', out,
                        '--exclude', 'scripts-tmp', '--exclude', 'reports/*'],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    args = json.load(open(os.path.join(out, 'args.json')))
    flat = lambda k: [e['path'] for s in args['shards'][k] for e in s]

    # A Laravel repo: no drupal/core, so its PHP must land in the generic shard with a stack label.
    lrepo, lout = os.path.join(tmp, 'laravel'), os.path.join(tmp, 'lout')
    os.makedirs(lrepo)
    sh(lrepo, 'git', 'init', '-q')
    sh(lrepo, 'git', 'config', 'user.email', 't@example.com')
    sh(lrepo, 'git', 'config', 'user.name', 't')
    write(lrepo, 'composer.json', '{"require": {"laravel/framework": "^11.0"}}')
    write(lrepo, 'artisan', '#!/usr/bin/env php\n')
    sh(lrepo, 'git', 'add', '-A')
    sh(lrepo, 'git', 'commit', '-qm', 'init')
    write(lrepo, 'app/Http/Controllers/PostController.php', '<?php\n')
    write(lrepo, 'resources/views/posts/show.blade.php', '<h1>{{ $post->title }}</h1>\n')
    write(lrepo, 'tests/Feature/PostTest.php', '<?php\n')
    write(lrepo, 'bin/deploy.sh', 'echo deploy\n')
    lr = subprocess.run([sys.executable, PREPARE, '--base', 'HEAD', '--out', lout], cwd=lrepo, capture_output=True, text=True)
    assert lr.returncode == 0, lr.stderr
    largs = json.load(open(os.path.join(lout, 'args.json')))
    lsummary = json.loads(lr.stdout[:lr.stdout.index('\nuntracked included:')])
    generic = {e['path']: e['stack'] for s in largs['shards']['generic'] for e in s}

    checks = {
        'drupal module file goes to the drupal shard': 'docroot/modules/custom/m/m.module' in flat('drupal'),
        'drupal repo has no generic shard': args['shards']['generic'] == [],
        'laravel controller goes to the generic shard with stack laravel':
            generic.get('app/Http/Controllers/PostController.php') == 'laravel',
        'blade template goes to generic (laravel) and a11y':
            generic.get('resources/views/posts/show.blade.php') == 'laravel'
            and any(e['path'] == 'resources/views/posts/show.blade.php' for s in largs['shards']['a11y'] for e in s),
        'laravel test file stays out of scope': 'tests/Feature/PostTest.php' in largs['skipped']
            and 'tests/Feature/PostTest.php' not in generic,
        'laravel repo has no drupal or nextjs shard': largs['shards']['drupal'] == [] and largs['shards']['nextjs'] == [],
        'summary lists the stack per shard': lsummary['stacks'] == {'generic-1': 'laravel'},
        'unclassified code is reported as not covered': largs['unclassified'] == ['bin/deploy.sh']
            and lsummary['notCovered'] == ['bin/deploy.sh'],
        '.tf goes to the infra shard': 'terraform/main.tf' in flat('infra'),
        'edge function JS goes to the infra shard':
            'terraform/modules/viewer-response/data/functions/viewer-response/main.js' in flat('infra'),
        '.patch goes to the drupal shard': 'patches/token/fix.patch' in flat('drupal'),
        '--exclude dir name drops untracked scratch files': 'scripts-tmp/audit.php' in args['skipped'],
        '--exclude glob drops report dir': 'reports/run1/index.php' in args['skipped'],
        'untracked included line lists in-scope untracked files':
            any(l.startswith('untracked included: ') and 'docroot/modules/custom/m/m.module' in l
                and 'scripts-tmp' not in l for l in lines),
        'last line is the workflow path': lines[-1] == f"workflow: {os.path.join(out, 'review.workflow.js')}",
        'workflow script copied verbatim':
            open(os.path.join(out, 'review.workflow.js')).read() == open(os.path.join(SKILL_DIR, 'review.workflow.js')).read(),
    }
    for name, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    print('\n'.join(l for l in lines if l.startswith(('untracked included:', 'workflow:'))))
    if not all(checks.values()):
        sys.exit(1)
    print('prepare selftest OK')
