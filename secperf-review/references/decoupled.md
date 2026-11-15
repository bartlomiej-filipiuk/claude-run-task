# Decoupled Drupal + Next.js seam

JSON:API / GraphQL / next-drupal. Items carry their area; skip areas excluded by --only.

Each item: severity is the default; `severity.md` escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read.

### DEC-01 · JSON:API write mode enabled or mutable routes left open

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, API5:2023 · **Applies to:** Drupal 10/11 core JSON:API (read_only default TRUE; sites upgraded from old installs may still hold read_only: false in active config)

**Signals:** config/sync/jsonapi.settings.yml with 'read_only: false'; drush cset jsonapi.settings read_only; Next code calling drupal.createResource/updateResource/deleteResource or fetch(..., {method:'POST'|'PATCH'|'DELETE'}) to /jsonapi; new create/edit permissions on the role used by the API consumer

**Why:** Turning off read-only mode opens POST, PATCH and DELETE on every exposed resource type. Only entity create, update and delete access then stands in the way, so one loose permission becomes a write path for API clients.

**Fix:** Keep read_only: true unless writes are needed. If they are, remove the mutable routes for all bundles except the ones you need, using a route subscriber or jsonapi_extras disabled resources. Give the writing consumer a role that has only 'create X content' for that bundle, and do the write server-side from a Route Handler or Server Action.

**Not a finding when:** Writes can be intended, for example a webform or comment bundle whose mutable routes are removed for all other bundles and whose writer role is minimal. Check the route subscriber and jsonapi_extras config in the same repo before you flag. Dev-only config splits (config/split/dev) with read_only false are fine.

**Also check:** Web service write exposure in config: jsonapi.settings `read_only: false` and rest.resource.*.yml enabling POST/PATCH/DELETE with cookie authentication, or new REST resources with weak permission mapping. JSON:API is read-only by default, and SA-CORE-2026-005 needed write access. Source: https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/security-considerations

**Sources:** https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/security-considerations · https://api-security.owasp.org/editions/2023/en/0x11-t10/

### DEC-02 · Anonymous or API-consumer role gets permissions that expose unpublished content, revisions or users over JSON:API

**Severity:** critical · **Area:** security · **Taxonomy:** A01:2025, API1:2023 · **Applies to:** Drupal 10/11 with JSON:API, GraphQL or custom REST

**Signals:** config/sync/user.role.anonymous.yml or user.role.authenticated.yml, or the role used by an OAuth consumer or scope (simple_oauth.oauth2_scope.*.yml), gaining 'bypass node access', 'view any unpublished content', 'view all revisions', 'view latest version', 'access user profiles', 'view unpublished paragraphs', 'administer *', 'issue subrequests'

