---
name: run-task
description: Use when a development task is to be analysed, implemented or fixed end to end in any project - given a tracker key or URL (Jira, GitHub, GitLab issue) or a pasted task description. Trigger on "/run-task", "zrób taska", "przeanalizuj taska", "fix <KEY>", "run this task", or a project overlay skill that hands over to it.
---

# Run a task end to end

Takes one task from intake to a proved, reviewed, locally committed change, in phases with user gates. The flow is
universal; everything that belongs to one project (repos, commands, base branch, traps, topology, extra steps) lives
in that project's profile, `.claude/run-task/profile.md` (contract in `profile.md` next to this file). Each run ends
with a retro that improves the profile and, with the user's approval, this skill (`improve.md`).

Files next to this one are read when their phase starts, not up front.

## Hard rules

- **We build only what the user confirmed.** A question that changes what is delivered (an AC, the scope, who sees
  it, the proof of an AC) goes to the user at whatever phase it appears. It is never settled by a ruling.
- **User gates.** (0) intake: blocking scope questions answered before any analysis agent; (1) plan: approved with
  every open question answered or explicitly deferred, before any code change; (2) result: the user reviews and
  merges. No gate is skipped, also when the user asks for speed: then ask shorter, with a recommendation per question.
- **No push and no tracker write** (comment, transition, new issue) without an explicit request. Commits are local,
  in the profile's format, without an AI footer unless the profile says otherwise.
- **One branch per repo**, named by the profile's pattern, off the profile's base fetched from its remote. Never work
  on the base branch. Before the first branch in a repo, `git status --porcelain` must be empty: uncommitted changes go
  to the user (commit, stash or stop), never into the task's diff.
- **Script commands use absolute paths.** `<T>` is the absolute path of `tasks/<ID>/`; every script runs after
  `cd <absolute repo path>`, so its output never lands inside a repo by accident.
- **Stage files explicitly**, never `git add -A`: formatters and hooks leave unrelated churn.
- **Never assume a test failure is a regression**: run it on the base first (`scripts/revert-check/`).
- **Every gate reports a result**: pass, fail, baseline (fails on the base too), skip with a reason, or
  `not covered` when the profile or the tooling cannot check this stack. `not covered` is never shown as a pass.
  Each result is recorded with `scripts/verdict/verdict.py record`, which stamps the commit of every touched repo; a
  result describes that commit only. The verdict is never above what `verdict.py check` allows; its one exception,
for a gate that stays missing or stale after a re-run, is in `qa-walk.md` ("Verdict").
- Chat in the language the profile or the user's instructions name; code, comments, docs and commits in English
  unless the profile says otherwise.

## Inputs and options

`/run-task <input> [--analysis-only] [--size=trivial|standard|large]`. `<input>` is a tracker key, an issue URL or
pasted text; `intake.md` turns it into a task id `<ID>` and `tasks/<ID>/source.md`. Options are read only as flags,
never from words inside pasted text. A project overlay skill (`improve.md`, "Graduation") may hand over with its own
options; it names the phase each one changes.

**Resume.** When `tasks/<ID>/` already exists, read `ac.md`, `gate.md` and `ledger.md` and continue at the first phase
whose artefact is missing; the ledger's first line always holds the current phase, task and step. Say where the run
resumes before doing anything. A run resumed in Phase 5 first runs `verdict.py check`: a gate it lists as missing or
stale runs again, whatever artefacts exist.

Artefacts go to `<artefacts>/<ID>/` (profile key `artefacts_dir`, default `tasks/` at the workspace root). The
directory must be ignored or outside every repo, or review scripts will read it as part of the change; inside a repo
use `.git/info/exclude`, which changes no tracked file.

## Roles and models

`roles.md`: who does what, the model class per role, the agent prompts. In short: the strongest model for scope
check, decider, approach check, reviewer, final review and verifier; a coding model for the implementer; a fast model
for diggers and scouts. The profile maps classes to model names. A model that is not available falls back to the
session model, said once in the gate message.

## Phase 0 - Intake

1. Fetch the task with the adapter for its input (`intake.md`), comments included. Save the whole source to
   `tasks/<ID>/source.md` (the artefacts directory: the profile's, or `tasks/` at the workspace root before there is
   one, added to `.git/info/exclude` at once when it sits inside a repo) and the description plus AC verbatim to `tasks/<ID>/ac.md`. `ac.md` is the intent file
   every reviewer reads: intent only, never the plan. Intake and the plan gate append the user's decisions to it.
2. Load the profile. None found: draft it by detection (`profile.md`, "Bootstrap") and go on with the draft; its
   questions go into the same message as the scope questions, so the user is stopped once. A drafted profile always
   waits for the user's confirmation, also when the scope check has no question.
3. Identify the repos the task touches; read the docs the profile and the source point at.
   **Tooling check** (`tooling.md`): helper skills, the LSP plugin and binary of each touched stack,
   `security-guidance`, the tracker CLI and the gate tools. Missing items go into the first message with their
   install commands and are installed after the user's yes.
4. Run the profile's base rules (a task family on another base branch, a drift check) and the Phase 0 extensions
   (the profile's, or the overlay's when `graduation` names one).
5. **Scope check** (`scope-check.md`, always): scout the files inline, then one fresh agent on the strongest model
   lists every point where the delivered change can drift from what the task's authors mean. Blocking points go to
   the user in one message, then stop. Answers go to `ac.md` as `## Decisions at intake`.
