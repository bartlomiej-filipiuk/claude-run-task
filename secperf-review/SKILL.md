---
name: secperf-review
description: Use after coding work to review the branch changes, or a PR/MR, for security (OWASP Top 10 2025, OWASP API Top 10 2023), performance that degrades with data growth, wrong or missing cache, logic anomalies (wrong result for a realistic input, contract mismatch, non-idempotent re-runs, code that misses its acceptance criteria), CI/container/edge config, and light WCAG 2.2 AA. Deepest checklists for Drupal 10/11 and Next.js (14-16, App or Pages Router); Laravel, Symfony, Django, FastAPI, Flask, Go, Rust, Rails, Java/Spring and other server code are reviewed in a generic shard labelled with the detected stack. Works across two repos of a decoupled project. Not for coding standards or style.
allowed-tools:
  - Bash
  - Read
  - Workflow
  - Agent
argument-hint: "[--drupal|--nextjs] [--only security,perf,cache,logic,a11y] [--base <ref>] [--pair <repo>] [--intent <ac-file>] [--path <dir>] [--exclude <glob>] [--out <dir>] [--deep] [<pr-url-or-number>]"
---

# secperf-review

Diff review for five risks: **security**, **performance over time**, **cache**, **logic anomalies**,
**accessibility (light)**, plus CI/container/edge config when such files change. Coding standards, style and
conventions are out of scope (`drupal-code-review`, `nextjs-code-review`, `code-review` cover them).

Every finder and verifier is a subagent with a fresh context: it gets the diff, the checklists, the project
context and (logic only) the acceptance criteria, never the planning or implementation conversation.

**Core principle:** a finding only counts if a line of real code proves it and a second model failed to
refute it. A short report that is all true beats a long one.

Invoking this skill is the user's opt-in to run the bundled workflow (`review.workflow.js`).

## Models

| Role | Model | Effort | Why |
|---|---|---|---|
| Orchestrator (you) | session model | session | runs the scripts, renders the report |
| Drupal / Next.js / generic / seam finders | Opus 5.5 | high | traces trust boundaries and cache metadata across files |
| Logic finder (per stack shard) | Opus 5.5 | high | traces inputs and states to a wrong result; reads the AC, not the plan |
| WCAG finder, infra finder | Sonnet 5.5 | medium | pattern-level checks on markup and config |
| Verifier (per finder, batched) | Opus 5.5 | medium (`--deep`: high) | refutes by default and has to quote the code that refutes |
| Final judge, `--deep` only | Fable 5.1 | medium | one batched call over critical/high findings |

Default runs never call Fable. Unresolved critical/high findings are reported as **disputed** with both
sides, and the tech lead decides.

## Step 1: Scope

Arguments: `--drupal` / `--nextjs` force one stack (default: autodetect). `--only` takes any of
`security,perf,cache,logic,a11y` (default: all). `--base <ref>` sets the diff base (`HEAD` = uncommitted changes
only). `--pair <repo>` adds the other repo of a decoupled project (e.g. `../react`): both diffs are reviewed in one
run and the seam finder checks what crosses between them. `--intent <file>` gives the logic finder the acceptance
criteria or spec, never the plan. `--path <dir>` limits the primary repo to one directory. `--out <dir>` keeps the
run files, the workflow copy and the report there (default: `<scratchpad>/secperf`; must be inside the project or
the scratchpad, see Step 3). `--exclude <glob>` (repeatable) leaves paths out. `--deep` adds Fable judgment and a deeper
verification pass.

**Per-repo config** (optional, `.claude/secperf/` in the repo root):
- `config.json`: `base` (used when `--base` is not given), `maxCommits` (default 40), `exclude` (list of regexes
  on repo-relative paths, e.g. generated files).
- `project.md`: topology and known traps (instances, caches, CDN, languages, deploy order). Every finder, the
  verifier and the judge read it first.

**Wrong-base guard:** when the diff spans more than `maxCommits` commits, `prepare.py` stops. That almost always
means a stale `origin/HEAD`; fix the base instead of passing `--force-wide`, unless the user asked for that range.

