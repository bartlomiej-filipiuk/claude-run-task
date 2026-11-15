---
name: change-map
description: Use when a branch, task or pull request needs to be understood quickly by a human reviewer - "pokaż co się zmieniło", "graf zmian", "mapa PR-a", "change map", before writing a PR description, or at the end of a task - on a Drupal and/or Next.js repo, also across the two repos of a decoupled project, also for a task that is already merged.
allowed-tools:
  - Bash
  - Read
  - Agent
argument-hint: "[--task <KEY>] [--base <ref>] [--pair <repo>] [--path <dir>] [--svg] [--html] [--title <text>] --out <file.md>"
---

# change-map

A reviewer's map of a change in two layers. The top layer is written for a human reading the PR for the first
time: what the change does, where to start the review, 3-5 flows (who starts what, which files take part),
the shipped settings and deploy needs in plain words. The bottom layer is the deterministic file map: entry
points, references between changed files, the Drupal - Next seam.

The script builds the graph; one Sonnet pass writes the top layer as JSON that may only name the script's node
ids; the script validates it and draws every diagram. A flow step between two files is drawn solid only when
the graph has a direct reference between them, otherwise dotted ("read from the code, check it").

Invoking this skill is the user's opt-in to the one Sonnet pass. Skip the pass (file map only) when the user
asks for "tylko graf" or the change has fewer than 4 code files.

## Run

```bash
python3 ~/.claude/skills/change-map/scripts/map.py --out <file.md> [--base REF] [--pair ../other-repo] [--path DIR] [--svg] [--title "KEY title"]
# a finished task, in any state of your checkout:
python3 ~/.claude/skills/change-map/scripts/map.py --task PROJ-153 --pair ../react --svg --out <file.md>
```

`--task KEY` finds the task on `--branch` (default `develop`): its PR merge commits (`Merged PR …: KEY…`), else
its own `KEY:` commits on the first-parent line, else the newest local branch named after it. It maps that range
on temporary detached worktrees (removed afterwards; your checkout is untouched). When other work landed between
the task's merges, the map is limited to the files the task itself changed and the header lists the foreign
commits. A repo with no trace of the task is skipped and named in the header.

`--committed [REF]` maps only committed changes up to REF (default `HEAD`) on a temporary detached worktree,
so local uncommitted edits and untracked files in your checkout stay out of the map. Use it at the end of a task
when the working tree holds unrelated changes.

`--svg` renders the graph with `mmdc` (`npm i -g @mermaid-js/mermaid-cli`) to `<out>.svg` next to the Markdown
and links it, for viewers or PR tools that do not render Mermaid.

Scope, base resolution, `--pair`, the 40-commit wrong-base guard and `.claude/secperf/config.json` come from
secperf-review's `prepare.py`, so the map shows the same diff as secperf and challenge. Docs are counted, not
drawn. Tests are drawn with dotted edges to what they exercise.

What the script reads (deterministic):
- **Entry points:** routes and services (`*.routing.yml`, `*.services.yml`), hooks / update / deploy hooks in
  `.module` `.install` `*.post_update.php` `*.deploy.php`, controllers, forms, plugins, event and route
  subscribers, drush commands, new modules, settings files, config objects, Next pages and API routes.
- **Edges:** PHP class references and `use`, services.yml `class:` and `@service` / `\Drupal::service()` DI,
  TS imports (`~/` = `src/`, relative, `@ffw/*` = `utils/packages/*`).
- **Seam:** Drupal bundle config vs React `registry.set("<bundle>--…")` components, `x-*` header names changed
  on both sides, Drupal route paths that appear in changed React files.
- Three or more config files of one family (`user.role.*`) become one node; their changed lines (permissions,
  settings) are listed under "Files by area". More than 45 nodes collapse to one node per area.

## Steps

1. Graph: run the script with `--json "$S/graph.json"` and a throwaway `--out`. Same scope flags as the final
   run (`--task` or `--base`, `--pair`, `--path`). Stop if `files` is 0 and say so.
2. Stories: one Agent call, `model: "sonnet"`, `effort: "high"`, the prompt below verbatim (fill the paths;
   intent file = `tasks/<KEY>/ac.md` or `spec.md` when it exists, otherwise drop that sentence). Save the
   returned JSON to `$S/stories.json`.
