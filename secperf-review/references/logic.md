# Logic anomalies

Stack-agnostic (Drupal PHP, Next.js/TypeScript, config). Area: logic. A logic finding says which input or state gives which wrong result, quoted from the code. "This looks fragile" is not a finding.

Each item: severity is the default; `severity.md` (Logic) escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read.

### LOG-01 · Inverted, partial or misgrouped condition

**Severity:** high · **Area:** logic · **Taxonomy:** CWE-480, CWE-783 · **Applies to:** any branch, filter, access-style check that is not a security control

**Signals:** `!` on the wrong operand; `&&` where the intent needs `||` (or the reverse); mixed `&&`/`||` without parentheses; `!==` vs `!=` against strings that can be numeric; early `return` / `continue` that skips a path the rest of the function needs; a filter that keeps what it should drop.

**Why:** The code runs fine and returns the opposite set, so tests that only check "something is returned" pass.

**Fix:** Rewrite the condition to match the intent in words, add a test for the case that flips.

**Not a finding when:** A test next to the code asserts the current behaviour and the intent (AC, docblock, test name) agrees with it.

### LOG-02 · Boundary and off-by-one

**Severity:** medium · **Area:** logic · **Taxonomy:** CWE-193 · **Applies to:** ranges, pagination, limits, slicing, dates

**Signals:** `<` vs `<=` on a limit or end date; page index 0 vs 1 mixed between producer and consumer; `slice`/`array_slice`/`substr` lengths; `range` end inclusive; "last N" built from an offset; date range end at 00:00 instead of end of day; a max length checked in one layer and a different one stored.

**Why:** The first or last item disappears or repeats, often only on the last page or on the last day.

**Fix:** State the bound as inclusive or exclusive once and use it on both sides; test the first and last element.

**Not a finding when:** The off-by-one is compensated in the same function or by the only caller you can read.

### LOG-03 · Empty, null, zero and false conflated

**Severity:** medium · **Area:** logic · **Taxonomy:** CWE-697 · **Applies to:** PHP and JS/TS

**Signals:** PHP `empty()` on values where `'0'` or `0` is valid; `if ($value)` on a numeric field; `isset()` where the key exists with `null`; JS `||` default where `0`, `''` or `false` are valid (use `??`); `!value` on counts; `== null` vs `=== undefined` on optional API fields; `array_filter()` without a callback dropping `0`/`'0'`; `Number('')` = 0.

**Why:** A legitimate zero, empty string or false is treated as "missing" and replaced or skipped.

**Fix:** Compare to the exact missing value (`=== null`, `??`, `array_key_exists`), keep the valid falsy ones.

**Not a finding when:** The field cannot hold the falsy value (schema, validation or type proves it).

### LOG-04 · Missing branch for a new or existing case

**Severity:** medium · **Area:** logic · **Taxonomy:** CWE-478 · **Applies to:** switch/match, maps keyed by type, bundle, language, status, market

**Signals:** a `switch`/`match`/lookup map that lists cases without a default, or a default that silently returns a plausible value; a new bundle, field, status, language or market added in the diff that existing branching does not know; `match` without `default` throwing `UnhandledMatchError` on a value that can occur.

**Why:** The unhandled case gets the default behaviour, which looks right in the common case and is wrong for the new one.

**Fix:** Handle the case explicitly; make the default fail loudly (exception, log) when an unknown case is a bug.

**Not a finding when:** The input is restricted upstream to the handled set (allowed values, enum type, validation).

### LOG-05 · Contract mismatch across a boundary

**Severity:** high · **Area:** logic · **Taxonomy:** CWE-573 · **Applies to:** Drupal ↔ Next (JSON:API, custom endpoints, headers), API ↔ client, config schema ↔ code, event payload ↔ listener

**Signals:** the producer emits a field name, shape (array vs single value, object vs list), null/absent convention, unit (seconds vs ms), id type (nid vs uuid) or URL/langcode format that differs from what the consumer reads; a renamed or removed field still read on the other side; a header set on one side and read with a different name or case expectation; optional on one side, required on the other.

**Why:** Each side is correct alone; the integration renders empty, crashes on null or shows stale fallback content.

**Fix:** Align both sides; add a typed parser or a contract test at the consumer.

**Not a finding when:** The consumer normalizes the shape (adapter, parser) and the normalizer handles the produced form; both sides are visible and agree.

### LOG-06 · Language, translation or market fallback wrong

**Severity:** medium · **Area:** logic · **Taxonomy:** n/a · **Applies to:** multilingual Drupal, i18n routing in Next

**Signals:** reading the default translation where the current one is needed (`$entity->get()` without `getTranslation()`, `->language()` vs the content language); langcode taken from the interface language instead of content language; a fallback chain that never reaches the last language or loops; per-market rules applied to every market sharing a language; locale or prefix built by string concatenation.

**Why:** One language or market sees another one's content, or an untranslated page, without any error.

**Fix:** Take the language from the same source the rest of the request uses; test one fallback and one non-fallback market.

**Not a finding when:** The entity or field is untranslatable, or the project context says the market shares the content by design.