**Why:** JSON:API applies ordinary entity access, so any permission on these roles is also API access. 'bypass node access' on anonymous makes every draft listable at /jsonapi/node/*. 'access user profiles' lets anyone list /jsonapi/user/user and harvest usernames.

**Fix:** Anonymous should have only 'access content' plus what the public site renders. Put preview powers on a separate role that only a server-side preview consumer has.

**Not a finding when:** A permission added to an editor role, or to a preview-only role whose consumer credentials live only server-side and are used only in draft mode (see DEC-03), is fine. 'view own unpublished content' on authenticated is normal. Check which role the file belongs to and which consumer or scope maps to it.

**Sources:** https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/security-considerations · https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/filtering · https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/

### DEC-03 · Privileged preview credentials used for public, cached rendering

**Severity:** critical · **Area:** security · **Taxonomy:** A01:2025, API1:2023 · **Applies to:** next-drupal 1.x (DrupalClient) and 2.x (NextDrupal, NextDrupalPages) or any Drupal client; App and Pages Router; Next 14-16

**Signals:** new NextDrupal(baseUrl, { auth: { clientId, clientSecret }, withAuth: true }) or new NextDrupalPages(...) or new DrupalClient(...) in a shared lib/drupal.ts; withAuth: true (constructor default or per call) on getResource, getResourceCollection, getResourceByPath, getMenu or translatePath in page.tsx, generateStaticParams, getStaticProps or layout without a draftMode()/context.draftMode branch; a fetch wrapper that always adds 'Authorization: Bearer'; a consumer whose role has 'Bypass content access control' (the next-drupal tutorial default)

**Why:** The next-drupal preview tutorial gives the consumer 'Bypass content access control' (plus 'View all revisions', 'View user information', 'Issue subrequests'). Public pages fetched with that token can include unpublished nodes, unpublished referenced entities from include=... and draft revisions. ISR or the full route cache then serves them to every visitor.

**Fix:** Use two clients. The public client has no auth, or a consumer whose role has anonymous-level permissions. The preview client is created and used only when (await draftMode()).isEnabled is true, or context.draftMode in the Pages Router. Also add filter[status]=1 to public collections as a second layer.

**Not a finding when:** Flag nothing if the authenticated consumer's role has only 'access content', for example when auth exists only to get past an obscured /jsonapi prefix or a rate limit. Read the scope and role config first. Having auth configured on the client is not enough: next-drupal only sends the header when withAuth is true (constructor default is false) or passed per call. Calls inside an isEnabled branch are fine. Draft Mode already skips all Next caches.

**Sources:** https://next-drupal.org/learn/draft-mode/create-oauth-client · https://next-drupal.org/docs/authentication · https://nextjs.org/docs/app/guides/draft-mode · https://raw.githubusercontent.com/chapter-three/next-drupal/main/packages/next-drupal/src/next-drupal-base.ts

### DEC-05 · New entity types or fields automatically exposed through JSON:API

**Severity:** low · **Area:** security · **Taxonomy:** A01:2025, API3:2023 · **Applies to:** Drupal 10/11 JSON:API, jsonapi_extras

**Signals:** new field.storage.*.yml or field.field.*.yml with internal-sounding names (notes, internal, phone, email, cost, secret); new content entity types; jsonapi_extras.jsonapi_resource_config.*.yml setting disabled: false for user--user, webform_submission, contact_message, path_alias, consumer, file--file; no hook_entity_field_access for new sensitive fields

**Why:** JSON:API exposes every entity type and field the requester can view, and field view access is allow by default. A field added for editors can show up in public API responses without anyone noticing (excessive data exposure).

**Fix:** Disable resource types and fields the frontend does not need in jsonapi_extras. Deny view on internal fields with hook_entity_field_access. Test with an anonymous GET to /jsonapi/{type}/{bundle}.

**Not a finding when:** The field may be public by design and rendered on the site. The resource may already be disabled in jsonapi_extras config elsewhere in the repo. The entity type's own access handler may already deny anonymous view (webform_submission, contact_message). Check those before flagging.

**Sources:** https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/security-considerations · https://www.drupal.org/project/jsonapi_extras · https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/

### DEC-08 · simple_oauth keys, consumer user, scopes or version are unsafe

**Severity:** high · **Area:** security · **Taxonomy:** A02:2025, A07:2025, API2:2023 · **Applies to:** simple_oauth 5.2.x and 6.x on Drupal 10/11 (global token lifetime settings only in 5.x and 6.0; deprecated in 6.1 where lifetime is per consumer)

**Signals:** simple_oauth.settings.yml public_key/private_key pointing inside the docroot (web/, sites/default/files); *.key or *.pem files committed; composer.lock simple_oauth 6.0.0-6.0.6 (SA-CONTRIB-2025-114, CVE-2025-12466); oauth2_scope config with granularity role pointing at administrator or a role with bypass; install or update hook creating a Consumer with 'secret' => 'secret', user_id 1, or confidential FALSE for a client_credentials client; very large access_token_expiration (simple_oauth.settings in 5.x/6.0, or the consumer's own expiration field in 6.1+); $settings['simple_oauth.key_permissions_check'] = FALSE in a prod settings file

**Why:** A readable private key lets anyone forge tokens. A client_credentials consumer tied to uid 1 or an admin role makes one leaked secret a full takeover. 6.0.0-6.0.6 let a token holder bypass _role route checks (the user must already have the role). Long-lived access tokens make any leak last longer.

**Fix:** Keep keys outside the docroot with 600 permissions and out of git. Use a dedicated low-permission user and role per consumer, confidential clients with random secrets injected from env, short access-token lifetimes (default about 300 s), and simple_oauth 6.0.7 or later (6.0.9 or 6.1.x current).

**Not a finding when:** A relative path like ../keys that resolves outside web/ is fine. Turning off the key permission check in container or dev settings is documented as a false-positive workaround. Long refresh-token lifetimes are normal. Consumers are content entities, so their secrets usually do not appear in config/sync.

**Sources:** https://www.drupal.org/project/simple_oauth · https://www.drupal.org/sa-contrib-2025-114 · https://git.drupalcode.org/project/simple_oauth/-/blob/6.0.x/README.md · https://git.drupalcode.org/project/simple_oauth/-/raw/6.1.x/config/schema/simple_oauth.schema.yml

### DEC-09 · Draft or preview entry route with a weak secret check or open redirect

**Severity:** medium · **Area:** security · **Taxonomy:** A01:2025, A07:2025, CWE-601 · **Applies to:** Next 14-16 draftMode (App Router) and draftMode/setPreviewData (Pages Router)

**Signals:** app/api/draft/route.ts, app/api/preview/*, pages/api/preview.ts; draftMode().enable(), res.setDraftMode() or res.setPreviewData() with no secret check; redirect(searchParams.get('slug')) or res.redirect(req.query.slug); secret compared with ==, or skipped when absent; NEXT_PUBLIC_*PREVIEW*; exit route called from <Link href="/api/disable-draft">

**Why:** Without a secret, anyone can turn on Draft Mode, which skips every Next cache and sends all their requests to Drupal (easy load amplification). It exposes drafts when draft fetches use preview credentials. Redirecting to a raw slug is an open redirect on your domain.

**Fix:** Use next-drupal enableDraftMode(request, drupal) unchanged. It validates the request with Drupal via validateDraftUrl and redirects to the validated path. In a hand-written route, check the secret, look the slug up in the CMS and redirect to the stored path. Exit with POST or a Server Action (or a <form method=GET>), because Link prefetch clears the cookie.

**Not a finding when:** The next-drupal enableDraftMode/disableDraftMode helpers used as-is. A route that looks up the entity by slug before redirecting. A route reachable only on an internal preview host behind auth.

**Also covers NSEC-29 (Draft mode / preview endpoint with a weak secret, no slug verification, or an open redirect).** Signals: app/api/draft/route.ts or pages/api/preview.ts calling draftMode().enable() / setPreviewData with no secret check or a hardcoded secret string; process.env.NEXT_PUBLIC_PREVIEW_SECRET; redirect(searchParams.get('slug')) or res.redirect(req.query.slug) without looking the slug up; the secret passed on to client pages; exit draft via a <Link> GET (it gets prefetched). Not a finding when: Library helpers that validate server-side (next-drupal draft helpers that validate the secret against Drupal, Sanity/Contentful preview SDK validators) are fine. Read the helper, not just the route. Local-only dev routes behind NODE_ENV checks.

**Sources:** https://nextjs.org/docs/app/guides/draft-mode · https://next-drupal.org/docs/draft-mode · https://raw.githubusercontent.com/chapter-three/next-drupal/main/packages/next-drupal/src/draft.ts · https://nextjs.org/docs/app/api-reference/functions/draft-mode

### DEC-10 · On-demand revalidation endpoint missing or bypassable secret check

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, API4:2023, API5:2023 · **Applies to:** Next 14-16 revalidateTag/revalidatePath (App) and res.revalidate (Pages); Drupal next module revalidators

**Signals:** app/api/revalidate/route.ts or pages/api/revalidate.ts calling revalidateTag, revalidatePath or res.revalidate; missing searchParams.get('secret') check; checks like if (secret && secret !== env) that pass when the param is absent; env var that can be empty (''==='' passes with ?secret=); handler returning (error as Error).message; path or tags taken raw from the query; next module debug enabled on prod (logs the revalidate URL including ?secret=)

**Why:** Anyone who can call it can flush caches in a loop. Every visitor then triggers a regeneration against Drupal (resource exhaustion), and with revalidatePath('/', 'layout') the whole site is invalidated. The Drupal next module sends the secret as a query string over GET, so it ends up in logs.

**Fix:** Fail closed when the env secret is unset or empty. Compare in constant time (crypto.timingSafeEqual). Accept only the tag and path formats you use (for example /^[a-z_]+(:[\w.-]+)?$/). Return generic errors. Keep next module debug logging off in prod and keep access logs private.

**Not a finding when:** The next-drupal template check `if (secret !== process.env.DRUPAL_REVALIDATE_SECRET) return 401` is sound when the env var is set to a non-empty value. The endpoint may also be protected at the network layer (Vercel deployment protection, IP allowlist). Accepting both GET and POST is needed for the Drupal next module.

**Also covers NSEC-30 (On-demand revalidation or webhook endpoints without a secret or signature check).** Signals: revalidateTag(tag), revalidatePath(path) or res.revalidate(path) inside a handler with no token check, or with a tag/path taken straight from the request with no allowlist. Stripe, Svix or GitHub webhook handlers that parse JSON without constructEvent or verify() on the raw body. A secret compared with == from a query string that shows up in logs. Not a finding when: revalidate* called inside an authenticated Server Action (NSEC-01 satisfied) is fine. Secrets in query strings are a documented pattern for CMS webhooks (the backend-for-frontend guide uses ?token=). Report that as low, not a blocker.

**Also check:** Unauthenticated on-demand revalidation endpoints: a route handler or webhook that calls revalidateTag/revalidatePath with a tag or path taken from the query string or body and no secret or signature check (the official example does exactly this). Anyone can purge the cache and cause a revalidation storm. Diff signals: revalidateTag(/revalidatePath( in app/api/**/route.ts or pages/api/** with searchParams.get('tag'|'path') and no comparison to a secret. Source: https://nextjs.org/docs/app/api-reference/functions/revalidateTag (example) and https://top10.owasp.org/2025

**Sources:** https://next-drupal.org/docs/on-demand-revalidation · https://github.com/chapter-three/next-drupal/blob/main/modules/next/src/Entity/NextSite.php · https://nextjs.org/docs/pages/guides/incremental-static-regeneration · https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/ · https://nextjs.org/docs/app/guides/backend-for-frontend · https://top10.owasp.org/2025/A08_2025-Software_or_Data_Integrity_Failures/

### DEC-11 · CORS in services.yml allows any origin together with credentials

**Severity:** medium · **Area:** security · **Taxonomy:** A02:2025, API8:2023, CWE-942 · **Applies to:** Drupal 10/11 (cors.config via asm89/stack-cors ^2.3)

**Signals:** sites/*/services.yml or *.services.yml cors.config: enabled: true with allowedOrigins: ['*'] or allowedOriginsPatterns: ['.*'] and supportsCredentials: true; session cookie_samesite changed to None together with wildcard CORS; Next Route Handlers echoing request Origin into Access-Control-Allow-Origin with Allow-Credentials: true