6. Propose the size in the scope message and re-check it after the answers: **trivial** (one repo, one internal task, no new boundary, no
   blocking points left), **standard**, **large** (new module, service, table, endpoint or package; several repos;
   a third-party integration such as payments or an external API; or a manual step on a remote environment). The
   user can change it.

## Phase 1 - Analysis

Reuse the Phase 0 anchors; every agent reads `ac.md` and `scope-check.json`, and a question answered there is never
asked again.
- **trivial**: analysis inline, no agents.
- **prior analysis exists** (an estimate, a scan, an earlier `tasks/<ID>*`): one strongest-model agent verifies
  every load-bearing claim against the current code, walks the profile's trap checklist, lists gaps and decides.
- **otherwise**: diggers (fast model, one per repo side) in parallel, then one strongest-model decider that
  spot-checks every load-bearing digger claim, walks the trap checklist and decides. Diggers start in one message,
  as parallel Agent calls.

Digger output `{facts, files, fix_options, risks, open_questions}`, every fact with file:line. Decider output
`{verified, refuted_or_corrected, recommended_fix, alternatives_rejected, architecture_ruling, implementation_steps,
internal_task_breakdown, test_plan, qa_steps, not_walkable_locally, rollout, risks, open_questions_for_user,
follow_ups}`:
- `alternatives_rejected` `[{option, why_rejected, evidence}]` always answers "no code: config, content or a process
  change" and "reuse what the codebase already has";
- `internal_task_breakdown` gives each task a review tier (`loop.md`);
- `qa_steps` `[{ac, where, expect, without_change}]`: at least one proof step per AC, a step that fails when the task
  does not work; an AC with no such step is an open question;
- `open_questions_for_user` `[{question, options, recommended, if_wrong}]` merges the diggers' questions after
  checking the code: a question the code answers becomes a verified fact;
- `test_plan` uses only the commands in the profile; a check the profile has no command for is `not covered`.

**Approach check** (`approach-check.md`): size large, or the plan adds a module, service, plugin, entity, table,
endpoint, package or a shared UI component used in several places, or needs a manual step on a remote environment. Otherwise `skip` with the
reason.

## Phase 2 - Plan gate

Write the full gate to `tasks/<ID>/gate.md`. The chat message carries the plan in at most five short bullets, the
open questions, the assumptions, the proof table, the task breakdown table and a link to `gate.md` for the rest.
`gate.md` holds:
- verified facts, what was refuted, ONE recommended fix;
- **Considered alternatives**: the decider's rejected options plus the approach check's alternatives and weak points
  with my ruling, one line each (option, why not, evidence);
- implementation steps, test plan;
- **How we will prove it works**: table `AC | step | what the tester sees | what the same step shows today on the
  base`, with the steps that cannot run locally listed under it;
- **Open questions**, always present ("none" when empty), numbered Q1...: the decider's questions, every AC without a
  proof step, an approach check that ended in "user decides", every intake question the user deferred. Each with its
  options and a recommendation in one line. Under it **Assumptions**: what the plan assumes without the user having
  said so;
- internal task breakdown `task | tier | what this tier skips`, risks, follow-ups for separate tracker items.

**Stop and wait.** Approval counts only when every open question has an answer or an explicit deferral (it becomes a
verdict condition). A bare yes with questions open gets one follow-up naming them ("I take the recommendations for Q2
and Q3?"). An AC without a proof step is never deferred silently: the user rewords it, accepts a manual proof, or
drops it. With `--analysis-only` the run ends here, after the retro.

After approval append `## Decisions at the gate` to `ac.md`: chosen option (what, not how), out of scope, answers,
changed or dropped AC, the approved proof step per AC as what the tester sees. No files, steps or task breakdown.

## Phase 3 - Plan

`tasks/<ID>/plan.md`, written by the session: small internal tasks, each one coherent unit of code plus its own test
plus its own review, with its tier, the files in scope, the test to write first, the proof steps it makes pass and
the gates to run. Not
`superpowers:writing-plans`: it saves plans inside the repo, adds a commit per step and hands over to its own executor,
which conflicts with this loop. Ledger in `tasks/<ID>/ledger.md`:
its first line is `phase | task | step`, updated at every step (it is what a resumed run reads); below it every
ruling I make on the user's behalf, one line each, repeated in the final message.

Then, before any code:
1. Create the branch in every repo the plan touches (`loop.md` step 1) and start the local stack on it.
2. `python3 ~/.claude/skills/run-task/scripts/verdict/verdict.py init <T> --repo <abs path> ... --task T1 ...`.
3. Write `tasks/<ID>/qa-walk/steps.mjs` from the approved proof table and run its proof steps on the fresh branch,
   which still equals the base (`qa-walk.md`, "Steps before the code"). Every proof step must fail the way its
   `withoutChange` says; one that passes or errors is fixed now, before an implementer relies on it.

## Phase 4 - Per-task loop

`loop.md`, for every internal task, no exceptions. A new question mid-loop that changes what is delivered stops that
task and goes to the user; independent tasks continue.

## Phase 5 - Final review and verdict

`final.md`: whole-branch review, intent check, security review, visual review when triggered, one fix wave, smoke,
QA walk, verdict, deliverables. Never skipped for a task with a code or config change.

## Phase 6 - Retro

`improve.md`, always, also after `--analysis-only` and after a stopped run: lessons with evidence, proposed profile
and skill changes, applied only after the user's yes; the graduation offer when its condition holds.

## Progress panel

When a `task_progress` tool is available, report as `panel.md` describes; otherwise skip the calls silently. A manual
step for the user is reported there as `needs_me` and always also written in the chat.
