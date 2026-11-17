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

1. **Branch**, made in Phase 3 for every repo in the plan (a repo the plan missed gets it here, the same way): clean
   tree (`git status --porcelain` empty), `git fetch <remote>`, then `git checkout -b <branch_pattern>
   <remote>/<base_branch>`.
2. **Ladder before writing**: understand the data flow, then YAGNI, reuse, the platform's own feature, cost of an
   abstraction, minimum design. The brief says it in one sentence.
3. **Tests first**, in the layer the profile's "Test layers" table names for this kind of change. Every task with
   logic leaves at least one test that fails without the change. Docs or config-only tasks say "no test" in the brief.
   A change type the table does not cover: pick the cheapest layer that proves the behaviour, and note it for the
   retro.
4. **Implement** through a fresh implementer (`roles.md`) with a brief file: the task, its tests, the proof steps it
   must make pass with their command, the gates to run, the files in scope. One implementer per checkout at a time.
5. **Gates, then proof steps**: the profile's gate commands for the touched repo. A failure is compared against the
   base before anyone calls it a regression. A gate with no command is `not covered`. Then the proof steps this task
   owns (`qa-walk.md`, "In the loop"); a failing step starts the fix round before any review agent runs.
6. **Review by tier**. Two scripts first, one after the other, nothing else touching the checkout until both exit:
   - challenge selection: `python3 ~/.claude/skills/challenge/scripts/hunks.py --base HEAD --intent tasks/<ID>/ac.md
     --out tasks/<ID>/challenge/T<N>` (`--pair <other repo>` when two repos changed). The script selects hunks in the
     stacks its `SKILL.md` lists (Drupal, Next.js, infra/CI files and per-language groups for other server code) and
     reports changed code no group claims as not covered. For that code the gate is `not covered: <stack>`, never
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
       `--base`; follow that skill for the Workflow call). Full packs for Drupal and Next.js, a generic shard for
       other server stacks: code it did not review (its `not_covered` list, or "nothing in scope" while the diff has
       code) gets the built-in `security-review`;
     - `claude-security`: per task the built-in `security-review` below; the plugin runs once, in the final review;
     - `security-review`: the built-in skill on the uncommitted diff. It covers security only, so report
       `not covered: perf, cache` beside its result; the reviewer's correctness lens carries logic;
     - `none`, or no tool reads the stack: `not covered: <stack>`.
     Docs or config text only = `skip`;
   - `challenge` with the same flags when the script selected hunks (full and light tier): the challenger asks, the
     implementer defends through SendMessage (no SendMessage: a fresh implementer gets the questions, the diff and
     the brief, and answers them), the challenger rules. Rejected answers join the fix round; escalated
     ones go to the final summary and the PR notes.

   **After a fix round** the same reviewer gets the next round through SendMessage (`task-review.md`, "Next round"):
   per accepted finding from every pass (review, security, challenge, revert) it says fixed or not fixed, and it
   reviews the lines the round changed. A finding it calls not fixed, or a new one I accept, starts the next round.
   Step 5 (gates and proof steps) and a failed revert check run again. Light tier: the session does the same inline. The
   reviewer cannot be reached (no SendMessage, a resumed session): the verifier gets one claim per accepted finding,
   "fixed at file:line", and a claim not CONFIRMED starts the next round.
   **Verifier** runs when the task wrote docs, an ADR, a guide or QA notes (claims from those texts), or a finding is
   disputed or about to be rejected. A fix round alone does not start it. Otherwise `skip`, "no claims". A finding I
   wanted to reject that is not REFUTED stands.
   Fix rounds: up to three by the same implementer, then a fresh one.

   Record `proof-steps`, `review`, `revert`, `secperf`, `challenge` and `verifier` for the task (`verdict.py record
   --task T<N>`). `--accepted` = findings this run of the pass produced that were accepted for a fix; it goes only on
   the record of a run that produced findings (0 when it found nothing), so `yield` counts runs, not re-records.
   After a fix round, re-record each pass with its new result: a pass that did not run again (the security review
   whose findings the reviewer confirmed fixed) gets `pass` with `--detail "fixed, confirmed in review round <K>"`
   and no `--accepted`.
7. **Controller check**: what agents could not do (a browser pass, headers on the wire, multi-instance assumptions).
   Full-tier task matching the visual trigger: the layout audit on the branch build (`visual-review.md`, per-task
   variant); findings join this task's fix round.
8. **Commit locally**: only the task's files, staged by name, the profile's `commit_format` and `commit_flags`, no AI
   footer unless the profile says otherwise. Update the ledger.

Mid-loop questions that change what is delivered stop this task and go to the user (`needs_me`), answer appended to
`ac.md` dated; everything about how to build it is a ruling in the ledger. While implementers work, write docs and
drafts for what is already done.
