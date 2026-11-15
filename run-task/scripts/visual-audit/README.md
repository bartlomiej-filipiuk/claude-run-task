# visual-audit

Loads pages at a viewport matrix in Chromium, measures layout faults per container (each section of `<main>`, plus
`<header>` and `<footer>`) and takes full-page screenshots. `compare.mjs` then splits the findings of a branch run
against a base run and builds side-by-side montages.

    node scripts/visual-audit/audit.mjs --url=<base url> --tag=base   --config=<dir>/visual.json --out=<dir> [--sha=<sha>]
    node scripts/visual-audit/audit.mjs --url=<base url> --tag=branch --config=<dir>/visual.json --out=<dir> [--sha=<sha>]
    node scripts/visual-audit/compare.mjs <dir> [--branch=branch] [--base=base]

`audit.mjs` also takes `--vp=375x812,1280x800` (overrides the viewports) and `--pages=id,id` (a subset of pages).
`compare.mjs` reads `<dir>/visual.json`, so keep the config in the output directory.

## visual.json

| key | required | meaning |
|---|---|---|
| `pages` | yes | `[{ "id": "home", "path": "/" }]`; `path` is appended to `--url` |
| `viewports` | no | `["375x812", "1440x900"]`; default 375x812, 768x1024, 1024x1366, 1280x800, 1440x900, 1920x1080 |
| `blockUrls` | no | Playwright URL globs whose requests are aborted, e.g. `["**consent.example.com**", "**googletagmanager.com**"]`; default none |
| `cookies` | no | `[{ "name": "banner_hidden", "value": "1" }]`, set for `--url` before each page (other Playwright cookie fields allowed); default none |
| `ignore` | no | findings `compare.mjs` drops: `{ "fingerprint": "..." }` or `{ "selector": "...", "kind": "..." }` (`kind` optional) |

## Outputs

- `<out>/<tag>.json`: `{ meta: { url, tag, sha, viewports, at }, results: [{ page, path, vp, findings }] }`. A finding is
  `{ kind, container, selector, detail, fingerprint }`; kinds: `page-overflow-x`, `outside-container-x`,
  `outside-container-y`, `text-clipped`, `covered`, `sections-overlap`, `heading-under-header`, `load-error`.
- `<out>/shots/<tag>/<page>-<w>x<h>.png`: full-page screenshot, cut at 6000 px.
- `<dir>/diff.json` (compare): `regression` (branch only), `preexisting` (both), `fixed` (base only). Without a base
  run every finding is listed as regression.
- `<dir>/montage/<page>-<n>.png` and `.txt` (compare): rows are viewports (three per image), columns base | branch.

## Requirements

- Node 18+.
- Playwright with Chromium installed (`npx playwright install chromium`), resolved from the current directory:
  run `audit.mjs` from the project that has `playwright` or `@playwright/test` in its `node_modules`, or set
  `VISUAL_AUDIT_PLAYWRIGHT` to the module name or path. Without it the script stops with exit 2 and says so.
- `ffmpeg` on `PATH` for the montages. Without it `compare.mjs` writes `diff.json`, prints one warning line and
  skips the montages.
