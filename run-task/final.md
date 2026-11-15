# Final review, verdict and deliverables (Phase 5)

`<BASE>` is the repo's base branch from the profile (or the base a base rule chose). In the commands below
`tasks/<ID>` stands for its absolute path `<T>`, and every command runs after `cd <absolute repo path>`. Two touched repos: scripts and
the security review run from one with `--pair <other repo>`.

## 1. Reviews, in parallel, then one fix wave

First the challenge script on the branch, no challenger agent:
`python3 ~/.claude/skills/challenge/scripts/hunks.py --base <BASE> --intent tasks/<ID>/ac.md --out tasks/<ID>/challenge/final`.
Then in ONE message:
- **final whole-branch review**: a fresh strong-model agent, effort high, with the profile's topology in mind. It gets
  the branch diff, `ac.md`, the selected hunks (`challenge/final/brief.md`) and `candidates.md`, and clears each hunk
  in one line or raises it as a finding. When the security review reports `not covered: perf, cache`, its brief adds
  growth with data and caching as review points. It is never skipped: it is the pass that sees how the tasks interact;
- **security review** on the branch by the profile's `security_review`, with the same rules as in `loop.md`
  (`secperf-review` with `--deep --base <BASE> --intent tasks/<ID>/ac.md --out tasks/<ID>/secperf/final`;
  `claude-security`: `/claude-security scan changes` on this branch at high effort for size large, medium otherwise,
  the cost accepted in the request; its report goes to `tasks/<ID>/security/`, its patch files are never applied
  without the fix wave);
- **intent check**, `intent-check.md`;
- **visual review** when its trigger matches, `visual-review.md`.

ONE fix wave for everything accepted, then the verifier with one claim per fixed finding, rulings for anything left.
Fix-wave changes (and later QA-walk fix rounds) are committed locally like a task (`loop.md` step 8).
Then `change-map --base <BASE> --svg --out tasks/<ID>/change-map.md` when the change-map skill supports the stack;
otherwise `not covered`.

## 2. Full gates and smoke

The profile's gates on the final state of each touched repo, then every `smoke` command (the whole suites, so a change
cannot break the main paths unnoticed). Every failure is run again without the change:
`python3 ~/.claude/skills/run-task/scripts/revert-check/revert-check.py --repo <repo> --base <BASE> --no-baseline [--pre '<revert_pre>'] -- <the failing tests>`.
Passes without the change = regression, joins the fix wave. Fails without it too = old failure, a `pre-existing`
ruling and a follow-up; it does not block. A failure that does not repeat is run twice more and reported as flaky.
No smoke configured = `not covered`. Docs-only tasks: `skip`.

## 3. QA walk and verdict

`qa-walk.md`: every step a tester will get is first done by script; proof steps must fail without the change. Then
the verdict at the top of `summary.md`: **GO**, **GO with conditions**, or **NO-GO**, by the table in `qa-walk.md`.
Never round up.

## 4. Deliverables in `tasks/<ID>/`

- `summary.md`: the verdict and its proof table first, every condition, then the intent table, what changed per repo
  and commit, gates (honest, including pre-existing failures and every `not covered`), deviations from the AC,
  "Rulings I made", rollout order, manual QA that remains;
- `qa-notes.md` (`qa-notes` skill when installed): the walked steps from `run.mjs --print-qa`, nothing that was not
  walked unless marked "not checked by us";
- the review artefacts already written (`intent-check.md`, `secperf/`, `challenge/`, `visual/`, `change-map.md`);
- every artefact an AC or an intake decision asks for (a recording, a document), linked under Deliverables;
- the Phase 5 extensions (the profile's, or the overlay's) when they apply.

## 5. Final message

In the chat language, short: the verdict in one word, the proof table (AC, step, with the change, without the change),
every condition, every gate that is `not covered`, the intent check counts with any item not covered or unexplained,
and the rulings that need the user's eye. Everything else is in `summary.md`, linked, not repeated.

Offer, never do unasked: a tracker comment draft (tracker inputs only, posted after approval), the push
(`git push -u <remote> <branch>` on explicit request), follow-up items. Then the retro (`improve.md`).