**Why:** With '*' and supportsCredentials: true, stack-cors echoes the caller's Origin (and adds Vary: Origin) rather than sending '*', so browsers accept it. A page on any origin that can make the browser send Drupal credentials can then read authenticated responses and make state-changing calls.

**Fix:** List the exact frontend origins. Set supportsCredentials: true only if the browser really sends Drupal cookies. Server-side Next fetches do not need CORS, so for SSR/ISR-only builds leave cors.config disabled.

**Not a finding when:** Drupal's scaffold default.services.yml already lists allowedOrigins: ['*'] with enabled: false and supportsCredentials: false, so a copied default block is not a finding; only enabled: true plus supportsCredentials: true is. Drupal's session cookie is SameSite=Lax by default (cookie_samesite: Lax in the scaffold), so a cross-site page does not get cookies sent; exploitability needs same-site origins (sibling subdomains), SameSite=None, or ambient credentials other than Bearer tokens, so lower the severity when none of those apply. allowedOrigins: ['*'] with supportsCredentials: false on a read-only public API is acceptable. development.services.yml or a local override is not prod. A single explicit origin with credentials is fine.

**Also check:** CORS misconfiguration in services.yml: `cors.config: enabled: true` with `allowedOrigins: ['*']` (the shipped default value) or reflecting origins together with `supportsCredentials: true`. Source: https://www.drupal.org/node/2715637

