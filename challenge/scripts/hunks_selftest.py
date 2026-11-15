#!/usr/bin/env python3
"""Build throwaway git repos and check hunks.py on the cases it once got wrong.

Drupal repo: a binary fixture without NUL bytes added with `git add -N` (used to crash the decoder), composer
`extra.patches` entries removed / swapped / added, a deleted, a changed and a swapped `.patch` file, a new one,
and one removed access check as the known positive (score pinned to the pre-generic value).
Polyglot repo: Laravel, Django, Go and Rust code from prepare's `generic` group, a pytest file, a Next.js route
handler (score pinned to the pre-generic value) and a shell script nothing classifies.
Exit 0 when every expectation holds.

  python3 hunks_selftest.py [--dir <empty dir>] [--script <hunks.py>]
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

PAD = ''.join(f'            "drupal/pad{i}": {{\n                "Pad {i}": "https://example.org/pad-{i}.patch"\n            }},\n'
              for i in range(3))


def composer(core, swap, webform):
    return ('{\n    "name": "x/site",\n    "require": {\n        "drupal/core": "^10"\n    },\n'
            '    "extra": {\n        "patches": {\n'
            f'            "drupal/core": {{\n{core}            }},\n{PAD}'
            f'            "drupal/swap": {{\n{swap}            }},\n{PAD.replace("pad", "pod")}'
            f'            "drupal/webform": {{\n{webform}            }}\n'
            '        }\n    }\n}\n')


KEEP = '                "Keep K": "https://example.org/keep.patch"\n'
BASE_COMPOSER = composer(
    '                "Remove A": "./patches/core/a.patch",\n' + KEEP,
    '                "Swap S": "https://example.org/swap-old.patch"\n',
    '                "Fix W": "./patches/webform/w.patch"\n')
NEW_COMPOSER = composer(
    KEEP,
    '                "Swap S": "https://example.org/swap-new.patch"\n',
    '                "Fix W": "./patches/webform/w.patch",\n                "Add C": "https://example.org/add-c.patch"\n')


def patch(f, old, new):
    return (f'diff --git a/{f} b/{f}\n--- a/{f}\n+++ b/{f}\n@@ -1,3 +1,3 @@\n'
            f' <?php\n-{old}\n+{new}\n }}\n')


BASE_PHP = """<?php

namespace Drupal\\foo\\Controller;

class FooController {

  public function view($account) {
    if (!$account->hasPermission('administer foo')) {
      throw new AccessDeniedHttpException();
    }
    return ['#markup' => 'ok'];
  }

}
"""
PHP = 'docroot/modules/custom/foo/src/Controller/FooController.php'
PNG = 'docroot/modules/custom/foo/tests/fixtures/logo.png'


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb' if isinstance(text, bytes) else 'w') as f:
        f.write(text)


def git(repo, *a):
    subprocess.run(['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@t', *a], check=True, capture_output=True)


HOOK = 'web/modules/custom/foo/src/Hook/FooHooks.php'
HOOK_SRC = """<?php

namespace Drupal\\foo\\Hook;

use Drupal\\Core\\Hook\\Attribute\\Hook;

final class FooHooks {

  #[Hook('node_insert')]
  public function nodeInsert($node): void {
    \\Drupal::logger('foo')->notice('inserted');
  }

}
"""


def build(repo):
    git(repo, 'init', '-q')
    git(repo, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    write(repo, 'composer.json', BASE_COMPOSER)
    write(repo, PHP, BASE_PHP)
    write(repo, HOOK, HOOK_SRC)
    write(repo, 'patches/core/a.patch', patch('src/A.php', '$a = 1;', '$a = 2;'))
    write(repo, 'patches/webform/w.patch', patch('src/W.php', '$w = 1;', '$w = 2;'))
    write(repo, 'patches/swap/s-1.patch', patch('src/LongEnoughName.php', '$s = 1;', '$s = 2;'))
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'base')
    git(repo, 'checkout', '-qb', 'feature')
    write(repo, 'composer.json', NEW_COMPOSER)
    write(repo, PHP, BASE_PHP.replace("""    if (!$account->hasPermission('administer foo')) {
      throw new AccessDeniedHttpException();
    }