**Default target** is the current branch: commits since the merge-base with the default branch, plus staged,
unstaged and untracked files. When HEAD has no commits ahead, the review covers uncommitted changes, or the
last commit when the tree is clean. The script states which one it used.

**PR/MR target** (URL or number): review it in a throwaway worktree so the user's checkout is untouched.

```bash
S=<scratchpad>/secperf; mkdir -p "$S"
# GitHub
git fetch origin "pull/<N>/head:secperf-pr-<N>"   && BASE_REF=origin/$(gh pr view <N> --json baseRefName -q .baseRefName)
# GitLab
git fetch origin "merge-requests/<N>/head:secperf-mr-<N>" && BASE_REF=origin/$(glab mr view <N> -F json | python3 -c 'import json,sys;print(json.load(sys.stdin)["target_branch"])')
git worktree add "$S/wt" secperf-pr-<N>   # or secperf-mr-<N>
cd "$S/wt"                                # then run Step 2 with --base "$BASE_REF"
```

Remove the worktree and the branch at the end (`git worktree remove "$S/wt"`, `git branch -D secperf-pr-<N>`).

## Step 2: Prepare

```bash
python3 ~/.claude/skills/secperf-review/scripts/prepare.py --out "$S" [--base REF] [--pair ../other-repo] [--intent AC.md] [--stack drupal|nextjs] [--only ...] [--path DIR] [--exclude GLOB ...] [--deep]
```

The script prints a summary, writes `$S/args.json`, copies `review.workflow.js` to `$S` and ends with two lines:
`untracked included: …` and `workflow: <absolute path>`. It does the deterministic work: diff base, file
classification (Drupal incl. `.patch` files / Next / generic / a11y / manifests / infra incl. CI pipelines, Terraform
and edge function JS), exclusions (vendor, core, contrib, node_modules, tests, dev env, config `exclude`, `--exclude`),
1500-line shards per finder, versions from lockfiles, `composer audit` / `npm audit` when a lockfile changed, and
the project context files.

**Generic shard:** every changed source file that Drupal, Next.js and infra did not claim (`.php`, `.py`, `.go`,
`.rs`, `.rb`, `.erb`, `.java`, `.kt`, `.cs`, `.ex`, `.scala`, `.swift`, Jinja files, `.html` under a `templates/`
dir) goes to `generic`, labelled with a stack from the nearest marker file: `artisan` or `laravel/framework` gives
laravel, `symfony/framework-bundle` symfony, `manage.py` or Django in the Python manifests django, then fastapi and
flask, a Gemfile with rails gives rails, `pom.xml` / `build.gradle` java; otherwise the language (`go`, `rust`,
`python`, `php`, ...). Each generic shard holds one stack and is reviewed with `generic-security.md`,
`generic-perf-cache.md` and `logic.md`; the finder reads that stack's row of the per-stack table. Tests next to the
code (`_test.go`, `test_*.py`, `*_spec.rb`, `*Test.java`) stay out, like `tests/` dirs. Changed code that no group
claims (for example `.ts` outside a Next app, shell scripts) is listed as `notCovered` and reported under
"Nie sprawdzone"; it never disappears into the skipped count.

`--exclude GLOB` (repeatable) drops repo-relative paths; a directory name drops everything under it. Read the
`untracked included` line: untracked files from other sessions (scratch scripts, test reports) land in the review
unless excluded. When one is not part of this change, rerun with `--exclude` for it.

Tell the user in one line what will be reviewed: the base per repo, the file counts per stack, the stack label of
every shard (the `stacks` map, e.g. `generic-1: laravel`), how many finders will run, the `notCovered` files, and
the notes. Stop there if nothing is in scope. Each stack shard runs two Opus finders (secperf and
logic). If more than 8 Opus finders would run, ask whether to go ahead or narrow with `--path` / `--only`.

## Step 3: Run the workflow

Read `$S/args.json` and pass its content **as a JSON object, never a JSON string**, to:

```
Workflow({ scriptPath: "<the path from the `workflow:` line>", args: <args.json object> })
```

