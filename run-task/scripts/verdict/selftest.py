#!/usr/bin/env python3
"""Offline check of verdict.py on a throwaway git repo. Run: python3 scripts/verdict/selftest.py"""
import json
import os
import subprocess
import sys
import tempfile

V = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verdict.py')
results = []


def run(*args):
    r = subprocess.run([sys.executable, V, *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def sh(cwd, *cmd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def commit(repo, name):
    with open(os.path.join(repo, name), 'w') as f:
        f.write(name)
    sh(repo, 'git', 'add', name)
    sh(repo, 'git', 'commit', '-qm', name)


def check(t):
    code, out, _ = run('check', t)
    return code, json.loads(out.strip().splitlines()[-1])


def expect(name, ok):
    results.append((name, ok))


def record_all(t, repo, result='pass'):
    for task in ('T1',):
        run('record', t, '--task', task, '--result', result, *sum([['--gate', g] for g in
            ('review', 'revert', 'secperf', 'challenge', 'verifier')], []))
    run('record', t, '--task', 'final', '--result', result, *sum([['--gate', g] for g in
        ('secperf', 'intent', 'challenge', 'visual', 'change-map', 'qa-walk')], []))
    run('record', t, '--task', 'final', '--repo', repo, '--result', result, *sum([['--gate', g] for g in
        ('lint', 'types', 'unit', 'integration', 'e2e', 'build', 'smoke')], []))
    run('record', t, '--task', 'final', '--gate', 'review', '--result', result)


with tempfile.TemporaryDirectory() as tmp:
    repo = os.path.join(tmp, 'repo')
    os.makedirs(repo)
    sh(repo, 'git', 'init', '-q')
    sh(repo, 'git', 'config', 'user.email', 't@example.com')
    sh(repo, 'git', 'config', 'user.name', 't')
    commit(repo, 'a')

    t = os.path.join(tmp, 'tasks', 'X-1')
    expect('init', run('init', t, '--repo', repo, '--task', 'T1')[0] == 0)

    code, res = check(t)
    expect('nothing recorded = INCOMPLETE with missing gates', code == 4 and 'T1 review' in res['missing']
           and any(m.startswith('final lint') for m in res['missing']))

    expect('unknown gate is refused', run('record', t, '--task', 'T1', '--gate', 'reveiw', '--result', 'pass')[0] == 2)
    expect('per-repo final gate without --repo is refused',
           run('record', t, '--task', 'final', '--gate', 'unit', '--result', 'pass')[0] == 2)
    expect('branch gate with --repo is refused',
           run('record', t, '--task', 'final', '--gate', 'intent', '--repo', repo, '--result', 'pass')[0] == 2)
    expect('skip without a reason is refused',
           run('record', t, '--task', 'T1', '--gate', 'revert', '--result', 'skip')[0] == 2)
    expect('task outside the plan is refused',
           run('record', t, '--task', 'T9', '--gate', 'review', '--result', 'pass')[0] == 2)

    record_all(t, repo)
    code, res = check(t)
    expect('everything passed at HEAD = GO', code == 0 and res['ceiling'] == 'GO')

    commit(repo, 'b')
    code, res = check(t)
    expect('a commit after the gates = INCOMPLETE, cheap gates stale', code == 4
           and any('final unit' in s for s in res['stale']) and any('final review' in s for s in res['stale']))

    # Fix wave: cheap gates and the final review round again at HEAD; secperf, intent and visual stay on the old commit.
    run('record', t, '--task', 'final', '--repo', repo, '--result', 'pass', *sum([['--gate', g] for g in
        ('lint', 'types', 'unit', 'integration', 'e2e', 'build', 'smoke')], []))
    run('record', t, '--task', 'final', '--result', 'pass', '--gate', 'challenge', '--gate', 'change-map',
        '--gate', 'qa-walk', '--gate', 'review')
    code, res = check(t)
    expect('agent reviews on an ancestor, delta reviewed later = GO with a note', code == 0
           and any('final secperf' in n for n in res['notes']))

    with open(os.path.join(repo, 'a'), 'w') as f:
        f.write('changed')
    code, res = check(t)
    expect('uncommitted tracked change now = INCOMPLETE', code == 4
           and any('uncommitted' in s for s in res['stale']))
    sh(repo, 'git', 'checkout', '-q', 'a')

    run('record', t, '--task', 'final', '--repo', repo, '--gate', 'e2e', '--result', 'not-covered',
        '--detail', 'no e2e command')
    run('record', t, '--task', 'final', '--gate', 'visual', '--result', 'not-covered', '--detail', 'no front end')
    code, res = check(t)
    expect('not-covered profile gate = GO with conditions; not-covered visual is no condition', code == 1
           and len(res['conditions']) == 1 and 'e2e' in res['conditions'][0])

    run('record', t, '--task', 'final', '--gate', 'qa-walk', '--result', 'fail', '--detail', 'S2 fails')
    code, res = check(t)
    expect('a failing gate = NO-GO', code == 3 and res['fail'] == [f'final qa-walk: S2 fails'])

    run('record', t, '--task', 'final', '--gate', 'qa-walk', '--result', 'pass')
    code, res = check(t)
    expect('the latest record of a gate wins', code == 1 and not res['fail'])

    # A new commit after the final review: agent reviews are no longer covered.
    commit(repo, 'c')
    run('record', t, '--task', 'final', '--repo', repo, '--result', 'pass', *sum([['--gate', g] for g in
        ('lint', 'types', 'unit', 'integration', 'e2e', 'build', 'smoke')], []))
    run('record', t, '--task', 'final', '--result', 'pass', '--gate', 'challenge', '--gate', 'change-map',
        '--gate', 'qa-walk')
    code, res = check(t)
    expect('agent review without a later fresh final review = INCOMPLETE', code == 4
           and any('final secperf' in s for s in res['stale']) and any('final review' in s for s in res['stale']))

    t2 = os.path.join(tmp, 'tasks', 'X-2')
    run('init', t2, '--repo', repo)
    run('record', t2, '--task', 'T1', '--gate', 'review', '--result', 'fail', '--accepted', '3')
    run('record', t2, '--task', 'T1', '--gate', 'review', '--result', 'pass')
    run('record', t2, '--task', 'final', '--gate', 'review', '--result', 'pass', '--accepted', '0')
    run('record', t2, '--task', 'T1', '--gate', 'secperf', '--result', 'pass', '--accepted', '1')
    run('record', t2, '--task', 'T1', '--gate', 'challenge', '--result', 'not-covered', '--detail', 'go')
    code, out, _ = run('yield', t2)
    expect('yield counts runs that carry --accepted, not re-records or not-covered',
           out.strip() == 'yield: review 3/2, secperf 1/1')

for name, ok in results:
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
if not all(ok for _, ok in results):
    sys.exit(1)
print(f'verdict selftest OK ({len(results)}/{len(results)})')
