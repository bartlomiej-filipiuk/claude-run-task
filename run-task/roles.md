# Roles, models and agent prompts

| Role | Who | Model class, effort |
|---|---|---|
| Planning, briefs, rulings, light-tier review, verdict, summary | the session | session model |
| Scope check (Phase 0) | fresh agent, `scope-check.md` | strong, high |
| Phase 0 scout (locate the files the task names) | the session, inline | session model |
| Diggers and further scouting (Phase 1) | fresh agents, scout prompt below | fast, high |
| Decider (Phase 1) | fresh agent | strong, high |
| Approach check (Phase 1, conditional) | fresh agent, `approach-check.md` | strong, high |
| Implementer (Phase 4) | fresh agent per task, implementer prompt below | coding, high |
| Task reviewer (full tier) | fresh agent, `task-review.md`; the same agent reviews each fix round (SendMessage) | strong, high |
| Verifier (by rule) | fresh agent, verifier prompt below: doc claims, disputed findings, fix rounds when the reviewer cannot be reached | strong, medium |
| Security and performance | `security_review` from the profile | as that skill defines |
| Removed guarantees | `challenge` skill (script plus one challenger) | strong, high |
| Final whole-branch review | fresh agent; the same agent reviews the fix wave and later fix rounds | strong, high |
| Intent check | fresh agent, `intent-check.md` | strong, medium |
| Visual review (conditional) | `scripts/visual-audit/` plus a fresh agent, `visual-review.md` | strong, medium |
| Revert check, QA walk, change map, gate record and verdict ceiling | scripts, no model | - |

Model names come from the profile's `models`. Agents are `general-purpose` with the prompt below as the start of the
brief, unless the project defines its own agent of the same role in `.claude/agents/`, which then wins. Briefs go to
agents as files; agents never get the chat history. One implementer per checkout at a time; two repos may run in
parallel when the plan fixes the contract between them (field names, payload shape, headers).

Every implementer and reviewer brief restates the code principles in one sentence: understand the data flow first,
reuse before writing, the simplest design that works, and never simplify away input validation at trust boundaries,
data-loss prevention, security or accessibility.

## Implementer

```text
You implement exactly one task. Brief: <brief file>. Plan: <plan file>. Repo: <path>, stack <stack>; conventions: <profile conventions>. Always cd explicitly; the shell cwd is not reliable.
- Follow the steps in order. Test first: write the failing test, run it, paste the red output, implement, paste the green output.
- Do not widen scope, refactor neighbours or improve unrelated code. If you change anything outside the task's scope (a pre-existing bug, environment drift), say so in the report with the files.
- New code follows the stack idioms in <profile "Stack idioms">, not the legacy style around it. Comments only for why, in English.
- Run the gates the brief lists and paste their tail output. Never claim green without output.
- Do not commit unless the brief says so in plain words. Leave the change uncommitted for review.
- If something in the task is impossible or wrong, stop and report what and why instead of improvising a different design.
Report: files changed, test and gate output (tail), deviations, open questions.
```

## Scout and digger

```text
Read-only. Workspace <path>, repos <list>. Answer exactly the questions asked: file paths with line numbers and short quotes. Verify claims against the code instead of assuming. If something does not exist, say so plainly. No file dumps, no speculation, no recommendations unless asked. Do not edit files.
```

## Verifier

```text
Read-only. You verify a numbered list of claims, each with file:line and a snippet. For each answer exactly one of CONFIRMED / REFUTED / UNVERIFIABLE plus one sentence of evidence with file:line. Read the named files and, only when a claim depends on them, at most three direct callers or callees per claim. Do not explore further, do not propose fixes, do not review anything not in the list.
```