""", ''))
    write(repo, HOOK, HOOK_SRC.replace("  #[Hook('node_insert')]\n", ''))
    os.remove(os.path.join(repo, 'patches/core/a.patch'))
    write(repo, 'patches/webform/w.patch', patch('src/W.php', '$w = 1;', '$w = 3;'))
    # Swapped for a reroll: git pairs the two files as a rename with changes.
    os.remove(os.path.join(repo, 'patches/swap/s-1.patch'))
    write(repo, 'patches/swap/s-2.patch', patch('src/LongEnoughName.php', '$s = 1;', '$s = 3;'))
    write(repo, 'patches/new/n.patch', patch('lib/other/thing.js', 'let n = 1;', 'let n = 2;'))
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'feature')
    # PNG signature plus high bytes, no NUL: git diffs it as text, and it is not valid UTF-8.
    write(repo, PNG, b'\x89PNG\r\n\x1a\n' + bytes(range(1, 256)) * 4)
    git(repo, 'add', '-N', PNG)


LARAVEL = 'laravel/app/Http/Controllers/PostController.php'
LARAVEL_PHP = """<?php

namespace App\\Http\\Controllers;

use App\\Models\\Post;
use Illuminate\\Http\\Request;

class PostController extends Controller
{
    public function update(Request $request, Post $post)
    {
        $this->authorize('update', $post);

        $post->update($request->validated());

        return redirect()->route('posts.show', $post);
    }
}
"""
DJANGO = 'django/blog/views.py'
DJANGO_PY = """from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect

from .models import Post


@permission_required('blog.change_post')
def publish(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.published = True
    post.save()
    return redirect(post)
"""
PYTEST = 'django/blog/tests/test_views.py'
PYTEST_PY = """import pytest


@pytest.mark.django_db
def test_publish_requires_permission(client, user):
    client.force_login(user)
    response = client.post('/posts/1/publish/')
    assert response.status_code == 403
"""
GO = 'go/internal/api/handler.go'
GO_SRC = """package api

import (
\t"net/http"

\t"example.com/app/internal/auth"
\t"example.com/app/internal/store"
)

type Handler struct{ Store *store.Store }

func (h *Handler) DeletePost(w http.ResponseWriter, r *http.Request) {
\tuser, ok := auth.UserFromContext(r.Context())
\tif !ok || !user.IsAdmin {
\t\thttp.Error(w, "forbidden", http.StatusForbidden)
\t\treturn
\t}
\tif err := h.Store.DeletePost(r.Context(), r.PathValue("id")); err != nil {
\t\thttp.Error(w, err.Error(), http.StatusInternalServerError)
\t\treturn
\t}
\tw.WriteHeader(http.StatusNoContent)
}
"""
GO_AUTH = """\tuser, ok := auth.UserFromContext(r.Context())
\tif !ok || !user.IsAdmin {
\t\thttp.Error(w, "forbidden", http.StatusForbidden)
\t\treturn
\t}
"""
RUST_MODEL = 'rust/src/model.rs'
RUST_MODEL_SRC = '#[derive(Debug)]\npub struct Post {\n    pub id: u64,\n    pub title: String,\n}\n'
RUST_LIB = 'rust/src/lib.rs'
RUST_LIB_SRC = ('#[derive(Debug)]\npub struct Counter(pub u32);\n\n#[cfg(test)]\nmod tests {\n    #[test]\n'
                '    fn counts() {\n        assert_eq!(super::Counter(1).0, 1);\n    }\n}\n')
NEXT = 'web/app/api/posts/[id]/route.ts'
NEXT_TS = """import { NextResponse } from 'next/server'
import { auth } from '@/auth'
import { db } from '@/db'

export async function DELETE(req: Request, { params }: { params: { id: string } }) {
  const session = await auth()
  // Only admins may delete posts.
  if (!session?.user?.isAdmin) {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 })
  }
  await db.post.delete({ where: { id: params.id } })
  return NextResponse.json({ ok: true })
}
"""
NEXT_AUTH = """  // Only admins may delete posts.
  if (!session?.user?.isAdmin) {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 })
  }
