# Retro and self-improvement (Phase 6)

After every run, also after `--analysis-only` and after a run the user stopped. The goal: the next run on this project
knows what this one had to discover, and a lesson that holds for every project reaches the core skill. Nothing changes
without the user's yes.

## 1. Collect lessons from this run's evidence

Read the ledger, the gate results and the chat. A lesson needs evidence from this run: a file, a command output, a
gate result or the user's words. Look for:
- **user corrections**: the user overruled a ruling, rejected a recommendation, said "not this", "shorter", "you are
  guessing", or answered a scope question differently than recommended;
- **discovered commands**: a gate or smoke command found by trial, a command that failed because the profile was
  wrong or empty, a step needed to make a check honest (a cache to bypass, a file sync, a seed);
- **late traps**: a problem found in the final review, the QA walk, the smoke or by the user that a checklist line
  would have caught at analysis;
- **coverage gaps**: every gate that reported `not covered`, with the stack and the tool;
- **scope drift**: an intent-check row `missing`, `unexplained` or `conflict`, a mid-loop scope question, an answer at
  the plan gate that the scope check should have asked at intake;
- **cost**: a step that took long or ran agents and changed nothing.

## 2. Classify each lesson

- **project**: true for this project only (a command, a trap, topology, a test layer, an extra step) goes to a section
  of the profile, or to `## Extensions` when it is a whole step keyed to a phase;
- **core**: true for any project (a scope-check lens that missed a kind of drift, a gate rule, a prompt that let
  something through, a new tracker adapter row) goes to a file of this skill;
- **tool**: a gap in a dependent skill or script (e.g. the security or challenge classifier does not know this stack)
  goes to that skill;
- **user**: a preference of the user about how the session talks or works, true in every project ("shorter gate
  messages") goes to the user's global instructions (e.g. `~/.claude/CLAUDE.md`).

A lesson with no evidence, or one that would not have changed anything in this run, is dropped. A correction of
something a rule already demands is a row only when the rule's wording let it happen; then the row tightens that
wording.

## 3. Propose, then apply on yes

One message, a table `# | lesson | evidence | target file and section | proposed text`, the proposed text exact and
short, in the target file's language. A value the run did not reveal (a service name, a path) is written as
`<needs: what>` and asked in the same message. The user answers per row (panel: `needs_me` `<ID>-retro`). Apply only
the accepted rows:
- profile rows: edit `.claude/run-task/profile.md`;
- user rows: edit the global instructions file the user named;
- core and tool rows: edit the skill where `~/.claude/skills/<skill>` resolves (installed by symlink it is the
  bundle's git repo). Check the change: a script change runs the script's selftest (and gets a new case for this
  lesson); a prompt or flow change gets one dry run, a fresh agent that reads the changed file with this task's inputs
  and says what it would do. Then one local commit in that repo per accepted row, message `retro <ID>: <lesson>`, so
  any lesson can be reverted. The skill installed as a plain copy: say which files to copy back to the source.
Then append one line to the profile's `## History`, also when no row was accepted:
`<date> | <ID> | <size> | <verdict> | lessons: <accepted numbers or none> | <output of verdict.py yield <T>>`.

**Prune.** Rules, passes and checklists only grow unless something removes them. When the last five History lines
carry a yield and a pass accepted 0 findings in all of them, the next retro proposes a row that narrows when it runs
(a tier, a trigger, a size), with the five counts as the evidence: a profile row when the pass is project-specific, a
core row otherwise. A pass that carries a hard rule (the final review, the QA walk, the negative control) is never
proposed for removal, only for a narrower brief.

## 4. Graduation to a project overlay skill

After the retro rows are answered, in a separate message, when the profile's `graduation` is `none` and one holds
(counted after this run's History line): the profile has at least one `## Extensions` step, its trap checklist has
grown past what fits a quick read, `## History` has five lines, or the user asks. Record the answer in `graduation`
(`declined <date>` or `overlay <skill name>`); a declined offer comes back only when the user asks.

The overlay is thin, never a copy of this skill, so core improvements keep reaching it. It lives at
`.claude/skills/<project>-task/SKILL.md` in the workspace; ask whether it is committed (the team shares the flow) or
kept local (git-ignored, or a workspace outside the repo):

```markdown
---
name: <project>-task
description: Use when a <project> task is to be analysed, implemented or fixed. Trigger on a <key pattern> key or "<project phrases>".
---

# <project> task

Run `Skill(run-task)` with the user's input; the profile `.claude/run-task/profile.md` applies.
Project steps, each at the phase named (moved here from the profile's Extensions):
- Phase 0: <step>
- Phase 5: <step>
Project-only options: `<word>` = <what it changes, at which phase>.
```

On graduation the steps move from the profile's `## Extensions` into the overlay (the section keeps one line naming
the overlay); the profile keeps the data (commands, traps, topology). Every place this skill runs "the profile's
extensions" reads the overlay's steps instead when `graduation` names one, so a run started through `/run-task`
directly behaves the same.