Never point `scriptPath` at `~/.claude/skills/…`: the Workflow tool only loads scripts from the working
directory, the scratchpad or an added directory, and rejects the skill directory. The copy in `$S` works when
`--out` is inside the project or the scratchpad (the default `<scratchpad>/secperf` is fine); any other `--out`
location is rejected, so keep it inside one of those.

It runs in the background, so wait for the completion notification. If the result is empty or strange,
read the run's `journal.jsonl` before drawing conclusions.

**Fallback when the Workflow tool is not available:** run the same roles with the Agent tool (`model: "opus"`
for finders and the verifier, `"sonnet"` for WCAG and infra). Reuse the prompts from `review.workflow.js` verbatim.
Effort is inherited from the session in that mode, so say so in the report.

## Step 4: Report

Chat in Polish, and the paste-ready comment in English. Use only what the workflow returned. Don't add
findings of your own and don't re-grade.

1. **Header, one line:** base per repo, the stack label per shard (`finders[].stack`), versions, finders and
   models used, audit status, whether the project context and the intent file were used.
2. **Verified positives:** one or two lines naming the controls the finders confirmed (from `positives`).
3. **Findings** (`findings`): table `# | Waga | Obszar | Plik:linia | Znalezisko | Status`. Show at most
   12. Put the rest under "Pozostałe" as one line each. Each finding shows its item id, taxonomy id, the
   quoted code, why it matters, and the fix. List `also` ids in brackets. Status is `confirmed` or
   `unverified`, and `unverified` also means the verifier failed or refused.
4. **Disputed** (`disputed`): the finder's claim and the verifier's missing evidence. The user decides.
5. **Notes** (`notes_low`): one line each, collapsed, unverified by design.
6. **Nie sprawdzone** (`notChecked`, skipped file count, infra files, failed finders, audits not run). Never
   leave this out, because silence reads as "covered".
7. **Odrzucone:** the count of `refuted` findings, plus a one-line reason for each when there are 5 or fewer.
8. **Paste-ready comment** in a ```text block. It's for the MR/PR or for a teammate. Plain English, short, no
   em dashes, no headers or bullet walls unless there are several findings. Start with the verdict, give the
   findings by number, and phrase disputed items as questions. Nothing is posted automatically.

A clean review is a valid result: "No security, performance, cache, logic or accessibility issues found in N
files", followed by the positives and the not-checked list.

**Save the run:** write the workflow result to `$S/result.json` and the Polish report from points 1-7 plus the
English comment to `$S/report.md`, then give the user both paths. Callers that keep a task ledger link to them.

## Red flags

- You add a finding that the workflow did not return, or you drop one without evidence.
- You report the refuted findings as findings.
- A dependency advisory is reported from `versions.md` instead of from the audit output. `versions.md` is a
  research snapshot from 2026-09-29, and it only gives hints.
- The not-checked section is missing.
- Something is posted to GitHub/GitLab/Jira without an explicit instruction.
- The run used `--force-wide` without the user asking for that range.
- A logic finding is reported without the input or state that produces the wrong result.

## Files

- `scripts/prepare.py` computes the scope and writes `args.json`.
- `review.workflow.js` holds the finder, verifier and judge orchestration with the prompts.
- `scripts/selftest.mjs` is an offline check of the orchestration logic with mocked agents
  (`node scripts/selftest.mjs`). Run it after editing the workflow.
- `scripts/prepare_selftest.py` checks `prepare.py` on a temp git repo (`python3 scripts/prepare_selftest.py`).
  Run it after editing `prepare.py`.
- `references/{drupal,nextjs,generic}-{security,perf-cache}.md`, `decoupled.md`, `logic.md`, `infra.md` and
  `wcag.md` are the checklists. The generic ones are stack-neutral and end with a per-stack signals table.
  Each item has signals, why, fix, "Not a finding when" and sources.
- `references/severity.md` is the rubric shared by all areas. `references/versions.md` holds the version
  and CVE notes, and they go stale, so refresh them separately.
