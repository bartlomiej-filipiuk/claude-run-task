#!/usr/bin/env python3
"""Prove that a task's tests guard the task's change.

Reverses the production part of the working-tree diff (against --base), runs the
test command, expects it to FAIL, then restores the working tree exactly.

Usage:
  revert-check.py --repo <path> [--base <rev>] [--pre '<cmd>'] [--keep <glob> ...]
                  [--new <path-or-glob> ...] [--test-glob <pattern>] -- <test command ...>

Tracked changes are reverted with a reverse patch. An untracked file is moved away only
when --new names it (path relative to the repo root, or a glob): a checkout holds
untracked files that are not the task's (notes, reports, other git worktrees), and
those must never be touched. Untracked directories that git reports as one entry
(nested repositories and worktrees) are never moved.

Test files are never reverted: the built-in conventions (TEST_SEGMENTS, TEST_NAMES)
plus every --test-glob (repeatable; a pattern without '/' matches the file name, one
with '/' the path from the repo root) plus every --keep glob (path from the repo root).

Before anything is reverted the test command runs once on the tree as it is and must
exit 0: a command that fails anyway (a deprecation notice turned into exit 1, a wrong
path) would make every verdict "pass". --no-baseline skips that run.

Exit codes: 0 pass (tests failed without the change), 1 fail (tests passed without
it), 2 error, 3 skip (no production file in the diff). The last stdout line is JSON.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import PurePosixPath

EXIT = {"pass": 0, "fail": 1, "error": 2, "skip": 3}
TEST_SEGMENTS = {"tests", "test", "spec", "e2e", "__tests__", "__snapshots__", "__mocks__", "fixtures"}
TEST_NAMES = ("*.test.*", "*.spec.*", "*Test.php", "*TestBase.php",
              "test_*.py", "*_test.py", "conftest.py",
              "*_test.go",
              "*_spec.rb", "*_test.rb",
              "*Test.java", "*Tests.java", "*IT.java", "*Test.kt", "*Tests.kt",
              "*Test.cs", "*Tests.cs")
IN_PROGRESS = ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD")
# Never take index.lock or refresh the index: another process may be using it.
GIT_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")


class Interrupted(Exception):
    pass


class Failure(Exception):
    pass


def log(msg):
    print(f"[revert-check] {msg}", file=sys.stderr, flush=True)


def git(root, *args, check=True):
    p = subprocess.run(["git", *args], cwd=root, env=GIT_ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode != 0:
        raise Failure(f"git {' '.join(args)} failed: {p.stderr.decode(errors='replace').strip()}")
    return p


def nul_list(data):
    return [x.decode() for x in data.split(b"\0") if x]


def parse_args(argv):
    if "--" not in argv:
        raise Failure("missing '--' before the test command")
    split = argv.index("--")
    command = argv[split + 1:]
    if not command:
        raise Failure("empty test command after '--'")
    ap = argparse.ArgumentParser(prog="revert-check.py")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--pre")
    ap.add_argument("--keep", nargs="+", action="extend", default=[])
    ap.add_argument("--new", nargs="+", action="extend", default=[])
    ap.add_argument("--test-glob", action="append", default=[])
    ap.add_argument("--no-baseline", action="store_true")
    args = ap.parse_args(argv[:split])
    args.command = command
    return args


def is_kept(path, keep_globs, test_globs):
    p = PurePosixPath(path)
    if TEST_SEGMENTS.intersection(p.parts):
        return True
    if any(fnmatch.fnmatchcase(p.name, g) for g in TEST_NAMES):
        return True
    if any(fnmatch.fnmatchcase(path if "/" in g else p.name, g) for g in test_globs):
        return True
    return any(fnmatch.fnmatchcase(path, g) for g in keep_globs)


def file_digest(path):
    if os.path.islink(path):
        return "link:" + os.readlink(path)
    if os.path.isdir(path):
        return "dir"
    if not os.path.exists(path):
        return "missing"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    # Only the executable bit: git tracks nothing else, and git apply rewrites files with the umask.
    return h.hexdigest() + (":x" if os.stat(path).st_mode & 0o100 else "")


def fingerprint(root, base):
    status = git(root, "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all").stdout
    paths = {entry[3:] for entry in nul_list(status)}
    paths |= set(nul_list(git(root, "diff", "--name-only", "-z", "--no-renames", base).stdout))
    head = git(root, "rev-parse", "HEAD", check=False).stdout.strip()
    return {"head": head.decode(), "status": status.hex(),
            "files": {p: file_digest(os.path.join(root, p)) for p in sorted(paths)}}


def run_cmd(cmd, cwd, shell=False):
    """Run with inherited stdout/stderr; on interrupt stop the child before re-raising."""
    child = subprocess.Popen(cmd, cwd=cwd, shell=shell)
    try:
        return child.wait()
    except Interrupted:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        raise


class Reverter:
    def __init__(self, root, tmp, patch, untracked):
        self.root, self.tmp, self.patch, self.untracked = root, tmp, patch, untracked
        self.store = os.path.join(tmp, "untracked")
        self.applied = False
        self.moved = []

    def revert(self):
        for rel in self.untracked:
            src = os.path.join(self.root, rel)
            if not (os.path.isfile(src) or os.path.islink(src)):
                raise Failure(f"{rel} is not a file; only files are moved away")
        if self.patch:
            git(self.root, "apply", "-R", "--check", "--whitespace=nowarn", self.patch)
            git(self.root, "apply", "-R", "--whitespace=nowarn", self.patch)
            self.applied = True
        for rel in self.untracked:
            dest = os.path.join(self.store, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(os.path.join(self.root, rel), dest)
            self.moved.append(rel)

    def restore(self):
        """Returns a list of problems; empty means fully restored."""
        problems = []
        for rel in list(self.moved):
            src, dest = os.path.join(self.store, rel), os.path.join(self.root, rel)
            try:
                if os.path.lexists(dest):
                    raise Failure(f"{rel} exists again in the repo")
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                shutil.move(src, dest)
                self.moved.remove(rel)
            except (OSError, Failure) as e:
                problems.append(f"move back {rel}: {e}")
        if self.applied:
            try:
                git(self.root, "apply", "--whitespace=nowarn", self.patch)
                self.applied = False
            except Failure as e:
                problems.append(str(e))
        return problems

    def manual_commands(self):
        cmds = [f"cd {shlex.quote(self.root)}"]
        if self.applied:
            cmds.append(f"git apply --whitespace=nowarn {shlex.quote(self.patch)}")
        for rel in self.moved:
            cmds.append(f"mkdir -p {shlex.quote(os.path.dirname(rel) or '.')} && "
                        f"mv {shlex.quote(os.path.join(self.store, rel))} {shlex.quote(rel)}")
        return cmds


def main(argv):
    out = {"result": "error", "test_exit": None, "reverted": [], "kept": [], "untracked_ignored": [], "note": ""}
    try:
        args = parse_args(argv)
    except Failure as e:
        out["note"] = str(e)
        return out

    def on_signal(signum, _frame):
        raise Interrupted(signum)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    repo = os.path.realpath(args.repo)
    reverter = None
    tmp = None
    try:
        root = git(repo, "rev-parse", "--show-toplevel").stdout.decode().strip()
        for name in IN_PROGRESS:
            marker = git(root, "rev-parse", "--path-format=absolute", "--git-path", name).stdout.decode().strip()
            if os.path.exists(marker):
                raise Failure(f"git operation in progress ({name}); finish or abort it first")
        git(root, "rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}")

        tracked = nul_list(git(root, "diff", "--name-only", "-z", "--no-renames", args.base).stdout)
        untracked = nul_list(git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout)
        prod_tracked = [p for p in tracked if not is_kept(p, args.keep, args.test_glob)]
        # A trailing slash is a nested repository or worktree reported as one entry: never the task's file.
        files = [p for p in untracked if not p.endswith("/")]
        for pattern in args.new:
            if not any(p == pattern or fnmatch.fnmatchcase(p, pattern) for p in files):
                raise Failure(f"--new {pattern} matches no untracked file")
        prod_untracked = [p for p in files if not is_kept(p, args.keep, args.test_glob)
                          and any(p == g or fnmatch.fnmatchcase(p, g) for g in args.new)]
        ignored = sorted(p for p in untracked if p not in prod_untracked and not is_kept(p, args.keep, args.test_glob))
        out["untracked_ignored"] = ignored
        hint = (f"; {len(ignored)} untracked path(s) not reverted, name the task's new production files with --new: "
                + ", ".join(ignored[:10])) if ignored else ""
        out["reverted"] = sorted(prod_tracked + prod_untracked)
        out["kept"] = sorted(p for p in tracked + untracked if is_kept(p, args.keep, args.test_glob))
        if not out["reverted"]:
            out["result"], out["note"] = "skip", "no production file in the diff" + hint
            return out

        if not args.no_baseline:
            log(f"baseline: {shlex.join(args.command)}")
            try:
                code = run_cmd(args.command, repo)
            except FileNotFoundError as e:
                raise Failure(f"test command not found: {e}")
            if code != 0:
                raise Failure(f"the tests do not pass with the change (exit {code}), so failing without it would "
                              "prove nothing; make the command exit 0 on the current tree first")

        before = fingerprint(root, args.base)
        tmp = tempfile.mkdtemp(prefix="revert-check-")
        if os.path.realpath(tmp).startswith(root + os.sep):
            raise Failure(f"temp dir {tmp} is inside the repo; set TMPDIR elsewhere")
        patch = None
        if prod_tracked:
            patch = os.path.join(tmp, "production.patch")
            diff = git(root, "diff", "--binary", "--no-renames", "--no-ext-diff", "--no-textconv", "--no-color",
                       "--src-prefix=a/", "--dst-prefix=b/", args.base, "--",
                       *[":(literal)" + p for p in prod_tracked]).stdout
            with open(patch, "wb") as f:
                f.write(diff)
        reverter = Reverter(root, tmp, patch, prod_untracked)

        log(f"reverting {len(out['reverted'])} production file(s), keeping {len(out['kept'])}")
        reverter.revert()
        if args.pre:
            log(f"pre: {args.pre}")
            if run_cmd(args.pre, repo, shell=True) != 0:
                raise Failure("--pre failed after the revert")
        log(f"running: {shlex.join(args.command)}")
        try:
            code = run_cmd(args.command, repo)
        except FileNotFoundError as e:
            raise Failure(f"test command not found: {e}")
        out["test_exit"] = code
        if code < 0:
            raise Failure(f"test command was killed by signal {-code}")
        if code != 0:
            out["result"], out["note"] = "pass", "tests fail without the production change"
        else:
            out["result"] = "fail"
            out["note"] = "tests pass without the production change: they do not guard it" + hint
    except Interrupted as e:
        out["result"], out["note"] = "error", f"interrupted by signal {e.args[0]}"
    except (Failure, OSError) as e:
        out["result"], out["note"] = "error", str(e)
    finally:
        # From here on a second Ctrl-C must not abort the restore half way.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if reverter is not None:
            finish(reverter, args, repo, root, before, out)
        elif tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def finish(reverter, args, repo, root, before, out):
    problems = reverter.restore()
    if not problems and args.pre:
        log(f"pre: {args.pre}")
        if run_cmd(args.pre, repo, shell=True) != 0:
            problems.append("--pre failed after the restore")
    if not problems:
        after = fingerprint(root, args.base)
        if after != before:
            names = sorted(p for p in {*before["files"], *after["files"]}
                           if before["files"].get(p) != after["files"].get(p))
            if names and all(p not in before["files"] for p in names):
                # New files the test run left behind (not gitignored): the restore itself is intact.
                out["note"] += "; test run left behind: " + ", ".join(names[:10])
            else:
                problems.append("working tree differs after restore: " + (", ".join(names[:10]) or "git status changed"))
    if not problems:
        shutil.rmtree(reverter.tmp, ignore_errors=True)
        return
    out["result"] = "error"
    out["note"] = "; ".join(filter(None, [out["note"], *problems])) + f"; temp dir kept: {reverter.tmp}"
    print("\n[revert-check] RESTORE PROBLEM. Restore by hand:", file=sys.stderr)
    for cmd in reverter.manual_commands():
        print(f"  {cmd}", file=sys.stderr)
    print(f"  # the production patch is {reverter.patch}; untracked originals under {reverter.store}",
          file=sys.stderr)
    print(f"  # if git apply refuses because the tests changed a file, reset it to the reverted state first:"
          f" git show {shlex.quote(args.base)}:<path> > <path>", file=sys.stderr, flush=True)


if __name__ == "__main__":
    result = main(sys.argv[1:])
    sys.stdout.flush()
    # Leading newline: the test output may not end with one, and the JSON must be a line of its own.
    print("\n" + json.dumps(result), flush=True)
    sys.exit(EXIT[result["result"]])
