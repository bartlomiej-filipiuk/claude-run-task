# qa-walk

QA steps for a task are a scripted walk through the real app on the local stack (forms, pages, CLI, API, whatever
the tester would touch), not text written from the code. Each proof step must also FAIL when the task's change is
removed: a step that passes with and without the change proves nothing.

## Steps file

A module that default-exports an array of steps (optional named export `intro`: Markdown printed at the top of the QA note):

| key | meaning |
|---|---|
| `id`, `ac`, `title` | unique id (`S1`), the acceptance criterion it covers, short name |
| `kind` | `proof` (shows the change works) or `regression` (shows nothing else broke) |
| `where` | tester-facing sentence: where and how to do it (an admin form, a page, a command) |
| `surface` | tester-facing sentence: where to look for the result (a page, a response, a log) |
| `expect` | tester-facing sentence: what to see there |
| `withoutChange` | proof steps only: what the same step shows when the change is missing |
| `run(ctx)` | does the walk, returns `{ pass: boolean, observed: string }`; a throw is `error`, never `fail` |
| `restore(ctx)` | optional, always called after `run` (also after a throw); a throw here makes the step `error` |

`cms` and `site` are still accepted as the older names of `where` and `surface` (when both are given, `where` and
`surface` win). Each of the pair must be a non-empty string.

Optional named export `notWalked`: checks we could not do locally, never run. Each entry is
`{ ac, who: 'tester'|'owner', where, expect, why }` (all non-empty strings; `where` = environment and place,
`expect` = what to see, `why` = why it was not walked locally). Validated like the steps.

`ctx` = `{ lib, outDir, browser(), shot(page, name, options) }`. `browser()` starts one shared Chromium on first call;
`shot()` saves a Playwright screenshot to `<outDir>/<name>.png`.

## Helper library (optional, project-supplied)

`--lib <file>` or the env variable `QA_WALK_LIB` names an ES module with the project's helpers (a relative path is
resolved against the current directory). The runner imports it once before the first step and passes the module
namespace as `ctx.lib`; without one `ctx.lib` is `null`. A lib that does not load stops the run with exit 2.

The runner itself uses one export, and only when a step calls `ctx.browser()`:

| export | contract |
|---|---|
| `chromium()` | optional; returns a Playwright `BrowserType` (`.launch()` is called on it). Without it `browser()` resolves `playwright` or `@playwright/test` from the current directory and throws when neither is installed. |

Everything else in the lib is for the steps: login contexts, form helpers, back-end state capture and restore, and so
on. Keep project URLs, credentials and paths in the lib (or env variables it reads), not in the runner.

## Commands

    node scripts/qa-walk/run.mjs <steps.mjs> [--lib <helpers.mjs>] [--only proof|regression] [--step S1,S2] [--out <file>]
    node scripts/qa-walk/run.mjs --table <with.json> <without.json>
    node scripts/qa-walk/run.mjs --print-qa <steps.mjs>
    node scripts/qa-walk/run.mjs --print-conditions <steps.mjs>
    node scripts/qa-walk/selftest.mjs

`run.mjs` writes `{ steps, summary }` to `--out` (default `result.json` next to the steps file) and screenshots to a
folder named after it; exit 0 all passed, 1 a step failed, 2 a step errored or the file is invalid. `--table` prints
`step | AC | kind | with the change | without the change | proves` and exits 0 only when every proof step passes
with and fails without the change and every regression step passes with it. `--print-qa` prints the QA note from
the same file, so the note and the walk cannot drift; its `tester` entries of `notWalked` follow as "Also check on
dev". `--print-conditions` lists every `notWalked` entry (tester and owner) as a table, or `No conditions from the walk.`

## Negative control

    python3 scripts/revert-check/revert-check.py --repo <repo> --base <branch> [--pre '<sync or cache-clear command>'] -- \
      node $PWD/scripts/qa-walk/run.mjs $PWD/<task>/qa-walk/steps.mjs --lib $PWD/<helpers.mjs> --only proof \
      --out $PWD/<task>/qa-walk/result-without.json
    node scripts/qa-walk/run.mjs --table <task>/qa-walk/result.json <task>/qa-walk/result-without.json

revert-check runs the walk once with the change (must exit 0), then without it; see `../revert-check/README.md`.
It runs the command inside `<repo>`, so pass absolute paths. Nothing else may run in `<repo>` meanwhile. State the
reverted code does not know (database rows, stored config) stays where it is.

## Rules

- Capture every text, setting and record the step edits BEFORE the edit, write it back in `restore` and compare.
- Switch off anything a local submit would send to a live third party (CRM, mail, payment) and refuse to submit
  unless it reports off; restore it afterwards and delete the test records.
- A step that cannot run locally is not put in the steps array; it goes into `notWalked` (`tester` when QA checks it
  on a shared environment, `owner` when the task owner has to run it).
