# Next.js security

Next.js 14-16, App Router and Pages Router, React 18/19. OWASP Top 10 (2025) and OWASP API Security Top 10 (2023).

Each item: severity is the default; `severity.md` escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read.

### NSEC-01 · Server Action performs a mutation or a read without its own authentication and authorization check

**Severity:** critical · **Area:** security · **Taxonomy:** A01:2025, API5:2023 (BFLA), API2:2023, CWE-862 · **Applies to:** App Router, Next 14 to 16 (Server Actions stable since 14); React 19 Server Functions

**Signals:** A new or changed function in a file that starts with 'use server', or an inline async function containing 'use server', that calls db/prisma/drizzle/fetch-with-credentials/revalidate*/cookies().set with no call to auth(), getSession(), getServerSession(), verifySession(), currentUser(), or a DAL helper that does those. Also: an action that trusts client flags such as formData.get('isAdmin'), a role argument, or searchParams for privilege decisions. Also: the page above the action has an auth redirect but the action body does not.

**Why:** Every Server Action is a public POST endpoint that anyone can call with the action ID, whatever the page UI shows. A page-level or layout-level check does not protect the actions defined in or imported by that page. The gap grows as more actions are added by copying existing ones.

**Fix:** Re-verify inside every action, or delegate to a server-only DAL function that does. Check authorization (role or ownership), not just login.
'use server'
export async function deletePost(id: string) {
  const session = await auth()
  if (!session?.user) throw new Error('Unauthorized')
  await dal.deletePostOwnedBy(session.user.id, id)
}

