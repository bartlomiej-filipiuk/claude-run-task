# Generic stacks: performance and cache

Server code outside Drupal and Next.js: Laravel, Symfony, Django, FastAPI, Flask, Go, Rust, Rails, Java/Spring and stacks close to them. Code that degrades with data growth, and cache use that is wrong, missing or switches a cache off.

Each item: severity is the default; `severity.md` escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read. Every performance finding says what grows (rows, items, requests) and at what scale it bites. Read your stack's row in the table at the end first.

### GPERF-01 · Query or remote call inside a loop (N+1) instead of eager loading or one batched query

**Severity:** high (unbounded list) · **Area:** performance · **Taxonomy:** - · **Applies to:** ORMs and DB clients in handlers, serializers, templates, resources and jobs

**Signals:** a relation or lookup touched per item in a loop, serializer, template or API resource (`$post->author` in a Blade loop without `with()`, a DRF nested serializer without `select_related` / `prefetch_related`, Rails `.each` over an association without `includes`, a lazy JPA `@OneToMany` read in a loop, `QueryRow` / `sqlx::query` per id inside a `for`); HTTP or cache calls per item.

**Why:** Queries grow with the list: a page of 100 rows becomes 101 queries, and the page gets slower as the data grows.

**Fix:** Eager-load (`with`, `select_related` / `prefetch_related`, `includes`, `JOIN FETCH` or an entity graph), or fetch all ids in one `IN` query and map them in memory.