"""
SHELL = 'scripts/deploy.sh'


def build_polyglot(repo):
    git(repo, 'init', '-q')
    git(repo, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    write(repo, 'laravel/composer.json', '{"require": {"laravel/framework": "^11.0"}}\n')
    write(repo, 'laravel/artisan', '#!/usr/bin/env php\n<?php\n')
    write(repo, 'django/manage.py', 'import django\n')
    write(repo, 'django/requirements.txt', 'Django==5.1\npytest-django\n')
    write(repo, 'go/go.mod', 'module example.com/app\n\ngo 1.22\n')
    write(repo, 'rust/Cargo.toml', '[package]\nname = "app"\nversion = "0.1.0"\n')
    write(repo, 'web/package.json', '{"dependencies": {"next": "15.1.0", "react": "19.0.0"}}\n')
    write(repo, 'web/next.config.js', 'module.exports = {}\n')
    for rel, text in ((LARAVEL, LARAVEL_PHP), (DJANGO, DJANGO_PY), (PYTEST, PYTEST_PY), (GO, GO_SRC),
                      (RUST_MODEL, RUST_MODEL_SRC), (RUST_LIB, RUST_LIB_SRC), (NEXT, NEXT_TS), (SHELL, 'rm -rf /srv/app/cache\n')):
        write(repo, rel, text)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'base')
    git(repo, 'checkout', '-qb', 'feature')
    write(repo, LARAVEL, LARAVEL_PHP.replace("        $this->authorize('update', $post);\n\n", ''))
    write(repo, DJANGO, DJANGO_PY.replace("@permission_required('blog.change_post')\n", ''))
    write(repo, PYTEST, PYTEST_PY.replace('    assert response.status_code == 403\n', ''))
    write(repo, GO, GO_SRC.replace(GO_AUTH, ''))
    write(repo, RUST_MODEL, RUST_MODEL_SRC.replace('#[derive(Debug)]\n', ''))
    write(repo, RUST_LIB, RUST_LIB_SRC.replace('#[derive(Debug)]\n', '').replace('    #[test]\n', '    #[test]\n    #[ignore]\n'))
    write(repo, NEXT, NEXT_TS.replace(NEXT_AUTH, ''))
    write(repo, SHELL, 'rm -rf /srv/app/cache/*\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'feature')


def run(script, repo):
    out = os.path.join(repo, '.out')
    r = subprocess.run([sys.executable, script, '--base', 'main', '--cap', '20', '--out', out],
                       cwd=repo, capture_output=True, text=True)
    print(f'repo: {repo}\nexit: {r.returncode}')
    if r.returncode:
        print(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'no stderr')
        sys.exit(1)
    return json.load(open(os.path.join(out, 'hunks.json'))), out


def show(data):
    for c in data['selected']:
        print(f"selected {c['file']} old line {c['old_line']}: score {c['score']}, {', '.join(c['signals'])}"
              f"{' (blocker)' if c['blocker'] else ''}")
    for c in data['unselected']:
        print(f"unselected {c['file']} old line {c['old_line']}: score {c['score']}, {', '.join(c['signals'])}")


def polyglot_checks(script, repo):
    data, _ = run(script, repo)
    show(data)
    sel = {c['file']: c for c in data['selected']}
    seen = list(sel) + [c['file'] for c in data['unselected']]
    blocker = lambda f, label: f in sel and sel[f]['blocker'] and label in sel[f]['signals']
    # Unit check on the scorer itself: the same removed attribute under the Rust row and the legacy row.
    spec = importlib.util.spec_from_file_location('hunks_under_test', script)
    hunks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hunks)
    derive = {'path': RUST_MODEL, 'old': 1, 'new': 1, 'lines': ['@@ -1,2 +1,1 @@', '-#[derive(Debug)]', ' pub struct Post {']}
    rust_row = hunks.row_for(RUST_MODEL, True)
    return {
        'laravel: removed $this->authorize() selected as blocker': blocker(LARAVEL, 'access/permission/sanitise check'),
        'django: removed @permission_required selected as blocker': blocker(DJANGO, 'access/permission/sanitise check'),
        'go: removed auth check selected as blocker': blocker(GO, 'access/permission/sanitise check'),
        'pytest: removed assert selected as blocker': blocker(PYTEST, 'assertion removed') and sel[PYTEST]['test_file'],
        'rust: removed #[derive(Debug)] alone is not a candidate': RUST_MODEL not in seen,
        'rust: #[derive(Debug)] is code for the rust row and the legacy row':
            hunks.score(derive, False, False, set(), set(), None, rust_row)[3] == []
            and hunks.score(derive, False, False, set(), set(), None)[3] == [],
        'rust: #[ignore] selected without the removed-comment bonus': RUST_LIB in sel and sel[RUST_LIB]['score'] == 4
            and sel[RUST_LIB]['removed_comments'] == [] and 'removed comment explains it' not in sel[RUST_LIB]['signals'],
        'next.js: route handler hunk scored as before (9, comment bonus, not blocker)': NEXT in sel
            and (sel[NEXT]['score'], sel[NEXT]['signals'], sel[NEXT]['blocker'])
            == (9, ['guard condition', 'removed comment explains it', 'return'], False),
        'shell script reported as not covered': data.get('not_covered') == [SHELL],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir')
    ap.add_argument('--script', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hunks.py'))
    a = ap.parse_args()
    repo = os.path.abspath(a.dir) if a.dir else tempfile.mkdtemp(prefix='hunks-selftest-')
    os.makedirs(repo, exist_ok=True)
    build(repo)
    data, out = run(a.script, repo)
    sel = data['selected']
    for c in sel:
        print(f"selected {c['file']} old line {c['old_line']}: score {c['score']}, {', '.join(c['signals'])}"
              f"{' (blocker)' if c['blocker'] else ''}")
    for c in data['unselected']:
        print(f"unselected {c['file']} old line {c['old_line']}: score {c['score']}, {', '.join(c['signals'])}")
    removed = lambda c, s: any(l.startswith('-') and s in l for l in c['hunk'].splitlines())
    files = [c['file'] for c in sel] + [c['file'] for c in data['unselected']]
    checks = {
        'access check removed is selected as blocker': any(c['file'] == PHP and c['blocker'] for c in sel),
        'drupal: access check hunk scored as before (9, same signals)': [
            (c['score'], c['signals']) for c in sel if c['file'] == PHP] == [
            (9, ['access/permission/sanitise check', 'guard condition', 'throw'])],
        'composer patch entry removed is selected': any(c['file'] == 'composer.json' and removed(c, 'a.patch') for c in sel),
        'composer patch entry swapped is selected': any(c['file'] == 'composer.json' and removed(c, 'swap-old') for c in sel),
        'composer patch entry added is not a candidate': files.count('composer.json') == 2,
        'deleted .patch file is selected': 'patches/core/a.patch' in [c['file'] for c in sel],
        'changed .patch file is selected': 'patches/webform/w.patch' in [c['file'] for c in sel],
        '.patch file swapped for a reroll is selected': 'patches/swap/s-2.patch' in [c['file'] for c in sel],
        'new .patch file is not a candidate': 'patches/new/n.patch' not in files,
        'binary fixture is not a candidate': PNG not in files,
        'drupal: removed #[Hook] attribute is selected as blocker': any(c['file'] == HOOK and c['blocker'] for c in sel),
        'candidates.md written': os.path.isfile(os.path.join(out, 'candidates.md')),
        'brief.md written': os.path.isfile(os.path.join(out, 'brief.md')),
    }
    poly = repo.rstrip('/') + '-polyglot'
    os.makedirs(poly, exist_ok=True)
    build_polyglot(poly)
    checks.update(polyglot_checks(a.script, poly))
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == '__main__':
    main()