**Also check:** Drupal session cookie SameSite changes (session.storage.options cookie_samesite: None) or CSRF handling for cookie-authenticated decoupled calls (X-CSRF-Token from /session/token on write requests); these interact with DEC-11 and preview iframes. https://git.drupalcode.org/project/drupal/-/raw/11.x/core/assets/scaffold/files/default.services.yml

**Sources:** https://www.drupal.org/node/2715637 · https://raw.githubusercontent.com/asm89/stack-cors/master/src/CorsService.php · https://git.drupalcode.org/project/drupal/-/raw/11.x/core/assets/scaffold/files/default.services.yml · https://api-security.owasp.org/editions/2023/en/0xa8-security-misconfiguration/

### DEC-15 · GraphQL server without depth or complexity limits, with introspection or debug on in prod

**Severity:** low · **Area:** security · **Taxonomy:** A02:2025, API4:2023, API8:2023 · **Applies to:** Drupal graphql 4.x (graphql_compose schemas included)

**Signals:** config/sync/graphql.graphql_servers.*.yml with disable_introspection: false, query_depth: null or 0, query_complexity: null or 0, debug_flag other than 0, batching: true with no limits; new public endpoint path

**Why:** Nested entity references (node, author, content, author and so on) let one anonymous query do thousands of entity loads. Debug flags return internal errors and traces. Introspection shows the whole schema, including fields meant only for preview.

