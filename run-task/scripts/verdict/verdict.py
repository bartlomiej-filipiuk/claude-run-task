#!/usr/bin/env python3
"""Gate record and verdict ceiling for one run-task task.

Every gate result is appended to <T>/gates.jsonl with the commit of every touched repo, so a result always says
which code it describes. `check` computes the highest verdict the records allow: a missing gate, or a final gate
that ran on another commit than HEAD, means the verdict cannot be written yet.

  verdict.py init   <T> --repo <path> [--repo <path>] [--task T1 --task T2 ...]
  verdict.py record <T> --task T2|final --gate <name> [--gate <name>] [--repo <path>]
                        --result pass|fail|baseline|skip|not-covered [--detail "<text>"] [--accepted N]
  verdict.py check  <T>
  verdict.py yield  <T>

Exit codes of check: 0 GO, 1 GO with conditions, 3 NO-GO, 4 INCOMPLETE; 2 = usage or data error (every command).
"""
import argparse
import json
import os
import subprocess
import sys

PER_TASK = ['review', 'revert', 'secperf', 'challenge', 'verifier']
FINAL_BRANCH = ['review', 'secperf', 'intent', 'challenge', 'visual', 'change-map', 'qa-walk']
FINAL_REPO = ['lint', 'types', 'unit', 'integration', 'e2e', 'build', 'smoke']
# Agent reviews may describe an older commit when the final reviewer's later round reviewed the delta to HEAD.
AGENT_GATES = {'secperf', 'intent', 'visual'}
# A `not-covered` result here leaves a check to a human: the verdict is at most GO with conditions.
CONDITION_IF_NOT_COVERED = set(FINAL_REPO) | {'qa-walk'}
KNOWN = set(PER_TASK) | set(FINAL_BRANCH) | set(FINAL_REPO) | {'scope', 'approach', 'proof-steps'}
RESULTS = ['pass', 'fail', 'baseline', 'skip', 'not-covered']


class DataError(Exception):
    pass


def git(repo, *args, check=True):
    r = subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise DataError(f'git {" ".join(args)} failed in {repo}: {r.stderr.strip()}')
    return r


def state(repos):
    heads, dirty = {}, {}
    for repo in repos:
        heads[repo] = git(repo, 'rev-parse', 'HEAD').stdout.strip()
        dirty[repo] = bool(git(repo, 'status', '--porcelain', '--untracked-files=no').stdout.strip())
    return heads, dirty


def load(tdir):
    path = os.path.join(tdir, 'gates.jsonl')
    if not os.path.exists(path):
        raise DataError(f'{path} does not exist: run init first')
    meta, recs = None, []
    with open(path) as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise DataError(f'gates.jsonl line {n}: {e}')
            if 'meta' in row:
                meta = row['meta']
            else:
                row['_n'] = n
                recs.append(row)
    if meta is None:
        raise DataError('gates.jsonl has no init line')
    return meta, recs


def append(tdir, row):
    with open(os.path.join(tdir, 'gates.jsonl'), 'a') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')


def cmd_init(a):
    repos = [os.path.abspath(r) for r in a.repo]
    for r in repos:
        git(r, 'rev-parse', 'HEAD')
    os.makedirs(a.tdir, exist_ok=True)
    append(a.tdir, {'meta': {'repos': repos, 'tasks': a.task or []}})
    print(f'init: {len(repos)} repo(s), {len(a.task or [])} task(s)')


def cmd_record(a):
    meta, _ = load(a.tdir)
    repo = os.path.abspath(a.repo) if a.repo else None
    if repo and repo not in meta['repos']:
        raise DataError(f'--repo {repo} is not a repo of this task: {meta["repos"]}')
    if a.task != 'final' and meta['tasks'] and a.task not in meta['tasks']:
        raise DataError(f'--task {a.task} is not in the plan: {meta["tasks"]} (run init again to add it)')
    if a.result in ('skip', 'not-covered') and not (a.detail or '').strip():
        raise DataError(f'--result {a.result} needs --detail with the reason')
    for g in a.gate:
        if g not in KNOWN:
            raise DataError(f'unknown gate {g!r}; known: {sorted(KNOWN)}')
        per_repo = a.task == 'final' and g in FINAL_REPO
        if per_repo and not repo:
            raise DataError(f'final gate {g} runs per repo: add --repo')
        if repo and not per_repo:
            raise DataError(f'gate {g} for task {a.task} is not per repo: drop --repo')
    heads, dirty = state(meta['repos'])
    for g in a.gate:
        append(a.tdir, {'task': a.task, 'gate': g, 'repo': repo, 'result': a.result, 'detail': a.detail or '',
                        'accepted': a.accepted, 'heads': heads, 'dirty': dirty})
    print(f'recorded {", ".join(a.gate)} = {a.result} for {a.task}')


