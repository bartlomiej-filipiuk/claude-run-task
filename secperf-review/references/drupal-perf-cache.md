# Drupal performance and cache

Drupal 10/11. Code that degrades with data growth, and cache metadata that is wrong, missing, or disables a cache layer.

Each item: severity is the default; `severity.md` escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read.

### DPERF-01 · Render output uses an entity, config or other object without adding it as a cacheable dependency

**Severity:** high · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** A build(), preprocess, hook_*_view, formatter or controller that reads data from ->load(, ::load(, \Drupal::config(, $this->configFactory->get(, ->getParameter( (route), or entity field values, and then puts that data in a render array (#markup, #theme vars, #items) with no matching $renderer->addCacheableDependency($build, $obj), CacheableMetadata::createFromObject($obj)->applyTo($build), or '#cache' => ['tags' => $entity->getCacheTags()] / $config->getCacheTags().

**Why:** Once the render cache, Dynamic Page Cache or Varnish has stored the output, nothing invalidates it when the source entity or config changes. Editors then see stale content until a full cache clear, and the team learns to run drush cr as a workaround.

**Fix:** Add every object you read as a dependency. For example: $build = [...]; $cm = CacheableMetadata::createFromRenderArray($build); $cm->addCacheableDependency($node)->addCacheableDependency($config); $cm->applyTo($build); Or use $renderer->addCacheableDependency($build, $node).

**Not a finding when:** Data rendered through the entity view builder (->view($entity)) or a field formatter already carries the entity tags. A block plugin whose getCacheTags() already returns the tags is covered. Output with max-age 0 is not cached anyway. Admin forms (FormBase) are not render cached in the normal way. Check whether the object's tags are merged anywhere further up (parent build, getCacheTags() override) before flagging. Config read only to decide a redirect or log message does not reach the output.

**Sources:** https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays · https://www.drupal.org/docs/drupal-apis/cache-api/cache-tags · https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Cache%21CacheableMetadata.php/class/CacheableMetadata/11.x

### DPERF-02 · addCacheableDependency() called with an object that is not CacheableDependencyInterface (silently sets max-age 0, deprecated)

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x. Deprecation notice for CacheableMetadata::addCacheableDependency() from 11.2.0 (hard requirement in 12.0), for Renderer::addCacheableDependency() from 11.3.0 (type error in 13.0). On 10.x and earlier 11.x it is silent.

**Signals:** ->addCacheableDependency($x) or $renderer->addCacheableDependency($build, $x) where $x is an array, a string, a plain DTO, a Guzzle response, a stdClass from a DB query, a FieldItemList, a Url object (not the GeneratedUrl from toString(TRUE)), an AccountProxy from \Drupal::currentUser() / $this->currentUser (AccountInterface is not cacheable, load the User entity instead), or a custom service that does not implement CacheableDependencyInterface. Also CacheableMetadata::createFromObject($x) on those types.

**Why:** A non-cacheable object is treated as uncacheable and max-age 0 is set. The 0 bubbles up and makes the page skip Dynamic Page Cache (see DPERF-06). On 10.x nothing in the logs shows it, so the page just gets slower; on 11.2+ it shows up as a deprecation, and it will become a fatal error in Drupal 12/13.

**Fix:** Pass objects that implement CacheableDependencyInterface: entities (including the User entity, not the AccountProxy), config, AccessResult, CacheableMetadata, and GeneratedUrl from $url->toString(TRUE). For custom data, build a CacheableMetadata with explicit tags, contexts and max-age, or have the value object implement CacheableDependencyInterface or use RefinableCacheableDependencyTrait. For the current user add the 'user' or narrower context instead of a dependency.

**Not a finding when:** If the author wants the output uncacheable and it is inside a #lazy_builder (so it gets auto-placeholdered), max-age 0 is acceptable. Entities, config objects, AccessResultInterface, CacheableMetadata and GeneratedUrl are all fine. Check the declared type or class of the argument before flagging; if the type cannot be seen from the diff, say so instead of asserting.

**Sources:** https://www.drupal.org/node/3525389 · https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays · https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Cache%21CacheableMetadata.php/class/CacheableMetadata/11.x

### DPERF-03 · Output varies by request, user, role or route but declares no matching cache context (wrong or private content served)

**Severity:** high · **Area:** cache · **Taxonomy:** CWE-524 · **Applies to:** Drupal 10.x and 11.x

**Signals:** The build or preprocess code reads \Drupal::request()->query->get(, $request->query->, $this->requestStack->getCurrentRequest(, \Drupal::routeMatch(, $this->currentUser->id(), ->hasRole(, ->hasPermission(, ->getRoles(, language manager ->getCurrentLanguage(, $_GET, $_COOKIE, or a header, and has no '#cache' => ['contexts' => [...]] with url.query_args:NAME, route, user, user.roles, user.permissions, languages:*, cookies:NAME or headers:NAME. The same applies to a block plugin whose build() does this without a getCacheContexts() override. Also '#cache' => ['keys' => [...]] on an element whose content varies and that has no matching contexts.

**Why:** The first variation rendered gets cached and served to everyone. That can be a logged-in user's name, a role-only link, or filter results for a different query string. When personal or role-restricted data is involved, this is a data leak and not only a performance bug.

**Fix:** Declare the narrowest context that matches what you read, for example '#cache' => ['contexts' => ['url.query_args:type', 'user.roles']]. In block plugins use: return Cache::mergeContexts(parent::getCacheContexts(), ['route']);

**Not a finding when:** user.permissions, theme and languages:language_interface are required contexts that the renderer always adds (renderer.config), so they need not be declared. languages:language_content is NOT required. Code that runs only in admin forms, POST handlers or with max-age 0 is not cached. When the value reaches the page through a context-aware block plugin (ContextAwarePluginTrait adds contexts from the injected context), the context is already there. Reading the request only for a redirect or a log message is fine.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api/cache-contexts · https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays

### DPERF-04 · Access result returned without cacheability (access decision cached for the wrong user)

**Severity:** high · **Area:** cache · **Taxonomy:** CWE-524 · **Applies to:** Drupal 10.x and 11.x

**Signals:** In hook_entity_access, hook_ENTITY_TYPE_access, #[Hook('entity_access')], custom AccessInterface::access(), route _custom_access or BlockBase::blockAccess(): return AccessResult::allowed()/forbidden()/allowedIf($cond) where $cond depends on the user, a field value, the route or config, but the chain has no ->cachePerUser(), ->cachePerPermissions(), ->addCacheableDependency($entity) or ->addCacheContexts([...]). Compare with hand-rolled permission checks like $account->hasPermission() wrapped in allowedIf().

**Why:** Access results bubble into render cache and Dynamic Page Cache. A decision computed for one user or one entity state gets reused for others, so content is either hidden from people who should see it or shown to people who should not. It also stays wrong after the entity field that drove the decision changes.

**Fix:** return AccessResult::allowedIf($node->getOwnerId() == $account->id())->cachePerUser()->addCacheableDependency($node); For permission checks use AccessResult::allowedIfHasPermission($account, 'x'), which already adds user.permissions, or ->cachePerPermissions() when the check is hand-rolled.

**Not a finding when:** allowedIfHasPermission() and allowedIfHasPermissions() already add user.permissions. AccessResult::neutral() or a constant allowed() with no condition needs no metadata. For access checks used only on routes that are never cached (admin routes, POST-only endpoints), the risk is lower; report at low severity.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21entity.api.php/function/hook_entity_access/11.x · https://www.drupal.org/docs/drupal-apis/cache-api/cache-contexts

### DPERF-05 · Cache context explosion: url, url.query_args, user, session, cookies, headers or ip used where a narrower context would do

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** 'contexts' => ['url'], ['url.query_args'] (all args), ['user'], ['session'], ['cookies'], ['headers'], ['ip'], ['url.path'] on blocks that appear on every page. Also getCacheContexts() returning 'user' when only roles or permissions matter. The problem is worse inside a render array that also has '#cache' => ['keys' => ...].

**Why:** Every distinct URL (including utm_*, fbclid or random cache-busting query strings) or every user creates a new cache_render and dynamic_page_cache entry. Hit rate drops and the cache bins keep growing with traffic. The user and session contexts also match auto_placeholder_conditions: on an element that is not placeholdered (no #lazy_builder, or main content and title blocks) they stop Dynamic Page Cache from caching the whole response.

**Fix:** Use the narrowest context. Use url.query_args:page instead of url.query_args or url, route or route.name instead of url, and user.roles or user.permissions instead of user. Put genuinely per-user fragments in a #lazy_builder so they get placeholdered and the rest of the page stays cached.

**Not a finding when:** Breadcrumbs and menus legitimately vary by url.path or route. 'user' is correct for truly personal output (for example 'Hello, NAME') when it sits inside a lazy builder or a block that core placeholders. Exposed Views filters add 'url' by design (FilterPluginBase, core behaviour). Required contexts (user.permissions, theme, languages:language_interface) are always present. Look at what data the code actually reads before flagging.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api/cache-contexts · https://www.drupal.org/docs/drupal-apis/render-api/auto-placeholdering

### DPERF-06 · max-age 0 set outside a lazy builder bubbles up and stops Dynamic Page Cache for the whole page

**Severity:** high · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** 'max-age' => 0, ->setCacheMaxAge(0), ->mergeCacheMaxAge(0), Cache::mergeMaxAges(..., 0), getCacheMaxAge() { return 0; }, use UncacheableDependencyTrait, '#cache' => ['max-age' => 0] in hook_preprocess_page/html/node, hook_page_attachments, hook_entity_view, field formatters, theme suggestions or node templates. Also ->addCacheableDependency() with a non-cacheable object (see DPERF-02).

**Why:** DynamicPageCacheSubscriber::shouldCacheResponse() rejects any response whose bubbled max-age is not permanent and is at or below 0. One element in a node template or preprocess hook makes every page using it rebuild from scratch for all users. This gets worse as content grows.

**Fix:** Find the real invalidation source and use cache tags. If the output truly must be dynamic, move it into a #lazy_builder with scalar args. Auto-placeholdering then isolates it and the rest of the page stays cached. In block plugins, max-age 0 is isolated because BlockViewBuilder uses a lazy builder, but the block itself is still rebuilt on every request.

**Not a finding when:** max-age 0 inside a #lazy_builder callback's returned array, or on an element with '#create_placeholder' => TRUE, is placeholdered and does not break Dynamic Page Cache. Normal block plugins are also rendered through a lazy builder (the main content and title blocks are not, and hook_page_attachments / html preprocess are never placeholdered). Forms with CSRF tokens and user-specific pages behind login may be intentionally uncacheable. Check where in the tree the 0 is set before flagging.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api/cache-max-age · https://www.drupal.org/docs/drupal-apis/render-api/auto-placeholdering · https://www.drupal.org/docs/8/core/modules/dynamic-page-cache/overview

### DPERF-07 · Time-based max-age relied on for anonymous freshness (Internal Page Cache and Varnish ignore bubbled max-age)

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** 'max-age' => 3600 or 86400, or getCacheMaxAge() returning N seconds, on content anonymous users see (a 'latest news' block, a countdown, a 'today' date, an exchange-rate widget), with a comment or PR text along the lines of 'refresh every hour'. The same applies to ->setCacheMaxAge(N) on a CacheableResponse.

**Why:** PageCache::storeResponse stores entries permanently (expiry comes only from the Expires header, not from bubbled max-age) and invalidates them by tags. FinishResponseSubscriber builds Cache-Control from the global system.performance page max_age setting, not from bubbled max-age, so Varnish and CDNs do not see it either. The docs say max-age does not work for anonymous users with Page Cache, Varnish or CDNs. Anonymous visitors see the first rendered version until some tag is invalidated, which may be never.

**Fix:** Add a custom cache tag, for example '#cache' => ['tags' => ['mymodule:hourly']], and invalidate it from hook_cron or a scheduled queue: Cache::invalidateTags(['mymodule:hourly']). Alternatively render the time-sensitive fragment client-side (JS fetch of a small uncached or short-TTL endpoint).

**Not a finding when:** max-age is still honoured by the render cache and Dynamic Page Cache for authenticated users, so a site with no anonymous traffic (intranet, login required) is fine. A site with the page_cache module disabled and no reverse proxy is also fine. Contrib that changes this (Cache Control Override, or a CDN/purge integration that emits Cache-Control from bubbled max-age) changes the picture, so check composer.json and the enabled modules. Issue 2352009 (bubbling max-age to page headers) is still open, so do not assume core fixed it.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api/cache-max-age · https://www.drupal.org/project/drupal/issues/2352009 · https://www.drupal.org/docs/administering-a-drupal-site/internal-page-cache

### DPERF-08 · page_cache_kill_switch triggered (disables both Internal Page Cache and Dynamic Page Cache for the request)

**Severity:** high · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** \Drupal::service('page_cache_kill_switch')->trigger(), an injected KillSwitch with ->trigger(), @page_cache_kill_switch in *.services.yml. Also indirectly: ->messenger()->addStatus/addMessage/addWarning/addError( or \Drupal::messenger()->add*( called on a GET page build for anonymous users, because Messenger::addMessage() calls the kill switch.

**Why:** The kill_switch service is tagged for both page_cache_response_policy and dynamic_page_cache_response_policy. Any code path that triggers it on a commonly visited page (event subscribers, hook_page_attachments, preprocess) turns those pages into full uncached bootstraps, and database load then scales with traffic.

**Fix:** Express the real dependency with cache contexts or tags, or placeholder the dynamic part with #lazy_builder. Keep kill_switch for genuinely one-off responses (for example a page right after a form submit). Do not call messenger on GET page builds for anonymous users.

**Not a finding when:** This is fine in form submit handlers, on POST or redirect responses, on admin-only routes, and in controllers that already return uncacheable responses (file downloads, streamed responses). Messages set during form submission are expected. Check whether the code path runs on GET for anonymous users.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21PageCache%21ResponsePolicy%21KillSwitch.php/class/KillSwitch/11.x · https://www.drupal.org/docs/administering-a-drupal-site/internal-page-cache

### DPERF-09 · Session started for anonymous users (Internal Page Cache and Varnish bypassed for that visitor from then on)

**Severity:** high · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** $request->getSession()->set(, $this->requestStack->getSession()->set(, \Drupal::request()->getSession()->set(, $_SESSION[ writes, \Drupal::service('tempstore.private')->get(...)->set( or $this->privateTempStore->set( for anonymous users, and messenger()->add*( on GET. Such code in an event subscriber on KernelEvents::REQUEST or RESPONSE, in hook_page_attachments, preprocess, or a block build() is especially bad. Also session_start( calls.

**Why:** The NoSessionOpen page cache request policy skips the page cache when a session exists. Varnish or CDN configs usually pass requests that carry a session cookie. One write (PrivateTempStore sets a core.tempstore.private.owner key in the session for anonymous users) turns a cached anonymous visitor into a full bootstrap on every later page view.

**Fix:** Keep anonymous state out of the session. Use a client-side cookie read by JavaScript, or query parameters. If per-visitor state is really needed, keep it to POST flows and explicit user actions, and never set it on plain page views.

**Not a finding when:** Writing to the session after a user action such as a form submit, add-to-cart or login flow is expected. Commerce carts and webforms with drafts do this by design. Code gated by $account->isAuthenticated() does not create new anonymous sessions. Reading via ->get() or ->has() on an existing session does not start one.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21PageCache%21RequestPolicy%21NoSessionOpen.php/class/NoSessionOpen/11.x · https://www.drupal.org/docs/administering-a-drupal-site/internal-page-cache

### DPERF-11 · Custom listing or aggregate rendered without list or entity cache tags (new or edited content never appears)

**Severity:** high · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** A block plugin, controller or preprocess that runs ->getQuery()/entityQuery(, \Drupal::database()->select( or loadByProperties( and renders the results (titles, counts, 'latest 5') with no '#cache' tags at all, or with only per-entity tags (node:ID) and no list tag. Also a count or total shown with no tags. Also a custom cache->set($cid, $data) of query results with no tags argument.

**Why:** Per-entity tags handle edits of listed items but miss new items. Without a list tag, a newly published node never shows up until a full cache clear. Direct SQL (database select) results have no automatic tags at all.

**Fix:** Add list tags plus the tags of the rendered items: $tags = Cache::mergeTags($type->getBundleListCacheTags('article'), ...array_map(fn($e) => $e->getCacheTags(), $entities)); For raw SQL on custom tables, invent a custom tag ('mymodule_table') and invalidate it in the write path.

**Not a finding when:** Output built through Views or through ->view() of each entity already has tags. Admin-only or max-age 0 output is fine. Check whether a parent element or getCacheTags() already includes the list tag.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api/cache-tags · https://www.drupal.org/node/3107058

### DPERF-12 · Cache invalidation storms: broad or bulk tag invalidation or bin clears in hot paths and loops

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** Cache::invalidateTags( or $this->cacheTagsInvalidator->invalidateTags( inside foreach, hook_entity_presave/update/insert, #[Hook('entity_update')], queue workers or cron. Invalidating 'rendered', 'node_list', 'config:*', '4xx-response', 'http_response' or 'library_info' from content hooks. \Drupal::cache('render')->deleteAll(), ->invalidateAll(), drupal_flush_all_caches(), \Drupal::service('router.builder')->rebuild() in runtime code. Also ->save() on many entities inside one database transaction (startTransaction) on a busy site.

**Why:** Each distinct tag invalidation is a write to cachetags (or Redis). Broad tags wipe large portions of cache_render and page cache. After a bulk import or a busy editing period, the site cold-starts over and over, and database load spikes grow with content volume. Broad tags such as node_list written inside long transactions also cause row-lock contention and deadlocks on the cachetags table (issue 2966607). Core dedupes the same tag within one request (CacheTagsChecksumTrait::invalidatedTags), but not distinct per-item tags or bin-wide clears.

**Fix:** Invalidate the narrowest tag that actually changed, and let core's entity save invalidate entity and list tags; do not add extra calls on top. Collect tags and call invalidateTags() once after the loop. Never call deleteAll(), drupal_flush_all_caches() or a router rebuild from request-time code. For bulk imports, use a queue or batch and keep transactions short.

**Not a finding when:** Invalidating a custom narrow tag once per operation is correct. Invalidating the same tag repeatedly in one request is deduplicated by core. Admin config forms that invalidate config:* or rendered on submit are expected and rare. Deploy-time code (hook_update_N, hook_deploy_NAME, drush commands) may flush caches.

**Also covers DPERF-10 (Overly broad list cache tag (node_list, taxonomy_term_list) where the bundle-specific tag would do).** Signals: 'tags' => ['node_list'], $entityType->getListCacheTags(), Cache::mergeTags(..., ['node_list']), 'media_list', 'taxonomy_term_list' or 'commerce_product_list' on a listing that only shows one bundle, for example an entity query with ->condition('type', 'article'). Not a finding when: The broad tag is correct when the listing mixes bundles, or when the query has no bundle condition. Core Views uses the entity-type-wide list tag by design (CachePluginBase::getCacheTags), so do not flag Views config for this; that needs contrib (views_custom_cache_tag) and is an optimisation, not a bug. Taxonomy term lists with one vocabulary can use taxonomy_term_list:VOCAB.

**Also check:** Cache tag invalidation inside long database transactions (startTransaction around many entity saves or imports) causing row-lock contention and deadlocks on the cachetags table when broad tags such as node_list are invalidated. Source: https://www.drupal.org/project/drupal/issues/2966607

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api/cache-tags · https://www.drupal.org/project/drupal/issues/2966607 · https://www.drupal.org/node/3107058

### DPERF-13 · Custom cache entries with unbounded cache IDs, no tags or no expiry (bin growth; cachetags table growth)

**Severity:** medium · **Area:** performance · **Taxonomy:** CWE-770 · **Applies to:** Drupal 10.x and 11.x. Cachetags purge on cache rebuild exists only from 11.2 (not in 10.5 or 10.6).

**Signals:** \Drupal::cache()->set($cid, ... or $this->cache->set( where $cid includes user input, the full query string, a search term, $request->getRequestUri(), a timestamp or a random value. Also set( with Cache::PERMANENT and no tags. Also '#cache' => ['keys' => [...]] combined with 'url' or 'url.query_args' contexts on elements shown site-wide. Also custom cache tags built from unbounded values ('mymodule:search:' . $term).

**Why:** Each unique key or tag creates a row. DatabaseBackend caps a bin at 5000 rows by default (database_cache_max_rows, enforced by garbage collection), but Redis and Memcache backends do not use that cap, and before 11.2 the cachetags table was never purged (from 11.2 it is truncated only on a full cache rebuild). With crawler traffic these bins and tables grow indefinitely and slow down every cache lookup and backup.

**Fix:** Build cache IDs from normalised, bounded parts (a hash of an allowlisted parameter set). Set an expire time for data that is not tag-invalidated (time() + 3600). Use tags that map to real data (entity or config). Drop render #cache keys on elements whose contexts include url or query args unless the fragment is really expensive.

**Not a finding when:** cid parts from a small fixed set (language, bundle, entity ID for existing entities) are fine. Temporary per-request caching in MemoryCache or drupal_static does not persist. A database backend with a row limit bounds growth. Check the configured cache backend (settings.php, services.yml with Redis) before rating severity.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api · https://www.drupal.org/project/drupal/issues/3097393

### DPERF-14 · Personalised or expensive fragment not built with a lazy builder, or lazy builder defined incorrectly

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x. A lazy builder may return a #type render array only from 10.5 and 11.2 (not in 10.4, 11.0 or 11.1).

**Signals:** Per-user output (cart count, 'Hello NAME', flag or like state, recently viewed) built inline in a node or page render array with 'contexts' => ['user'] or ['session'] and no '#lazy_builder'. Also a '#lazy_builder' => [callback, $args] where $args contains an object or array (entity, $node) instead of scalars, or the element has children or other # keys besides #cache, #create_placeholder, #lazy_builder_preview, #placeholder_strategy_denylist and #preview. Also a callback class that has neither TrustedCallbackInterface::trustedCallbacks() nor a #[TrustedCallback] attribute on the method (and does not implement RenderCallbackInterface), or a procedural function string for #lazy_builder, #pre_render or #post_render.

**Why:** Without a lazy builder, core cannot placeholder the fragment. Its user or session context bubbles to the page, and Dynamic Page Cache then refuses to cache the page for every authenticated user. Invalid lazy-builder definitions fail assertions in development, and untrusted callbacks throw UntrustedCallbackException at render time.

**Fix:** '#lazy_builder' => [MyLazyBuilder::class . '::build', [$node->id(), $langcode]], '#create_placeholder' => TRUE, and mark the callback trusted: implement TrustedCallbackInterface { public static function trustedCallbacks() { return ['build']; } } or add #[TrustedCallback] to the method. Load the entity by ID inside the callback. On versions before 10.5/11.2, return #theme or #markup rather than #type.

**Not a finding when:** Blocks placed through block layout are already built through a lazy builder by BlockViewBuilder, so a per-user block plugin is fine. Closures are allowed as callbacks (doTrustedCallback treats Closure as safe). Service-method strings such as 'my_module.lazy_builder:build' are valid lazy builder callbacks and are resolved through the callable resolver; check that service class for trust before flagging. Classes implementing RenderCallbackInterface (element plugins) need no trustedCallbacks(). Output with only user.roles or user.permissions is low-cardinality and need not be placeholdered.

**Sources:** https://www.drupal.org/docs/drupal-apis/render-api/auto-placeholdering · https://www.drupal.org/node/2966725 · https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Security%21TrustedCallbackInterface.php/interface/TrustedCallbackInterface/11.x · https://www.drupal.org/docs/8/core/modules/big-pipe/overview

### DPERF-15 · Early rendering: render arrays turned into strings in controllers or isolated contexts, losing or leaking cache metadata

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x (renderPlain deprecated in 10.3, removed in 12.0)

**Signals:** In a controller, form or route callback: $renderer->render($build), ->renderRoot( or \Drupal::service('renderer')->render( whose string is returned in a response or put into '#markup' or JSON. Also ->renderPlain( (deprecated in 10.3) or ->renderInIsolation( with the string result placed into a cacheable page. Also Url::toString() without TRUE in a controller. Also the error 'leaked metadata was detected' in the PR discussion.

**Why:** renderInIsolation and renderPlain discard the bubbling of tags, contexts and attachments, so a parent that embeds the string is cached with too little metadata (stale or wrong-user content). In controllers, early rendering makes core throw a LogicException about leaked metadata (EarlyRenderingControllerWrapperSubscriber).

**Fix:** Return render arrays and let the theme layer render them. When a string is unavoidable (JSON, mail), use $context = new RenderContext(); $out = $renderer->executeInRenderContext($context, fn() => $renderer->render($build)); and then apply $context->pop() to the response via addCacheableDependency. Use $url->toString(TRUE) and apply its metadata.

**Not a finding when:** renderInIsolation() for emails, PDF generation, CLI output or other output that is never page-cached is correct. $renderer->render() called inside preprocess, formatters, #pre_render or #lazy_builder callbacks runs in an active render context and bubbles correctly, so it is not a metadata bug by itself. Calling render() with no render context at all throws a LogicException at once, so it fails loudly and is caught by tests. Check the destination of the string before flagging.

**Sources:** https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays · https://www.drupal.org/node/3407994

### DPERF-16 · Custom controller returns a non-cacheable Response or JsonResponse on a hot route, or a CacheableJsonResponse without metadata

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** return new JsonResponse( or new Response( in a controller for a GET route used by the front end, AJAX autocompletes or decoupled clients. Also new CacheableJsonResponse( or CacheableResponse without ->addCacheableDependency(...) or ->getCacheableMetadata()->addCacheContexts/Tags, especially when the data comes from a query string, entities or config.

**Why:** Internal Page Cache stores only CacheableResponseInterface responses, so a plain JsonResponse is 'UNCACHEABLE (no cacheability)' and every anonymous hit runs a full bootstrap and query. The opposite mistake, a CacheableJsonResponse with no tags or contexts, is cached permanently for anonymous users and never invalidated, and Dynamic Page Cache can serve one query string's data for another.

**Fix:** $response = new CacheableJsonResponse($data); $response->addCacheableDependency(CacheableMetadata::createFromRenderArray(['#cache' => ['tags' => $tags, 'contexts' => ['url.query_args:q']]])); For per-user endpoints, keep them uncacheable or add the 'user' context deliberately.

**Not a finding when:** POST, PUT or DELETE endpoints, per-user endpoints behind authentication, CSRF-token endpoints and file downloads (BinaryFileResponse and StreamedResponse are never page-cached) do not need caching. Routes with 'no_cache: TRUE' on purpose are fine. Low-traffic admin JSON is fine.

**Also covers DEC-19 (Custom endpoint for the frontend relies on cache contexts or max-age under the Internal Page Cache).** Signals: new CacheableJsonResponse or CacheableResponse in a controller or REST plugin; ->addCacheableDependency with contexts like 'headers:*', 'languages:language_interface', 'cookies:*', 'user', 'session', 'url.query_args:x' in anonymous-facing routes; setMaxAge(0) or small max-age expecting expiry; missing addCacheableDependency($entity) or cache tags; JsonResponse (uncacheable) on hot endpoints Not a finding when: Contexts still work for authenticated users (Dynamic Page Cache) and in render arrays. Only anonymous full-response caching is affected. url.query_args contexts are harmless because the query string is part of the page cache key. Sites without page_cache are unaffected.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api · https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays · https://www.drupal.org/docs/administering-a-drupal-site/internal-page-cache · https://git.drupalcode.org/project/drupal/-/blob/11.x/core/modules/page_cache/src/StackMiddleware/PageCache.php · https://www.drupal.org/docs/develop/drupal-apis/cache-api/cache-contexts

### DPERF-17 · Block plugin cacheability wrong: missing getCacheTags/getCacheContexts overrides, max-age 0 shortcut, or parent metadata dropped

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x (CacheOptionalInterface exists from 10.5 and 11.1)

**Signals:** A class extending BlockBase in src/Plugin/Block/ whose build() uses the current route, user, node from the route or config, with no getCacheContexts() or getCacheTags() override. Also getCacheMaxAge() { return 0; } added 'because it was not updating'. Also overrides that return ['route'] without Cache::mergeContexts(parent::getCacheContexts(), ...), which drops contexts that come from the plugin context.

**Why:** Block output is render-cached by block ID. Missing contexts show one page's data on every page; missing tags keep stale content; and max-age 0 makes the block rebuild on every request for authenticated users while still being cached forever for anonymous users by the page cache (max-age is ignored there).

**Fix:** public function getCacheContexts() { return Cache::mergeContexts(parent::getCacheContexts(), ['route']); } public function getCacheTags() { return Cache::mergeTags(parent::getCacheTags(), $node->getCacheTags()); } Or put '#cache' in the array returned by build() with the dependencies you read.

**Not a finding when:** Blocks implementing CacheOptionalInterface intentionally skip render cache keys (BlockViewBuilder). Blocks using context_definitions (for example 'node' => EntityContextDefinition) get context cacheability from ContextAwarePluginTrait. Cacheability can also be declared in build()'s '#cache'. Check both places before flagging.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Block%21BlockPluginInterface.php/interface/BlockPluginInterface/11.x · https://www.drupal.org/docs/drupal-apis/cache-api/cache-max-age

### DPERF-18 · Entity load inside a loop (N+1) instead of loadMultiple()

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** Inside foreach, for or array_map: Node::load($id), $storage->load($id), \Drupal::entityTypeManager()->getStorage(...)->load(, User::load(, File::load(, Term::load(, ->loadByProperties( per item. Also $item->entity accessed in a loop over a multi-value reference field in custom code (each access can load separately unless referencedEntities() is used).

**Why:** Each load is at least one query per entity, plus field tables on a cache miss. The cost grows linearly with list size. A 'show all related' block that is fast with 10 items becomes seconds with thousands.

**Fix:** $entities = $storage->loadMultiple($ids); For reference fields use $node->get('field_tags')->referencedEntities(); Collect IDs first, load once, then iterate.

**Not a finding when:** A loop that is bounded by a small constant (for example up to three configured items) is minor. Loads that are guaranteed to hit the entity static cache (the same IDs loaded just before) are also cheap. Drush or update hooks that process in batches with resets are fine. Rate low severity if the list is config-bounded.

**Also covers DPERF-20 (Full entities loaded only to read one field, check existence or count).** Signals: count($storage->loadByProperties( or count(Node::loadMultiple( to count. Also !empty($storage->loadByProperties(['field_x' => $v])) to check existence. Also loadMultiple($ids) followed by only ->label(), ->id() or ->get('field_x')->value in a loop over many IDs. Also array_map(fn($n) => $n->field_date->value, $nodes) for sorting or filtering in PHP what could be a query condition or sort. Not a finding when: The entities may be loaded for rendering in the same request anyway (then they are in the static cache). Small bounded sets are fine. Direct SQL on field tables bypasses access and entity APIs, so do not recommend it for user-facing listings that need node access.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21EntityStorageInterface.php/function/EntityStorageInterface%3A%3AloadMultiple/11.x · https://www.drupal.org/docs/drupal-apis/entity-api/working-with-the-entity-api · https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21Query%21QueryInterface.php/function/QueryInterface%3A%3Arange/11.x

### DPERF-19 · Entity query or database select on a growing table without range(), pager or batching

**Severity:** high · **Area:** performance · **Taxonomy:** CWE-400 · **Applies to:** Drupal 10.x and 11.x

**Signals:** ->getQuery()/::entityQuery( ... ->execute() with no ->range( or ->pager( followed by loadMultiple($ids) on nodes, users, comments, media, files, commerce orders, log or submission entities. Also ->loadMultiple() with no arguments (loads ALL entities), ->loadByProperties([...]) on broad conditions, \Drupal::database()->select(...)->execute()->fetchAll() on custom tables, and webform_submission or watchdog selects without a limit.

**Why:** The result set and memory grow with the data. It is fine at launch and turns into timeouts or out-of-memory errors once the table has 100k or more rows. Most often it hits cron, exports and the 'all items' page.

**Fix:** Add ->range(0, $limit) or ->pager($n). Use ->count()->execute() for counts. For processing all rows, use a queue or batch with ->range($offset, $chunk) or an ID cursor (condition('nid', $last, '>')->sort('nid')->range(0, 100)).

**Not a finding when:** Queries on config entities, vocabularies with a known small size, or entities filtered by a unique value (condition on an ID or a unique field) do not need a range. Queries already inside a Batch operation with a sandbox limit are fine. Check the entity type and the conditions.

**Also check:** Views configured without a bound: pager type 'none' or items_per_page 0 (all items) on content views, or 'offset' hacks, in config/sync/views.view.*.yml. Detectable in a config diff and grows with content. Source: https://api.drupal.org/api/drupal/core%21modules%21views%21src%21Plugin%21views%21pager%21None.php/class/None/11.x

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21Query%21QueryInterface.php/function/QueryInterface%3A%3Arange/11.x · https://www.drupal.org/docs/drupal-apis/batch-api/batch-api-overview

### DPERF-21 · Heavy logic in preprocess functions or Twig (queries, loads, HTTP, nested rendering per item)

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** In *.theme or *.module preprocess functions (hook_preprocess_node, _field, _paragraph, _views_view_field, _block, _html, _page), or #[Hook('preprocess_node')] methods: entityQuery, ->load(, loadMultiple(, \Drupal::database(, \Drupal::httpClient(, file_get_contents(, views_embed_view(, views_get_view_result(. In *.html.twig: drupal_view(, drupal_entity(, drupal_block(, drupal_field( (twig_tweak) inside {% for %} loops, or chains like node.field_ref.entity.field_other.entity.label repeated per row.

**Why:** Preprocess runs on every render-cache miss and once per item. In teaser lists, Views rows and paragraphs, the cost multiplies by the number of items and nesting depth. Page build time grows with content even when individual pages look fine in development.

**Fix:** Move data fetching to a service called once per request, and use loadMultiple for all items. Put expensive or personalised parts in a #lazy_builder, or compute the data at save time (a stored field or computed field with cache). In Twig, prefer {{ content.field_x }} (already built) over walking entity references.

**Not a finding when:** Preprocess work on render-cached elements runs only on a cache miss. When cacheability is correct and invalidation is rare, a single load for a single page element is fine. hook_preprocess_html or page doing one config read is fine. Judge the per-item multiplier, not a single call.

**Sources:** https://www.drupal.org/docs/drupal-apis/render-api/render-arrays · https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays

### DPERF-23 · Expensive or uncacheable entity and node access hooks, and query alters that apply to every query

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** New hook_entity_access, hook_ENTITY_TYPE_access, hook_node_access, or #[Hook('entity_access')] or #[Hook('node_access')] that runs entity queries, loads other entities, calls HTTP or reads the database per call, or returns results without cacheability. Also hook_node_grants or hook_node_access_records (grants system; adds the user.node_grants context and node_access joins on every listing query and requires a node_access rebuild). Also hook_query_alter or hook_query_TAG_alter that adds joins or subqueries without checking $query->hasTag() first, or that alters 'entity_query' or 'node_access' broadly.

**Why:** Access hooks run for every entity access check (each teaser, each reference field, each menu link), so their cost multiplies by the number of items on the page. Node grants add joins to every node listing query and a per-user grants context. The cost grows with content and user count, and a node_access rebuild on large sites can take hours.

**Fix:** Keep access hooks O(1): use data already on the entity, static per-request memoisation keyed by entity ID and user, and return AccessResult with correct cacheability (cachePerUser or addCacheableDependency). In query alters, return early unless $query->hasTag('your_tag'). Before adding grants, check whether a permission-based or field-based check (for example contrib access modules) would do.

**Not a finding when:** A simple field or permission check with no I/O is cheap. hook_query_TAG_alter scoped to a custom tag only affects queries that opt in. The grants system is the correct tool for listing-level access (Views, search). Flag the cost, not the approach, when listings must respect the access rule.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21entity.api.php/function/hook_entity_access/11.x · https://api.drupal.org/api/drupal/core%21modules%21node%21node.api.php/function/hook_node_grants/11.x

### DPERF-24 · Views config disables caching or adds cache-defeating handlers (cache none, random sort, exposed filters on high-traffic displays)

**Severity:** medium · **Area:** cache · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** In config/sync/views.view.*.yml: 'cache:' with 'type: none', or 'type: time' on content that should be tag-invalidated. Also 'sorts:' with 'plugin_id: random' (the Random sort is uncacheable, max-age 0). Also 'exposed: true' filters on displays embedded site-wide (they add the 'url' context), and 'max-age: 0' under 'cache_metadata'. Also a custom Views plugin or handler using UncacheableDependencyTrait or getCacheMaxAge() returning 0. Also views_embed_view() or views_get_view_result() in preprocess.

**Why:** 'none' disables results and output caching, so every view render re-runs the SQL, which gets slower as the base table grows. A random sort or an uncacheable handler bubbles max-age 0 into the page. Exposed filters vary per URL. Time-based cache shows stale content to anonymous users (see DPERF-07).

**Fix:** Use 'type: tag' (the default) for content listings. Replace random sort with a precomputed or JavaScript-based shuffle, or put the view in a block that is placeholdered. Keep exposed filters on dedicated search pages, and combine them with Search API caching where available.

**Not a finding when:** 'none' is correct for admin views (/admin/content), views with per-user data behind login, and Search API views that use their own cache plugins ('search_api_tag', 'search_api_time'). Exposed filters on the actual search page are expected. Check the display's path, the access settings and the base table.

**Sources:** https://www.drupal.org/docs/drupal-apis/cache-api/cache-tags · https://www.drupal.org/docs/drupal-apis/cache-api/cache-max-age

### DPERF-25 · hook_cron or a drush command doing unbounded work in one run instead of Queue API or Batch

**Severity:** high · **Area:** performance · **Taxonomy:** CWE-400 · **Applies to:** Drupal 10.x and 11.x (the #[QueueWorker] attribute exists from 10.3; older code uses the @QueueWorker annotation)

**Signals:** hook_cron or #[Hook('cron')] that loads, queries or saves all entities, sends mails in a loop, calls external APIs per item, re-indexes or re-imports feeds, with no ->range() and no state cursor. Also a batch operation that does all the work on its first call without using $context['sandbox'] and $context['finished']. Also a QueueWorker with a very large 'cron' => ['time' => N] or slow per-item work, or a queue populated with one item per row and no deduplication.

**Why:** Cron runs in one PHP process with time and memory limits. The work grows with data until cron times out partway through, sometimes holding the cron lock (900 seconds), and every later cron task (search index, cache purge, cleanup) stops running. With the automated_cron module the page request that triggers cron pays the cost.

**Fix:** In hook_cron, only enqueue: $queue = \Drupal::queue('mymodule_sync'); foreach ($ids as $id) { $queue->createItem(['id' => $id]); }. Process with a #[QueueWorker(id: 'mymodule_sync', cron: ['time' => 30])] plugin. Track progress with a state cursor, and throttle by timestamp (\Drupal::state()->get('mymodule.last_run')). For UI-triggered bulk work use Batch API with a sandbox.

**Not a finding when:** Cron tasks bounded by design (for example deleting rows older than X with a single DELETE query, or processing up to 50 items) are fine. Cron that only enqueues is fine. A QueueWorker without a 'cron' key is not run by cron at all (it needs drush queue:run or another runner), which is intentional for heavy workers and not a bug. Drush commands intended to run for a long time in CLI are acceptable if they batch and reset static caches (see DPERF-29).

**Also check:** hook_update_N or post-update code that processes a whole table in one call without $sandbox and $sandbox['#finished'], which times out on production data during deploys. Source: https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Extension%21module.api.php/function/hook_update_N/11.x

**Sources:** https://api.drupal.org/api/drupal/core%21core.api.php/function/hook_cron/11.x · https://api.drupal.org/api/drupal/core%21core.api.php/group/queue/11.x · https://www.drupal.org/docs/drupal-apis/batch-api/batch-api-overview

### DPERF-26 · Unbounded data growth: custom tables, key_value, logs or tracking rows with no cleanup

**Severity:** medium · **Area:** performance · **Taxonomy:** CWE-770 · **Applies to:** Drupal 10.x and 11.x

**Signals:** hook_schema or an update hook creating a table with a 'created' or 'timestamp' column for events, logs, views, clicks, API responses or import history, and no DELETE in hook_cron and no purge queue. Also \Drupal::keyValue('x')->set($dynamic_key, ...) with per-entity or per-request keys, or keyValueExpirable set() where no expiry is given (use setWithExpire()). Also \Drupal::logger()->info()/notice() per request or per item in hot paths. Also dblog.settings.yml with 'row_limit: 0' (unlimited). Also entity types used as logs (one entity per event) with no retention.

**Why:** These tables grow linearly with traffic or time. Queries, backups, database dumps for local environments and migrations get slower month by month, and nobody notices until the database is tens of gigabytes.

**Fix:** Add a retention policy in hook_cron: $this->database->delete('mymodule_log')->condition('created', time() - 30*86400, '<')->execute(); Use keyValueExpirable with setWithExpire(). Log at debug level or behind a setting. Keep dblog row_limit bounded (core default 1000), or use syslog.

**Not a finding when:** Tables of business data that must be kept (orders, submissions with a legal retention requirement) are not a problem; suggest archiving, not deletion. Expired keyValueExpirable entries are garbage-collected by system cron. dblog with the default row_limit is self-limiting. Check for existing cleanup elsewhere in the module before flagging.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Database%21database.api.php/function/hook_schema/11.x · https://api.drupal.org/api/drupal/core%21core.api.php/function/hook_cron/11.x

### DPERF-27 · State API used for large, per-entity or frequently changing data (State is a cache collector since 10.3)

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** Drupal 10.3+ (cache collector enabled by default on new installs, opt-in via $settings['state_cache'] for existing sites) and 11.x (always on, the setting was removed in 11.0)

**Signals:** \Drupal::state()->set( or $this->state->set( with a large array (API response dumps, ID lists, serialized objects), with a dynamic key per entity or user ('mymodule.last_seen.' . $uid), or called on every request (counters, timestamps in an event subscriber or preprocess).

**Why:** State extends CacheCollector, so accessed keys are persisted together in one cache entry. Frequent writes invalidate that entry for all requests, and large or dynamic keys bloat what every request loads. The change record says State should hold a small number of small, commonly accessed items (it suggests reviewing usage above about 100 entries or 100,000 bytes) and points to the key value API for the rest.

**Fix:** Use a custom table, key_value (keyValue('mymodule')) for per-entity data, or a cache bin for cached API data. Keep State for small, rarely changing system flags (last cron run, a feature toggle).

**Not a finding when:** Small scalar values written rarely (a last-import timestamp updated by cron once an hour) are what State is for. A write in cron or a drush command is not a per-request write. Check how often the write path runs.

**Sources:** https://www.drupal.org/node/3177901 · https://www.drupal.org/node/3443018

### DPERF-28 · Missing indexes in hook_schema or update hooks for columns used in WHERE, JOIN or ORDER BY

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** New or changed hook_schema() in *.install, or a schema update in hook_update_N using ->createTable( or ->addField(, where 'fields' are added but no 'indexes', 'unique keys' or 'primary key' cover columns that appear in ->condition('col', ...), ->orderBy('col') or joins in the same diff (uid, entity_id, status, created, type, foreign IDs). Also ->addField without a matching ->addIndex( when the new column is queried.

**Why:** Without an index, every lookup scans the whole table. That is invisible with test data and grows linearly with rows, so a table that grows daily (see DPERF-26) becomes the slowest query on the site.

**Fix:** 'indexes' => ['uid_created' => ['uid', 'created']], 'primary key' => ['id']. In updates: $schema->addIndex('mymodule_log', 'uid_created', ['uid', 'created'], $spec); Match composite index order to the query's equality columns first, then the sort column.

**Not a finding when:** Tiny lookup tables (tens of rows), tables only read by primary key, and content entity base fields (the entity storage schema handles those, though custom entities may need an index via the storage schema handler) do not need extra indexes. Do not ask for indexes on every column; index writes cost too.

**Also check:** Non-indexable or randomised SQL: ->orderRandom(), addExpression('RAND()'), entity query or Views 'contains' / LIKE '%term%' filters on large unindexed columns, and ORDER BY on unindexed expressions. Grows with table size. Source: https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Database%21Query%21SelectInterface.php/function/SelectInterface%3A%3AorderRandom/11.x

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Database%21database.api.php/function/hook_schema/11.x

### DPERF-29 · Static or in-memory caches that grow unbounded in long-running drush, queue or migrate processes

**Severity:** medium · **Area:** performance · **Taxonomy:** CWE-401 · **Applies to:** Drupal 10.x including 10.5 (entity static cache is unbounded MemoryCache) and 11.2+ (entity memory cache is an LRU with entity.memory_cache.slots = 1000)

**Signals:** &drupal_static(__FUNCTION__) or a service property like $this->cache[$id] = ... filled per entity with no size limit, in services used by drush commands, QueueWorkers, migrations or Batch. Also drush or queue loops that ->load() or ->save() thousands of entities without $storage->resetCache($ids) (on 10.x) or without chunking. Also MemoryCache or 'cache.memory' bins used as an application cache without eviction.

**Why:** In web requests the memory is freed after each request. In a CLI process that runs for an hour, every loaded entity and every cached value stays until PHP runs out of memory, and the job fails at the same point every time the data grows. Core 11.2+ bounds only the entity memory cache (LRU, 1000 slots, roughly 200MB per the change record), not your own static arrays.

**Fix:** Process in chunks and, on 10.x, call $storage->resetCache($ids) after each chunk. Cap custom static arrays or use drupal_static_reset('name'). In 11.x, lower entity.memory_cache.slots on memory-constrained hosts, or use LruMemoryCache for custom memoisation.

**Not a finding when:** Per-request memoisation in web code (a handful of keys, or keyed by current user) is a good pattern. Static caches keyed by bundle or config are bounded. On 11.2+ the entity load cache is already LRU-bounded, so do not flag entity loads in drush loops on 11.2+ unless memory limits are tight.

**Sources:** https://www.drupal.org/node/3512407 · https://api.drupal.org/api/drupal/core%21includes%21bootstrap.inc/function/drupal_static/11.x

### DPERF-30 · External HTTP call during page build without cache, short timeout or placeholder

**Severity:** high · **Area:** performance · **Taxonomy:** CWE-400 · **Applies to:** Drupal 10.x and 11.x

**Signals:** \Drupal::httpClient()->get( or request(, $this->httpClient->, new GuzzleHttp\Client(, file_get_contents('http, or curl_exec( inside block build(), controllers, preprocess, hook_entity_view, field formatters, event subscribers on KernelEvents::REQUEST or RESPONSE, or form builds. Also no 'timeout' or 'connect_timeout' option passed, and no $this->cache->get() or ->set() around the call.

**Why:** Core's ClientFactory default timeout is 30 seconds, so a slow or failing third party ties up PHP workers for up to 30 seconds per request. Under load that exhausts the FPM pool and takes the whole site down. Without caching, every cache miss or every request (if max-age 0) repeats the call.

**Fix:** $data = $this->cache->get($cid)?->data ?? ...; $response = $this->httpClient->get($url, ['timeout' => 3, 'connect_timeout' => 2]); $this->cache->set($cid, $data, time() + 900, ['mymodule:feed']); Catch GuzzleException and render a fallback. Prefer fetching in cron or a queue and rendering from stored data. If it must be live, put it in a #lazy_builder so BigPipe streams the rest of the page.

**Not a finding when:** Calls in form submit handlers or POST endpoints, where the user expects to wait, are acceptable if they have a timeout. Calls in cron, queue workers or drush are fine. Calls to local services (Solr via Search API, Redis) go through their own clients with configured timeouts. OAuth token requests that are cached are fine.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Http%21ClientFactory.php/11.x · https://www.drupal.org/docs/8/core/modules/big-pipe/overview

### DPERF-33 · Entity save or heavy work in entity CRUD hooks that fires for every save (import and bulk-edit amplification)

**Severity:** medium · **Area:** performance · **Taxonomy:** - · **Applies to:** Drupal 10.x and 11.x

**Signals:** hook_entity_presave, hook_entity_insert, hook_entity_update, hook_ENTITY_TYPE_update, or #[Hook('node_update')] etc. that call ->save() on other entities (parents, related nodes, users), run entity queries across the site, call HTTP APIs, rebuild menus or routers, or recalculate aggregates by loading all children. The hooks are unconditional, with no check of $entity->bundle(), no check that the relevant field changed ($entity->original or $entity->getOriginal() comparison), and no guard for isSyncing().

**Why:** Every save, including migrations, bulk operations, workflow transitions and translations, pays this cost. Chained saves trigger more hooks and cache tag invalidations (DPERF-12). Imports that took minutes start taking hours as related content grows, and recursive saves can cause loops.

**Fix:** Return early unless the bundle matches and the watched field actually changed. Push follow-up work to a queue ($queue->createItem(['nid' => $entity->id()])). Skip when $entity->isSyncing() during migrations. Aggregate with a count or aggregate query instead of loading all children.

**Not a finding when:** Cheap, bundle-scoped updates of fields on the same entity in presave (no extra save) are fine. Hooks that already enqueue work are fine. Check for existing bundle and field-change guards before flagging.

**Sources:** https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21entity.api.php/function/hook_entity_presave/11.x · https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Entity%21entity.api.php/function/hook_entity_update/11.x · https://api.drupal.org/api/drupal/core%21core.api.php/group/queue/11.x

### DPERF-34 · Custom code overriding Cache-Control / Expires / Vary / private headers

**Severity:** medium · **Area:** cache

**Check:** Custom code that sets its own Cache-Control, Expires, Vary or private/no-store headers (response event subscribers, $response->setPrivate(), ->setMaxAge(), headers->set('Cache-Control', ...)) and so overrides FinishResponseSubscriber and breaks page cache, Varnish or CDN caching. Source: https://git.drupalcode.org/project/drupal/-/blob/11.x/core/lib/Drupal/Core/EventSubscriber/FinishResponseSubscriber.php

### DPERF-35 · Heavy libraries attached site-wide

**Severity:** low · **Area:** performance

**Check:** Asset loading cost in *.libraries.yml and attach_library: heavy libraries attached site-wide (theme .info.yml libraries, hook_page_attachments, preprocess_html) but used on one page, preprocess: false, external unminified scripts without async or defer, large CSS or JS added to every page. Source: https://www.drupal.org/docs/theming-drupal/adding-assets-css-js-to-a-drupal-theme-via-librariesyml
