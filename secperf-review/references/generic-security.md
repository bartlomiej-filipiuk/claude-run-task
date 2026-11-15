# Generic stacks: security

Server code outside Drupal and Next.js: Laravel, Symfony, Django, FastAPI, Flask, Go, Rust, Rails, Java/Spring and stacks close to them. OWASP Top 10 (2025) and OWASP API Security Top 10 (2023).

Each item: severity is the default; `severity.md` escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read. The items are stack-neutral. Read your stack's row in the table at the end first: it names the framework's guards, sinks and traps that the items refer to.

### GSEC-01 · Handler reachable without the authentication or authorization it needs (function level)

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, A07:2025, API5:2023, CWE-862, CWE-306 · **Applies to:** routes, controllers, views, RPC and GraphQL resolvers, consumers fed from outside

**Signals:** a new or changed handler that writes data, returns non-public data, exports, sends mail or calls a paid API, with no auth middleware, decorator, dependency, policy or annotation on the handler, its route group or its router; an auth guard removed, moved after the routes it should cover, or replaced by a login-only check on an admin action; methods on the same path guarded differently (GET guarded, DELETE not); a role check that only hides a button in the template.

**Why:** Anyone who can reach the URL calls the handler directly. A login-only check on an admin function lets every account use it.

**Fix:** Guard the route group or router with the framework's auth mechanism and deny by default, then check the specific permission or policy per action.

**Not a finding when:** the route is public by design (landing, health, sitemap, login, password-reset request, OAuth callback, a webhook that verifies a signature before doing anything). A parent group, router dependency or global default (DRF `DEFAULT_PERMISSION_CLASSES`, Spring `anyRequest().authenticated()`, a Laravel route group) already covers it: read the route file before flagging.

**Sources:** https://top10.owasp.org/2025/A01_2025-Broken_Access_Control/ · https://api-security.owasp.org/editions/2023/en/0x11-t10

### GSEC-02 · Object loaded by id from the request without an owner or tenant condition (BOLA/IDOR)

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, API1:2023, CWE-639 · **Applies to:** any handler that takes an id, slug or uuid from the path, query, body or token claims

**Signals:** `find($id)`, `get(pk=...)`, `First(&x, id)`, `findById(id)`, `query.get(id)`, or update/delete by id, where the query has no user or tenant column and no policy or permission call on the loaded object; route-model binding or extractors that load the object with no check after it; owner or tenant ids for writes taken from input (`user_id`, `org_id`, `tenant_id` in the body) instead of the session.

**Why:** Any user changes the id and reads or changes someone else's record.

**Fix:** Scope the query to the caller (`where owner_id = current user`, a tenant-scoped repository or default scope), or authorize the loaded object with the framework's policy API before using it. Take owner and tenant ids from the session, never from input.

**Not a finding when:** the data is public by design; the object is the caller's own by construction (`request.user`, `current_user`); an admin-only route whose permission covers all records; a default scope, row-level security or repository wrapper already filters by tenant (find it before flagging).

**Sources:** https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/ · https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html

### GSEC-03 · Request bound to a model without an allowlist, or a model returned whole (mass assignment, data exposure)

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, API3:2023, CWE-915, CWE-213 · **Applies to:** ORM create/update from request data, serializers, response models

**Signals:** the whole request passed to create/update/fill/bind (`$request->all()`, `**request.data`, `params` without `permit`, `BindJSON` into the DB struct, `@RequestBody` straight into an entity); `$guarded = []`, `fields = "__all__"`, `permit!`; a response that serializes the ORM row or entity directly (password hash, tokens, `is_admin`, internal notes); FastAPI routes returning ORM rows without `response_model`.

**Why:** A user sets fields they must not set (`role`, `is_admin`, `price`, `owner_id`) or reads fields they must not see.

**Fix:** Bind to an explicit input DTO, form request, serializer or `permit` list. Return an explicit output schema or resource class.

**Not a finding when:** the model's allowlist (`$fillable`, serializer `fields`, the DTO) holds only fields the caller may set; admin-only endpoints where every field is editable by design; internal jobs whose output is never returned.

**Sources:** https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/ · https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html

