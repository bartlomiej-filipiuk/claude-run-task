# Next.js performance and cache

Next.js 14-16. Defaults differ per version; check `applies_to` against the version in the review header.

Each item: severity is the default; `severity.md` escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read.

### NPERF-01 · Request-time API read in a root or shared layout makes every child route dynamic or blocking

**Severity:** high · **Area:** performance · **Taxonomy:** - · **Applies to:** App Router, Next 14 to 16 (previous model: route becomes fully dynamic; Cache Components: blocking-route error unless inside Suspense)

**Signals:** cookies(), headers(), draftMode(), connection() or an auth helper that wraps them (auth(), getSession(), getServerSession()) added to app/layout.tsx, app/(group)/layout.tsx or a component rendered by a layout (header, nav, footer). Under Cache Components also: `await params` destructured at the top of a layout for a dynamic segment not covered by generateStaticParams, or a runtime read inside generateMetadata/generateViewport. Layouts do not receive searchParams, so an `await searchParams` signal only applies to pages.

**Why:** In the previous model, one request-time read in a layout opts every route under it out of the Full Route Cache. All pages then render on every request, and server load grows with traffic. Under Cache Components, a layout that reads runtime data blocks navigation and loading.js cannot cover it.

**Bad:**
```
// app/layout.tsx
export default async function RootLayout({ children }) {
  const session = await auth() // reads cookies()
  return <html><body><Header user={session?.user} />{children}</body></html>
}
```

**Fix:** Read request data in the smallest leaf component that needs it, wrapped in <Suspense>. Pass the params promise down and await it deeper (params.then(...) inside Suspense). Keep root layouts free of request-time APIs, and move auth redirects into the page or proxy.

**Not a finding when:** Fine when every route under that layout is per-user anyway (for example app/(dashboard)/layout.tsx behind login) and the build output already shows them as dynamic. Fine under Cache Components if the read sits in a child wrapped in <Suspense>. Reading cookies in proxy.ts does not make pages dynamic. A Pages Router _app has no such effect. The docs describe params as runtime data only under Cache Components; do not flag `await params` in a layout in the previous model.

**Sources:** https://nextjs.org/docs/app/getting-started/caching · https://nextjs.org/docs/app/getting-started/fetching-data · https://nextjs.org/docs/14/app/building-your-application/caching

### NPERF-02 · Uncached fetch or noStore/connection() in a shared data helper opts many routes out of caching

**Severity:** high · **Area:** cache · **Taxonomy:** - · **Applies to:** App Router, Next 14 and 15, and 16 without Cache Components; under Cache Components it becomes a dynamic hole that needs Suspense

**Signals:** In lib/, services/, api-client files or components used by many routes: `cache: 'no-store'`, `next: { revalidate: 0 }`, `unstable_noStore()`, `await connection()`. Also a new shared CMS/GraphQL client that sets no-store for every call.

**Why:** A single uncached fetch in a helper imported by the header, footer or menu makes every route that renders it dynamic. It also hits the origin API on every request, so CMS or API load scales linearly with traffic.

**Bad:**
```
// lib/cms.ts
export const cms = (q) => fetch(CMS_URL, { method: 'POST', body: q, cache: 'no-store' })
```

**Fix:** Cache stable data: `fetch(url, { next: { revalidate: 3600, tags: ['menu'] } })` or 'use cache' + cacheLife('hours') + cacheTag('menu'). Keep no-store only in the one component that needs real-time data, behind Suspense.

**Not a finding when:** Fine for data that must be fresh per request (cart, stock, balances, preview/draft). Fine in Route Handlers or Server Actions, which are not prerendered. In Next 15 and later a fetch with no options is not no-store: it still runs once at build if the route is otherwise static. Do not flag a missing option alone.

**Sources:** https://nextjs.org/docs/app/api-reference/functions/fetch · https://nextjs.org/docs/app/guides/caching-without-cache-components

### NPERF-03 · Route segment config forcing dynamic rendering spreads through layouts

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** App Router, Next 14 to 16 previous model. With cacheComponents: true, dynamic/revalidate/fetchCache/dynamicParams are removed and cause build errors

**Signals:** `export const dynamic = 'force-dynamic'`, `export const revalidate = 0`, `export const fetchCache = 'force-no-store'` or 'default-no-store', especially in layout.tsx. The same line copy-pasted into many page.tsx files to 'fix' a build error.

**Why:** force-dynamic skips the Full Route Cache and sets no-store on every fetch in that segment (Next 15 and later). In a layout it covers every child route. It usually hides a build or prerender error, and every page then costs a full render and origin fetches per request.

**Bad:**
```
// app/(site)/layout.tsx
export const dynamic = 'force-dynamic' // added to silence 'Dynamic server usage' build error
```

**Fix:** Fix the real cause instead: move request-time reads down, cache data with revalidate or tags, or use connection() only where per-request output is needed. Keep shared layouts at 'auto'. On Next 16, move to Cache Components with Suspense and 'use cache'.

**Not a finding when:** Justified on routes that are per-user or real-time by nature (dashboards, checkout, webhook route handlers, draft preview). A Route Handler that must never be cached is fine. revalidate = 0 on a leaf page with a comment explaining why is fine.

