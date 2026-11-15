# Severity rubric

Applies across all areas. Item-level escalation/downgrade notes override the default severity.

General rules (all areas):
- Severity is assigned from evidence in the diff plus the code the finder read. Every finding carries file:line, the code, and the item id. If the reviewer cannot show the data path (source to sink, or the read that varies the output), the finding is reported one level lower and tagged "unverified".
- One finding per line: when several items match the same code, report the highest-severity item and list the others as "also".
- Absence-type checks (no rate limit, no CSP, no cacheHandler, no hook_entity_field_access) are never above low and are phrased as a question.
- Escalation and downgrade rules stated per item override the default.

Security (OWASP Top 10, API Top 10):
- critical: exploitable by an unauthenticated or any authenticated user without special conditions, and the outcome is code execution, SQL injection, credential or secret disclosure, or full read/write of other users' data (DSEC-11, DSEC-26, DSEC-36, NSEC-01 without any auth, NSEC-06, DEC-02 for anonymous, DEC-03, NPERF-09 with proven personalization, NSEC-34 when other users' sessions or PII are served).
- high: an attacker with a normal account, or anonymous under one realistic condition (a public route, a known id), reaches other users' data, elevates privilege, uploads executable content, or bypasses auth (BOLA/IDOR, mass assignment, missing auth on a handler, SSRF to internal hosts, stored XSS in public content, secrets in the bundle, middleware-only auth, cache leaks of private data).
- medium: needs a privileged victim, an admin misconfiguration, or a second bug (reflected XSS in admin, open redirect, CSRF on low-impact actions, error text disclosure, excessive data exposure without sensitive fields, CORS without credentials, cookie flags, weak preview secret, GraphQL limits).
- low: hardening or hygiene with no demonstrated path (missing server-only, missing rate limit, autocomplete tokens, source maps).
- Config-only changes (yml, settings.php, next.config) are graded by what the config opens, not by the file type.

Performance (must state growth scale):
- critical: not used for performance; a performance issue is at most high unless it also opens a DoS from anonymous input (then grade under security).
- high: cost grows with a table, entity count, or request rate that the site already has in the tens of thousands or more, or the defect disables a whole cache layer for every request (unbounded query on nodes/users/orders, N+1 over an unbounded list, cron/update doing all rows in one run, external HTTP in page build, proxy running on every asset request, request-time read in the root layout). Bites within months on a content site; on day one for a shop.
- medium: linear growth on a bounded or slow-growing set (per-page loops over a paged list, per-save hooks that matter only in bulk imports, table growth with no cleanup, missing index on a query the diff shows, State/key_value misuse, module-level Map growth keyed by user). Bites at tens of thousands of rows or in imports and migrations.
- low: constant overhead or hygiene (image sizes, heavy client library, own-API fetch, token per call, per-item cost on lists under a hundred).

Cache (correctness first, then efficiency):
- critical: only when the cache serves one user's private response to others (graded as security, see above).
- high: users see wrong or stale content with no recovery except a manual cache clear, or a whole cache layer is silently disabled for all anonymous traffic (missing cacheable dependency or list tag, max-age 0 bubbling outside a lazy builder, kill switch, anonymous session start, access result without cacheability, uncached fetch in a shared helper, custom auth provider without request policy).
- medium: stale for a bounded time or on one route, wrong contexts on non-personal data, broad invalidation that hurts under load, no revalidation path for CMS data, wrong tag names, force-static on a route that reads request data, unbounded cache ids.
- low: efficiency only (broad list tags, low hit rate, short revalidate on one fetch).

Accessibility (WCAG 2.2 AA, light):
- high: a keyboard or screen-reader user cannot complete a task on the changed UI (unlabeled form control, unnamed control, clickable div with no keyboard path, dialog without focus management, focus outline removed globally, informative image with no alt).
- medium: the task is possible but confusing or partially blocked (ARIA role without keyboard support, unannounced async result, aria-hidden on focusable, wrong lang, autoplay without pause, drag-only, paste blocked on login, errors not linked to fields, zoom blocked, hover-only reveal, contrast below 4.5:1 on literal colours, missing main landmark).
- low: best-practice and judgement items (headings, target size, onChange navigation, route announcer, tables without th).
- Never report what the project's own lint config already blocks (tsc alt on next/image, jsx-a11y rules that are enabled in the repo's eslint config).

Logic (must name the input or state that gives the wrong result):
- critical: not used for logic; a logic bug that exposes data or bypasses access is graded under security.
- high: wrong data saved, lost or shown for a common input, or a core flow (publish, submit, checkout, search, navigation) broken for a realistic case; non-idempotent re-runs that duplicate or corrupt data; per-container state that diverges in production; a cross-boundary contract mismatch that renders empty or crashes; an acceptance criterion not implemented (LOG-01, LOG-05, LOG-08, LOG-09, LOG-11).
- medium: wrong result for an edge input or a subset (one language or market, one date, the last page, a zero value), recoverable by an edit or a re-save; existing data not migrated to a new rule; errors hidden behind a plausible fallback.
- low: unlikely input with a cosmetic outcome, or a defensive gap with no path shown. Phrase as a question.
- A finding whose intent is ambiguous (no AC, no docblock, no test) is at most medium and phrased as a question.

Infra (CI, containers, web server, edge cache): grade by what the setting opens, with the security and cache scales above. A secret in an image layer or log is high; an unpinned build input is medium; a missing required variable that silently disables a control is medium.