### GSEC-04 · Injection: SQL, shell, template or deserializer fed with input

**Severity:** critical (high when only an authenticated admin reaches it) · **Area:** security · **Taxonomy:** A05:2025, A08:2025, CWE-89, CWE-78, CWE-1336, CWE-502 · **Applies to:** raw queries, ORM raw fragments, process execution, template compilation, deserializers

**Signals:** SQL text built by concatenation, interpolation or formatting (`"..." . $x`, f-strings, `%`, `.format`, `fmt.Sprintf`, `format!`, `"#{x}"`, `+` in Java) passed to raw/execute/whereRaw/extra/Raw/createQuery; column or sort direction from input; shell commands with input via `shell=True`, `sh -c`, backticks, `system`, `Runtime.exec`; templates compiled from input (`render_template_string`, `Template(input)`, `Blade::compileString`); `pickle`, `yaml.load` without a safe loader, `Marshal.load`, `unserialize`, `ObjectInputStream` on untrusted bytes.

**Why:** The input becomes code: data theft, data loss or remote code execution.

**Fix:** Bound parameters and query builders; allowlist identifiers; argument arrays without a shell; fixed templates with data passed as context; data-only formats (JSON) with schema validation.

**Not a finding when:** every interpolated value is a constant, an allowlisted identifier or a server-generated integer; the raw call takes bindings (`whereRaw('x = ?', [$v])`, `sqlx::query!` with `$1`); the serialized data is signed and verified before parsing.

**Sources:** https://top10.owasp.org/2025/A05_2025-Injection/ · https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html · https://cwe.mitre.org/data/definitions/78.html · https://cwe.mitre.org/data/definitions/1336.html

### GSEC-05 · Output escaping switched off (XSS)

**Severity:** high (stored, on public pages) · **Area:** security · **Taxonomy:** A05:2025, CWE-79 · **Applies to:** server templates, HTML built in code, HTML email

**Signals:** user or stored data printed unescaped: Blade `{!! !!}`, Twig `\|raw`, Django/Jinja `\|safe`, `mark_safe`, `{% autoescape off %}`, `Markup(...)`, Rails `raw` / `.html_safe` / `<%==`, Go `template.HTML(...)` or `text/template` used for HTML, Thymeleaf `th:utext`, Razor `Html.Raw`; HTML assembled by string concatenation; a `text/html` response that echoes input.

**Why:** Script runs in the victim's session: account takeover and actions on their behalf.

**Fix:** Keep auto-escaping on. Sanitize rich text with an allowlist sanitizer (bleach or nh3, HTML Purifier, ammonia, OWASP Java HTML Sanitizer) before marking it safe.

**Not a finding when:** the value is a constant, built by the server, or passed through an allowlist sanitizer on the way in; JSON APIs served as `application/json`. Reflected or admin-only XSS is medium per `severity.md`.

**Sources:** https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html

### GSEC-06 · Path, upload or outbound URL taken from input (traversal, upload, SSRF, open redirect)

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, API7:2023, CWE-22, CWE-434, CWE-918, CWE-601 · **Applies to:** file reads and writes, archive extraction, uploads, HTTP clients, redirects

**Signals:** file paths joined with input (`os.path.join(base, request...)`, `filepath.Join(dir, r.URL...)`, `storage_path($name)`, `File.read(params[...])`); archive entries extracted without a containment check; uploads stored under the client filename, in a public or executable dir, or without type and size limits; HTTP client calls (`requests.get(url)`, `Http::get($url)`, `http.Get(u)`, `reqwest::get`, `RestTemplate`) with a URL or host from input or stored user data; redirects to a `next` / `return_to` URL from input.

**Why:** Reads or overwrites files outside the intended dir, stores executable content, reaches internal services and cloud metadata, or sends users to a phishing page.

**Fix:** Resolve and check containment (`filepath.IsLocal`, `os.path.realpath` plus a prefix check, `Path::starts_with` after `canonicalize`); generate storage names; allowlist hosts and schemes and block private ranges after DNS resolution; allow only relative redirects or an allowlist.

**Not a finding when:** the path or URL comes from a server-side constant, or from an id the server maps to a fixed location; the outbound host is fixed in config and only an encoded path or query part varies.