**Fix:** Set query_depth (for example 8 to 10) and query_complexity, disable introspection in prod (config split), keep debug_flag 0 in prod, and use persisted queries for the frontend.

**Not a finding when:** Dev or staging config splits. An endpoint reachable only with server-side OAuth where the frontend queries are fixed persisted queries.

**Sources:** https://www.drupal.org/project/graphql · https://git.drupalcode.org/project/graphql/-/blob/8.x-4.x/config/schema/graphql.schema.yml · https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/

### DEC-18 · Custom Drupal authentication provider without a page cache request policy

**Severity:** high · **Area:** cache · **Taxonomy:** A01:2025, A07:2025 · **Applies to:** Drupal 10/11 with page_cache enabled

**Signals:** *.services.yml tag { name: authentication_provider } for a new API-key, JWT or custom-header provider with no companion service tagged page_cache_request_policy; routes with options: _auth: [custom_provider]

**Why:** The Internal Page Cache runs before authentication and keys only on URL. The first authenticated response through a custom header auth is cached and served to anonymous callers, and access is effectively cached too. simple_oauth and basic_auth ship their own policies. Custom providers must add one.

**Fix:** Add a RequestPolicyInterface class that returns DENY when your auth header is present, and tag it page_cache_request_policy, as DisallowSimpleOauthRequests does.

**Not a finding when:** simple_oauth, basic_auth or cookie-session auth: core and contrib already handle these. Sites with page_cache uninstalled (check core.extension.yml). Providers used only on POST routes.

**Sources:** https://www.drupal.org/project/drupal/issues/3076065 · https://git.drupalcode.org/project/simple_oauth/-/blob/6.0.x/simple_oauth.services.yml · https://www.drupal.org/docs/administering-a-drupal-site/internal-page-cache

### DEC-20 · Varnish or CDN in front of the Drupal API caches private responses or serves stale data to Next revalidation