**Also covers DEC-28 (Public Drupal pages rendered dynamically on every request).** Signals: export const dynamic = 'force-dynamic', revalidate = 0 or cache: 'no-store' on content pages; cookies() or headers() read in the root layout (makes every route dynamic); getServerSideProps for plain content pages; Next 15+ plain fetch(drupalUrl) in a route that is dynamic for other reasons Not a finding when: Search results, account and personalised pages, and draft previews are meant to be dynamic. A short revalidate (60 s) is not dynamic. Next 15+ routes without dynamic APIs are still prerendered once at build even with a default fetch. Reading draftMode().isEnabled does not by itself make a route dynamic.

**Also check:** export const runtime = 'edge' on pages, layouts or route handlers that also rely on revalidate or ISR. The docs state the revalidate value is not available with the deprecated edge runtime, and runtime = 'edge' is deprecated in the 16 route segment config. Diff signals: runtime = 'edge' next to revalidate/generateStaticParams. Sources: https://nextjs.org/docs/app/guides/caching-without-cache-components#route-segment-config-revalidate and https://nextjs.org/docs/app/api-reference/file-conventions/route-segment-config

**Sources:** https://nextjs.org/docs/app/guides/caching-without-cache-components · https://nextjs.org/docs/app/api-reference/file-conventions/route-segment-config · https://nextjs.org/blog/next-15 · https://nextjs.org/docs/app/guides/upgrading/version-15 · https://nextjs.org/docs/app/api-reference/functions/fetch · https://nextjs.org/docs/app/guides/incremental-static-regeneration

### NPERF-05 · GET Route Handler cached when it should not be, or uncached when it should be, depending on version

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Next 14 (GET cached by default), Next 15 and 16 without Cache Components (not cached unless dynamic = 'force-static'), Next 16 with Cache Components (prerendered only if it does no network, DB or runtime work)

**Signals:** app/**/route.ts with `export async function GET()` that does not read `request`, cookies() or headers(). Next 14 projects returning DB/CMS data from such a handler. Next 15 and later handlers serving expensive, rarely-changing data with no `dynamic = 'force-static'`/revalidate or 'use cache' helper.

**Why:** On Next 14 the handler output is frozen at build or first request and served stale until redeploy or revalidation. On 15 and later without opt-in, an expensive GET that queries a DB or fetches runs on every request. Under Cache Components, a handler that does only deterministic work is prerendered by design; one that queries a DB or fetches is not prerendered and is not frozen.

**Bad:**
```
// Next 14: frozen at build time
export async function GET() {
  const rates = await getRatesFromDb()
  return Response.json(rates)
}
```

**Fix:** Choose explicitly. For fresh data read the request (or on 14 use `dynamic = 'force-dynamic'`). For cacheable data use `export const dynamic = 'force-static'` + `revalidate = N` (previous model), or a helper function with 'use cache' + cacheLife (16 with Cache Components; 'use cache' cannot sit directly in the handler body).

**Not a finding when:** Metadata routes (sitemap.ts, robots.ts, icon, opengraph-image) are meant to be static. POST/PUT/DELETE are never cached. A handler that reads request.url/searchParams/headers is dynamic in every version. Under Cache Components a DB query or network fetch stops prerendering, so the handler is not frozen unless it is wrapped in 'use cache'. Do not flag a handler on 15+ for being uncached unless the work is demonstrably expensive and the data rarely changes.

**Sources:** https://nextjs.org/blog/next-15 · https://nextjs.org/docs/app/getting-started/route-handlers · https://nextjs.org/docs/14/app/building-your-application/caching

### NPERF-06 · Data cached with no time-based or on-demand revalidation path

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** App and Pages Router, Next 14 to 16

**Signals:** `cache: 'force-cache'` with no `next.revalidate` and no `next.tags`. unstable_cache(fn, keys) with no options. getStaticProps returning props with no `revalidate` and no res.revalidate() webhook in the repo. `revalidate = false`. `cacheLife('max')` with no cacheTag. Only on Next 14: plain fetch() with no options (cached indefinitely).

**Why:** The entry stays until the next deploy (or, for the Data Cache and unstable_cache, across deploys too). Editors change content and the site keeps serving old data. Teams then work around it with force-dynamic, which swaps a correctness bug for a load problem.

**Bad:**
```
const menu = await fetch(`${CMS}/menu`, { cache: 'force-cache' }) // no revalidate, no tags
```

**Fix:** Attach a tag and wire a mutation or webhook to revalidateTag(tag, 'max') / updateTag(tag), or set a revalidate window that matches how often the content changes.

**Not a finding when:** Grep the repo for revalidateTag/revalidatePath/res.revalidate with the same tag or path before flagging, since on-demand invalidation may live in a webhook route. Content that is truly immutable (hashed assets, versioned API responses, legal text) is fine. A 'use cache' without cacheLife still revalidates every 15 min via the default profile, so it is not 'never'.