**Sources:** https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html · https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html · https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html · https://cwe.mitre.org/data/definitions/22.html

### GSEC-07 · CSRF, CORS or cookie protection weakened on cookie-authenticated endpoints

**Severity:** medium (high when the action moves money or changes credentials or roles) · **Area:** security · **Taxonomy:** A01:2025, CWE-352, CWE-942, CWE-1004 · **Applies to:** session-cookie auth, CORS config, Set-Cookie

**Signals:** CSRF protection removed or bypassed (`$except`, `@csrf_exempt`, `skip_forgery_protection`, `csrf().disable()`, `csrf_protection: false`) on a state-changing route that authenticates by cookie; state changes on GET; CORS that reflects the Origin or allows `*` together with credentials; session cookies without `Secure` or `HttpOnly`, or with `SameSite=None`.

**Why:** Another site makes the victim's browser perform the action, or reads authenticated responses.

**Fix:** Keep the framework's CSRF protection on browser routes and exempt only token-authenticated APIs or signed webhooks; allowlist CORS origins; set `Secure`, `HttpOnly` and `SameSite=Lax` or `Strict`.

**Not a finding when:** the route authenticates with a bearer token or API key, not a cookie; a webhook verifies a signature; CORS without credentials on public data.

**Sources:** https://top10.owasp.org/2025/A01_2025-Broken_Access_Control/

### GSEC-08 · Secret, debug mode or verification switched off

**Severity:** high · **Area:** security · **Taxonomy:** A02:2025, A04:2025, A07:2025, CWE-798, CWE-295, CWE-347, CWE-208, CWE-330 · **Applies to:** config and settings, HTTP client setup, auth and token code

**Signals:** hardcoded secrets, keys or default fallbacks (`getenv("SECRET_KEY", "dev")`); debug or profiler enabled in production config (`APP_DEBUG=true`, `DEBUG = True`, `debug=True`, Symfony profiler, exposed Spring actuator); TLS verification off (`verify=False`, `InsecureSkipVerify: true`, `danger_accept_invalid_certs(true)`, trust-all managers); JWT parsed without pinning the algorithm, or claims used before the signature is checked; signatures, HMACs or tokens compared with `==`; tokens, reset codes or session ids from a non-crypto RNG (`random`, `math/rand`, `rand()`, `java.util.Random`).

**Why:** Secrets leak through the repo, debug pages leak code and environment, and switched-off verification lets an attacker forge tokens or read traffic.

**Fix:** Secrets from the environment or a secret store, with no fallback; debug only in dev config; TLS verification on; pinned JWT algorithms, verified before use; constant-time compares; a crypto RNG (`secrets`, `crypto/rand`, `random_bytes`, `SecureRandom`, `OsRng`).

**Not a finding when:** test fixtures and local dev config that cannot reach production; public keys and publishable client ids; randomness with no security role (shuffles, jitter).

**Sources:** https://top10.owasp.org/2025/A02_2025-Security_Misconfiguration/ · https://top10.owasp.org/2025/A04_2025-Cryptographic_Failures/ · https://top10.owasp.org/2025/A07_2025-Authentication_Failures/

### GSEC-09 · Error path that fails open, leaks internals or crashes on input

**Severity:** medium (high when an auth, signature or payment check fails open) · **Area:** security · **Taxonomy:** A10:2025, CWE-636, CWE-209, CWE-248, CWE-755 · **Applies to:** auth and verification code, handlers, background jobs

**Signals:** an error from a verify, authorize or parse call ignored or swallowed while execution continues (`_ = ...Verify(...)`, `except: pass`, `rescue nil`, an empty `catch`, `if err != nil { log... }` without a return); a default that grants access when a lookup fails; stack traces, SQL errors or exception messages returned to clients; Rust `unwrap()` / `expect()` / indexing on request data, Go nil dereference on optional input, a panic in a handler with no recovery.

**Why:** A failing dependency or crafted input turns a deny into an allow, leaks schema and paths, or kills the worker.

**Fix:** Fail closed: return or raise before the protected action. Send generic messages to clients and log details on the server. Handle the `Err` / `None` branch of input parsing explicitly.