**Severity:** medium · **Area:** cache · **Taxonomy:** A01:2025 · **Applies to:** Drupal behind Varnish, Fastly or Cloudflare with purge; Next ISR or on-demand revalidation

**Signals:** VCL changes that unset req.http.Authorization or Cookie before lookup, or remove the builtin pass on Authorization; hash_data without Authorization for /jsonapi; CDN rules 'cache everything' on /jsonapi or /graphql; system.performance cache.page.max_age raised; revalidate webhook fired from Drupal hook_entity_update while purge is queued (purge_queuer, late_runtime_processor) and Next fetches through the CDN host

**Why:** The builtin VCL passes requests that carry Authorization. Custom VCL that strips or ignores it caches private JSON:API output for everyone. The Drupal next module webhook fires at entity save while the purge queue runs later, so Next may regenerate from a stale CDN copy and keep it until the next revalidation.

**Fix:** Keep pass on Authorization for API paths. Point Next server fetches at an origin host that skips the CDN, or trigger Next revalidation after the purge has run (purge processor or queue order). Keep a sane Drupal max-age.

**Not a finding when:** Caching anonymous GET /jsonapi at the edge is fine when purge by cache tag is set up. A server fetch URL (DRUPAL_BASE_URL) that already points at an internal origin avoids the race. Check which host Next uses.

**Also check:** CDN or reverse-proxy caching of App Router routes without partitioning by the RSC request headers and the _rsc parameter, or with Vary ignored or query strings stripped (root cause of CVE-2026-44576/44582 exposure; also missing CDN purge after revalidateTag). Diff signals: nginx/Varnish/Cloudflare/Fastly/Terraform config with 'cache everything', ignore-query-string, or Vary removal in front of a Next app. Sources: https://nextjs.org/docs/app/guides/cdn-caching and https://github.com/vercel/next.js/security/advisories/GHSA-wfc6-r584-vfw7

**Sources:** https://github.com/varnishcache/varnish-cache/blob/master/bin/varnishd/builtin.vcl · https://www.drupal.org/docs/administering-a-drupal-site/internal-page-cache · https://github.com/chapter-three/next-drupal/blob/main/modules/next/src/Plugin/Next/Revalidator/CacheTag.php

### DEC-23 · No revalidation for menus, taxonomy, media, blocks, aliases or unpublish

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal next module (revalidation only for bundles with next_entity_type_config); Next ISR

**Signals:** new Next usage of getMenu, taxonomy terms, media or block_content without a matching next.next_entity_type_config.<type>.<bundle>.yml; fetches of menus or footers with next: { revalidate: false } or no tags; Path revalidator only (entity URL) while listing pages or referencing pages embed the entity; path alias changes (old URL never revalidated); unpublish or delete of content shown in listings

**Why:** The next module only dispatches revalidation for entity bundles configured in next_entity_type_config. Menu link, term, media or block changes, and pages that embed the entity, stay stale indefinitely.

**Fix:** Add next_entity_type_config for menu_link_content, taxonomy_term, media and block_content bundles with the CacheTag plugin and fitting additional_tags (for example config:system.menu.main). Tag the matching Next fetches. Keep a TTL fallback for layout data.

**Not a finding when:** Layout data with a short revalidate time (for example 300) is an acceptable trade-off. Custom revalidator plugins or hook_entity_update code in the diff may already cover these types.

**Sources:** https://github.com/chapter-three/next-drupal/blob/main/modules/next/src/NextEntityTypeManager.php · https://next-drupal.org/docs/revalidator

### DEC-24 · Self-hosted multi-instance Next without a shared cache handler

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Next 14.1+ self-hosted (Docker, Kubernetes, several PM2 instances)

**Signals:** the diff adds or raises replicas above 1 in a Dockerfile, helm or k8s manifest, or enables PM2 cluster mode, for the Next app; next.config in the same repo has no cacheHandler or cacheHandlers; the revalidate webhook points at a load-balanced URL