3. Final: run the script again with the same scope flags plus `--stories "$S/stories.json" --svg --html --out
   <file.md>`. `flow_warnings` in its output lists steps it dropped (unknown node ids); report them.
4. Tell the user in one line: flows, files, dotted (inferred) steps, warnings, and the paths of `.md`, `.svg`,
   `.html` and `flow.json` (written next to the map; the Herdr task window draws the flows from it). Open the `.html` when the user asked to see the map (`open <file>.html`).

```text
You write the reader-facing part of a "change map" for a pull request, so a reviewer understands the change at first glance. A script already built the graph of changed files; you explain it as flows. You do not review the code and you do not judge it.

Read the graph: <S>/graph.json
Each node is one changed file with a short id (F1, F2, ...), its entry points (hooks, routes, services, plugins, config), symbols, config_changes, and the exact commands to see its diff (diff_cmd) and its content after the change (show_cmd). Run those commands for the files you need. Optional intent context: <intent file> (use it to name what the change is for; describe what the code does, not what the spec hopes).

Rules:
- Every file you mention must be referenced by its node id from graph.json. Never invent a node id. Actors (who or what starts a flow) are plain names of at most 30 characters, e.g. "Editor", "Admin", "Deploy", "Cron", "Visitor".
- 3 to 5 flows. Each flow is one thing that happens at runtime or at deploy. At most 8 steps per flow. Use "kind": "sequence" for an interaction between a person and the system, "flow" for everything else.
- A step goes from one participant to the next ("from"/"to" = node id or actor) with a short text of at most 12 words saying what happens, in plain words, present tense, and "call": the function, method or hook the "to" side runs for that step as the code names it (e.g. "HtmlSanitizer::sanitize()", "hook_entity_presave()", "useBanner()"), read from the diff or the file; "" when no single call does it. Never invent a name that is not in the code. And "detail": one or two sentences of at most 40 words on what that code does in this step (the condition it checks, what it changes or returns), read from the code.
- Each flow also gets "summary": two or three sentences on what happens in it and why it matters.
- labels: for every node you use, a plain-words role of at most 6 words, not the file name.
- roles: for every node you use, one sentence of at most 20 words on what this file does in this change.
- tldr: 3 to 5 bullets of at most 20 words each: what changes for whom, the main risk, what a person must do after deploy (if anything). No file names.
- checks: the checks and validations the changed code performs (access and permission checks, input validation, guards against stale or concurrent data, transactions and rollback, error handling, cache or security headers), at most 8, one sentence each, with the node ids. Only what the code shows; an empty list when there are none.
- summary: 3 to 5 sentences for a reviewer who has not seen the task. What changes for users and editors, and the main moving parts.
- review_order: 3 to 5 nodes, most risky first (access and security, then data and config, then UI), each with one sentence why.
- settings: what the shipped config means in plain words, with the node ids it comes from. Read config_changes and the diffs; state only what they show.
- deploy: what has to exist or happen per environment (secrets, splits, settings files), with node ids. Only what the code or config shows.
- English, plain, no marketing words, no em dashes.
Do not modify any files.

Return only one JSON object:
{"tldr": ["..."], "checks": [{"text": "...", "nodes": ["F7"]}], "summary": "...", "review_order": [{"node": "F7", "why": "..."}], "labels": {"F7": "..."}, "roles": {"F7": "..."}, "flows": [{"title": "...", "trigger": "one sentence: who/what starts it", "summary": "...", "kind": "sequence|flow", "steps": [{"from": "Editor", "to": "F7", "text": "...", "call": "Class::method()", "detail": "..."}], "note": "optional one sentence"}], "settings": [{"text": "...", "nodes": ["F3"]}], "deploy": [{"text": "...", "nodes": ["F9"]}]}
```

The map opens with a TL;DR: the model's bullets, every flow as numbered steps in a collapsed block (rendered by the script from the
same flow data as the diagrams) and the checks and validations list. The top layer is a navigation aid written by a model from the code; the dotted steps and the summary are not
verified facts. Say so when you hand the map to someone. Azure DevOps PR descriptions may not render
```mermaid blocks: paste the `.md` and attach the `.svg`, or share the `.html`.

## Files

- `scripts/map.py` - graph, JSON export, stories validation and rendering, SVG/HTML output; imports
  `prepare.collect()` from secperf-review. The HTML loads marked and mermaid from jsdelivr, so it needs a network.
