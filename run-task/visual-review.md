# Visual review (Phase 4 controller check and Phase 5, conditional)

Does every page still look right at every screen size, and did this branch break anything a user sees? Measures layout
faults on real pages of the branch build, compares them with the base build, and has one agent look at the montages.
Web front ends only.

## Trigger and skip

Runs when the branch diff touches a path matching the profile's `visual.trigger_globs` (front-end components, styles,
pages, layouts; tests, types and docs excluded). A back-end task that changes what the front renders can be pulled in
by a ruling. Gate `visual` = `skip` with the reason when no path matches, with `--analysis-only`, when no local page
renders the touched component, or per task for tiers light and docs (the branch run in Phase 5 still happens). Empty
`visual.trigger_globs` while the diff touches templates, styles or front-end components = `not covered`.

## Inputs: `tasks/<ID>/visual/visual.json`

Written with the plan in Phase 3:

```json
{ "pages": [{ "id": "pricing", "path": "/pricing", "why": "renders the changed card grid" }],
  "viewports": ["375x812", "768x1024", "1024x1366", "1280x800", "1440x900", "1920x1080"],
  "variants": [{ "id": "long-title", "set": "<command that sets the content state>", "restore": "<command that restores it>" }],
  "ignore": [{ "fingerprint": "outside-container-x|...", "why": "carousel arrow sits outside the column by design" }],
  "blockUrls": ["**/analytics.example.com/**"],
  "cookies": [{ "name": "consent", "value": "1" }] }
```

`viewports` is optional (default above). Variants are content states set before and restored after both audits.
Key names follow `scripts/visual-audit/README.md`.

## Commands

Run from the front-end repo (Playwright is resolved from there). Branch build and base build come from the profile's
`visual.build` and `visual.base_url`; a production build, never a dev server.

```bash
V=tasks/<ID>/visual
node ~/.claude/skills/run-task/scripts/visual-audit/audit.mjs --url=<branch url> --tag=branch --config=$V/visual.json --out=$V --sha=<branch sha>
node ~/.claude/skills/run-task/scripts/visual-audit/audit.mjs --url=<base url> --tag=base --config=$V/visual.json --out=$V --sha=<base sha>
# per variant: run "set" (and the profile's cache_bypass), audit both with --tag=branch-<id> / base-<id>, run "restore"
node ~/.claude/skills/run-task/scripts/visual-audit/compare.mjs $V   # diff.json + montages (rows = viewports, base | branch)
```

Per task (Phase 4, full tier): branch only, three viewports (375x812, 1280x800, 1440x900), pages of the touched
component; run the base only when there are findings, to tell a regression from a pre-existing fault.

## The review agent

One Agent call, strong model, effort medium, fresh context. Give it `diff.json`, the montage paths (at most 8 per
call), `visual.json`, `ac.md` and the front-end file list of the branch diff (names only). Not the plan, ledger or
chat. Prompt verbatim (fill paths):

```text
You review how a website looks after a change, from measurements and screenshots. You did not write the change. Do not read code.

Files: <V>/diff.json (findings: regression = only on the branch, preexisting = also on the base, fixed = only on the base), <V>/visual.json (pages and why they are checked), montages <list> (each has a .txt naming its rows = viewports and columns = base | branch), the intent <tasks/ID/ac.md>, and the changed files: <names>.

1. Every regression row: real or false positive? Open its montage and say what you see. Typical false positives: decorative elements or carousel arrows placed outside a content column on purpose, transparent layers that do not block anything visible, sliders whose off-screen slides are clipped.
2. Every page and viewport in the montages, branch column: text covered or overlapping, text outside its panel, heading under the site header, call to action off-screen inside a full-height block, horizontal scrollbar, media stretched, letterboxed or missing, blank area taller than the screen, text cut mid-word.
3. Differences between base and branch columns that the intent does not explain.
Only the listed pages. Do not modify files.

Return only JSON:
{"findings": [{"id": "V1", "page": "...", "viewport": "WxH", "kind": "regression|pre-existing|unexplained-diff", "severity": "blocker|major|minor", "what": "one sentence", "evidence": "montage path + fingerprint", "why": "one sentence"}], "dismissed": [{"fingerprint": "...", "why": "..."}], "ok": ["page@WxH"]}
Severity: blocker = text unreadable or covered, or the call to action unreachable, at any viewport; major = layout broken but content reachable; minor = spacing or alignment.
```

## Routing and output

- regression, not dismissed: the fix wave (per task: that task's fix round), then re-run the audit on those page x
  viewport pairs; the measurement is the re-review;
- pre-existing: a `follow-up` ruling and a line under Follow-ups in `summary.md`; never fixed without the user;
- unexplained-diff: a question at the result gate, next to the intent check's unexplained rows;
- dismissed: claims for the verifier; once confirmed, add to `ignore` with the reason.

`tasks/<ID>/visual/visual-review.md`: pages x viewports, branch and base SHA, variants, table
`id | page@viewport | kind | severity | what | ruling`, dismissed as a count with reasons, montage links. Gate `visual`:
`baseline` when every finding is pre-existing.