**Also check:** 'use cache' scope with no explicit cacheLife (implicit default profile: 15 min revalidate, never expires), or a short-lived cache nested inside an outer 'use cache' without cacheLife, which fails prerender. Diff signals: 'use cache' with no cacheLife( call in the same function; cacheLife('seconds') helper imported into another cached scope. Sources: https://nextjs.org/docs/app/api-reference/functions/cacheLife#nested-short-lived-caches and https://nextjs.org/docs/app/api-reference/directives/use-cache

**Sources:** https://nextjs.org/docs/app/api-reference/functions/fetch · https://nextjs.org/docs/app/api-reference/functions/unstable_cache · https://nextjs.org/docs/pages/guides/incremental-static-regeneration · https://nextjs.org/docs/app/api-reference/functions/cacheLife

### NPERF-07 · Revalidation window too short, or one short value dragging a whole route down

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** App Router, Next 14 to 16; Pages Router getStaticProps

**Signals:** `revalidate: 1`..`revalidate: 30`, `export const revalidate = 10`, `cacheLife('seconds')`, inline `cacheLife({ revalidate: 0 })` or `expire` under 300. A low revalidate on one fetch inside a shared layout component.

**Why:** The lowest revalidate across a route's layouts, pages and fetches sets the rate for the whole route. One 10-second fetch in the header re-renders every page every 10 s under traffic. Under Cache Components, expire under 5 min or revalidate 0 leaves the entry out of the static shell, so it becomes a request-time hole.

**Bad:**
```
// components/Header.tsx used by every layout
const promo = await fetch(PROMO_URL, { next: { revalidate: 5 } })
```

**Fix:** Match the window to the real change rate and prefer tag-based invalidation for editorial content. Keep short windows in a leaf component behind Suspense (for example 'use cache: remote' + cacheLife('seconds') inside Suspense).

**Not a finding when:** Genuinely live data (prices, scores, stock) with a comment is fine. A short window on a single leaf route with little traffic is low impact. Pages Router revalidate only affects that page.

**Sources:** https://nextjs.org/docs/app/guides/caching-without-cache-components · https://nextjs.org/docs/app/api-reference/functions/cacheLife · https://nextjs.org/docs/app/api-reference/functions/fetch

### NPERF-09 · Public/s-maxage Cache-Control set on personalized SSR pages, API routes or Route Handlers

**Severity:** critical · **Area:** security · **Taxonomy:** A01:2025 Broken Access Control; CWE-524; CWE-525 · **Applies to:** Pages Router getServerSideProps and API routes; App Router Route Handlers, proxy, next.config headers(); Next 14 to 16

**Signals:** `res.setHeader('Cache-Control', 'public, s-maxage=` in getServerSideProps or pages/api that also reads req.cookies, session or Authorization. `headers: { 'Cache-Control': 'public, max-age=...' }` in route.ts returning user data. next.config.js `headers()` with source '/:path*' setting public caching. Missing `Vary` for cookie-dependent responses.

**Why:** Next sets `private, no-cache, no-store` on dynamic pages to prevent this. Once code overrides it with public/s-maxage, a CDN or reverse proxy caches the first user's HTML or JSON and serves it to everyone, which leaks session-specific data. Since Next 15 custom Cache-Control values are no longer overridden by the framework, so the override takes effect.

**Bad:**
```
export async function getServerSideProps({ req, res }) {
  const user = await getUser(req)
  res.setHeader('Cache-Control', 'public, s-maxage=60, stale-while-revalidate=300')
  return { props: { user } }
}
```

**Fix:** Use `private, no-store` for personalized responses. Cache only anonymous variants. Split personalized parts into a client fetch or a separate uncached endpoint. When you must vary, cache by an explicit key the CDN understands, not by cookie.

**Not a finding when:** Fine when the handler provably returns the same output for every visitor: it reads no cookies, session or auth header, and the proxy/middleware does not rewrite by user. The SWR example in the gSSP docs is for anonymous pages. Static asset or image routes with public caching are fine.

**Sources:** https://nextjs.org/docs/pages/building-your-application/data-fetching/get-server-side-props · https://nextjs.org/docs/app/guides/self-hosting · https://nextjs.org/docs/app/guides/cdn-caching · https://top10.owasp.org/2025

### NPERF-10 · High-cardinality or unstable cache keys: near-zero hit rate and cache growth

**Severity:** low · **Area:** performance · **Taxonomy:** CWE-400 · **Applies to:** App Router, Next 14 to 16 ('use cache' 16; unstable_cache 14+)

**Signals:** 'use cache' functions or components taking whole objects (user, request-derived config, searchParams object, Date, full filter objects), raw query strings or session ids as arguments. unstable_cache keyParts containing Date.now(), Math.random() or JSON.stringify(largeObject). 'use cache' added to reduce runtime DB load on a serverless deployment.

**Why:** Every distinct serialized input creates a new entry. Keys built from timestamps, raw query strings or session ids never repeat, so the cache only adds serialization cost and fills memory (self-hosted in-memory LRU, capped by cacheMaxMemorySize) or remote storage. On serverless the default in-memory 'use cache' entries typically do not persist across requests.

**Bad:**
```
async function Results({ searchParams }: { searchParams: Record<string,string> }) {
  'use cache'
  return <List items={await search(searchParams)} /> // utm_*, fbclid, etc. all create new entries
}
```

**Fix:** Normalize arguments to the minimal primitives that change the output (id, locale, page number, sorted filters). Cache shared data separately from per-user data. For runtime caching on serverless, use 'use cache: remote' with a cache handler only where the hit rate justifies the roundtrip.

**Not a finding when:** Per-user keys are correct, not a smell, when the data really is per-user and reuse per user is expected. A small enum of filters or locales is fine. Build-time prerendering still benefits even when runtime reuse is low.

**Sources:** https://nextjs.org/docs/app/api-reference/directives/use-cache · https://nextjs.org/docs/app/getting-started/caching · https://nextjs.org/docs/app/api-reference/functions/unstable_cache

### NPERF-12 · Sequential awaits for independent data (request waterfall)

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** App Router Server Components, Route Handlers, Server Actions; Pages Router getServerSideProps/getStaticProps; Next 14 to 16

**Signals:** Two or more consecutive `const x = await fetchA(...)` / `await db...` lines where the second call does not use the first result. Awaiting in a layout before children can start. `for (const x of list) await ...` where the calls are independent.

**Why:** Latency adds up: three 200 ms calls become 600 ms TTFB per request, and every new data source added later makes it worse. Under load it also holds server workers longer.

**Bad:**
```
const { username } = await params
const artist = await getArtist(username)
const albums = await getAlbums(username) // does not depend on artist
```

**Fix:** Start the calls, then `await Promise.all([...])` (or Promise.allSettled when partial failure is acceptable). Split independent sections into separate async components under their own <Suspense>, or use the preload pattern (`void getItem(id)`).

**Not a finding when:** Not a problem when the second call needs the first result (getArtist, then getPlaylists(artist.id)). Calls that are both memoized or cached and fast are low impact. Queries on one DB connection may serialize anyway, so still parallelize but mark it low. Awaiting params first is fine.

**Sources:** https://nextjs.org/docs/app/getting-started/fetching-data

### NPERF-13 · Per-item fetch or query inside loops or map (N+1), or unbounded fan-out

**Severity:** high · **Area:** performance · **Taxonomy:** CWE-400 · **Applies to:** App and Pages Router server code, Next 14 to 16

**Signals:** `items.map(async (item) => await fetch(`/api/x/${item.id}`))`, `for (...) { await db.x.findUnique(...) }` in page, layout, generateStaticParams, getStaticProps or route.ts. `Promise.all(list.map(fetch))` over a list whose size comes from the DB or CMS. Each child component in a rendered list doing its own query by id.

**Why:** Request count grows with data size. A list of 20 becomes 20 calls today and 500 next year. Unbounded Promise.all over a growing list also hits upstream rate limits and exhausts connection pools.

**Bad:**
```
const posts = await getPosts()
const withAuthors = await Promise.all(posts.map(p => fetch(`${API}/users/${p.authorId}`).then(r => r.json())))
```

**Fix:** Use a batch endpoint or `WHERE id IN (...)`, include relations in the list query, or fetch once in the parent and pass data down. If fan-out cannot be avoided, cap concurrency and paginate.

**Not a finding when:** Identical GET fetches are memoized per render pass in Server Components, layouts, pages, generateStaticParams and generateMetadata, so many components asking for the same URL is not N+1. That memoization does NOT apply in Route Handlers (they are outside the React tree) and does not apply to non-fetch DB calls unless wrapped in React.cache. A small list with a fixed size (for example 3 featured items) is fine. Build-time-only loops in generateStaticParams with caching are lower severity.

**Also covers DEC-30 (N+1 Drupal API calls and request waterfalls from Next).** Signals: items.map(async i => drupal.getResource(...)) or for...of with await getResource per item; each card or paragraph component fetching its own referenced entity; sequential awaits of independent calls (menu, footer, node) in layout or page; translatePath then getResource per slug inside generateStaticParams loops Not a finding when: In the App Router, identical GET fetch calls in one render pass are memoized, so repeated getMenu('main') in several components is one request; memoization does not apply in Route Handlers, when an AbortController signal is passed, or in the Pages Router (getStaticProps). Calls that depend on the previous result, such as translatePath before getResource, are necessarily sequential.

**Sources:** https://nextjs.org/docs/app/getting-started/fetching-data · https://nextjs.org/docs/app/api-reference/functions/fetch · https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/filtering

### NPERF-14 · generateStaticParams / getStaticPaths prerendering every entity, or missing it so ISR never kicks in

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** App Router generateStaticParams (Next 14 to 16), Pages Router getStaticPaths

**Signals:** generateStaticParams returning `allProducts.map(...)` or getStaticPaths with `fallback: false` over all DB rows. A dynamic [slug] page with `revalidate` but no generateStaticParams (previous model). `return []` in a project with cacheComponents: true. `dynamicParams = false` added.

**Why:** Build time and deploy size grow with the catalogue. Thousands of pages rebuild on every deploy. In the previous model, a dynamic route needs generateStaticParams (even `[]`) or force-static to be ISR-cached at runtime; without it every request renders. Under Cache Components an empty array is a build error.

**Bad:**
```
export async function generateStaticParams() {
  const all = await db.product.findMany({ select: { slug: true } }) // 80k rows
  return all.map(p => ({ slug: p.slug }))
}
```

**Fix:** Prerender the top N (popular) paths and let the rest render on first visit: App Router with dynamicParams true (default) plus `return []` or a subset; Pages Router with `fallback: 'blocking'`. Under Cache Components, return at least one real param.

**Not a finding when:** A small, bounded set (docs, locales, <1k pages) is fine to prerender fully. Static export (output: 'export') must list all paths. dynamicParams = false is correct when unknown slugs should 404.

**Also covers DEC-31 (Fetching every node at build or request time).** Signals: while (links.next) loops pulling all pages of /jsonapi/node/*; generateStaticParams or getStaticPaths returning every node (getResourceCollectionPathSegments over all types) with fallback: false or dynamicParams = false; page[limit] set above 50 expecting more Not a finding when: Small sites with a bounded content count. Static export (output: 'export') needs all paths, so flag it only as a performance note there.

**Sources:** https://nextjs.org/docs/app/api-reference/functions/generate-static-params · https://nextjs.org/docs/pages/guides/incremental-static-regeneration · https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/pagination

### NPERF-15 · Pages Router getServerSideProps used for data that is the same for every visitor

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** Pages Router, Next 14 to 16

**Signals:** `export async function getServerSideProps(` or `export const getServerSideProps = async () =>` that does not use req, res, query, cookies or preview, or uses only `params`, and fetches CMS or catalogue data. New pages/* files choosing gSSP by default.

**Why:** gSSP renders on every request and on every client-side navigation (a JSON request per nav), so origin and CMS load scale with traffic. The docs recommend getStaticProps + ISR when data does not need to be fetched at request time.

**Bad:**
```
export async function getServerSideProps({ params }) {
  const page = await cms.getPage(params.slug)
  return { props: { page } }
}
```

**Fix:** `export async function getStaticProps({ params }) { ...; return { props, revalidate: 300 } }` with getStaticPaths `fallback: 'blocking'`, plus res.revalidate() from a CMS webhook for immediate updates.

**Not a finding when:** Needed when output depends on the request: auth or session, geolocation, A/B cookies, query-string search, draft preview, or redirects based on user. A gSSP that sets a correct public Cache-Control for anonymous data is an accepted alternative. Check that it reads no cookies first.

**Sources:** https://nextjs.org/docs/pages/building-your-application/data-fetching/get-server-side-props · https://nextjs.org/docs/pages/guides/incremental-static-regeneration

### NPERF-17 · Missing or misplaced Suspense: slow data blocks the whole page or navigation

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** App Router, Next 14 to 16 (Cache Components turns many of these into dev/build errors)

**Signals:** New async Server Component with slow fetch/DB rendered directly in page.tsx with no <Suspense>. An uncached fetch or cookies() in layout.tsx (loading.js in the same segment does not cover the layout). A single <Suspense> or loading.js wrapping the whole page when only one widget is slow.

**Why:** Without a boundary, TTFB equals the slowest query, and navigation hangs with no feedback. It gets worse as queries slow with data growth. Boundaries placed too high also throw away the static shell.

**Bad:**
```
export default async function Page() {
  const recs = await getRecommendations() // 1.5s
  return (<><Hero /><Recs data={recs} /></>)
}
```

**Fix:** Wrap each independently slow section in its own <Suspense fallback={<Skeleton/>}> close to the data access. Move layout-level uncached reads into the page or into a Suspense-wrapped child.

**Not a finding when:** Cached or prerendered data needs no boundary. Bots receive the fully rendered page anyway. Suspense around purely synchronous components does nothing but is harmless. Under Cache Components the dev overlay flags blocking routes, so a green build suggests the structure is valid.

**Sources:** https://nextjs.org/docs/app/getting-started/fetching-data · https://nextjs.org/docs/app/getting-started/caching

### NPERF-18 · 'use client' placed too high (layout, page, or provider wrapping the whole document)

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** App Router, Next 14 to 16

**Signals:** 'use client' as the first line of app/**/layout.tsx or page.tsx. A new 'use client' on a file that imports many components or heavy libs. A context provider that wraps <html> or renders the whole layout instead of `{children}`. Converting a Server Component to client only to use one hook.

**Why:** Everything a 'use client' file imports and renders directly goes into the client bundle. Marking a layout or page as client ships the whole subtree's JS, loses server data fetching, and bundle size grows with every component added below.

**Bad:**
```
// app/products/page.tsx
'use client'
import { useState } from 'react'
import ProductGrid from '@/components/ProductGrid' // now all client JS
```

**Fix:** Keep pages and layouts as Server Components and extract the interactive leaf (<Search/>, <LikeButton/>) into its own 'use client' file. Pass server content as children. Render providers as deep as possible, wrapping only {children}.

**Not a finding when:** Server Components passed as children or props to a client component stay server-rendered, so a provider that wraps {children} is fine. Small, genuinely interactive pages (a form wizard) are acceptable. Pages Router has no directive; everything is client there anyway.

**Sources:** https://nextjs.org/docs/app/getting-started/server-and-client-components

### NPERF-19 · Heavy libraries or barrel imports added to client components

**Severity:** low · **Area:** performance · **Taxonomy:** - · **Applies to:** App Router 'use client' files and all Pages Router components; Next 14 to 16

**Signals:** New imports in client code of moment, full `lodash` (import _ from 'lodash'), chart.js/echarts/highcharts, highlight.js/prismjs/shiki, marked/react-markdown/remark, xlsx, pdfjs, @mui/x-*, firebase, aws-sdk. `import { X } from '@/components'` (local index.ts barrel) in a client file. `import * as Icons from ...`.

**Why:** Client JS affects download, parse and hydration on every visit, and each dependency added compounds. Local barrels can pull the whole components folder, including other heavy client components, into a single route. Libraries that only turn data into markup (highlighting, markdown) do not need to run on the client at all.

**Bad:**
```
'use client'
import _ from 'lodash'
import Highlight from 'prism-react-renderer'
import { Button, Chart, Map } from '@/components' // index.ts re-exports everything
```

**Fix:** Move data-to-markup work to Server Components (for example shiki codeToHtml on the server). Lazy-load heavy interactive widgets with next/dynamic or import() on interaction. Import from direct paths. Add third-party multi-export packages to experimental.optimizePackageImports.

**Not a finding when:** Packages optimized by default do not need changes: lucide-react, date-fns, lodash-es, ramda, antd, react-bootstrap, @mui/material, @mui/icons-material, @heroicons/react/*, @headlessui/react, react-icons/*, recharts, rxjs, @tabler/icons-react, effect and others (see the optimizePackageImports list; the option itself is still labelled experimental). Imports in server-only files do not affect the client bundle. Check with `next experimental-analyze` (16.1+, Turbopack) or @next/bundle-analyzer before calling it high.

**Sources:** https://nextjs.org/docs/app/guides/package-bundling · https://nextjs.org/docs/app/api-reference/config/next-config-js/optimizePackageImports · https://nextjs.org/docs/app/guides/lazy-loading · https://nextjs.org/blog/next-16-1

### NPERF-21 · next/image without correct sizes, or with forced quality or unoptimized

**Severity:** low · **Area:** performance · **Taxonomy:** - · **Applies to:** App and Pages Router, Next 14 to 16 (images.qualities added 14.2.23; 16: qualities default [75], quality coerced to allowed values)

**Signals:** `<Image fill` or CSS-responsive images (className w-full, style width:100%) with no `sizes` prop. `unoptimized` on raster photos, or `images.unoptimized: true` added to next.config. `quality={100}`/`quality={90}` added on 16 without images.qualities config. A plain `<img src=` for CMS content images in JSX.

**Why:** Without sizes, the browser assumes 100vw and downloads the largest candidate, so a grid of cards pulls full-width images on mobile. Page weight grows with every image added to lists. unoptimized ships originals. On 16 a quality outside images.qualities is coerced to the closest allowed value (dev logs a warning), so the intent is not met.

**Bad:**
```
<div className="relative aspect-video"><Image src={card.img} fill alt={card.alt} /></div> // no sizes, in a 3-column grid
```

**Fix:** Set `sizes` to the rendered width per breakpoint, for example `sizes="(max-width: 768px) 100vw, 33vw"`. Keep default quality or add values to images.qualities. Use next/image for content images.

**Not a finding when:** Fixed-size images with explicit width and height (icons, avatars) do not need sizes. SVGs are automatically unoptimized. A Drupal or other image-style CDN URL may already be optimized via a custom loader. <img> inside emails or OG templates is fine. unoptimized is the documented choice for images that need authentication.

**Also covers NPERF-22 (LCP image not prioritized, or priority/preload spread across many images).** Signals: Hero or banner <Image> in the first viewport without priority (14/15) or preload / loading="eager" / fetchPriority="high" (16). `priority` or `preload` inside `.map()` over lists or carousels. New `priority` usage on a Next 16 project. Not a finding when: When several images could be the LCP depending on viewport, the docs advise against preload; fetchPriority is the right tool. Below-the-fold images should stay lazy. `priority` on 14 and 15 is correct, not deprecated.

**Sources:** https://nextjs.org/docs/app/api-reference/components/image · https://nextjs.org/blog/next-16

### NPERF-26 · proxy.ts/middleware.ts without a tight matcher, or doing slow I/O on every request

**Severity:** high · **Area:** performance · **Taxonomy:** - · **Applies to:** Next 14 and 15 middleware.ts (Edge; Node runtime stable in 15.5); Next 16 proxy.ts (Node runtime only; middleware.ts deprecated, Edge only)

**Signals:** middleware.ts or proxy.ts without `export const config = { matcher: ... }`, or matcher '/:path*'. `await fetch(`/DB/session lookups, JWT verification with remote JWKS fetch, or geolocation API calls inside the function. Matcher that does not exclude _next/static, _next/image, favicon.ico and public assets.

**Why:** Without a matcher, proxy runs on every request, including static files, image optimization and prefetches. Any network call there adds latency to every asset and multiplies with traffic and prefetching. It can also block CSS and JS when auth redirects hit asset paths.

**Bad:**
```
export async function middleware(req) {
  const res = await fetch(`${AUTH}/session`, { headers: { cookie: req.headers.get('cookie') ?? '' } })
  if (!res.ok) return NextResponse.redirect(new URL('/login', req.url))
} // no config.matcher
```

**Fix:** Add a negative-lookahead matcher, for example `'/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)'`, optionally with `missing` for prefetch headers. Do cheap cookie presence checks in proxy and real auth in the page or Server Action. Use event.waitUntil for logging.

**Not a finding when:** Proxy still runs for _next/data even when it is excluded; that is by design, not a bug. Lightweight synchronous logic (redirect maps, locale cookie) is fine broadly. Do not copy the docs' example matcher blindly when the proxy does authentication: it excludes `api`, which leaves API routes unprotected. Server Function calls are POSTs to the page route, so a matcher that excludes the path also skips them; auth must be checked inside each Server Function (security pack). Do not use module-level state in proxy; the docs say not to rely on shared modules or globals.

**Sources:** https://nextjs.org/docs/app/api-reference/file-conventions/proxy · https://nextjs.org/blog/next-16

### NPERF-27 · Module-level Map/object caches in server code that grow without bound (memory leak and cross-user data)

**Severity:** medium · **Area:** performance · **Taxonomy:** CWE-401; CWE-770; CWE-524 · **Applies to:** Server Components, Route Handlers, Server Actions, API routes, proxy; Next 14 to 16; worst on long-lived self-hosted Node

**Signals:** Module scope `const cache = new Map()`, `const memo = {}`, `let results = []` in server files, filled with `.set(key` where key comes from userId, URL, query or slug, with no max size, TTL or eviction. `globalThis.__cache ??= new Map()`. Arrays pushed to per request.

**Why:** Module scope lives as long as the Node process and is shared by all requests and users. Keys from request data grow without limit and memory climbs until OOM or restart. If the key omits the user, other users can read each other's values. On serverless it is also unreliable, since each instance has its own copy.

**Bad:**
```
// lib/pricing.ts
const priceCache = new Map<string, Price>()
export async function getPrice(userId: string, sku: string) {
  const k = `${userId}:${sku}`
  if (!priceCache.has(k)) priceCache.set(k, await fetchPrice(userId, sku))
  return priceCache.get(k)!
}
```

**Fix:** Use framework caches (fetch cache, unstable_cache, 'use cache' with a cache handler) or a bounded LRU (max entries and TTL) or Redis. Keep per-request state in React.cache or local variables.

**Not a finding when:** Singletons with fixed cardinality are fine: `globalThis.prisma ??= new PrismaClient()`, parsed config, a Map keyed by a small enum or locale list. An LRU with a max (lru-cache `max`) is fine. Client-side module caches live per tab and are a different concern. A Map that stores runtime Promises and is read from a 'use cache' scope is a separate build-hang problem described in the use cache troubleshooting section.

**Sources:** https://nextjs.org/docs/app/api-reference/file-conventions/proxy · https://nextjs.org/docs/app/guides/self-hosting · https://nextjs.org/docs/app/api-reference/directives/use-cache

### NPERF-28 · Revalidation storms: revalidatePath('/') or broad invalidation in frequent actions or webhooks

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** App Router, Next 14 to 16; Pages Router res.revalidate loops

**Signals:** `revalidatePath('/')`, `revalidatePath('/', 'layout')`, or `revalidatePath('/[locale]', 'layout')` in Server Actions or webhook route handlers. revalidateTag/res.revalidate called in a loop over many items per webhook. One catch-all tag ('all', 'cms') on every fetch, invalidated on any edit.

**Why:** revalidatePath('/', 'layout') purges the client cache and invalidates all cached data. Every page then re-renders and re-fetches on its next visit, which hits the origin with a burst of traffic. In Server Functions, revalidatePath currently also refreshes all previously visited pages on the next navigation. Invalidation cost grows with site size and edit frequency.

**Bad:**
```
'use server'
export async function likePost(id) {
  await db.like.create({ data: { postId: id } })
  revalidatePath('/', 'layout') // on every like
}
```

**Fix:** Invalidate narrowly with specific tags (`post-${id}`, 'posts-list') via revalidateTag(tag, 'max') for SWR, or a literal path. Debounce or batch webhook invalidations.

**Not a finding when:** Acceptable for rare global changes (site settings, menu, deploy-time hooks) on small sites. Revalidation is lazy (on next visit), not all at once. The storm is traffic-driven, so severity depends on traffic and edit rate.

**Also covers DEC-22 (Over-invalidation: every Drupal save purges the whole site).** Signals: revalidatePath('/', 'layout') or revalidatePath('/') in the revalidate handler or a Server Action; loops calling res.revalidate for all paths; broad tags (for example 'drupal' or 'all') attached to every fetch and sent on each save; next module Path revalidator 'additional_paths' listing '/' plus many pages Not a finding when: Small sites with few pages. A global purge triggered only by config or menu changes, which really touch every page through the layout. In Pages Router, the one res.revalidate per path the webhook sends is targeted, not global.

**Sources:** https://nextjs.org/docs/app/api-reference/functions/revalidatePath · https://nextjs.org/docs/app/api-reference/functions/revalidateTag · https://nextjs.org/docs/app/guides/incremental-static-regeneration

### NPERF-30 · On-demand invalidation that silently does nothing (tag or path mismatch, multi-instance)

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** App Router and Pages Router on-demand ISR, Next 14 to 16

**Signals:** revalidateTag('post-' + id) where the fetch or cacheTag uses a different format or casing. Tags built from long strings (>256 chars) or more than 128 tags per fetch. revalidatePath with the rewrite source instead of the destination route. res.revalidate('/rewritten-path'). Multiple replicas (Dockerfile/Helm/K8s replicas >1) with no cacheHandler/cacheHandlers in next.config.

**Why:** Tags are case-sensitive and over-length tags are never assigned, so revalidating them is a no-op. revalidatePath works on the route file path, not the browser URL. On multiple instances, revalidateTag only clears the local instance unless the cache handler coordinates tags. Editors see stale content and the team adds force-dynamic.

**Bad:**
```
fetch(url, { next: { tags: [`Post-${slug}`] } })
// webhook
revalidateTag(`post-${slug}`, 'max') // case mismatch, no-op
```

**Fix:** Centralize tag builders (`export const postTag = (id: string) => `post:${id}``) used by both cacheTag/fetch and the invalidation call. Revalidate destination paths. For multi-instance self-hosting, configure a shared cacheHandler/cacheHandlers with refreshTags.

**Not a finding when:** Vercel and other managed platforms coordinate the cache across instances. A single self-hosted instance with persistent disk is fine. revalidatePath('/blog/[slug]', 'page') with a pattern is valid when type is given. A CDN in front of Next keeps serving its own copy until s-maxage expires, so on-demand revalidation also needs a CDN purge.

**Also covers DEC-21 (Next cache tags do not match what Drupal sends on revalidation).** Signals: fetch or getResource with next: { tags: [...] } or tags: [...] using uuid (`node:${uuid}`), bundle names ('article'), or resource types ('node--article') while Drupal sends node:123 and node_list:article; listing pages (getResourceCollection, views) with no node_list:<bundle> tag; tags built from long strings over 256 chars or more than 128 tags; revalidateTag(tag) with one argument in Next 16 (deprecated); next_entity_type_config CacheTag plugin with entity_list_tag disabled Not a finding when: Path-based revalidation (the Path plugin) needs no tags. Short revalidate TTLs may be an intended fallback. The single-argument revalidateTag is deprecated in 16 (TypeScript error; it only runs if the error is suppressed and then behaves like expire: 0) and is the only form in 14-15, so flag it as low severity and only on Next 16 code. Note that 'max' serves stale content to the first visitor after an edit.

**Also covers NPERF-29 (Next 16 invalidation API misuse: single-argument revalidateTag, updateTag outside Server Actions).** Signals: `revalidateTag('x')` with one argument in a Next 16 project. `updateTag(` in route.ts, proxy or client code. `revalidateTag(tag, { expire: 0 })` in hot paths. revalidateTag in a Server Action where the user expects to see their own write immediately. Not a finding when: On Next 14 and 15 the one-argument revalidateTag is the only signature, so do not flag it there. Check package.json. `{ expire: 0 }` is legitimate for takedowns or legal removals.

**Also check:** Mutation without any invalidation: a Server Action or route handler that writes to the DB or CMS and calls none of revalidateTag/updateTag/revalidatePath/refresh/router.refresh, so cached pages stay stale and the team later adds force-dynamic. Diff signals: 'use server' function with db.*.create/update/delete and no revalidation call. Source: https://nextjs.org/docs/app/getting-started/revalidating

**Sources:** https://nextjs.org/docs/app/api-reference/functions/revalidateTag · https://nextjs.org/docs/app/api-reference/functions/revalidatePath · https://nextjs.org/docs/app/api-reference/functions/fetch · https://nextjs.org/docs/app/guides/self-hosting · https://nextjs.org/docs/app/guides/cdn-caching · https://github.com/chapter-three/next-drupal/blob/main/modules/next/src/Plugin/Next/Revalidator/CacheTag.php · https://next-drupal.org/docs/on-demand-revalidation · https://nextjs.org/blog/next-16 · https://nextjs.org/docs/app/api-reference/functions/updateTag

### NPERF-36 · dynamic = 'force-static' on a route that reads cookies, headers or search params (silently wrong content)

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** App Router previous model, Next 14 to 16 without Cache Components (removed under cacheComponents)

**Signals:** `export const dynamic = 'force-static'` in a page, layout or route.ts that also uses cookies(), headers(), useSearchParams(), or locale/geo/AB logic based on them.

**Why:** force-static forces cookies(), headers() and useSearchParams() to return empty values, so the route is prerendered once with defaults. Every user then gets the same logged-out, default-locale or unfiltered output, and the mismatch is easy to miss because the code reads correctly.

**Bad:**
```
export const dynamic = 'force-static'
export default async function Page() {
  const lang = (await cookies()).get('lang')?.value ?? 'en' // always 'en'
}
```

**Fix:** Remove request-dependent logic from the static route (move it to the client or a Suspense-wrapped dynamic part), or let the route be dynamic and cache the underlying data instead.

**Not a finding when:** force-static on a GET Route Handler or page that reads no request data is the documented way to opt into caching (Next 15+). Reading cookies only in a client component under that route is unaffected. Do not flag it on a Cache Components project, where the option no longer exists (that is a build-error finding under NPERF-03).

**Sources:** https://nextjs.org/docs/app/guides/caching-without-cache-components · https://nextjs.org/docs/app/getting-started/route-handlers

### NPERF-37 · process.env read in a statically prerendered route is frozen at build time

**Severity:** medium · **Area:** cache

**Check:** Environment variables read in a statically prerendered route are frozen at build time (a single Docker image promoted across environments then serves the wrong value). Diff signals: process.env.X (not NEXT_PUBLIC_) read in a page/layout/route with no connection(), cookies() or headers() call. Source: https://nextjs.org/docs/app/guides/self-hosting#environment-variables

### NPERF-38 · Server code fetching the app's own API route

**Severity:** low · **Area:** performance

**Check:** Server Component or getServerSideProps fetching the app's own API route (fetch('/api/...') or fetch(`${SITE_URL}/api/...`)) instead of calling the shared function directly. It adds a network hop, breaks at build time when the server is not running, and duplicates caching. Source: https://nextjs.org/docs/pages/building-your-application/data-fetching/get-server-side-props ('You do not have to call a Next.js API Route ... since the function runs on the server')