**Not a finding when:** Follow the call chain before flagging: many projects keep the check in a DAL function (data/*.ts with import 'server-only') and the action is a thin wrapper. That is the pattern the docs recommend. Some actions are public on purpose (login, signup, newsletter, contact form, password reset request). They need validation and rate limiting (NSEC-31), not an auth check. Wrapper helpers like authAction(), protectedAction() or next-safe-action middleware (`actionClient.use(authMiddleware)`) count as a check once you confirm the wrapper really verifies the session.

**Sources:** https://nextjs.org/docs/app/guides/data-security · https://nextjs.org/docs/app/guides/authentication · https://react.dev/reference/rsc/use-server · https://top10.owasp.org/2025/A01_2025-Broken_Access_Control/

### NSEC-02 · Route Handler or pages/api endpoint without authentication or function-level authorization

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, API2:2023, API5:2023, CWE-306, CWE-862 · **Applies to:** App Router route.ts (Next 13.2+), Pages Router pages/api/*

**Signals:** New export async function GET|POST|PUT|PATCH|DELETE in app/**/route.ts, or a new default export handler(req, res) in pages/api/**, that touches data or side effects and has no session or token check. Admin-sounding paths (api/admin, api/internal, api/export, api/users) with only an authentication check and no role check. A handler that relies on the proxy/middleware matcher covering '/api/:path*' as its only check.

**Why:** Route Handlers and API Routes are publicly reachable HTTP endpoints. The docs say to treat them like public APIs and verify the caller in the handler. Internal-only endpoints tend to multiply and get forgotten (API9).

**Fix:** Call the DAL session check at the top and return 401 or 403. Check the role or permission for privileged operations.
const session = await verifySession()
if (!session) return new Response(null, { status: 401 })
if (session.user.role !== 'admin') return new Response(null, { status: 403 })

**Not a finding when:** Some endpoints are public by design: health checks, sitemap/rss/robots, OG images, public content JSON, webhooks verified by signature (see NSEC-30), and Auth.js catch-all routes (app/api/auth/[...nextauth]). Library factory handlers (`export { handler as GET, handler as POST }`) do their own auth. Do not flag an unauthenticated GET that only returns data already public on the site.

**Sources:** https://nextjs.org/docs/app/guides/authentication · https://nextjs.org/docs/app/guides/backend-for-frontend · https://api-security.owasp.org/editions/2023/en/0x11-t10

### NSEC-03 · BOLA / IDOR: object ID from the client used without an ownership or tenant check

**Severity:** high · **Area:** security · **Taxonomy:** API1:2023 (BOLA), A01:2025, CWE-639 · **Applies to:** Server Actions, Route Handlers, pages/api, Server Components that read params/searchParams (all versions)

**Signals:** A Server Action argument or formData.get('id'|'postId'|'userId'|'orderId'|'teamId'), await params.id, searchParams.get('id'), or req.query.id passed straight into findUnique/findFirst/update/delete/where: { id } or a backend fetch(`/orders/${id}`) with no session.user.id or tenantId in the query and no comparison afterwards. Also: an action that takes userId as a parameter instead of reading it from the session.

**Why:** Authentication alone lets any logged-in user read or change another user's records by changing an ID. IDs in hidden inputs, action closures and dynamic segments are all client-controlled. This is the most common API flaw and gets worse as more object types are added.

**Fix:** Scope the query by owner or tenant, or load the object and compare it before acting. Take the acting user's ID from the session, never from arguments.
await db.post.delete({ where: { id: postId, authorId: session.user.id } })

**Not a finding when:** The resource may be public by design (published article by slug). The query may already include the owner in `where` (look for compound filters). Row-level security may be enforced in the database (Supabase/Postgres RLS with the user's JWT, not the service key), or a backend API may enforce ownership using the forwarded user token. Admin endpoints with an explicit role check can take arbitrary IDs.

**Sources:** https://nextjs.org/docs/app/guides/data-security · https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html · https://api-security.owasp.org/editions/2023/en/0x11-t10

### NSEC-04 · 'use server' module exports helpers that become callable endpoints

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, API5:2023, API9:2023, CWE-749 · **Applies to:** App Router, Next 14 to 16, React 19 Server Functions. The 'use cache' remark below applies only with Cache Components (Next 16) and is a hygiene note, not an endpoint issue.

**Signals:** A file with top-level 'use server' that exports functions that are not meant to be actions: getUserById(id), getAllUsers(), sendEmail(to, body), queryDb(sql), createAdmin(), functions that take a userId/tenantId argument, or functions that return raw records. A shared utils file that gains 'use server' so a client component can import it. Lower severity hygiene signal: an exported async function containing 'use cache' that takes userId and returns that user's data (only an endpoint if the file is also 'use server').

**Why:** Every exported async function in a 'use server' module is a Server Function the client can call with arbitrary serializable arguments. Moving a data helper into such a file quietly publishes it as an endpoint. The July 2026 advisory (CVE-2026-64643) showed that action and 'use cache' endpoint IDs can be disclosed globally, so ID secrecy is not protection. Separately, the Next.js docs say to keep per-user 'use cache' getters unexported so that server code cannot request another user's data by passing a different ID.

**Fix:** Put data helpers in a module with import 'server-only' (not 'use server'). Export only real actions from 'use server' files, each with its own auth. Keep per-user 'use cache' functions unexported and resolve the user inside the exported wrapper.

**Not a finding when:** Actions never referenced from client code are removed from the client bundle at build time (dead code elimination, docs data-security), so an unused export is lower risk (report it as low, not high). 'server-only' files are not endpoints. Actions that take an ID and then check ownership are fine (see NSEC-03). An exported 'use cache' function in a normal module (no 'use server') is not an HTTP endpoint; report only as a low hygiene note.

**Sources:** https://react.dev/reference/rsc/use-server · https://nextjs.org/docs/app/guides/data-security · https://nextjs.org/docs/app/guides/authentication-with-cache-components · https://nextjs.org/blog/july-2026-security-release

### NSEC-05 · No runtime validation of Server Action / Route Handler input (TypeScript types treated as validation)

**Severity:** medium · **Area:** security · **Taxonomy:** A05:2025, A06:2025, API8:2023, CWE-20 · **Applies to:** All routers and versions

**Signals:** formData.get('x') as string, `await request.json()` or req.body destructured and used directly, action parameters typed as `(data: CreateUserInput)` with no zod/valibot/yup parse, Number(params.id) with no NaN check, searchParams used as enum without an allowlist, files from formData.get('file') used with no type or size check.

**Why:** Action arguments and request bodies are fully client-controlled. TypeScript types disappear at runtime. Unvalidated input feeds injection, mass assignment, crashes (A10) and logic abuse.

**Fix:** Parse at the boundary with a schema and return field errors.
const parsed = Schema.safeParse(Object.fromEntries(formData))
if (!parsed.success) return { errors: parsed.error.flatten().fieldErrors }

**Not a finding when:** Validation may happen in the DAL function the action calls, or in a wrapper (next-safe-action `.inputSchema()`/`.schema()`, tRPC input). Check that before flagging. Values used only as opaque lookup keys in a parameterized ORM query are low risk. Report those as low, not high.

**Sources:** https://nextjs.org/docs/app/guides/data-security · https://nextjs.org/docs/app/guides/authentication · https://react.dev/reference/rsc/use-server

### NSEC-06 · Injection sinks: raw SQL strings, path traversal with route params, shell/eval with user data

**Severity:** critical · **Area:** security · **Taxonomy:** A05:2025, CWE-89, CWE-22, CWE-78, CWE-94 · **Applies to:** All routers and versions (server code: actions, route handlers, gSSP, Server Components)

**Signals:** $queryRawUnsafe / $executeRawUnsafe, sql.raw(), knex.raw(`...${x}`), db.query(`SELECT ... ${x}`), mysql.query(string + x); fs.readFile / createReadStream / path.join(process.cwd(), params.slug) or path.resolve(..., searchParams.get('file')); child_process exec/execSync/spawn with shell:true and interpolated input; eval, new Function, vm.runInNewContext with request data; RegExp built from user input (ReDoS).

**Why:** Server Components and actions run with full server privileges, so one interpolated value can read the database or filesystem. [param] folders are user input, as the Next audit checklist points out.

**Fix:** Use tagged-template or parameterized queries (sql`... ${x}` in drizzle/postgres.js/Prisma $queryRaw tagged form). For files, resolve the path and check it stays inside an allowed base directory, or map IDs to known files. Use execFile with an argument array and no shell.

**Not a finding when:** Prisma `$queryRaw` used as a tagged template (`$queryRaw`...``) and drizzle/postgres.js/Vercel Postgres `sql` tags parameterize automatically, so they are safe. The dangerous forms are the *Unsafe variants and string concatenation. path.join with a value from generateStaticParams or a constant allowlist is fine.

**Also check:** ORM and NoSQL filter or operator injection: client JSON passed as a whole filter (where: body.filter, Mongo find({ email: body.email }) where email can be { $ne: null }, Prisma where built from request objects, dynamic orderBy or column names from query params). Not covered by NSEC-06 (raw SQL only) or NSEC-07 (mass assignment on writes). Source: https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html

**Sources:** https://nextjs.org/docs/app/guides/data-security · https://top10.owasp.org/2025/A05_2025-Injection/ · https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html

### NSEC-07 · Mass assignment: whole request body or FormData spread into create/update

**Severity:** high · **Area:** security · **Taxonomy:** API3:2023 (BOPLA), A01:2025, CWE-915 · **Applies to:** Server Actions, Route Handlers, pages/api (all versions)

**Signals:** data: Object.fromEntries(formData), data: await request.json(), data: req.body, { ...body }, { ...input, updatedAt } passed to prisma/drizzle/mongoose create/update/upsert, or forwarded as-is to a backend PATCH. Models with sensitive columns (role, isAdmin, ownerId, tenantId, emailVerified, balance, status, price).

**Why:** Attackers add extra fields (role: 'admin', ownerId) that the form never showed. The ORM writes them. Each new column added to the model later becomes writable without anyone noticing.

**Fix:** Allowlist fields with a strict schema (z.object({...}).strict() or .pick()) and build the update object explicitly. Set ownerId and tenantId from the session.

**Not a finding when:** If a strict schema parse runs right before the spread and the schema has only safe fields, it is fine. Models without privileged columns (for example a pure contact message) are low risk.

**Sources:** https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html · https://api-security.owasp.org/editions/2023/en/0x11-t10

### NSEC-08 · Server Action / Route Handler returns full DB records or upstream API payloads

**Severity:** medium · **Area:** security · **Taxonomy:** API3:2023 (excessive data exposure), A01:2025, CWE-201, CWE-213 · **Applies to:** All routers and versions

**Signals:** return db.user.update(...), return await prisma.x.findMany() without select, Response.json(user), res.json(order) where the model has passwordHash, tokens, internal notes, email or phone of other users. An action that returns the whole upstream response (return await res.json()) from a backend or CMS. Server Action return values used by useActionState.

**Why:** Server Action return values and handler responses are serialized to the client and visible in devtools, whatever the UI renders. Columns added to the model later leak automatically.

**Fix:** Return a DTO with only the fields the UI needs ({ success: true } or a picked object), or use `select` in the query.

**Not a finding when:** Models or types that contain only public fields, explicit select/columns, or a DTO mapping function in the DAL. Auth.js session objects by default expose only name, email and image.

**Sources:** https://nextjs.org/docs/app/guides/data-security · https://nextjs.org/docs/app/guides/authentication · https://api-security.owasp.org/editions/2023/en/0x11-t10

### NSEC-09 · Sensitive server data passed to Client Components or Pages Router props (RSC payload / __NEXT_DATA__)

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, CWE-200, CWE-201 · **Applies to:** App Router (Server to Client Component props, React 18/19); Pages Router getServerSideProps/getStaticProps props

**Signals:** A Server Component passing user={userRow}, session={session}, config={process.env...}, token={...} into a component whose file has 'use client'. 'use client' prop types that accept whole models (User, Order, Session) instead of picked fields. Pages Router: return { props: { user } } or props: { session } in getServerSideProps with a full record, props containing API keys or tokens. A context provider in a client file fed with the raw session.

**Why:** Everything passed to a Client Component is serialized into the RSC payload. Pages Router props are embedded in the HTML (__NEXT_DATA__) for hydration. Hidden fields are still delivered even when not rendered.

**Fix:** Build a minimal DTO on the server and pass only rendered fields. Optionally enable experimental.taint and call experimental_taintObjectReference / taintUniqueValue on secret-bearing objects and values as defense in depth.

**Not a finding when:** The object may already be a DTO (check the DAL function return shape). Passing data to another Server Component (no 'use client' in the target file or its import chain) is not serialized to the client. Taint does not cover derived values (uppercased or substringed), so its absence is not a finding by itself.

**Also covers DEC-06 (Whole Drupal resources passed to Client Components or page props).** Signals: 'use client' component props typed DrupalNode, JsonApiResource, DrupalUser or any; <Card node={node}/> where node is a raw getResource result; getStaticProps or getServerSideProps returning { props: { resource } }; include=uid,revision_uid with the whole object passed down Not a finding when: Data that stays in Server Components is not serialized. A resource already cut down with fields[type]=title,path,body and fetched anonymously exposes nothing extra. Check how it was fetched before flagging. Anonymous JSON:API already hides fields the public cannot view, so with an unprivileged client this is mostly a size issue.

**Also covers NPERF-16 (Oversized data crossing the server-to-client boundary (page props, RSC props)).** Signals: Returning whole ORM rows or lists in `props` (`props: { products }` with nested relations). Passing full CMS entries or `user` objects to 'use client' components. `JSON.parse(JSON.stringify(data))` to make large objects serializable. Not a finding when: Small, already-trimmed props are fine. Passing server-rendered JSX as children to a client component does not ship its source or data as props. Watch for the security angle (tokens, emails, internal ids) even when size is small. The diff rarely shows how large the real data is, so only flag when the query has no select/pagination or includes broad relations.

**Also covers NSEC-10 (Data-access or secret-handling module without 'server-only' guard).** Signals: New lib/db.ts, lib/dal.ts, data/*.ts, lib/session.ts or services that import a DB client, read process.env.*SECRET*/*KEY*, or hold hardcoded credentials, without import 'server-only' at the top. The same module imported from a 'use client' file somewhere in the diff. Not a finding when: Non-NEXT_PUBLIC_ env vars are not inlined into client bundles (they become undefined there), so the missing guard alone does not leak env secrets. Report it as low unless the module has hardcoded secrets or proprietary logic, or is imported client-side. 'use server' files are resolved in the server layer and are already protected. Pages Router-only projects cannot use this guard the same way.

**Sources:** https://nextjs.org/docs/app/guides/data-security · https://nextjs.org/docs/pages/building-your-application/data-fetching/get-server-side-props · https://react.dev/reference/react/experimental_taintUniqueValue · https://nextjs.org/docs/app/api-reference/config/next-config-js/taint · https://nextjs.org/docs/app/getting-started/server-and-client-components · https://nextjs.org/docs/app/getting-started/server-and-client-components#preventing-environment-poisoning

### NSEC-11 · Inline Server Action closure captures secrets or privileged values

**Severity:** medium · **Area:** security · **Taxonomy:** A04:2025, A01:2025, CWE-200 · **Applies to:** App Router, Next 14 to 16

**Signals:** An async function with 'use server' defined inside a Server Component body that references outer variables such as apiKey, token, session.accessToken, user.passwordHash, a secret-bearing config, or a DB row. Also: NEXT_SERVER_ACTIONS_ENCRYPTION_KEY committed in .env or prefixed NEXT_PUBLIC_.

**Why:** Captured variables make a round trip through the client, encrypted with a per-build key. The docs say not to rely on that encryption alone. A leaked or committed encryption key exposes and allows tampering with every closure.

**Fix:** Capture only non-sensitive identifiers and re-read secrets or session inside the action body. Keep NEXT_SERVER_ACTIONS_ENCRYPTION_KEY in the deployment secret store.

**Not a finding when:** Capturing a public ID or version number (the docs' own publishVersion example) is fine, but the action still needs NSEC-01 and NSEC-03 checks. Module-level actions in 'use server' files have no closure.

**Sources:** https://nextjs.org/docs/app/guides/data-security

### NSEC-12 · Secret exposed through NEXT_PUBLIC_ env var, next.config `env`, or a committed .env file

**Severity:** high · **Area:** security · **Taxonomy:** A02:2025, A04:2025, CWE-200, CWE-798 · **Applies to:** All routers and versions (NEXT_PUBLIC_ since 9.4)

**Signals:** NEXT_PUBLIC_*SECRET*, *_API_KEY, *TOKEN*, *PASSWORD*, *PRIVATE*, *SERVICE_ROLE*, *DB_*; process.env.NEXT_PUBLIC_X used in a server-to-server call to a private API; next.config `env: { SECRET: process.env.SECRET }` (inlined at build); .env, .env.local or .env.production added to git; a .gitignore change that removes .env*; secrets hardcoded in next.config or client files.

**Why:** NEXT_PUBLIC_ values are inlined into the JS bundle at build time and are readable by anyone. They also stay frozen in built artifacts, so rotating them requires a rebuild.

**Fix:** Drop the prefix and read the value only in server code (DAL, route handler, action). Proxy the call through the server if the browser needs the result. Rotate any secret that was already built into a bundle. Keep .env* in .gitignore and commit only .env.example.

**Not a finding when:** Some keys are designed to be public: Stripe pk_*, Google Maps/Analytics IDs, Sentry DSN, Algolia search-only key, Firebase web config, reCAPTCHA site key, and a Supabase anon key when RLS is on (check that). .env.example or .env.test with dummy values is fine.

**Also covers DEC-07 (OAuth client secret or Drupal access token reaches the browser).** Signals: NEXT_PUBLIC_DRUPAL_CLIENT_SECRET or any NEXT_PUBLIC_*SECRET*, *TOKEN*, *PREVIEW*; next.config.js env: { DRUPAL_CLIENT_SECRET: ... } (always inlined into the bundle); publicRuntimeConfig with secrets; new NextDrupal(...auth...) or getAccessToken() imported from a 'use client' file; localStorage.setItem('access_token'...); access_token in props or JSON; lib/drupal.ts without import 'server-only' Not a finding when: NEXT_PUBLIC_DRUPAL_BASE_URL is meant to be public. A public PKCE client_id is not a secret. A user's own token in an httpOnly, Secure cookie used by the server is the recommended pattern. A dynamic process.env[name] lookup is not inlined.

**Also check:** next.config exposure switches: productionBrowserSourceMaps: true (ships source and comments to browsers), poweredByHeader left on, output tracing or public/ folder committed with backups, .map and .env files under public/. Source: https://nextjs.org/docs/app/api-reference/config/next-config-js/productionBrowserSourceMaps

**Sources:** https://nextjs.org/docs/app/guides/environment-variables · https://nextjs.org/docs/app/guides/production-checklist · https://nextjs.org/docs/app/api-reference/config/next-config-js/env · https://nextjs.org/docs/app/guides/data-security

### NSEC-13 · middleware.ts / proxy.ts used as the only authentication or authorization layer

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, A07:2025, CWE-288, CVE-2025-29927 · **Applies to:** All versions with middleware (12+) or proxy (16+). CVE-2025-29927 affects 11.1.4 to 15.2.2 (patched 12.3.5, 13.5.9, 14.2.25, 15.2.3). May 2026: four bypass advisories (App Router segment-prefetch GHSA-267c and follow-up GHSA-26hh, Pages Router i18n default-locale GHSA-36qx, dynamic route parameter injection GHSA-492v), all 13.x to 16.x, fixed in 15.5.18 / 16.2.6, 13.x and 14.x get no fix. July 2026: CVE-2026-64642 (App Router built with Turbopack and a single i18n locale), fixed in 15.5.21 / 16.2.11.

**Signals:** Auth or role logic added to middleware.ts/proxy.ts (cookies().get('session'), NextResponse.redirect('/login'), `export { auth as middleware }`, `export default auth(...)`, `authorized` callback in auth.config.ts) while the pages, route handlers or actions under those paths have no session check of their own. matcher edits that exclude paths (api, _next, static, locales) or move routes. Custom header trust such as checking x-middleware-subrequest.

**Why:** Middleware and proxy have been bypassed several times: the x-middleware-subrequest header in 2025, four more bypass advisories in May 2026 and one in July 2026. The Next.js docs also say a matcher that excludes a path skips Server Function POSTs on that path. When proxy is the only gate, one framework bug or one matcher change exposes everything behind it.

**Fix:** Treat proxy as an optimistic redirect only. Enforce auth in the DAL, every Server Action and every Route Handler. Keep next patched. If upgrading is impossible for CVE-2025-29927, strip x-middleware-subrequest at the edge.

**Not a finding when:** Proxy checks are fine and recommended as long as the data layer also checks. Static pages whose content is shared between users (a paywall) can only be protected in proxy, per the docs. Accept that there, but require a patched next version. Vercel-hosted apps were auto-protected from CVE-2025-29927 specifically, not from every later bypass.

**Also covers DEC-16 (Preview or private routes protected only in middleware/proxy on a vulnerable Next version).** Signals: middleware.ts or proxy.ts doing the only auth check for /preview, /api/draft, /account or /api/drupal/*; package.json or lockfile setting next to a version below 15.5.21 or 16.2.11 (or below 14.2.25 / 15.2.3); matcher configs that skip locale-prefixed or _next/data paths Not a finding when: Middleware used only for redirects or locale detection. Auth that is also enforced inside the handler or data access layer. The version is already patched. CVE-2025-29927 is not exploitable on Vercel-hosted deployments (they are protected automatically).

**Sources:** https://github.com/vercel/next.js/security/advisories/GHSA-f82v-jwr5-mffw · https://nextjs.org/docs/app/guides/authentication · https://nextjs.org/docs/app/api-reference/file-conventions/proxy · https://vercel.com/changelog/next-js-may-2026-security-release · https://nextjs.org/blog/july-2026-security-release · https://github.com/advisories/GHSA-f82v-jwr5-mffw · https://nextjs.org/docs/app/guides/data-security

### NSEC-14 · Proxy-injected identity headers trusted downstream, or request headers reflected into the response

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, A02:2025, CWE-290, CWE-918, CVE-2025-57822 · **Applies to:** All versions with middleware/proxy for the identity-header part. The reflection SSRF (GHSA-4342-x723-ch2f, CVE-2025-57822) affects self-hosted apps below 14.2.32 / 15.4.7 only, so it matters mainly on old lockfiles.

**Signals:** The proxy sets requestHeaders.set('x-user-id'|'x-user-role'|'x-tenant', ...) and pages, actions or handlers read (await headers()).get('x-user-id') for authorization. The proxy does not delete the incoming header of the same name first. NextResponse.next({ headers: request.headers }) or NextResponse.next({ headers: requestHeaders }) (response headers) instead of { request: { headers } }. Trusting x-forwarded-for / x-real-ip / x-forwarded-host for auth or allowlists.

**Why:** If proxy does not run for a path (matcher, bypass CVE) or does not overwrite the header, the client supplies the identity. Passing request headers as response headers exposes internal values and was the root of a 2025 SSRF advisory in self-hosted setups.

**Fix:** Downstream code re-derives identity from the session cookie. If headers are used, the proxy must always delete and then set them, and must use NextResponse.next({ request: { headers } }). Treat x-forwarded-* as spoofable unless your platform overwrites them.

**Not a finding when:** Headers used only for non-security purposes (locale, A/B bucket, request ID, CSP nonce in x-nonce) are fine. Platforms like Vercel overwrite x-forwarded-for. Check the hosting before flagging IP-based logic. On next >= 14.2.32 / 15.4.7 the reflection pattern is a hygiene issue, not the original SSRF.

**Sources:** https://nextjs.org/docs/app/api-reference/file-conventions/proxy · https://nextjs.org/docs/app/guides/backend-for-frontend · https://github.com/vercel/next.js/security/advisories/GHSA-4342-x723-ch2f

### NSEC-15 · Auth check only in layout.tsx (or `return null` gating) protecting nested pages and slots

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, CWE-862 · **Applies to:** App Router, all versions

**Signals:** layout.tsx that calls auth()/getSession() and redirects or returns null, while the page.tsx files, parallel route slots (@slot) or actions under it fetch protected data with no check of their own. A layout that hides {children} for unauthorized users.

**Why:** Layouts do not re-render on client navigation, and they do not stop child segments or slots from running or from appearing in the RSC payload. Server Actions in those pages are separate entry points anyway.

**Fix:** Do the check in the DAL function that fetches the data (getUser(), getDashboardData()) or in the page or leaf component, not only in the layout.

**Not a finding when:** A layout check for UI purposes (showing the user menu) is fine when the pages below fetch through an authorizing DAL. Confirm that before flagging.

**Sources:** https://nextjs.org/docs/app/guides/authentication

### NSEC-16 · Vulnerable or unsupported next / React Server Components version in package.json or lockfile

**Severity:** high · **Area:** security · **Taxonomy:** A03:2025, CWE-1104, CWE-502 (CVE-2025-55182), CVE-2025-29927 · **Applies to:** Next 14 and older (unsupported, no patches), 15.x and 16.x below the current patch listed at github.com/vercel/next.js/security/advisories. RSC deserialization CVEs (CVE-2025-55182 and follow-ups) apply to App Router only. Image optimizer, proxy bypass and i18n advisories also hit Pages Router apps.

**Signals:** package.json or lockfile lines for "next": 14.x or older; 15.x or 16.x below the current minimum (as of 2026-09-29 the last shipped patches are 16.3.6 / 15.5.26, and a scheduled release on 2026-09-30 brings 16.3.7 / 15.5.27 with nine advisories, one critical: read the blog at review time, do not hardcode); "react-server-dom-webpack|turbopack|parcel" below 19.0.6 / 19.1.7 / 19.2.6 (non-Next RSC frameworks); a PR that downgrades next or pins an old canary (14.3.0-canary.77+ carried React2Shell). Image optimizer exposure to AVIF: next below 16.3.3 / 15.5.24 that optimizes remote or user-uploaded images through the default loader (any next from 10.0.0). next/og ImageResponse on the Node runtime with next >=16.2.0 <16.3.6 (15.x is not affected). Windows-hosted server below 16.3.3 / 15.5.24 that uses both Pages Router and App Router without Cache Components (CVE-2026-75604; the host OS is rarely visible in a diff, mention only if Dockerfile or CI shows Windows).

**Why:** CVE-2025-55182 was a CVSS 10 pre-auth RCE through RSC deserialization, reachable on any App Router app with a Server Function endpoint. At least five follow-up DoS fixes and one source-exposure fix shipped through May 2026, and Next now ships security patches monthly plus out-of-band. 14.x gets no fixes at all. Leaving the version alone means inheriting every later bug.

**Fix:** Upgrade to the newest patch of the Active LTS (16.x) or Maintenance LTS (15.5.x) line. Check github.com/vercel/next.js/security/advisories and nextjs.org/blog for the current minimum at review time. Move 14.x projects to 15.5 or 16. Note that the AVIF fix works by disabling AVIF optimization, so expect a behavior change after upgrading.

**Not a finding when:** Next ships its own copy of the RSC runtime, so the root `react` version alone does not show exposure. Judge by `next`. Pages Router-only apps are not affected by the RSC deserialization CVEs, but they are still affected by the proxy bypass, image optimizer and i18n advisories. Vercel/Netlify firewall mitigations reduce exposure but are not a reason to skip the upgrade. A diff that does not touch package.json should get only a one-line note if the current version is old, not a finding for the change. package.json ranges (^16.2.0) do not show the resolved version, read the lockfile. Do not cite CVE-2025-66478: it was rejected as a duplicate of CVE-2025-55182.

**Also covers NPERF-34 (Next.js resolved to a version with known cache poisoning or cache-confusion advisories (or to an unpatched 13.x/14.x line)).** Signals: package.json or lockfile `"next":` resolving below the current patched release of its line, or to any 13.x/14.x. Downgrade or pin commits. Image optimization of API-route images that vary by cookie or Authorization (57752). ISR with next start/standalone, or a CDN caching 204s (49826). A CDN or reverse proxy config in front of an App Router app that ignores Vary or strips the `_rsc` query parameter (44576/44582). fetch(new Request(init), differentInit) or cached POST bodies (64648/64647). Not a finding when: 46982 does not affect App-Router-only apps or Vercel deployments. 57752 needs image-serving API routes that vary by request headers. 49826 needs 15.1.x with static pages and a cache that stores the 204. 44576/44582 need a shared cache that does not partition RSC variants. 64648/64647 need the specific fetch/Request pattern; standard fetch(url, init) and cache: 'no-store' are not affected, and Pages Router is unaffected by 64648. Check the resolved version in the lockfile, not the caret range.

**Sources:** https://github.com/vercel/next.js/security/advisories · https://github.com/vercel/next.js/security/advisories/GHSA-9qr9-h5gf-34mp · https://react.dev/blog/2025/12/03/critical-security-vulnerability-in-react-server-components · https://react.dev/blog/2025/12/11/denial-of-service-and-source-code-exposure-in-react-server-components · https://nextjs.org/support-policy · https://nextjs.org/blog/august-2026-security-release · https://nextjs.org/blog/nextjs-security-update-september-22-2026 · https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026 · https://github.com/vercel/next.js/security/advisories/GHSA-2xp9-vwfh-vxw4 · https://github.com/advisories/GHSA-gp8f-8m3g-qvj9 · https://github.com/advisories/GHSA-67rr-84xm-4c7r · https://github.com/advisories/GHSA-g5qg-72qw-gw5v · https://github.com/vercel/next.js/security/advisories/GHSA-wfc6-r584-vfw7 · https://github.com/vercel/next.js/security/advisories/GHSA-vfv6-92ff-j949 · https://github.com/vercel/next.js/security/advisories/GHSA-68g3-v927-f742

### NSEC-17 · Risky dependency additions: floating ranges, non-registry sources, lockfile drift

**Severity:** medium · **Area:** security · **Taxonomy:** A03:2025, A08:2025, CWE-1357, CWE-829 · **Applies to:** Any npm/pnpm/yarn/bun project

**Signals:** package.json versions set to "latest", "*", "x", or git+https/github:/http tarball URLs. A lockfile with `resolved` pointing to a non-registry host, integrity removed, or the lockfile deleted or not updated while package.json changed. New packages with postinstall scripts (package-lock.json marks them with hasInstallScript: true). Names one letter off popular packages. `overrides`/`resolutions` that pin a vulnerable version.

**Why:** A03:2025 is now its own category. A floating or unpinned source lets a compromised upstream publish straight into your build. Lockfile drift makes builds non-reproducible.

**Fix:** Pin exact or caret ranges from the registry, commit the updated lockfile, and use npm ci / pnpm install --frozen-lockfile in CI. Review install scripts of new packages.

**Not a finding when:** workspace:, file: or link: protocols in monorepos. Renovate/Dependabot PRs that bump the lockfile coherently. Private registry hosts configured in .npmrc.

**Sources:** https://top10.owasp.org/2025/A03_2025-Software_Supply_Chain_Failures/ · https://top10.owasp.org/2025/A08_2025-Software_or_Data_Integrity_Failures/

### NSEC-18 · SSRF: server-side fetch of a user-supplied URL or host

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025 (CWE-918), API7:2023, API10:2023 · **Applies to:** All routers and versions; Route Handlers, Server Actions, gSSP, generateMetadata, opengraph-image / ImageResponse, proxy rewrites

**Signals:** fetch(url), axios.get(url), got(url), new URL(input) where the input comes from searchParams, params, formData, a request body or headers. Catch-all proxy handlers app/api/[...path]/route.ts that build the upstream URL from user segments without a fixed origin. NextResponse.rewrite(new URL(userInput)). Link-preview, oEmbed, webhook-test, 'import from URL' and image-fetch features. fetch without redirect: 'manual' on user-influenced URLs.

**Why:** The server can reach cloud metadata (169.254.169.254), internal services and the Drupal admin or backend network that the attacker cannot reach directly. Next.js has shipped several SSRF advisories of its own (middleware redirects, WebSocket upgrades, Server Actions on custom servers, rewrites), which shows how easily this shape appears.

**Fix:** Fix the origin in code (new URL(path, 'https://api.internal') and check url.origin). Allowlist hosts and schemes (https only), resolve DNS and reject private or link-local ranges, disable or re-validate redirects, and set timeouts.

**Not a finding when:** User input used only as an encoded path or query value against a hardcoded origin is not host-controlling, though path injection like ../ is still worth a note. URLs coming from trusted CMS or config data, not the request, are fine.

**Also covers DEC-12 (Next proxy to Drupal forwards request-controlled hosts or paths with server credentials).** Signals: app/api/[...path]/route.ts or pages/api/proxy/[...path].ts doing fetch(`${DRUPAL}/${params.path.join('/')}`) with an Authorization header; fetch(searchParams.get('url')); next.config rewrites()/redirects() whose destination hostname uses a :param (for example destination: 'https://:tenant.example.com/...'); has-based host rewrites; images.dangerouslyAllowLocalIP: true Not a finding when: A rewrite to a fixed Drupal host that passes only the path (source '/jsonapi/:path*' to destination 'https://cms.example.com/jsonapi/:path*') with no credentials is ordinary. The Drupal access rules then apply to the anonymous caller. next-drupal translatePath(path) on user paths is fine because it only resolves routes.

**Also check:** Forwarding credentials to a wrong host: catch-all proxy route handlers that do new Request(url, request) or copy Cookie / Authorization headers to an upstream whose host is influenced by input, and server fetches that attach the session token to third-party URLs. The Next.js docs example copies the whole request to a fixed origin, which is fine only because the origin is fixed. Source: https://nextjs.org/docs/app/guides/backend-for-frontend (Proxying to a backend, Working with headers)

**Sources:** https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html · https://api-security.owasp.org/editions/2023/en/0x11-t10 · https://top10.owasp.org/2025/A01_2025-Broken_Access_Control/ · https://nextjs.org/docs/app/guides/backend-for-frontend · https://github.com/advisories/GHSA-p9j2-gv94-2wf4 · https://nextjs.org/blog/july-2026-security-release · https://api-security.owasp.org/editions/2023/en/0xa7-server-side-request-forgery/

### NSEC-19 · rewrites()/redirects() destination hostname built from request input; Host-header trust on custom servers

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025 (CWE-918, CWE-601), A02:2025, CVE-2026-64645, CVE-2026-64649 · **Applies to:** next.config rewrites/redirects: CVE-2026-64645 affects >=12.0.0 <15.5.21 and >=16.0.0 <16.2.11 even with hostname suffixes; CVE-2026-64649 affects Server Actions on custom servers (server.js) when Host-associated headers are attacker-controlled

**Signals:** In next.config: destination: 'https://:tenant.api.example.com' or a destination hostname that uses a `has` capture (?<region>.+). Loose captures like (.+) or (.*) in hostname positions. A custom server.js/server.ts that forwards the Host / X-Forwarded-Host header unchanged into Next, combined with Server Actions that redirect.

**Why:** Next's own advisory showed that a request-controlled hostname can escape the intended suffix. That gives SSRF through rewrites and an open redirect through redirects. Custom servers that trust Host let Server Actions send outbound requests to attacker hosts.

**Fix:** Do not build external hostnames from request input. If you must, constrain the capture to hostname-safe characters, for example (?<region>[a-z0-9-]+), or map to an allowlist. Upgrade to a patched next. On custom servers, normalize or pin the Host header.

**Not a finding when:** Params used only in the path part of an external destination ('https://api.example.com/:path*') are not hostname control. Internal rewrites to local routes are fine.

**Also check:** Host header used to build absolute URLs in password-reset, verification or invite emails and redirects: diff signals (await headers()).get('host' | 'x-forwarded-host'), req.headers.host interpolated into a URL; fix is a fixed NEXTAUTH_URL / SITE_URL env var. Source: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

**Sources:** https://github.com/vercel/next.js/security/advisories/GHSA-p9j2-gv94-2wf4 · https://nextjs.org/blog/july-2026-security-release

### NSEC-20 · Image Optimizer config opens SSRF, XSS or resource abuse (remotePatterns wildcards, SVG, local IPs)

**Severity:** medium · **Area:** security · **Taxonomy:** A02:2025, API7:2023, API4:2023, CWE-918, CWE-79 · **Applies to:** next/image default loader, self-hosted or Vercel; options by version: domains deprecated v14.0.0, contentDispositionType default 'attachment' v15.0.0, dangerouslyAllowLocalIP (default false) and maximumRedirects (default 3) v16.0.0, qualities required in v16, maximumResponseBody v16.1.2

**Signals:** images.remotePatterns entries with hostname: '**' or '*', or broad '**.amazonaws.com' / '**.cloudfront.net' without pathname; protocol, pathname or search omitted (implies **); images.domains (deprecated); dangerouslyAllowSVG: true without contentSecurityPolicy "script-src 'none'; sandbox;" and contentDispositionType: 'attachment'; contentDispositionType: 'inline'; dangerouslyAllowLocalIP: true; maximumRedirects raised above the default of 3; localPatterns without search. Note: images.formats containing 'image/avif' is NOT the trigger for the August 2026 AVIF RCE (that is about AVIF input files, handled in NSEC-16).

**Why:** The optimizer fetches and processes remote images on your server. Wildcards turn /_next/image into an open fetch proxy and CPU sink (several 2025 and 2026 DoS and content-injection advisories, for example CVE-2026-64644 SVG CPU exhaustion). Redirects from allowed hosts are not re-checked against remotePatterns (docs). SVG can carry scripts.

**Fix:** Scope each pattern to protocol, exact hostname and pathname prefix (for example https://bucket.s3.amazonaws.com/my-bucket/**). Set search explicitly. Keep SVG off or keep CSP plus attachment. Keep dangerouslyAllowLocalIP false and maximumRedirects low or 0.

**Not a finding when:** A custom `loader` (Cloudinary, Imgix, Drupal image styles) or unoptimized: true bypasses the Next optimizer, so remotePatterns breadth matters less. A wildcard subdomain of your own domain (**.yourcompany.com) is usually fine. Tenant-shared hosts (S3, Cloudinary, GitHub user content) without a path restriction are the real risk. `.svg` src is served unoptimized automatically, so dangerouslyAllowSVG is only needed for the optimizer path.

**Also covers DEC-13 (next/image remotePatterns too broad for the Drupal files host).** Signals: next.config images.remotePatterns with hostname: '**' or protocol and pathname omitted (omitted fields imply **); missing pathname ('/sites/default/files/**'); images.domains; dangerouslyAllowSVG: true without contentSecurityPolicy or with contentDispositionType: 'inline'; dangerouslyAllowLocalIP: true (often added so the DDEV or docker Drupal works); maximumRedirects raised while patterns are broad Not a finding when: Drupal image style URLs carry ?itok=..., so leaving search unset (or a fixed value) is often deliberate; search: '' would block them. Flag it as low severity only if hostname and pathname are tight. dangerouslyAllowLocalIP inside a NODE_ENV === 'development' branch is fine. A single '*' hostname matches one subdomain segment only, so it is not the same as '**'.

**Also covers NPERF-23 (Image optimizer config that multiplies work or cache entries, or opens it to abuse).** Signals: images.remotePatterns with `hostname: '**'` or protocol-only patterns. images.domains. A minimumCacheTTL far below the version default (for example 0, or 60 on 16). images.dangerouslyAllowLocalIP: true or a raised maximumRedirects. Large custom deviceSizes/imageSizes/qualities arrays. Image src built from user input or query strings. Not a finding when: A custom loader pointing at an external image CDN bypasses the built-in optimizer. On Next 14/15 a minimumCacheTTL of 60 is the default, not a smell. A low TTL can be deliberate for frequently replaced images at the same URL, but a versioned URL is the better fix. dangerouslyAllowLocalIP is intended only for private networks.

**Sources:** https://nextjs.org/docs/app/api-reference/components/image · https://github.com/vercel/next.js/security/advisories · https://nextjs.org/blog/july-2026-security-release · https://nextjs.org/blog/august-2026-security-release · https://nextjs.org/blog/next-16 · https://github.com/advisories/GHSA-g5qg-72qw-gw5v

### NSEC-21 · Open redirect through redirect(), NextResponse.redirect(), router.push() or location with user input

**Severity:** medium · **Area:** security · **Taxonomy:** A01:2025, CWE-601 · **Applies to:** All routers and versions (next/navigation redirect accepts absolute URLs)

**Signals:** redirect(searchParams.get('next'|'returnTo'|'callbackUrl'|'redirect'|'url')), redirect(formData.get('redirectTo') as string), NextResponse.redirect(new URL(param, request.url)) (an absolute param wins over the base), res.redirect(req.query.next), router.push(query.next), window.location.href = param, Auth.js redirect callback returning url unchecked, login pages with a ?next= param.

**Why:** Redirects to attacker domains after login are a staple of phishing and token theft. new URL(abs, base) quietly accepts absolute and protocol-relative (//evil.com) values.

**Fix:** Resolve against your origin and compare origins, as in the docs callback example.
const dest = new URL(next ?? '/', request.url)
if (dest.origin !== request.nextUrl.origin) return new Response('Invalid redirect', { status: 400 })
Or accept only paths that start with a single '/' and not '//' or '/\'.

**Not a finding when:** Redirect targets from a server allowlist, a DB or CMS lookup (the draft-mode docs pattern redirect(post.slug)), or a constant. Templated internal paths like `/posts/${id}` are same-origin as long as id cannot start with '/'.

**Sources:** https://nextjs.org/docs/app/api-reference/functions/redirect · https://nextjs.org/docs/app/guides/backend-for-frontend · https://nextjs.org/docs/app/guides/draft-mode · https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

### NSEC-22 · dangerouslySetInnerHTML (or raw-HTML parsers) with CMS or user HTML and no sanitization

**Severity:** high · **Area:** security · **Taxonomy:** A05:2025, CWE-79 · **Applies to:** React 18/19, both routers; decoupled Drupal/headless CMS frontends

**Signals:** dangerouslySetInnerHTML={{ __html: node.body.value | body.processed | post.content | comment.text | field.html }}, html-react-parser / react-html-parser / interweave on remote HTML, marked() or markdown-it with html: true, rehype-raw without rehype-sanitize, remark-html with sanitize: false, innerHTML in useEffect.

**Why:** React escapes by default, and this prop turns that off. Any editor-controlled, user-generated or compromised CMS content becomes script on your origin and can reach session data and Server Actions.

**Fix:** Sanitize server-side with an allowlist (isomorphic-dompurify, sanitize-html, rehype-sanitize) before rendering, or render structured fields as React elements. Pair with a CSP (NSEC-25).

**Not a finding when:** Drupal `processed` output from a restricted text format (Basic HTML with filter_html) is already filtered by Drupal. Check which text formats editors can use: Full HTML is not safe. Static strings from the repo, build-time MDX written by developers, and output of a sanitizer applied a few lines earlier are fine.

**Also covers DEC-14 (Rendering Drupal rich text from .value instead of .processed).** Signals: dangerouslySetInnerHTML={{ __html: node.body.value }}; html-react-parser parse(node.body.value) or parse(field.value); GraphQL selecting body { value } instead of processed; custom sanitizers replacing Drupal text formats; filter.format.full_html granted to untrusted roles in config Not a finding when: Plain-text fields rendered as React children are escaped. `processed` from a restricted format is the intended path. Content from trusted admins with full_html is a policy decision, so mention it as low severity.

**Sources:** https://react.dev/reference/react-dom/components/common · https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html · https://top10.owasp.org/2025/A05_2025-Injection/ · https://next-drupal.org/docs/pages

### NSEC-23 · Unescaped data in inline <script> (JSON-LD, next/script inline, beforeInteractive)

**Severity:** medium · **Area:** security · **Taxonomy:** A05:2025, CWE-79 · **Applies to:** All versions; GHSA-gx5p-jg67-6x7h (beforeInteractive with untrusted input, both routers) fixed in 15.5.18 / 16.2.6 in the May 2026 release

**Signals:** <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}> without .replace(/</g, '\\u003c'); <Script id=... dangerouslySetInnerHTML> or template literals that interpolate CMS, params or searchParams values; strategy="beforeInteractive" with dynamic content; window.__CONFIG__ = ${JSON.stringify(x)} in _document.

**Why:** JSON.stringify does not escape </script>, so a product name or title from a CMS can break out and run script. The Next docs call this out explicitly for JSON-LD.

**Fix:** JSON.stringify(jsonLd).replace(/</g, '\\u003c'), or use serialize-javascript. Keep user data out of inline executable scripts. Pass it through data attributes or props instead.

**Not a finding when:** Fully static objects with no external data. JSON rendered through React text children (not inside a <script>).

**Sources:** https://nextjs.org/docs/app/guides/json-ld · https://vercel.com/changelog/next-js-may-2026-security-release

### NSEC-24 · User-controlled URLs in href/src/action (javascript:, data:) and client-side navigation sinks

**Severity:** low · **Area:** security · **Taxonomy:** A05:2025, CWE-79, CWE-601 · **Applies to:** React 18 (dev-only warning, no blocking): Next 14 apps and older. React 19 (Next 15 and 16) blocks javascript: URLs in React-rendered href, src, action, formAction and object data, but not imperative sinks (window.open, location.assign, location.href) or non-React-managed HTML.

**Signals:** <a href={user.website}>, <Link href={profile.url}>, <iframe src={embedUrl}>, <object data=...>, formAction={url}, window.open(param), location.assign(param), location.href = param where the value comes from users or a CMS link field without a scheme check. Report the JSX attribute cases only when package.json shows React 18 or when the URL also feeds an imperative sink or raw HTML.

**Why:** javascript: URLs execute script when clicked. React 19 neutralizes them in JSX attributes, but React 18 apps only get a console warning, and imperative navigation sinks are not covered by React at all. data: URLs are mostly blocked by browsers for top-level navigation, so the practical risk is javascript: and phishing to attacker http(s) pages.

**Fix:** Parse with new URL() and allow only http:, https: and mailto: (plus relative paths). Render the link as plain text otherwise.

**Not a finding when:** Links built from constants or internal routes. CMS link fields that the backend already validates to http(s) (Drupal link field with external/internal allowed only; check the field settings). On React 19 a JSX <a href={userUrl}> is already neutralized for javascript:, so do not report it as high.

**Sources:** https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html · https://github.com/facebook/react/pull/15047

### NSEC-25 · CSP missing or ineffective (unsafe-inline/unsafe-eval in production, broken nonce setup) and key security headers removed

**Severity:** medium · **Area:** security · **Taxonomy:** A02:2025, CWE-693, CWE-1021 · **Applies to:** All versions; nonce CSP requires dynamic rendering (not compatible with static/ISR/PPR shells); experimental SRI for App Router since v14.0.0; GHSA-ffhc-5mcf-pf4q (XSS in App Router with CSP nonces) fixed in 15.5.18 / 16.2.6

**Signals:** The headers() array in next.config or a Content-Security-Policy set in proxy.ts with script-src 'unsafe-inline' or 'unsafe-eval' not guarded by isDev. A nonce from Math.random(), a module-level constant, or reused across requests. The CSP set only on the response and not on the request headers (Next extracts the nonce from the request CSP). A nonce CSP on pages that are still statically rendered. The proxy matcher excluding pages that need the CSP. Removal of frame-ancestors / X-Frame-Options, X-Content-Type-Options, Referrer-Policy, or Strict-Transport-Security. A new third-party <Script> without a nonce under a nonce policy.

**Why:** Without a working CSP, any XSS from NSEC-22, NSEC-23 or NSEC-24 becomes full script execution. A broken nonce setup gives false confidence or pushes teams to add unsafe-inline later.

**Fix:** Follow the Next CSP guide: a per-request nonce with crypto.randomUUID in proxy, set on both the request and the response, 'strict-dynamic', object-src 'none', base-uri 'self', frame-ancestors 'none', and pages forced dynamic with await connection(). For static sites, use a header CSP in next.config with experimental.sri.

**Not a finding when:** 'unsafe-eval' guarded by NODE_ENV === 'development' is expected. style-src 'unsafe-inline' is common and low risk. CSP and headers are often set at the CDN, Nginx or Vercel level (vercel.json) instead. Check before flagging 'missing'. Only flag what the diff weakens or newly introduces. A missing CSP in a diff that never touches headers is at most a low note.

**Sources:** https://nextjs.org/docs/app/guides/content-security-policy · https://nextjs.org/docs/app/api-reference/config/next-config-js/headers · https://vercel.com/changelog/next-js-may-2026-security-release

### NSEC-26 · CORS misconfiguration in Route Handlers, pages/api or proxy

**Severity:** high · **Area:** security · **Taxonomy:** A02:2025, API8:2023, CWE-942 · **Applies to:** All versions

**Signals:** Reflecting request.headers.get('origin') back as Access-Control-Allow-Origin without an allowlist, especially with 'Access-Control-Allow-Credentials': 'true'. Origin checks with includes('example.com') or endsWith('example.com') (matches evilexample.com). The cors() package with origin: true or a function returning true. 'null' allowed as an origin. A global CORS header in next.config headers() for source '/(.*)' on cookie-authenticated routes. Lower severity: 'Access-Control-Allow-Origin': '*' together with 'Access-Control-Allow-Credentials': 'true' is an invalid combination that browsers reject, so it is a broken config, not an exploitable one.

**Why:** Credentialed CORS to arbitrary reflected origins lets any site read authenticated API responses. The browser's same-origin protection is gone for those endpoints.

**Fix:** An exact-match allowlist (array.includes(origin)) as in the proxy CORS example. Set Allow-Credentials only for allowlisted origins. Add Vary: Origin.

**Not a finding when:** A public, unauthenticated, read-only API (no cookies, no Authorization) with '*' is fine. Same-origin apps need no CORS headers at all. A wildcard '*' without credentials cannot be used to read cookie-authenticated responses.

**Sources:** https://nextjs.org/docs/app/api-reference/file-conventions/proxy · https://nextjs.org/docs/app/api-reference/file-conventions/route · https://api-security.owasp.org/editions/2023/en/0x11-t10

### NSEC-27 · CSRF: cookie-authenticated Route Handler or API Route mutates state (including via GET), or serverActions.allowedOrigins is too broad

**Severity:** medium · **Area:** security · **Taxonomy:** A01:2025 (CWE-352) · **Applies to:** Route Handlers and pages/api (no built-in CSRF check). Server Actions compare Origin with Host or X-Forwarded-Host; GHSA-mq59-m269-xvcx (Origin: null treated as missing, moderate) affects only next 16.0.1 up to 16.1.6 and is fixed in 16.1.7. serverActions config lives under experimental in the 16.3 docs.

**Signals:** export async function GET(...) that deletes, updates, logs out, sends email or toggles state. A pages/api handler without an if (req.method !== 'POST') guard. Cookie-auth POST/PUT/DELETE route handlers with no Origin or CSRF token check. experimental.serverActions.allowedOrigins containing '**', a bare '*', 'null', or broad third-party domains (per docs '*' matches exactly one host label and '**' one or more labels, only at the start). Session cookies with sameSite: 'none'.

**Why:** Server Actions have an Origin/Host check (and only accept POST), but Route Handlers and API Routes do not. GET mutations can be triggered by <img> or prefetch. SameSite=Lax still allows top-level GET navigations. Note that the docs say a request with no Origin header at all is allowed through with a warning.

**Fix:** Mutate only on POST/PUT/DELETE. Check Origin against an allowlist in cookie-authenticated handlers, or use CSRF tokens. Keep allowedOrigins to exact proxy hostnames. Never allow 'null'.

**Not a finding when:** Endpoints authenticated with an Authorization bearer header (not cookies) are not CSRF-prone. Draft-mode enable via GET is an accepted CMS contract (the docs explain it), but exit should use POST. Webhooks use signatures instead. allowedOrigins entries like 'my-proxy.com' or '*.my-proxy.com' are the documented pattern, not a finding.

**Sources:** https://nextjs.org/docs/app/guides/data-security · https://nextjs.org/docs/app/api-reference/config/next-config-js/serverActions · https://github.com/vercel/next.js/security/advisories/GHSA-mq59-m269-xvcx · https://top10.owasp.org/2025/A01_2025-Broken_Access_Control/

### NSEC-28 · Session or token cookies set without httpOnly / secure / sameSite / expiry, or tokens kept in localStorage

**Severity:** medium · **Area:** security · **Taxonomy:** A07:2025, CWE-1004, CWE-614, CWE-922 · **Applies to:** All versions (cookies() API is async in Next 15+)

**Signals:** (await cookies()).set('session'|'token'|'jwt'|'access_token', value) or response.cookies.set(...) or res.setHeader('Set-Cookie', ...) without httpOnly: true, secure: true, sameSite: 'lax'|'strict', expires or maxAge. sameSite: 'none' without secure. document.cookie = or js-cookie Cookies.set for auth tokens. localStorage.setItem('token', ...). Cookies set from Client Components.

**Why:** Tokens readable by JS turn any XSS into account takeover. Missing Secure leaks them over HTTP. Missing expiry creates long-lived sessions.

**Fix:** Set cookies on the server with { httpOnly: true, secure: true, sameSite: 'lax', path: '/', expires } as in the Next auth guide. Keep the session payload minimal, with no PII.

**Not a finding when:** Non-sensitive preference cookies (theme, locale, consent, A/B bucket) may be readable by JS. Auth libraries (Auth.js, iron-session, Clerk) set proper flags by default. Flag only explicit overrides. secure: process.env.NODE_ENV === 'production' is acceptable. The backend-for-frontend callback example intentionally uses a session cookie (expires: undefined), which is fine.

**Sources:** https://nextjs.org/docs/app/guides/authentication · https://nextjs.org/docs/app/api-reference/functions/cookies

### NSEC-31 · No rate limiting or size limits on expensive or abusable public actions and endpoints

**Severity:** low · **Area:** security · **Taxonomy:** API4:2023, API6:2023, A06:2025, CWE-770, CWE-307 · **Applies to:** Server Actions, Route Handlers, pages/api (all versions)

**Signals:** Public login, signup, password reset, OTP/2FA verify, contact/newsletter forms, email or SMS sending, LLM/AI calls, PDF generation, search or export actions and handlers with no rate-limit call (checkRateLimit, @upstash/ratelimit, arcjet). serverActions.bodySizeLimit raised to many MB (default is 1MB). pages/api config { api: { bodyParser: { sizeLimit: '50mb' }, responseLimit: false } }. formData.get('file') without a size or type check. Pagination take/limit from the query without a max.

**Why:** These flows are brute-forced or scripted (credential stuffing, SMS pumping, LLM cost abuse), and costs grow with traffic. Next.js itself has shipped several DoS advisories on Server Actions, so application-level limits matter.

**Fix:** Rate limit per IP and per account on sensitive flows. Cap the body size and page size (Math.min(limit, 100)). Validate uploads and send them directly to storage from the browser.

**Not a finding when:** Rate limiting may live at the edge (Vercel Firewall, Cloudflare, WAF rules) or in the backend API. Ask for or check the config before calling it missing. Internal or admin-only endpoints are lower priority. Absence of a call is weak evidence in a diff: report as a question or low unless the flow is clearly public and abusable (login, OTP, SMS, LLM).

**Sources:** https://nextjs.org/docs/app/guides/backend-for-frontend · https://nextjs.org/docs/app/api-reference/config/next-config-js/serverActions · https://api-security.owasp.org/editions/2023/en/0x11-t10

### NSEC-32 · Auth.js / NextAuth misconfiguration: tokens in session, unchecked redirect callback, dangerous account linking, vulnerable versions

**Severity:** high · **Area:** security · **Taxonomy:** A07:2025, A01:2025, A03:2025, CWE-200, CWE-601 · **Applies to:** next-auth v4, Auth.js v5 (next-auth@5 beta), @auth/core. Fixed versions: GHSA-x445-f3h2-j279 (CVE-2026-73419, OAuth provider confusion, moderate) and GHSA-7rqj-j65f-68wh (CVE-2026-73420, email normalizer homoglyph, CVSS 9.1) both fixed in @auth/core 0.41.3, next-auth 4.24.15, next-auth 5.0.0-beta.32. GHSA-5jpx-9hw9-2fx4 (email misdelivery via nodemailer parser) fixed in next-auth 4.24.12 and 5.0.0-beta.30.

**Signals:** callbacks.session copying token.accessToken, refreshToken, account.access_token, the whole token or DB user into session (exposed through /api/auth/session and useSession). callbacks.redirect returning url without an origin check. allowDangerousEmailAccountLinking: true. A signIn callback returning true without checking provider or email_verified. A jwt callback copying fields from the client-supplied `session` argument on trigger === 'update' (role, id). A hardcoded secret, debug: true in production, trustHost: true on self-host without a trusted proxy. The authorized callback as the only gate (see NSEC-13). next-auth below 4.24.15 / 5.0.0-beta.32 or @auth/core below 0.41.3, especially with the Email/magic-link provider or several OAuth providers with account linking.

**Why:** The session object is delivered to the browser, so tokens placed there are exposed. Misused redirect and linking settings allow open redirects and account takeover through a provider that does not verify emails. The 2026 advisories add sign-in link misdelivery (email provider) and cross-provider account linking.

**Fix:** Keep provider tokens in the JWT or DB and read them server-side only. Expose only id, name and role in the session. Restrict redirect to the same origin (url.startsWith(baseUrl)). Avoid dangerous linking unless every provider verifies emails. Validate update() payloads. Upgrade to next-auth 4.24.15 / 5.0.0-beta.32 or @auth/core 0.41.3 or newer.

**Not a finding when:** Adding user.id or role to the session is normal and documented. Access tokens are sometimes intentionally sent to the client for direct browser-to-API calls. If so, ask for short expiry and scoped tokens instead of blocking. Projects using only the Credentials provider are not exposed to the email and OAuth advisories.

**Sources:** https://authjs.dev/guides/extending-the-session · https://github.com/nextauthjs/next-auth/security · https://github.com/advisories/GHSA-x445-f3h2-j279 · https://github.com/advisories/GHSA-7rqj-j65f-68wh · https://github.com/advisories/GHSA-5jpx-9hw9-2fx4 · https://nextjs.org/docs/app/guides/authentication

### NSEC-33 · Error details, stack traces or upstream errors returned to the client

**Severity:** medium · **Area:** security · **Taxonomy:** A10:2025 (CWE-209), A09:2025, API8:2023 · **Applies to:** Route Handlers, pages/api, Server Actions returning errors; Server Component errors are sanitized in production (generic message plus digest)

**Signals:** catch (e) { return Response.json({ error: e.message, stack: e.stack }) }, res.status(500).json(err), return { error: String(error) } or { error: e } from a Server Action, JSON.stringify(error), Prisma or DB error objects or upstream response bodies passed straight through, error.tsx rendering error.message for Client Component errors. Logging of tokens, cookies or full request bodies (console.log(request.headers)).

**Why:** DB errors show table and column names, internal hosts and query shapes that help injection and reconnaissance. Returned values bypass Next's production error sanitization.

**Fix:** Log the full error server-side with a correlation ID and return a generic message plus that ID. Model expected errors as explicit safe messages (validation field errors).

**Not a finding when:** Errors thrown in Server Components reach error.tsx as a generic message plus digest in production, so rendering error.message there is fine for server errors. Intentional validation messages (zod fieldErrors, 'Email already used' where enumeration is acceptable) are fine. Dev-only branches guarded by NODE_ENV are fine. Note the Next docs' own route handler example returns reason.message; it is a docs simplification, and the same page says to avoid exposing sensitive information.

**Sources:** https://top10.owasp.org/2025/A10_2025-Mishandling_of_Exceptional_Conditions/ · https://nextjs.org/docs/app/api-reference/file-conventions/error · https://nextjs.org/docs/app/guides/backend-for-frontend

### NSEC-34 · Per-user or private data written to a shared cache (unstable_cache, use cache, CDN) and served to other users

**Severity:** high · **Area:** cache · **Taxonomy:** A01:2025, CWE-524, CWE-200 · **Applies to:** App Router unstable_cache (14 and 15, replaced by 'use cache' in 16), 'use cache' / 'use cache: remote' / cacheComponents (16), Pages Router gSSP Cache-Control, Route Handlers

**Signals:** unstable_cache(async () => query(userId), ['static-key']) where userId is captured from a closure and not passed as an argument or added to keyParts (the docs say closures must be added to keyParts): this is the main real cross-user leak. Also: res.setHeader('Cache-Control', 'public, s-maxage=...') or a CDN rule in gSSP or a route handler of a personalized page. 'use cache: remote' or plain 'use cache' functions that take a token, email or password as argument or cacheTag value (stored in plain text in the key and tags). An exported 'use cache' function that accepts userId (see NSEC-04). Lower severity: fetch(url, { headers: { Authorization | Cookie }, cache: 'force-cache' } is keyed on URL, method, headers and body, so it does not mix users, but it stores per-user data in the shared cache.

**Why:** A shared cache entry filled for user A is served to user B when the key does not contain the user identity, which is a data leak that grows with traffic and is hard to notice in testing. The July 2026 advisories also showed cache confusion in the framework itself for fetch calls with bodies (CVE-2026-64647, CVE-2026-64648).

**Fix:** Resolve the user outside the cached function and pass only the stable user ID as an argument (part of the cache key). Use 'use cache: private' for data that must stay in the browser. Mark personalized SSR responses private, no-store. Never key or tag on secrets.

**Not a finding when:** Cached functions that take the user ID as an argument, or resolve it in the exported wrapper and pass it to an unexported cached function (the documented pattern), are fine. Plain 'use cache' includes arguments and captured variables in the key, and cannot read cookies() or headers() (it throws), so a cross-user leak from it needs a token or ID smuggled in some other way. Public content with no per-user fields is fine. Draft mode already bypasses caches. The cache performance pack covers cache efficiency; this item is only about cross-user exposure. Do not flag `dynamic = 'force-static'` on a handler that reads the session as a leak: force-static returns empty cookies and headers, so it breaks auth rather than leaking another user's data.

**Also covers DEC-17 (User-specific or authenticated Drupal responses stored in shared Next caches).** Signals: unstable_cache(async () => fetch(..., { headers: { Authorization: token } }), [key]) where token or userId comes from a closure and is not in keyParts (closure values are not part of the unstable_cache key); 'use cache' function whose token comes from a module-level variable or shared store instead of an argument; export const fetchCache = 'force-cache' or 'default-cache' in a layout that also renders account data; a page or route with revalidate/ISR whose data is fetched with a per-user or privileged token; Next 14 code with no cache option fetching /jsonapi/user or webform submissions outside a dynamic route; getServerSideProps res.setHeader('Cache-Control','public, s-maxage=...') on pages with session data; fetch(new Request(url, init), otherInit) with a body on a version below the fix (CVE-2026-64648) Not a finding when: force-cache fetch with a per-user Authorization or Cookie header is NOT a cross-user leak by itself: the fetch cache key includes URL, method, headers and body, so each token gets its own entry (it only costs memory). force-cache with the server's anonymous-level token (identical for all users) is shared public data and fine. cookies() and headers() throw inside 'use cache' and unstable_cache, so the risk needs the token to arrive by closure or module state. In Next 14, fetches after cookies() or headers() or in dynamic routes are not cached. Draft Mode skips caches. A 'use cache' function taking userId as an argument, or capturing it from the closure (captured values become key arguments), has a per-user key.

**Also covers NPERF-08 (Shared cache (unstable_cache, 'use cache', force-cache) keyed without the user, so one user's data is served to others).** Signals: unstable_cache(async () => ...userId/session..., ['static-key']) where the user id comes from a closure (typically read from cookies()/session just above) and is not in keyParts or the function arguments. A module-level cached function named getCurrentUser/getMyOrders. 'use cache' function or component whose per-user output depends on identity taken from a non-Next source: AsyncLocalStorage, a global or module variable, a third-party auth client that does not use next/headers, or a server-held token, and the user id is not an argument. `fetch(..., { cache: 'force-cache' })` sending an Authorization or cookie header for per-user data (separate entries per header, but private data now sits in the shared server cache). Not a finding when: 'use cache' functions cannot call cookies() or headers() (error next-request-in-use-cache, also through helpers), so a direct read inside is a build or runtime error, not a leak. With 'use cache', a variable captured from the outer scope is part of the key, so do not flag a user id that comes from a closure there. When the user id is a parameter or listed in keyParts, keys are correct. fetch force-cache keys include URL, method, headers and body. React.cache() is per request and safe. Still check whether storing private data server-side is acceptable for the project.

**Sources:** https://nextjs.org/docs/app/guides/authentication-with-cache-components · https://nextjs.org/docs/app/api-reference/functions/unstable_cache · https://nextjs.org/docs/app/api-reference/functions/fetch · https://nextjs.org/docs/pages/building-your-application/data-fetching/get-server-side-props · https://nextjs.org/blog/july-2026-security-release · https://nextjs.org/docs/app/api-reference/directives/use-cache · https://nextjs.org/docs/app/guides/upgrading/version-15 · https://github.com/advisories/GHSA-68g3-v927-f742 · https://nextjs.org/docs/app/api-reference/directives/use-cache-private · https://top10.owasp.org/2025

### NSEC-35 · Weak randomness or hashing for tokens, sessions and passwords

**Severity:** high · **Area:** security

**Check:** Cryptographic failures (A04:2025 has no dedicated item): Math.random() or Date.now() for reset tokens, session IDs, invite codes or OTPs; md5/sha1/unsalted sha256 for passwords instead of argon2/bcrypt/scrypt; hardcoded or short JWT/session secrets; crypto.createCipheriv with a static IV. Source: https://top10.owasp.org/2025/A04_2025-Cryptographic_Failures/

### NSEC-36 · JWT decoded but not verified before an auth decision

**Severity:** high · **Area:** security

**Check:** Tokens decoded but not verified in proxy, route handlers or actions: jose decodeJwt() or jwt.decode() used for auth decisions instead of jwtVerify()/verify(), missing algorithms allowlist, cookie value trusted without signature. Frequent in hand-rolled proxy.ts auth. Source: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html (language-independent guidance) and the verified jwtVerify example in https://nextjs.org/docs/app/guides/authentication

### NSEC-37 · postMessage without origin checks

**Severity:** medium · **Area:** security

**Check:** Client-side window.postMessage listeners without an event.origin check, and postMessage(data, '*') with sensitive data, in 'use client' components (embedded widgets, OAuth popups, iframe previews). Source: https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html

### NSEC-38 · User uploads stored or served unsafely from the app origin

**Severity:** high · **Area:** security

**Check:** File uploads served back from your own origin: trusting client Content-Type or extension, user filenames used in paths, SVG or HTML uploads served inline from the app domain (stored XSS), no size cap. Partly touched by NSEC-05 and NSEC-31 but no dedicated check. Source: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