**Why:** The default file-system cache is per instance, and on-demand revalidation only invalidates the instance that received the webhook. Other pods keep serving old Drupal content, and users see different versions depending on which pod answers.

**Fix:** Configure a shared cacheHandler (Redis or similar) or cacheHandlers for 'use cache', or fan the webhook out to all instances.

**Not a finding when:** Vercel and managed platforms share the cache. A single replica. Using only time-based revalidation is not broken, but pods will still disagree during the TTL.

**Sources:** https://nextjs.org/docs/app/guides/incremental-static-regeneration · https://nextjs.org/docs/app/guides/self-hosting · https://nextjs.org/docs/app/api-reference/config/next-config-js/incrementalCacheHandlerPath

### DEC-25 · Language not part of the cache key or of the revalidation

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Multilingual Drupal 10/11 JSON:API or GraphQL; Next i18n (Pages i18n config or App Router [lang] segment)

**Signals:** language negotiation config (language.types.yml, language.negotiation.yml) switched to session, Accept-Language or user preference for API routes; fetches to /jsonapi without the /{langcode}/ prefix or next-drupal locale/defaultLocale options; Path revalidator paths without a language prefix; custom endpoints reading \Drupal::languageManager()->getCurrentLanguage() while anonymous page cache is on; 'use cache' functions reading locale from headers() instead of an argument

**Why:** Drupal JSON:API picks the language through negotiation. The Internal Page Cache keys only on URL, so header- or session-based negotiation serves the first requester's language to everyone. Path-based revalidation that only hits the default-language path leaves translations stale.

**Fix:** Use URL-prefix negotiation for API calls (/de/jsonapi/...), pass locale to every next-drupal call, include the language in Next paths and cache keys, and prefer tag revalidation (node:NID covers all translations).

**Not a finding when:** Monolingual sites. Tag-based revalidation already covers every translation because Drupal entity cache tags are language-neutral. The JSON:API Multilingual contrib module (jsonapi_multilingual) chooses the language with a ?langCode= query parameter, which is part of the URL key. Core JSON:API has no language fallback candidates, so missing translations behave per site negotiation config.

**Sources:** https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/translations · https://www.drupal.org/docs/administering-a-drupal-site/internal-page-cache · https://github.com/chapter-three/next-drupal/blob/main/modules/next/src/Plugin/Next/Revalidator/Path.php

### DEC-26 · Drupal outage turned into a cached 404, empty page or fallback content

**Severity:** medium · **Area:** cache · **Taxonomy:** A10:2025 · **Applies to:** Next 14-16 ISR (App Router pages with revalidate or tags; Pages Router getStaticProps). Pages Router notFound: true is documented to replace a good page; App Router notFound() during regeneration is not documented (treat as likely, unverified)

**Signals:** try { await drupal.getResource... } catch { return { notFound: true } } or catch { notFound() }; catch returning { props: { node: null } } or default content with revalidate; if (!res.ok) return [] in data helpers; fetches to Drupal with no timeout (no AbortSignal.timeout) in generateStaticParams or pages; error.tsx masking fetch errors in cached segments

**Why:** When a background regeneration throws, Next keeps serving the last good page and retries on the next request (documented). When the code instead returns empty props, default content or a value that renders a fallback, that result replaces the good page. In the Pages Router, notFound: true returns 404 even if a page was generated before. A short Drupal outage becomes hours of 404s or blank pages cached for every visitor.

**Fix:** Throw on 5xx, network errors and timeouts so ISR keeps the last good page. Return notFound only for a real 404, for example when translatePath returns null. Add AbortSignal.timeout(...) to Drupal fetches.

**Not a finding when:** next-drupal translatePath returns null only for a 404 and throws on other errors, so `if (!path) notFound()` is correct. Returning notFound on a genuine JSON:API 404 or 403 for deleted or unpublished content is intended. For the App Router notFound() case, state the behavior as unverified in the finding rather than asserting it.

