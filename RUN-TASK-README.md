# run-task bundle

A project-independent task flow for Claude Code: intake with a scope check, analysis, a plan gate, a per-task loop
with tests and reviews, a final review with a scripted QA walk and a GO / NO-GO verdict, and a retro that improves the
project profile and the skill itself.

## Contents

| Directory | What |
|---|---|
| `run-task/` | the flow (`SKILL.md` plus one file per phase or prompt) and its scripts: `revert-check`, `qa-walk`, `visual-audit`, `verdict` |
| `secperf-review/` | security, performance, cache and logic review of a diff (Drupal, Next.js, and a generic shard for Laravel, Symfony, Django, FastAPI, Flask, Go, Rust, Rails, Java) |
| `challenge/` | asks for evidence when a diff removes a guarantee (side effect, guard, assertion) |
| `change-map/` | change map of a branch for the PR reader |
| `qa-notes/` | QA notes from a finished task |

## Install

This directory is a git repo. Install by symlink, so the retro's improvements land in the repo as commits and can be
reverted:

```bash
for s in run-task secperf-review challenge change-map qa-notes; do
  [ -e ~/.claude/skills/$s ] && mv ~/.claude/skills/$s ~/.claude/skills/$s.bak-$(date +%F)
  ln -s "$PWD/$s" ~/.claude/skills/$s
done
```

Existing copies of the helper skills are moved aside, not deleted; compare them before removing the backups.

## Requirements

- git, python3, node 20+.
- Per project, as needed: Playwright in the front-end repo (`qa-walk`, `visual-audit`), `ffmpeg` (montages; skipped
  without it), `mmdc` (`change-map --svg`).
- Per tracker: `twg` CLI or the Atlassian MCP (Jira), `gh` (GitHub), `glab` (GitLab). Pasted text needs nothing.
- Recommended plugins (official marketplace; `run-task` checks them on every run and offers to install what is
  missing, see `run-task/tooling.md`): the LSP plugin of each stack you work in (`typescript-lsp`, `pyright-lsp`,
  `php-lsp`, `gopls-lsp`, `rust-analyzer-lsp`, ...) with its language server binary, and `security-guidance`. Run
  `security-guidance` with its per-turn review off, `ENABLE_STOP_REVIEW=0` in the `env` block of
  `~/.claude/settings.json`: the flow has its own reviews, and that review costs one model call per turn. Its edit-time
  pattern warnings and commit review stay on.
- Optional: `claude-security` (profile `security_review: claude-security`), a panel mod exposing `task_progress`.

## First run in a project

`/run-task <tracker key | issue URL | pasted text>`. Without `.claude/run-task/profile.md` the skill detects repos,
branches, stacks and commands, shows a draft profile, asks what it cannot detect, and writes it after your yes.

## Limits

- `secperf-review` and `challenge` have full packs for Drupal and Next.js and a generic shard with per-stack rows for
  Laravel, Symfony, Django, FastAPI, Flask, Go, Rust, Rails and Java. Code no group claims is reported as
  `not covered`. `change-map` still reads only Drupal and Next.js. Stack defaults for gates: `run-task/stacks.md`.
- After a few runs the retro offers a thin project overlay skill (`<project>-task`) that hands over to `run-task` and
  carries the project's own steps.