**Not a finding when:** the loop is bounded to a few items by construction; the relation is already eager-loaded further up (the query, a default scope, `$with`, the serializer's `get_queryset`). A paged list of a fixed small size is medium, not high.

**Sources:** https://docs.djangoproject.com/en/stable/topics/db/optimization/ · https://laravel.com/docs/eloquent-relationships#eager-loading · https://guides.rubyonrails.org/active_record_querying.html#eager-loading-associations

### GPERF-02 · Unbounded read: list endpoint, query or export without a limit or pagination

**Severity:** high · **Area:** performance · **Taxonomy:** API4:2023, CWE-770 · **Applies to:** list endpoints, exports, admin screens, scheduled jobs

**Signals:** `all()`, `get()`, `findAll()`, `Find(&rows)`, `fetch_all` without `limit` / `paginate` / page size on tables that grow (users, orders, events, logs); a page size or limit from input with no maximum; all rows loaded to count or filter in memory (`len(qs)`, `->get()->count()`, `.to_a.size`); a whole export built in memory.

**Why:** Memory and response time grow with the table, and one request can exhaust a worker.

**Fix:** Paginate with a server-side maximum; count in the database; stream or chunk large reads (`chunk`, `lazy`, `iterator()`, `find_each`, a cursor).

**Not a finding when:** the table is small and bounded by design (config, countries, roles); the query is filtered to a bounded set (one user's last N); a global default page size with a maximum applies (DRF `PAGE_SIZE`, Spring `Pageable` limits).

**Sources:** https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/

### GPERF-03 · New filter, join or sort on a growing table without an index

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** migrations, model definitions, new query conditions

**Signals:** a new `WHERE`, `ORDER BY` or `JOIN` column with no index in the migration or schema; a foreign key column without an index on PostgreSQL (MySQL InnoDB creates one, PostgreSQL does not); `LIKE '%x%'` on a large text column; a uniqueness rule checked only in code, with no unique index.

**Why:** Full scans get slower with every row, and duplicates slip through concurrent requests.

**Fix:** Add the index or unique constraint in the same migration; use full-text search for contains-search.

**Not a finding when:** the table is small and bounded; an existing composite index has the column as its leading part; the ORM creates the index (Django `ForeignKey` has `db_index=True` by default).

**Sources:** https://docs.djangoproject.com/en/stable/ref/models/fields/#foreignkey · https://docs.djangoproject.com/en/stable/topics/db/optimization/

### GPERF-04 · Slow or external work in the request path without a timeout

**Severity:** high · **Area:** performance · **Taxonomy:** API4:2023, CWE-400 · **Applies to:** HTTP clients, SMTP, payment, AI and search APIs, file conversion

**Signals:** an outbound call in a request handler without a timeout (`requests.get(url)` without `timeout=`, Go `http.Get` or `http.Client{}` without `Timeout`, Laravel `Http::` without `timeout()`, `reqwest` without `timeout`, `RestTemplate` defaults); mail, PDF or image generation and webhooks done inline instead of queued; blocking I/O inside async handlers (sync DB calls in FastAPI `async def`, `std::fs` in tokio without `spawn_blocking`); Go servers without `ReadHeaderTimeout`.

**Why:** One slow dependency holds every worker, so the whole site stalls while it hangs.

**Fix:** Explicit connect and read timeouts; queue slow side work; cache stable responses; degrade when the dependency fails.

**Not a finding when:** the call runs in a queued job with its own timeout; the client gets its timeout from shared config or a factory (find it before flagging).

**Sources:** https://pkg.go.dev/net/http#Server · https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/

### GPERF-05 · Cache key or HTTP cache missing a dimension the output depends on (wrong or private content served)

**Severity:** high · **Area:** cache · **Taxonomy:** A01:2025, CWE-524 · **Applies to:** application caches, view, page and fragment caches, HTTP cache headers

**Signals:** `Cache::remember`, `cache.get_or_set`, `@cache_page`, `@cache.cached`, `Rails.cache.fetch`, `@Cacheable`, Redis / `moka` / `lru` keys built without the user, tenant, locale, permission set or query parameter the value depends on; `@cache_page`, `Cache-Control: public` or `s-maxage` on responses that read the session or user; no `Vary` for a request header that changes the output.

**Why:** The first visitor's data is served to the next ones: private data leaks, or users see the wrong language, tenant or permissions.

**Fix:** Put every varying input in the key (user or tenant id, locale, role set, normalized query), or cache only the shared part. Mark personalized responses `private` or `no-store`, or add `Vary`.

**Not a finding when:** the value is the same for everyone (public catalogue, config); the key already holds the dimension through a prefix or helper (read it).

**Sources:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching

### GPERF-06 · Cache never invalidated on write, or invalidated far too broadly

**Severity:** medium (high when users see stale prices, stock or permissions) · **Area:** cache · **Taxonomy:** - · **Applies to:** application caches, CDN purges

**Signals:** a new cached read with no matching forget, delete or evict on the write path (`Cache::forget`, `cache.delete`, `@CacheEvict`, `Rails.cache.delete`, `touch: true`); a TTL long enough that stale data matters; the reverse: `Cache::flush()`, `cache.clear()`, `@CacheEvict(allEntries = true)` or a full CDN purge on every save.

**Why:** Users see stale data until expiry, or every write empties the cache and the database takes the full load.

**Fix:** Invalidate the exact keys or tags the write affects, after the transaction commits. Keep TTLs as a safety net, not as the mechanism.

**Not a finding when:** the staleness is acceptable and stated (minutes on non-critical data); writer and reader share a versioned key that changes on write.

**Sources:** https://docs.djangoproject.com/en/stable/topics/cache/

### GPERF-07 · Unbounded growth: in-process caches, tables or queues without cleanup

**Severity:** medium · **Area:** performance · **Taxonomy:** CWE-401, CWE-770 · **Applies to:** module-level maps, static fields, event and log tables, job queues

**Signals:** a module-level dict or map, static `HashMap`, `OnceLock<Mutex<HashMap>>` or class-level array filled per request or per user with no eviction; `functools.lru_cache` on methods or with unbounded arguments; new tables for events, logs, tokens or sessions with no pruning job; one job per row with no batching or retry limit.

**Why:** Memory grows until the process restarts and tables grow until queries slow down. Per-process caches also diverge between instances.

**Fix:** A bounded LRU with a TTL, or a shared cache; a scheduled prune with an index on the timestamp; batched jobs with retry limits.

**Not a finding when:** the key space is small and fixed (an enum, config); the process is short-lived (a CLI command, one job).

**Sources:** https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/

### GPERF-08 · Per-item writes and save hooks that multiply under bulk operations

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** handlers, imports, model callbacks, signals, event listeners

**Signals:** loops that save one row at a time instead of a bulk insert or update; work in save hooks (`post_save`, Eloquent observers, `after_save`, JPA `@PostPersist`) that sends mail, calls HTTP or saves other rows on every write; whole files read into memory; a multi-step write without a transaction (partial writes, long lock times).

**Why:** Imports and busy endpoints multiply the per-item cost, and hooks fire in places the author did not expect.

**Fix:** Bulk operations (`bulk_create`, `insert`, `upsert_all`, batched `saveAll`); queue the fan-out; stream large files; wrap multi-step writes in a transaction.

**Not a finding when:** the volume is small and bounded; the hook guards itself (checks changed fields, skips bulk imports).

**Sources:** https://docs.djangoproject.com/en/stable/topics/db/optimization/

## Per-stack signals

| Stack | N+1 and unbounded reads | Cache API and keys | Traps |
|---|---|---|---|
| Laravel | lazy relations in Blade or API resources without `with()`; `->get()` / `::all()` instead of `paginate()` / `chunk()` / `lazy()` | `Cache::remember` keys, `Cache::tags` + `forget` on save, `Cache::flush` | `Http::` without `timeout()`; queued jobs without `tries` / `timeout` |
| Symfony | Doctrine lazy associations in loops (fetch joins); `findAll()` | Symfony Cache `get()` with a callback, tag-aware invalidation, `setPublic()` / `setSharedMaxAge()` on responses | HttpClient without `timeout`; Messenger handlers without retry limits |
| Django | serializers and templates without `select_related` / `prefetch_related`; `.all()` in views without pagination; `len(qs)` instead of `.count()` | `cache.get_or_set` keys, `@cache_page` on authenticated views, `vary_on_cookie` | `post_save` signals fanning out; `requests` without `timeout=` |
| FastAPI | SQLAlchemy lazy loads in response models (`selectinload` / `joinedload`); sync DB calls inside `async def` | Redis or `fastapi-cache` keys without the user | `httpx` / `requests` without `timeout`; heavy work in `BackgroundTasks` |
| Flask | lazy relations in Jinja loops; `.query.all()` | Flask-Caching `@cache.cached` on views that read `current_user` | `requests` without `timeout`; work in `before_request` on every call |
| Go | `QueryRow` per id in a loop; `rows` without `defer rows.Close()`; no `LIMIT` | package-level `map` caches without eviction or a mutex | `http.Client{}` without `Timeout`; servers without `ReadHeaderTimeout`; one goroutine per item with no bound |
| Rust | per-item `sqlx::query` in loops; `fetch_all` on unbounded queries | `moka` / `lru` / static `HashMap` without size or TTL | blocking calls in async handlers without `spawn_blocking`; `reqwest` without `timeout` |
| Rails | `.each` over associations without `includes` / `preload`; `.all` without pagination | `Rails.cache.fetch` keys without user or locale, `touch: true` chains | `after_save` callbacks fanning out; jobs without `retry_on` limits |
| Java/Spring | lazy `@OneToMany` in loops (`JOIN FETCH`, `@EntityGraph`); `findAll()` without `Pageable` | `@Cacheable` keys without user or tenant, `@CacheEvict(allEntries = true)` on hot paths | `RestTemplate` / `WebClient` without timeouts; HTTP calls inside `@Transactional`; open-session-in-view lazy loads |