def evaluate(meta, recs):
    now, now_dirty = state(meta['repos'])
    latest = {}
    for r in recs:
        latest[(r['task'], r['gate'], r.get('repo'))] = r
    missing, stale, fails, conditions, notes = [], [], [], [], []

    tasks = list(meta['tasks']) or sorted({r['task'] for r in recs if r['task'] != 'final'})
    for t in tasks:
        missing += [f'{t} {g}' for g in PER_TASK if (t, g, None) not in latest]
    missing += [f'final {g}' for g in FINAL_BRANCH if ('final', g, None) not in latest]
    for repo in meta['repos']:
        missing += [f'final {g} ({repo})' for g in FINAL_REPO if ('final', g, repo) not in latest]
    for repo, d in now_dirty.items():
        if d:
            stale.append(f'uncommitted changes in {repo}: commit them, then run the final gates again')

    def fresh(r):
        return r['heads'] == now and not any(r['dirty'].values())

    def ancestor(r):
        return all(git(repo, 'merge-base', '--is-ancestor', r['heads'].get(repo, ''), now[repo], check=False)
                   .returncode == 0 for repo in meta['repos'])

    review = latest.get(('final', 'review', None))
    for key, r in latest.items():
        task, g, repo = key
        label = f'{task} {g}' + (f' ({repo})' if repo else '')
        if r['result'] == 'fail':
            fails.append(f'{label}: {r["detail"]}' if r['detail'] else label)
        if task != 'final':
            continue
        if not fresh(r):
            if (g in AGENT_GATES and review and fresh(review) and review['_n'] > r['_n'] and ancestor(r)):
                notes.append(f'{label} ran on an earlier commit; the delta to HEAD was reviewed by the final review '
                             f'round recorded after it')
            else:
                stale.append(f'{label} describes another commit than HEAD or uncommitted code: run it again')
        if r['result'] == 'not-covered' and g in CONDITION_IF_NOT_COVERED:
            conditions.append(f'{label}: not covered: {r["detail"]}')

    if missing or stale:
        ceiling = 'INCOMPLETE'
    elif fails:
        ceiling = 'NO-GO'
    elif conditions:
        ceiling = 'GO with conditions'
    else:
        ceiling = 'GO'
    return {'ceiling': ceiling, 'missing': missing, 'stale': stale, 'fail': fails, 'conditions': conditions,
            'notes': notes}


def cmd_check(a):
    meta, recs = load(a.tdir)
    res = evaluate(meta, recs)
    print(f'ceiling: {res["ceiling"]}')
    for k in ('missing', 'stale', 'fail', 'conditions', 'notes'):
        for item in res[k]:
            print(f'{k}: {item}')
    print(json.dumps(res))
    return {'GO': 0, 'GO with conditions': 1, 'NO-GO': 3, 'INCOMPLETE': 4}[res['ceiling']]


def cmd_yield(a):
    _, recs = load(a.tdir)
    runs, accepted = {}, {}
    for r in recs:
        if r.get('accepted') is None:  # a re-record after a fix round, not a run of the pass
            continue
        runs[r['gate']] = runs.get(r['gate'], 0) + 1
        accepted[r['gate']] = accepted.get(r['gate'], 0) + (r.get('accepted') or 0)
    seen = list(dict.fromkeys(g for g in PER_TASK + FINAL_BRANCH + FINAL_REPO + sorted(KNOWN) if g in runs))
    print('yield: ' + (', '.join(f'{g} {accepted[g]}/{runs[g]}' for g in seen) or 'none'))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('init')
    s.add_argument('tdir')
    s.add_argument('--repo', action='append', required=True)
    s.add_argument('--task', action='append')
    s = sub.add_parser('record')
    s.add_argument('tdir')
    s.add_argument('--task', required=True)
    s.add_argument('--gate', action='append', required=True)
    s.add_argument('--repo')
    s.add_argument('--result', required=True, choices=RESULTS)
    s.add_argument('--detail')
    s.add_argument('--accepted', type=int, default=None)
    for name in ('check', 'yield'):
        sub.add_parser(name).add_argument('tdir')
    a = p.parse_args(argv)
    a.tdir = os.path.abspath(a.tdir)
    try:
        return {'init': cmd_init, 'record': cmd_record, 'check': cmd_check, 'yield': cmd_yield}[a.cmd](a) or 0
    except DataError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