**Not a finding when:** a framework-level handler turns the panic or exception into a 4xx/5xx without details and nothing was written yet; the ignored error is cosmetic (closing a response body, a log write).

**Sources:** https://top10.owasp.org/2025/A10_2025-Mishandling_of_Exceptional_Conditions/

## Per-stack signals

| Stack | Auth and object guards | Injection and escaping sinks | Traps |
|---|---|---|---|
| Laravel | `auth` / `can:` route middleware, `$this->authorize()`, `Gate::`, policies, `FormRequest::authorize()`; route-model binding loads the model before any policy | `DB::raw`, `*Raw(` with interpolation, `{!! !!}`, `$request->all()` into `create`/`update`/`fill`, `$guarded = []` | `withoutMiddleware`, CSRF `$except`, `APP_DEBUG=true`, `getClientOriginalName()` in `storeAs`, signed URLs without the `signed` middleware |
| Symfony | `#[IsGranted]`, `denyAccessUnlessGranted()`, voters, `access_control` in `security.yaml` | `createQuery` / `->where("...$x")` concatenation, Twig `\|raw` | `csrf_protection: false`, profiler outside `when@dev`, `#[MapEntity]` arguments guarded only by `ROLE_USER` |
| Django | `@login_required`, `@permission_required`, `LoginRequiredMixin`, DRF `permission_classes`, `get_queryset()` scoped to `request.user` | `.raw(f"...")`, `.extra(`, `RawSQL(`, `cursor.execute(f"...")`, `\|safe`, `mark_safe` | `@csrf_exempt`, `AllowAny`, `fields = "__all__"`, `DEBUG = True`, `ALLOWED_HOSTS = ["*"]` |
| FastAPI | `Depends(get_current_user)` / `Security(...)` on the route or `APIRouter(dependencies=...)` | `text(f"...")`, `execute(f"...")` | ORM rows returned without `response_model`, `allow_origins=["*"]` with `allow_credentials=True`, `httpx`/`requests` to a URL from input |
| Flask | `@login_required` below `@route`, `before_request` on the blueprint, `current_user` filters | `render_template_string` with input, `\|safe`, `Markup(` | `send_file(os.path.join(..., input))`, hardcoded `SECRET_KEY`, `debug=True` |
| Go | auth middleware in `Use` / `Group` / `With` registered before the routes (chi, gin, echo, gorilla, ServeMux wrappers); `r.PathValue` / `c.Param` ids scoped by the user | `fmt.Sprintf` SQL, GORM `Raw(fmt.Sprintf` / `Where("..." + x)`, `exec.Command("sh", "-c")`, `template.HTML(` | ignored `err` in auth (`_ = ...Verify`), `InsecureSkipVerify`, `math/rand` tokens, servers without timeouts, `io.ReadAll(r.Body)` without `MaxBytesReader` |
| Rust | axum/actix auth extractors (`AuthUser`, `Claims`, session) or an auth `.layer` / `.wrap` on the router; a handler without either is public | `format!` into `sqlx::query` / `execute` instead of `query!` or `.bind`, `Command::new("sh").arg("-c")` | `unsafe` blocks touching input-derived data, `unwrap()` / `expect()` on request data (one panic per request), `danger_accept_invalid_certs`, permissive `CorsLayer` |
| Rails | `before_action :authenticate_user!`, Pundit `authorize` / `policy_scope`, CanCanCan `load_and_authorize_resource`, `current_user.posts.find` | `where("... #{x}")`, `find_by_sql`, `order(params[...])`, `raw`, `.html_safe`, `<%==` | `skip_before_action`, `permit!`, `skip_forgery_protection`, `Marshal.load` / `YAML.load` on input |
| Java/Spring | `SecurityFilterChain` with `requestMatchers(...)`, `@PreAuthorize` / `@Secured` with method security enabled, repository queries that include the owner | `createQuery` / `createNativeQuery` or JDBC `Statement` with concatenation, `th:utext`, SpEL built from input | `permitAll()` on new paths, `csrf().disable()` with cookie sessions, exposed actuator endpoints, `@RequestBody` entities, `ObjectInputStream` |
