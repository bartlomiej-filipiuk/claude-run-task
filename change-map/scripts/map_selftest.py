#!/usr/bin/env python3
"""Offline check of map.py's output safety on a throwaway git repo. Run: python3 scripts/map_selftest.py

A branch under review controls its file names and contents: the diff commands handed to agents must stay one quoted
argument per value, and the HTML viewer must sanitise what it renders and pin its CDN scripts.
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile

MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'map.py')
EVIL = "docroot/modules/custom/m/a';touch pwned;'.php"


def sh(cwd, *cmd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


with tempfile.TemporaryDirectory() as tmp:
    repo = os.path.join(tmp, 'repo')
    os.makedirs(repo)
    sh(repo, 'git', 'init', '-q')
    sh(repo, 'git', 'symbolic-ref', 'HEAD', 'refs/heads/main')
    sh(repo, 'git', 'config', 'user.email', 't@example.com')
    sh(repo, 'git', 'config', 'user.name', 't')
    write(repo, 'composer.json', '{"require": {"drupal/core": "^10"}}')
    write(repo, 'README.md', 'x\n')
    sh(repo, 'git', 'add', '-A')
    sh(repo, 'git', 'commit', '-qm', 'init')
    sh(repo, 'git', 'checkout', '-qb', 'feature')
    write(repo, EVIL, '<?php\n// </SCRIPT><img src=x onerror=alert(1)>\nfunction m_evil() {}\n')
    sh(repo, 'git', 'add', '-A')
    sh(repo, 'git', 'commit', '-qm', 'feature')

    out, graph = os.path.join(tmp, 'map.md'), os.path.join(tmp, 'graph.json')
    r = subprocess.run([sys.executable, MAP, '--base', 'main', '--committed', '--json', graph, '--html', '--out', out],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    nodes = json.load(open(graph))['nodes']
    node = next((n for n in nodes if n['path'].endswith(".php") and 'pwned' in n['path']), None)
    html = open(os.path.splitext(out)[0] + '.html').read()
    md_block = html.split('<script id="md" type="text/markdown">', 1)[1].split('</script>', 1)[0]

    checks = {
        'the file with a quote in its name is mapped': node is not None,
        'diff command keeps the file name as one argument': node is not None
            and shlex.split(node['diff_cmd'])[-1] == EVIL,
        'show command keeps the file name as one argument': node is not None
            and EVIL in shlex.split(node['show_cmd'])[-1],
        'viewer sanitises rendered Markdown': 'DOMPurify.sanitize(marked.parse(' in html,
        'every CDN script is pinned with SRI': html.count('<script src=') == html.count('integrity="sha384-'),
        'no closing script tag survives inside the Markdown block, any case': '</script' not in md_block.lower(),
    }
    for name, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not all(checks.values()):
        sys.exit(1)
    print('map selftest OK')
