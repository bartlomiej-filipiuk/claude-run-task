# Per-task loop (Phase 4)

For every internal task of the plan, in order. In the commands below `tasks/<ID>` stands for its absolute path `<T>`,
and every command runs after `cd <absolute repo path>`. Commands, test layers and idioms come from the profile.

## Review tiers

| tier | when | passes |
|---|---|---|
| full | behaviour change: anything a user, an admin or another system sees; access, schema, endpoints, services | revert + reviewer agent + security review + challenge + verifier by rule |
| light | small mechanical code with no new boundary (roughly up to 60 lines), e.g. a migration step, a form alter | revert + inline review on the `task-review.md` lenses + security review + challenge + verifier by rule |
| docs | docs, guides, config text only | challenge script + verifier on the doc claims |

The profile's trap checklist is part of every tier. The challenge script corrects the tier: when it selects a
blocker-class hunk (removed side effect, guard, access check, permission, security switch, test assertion), a light or
docs task is raised to full before anything else starts. Ruling: "T3 raised to full: <signal>".

## Steps

1. **Branch** (first task per repo): clean tree (`git status --porcelain` empty), `git fetch <remote>`, then
   `git checkout -b <branch_pattern> <remote>/<base_branch>`.
2. **Ladder before writing**: understand the data flow, then YAGNI, reuse, the platform's own feature, cost of an
   abstraction, minimum design. The brief says it in one sentence.
3. **Tests first**, in the layer the profile's "Test layers" table names for this kind of change. Every task with
   logic leaves at least one test that fails without the change. Docs or config-only tasks say "no test" in the brief.
   A change type the table does not cover: pick the cheapest layer that proves the behaviour, and note it for the
   retro.
4. **Implement** through a fresh implementer (`roles.md`) with a brief file: the task, its tests, the gates to run,
   the files in scope. One implementer per checkout at a time.
5. **Gates**: the profile's gate commands for the touched repo. A failure is compared against the base before anyone
   calls it a regression. A gate with no command is `not covered`.
6. **Review by tier**. Two scripts first, one after the other, nothing else touching the checkout until both exit:
   - challenge selection: `python3 ~/.claude/skills/challenge/scripts/hunks.py --base HEAD --intent tasks/<ID>/ac.md
     --out tasks/<ID>/challenge/T<N>` (`--pair <other repo>` when two repos changed). The script reads only Drupal
     projects (`drupal/core` in `composer.json`), Next.js apps and infra/CI files, and it reports "0 selected", not
     an error, for anything else. When the task changes code outside those, the gate is `not covered: <stack>`, never
     `skip`; I read the removed lines of the diff myself for the blocker signals above (removed side effect, guard, access check, permission, security switch, test assertion) (raise the tier when one is
     there), and the reviewer's "removed guarantee" check carries the rest.
   - revert check: `python3 ~/.claude/skills/run-task/scripts/revert-check/revert-check.py --repo <repo> [--pre '<revert_pre>']
     [--test-glob <pattern> ...] [--new <new production files>] -- <the task's test command>`. Exit 0 = pass (the
     tests fail without the change); 1 = fail, joins the fix round (the test does not guard the change); 3 = skip (no
     production change); 2 = error, read the `note` in its last output line, fix the cause, run again. Tasks proven
     only by end-to-end tests or docs-only: `skip` with that reason.

   Then in ONE message:
   - the reviewer (full tier), `task-review.md`;
   - the security review on the uncommitted task diff, by the profile's `security_review`:
     - `secperf-review`: `--base HEAD --intent tasks/<ID>/ac.md --out tasks/<ID>/secperf/T<N>` (never without
       `--base`; follow that skill for the Workflow call). It reads only Drupal and Next.js code: when the task
       changes code it did not review (its "not checked" or skipped list, or "nothing in scope" while the diff has
       code), run the built-in `security-review` on that code;
     - `claude-security`: per task the built-in `security-review` below; the plugin runs once, in the final review;
     - `security-review`: the built-in skill on the uncommitted diff. It covers security only, so report
       `not covered: perf, cache` beside its result; the reviewer's correctness lens carries logic;
     - `none`, or no tool reads the stack: `not covered: <stack>`.
     Docs or config text only = `skip`;
   - `challenge` with the same flags when the script selected hunks (full and light tier): the challenger asks, the
     implementer defends through SendMessage (no SendMessage: a fresh implementer gets the questions, the diff and
     the brief, and answers them), the challenger rules. Rejected answers join the fix round; escalated
     ones go to the final summary and the PR notes.

   **Verifier** runs when at least one holds: the task wrote docs, an ADR, a guide or QA notes (claims from those
   texts); a finding is disputed or about to be rejected; a fix round happened (one claim per accepted finding, "fixed
   at file:line"). Otherwise `skip`, "no claims". A "fixed" claim that is not CONFIRMED starts the next round; a
   finding I wanted to reject that is not REFUTED stands.
   Fix rounds: up to three by the same implementer, then a fresh one; after each round the verifier, and a failed
   revert check runs again.
7. **Controller check**: what agents could not do (a browser pass, headers on the wire, multi-instance assumptions).
   Full-tier task matching the visual trigger: the layout audit on the branch build (`visual-review.md`, per-task
   variant); findings join this task's fix round.
8. **Commit locally**: only the task's files, staged by name, the profile's `commit_format` and `commit_flags`, no AI
   footer unless the profile says otherwise. Update the ledger.

Mid-loop questions that change what is delivered stop this task and go to the user (`needs_me`), answer appended to
`ac.md` dated; everything about how to build it is a ruling in the ledger. While implementers work, write docs and
drafts for what is already done.
