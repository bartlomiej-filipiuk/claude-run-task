# revert-check

Proves that a task's tests guard the task's change. It reverses the production part of the working-tree diff
(against `--base`, default `HEAD`, plus the untracked files named with `--new`), runs the test command, expects it to FAIL, then restores
the working tree and checks it is byte-identical (status + sha256 fingerprint). Test files stay as they are. It never
touches the index, commits or stash.

A file counts as a test file when any of these match:

- a path segment: `tests/`, `test/`, `spec/`, `e2e/`, `__tests__/`, `__snapshots__/`, `__mocks__/`, `fixtures/`;
- the file name: `*.test.*`, `*.spec.*` (JS/TS), `*Test.php`, `*TestBase.php`, `test_*.py`, `*_test.py`, `conftest.py`,
  `*_test.go`, `*_spec.rb`, `*_test.rb`, `*Test.java`, `*Tests.java`, `*IT.java`, `*Test.kt`, `*Tests.kt`, `*Test.cs`,
  `*Tests.cs`;
- `--test-glob <pattern>` (repeatable): a project convention the defaults miss. A pattern without `/` matches the file
  name (`--test-glob 'verify_*.py'`), one with `/` matches the path from the repo root (`--test-glob 'qa/*'`);
- `--keep <glob> ...`: any other path (from the repo root) that must stay as it is.

Examples:

    python3 scripts/revert-check/revert-check.py --repo <repo> -- env CI=true npx jest --ci --watchAll=false <path>
    python3 scripts/revert-check/revert-check.py --repo <repo> -- python3 -m pytest -q <path>
    python3 scripts/revert-check/revert-check.py --repo <repo> -- go test ./...
    python3 scripts/revert-check/revert-check.py --repo <repo> --test-glob 'check_*.py' -- python3 -m pytest -q checks/
    python3 scripts/revert-check/revert-check.py --repo <repo> --pre '<sync command>' -- <test command in a container>

`--pre` runs after the revert and again after the restore (e.g. a container file sync that has to see both states).
The test command first runs once on the tree as it is and must exit 0; otherwise the tool stops with an error: a
command that exits non-zero anyway (deprecation notices turned into exit 1, a wrong path) would make every run report
"pass" for nothing. `--no-baseline` skips that run. The baseline run and the reverted run are seconds apart: a runner
that caches compiled code by file time and size (Python `.pyc`; set `PYTHONDONTWRITEBYTECODE=1`) can serve the
unreverted code to the second run; jest (content hash) and PHPUnit on the CLI (no opcache) do not.
`--new <path-or-glob> ...` names the task's new, still untracked production files (paths relative to the repo root);
only those are moved away. Every other untracked path stays where it is and is listed in `untracked_ignored`: a
checkout holds notes, reports and other git worktrees that are not the task's. A `--new` value that matches no
untracked file is an error.
Add `--base <branch>` (or the branch point) when the task is already committed.

| exit | result | meaning |
|---|---|---|
| 0 | pass | tests fail without the change: they guard it |
| 1 | fail | tests pass without the change: they do not guard it |
| 2 | error | cannot revert/restore, fingerprint mismatch, operation in progress, interrupted |
| 3 | skip | no production file in the diff |

The last stdout line is JSON: `{"result", "test_exit", "reverted", "kept", "untracked_ignored", "note"}`. If the restore fails, the tool
prints the exact commands to restore by hand and keeps its temp directory.

**Never run it while another agent or person edits the same checkout**: for the duration of the test run the
production change is gone from the working tree, and edits made meanwhile break the restore.

Self-test (temp repos only): `python3 -I scripts/revert-check/selftest.py`.
