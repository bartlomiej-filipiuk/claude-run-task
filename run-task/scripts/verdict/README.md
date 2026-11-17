# verdict

Records every gate result of a task together with the commit of every touched repo, and computes the highest verdict
those records allow. A review or a test run describes one commit; a result recorded before a later commit no longer
says anything about HEAD.

## Commands

    python3 verdict.py init   <T> --repo <abs repo path> [--repo ...] [--task T1 --task T2 ...]
    python3 verdict.py record <T> --task T2|final --gate <name> [--gate <name> ...] [--repo <abs repo path>]
                                  --result pass|fail|baseline|skip|not-covered [--detail "<reason or counts>"] [--accepted N]
    python3 verdict.py check  <T>
    python3 verdict.py yield  <T>
    python3 selftest.py

`<T>` is the task's artefacts directory; the records go to `<T>/gates.jsonl`. `init` again (for example when the plan
gains a task) adds a new meta line; the last one counts. `record` reads HEAD and the dirty state of every repo itself.
`skip` and `not-covered` need `--detail` with the reason. `--accepted` is the number of findings from this run of the
gate that were accepted for a fix (0 when it found nothing); a re-record after a fix round leaves it out. `yield`
prints `<gate> <accepted>/<runs>`, counting only records that carry `--accepted`.

## Gates

| scope | names |
|---|---|
| per internal task (`--task T<N>`) | `review`, `revert`, `secperf`, `challenge`, `verifier`; optional `proof-steps`, `scope`, `approach` |
| final, whole branch (`--task final`) | `review`, `secperf`, `intent`, `challenge`, `visual`, `change-map`, `qa-walk` |
| final, per repo (`--task final --repo`) | `lint`, `types`, `unit`, `integration`, `e2e`, `build`, `smoke` |

`secperf` is the profile's security review, whatever tool it names. Every name in the table except the optional ones
is required; an unknown name is refused, so a typo cannot hide a missing gate.

## check

Prints `ceiling: <verdict>`, one line per item, and a JSON line last. Exit 0 GO, 1 GO with conditions, 3 NO-GO,
4 INCOMPLETE, 2 error.

- **INCOMPLETE**: a required gate has no record, a final gate's record describes another commit than HEAD, or a
  repo has uncommitted tracked changes. Exception: `secperf`, `intent` and `visual` may describe an earlier commit of
  the same branch when a final `review` was recorded at HEAD after them (the reviewer's later round covered the
  delta); `check` lists that as a note.
- **NO-GO**: the latest record of any gate, per-task or final, is `fail`.
- **GO with conditions**: a final per-repo gate or `qa-walk` is `not-covered`.
- **GO** otherwise.

The verdict in `summary.md` is never above the ceiling; the session applies the rest of the verdict table (proof
table, intent rows, rulings) within it. The latest record per task, gate and repo counts.
