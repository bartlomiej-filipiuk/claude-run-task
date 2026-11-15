#!/usr/bin/env python3
"""Self-test for revert-check.py: builds throwaway git repos and checks every case.

Run: python3 -I scripts/revert-check/selftest.py   (exit 0 = all cases passed)
"""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "revert-check.py")
GIT_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
# The baseline run and the reverted run are less than a second apart and mod.py keeps its size, so a .pyc written
# by the first would be served to the second (Python validates by mtime in seconds and size).
RUN_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
PY = sys.executable

# The "test suite" inside every temp repo: exits 0 when mod.f() returns the expected value.
CHECK_F = "import sys; sys.path.insert(0, '.'); import mod; sys.exit(0 if mod.f() == {want} else 1)\n"


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, env=GIT_ENV, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def write(repo, rel, content):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(content, bytes) else "w") as f:
        f.write(content)


def read(repo, rel):
    with open(os.path.join(repo, rel), "rb") as f:
        return f.read()


def new_repo(files):
    repo = tempfile.mkdtemp(prefix="rc-selftest-")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "selftest@example.invalid")
    git(repo, "config", "user.name", "selftest")
    for rel, content in files.items():
        write(repo, rel, content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return repo


def snapshot(repo):
    """Everything the tool must leave untouched: HEAD, index bytes, status, every file outside .git."""
    files = {}
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            path = os.path.join(dirpath, name)
            files[os.path.relpath(path, repo)] = (hashlib.sha256(read(repo, path)).hexdigest(),
                                                  os.stat(path).st_mode & 0o111)
    return (git(repo, "rev-parse", "HEAD"), hashlib.sha256(read(repo, ".git/index")).hexdigest(),
            git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all"), files)


def run_tool(repo, tool_args, test_cmd):
    p = subprocess.run([PY, TOOL, "--repo", repo, *tool_args, "--", *test_cmd], env=RUN_ENV,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1]), p


def expect(case, cond, detail):
    if not cond:
        raise AssertionError(f"{case}: {detail}")


def checked(case, repo, tool_args, test_cmd, want_exit, want_result):
    before = snapshot(repo)
    code, out, proc = run_tool(repo, tool_args, test_cmd)
    expect(case, code == want_exit and out["result"] == want_result,
           f"exit {code} / {out}, want {want_exit} / {want_result}\nstderr:\n{proc.stderr}")
    expect(case, snapshot(repo) == before, "working tree, index or HEAD changed")
    return out


def base_files(want=1):
    return {"mod.py": "def f():\n    return 1\n", "tests/check.py": CHECK_F.format(want=want)}


def case1():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    write(repo, "tests/check.py", CHECK_F.format(want=2))
    out = checked("1 guarded change", repo, [], [PY, "tests/check.py"], 0, "pass")
    expect("1", out["reverted"] == ["mod.py"] and out["kept"] == ["tests/check.py"], out)
    return repo


def case2():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 1\n\n\ndef g():\n    return 5\n")
    checked("2 unguarded change", repo, [], [PY, "tests/check.py"], 1, "fail")
    return repo


def case3():
    repo = new_repo(base_files())
    write(repo, "helper.py", "def h():\n    return 3\n")
    write(repo, "tests/check_helper.py", "import sys; sys.path.insert(0, '.'); import helper; sys.exit(0)\n")
    out = checked("3 untracked production file", repo, ["--new", "helper.py"], [PY, "tests/check_helper.py"], 0, "pass")
    expect("3", out["reverted"] == ["helper.py"], out)
    expect("3", read(repo, "helper.py") == b"def h():\n    return 3\n", "helper.py not restored")
    return repo


def case4():
    repo = new_repo(base_files())
    write(repo, "tests/check.py", CHECK_F.format(want=1) + "# more assertions\n")
    write(repo, "src/widget.spec.ts", "// spec\n")
    checked("4 only test files", repo, [], [PY, "tests/check.py"], 3, "skip")
    return repo


def case5():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    write(repo, "tests/check.py", CHECK_F.format(want=2))
    git(repo, "commit", "-q", "-am", "the task")
    checked("5 --base with committed change", repo, ["--base", "HEAD~1"], [PY, "tests/check.py"], 0, "pass")
    return repo


def case6():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    marker = tempfile.mktemp(prefix="rc-started-")
    write(repo, "tests/slow.py", f"import time\nopen({marker!r}, 'w').close()\ntime.sleep(60)\n")
    before = snapshot(repo)
    # Own session = own process group, so the SIGINT reaches tool and test like a terminal Ctrl-C does.
    proc = subprocess.Popen([PY, TOOL, "--repo", repo, "--no-baseline", "--", PY, "tests/slow.py"], start_new_session=True,
                            env=RUN_ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 20
    while not os.path.exists(marker) and time.time() < deadline:
        time.sleep(0.05)
    expect("6", os.path.exists(marker), "test command never started")
    expect("6", read(repo, "mod.py") == b"def f():\n    return 1\n", "mod.py not reverted while the test runs")
    os.killpg(proc.pid, signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=30)
    out = json.loads(stdout.strip().splitlines()[-1])
    expect("6 SIGINT mid-run", proc.returncode == 2 and out["result"] == "error" and "interrupted" in out["note"],
           f"exit {proc.returncode} / {out}\nstderr:\n{stderr}")
    expect("6 SIGINT mid-run", snapshot(repo) == before, "working tree, index or HEAD changed")
    os.unlink(marker)
    return repo


def case7():
    old, new = bytes(range(256)) * 4, b"\x00\xff\x10PNG" + bytes(range(255, -1, -1)) * 4
    repo = new_repo(dict(base_files(), **{"assets/logo.bin": old}))
    write(repo, "assets/logo.bin", new)
    write(repo, "tests/check_bin.py", f"import sys; sys.exit(0 if open('assets/logo.bin', 'rb').read() == {new!r} else 1)\n")
    out = checked("7 binary production file", repo, [], [PY, "tests/check_bin.py"], 0, "pass")
    expect("7", out["reverted"] == ["assets/logo.bin"], out)
    expect("7", read(repo, "assets/logo.bin") == new, "binary file not byte-identical after restore")
    return repo


def case8():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    write(repo, "tests/check.py", CHECK_F.format(want=2))
    log = tempfile.mktemp(prefix="rc-pre-")
    pre = f"{PY} -c \"import sys; open({log!r}, 'a').write(open('mod.py').read().split()[-1] + chr(10))\""
    checked("8 --pre twice", repo, ["--pre", pre], [PY, "tests/check.py"], 0, "pass")
    with open(log) as f:
        calls = f.read().split()
    os.unlink(log)
    expect("8", calls == ["1", "2"], f"--pre calls saw {calls}, want ['1', '2'] (reverted, then restored)")
    return repo


def case9():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    write(repo, ".git/MERGE_HEAD", git(repo, "rev-parse", "HEAD").decode())
    out = checked("9 refuses during a merge", repo, [], [PY, "tests/check.py"], 2, "error")
    expect("9", "MERGE_HEAD" in out["note"], out)
    return repo


def foreign_untracked(repo):
    """What a real checkout holds beside the task: a note and another git worktree with its own files."""
    write(repo, "notes.txt", "not the task's file\n")
    write(repo, ".wt/other/package.json", "{}\n")
    git(os.path.join(repo, ".wt/other"), "init", "-q")


def case10():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    foreign_untracked(repo)
    present = "import os, sys\nif not (os.path.isfile('notes.txt') and os.path.isdir('.wt/other/.git')): sys.exit(99)\n"
    write(repo, "tests/check.py", present + CHECK_F.format(want=2))
    out = checked("10 foreign untracked paths stay", repo, [], [PY, "tests/check.py"], 0, "pass")
    expect("10", out["test_exit"] == 1, f"foreign paths were missing while the tests ran: {out}")
    expect("10", out["reverted"] == ["mod.py"] and out["untracked_ignored"] == [".wt/other/", "notes.txt"], out)
    return repo


def case11():
    repo = new_repo(base_files())
    write(repo, "helper.py", "def h():\n    return 3\n")
    write(repo, "tests/check_helper.py", "import sys; sys.path.insert(0, '.'); import helper; sys.exit(0)\n")
    out = checked("11 unnamed new file", repo, [], [PY, "tests/check_helper.py"], 3, "skip")
    expect("11", "--new" in out["note"] and out["untracked_ignored"] == ["helper.py"], out)
    return repo


def case12():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    foreign_untracked(repo)
    for pattern in ("nomatch.py", ".wt/other/", ".wt/*"):
        out = checked(f"12 --new {pattern}", repo, ["--new", pattern], [PY, "tests/check.py"], 2, "error")
        expect("12", "matches no untracked file" in out["note"], out)
    return repo


def case13():
    repo = new_repo(base_files())
    write(repo, "mod.py", "def f():\n    return 2\n")
    write(repo, "tests/always_red.py", "import sys; sys.exit(1)\n")
    out = checked("13 tests red with the change", repo, [], [PY, "tests/always_red.py"], 2, "error")
    expect("13", "do not pass with the change" in out["note"] and out["test_exit"] is None, out)
    out = checked("13 --no-baseline", repo, ["--no-baseline"], [PY, "tests/always_red.py"], 0, "pass")
    return repo


def case14():
    # A Python test outside a tests/ folder is kept, so reverting mod.py alone makes it fail.
    repo = new_repo(dict(base_files(), **{"test_mod.py": CHECK_F.format(want=1), "checks/verify_mod.py": CHECK_F.format(want=1)}))
    write(repo, "mod.py", "def f():\n    return 2\n")
    write(repo, "test_mod.py", CHECK_F.format(want=2))
    out = checked("14 Python test file", repo, [], [PY, "test_mod.py"], 0, "pass")
    expect("14", out["reverted"] == ["mod.py"] and out["kept"] == ["test_mod.py"], out)
    # A project convention the defaults do not know is added with --test-glob.
    write(repo, "checks/verify_mod.py", CHECK_F.format(want=2))
    out = checked("14 --test-glob", repo, ["--test-glob", "verify_*.py"], [PY, "checks/verify_mod.py"], 0, "pass")
    expect("14", out["reverted"] == ["mod.py"] and out["kept"] == ["checks/verify_mod.py", "test_mod.py"], out)
    return repo


def main():
    cases = [case1, case2, case3, case4, case5, case6, case7, case8, case9, case10, case11, case12, case13, case14]
    failed = 0
    for case in cases:
        repo = None
        try:
            repo = case()
            print(f"ok   {case.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {case.__name__}: {e}")
        finally:
            if repo:
                shutil.rmtree(repo, ignore_errors=True)
    print(f"{len(cases) - failed}/{len(cases)} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
