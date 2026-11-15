---
name: challenge
description: Use after coding work (yours or a subagent's), before commit or PR, when a diff removes or switches off behaviour that used to be guaranteed - deleted side effects (delete/save/invalidate), weakened guards or access checks, removed error handling, deleted test assertions, removed config registrations, features disabled by added code - and the change must be defended with evidence or fixed. Selects hunks in Drupal, Next.js and infra files and in PHP (Laravel, Symfony), Python (Django, FastAPI, Flask), Go, Rust, Ruby/Rails, Java/Kotlin/C#/Scala/Swift and Elixir code and tests; other changed code is reported as not covered. Works on a local git repo, also across two repos with --pair. Not a bug hunt and not a style review.
allowed-tools:
  - Bash
  - Read
  - Agent
  - SendMessage
argument-hint: "[--base <ref>] [--pair <repo>] [--intent <ac-file>] [--path <dir>] [--cap 5] [--out <dir>]"
---

# challenge

An independent devil's advocate for significant behaviour changes. A script picks the few hunks that remove a
guarantee; a fresh Fable agent asks what guarantees it now; the coding side must answer with evidence or fix;
the same Fable agent rules.

**Core principle:** a removal is fine when something else now provides the guarantee, or the acceptance criteria
say it is no longer wanted. The defense has to point at that replacement. A test that only proves the removal
happened is not a defense.

Invoking this skill is the user's opt-in to run the Fable challenger it describes.

## Roles

| Role | Who | Effort |
|---|---|---|
| Hunk selection | `scripts/hunks.py` (deterministic, no model) | - |
| Challenger and judge (one agent, continued with SendMessage) | Agent, `model: "fable"` | high |
| Defender | whoever wrote the code: the implementer subagent (via SendMessage), or you in session | - |

The challenger gets the brief, the code and the acceptance criteria. It never gets the plan, the implementer's
reasoning, or the defender's chat. The defender gets the questions only, never the challenger's reasoning.

## Step 1: Select hunks

```bash
S=<out dir, default <scratchpad>/challenge>; mkdir -p "$S"
python3 ~/.claude/skills/challenge/scripts/hunks.py --out "$S" [--base REF] [--pair ../other-repo] [--intent AC.md] [--path DIR] [--cap 5]
```

Scope, base resolution, `--pair`, the 40-commit wrong-base guard and per-repo `.claude/secperf/config.json`
come from secperf-review's `prepare.py` (same diff as secperf). The script scores hunks by what they remove:
side effects, guards, access/sanitise checks, throws, error handling, test methods and assertions, YAML
registrations; YAML lines judged by their key path in the base file (removed permissions, roles, required or
allowed entries and changed security switches are blocker-class; changed limits count, except widget and
listing settings in form/view displays and views); plus behaviour switched off by added code (module
replacement, skipped tests, TLS verify off, `enabled: false`, ignore pragmas); a removed or replaced
`extra.patches` entry in `composer.json` and a deleted or changed `*.patch` file (blocker-class, one hunk per
patch file; an added entry or new patch scores 0). Binary files (by git or by extension) are skipped.
Drupal, Next.js and infra files keep the original PHP/JS patterns. Files in secperf's `generic` group and the tests
of those languages (`_test.go`, `test_*.py`, `*_spec.rb`, `*Test.java`, `tests/` dirs) are scored in a separate
pass with a per-language row keyed by file extension: access guards (`$this->authorize()`, `Gate::`, `can()`,
`@permission_required`, `permission_classes`, `Depends(get_current_user)`, Go auth middleware and 401/403 paths,
`before_action`, `@PreAuthorize`, axum/actix auth extractors), side effects, error paths (`raise`, `panic`,
`if err != nil`, `rescue`), test definitions and assertions (`func Test`, `#[test]`, `assert_eq!`, pytest `assert`,
testify, RSpec `expect`, JUnit), skip pragmas (`#[ignore]`, `@pytest.mark.skip`, `t.Skip`, `@Disabled`) and access
switched off by added code (`@csrf_exempt`, `withoutMiddleware`, `skip_before_action`, `permitAll()`). Rust and
PHP 8 `#[...]` attributes, Python decorators and Java annotations are code there, not comments. Changed code that no
row covers (for example `.ts` outside a Next app, shell scripts) is printed as `not_covered` and listed under
"Not covered" in `candidates.md`. Moved lines, restructured guards with the same condition atoms and
comment-only edits score zero; a removed comment that is not replaced triples the score. Top `--cap` (default
5) go to `$S/brief.md`, with the enclosing function and its callers. Every hunk that scored but was not
selected (below threshold or beyond the cap) is listed in `$S/candidates.md`, so a later reviewer, not only the
regex, decides that it needs no question.

Tell the user in one line: base, candidates, selected, blocker yes/no, and the `not_covered` files if any (report
them as not covered, never as clean). **No selected hunks: stop.** Report "nothing to challenge" with the candidate
count and the `not_covered` list. Nothing else runs.

### Script-only run (whole branch, no challenger)

When a flow only wants the selection for a human or another reviewer (the final phase of `/run-task`),
run Step 1 alone and stop:

```bash
python3 ~/.claude/skills/challenge/scripts/hunks.py --base <integration branch> --out "$S" [--pair ../other-repo] [--cap 5]
```

It writes `$S/brief.md` (selected hunks with diff, enclosing function and callers) and `$S/candidates.md`
(every scored hunk that was not selected), plus `$S/hunks.json`. Both .md files are written even when nothing
is selected. Hand over both files; no model runs.

## Step 2: Challenge

One Agent call, `model: "fable"`, `effort: "high"`, prompt verbatim (fill the paths):

```text
You are an independent challenger. You did not write this code and you know nothing about how it was planned; that is on purpose. Your job is to make the author defend changes that remove a guarantee, not to hunt bugs or review style (other reviewers do that).

Read the brief: <S>/brief.md. For each hunk, read the code before the change (git -C <repo> show <base>:<path>) and after (the working tree), the enclosing function, the listed callers, tests near the code, and the intent file if the brief names one. If the brief says no intent is available, say so and do not infer intent from commit messages or comments written in this change.

For each hunk decide: does it remove or switch off something the old code made true (a key deleted on failure, an access check, a cache invalidation, an error path, a test pin, a registered plugin)? If yes, write ONE question:
"Old code guaranteed G: <quote, file:line in base>. Which code or test guarantees G now, or which acceptance criterion says G is no longer wanted?"
Add "What happens for <concrete input or state>?" when a specific case makes the risk concrete.
If the hunk is a restructure that keeps G, or the code right next to it plainly provides G, ask nothing and give the reason in one line.
Merge hunks that remove the same guarantee into one question. At most <cap> questions. Severity: blocker (data loss, security, a broken flow if unanswered), should-answer, note.
Do not propose fixes. Do not modify files.

Return only a JSON block:
{"intent_available": bool, "questions": [{"id": "Q1", "hunks": ["H1"], "file": "path", "line": int, "severity": "blocker|should-answer|note", "guarantee": "G in one sentence", "quote": "old code, file:line", "question": "..."}], "no_question": [{"hunk": "H2", "reason": "..."}]}
Keep your reading in mind; you will rule on the author's answers later in this conversation.
```

Save the JSON to `$S/questions.json`. Zero questions: report the `no_question` reasons and stop.

## Step 3: Defend

Send each question (id, file:line, guarantee, question; nothing else) to the defender. In `/run-task` that is
the implementer of the task via SendMessage; standalone it is you. The answer per question uses this schema and
nothing else:

```json
{"id": "Q1", "action": "defend | fixed | cannot-defend",
 "evidence": [{"type": "code | test | ac", "ref": "file:line | TestClass::method | AC quote", "shows": "one sentence: how this provides G now"}]}
```

Rules for the defender, given with the questions:
- Evidence must show the replacement guarantee (or the AC line dropping G), not the removal itself.
- A test counts only if it asserts the new guarantee. A test asserting "the old call no longer happens" is not
  evidence.
- "Cleaner", "equivalent", "never needed" without a ref are not evidence.
- `fixed` means the code changed; evidence then points at the fix and its test.
- When you cannot point at the guarantee, answer `cannot-defend` and fix, or leave it to the human.

Save to `$S/defense.json`.

## Step 4: Rule

SendMessage to the same challenger agent:

```text
Here are the author's answers: <defense.json content>. Rule on each question. Open every ref and check that it shows G (or that the AC line drops G). Accept only then. Reject when the evidence only proves the removal, when a ref does not say what is claimed, or when the answer is "cleaner/equivalent/never needed" without a ref. Escalate when only a human can decide (a product decision, an ambiguous or missing AC). Return only JSON: {"rulings": [{"id": "Q1", "ruling": "accept|reject|escalate", "checked": "what you opened", "reason": "one sentence"}]}
```

Rejected questions go back to the defender once (fix or better evidence), then one more SendMessage ruling on
those only. Whatever is still rejected after that is escalated. Save to `$S/rulings.json`.

## Step 5: Report

Chat in Polish, file `$S/report.md`:
1. One line: base, candidates/selected hunks, questions, accepted / fixed / escalated.
2. Table `# | Waga | Plik:linia | Gwarancja | Obrona | Werdykt`.
3. **Do decyzji człowieka:** escalated items with the question and both sides, one line each.
4. Paste-ready English block "Questions for the reviewer" with the escalated items only, for the PR description.

## Red flags

- Running the challenger when `hunks.py` selected nothing.
- Giving the challenger the plan, the ledger or the implementer's summary.
- Paraphrasing a defense into something stronger than the defender wrote.
- Accepting a ruling the challenger did not return, or re-asking until it accepts.
- `--force-wide` without the user asking for that range.

## Files

- `scripts/hunks.py` - hunk selection and brief; imports `prepare.collect()` from the sibling
  `secperf-review/scripts` (both skills installed side by side), falling back to `~/.claude/skills/secperf-review`.
- `scripts/hunks_selftest.py` - builds two temp repos (Drupal: binary fixture, composer patches, `.patch` files, a
  removed access check; polyglot: Laravel, Django, pytest, Go, Rust, Next.js, a shell script) and checks the
  selection, including that Drupal and Next.js hunks score exactly as before; run it after changing the scorer.