### LOG-07 · Dates, times and time zones

**Severity:** medium · **Area:** logic · **Taxonomy:** CWE-682 · **Applies to:** scheduling, publish windows, expiry, sorting by date

**Signals:** comparing a UTC timestamp with a site-time-zone date string; `strtotime`/`new Date()` on a date-only string (midnight in which zone?); seconds vs milliseconds; `REQUEST_TIME` or "now" read once and reused across a long batch; DST-sensitive "+1 day" arithmetic; comparing date strings in non-ISO format.

**Why:** Content publishes or expires hours early or late, or sorts wrongly, for some users or some days.

**Fix:** Normalize to UTC timestamps for comparison, convert only for display; name the unit.

**Not a finding when:** Both sides of the comparison come from the same storage format and zone.

### LOG-08 · Non-idempotent re-run

**Severity:** high · **Area:** logic · **Taxonomy:** CWE-837 · **Applies to:** cron, deploy/update hooks, batch, queue workers, webhooks, imports, form submit retries

**Signals:** an insert or append without a "does it exist" check in code that can run twice (retry, re-deploy, double submit, overlapping cron); a deploy hook that is not safe if the previous run died halfway; a counter or list incremented on every run; a webhook handler without dedupe on the event id; partial state written before a step that can fail.

**Why:** Duplicates, doubled values or half-migrated data that only show up after a retry.

**Fix:** Upsert or check-then-write in a transaction, keyed on a natural id; make each step resumable.

**Not a finding when:** The framework guarantees single execution for this path (e.g. a post-update hook recorded only on success and the work itself is atomic).

### LOG-09 · Per-process state assumed to be shared

**Severity:** high · **Area:** logic · **Taxonomy:** CWE-362 · **Applies to:** multi-container or multi-worker deployments, serverless, Node servers

**Signals:** static/class properties, module-level variables or in-memory maps used as a cache, lock or counter across requests; files written to a per-container temp path and read by a later request; read-modify-write on a shared row or State key without a lock; "first request initializes" logic.

**Why:** Works on one local container; with several instances requests disagree, race or lose updates.

**Fix:** Move shared state to the database, cache backend or shared storage; use a lock or atomic update for read-modify-write.

**Not a finding when:** The state is only a per-request memo, or the project context says the service runs a single instance.

### LOG-10 · Error turned into silent success

**Severity:** medium · **Area:** logic · **Taxonomy:** CWE-390, CWE-754 · **Applies to:** PHP and JS/TS

**Signals:** `catch` that logs and returns a normal-looking value the caller treats as success; a promise without `await` or `.catch` in a path whose result matters; a fallback default that hides a failed fetch (empty list, cached old value) without any signal; a function returning `false`/`null` for both "none" and "failed"; a success message shown after a failed save.

**Why:** The failure is invisible: users or editors see success, monitoring sees nothing, data is missing.

**Fix:** Propagate or surface the error to the caller that must decide; log at error level with context; separate "empty" from "failed".

**Not a finding when:** The fallback is intended and documented (degraded mode) and the failure is logged at a level monitoring sees.

### LOG-11 · Code does not do what the intent says

**Severity:** high · **Area:** logic · **Taxonomy:** n/a · **Applies to:** only when the intent is available (the --intent file, a docblock, a test name or a comment stating the rule)

**Signals:** an acceptance criterion that no code path implements; a rule implemented for one case of several the AC lists; a limit, default, order or label different from the one stated; a behaviour the AC forbids.

**Why:** The change passes its own tests and still fails acceptance.

**Fix:** Implement the missing case or align the value; when the AC is ambiguous, phrase the finding as a question.

**Not a finding when:** The intent file says the case is out of scope or deferred; the difference is a deliberate, documented decision.

### LOG-12 · Derived data not updated

**Severity:** medium · **Area:** logic · **Taxonomy:** n/a · **Applies to:** search indexes, computed or denormalized fields, generated files, aggregates, existing content after a rule change

**Signals:** a change to how a value is computed, indexed or stored that applies only on the next save; no re-index, re-save or update hook for existing rows; a copy of a value kept in two places and only one written.

**Why:** New content follows the new rule, existing content keeps the old one until someone edits it.

**Fix:** Add a deploy/update hook or re-index step for existing data, or compute at read time.

**Not a finding when:** Existing data cannot be affected (new field, new bundle) or the plan states a manual re-run step.

### LOG-13 · Copy-paste and shared mutation

**Severity:** medium · **Area:** logic · **Taxonomy:** CWE-1109 · **Applies to:** PHP and JS/TS

**Signals:** a duplicated block where one identifier was not updated (`$a` used in the `$b` copy); a variable shadowing an outer one; a JS object or array from props, cache or a module constant mutated in place (`sort()`, `push`, property assignment); a PHP object passed and modified by a callee the caller did not expect.

**Why:** The wrong field is written, or a shared value changes for every later reader.

**Fix:** Use the intended identifier; copy before mutating (`[...arr].sort()`, `structuredClone`, `clone`).

**Not a finding when:** The mutation is on a local copy created in the same function.
