# Project profile

Everything the flow needs to know about one project, in `.claude/run-task/profile.md` at the workspace root: the
repo's own root for a single-repo project, the directory that holds the repos for a multi-repo one. The flow reads it at Phase 0 and the retro
(`improve.md`) is the only thing that changes it, always after the user's yes.

A key the profile leaves empty is not guessed at run time: the gate that needs it reports `not covered: <key>` and
the retro asks for it.

## Template

```markdown
---
project: <name>
language: { chat: <language>, repo: English }
artefacts_dir: tasks/            # must be git-ignored or outside every repo
tracker: { type: jira|github|gitlab|none, key_pattern: "<regex>", write_policy: draft-then-approve }
models: { strong: <model>, coding: <model>, fast: <model> }   # names the Agent tool accepts
repos:
  - name: <name>
    path: <relative path>
    stack: <e.g. Laravel 12 / PHP 8.4, Next.js 16, Django 5>
    base_branch: <develop|main>
    remote: <name used for push>
    branch_pattern: feature/<ID>-<slug>
    commit_format: "<ID>: <what>"
    commit_flags: ""             # e.g. -n only when a hook enforces a foreign format; say why below
    gates:                       # one command each, run from the repo; empty = not covered
      lint: ""
      types: ""
      unit: ""
      integration: ""
      e2e: ""
      build: ""
    test_globs: []               # extra test-file patterns for scripts/revert-check (--test-glob)
    revert_pre: ""               # command run after each revert/restore, e.g. a container file sync
    conventions: []              # docs to read before writing code (paths)
    review_checklists: []        # paths of checklist files the reviewer reads (a skill's SKILL.md path counts)
security_review: secperf-review | claude-security | security-review | none
                                 # claude-security: final review of large tasks on stacks without a full secperf pack
plugins: []                      # plugins this project relies on, e.g. [typescript-lsp, security-guidance]
tooling_declined: []             # "<item> <date>": not offered again
smoke: []                        # whole-suite commands for Phase 5, per repo
local_stack: { run: "", urls: {}, cache_bypass: "", not_walkable: [] }   # run = how to start the product locally
qa_walk: { lib: "" }             # optional project helper library for scripts/qa-walk
visual: { trigger_globs: [], build: "", base_url: "", blockUrls: [], cookies: [] }
graduation: none                 # none | declined <date> | overlay <skill name>
---

## Base rules
<task families that branch off another base, drift checks; "none">

## Stack idioms
<how new code should look here, beyond the linters>

## Test layers
| Change | Test layer | Command |

## Trap checklist
<one bullet per trap: the trap, how to check it, the task that taught it>

## Topology
<production shape the reviewers must keep in mind: instances, caches, CDN, queues, shared storage>

## Extensions
<project steps keyed to a phase: "Phase 5: <step>, <command>, <when>">

## History
<date> | <ID> | <size> | <verdict> | lessons: <accepted numbers or none> | yield: <gate accepted/runs, ...>
```

## Bootstrap (no profile yet)

1. Detect without asking: repos (`git rev-parse` in the workspace and its direct subdirectories), remotes and the
   default branch (`git remote -v`, `git symbolic-ref refs/remotes/<remote>/HEAD`), commit message style
   (`git log --oneline -20`), stacks and their commands (`composer.json`, `package.json`, `pyproject.toml`,
   `Makefile`, `justfile` scripts, CI workflow steps), commit hooks (`.husky`, `grumphp.yml`,
   `.pre-commit-config.yaml`), the local app (`.env` app URL, `docker-compose*` ports, `.ddev`, `.lando*`, Sail, Herd),
   front-end paths for `visual.trigger_globs` (templates, components, styles), installed review skills that match a
   stack for `review_checklists` (e.g. `<stack>-code-review`), docs (`CLAUDE.md`, `AGENTS.md`, `README`, `docs/adr`),
   an existing secperf topology file (`.claude/secperf/project.md`). `models`: the strongest, a coding and a fast
   model the Agent tool offers. `security_review`: `secperf-review` when installed (it has Drupal, Next.js and a
   generic shard for other stacks), otherwise the built-in `security-review`. `smoke`: the full test suite command per
   repo. Gates the repo does not declare: `stacks.md`, with its rules (binary resolves, run once on the base, marked
   `# default`).
   **Tooling**: `tooling.md` (checked on every run, not only here).
2. Write the draft to `.claude/run-task/profile.md` with every proposed value marked `# detected` or `# guessed`,
   and list the gates that stay `not covered`. The run goes on with the draft (scope check included).
3. The scope-check message gets a short **Profile** block after the scope questions: the path of the draft, the
   `not covered` list, the missing tooling, the detected base branch, push remote, commit format and artefacts directory as one line to
   confirm, and questions only where detection found nothing or more than one candidate (base branch, remote, commit
   style, local app URL, chat language when the user's instructions do not say). One stop for both.
4. After the answers, fix the draft and drop the markers. The profile stays out of git through `.git/info/exclude`
   unless the user wants it committed for the team.
