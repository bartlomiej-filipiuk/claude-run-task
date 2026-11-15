# QA walk and verdict (Phase 5)

The last check of a task, the source of the QA note and of the go/no-go. Every step a tester will be asked to do is
first done by us, by script, through the real app on the local stack (admin forms, pages, API, CLI). A step is chosen
so that it fails when the task does not work; a step that can only pass proves nothing.

Tool: `~/.claude/skills/run-task/scripts/qa-walk/` (`run.mjs`; step schema and the lib contract in its README). The
project's helper library (logins, form helpers, state capture and restore) is the profile's `qa_walk.lib`; without
one, steps use Playwright or plain HTTP and CLI calls directly. Writing a lib the first time is a retro lesson.

## Steps are fixed at the plan gate, not after the code

The gate lists at least one proof step per AC: where the tester acts, where they look, what they see, and what the
same step shows today on the base. The user approves them with the plan. When no step can tell "works" from "does not
work" for an AC, it is an open question at the gate: another proof (an API call, a command, a log entry) or a
rewording. After the code is written the steps may get more precise, never weaker.

## Two kinds of step

| kind | question | with the change | without the change |
|---|---|---|---|
| `proof` | does the task do what the AC says? | pass | must fail, the way `withoutChange` predicts |
| `regression` | does what worked before still work? | pass | not run |

A proof step that passes without the change is not a proof: tighten it, or relabel it `regression`, and then that AC
has no proof yet.

An AC that asks for an artefact rather than a behaviour (a demo recording, a document, a diagram, a migration report)
is proved by the artefact itself: it is produced in Phase 5, linked under Deliverables in `summary.md`, and needs no
step and no negative control. It is not an open question at the plan gate.

## Order of work (after the fix wave and the full gate run)

1. Write `tasks/<ID>/qa-walk/steps.mjs`. `where`, `surface` and `expect` are the sentences that go into the QA note;
   write `expect` from what the run shows, not from what the code suggests.
2. Run with the change: `node ~/.claude/skills/run-task/scripts/qa-walk/run.mjs tasks/<ID>/qa-walk/steps.mjs
   [--lib <profile qa_walk.lib>]`. Every step must pass. A failing step is a finding for one more fix round; when the
   step itself was wrong, correct the path or the wording, never the pass condition to fit the result.
3. Negative control, once per touched repo, proof steps only, through `scripts/revert-check/` with `--base <BASE>`
   and the profile's `revert_pre` (command in the qa-walk README). Nothing else touches that checkout meanwhile. `fail`
   in the predicted way is the proof; `error` is not a fail. State a file revert does not undo (imported config, a
   migration that ran, stored records) is undone and redone in `--pre`, or the step gets "no negative control:
   <reason>" and becomes a verdict condition.
4. `run.mjs --table result.json result-without.json > tasks/<ID>/qa-walk/proof-table.md`.
5. Checks that cannot run locally (the profile's `local_stack.not_walkable`, remote caches, SSO, third parties) are
   not steps: they go into the `notWalked` export with who checks them (`tester` on a shared environment, `owner`
   for what only the task owner can do).
6. `run.mjs --print-qa steps.mjs` is the body of the QA note; `--print-conditions` gives the list for the verdict.
   Nothing is in the note that is not in the steps file.

Local safety: switch off anything a local submit would send to a live third party (CRM, mail, payments) and restore
it after; capture every edited text, setting and record before the edit and write it back after.

No way to run the product locally (the profile's `local_stack.run` and `local_stack.urls` both empty) while the task
has a visible or measurable outcome: `qa-walk` = `not covered`, every proof step becomes a verdict condition for a
tester. A CLI or a library is run through its command or its tests, not a URL.

No visible or measurable outcome (docs only, CI only, a refactor with no behaviour change): `qa-walk` = `skip` with
the reason, and the verdict rests on the gates and the reviews.

## Verdict

First block of `summary.md` and of the final message. First line is one of the three words, then the proof table,
then the conditions or the reasons.

| verdict | when |
|---|---|
| **GO** | every AC and decision has at least one proof step that proves (pass with, fail without); every regression step passes; gates are green or equal to the base; smoke is green or every failure also fails without the change; the intent check has no `missing` and no `unexplained` row; no open blocker or major from any review |
| **GO with conditions** | as GO, but something named is left to a human: a not-walked step that decides an AC, a proof without a negative control, a manual rollout step, a deferred question, a test or gate command that is `not covered` for code the branch changes. Each condition says what, who, where and what they should see; tester conditions go into the QA note, the rest are `needs_me` items |
| **NO-GO** | an AC with no proving step, a failing step, a red gate that is not the baseline, a smoke test that passes without the change and fails with it, an open blocker or major |

A review that is `not covered` (challenge, perf and cache, visual, change map) is listed under Gates in `summary.md`
and is not a condition by itself.

Never round up: one missing proof is a condition or a NO-GO, not a footnote under GO. The verdict says whether the
task does what was asked; it does not replace QA.