**Sources:** https://nextjs.org/docs/pages/guides/incremental-static-regeneration · https://nextjs.org/docs/pages/api-reference/functions/get-static-props · https://nextjs.org/docs/app/guides/incremental-static-regeneration · https://top10.owasp.org/2025/A10_2025-Mishandling_of_Exceptional_Conditions/

### DEC-27 · Private Drupal files or access-controlled media served through the Next image optimizer or a custom image proxy

**Severity:** high · **Area:** cache · **Taxonomy:** A01:2025, CWE-524 · **Applies to:** Next 14-16 next/image; CVE-2025-57752 (images returned by Next API routes that vary on Cookie or Authorization) affects 14.0-14.2.30 and 15.0.0-15.4.4, fixed in 14.2.31 and 15.4.5

**Signals:** next/image src pointing at /system/files/..., private:// derived URLs or protected media; Route Handler that fetches Drupal files with the user's cookie or token and is used as an Image src; custom loader forwarding Authorization; remotePatterns pathname '/system/files/**'

**Why:** The default image optimizer does not forward headers when fetching a remote src, so private images fail or tempt developers into a proxy. Optimized variants are cached by URL, width and quality, not by user. Before 14.2.31 and 15.4.5, API-route images that varied by Cookie or Authorization were served to other users (cache key confusion).

**Fix:** Serve private files with a plain <img> or a streaming Route Handler with Cache-Control: private, no-store and an access check, and set unoptimized on those Images. Keep public images on public:// image styles. Upgrade Next.

**Not a finding when:** Public files (/sites/default/files/...) through next/image are the normal case. A proxy that is public by design, for example serving signed URLs that do not depend on the user, is fine. The CVE only matters when the Image src is a Next API route or Route Handler, not a direct Drupal URL.

**Sources:** https://github.com/advisories/GHSA-g5qg-72qw-gw5v · https://nextjs.org/docs/app/api-reference/components/image

### DEC-29 · JSON:API over-fetching: deep or wide includes and no sparse fieldsets

**Severity:** medium · **Area:** performance · **Taxonomy:** API4:2023 · **Applies to:** Drupal JSON:API with next-drupal or drupal-jsonapi-params

**Signals:** include= with more than 2 levels (field_sections.field_items.field_media.field_media_image) or many relationships; include=uid,revision_uid,node_type; no fields[...] or addFields() for list and teaser queries; getResourceCollection used for cards that render only title, path and image; page[limit]=50 on menus or cards that show 5

**Why:** Each include triggers entity loads, access checks and normalization. Response size and time to first byte grow with content depth and data volume. The JSON:API docs warn that includes can make responses large and slow.

**Fix:** Add fields[node--article]=title,path,field_image and fields[file--file]=uri,url, include only what is rendered, keep includes shallow, and paginate lists to what is shown.

**Not a finding when:** Detail pages that really render deep paragraphs may need nested includes. Check whether sparse fieldsets trim each type. A one-off build-time script is lower priority.

**Sources:** https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/includes · https://jsonapi.org/format/#fetching-sparse-fieldsets · https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/fetching-resources-get

### DEC-35 · New OAuth token requested for every Drupal API call

**Severity:** low · **Area:** performance · **Taxonomy:** - · **Applies to:** Custom Drupal clients in Next 14-16 (next-drupal caches the token itself)

**Signals:** fetch(`${DRUPAL}/oauth/token`, { method: 'POST', body: 'grant_type=client_credentials...' }) inside per-request data helpers; getAccessToken() called without reuse; NextDrupal instantiated inside a component or request handler instead of at module scope

**Why:** Each page render adds a token round trip with RSA signing and writes a row to the simple_oauth token table. Latency doubles and the token table grows until cron purges it.

**Fix:** Create the client once at module scope (next-drupal reuses the token until it expires), or cache the token server-side until expires_in minus a margin.

**Not a finding when:** Per-user tokens exchanged at login are expected. Serverless cold starts will fetch a token once per instance, which is fine.

**Sources:** https://next-drupal.org/docs/authentication · https://git.drupalcode.org/project/simple_oauth/-/blob/6.0.x/README.md
