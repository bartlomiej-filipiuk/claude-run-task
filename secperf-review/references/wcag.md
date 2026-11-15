# Accessibility (WCAG 2.2 AA, light)

Only what code shows: Twig, Form API / render arrays, JSX. Skip anything the repo's enabled eslint jsx-a11y rules already block.

Each item: severity is the default; `severity.md` escalation and downgrade rules apply. Report a pattern only when "Not a finding when" does not hold for the code you read.

### A11Y-01 · Image rendered without an alt attribute (JSX img/Image, Twig img, Drupal image render arrays)

**Severity:** high · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 1.1.1 (A) · **Applies to:** Drupal 10/11 Twig and render arrays; Next.js 14-16 App and Pages Router

**Signals:** JSX: `<img` or `<Image` (next/image) with no `alt=` prop, or an `alt={x}` where x can be undefined (`alt={item.alt}` from CMS/JSON:API data without a fallback). Twig: `<img src="{{ file_url(` / `{{ image_url }}` / `src="{{ node.field_image.entity.uri.value` with no `alt=`. PHP: `'#theme' => 'image'` or `'#theme' => 'image_style'` without `'#alt'`, or `'#type' => 'html_tag', '#tag' => 'img'` without alt in #attributes. Also `// eslint-disable-next-line jsx-a11y/alt-text` or `@next/next/no-img-element` disables next to an img.

**Why:** A screen reader announces a missing alt as the file name or URL, and an image link loses its accessible name entirely. On a decoupled site one bad component spreads this to every page that uses it.

**Fix:** Always pass alt. Use meaningful text, or `alt=""` when the image is decorative. For CMS data, map the field's alt explicitly: `<Image src={img.url} alt={img.alt ?? ''} ... />`. In Drupal, render the field through its formatter (`{{ content.field_image }}`), or pass `'#alt' => $item->alt`. In Twig: `<img src="{{ url }}" alt="{{ alt }}">`.

**Not a finding when:** `{{ content.field_image }}` and image/responsive_image formatters output alt from the field, so do not flag them. `alt=""` is correct for decorative images (see A11Y-02). An img inside an element with role=presentation/aria-hidden that is purely decorative is fine. CSS background images are out of scope here. The eslint alt-text rule in eslint-config-next only covers `img` and `Image`, so a custom wrapper (`<CmsImage>`) needs a manual check that it forwards alt. In TypeScript projects `alt` is a required prop of next/image, so a literally missing prop already fails tsc and the dev overlay. Spend effort on wrappers, untyped/any data, and `alt={undefined}` paths instead.

**Also covers DEC-36 (Drupal image alt text not passed to next/image).** Signals: <Image alt="" .../> or alt={node.title} for content images; JSON:API image relationship meta.alt (next-drupal: field_image.resourceIdObjMeta.alt, field_media_image.resourceIdObjMeta.alt, or thumbnail.resourceIdObjMeta.alt) not read; GraphQL image fragments without alt; html-react-parser replace() for <img> dropping the alt attribute Not a finding when: Decorative background images and icons next to a text label are correct with alt="". Using the title as alt can be acceptable when the image is the linked teaser and no other text is present.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html · https://nextjs.org/docs/app/api-reference/components/image#alt · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/alt-text.md · https://nextjs.org/docs/app/api-reference/components/image

### A11Y-03 · Form control without a programmatic label (placeholder used as label, Form API #title missing or label suppressed)

**Severity:** high · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 1.3.1 (A), 3.3.2 (A), 4.1.2 (A) · **Applies to:** Drupal 10/11 Form API and Twig; React/JSX in Next.js 14-16

**Signals:** JSX: `<input`, `<select`, `<textarea` with `placeholder=` but no `<label htmlFor=` matching its `id`, no wrapping `<label>`, no `aria-label`/`aria-labelledby` (jsx-a11y/label-has-associated-control, on in recommended; control-has-associated-label is off even in recommended). `<label>` without `htmlFor` and not wrapping the control. Hardcoded `id="email"` in a reusable component (breaks htmlFor when the component renders twice; prefer `useId()`). Drupal PHP: a `'#type' => 'textfield'|'select'|'search'|'email'|'textarea'` element with no `'#title'`, or `unset($form[...]['#title'])` in a form_alter, or `'#title_display' => 'attribute'` on anything other than checkboxes/radios (no label is output at all). Twig overrides of form-element.html.twig / input templates that drop `{{ label }}`.

**Why:** Without a programmatic label a screen reader announces only "edit text". Placeholder text disappears as soon as the user types and is not a reliable accessible name. In Drupal, a missing #title makes core skip the label completely (FormPreprocess sets title_display to none).

**Fix:** Drupal: always set `'#title' => $this->t('Search')` and use `'#title_display' => 'invisible'` when it must be visually hidden (it renders a visually-hidden label). React: `const id = useId(); <label htmlFor={id}>Email</label><input id={id} />`, or `aria-label` for icon-only search inputs. Keep placeholder only as an example hint.

**Not a finding when:** `'#title_display' => 'invisible'` is the correct Drupal pattern, not a bug. `'#title_display' => 'attribute'` on checkboxes/radios is core's documented pattern for tables of checkboxes where row and column give context (title tooltip becomes the name), so downgrade to a suggestion there. `#password_confirm` and other composite parents intentionally have no #title because their children carry labels. Hidden inputs (`type="hidden"`, `'#type' => 'hidden'|'value'|'token'`), submit/button elements (`'#type' => 'submit'` uses #value as its name), and `aria-labelledby` pointing at a visible heading are fine. Radios/checkboxes groups in Drupal get their label from the wrapper fieldset legend. A component that receives `label` as a prop and renders `<label htmlFor>` internally is fine, so check the component before flagging its call site.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions.html · https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html · https://api.drupal.org/api/drupal/core%21lib%21Drupal%21Core%21Render%21Element%21FormElementBase.php/class/FormElementBase/11.x · https://www.drupal.org/docs/drupal-apis/form-api/form-render-elements · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/label-has-associated-control.md · https://react.dev/reference/react/useId

### A11Y-04 · Icon-only button or link, svg, or iframe with no accessible name

**Severity:** high · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 4.1.2 (A), 2.4.4 (A), 1.1.1 (A) · **Applies to:** All versions

**Signals:** JSX: `<button` or `<a`/`<Link` whose only child is an icon component (`<XIcon />`, `<svg`, `<FontAwesomeIcon`, `<i className="icon-`) and no `aria-label`, `aria-labelledby`, `title` on svg, or visually-hidden text (`sr-only`, `visually-hidden`). jsx-a11y/anchor-has-content is on in recommended, but control-has-associated-label is OFF in both recommended and strict, so buttons need manual review. `<iframe` without `title=` (jsx-a11y/iframe-has-title, on in recommended), for example YouTube/Maps embeds. Twig: `<a href="{{ url }}"><i class="..."></i></a>` or `<button><svg`. Drupal: `Link::fromTextAndUrl(Markup::create('<svg...'), $url)` or `'#title' => ['#markup' => '<i ...>']` in a `'#type' => 'link'` render array.

**Why:** Close, burger menu, social, search and carousel arrow buttons are the most common unnamed controls. A screen reader announces just "button" or reads the URL, and voice-control users cannot target them.

**Fix:** Add `aria-label="Close dialog"` to the control, or `<span className="sr-only">Close</span>` next to an `aria-hidden="true"` icon. In Twig: `<span class="visually-hidden">{{ 'Close'|t }}</span>`. Give each iframe a descriptive `title`.

**Not a finding when:** An icon next to visible text inside the same button is fine (the icon should then be aria-hidden). Components that accept a required `label` prop and render it as aria-label are fine. Check the component signature. A decorative svg with `aria-hidden="true"` beside text is correct. Drupal core Olivero/Claro templates already contain visually-hidden labels, so only flag changed markup. An svg with `<title>` plus role="img" has a name. Icon-font glyphs (`<i class="fa">`) inside a labelled control are fine.

**Also covers A11Y-02 (Alt text that is present but meaningless, redundant, or wrong for the image's role).** Signals: `alt="image"`, `alt="photo"`, `alt="logo"`, `alt="icon"`, `alt={fileName}`, `alt={src}`, `alt={title}` sitting next to a visible `{title}` caption, alt containing the word "image of"/"picture of" (jsx-a11y/img-redundant-alt). `alt=""` on the only content of a `<a>`/`<Link>`/`<button>` (the link ends up with no name). Drupal config diffs: `alt_field_required: false` or `alt_field: false` in field.field.*.yml for a content image field. Not a finding when: `alt=""` on a card image when the card's link already has visible text is correct. alt equal to a product name can be fine if no visible caption repeats it. Turning off alt_field_required is acceptable for fields that are purely decorative (for example a background/hero pattern), so ask before flagging. Do not judge alt quality on content editors' data. Only literals and mappings in code are in scope. `alt="logo"` on a logo that is the only content of a home link is weak but not empty, so report as a suggestion.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html · https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/control-has-associated-label.md · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/iframe-has-title.md · https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html · https://html.spec.whatwg.org/multipage/images.html#alt · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/img-redundant-alt.md · https://www.drupal.org/node/2461557

### A11Y-05 · Clickable div/span (or li, img, tr) used instead of a button or link

**Severity:** high · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 2.1.1 (A), 4.1.2 (A) · **Applies to:** All versions; Drupal behaviors JS and Next.js client components

**Signals:** JSX: `<div onClick=`, `<span onClick=`, `<li onClick=`, `<img onClick=`, `<tr onClick=` without `role`, `tabIndex`, and a key handler (jsx-a11y/no-static-element-interactions, click-events-have-key-events; both on in recommended, not in eslint-config-next). `router.push(` inside an onClick on a non-link element. Drupal JS: `once('x', '.card', context).forEach(el => el.addEventListener('click'` or jQuery `.on('click'` bound to a div/li class selector. Twig: `<div class="..." data-href=`, or `onclick=` on non-interactive elements.

**Why:** Keyboard and switch users cannot reach or activate the element, and screen readers do not announce it as actionable. When `router.push` sits on a div, the link is also lost for opening in a new tab and for crawlers.

**Fix:** Use `<button type="button">` for actions and `<a href>`/`<Link href>` for navigation. For a whole-card link, put a real link on the title and stretch its clickable area with CSS (`::after { inset: 0 }`) instead of a click handler on the card.

**Not a finding when:** An onClick on a wrapper used only for event delegation from real buttons inside it is fine. So is `onClick` that only stops propagation (e.g. a modal content wrapper) or a backdrop click-to-close when an Escape key and a close button also exist. A div with `role="button" tabIndex={0}` and Enter/Space handling is technically compliant (see A11Y-06), though a native button is still better. Mouse-only enhancements (hover previews) that duplicate a real link are fine. A Drupal 'clickable teaser' behavior that, on click, triggers or follows the card's own real `<a href>` is a progressive enhancement and fine, because keyboard users already have the link. Check that the card contains a real link before flagging.

**Also covers A11Y-07 (Link used as a button (href="#", javascript:void(0), or anchor without href)).** Signals: `<a href="#" onClick=`, `<a href="javascript:void(0)"`, `<a onClick=` with no href, `<Link href="#"` (jsx-a11y/anchor-is-valid, on in recommended). Twig: `<a href="#" class="js-toggle`, `<a href="javascript:`. Drupal: `Url::fromUserInput('#')` or `Url::fromRoute('<none>')` wrapped in a link that JS turns into a toggle. Not a finding when: `href="#main-content"` and other in-page fragment links (skip links, table of contents) are valid navigation. Drupal `<nolink>`/`<button>` menu items rendered by core as `<span>`/`<button>` are fine. An `<a>` without href used purely as a placeholder with no handler is not interactive and is fine.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html · https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/no-static-element-interactions.md · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/click-events-have-key-events.md · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/anchor-is-valid.md

### A11Y-06 · ARIA widget role without the keyboard support or required state it promises

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 2.1.1 (A), 4.1.2 (A) · **Applies to:** All versions

**Signals:** `role="button"` without `tabIndex={0}` and an onKeyDown handling Enter and Space. `role="tab"`, `role="tablist"`, `role="menu"`, `role="menuitem"`, `role="listbox"`, `role="option"`, `role="combobox"`, `role="slider"`, `role="switch"`, `role="checkbox"` added by hand with no arrow-key handling (`ArrowDown`, `ArrowRight`, `Home`, `End`) or missing required state (`aria-selected`, `aria-checked`, `aria-expanded`, `aria-valuenow`) (jsx-a11y/role-has-required-aria-props is on in eslint-config-next; interactive-supports-focus is on in recommended). `tabIndex` greater than 0 (jsx-a11y/tabindex-no-positive). `tabIndex={0}` on non-interactive content (no-noninteractive-tabindex). `role="menu"` on a site navigation `<ul>`. Toggle buttons without `aria-expanded`/`aria-pressed` bound to state.

**Why:** A role tells assistive tech which keys work. If they do not, users get stuck in a control that sounds operable, which is worse than plain HTML. A positive tabindex scrambles tab order across the whole page as components are added.

**Fix:** Prefer native elements (`<button>`, `<input type="checkbox">`, `<details>`, `<select>`). When a custom widget is needed, follow the matching WAI-ARIA APG pattern or use a tested library (Radix, React Aria, Headless UI). Bind state: `<button aria-expanded={open} aria-controls={id}>`. Use a plain `<nav><ul>` for site menus, not role=menu.

**Not a finding when:** Roles rendered by a well-known headless library (Radix, React Aria, Headless UI, Reach, Drupal core dropbutton/tabledrag) already include keyboard handling, so do not flag their output. Landmark and structural roles (`role="navigation"`, `"region"`, `"list"`, `"status"`, `"alert"`, `"img"` with aria-label) need no keyboard support. `tabIndex={-1}` for programmatic focus is correct. `tabIndex={0}` on a scrollable overflow container (code block, table wrapper with overflow: auto) is the recommended way to make it keyboard-scrollable, so do not flag it under no-noninteractive-tabindex.

**Sources:** https://www.w3.org/WAI/ARIA/apg/patterns/ · https://www.w3.org/TR/using-aria/ · https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/interactive-supports-focus.md · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/tabindex-no-positive.md

### A11Y-08 · Focus indicator removed (outline: none / focus:outline-none) with no visible replacement

**Severity:** high · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 2.4.7 (AA); failures F78, F55 · **Applies to:** All versions; CSS/SCSS, Tailwind v3 and v4, CSS-in-JS, Drupal theme CSS

**Signals:** CSS/SCSS: `outline: none`, `outline: 0` on `*`, `:focus`, `a`, `button`, `input`, or a component class, with no `:focus-visible` (or `:focus`) rule for the same element that adds an outline, box-shadow, or border. Tailwind: `outline-none` or `focus:outline-none` with none of `focus-visible:ring-*`, `focus-visible:outline-*`, `focus:ring-*`, `focus:border-*`, `focus:shadow-*` on the same element. In Tailwind v4 `outline-none` means outline-style: none, so it is a genuine removal. `*:focus { outline: none }` in a global stylesheet. JS: `onFocus={e => e.target.blur()}` or `el.blur()` in a focus handler (F55). `-webkit-tap-highlight-color` is unrelated.

**Why:** Keyboard users lose track of where they are on every page that loads the stylesheet. It is a one-line change in a global file with site-wide impact, and regression tests rarely catch it.

**Fix:** Keep the outline, or replace it: `.btn:focus { outline: none } .btn:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }`. In Tailwind: `focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2` (v3), or `outline-hidden focus-visible:ring-2` (v4, keeps a transparent outline for forced-colors mode).

**Not a finding when:** `outline: none` together with a visible replacement (box-shadow ring, border change, background change) on `:focus` or `:focus-visible` is fine, including Tailwind `focus:ring-*`. Check the same selector and any component-level styles before flagging. `:focus:not(:focus-visible) { outline: none }` is a legitimate pattern. `outline: 2px solid transparent` and Tailwind v4 `outline-hidden` are deliberate: the transparent outline shows up in Windows forced-colors mode, and they are normally paired with a ring or box-shadow. Do not flag them on their own. `outline: none` on elements that are never focusable (plain divs without tabindex) or on `tabindex="-1"` programmatic-focus targets like `<main>` or headings is acceptable. Focus styling often lives in a design-system base layer, so grep the repo for `:focus-visible` before flagging a single component.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html · https://www.w3.org/WAI/WCAG22/Techniques/failures/F78 · https://www.w3.org/WAI/WCAG22/Techniques/failures/F55 · https://www.w3.org/WAI/WCAG22/Techniques/css/C45 · https://tailwindcss.com/docs/outline-style

### A11Y-09 · Custom modal, drawer, or off-canvas menu without focus management (initial focus, trap, Escape, return focus)

**Severity:** high · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 2.4.3 (A), 4.1.2 (A); 2.1.2 (A) only if a trap has no keyboard exit · **Applies to:** Next.js client components; Drupal custom JS dialogs (not Drupal.dialog)

**Signals:** New components named Modal/Dialog/Drawer/Lightbox/OffCanvas/MobileMenu rendered with `createPortal(` or conditional `{open && <div className="modal"`, with none of: `ref.current.focus()` in an effect when opened, a Tab-trapping keydown handler or `inert` on the background, an `Escape` key handler, restoring focus to the trigger on close. `role="dialog"` without `aria-modal="true"` and `aria-labelledby`/`aria-label`. Body scroll lock (`overflow: hidden` on body) added with no focus logic. Drupal: jQuery `.fadeIn()`/`.addClass('is-open')` on an overlay div. Using `<dialog>` with `.show()` instead of `.showModal()` for something visually modal.

**Why:** When focus stays behind the overlay, keyboard and screen reader users keep tabbing through hidden page content and cannot reach or close the dialog. When focus is not restored on close, they are dropped at the top of the page.

**Fix:** Use native `<dialog>` with `dialogRef.current.showModal()`, which gives a focus trap, Escape to close and inert background, then return focus to the trigger on close. Alternatively use a tested library (Radix Dialog, React Aria, Headless UI) or `Drupal.dialog()` in Drupal. Label it: `<dialog aria-labelledby="dlg-title">`.

**Not a finding when:** Components built on Radix/Headless UI/React Aria/MUI Dialog, native `showModal()`, or `Drupal.dialog`/`Drupal.ajax` dialogs already handle focus, so check the import before flagging. Non-modal popovers, tooltips and disclosure menus do not need a focus trap (they need Escape and correct aria-expanded). The Next.js intercepting-route modal pattern still needs focus handling in the modal component itself. A trap that includes an Escape or close-button exit is not a 2.1.2 failure.

**Sources:** https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ · https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html · https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html · https://developer.mozilla.org/en-US/docs/Web/HTML/Element/dialog

### A11Y-10 · Client-side view change that is not announced: missing or duplicated page title for the route announcer, or in-page content swap without focus or announcement

**Severity:** low · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 2.4.2 (A), 2.4.3 (A), 4.1.3 (AA) · **Applies to:** Next.js 14-16 App Router (metadata / generateMetadata) and Pages Router (next/head); decoupled Drupal frontends

**Signals:** New `app/**/page.tsx` or dynamic route with no `export const metadata`/`generateMetadata` returning a `title` and no layout title template, so every page gets the same title. Pages Router: new `pages/*.tsx` without `<Head><title>`. `title: 'Home'` or a static title reused on dynamic `[slug]` pages. Multi-step flows, tabs, or filter views that replace the main content via `useState` (`setStep(n)`) without moving focus to the new heading (`headingRef.current?.focus()` with `tabIndex={-1}`). Custom `router.push` + `window.scrollTo(0,0)` with manual focus code that fights the built-in announcer.

**Why:** The Next.js route announcer takes document.title if set, else the first h1, else the pathname, and announces only when that value differs from the previous route's. Identical titles between two routes therefore produce no announcement at all. State-driven step or tab changes do not trigger the announcer either, so screen reader users do not know the content changed.

**Fix:** Give every route a unique title: `export async function generateMetadata({ params }) { const { slug } = await params; return { title: post.title } }` (Next 15+; in Next 14 `params` is not a Promise, so drop the await) plus `title: { template: '%s | Site' }` in the root layout. For step or view swaps inside one route, focus the new step heading: `<h2 ref={ref} tabIndex={-1}>` and `useEffect(() => ref.current?.focus(), [step])`, or announce via a live region (A11Y-11).

**Not a finding when:** Do not ask for manual focus management on ordinary `<Link>` navigation. Next.js already announces route changes, and adding focus code on top can cause double announcements. A title inherited from a layout `title.template` with a page-level `title` is fine, and so is a route that inherits a distinct title from a nested layout. Search-param-only updates (sorting a list) usually need a status message, not a title change. WCAG 2.4.2 asks for a descriptive title, not strictly a unique one, so report identical titles as a medium/low issue.

**Sources:** https://nextjs.org/docs/architecture/accessibility · https://github.com/vercel/next.js/blob/canary/packages/next/src/client/components/app-router-announcer.tsx · https://nextjs.org/docs/app/api-reference/functions/generate-metadata · https://www.w3.org/WAI/WCAG22/Understanding/page-titled.html · https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html

### A11Y-11 · Async update (AJAX results, toast, form result, cart count) with no live region or Drupal.announce

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 4.1.3 (AA) · **Applies to:** Drupal 10/11 AJAX/behaviors and Views exposed filters; React client components in Next.js 14-16

**Signals:** New toast/notification/snackbar components without `role="status"`, `role="alert"` or `aria-live`. Search/filter results rendered after `fetch(`/`useSWR`/`useQuery`/Server Action with a result count or "No results" text and no live region. `useFormState`/`useActionState` success or error message rendered without role=status/alert. Live region that is conditionally mounted together with its message (`{msg && <div aria-live="polite">{msg}</div>}`), which many screen readers miss. Drupal: `AjaxResponse` with `ReplaceCommand`/`HtmlCommand` or custom JS that injects results, with no `Drupal.announce(` call. `Drupal.announce('literal')` without `Drupal.t()`.

**Why:** Sighted users see the change and screen reader users hear nothing, so they do not know a search returned results, an item was added to the cart, or a form failed. It shows up across every page that reuses the component.

**Fix:** Render the live region once and change only its text: `<div role="status" aria-live="polite" className="sr-only">{message}</div>`. Use `role="alert"` only for errors that need immediate attention. In Drupal: `Drupal.announce(Drupal.t('@count results found', {'@count': n}))`, or `MessageCommand` for status messages, which core announces.

**Not a finding when:** Drupal core `MessageCommand`/`Drupal.Message.add()` already announce (Drupal.Message.add calls Drupal.announce unless options.announce is an empty string), so adding a second `Drupal.announce` for the same text double-announces. Libraries such as react-hot-toast and sonner render live regions (check the version or props). Content that loads on first render (not after a user action) does not need an announcement. Do not ask for aria-live on large regions like whole result lists, since announcing only a short summary is the right pattern. `role="alert"` inserted dynamically with its message is announced by most screen readers, so only flag the conditional-mount pattern for `aria-live` regions or as low confidence.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html · https://www.drupal.org/docs/drupal-apis/javascript-api/accessibility-tools-for-javascript-in-drupal · https://github.com/drupal/drupal/blob/11.x/core/misc/message.js · https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/ARIA_Live_Regions

### A11Y-12 · aria-hidden or role=presentation on a focusable element or on a container with focusable children

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 4.1.2 (A), 1.3.1 (A) · **Applies to:** All versions; the `inert` fix needs React 19 (boolean prop) or the string form on React 18

**Signals:** `aria-hidden="true"` or `aria-hidden={true}` on `<a`, `<button`, `<input`, `<Link`, or any element with `tabIndex={0}` (jsx-a11y/no-aria-hidden-on-focusable exists but is in neither recommended nor strict, and not in eslint-config-next). `aria-hidden` on a wrapper (carousel slide, off-canvas menu, collapsed accordion panel, cloned slider items) that still contains links or buttons with no `inert` or `tabIndex={-1}` handling. `role="presentation"`/`role="none"` on a button or link. Twig: `aria-hidden="true"` on `.slick-slide` / menu wrappers toggled by JS.

**Why:** Keyboard focus lands on elements that screen readers say do not exist, so users hear silence or nonsense. Carousels and hidden mobile menus are the usual cause, and the issue repeats on every page that carries them.

**Fix:** Hide inactive content with the `inert` attribute, `hidden`, or `display:none`. In React 19 use `<div inert={!active}>`. In React 18 booleans are not supported (inert={false} warns), so use `inert={active ? undefined : ''}`. Or remove its children from tab order. Put `aria-hidden="true"` only on decorative, non-focusable things like icons.

**Not a finding when:** `aria-hidden` on a decorative `<svg>`/`<i>` inside a named button is correct. Elements also hidden with `display:none`/`visibility:hidden`/`hidden` are fine because they are not focusable. Libraries that pair aria-hidden with `inert` or tabindex=-1 on children (recent Swiper/Embla configs, Radix) are fine. Verify the library version. Using ARIA allows aria-hidden on interactive elements that are neither visible nor interactable and not focusable.

**Sources:** https://www.w3.org/TR/using-aria/ · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/no-aria-hidden-on-focusable.md · https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/inert · https://github.com/facebook/react/pull/24730

### A11Y-14 · Missing or wrong html lang, and content in another language without a lang attribute

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 3.1.1 (A), 3.1.2 (AA) · **Applies to:** Next.js App Router root layout, Pages Router _document; Drupal custom html.html.twig and multilingual Twig

**Signals:** App Router: `app/layout.tsx` or `app/[locale]/layout.tsx` rendering `<html>` with no `lang`, or hardcoded `lang="en"` in a multilingual app that has a `[locale]`/`[lang]` segment or next-intl (should be `lang={locale}`). Pages Router: custom `pages/_document.tsx` `<Html>` without `lang` when next.config has no `i18n` block (jsx-a11y/html-has-lang, on in recommended; jsx-a11y/lang for invalid codes). Drupal: a theme override of html.html.twig that replaces `<html{{ html_attributes }}>` with a literal `<html>` or `<html lang="en">`. Language switcher links whose labels are in the target language (`Deutsch`, `Polski`) without `lang="de"`/`hreflang`. A content block rendering a translation or a quote in a different language than the page without `lang` on its wrapper.

**Why:** Screen readers choose pronunciation from lang. A wrong or missing value makes a Polish page read with English phonetics, which is close to unintelligible, and it affects every page at once.

**Fix:** App Router: `export default async function RootLayout({ children, params }) { const { locale } = await params; return <html lang={locale}>...` (Next 15+; in Next 14 `params` is a plain object, no await). Pages Router: rely on `i18n` config (Next adds lang automatically) or set `<Html lang="pl">`. Drupal: keep `{{ html_attributes }}`, and for switched content `<div{{ attributes.setAttribute('lang', langcode) }}>` or `<a lang="de" hreflang="de">Deutsch</a>`.

**Not a finding when:** Pages Router with `i18n` in next.config already sets `<html lang>`, so do not flag a custom _document without lang there. Drupal core html.html.twig and core themes already output lang via html_attributes. Proper names, technical terms and loanwords do not need lang (3.1.2 exceptions). Single-language sites with a correct hardcoded lang are fine. `output: 'export'` does not support Pages Router i18n routing, so there a missing lang is real.

**Also covers DEC-37 (Page and fallback content language not reflected in lang attributes).** Signals: <html lang="en"> hardcoded in app/layout.tsx or _document.tsx while locales exist; resource langcode ignored Not a finding when: Monolingual sites with the correct static lang. The Pages Router i18n config sets html lang automatically when locales are configured and _document does not override it. Whether Drupal returns default-language content for a missing translation depends on the site (core JSON:API has no language fallback candidates), so the fallback-block check needs the data, not only the diff.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/language-of-page.html · https://www.w3.org/WAI/WCAG22/Understanding/language-of-parts.html · https://nextjs.org/docs/pages/guides/internationalization · https://api.drupal.org/api/drupal/core%21modules%21system%21templates%21html.html.twig/11.x · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/html-has-lang.md · https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module/translations · https://nextjs.org/docs/app/guides/upgrading/version-15

### A11Y-15 · Heading structure broken by a template or component: hardcoded h1 in reusable parts, skipped levels, fake or empty headings

**Severity:** low · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 1.3.1 (A), 2.4.6 (AA) · **Applies to:** Drupal Twig (paragraph, block, view mode, SDC templates); React components in Next.js

**Signals:** Twig: a hardcoded `<h1` inside `paragraph--*.html.twig`, `block--*.html.twig`, `node--*--teaser.html.twig`, `views-view-*.html.twig` or an SDC component, where page.html.twig/page title block already renders the h1. Card or teaser templates using `<h4>`/`<h5>` straight under an `<h2>` section for styling. `<div class="h2">`/`<p class="title">`/`<strong class="heading">` styled to look like a heading. JSX: `<h1>` inside a reusable `Card`/`Hero`/`Section` component, heading tags chosen for font size, `<h2>{title}</h2>` where title may be empty (jsx-a11y/heading-has-content, on in recommended). Removing `{{ title_prefix }}{{ title }}{{ title_suffix }}` heading wrappers from block templates.

**Why:** Screen reader users navigate by headings. Components with hardcoded levels produce multiple h1s or jumps, and the problem multiplies as editors combine components on landing pages.

**Fix:** Let the parent pick the level: a `headingLevel` prop (`const H = \`h${level}\``) in React, or a variable in Twig (`{% set tag = heading_level|default('h2') %}<{{ tag }}>`). Keep one h1 per page from the page title. Style with classes, not heading tags.

**Not a finding when:** A Hero or page-title component that is designed to be the only h1 on the page (used once in the layout) is fine. Drupal core page title block renders the h1, and a node full view mode template often hides the title for that reason, so check both before flagging. Skipping levels and multiple h1s are advisory, not hard WCAG failures. Report as low unless headings are missing entirely or fake headings replace real ones.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html · https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels.html · https://www.w3.org/WAI/tutorials/page-structure/headings/ · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/heading-has-content.md

### A11Y-17 · Autoplaying media, auto-advancing carousels, or motion with no pause control

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 1.4.2 (A), 2.2.2 (A), 1.2.2 (A) · **Applies to:** All versions

**Signals:** `<video autoPlay` / `autoplay` without `muted` (sound plays, 1.4.2). `<video autoPlay muted loop` background video with no pause button (2.2.2 when longer than 5 s). `<audio autoPlay`. Carousel/slider config `autoplay: true`, `autoplay: { delay`, `autoplaySpeed`, Slick `autoplay: true`, Swiper `autoplay`, Embla Autoplay plugin, `setInterval(next` in a slider, with no visible pause/stop control. YouTube/Vimeo embed URLs with `autoplay=1`. `<video` with speech and no `<track kind="captions"` (jsx-a11y/media-has-caption, on in recommended). `<marquee`, `<blink` (jsx-a11y/no-distracting-elements).

**Why:** Unexpected sound drowns out screen readers. Moving content for longer than five seconds without a pause blocks people with attention or vestibular issues. Auto-rotating hero carousels also move content away before keyboard users reach it, and auto-updating content has no 5-second grace period.

**Fix:** Do not autoplay audio. For motion longer than 5 seconds, render a visible pause/play button; pausing on hover and focus is a helpful extra, not a substitute. Respect `prefers-reduced-motion` as good practice (`window.matchMedia('(prefers-reduced-motion: reduce)').matches`). Add `<track kind="captions" src=... srcLang="en">` to videos with speech.

**Not a finding when:** Motion that stops by itself within 5 seconds is fine. Muted decorative video under 5 seconds or non-looping is fine. Loading spinners, skeletons and progress animations are exempt (W3C: a loading animation is not presented in parallel with other content). media-has-caption flags every `<video>`, but silent or decorative video does not need captions. A carousel with autoplay off by default, or with visible pause controls implemented elsewhere in the component, is fine. A missing `prefers-reduced-motion` override on an infinite CSS animation is a best-practice note, not an AA failure (2.3.3 is AAA), so do not report it as a WCAG failure.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html · https://www.w3.org/WAI/WCAG22/Understanding/audio-control.html · https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded.html · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/media-has-caption.md

### A11Y-19 · Drag-only interaction without a single-pointer alternative (2.5.7)

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 2.5.7 (AA) · **Applies to:** All versions

**Signals:** Imports of `@dnd-kit/*`, `react-beautiful-dnd`, `@hello-pangea/dnd`, `react-dnd`, `sortablejs`/`react-sortablejs`, `interactjs`, `Draggable`. `draggable="true"`/`draggable` with `onDragStart`/`onDrop`. Pointer tracking (`onPointerDown` + `onPointerMove`, `onMouseMove` while dragging) for custom sliders, range pickers, crop tools, before/after image comparers, kanban boards, file upload drop zones. Custom range slider built from divs instead of `<input type="range">`. Drupal JS using jQuery UI sortable/draggable in custom modules.

**Why:** People with tremors, head pointers or switch devices cannot press and hold while moving. When reordering or setting a value is drag-only, they cannot do the task at all.

**Fix:** Offer click/tap alternatives next to the drag: up/down or "Move to" buttons for sortable lists, a menu to move a card between columns, click-on-track for sliders (native `<input type="range">` gives this), a "Browse files" button next to a drop zone.

**Not a finding when:** A keyboard alternative alone (dnd-kit KeyboardSensor) meets 2.1.1 but not 2.5.7, which needs a single-pointer alternative. Drupal core tabledrag has "Show row weights" with select lists, which is an acceptable alternative. File drop zones that also have a file input button pass (W3C does not address file drops explicitly, so this is a reasonable reading, not quoted text). Native `<input type="range">` passes because the user agent handles it. Scrolling, panning handled by the browser, and drag used only as an optional shortcut when buttons exist are fine.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html

### A11Y-20 · Interactive target explicitly sized below 24x24 CSS px without enough spacing (2.5.8)

**Severity:** low · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 2.5.8 (AA) · **Applies to:** All versions; CSS/SCSS/Tailwind

**Signals:** Buttons/links/icons given explicit small sizes: `width: 16px; height: 16px`, `20px`, Tailwind `w-4 h-4`/`size-4`/`w-5 h-5`/`h-5` directly on a `<button>`/`<a>` with `p-0`, or `padding: 0` on icon buttons (close X, carousel dots, pagination dots, social icons, tag remove buttons, star ratings). Carousel dot buttons styled `8px`/`10px` circles. Tightly packed icon rows (`gap-0`, `gap-1`) of small links.

**Why:** Small targets cause missed taps for users with limited dexterity and on touch screens. Pagination and carousel dots are the usual offenders and appear site-wide.

**Fix:** Give the clickable element at least 24x24 px, for example by padding the button around a 16px icon: `.icon-btn { min-width: 24px; min-height: 24px; }` or Tailwind `p-1` around `size-4`, or `min-w-6 min-h-6`. Or space small targets so a 24px circle around each does not touch its neighbours.

**Not a finding when:** Size of the icon inside the button is not the same as the target size. Check the button's padding and min size, not the svg. Exceptions per the normative text: spacing (24px circles do not intersect other targets), equivalent control on the same page, inline (target in a sentence or line-height constrained), user agent control not restyled by the author, and essential. This needs rendered sizes to confirm, so report only explicit small sizes on the interactive element itself, as a question.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html · https://www.w3.org/WAI/WCAG22/Techniques/css/C42

### A11Y-22 · Login or OTP field that blocks paste or autofill, or a puzzle CAPTCHA in authentication (3.3.8), and missing autocomplete tokens on personal fields (1.3.5)

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 3.3.8 (AA), 1.3.5 (AA); failure F109 · **Applies to:** Drupal user login/password-reset forms and custom auth forms; Next.js auth pages (NextAuth/Auth.js, custom). Registration and password-change forms are out of 3.3.8 scope.

**Signals:** `onPaste={e => e.preventDefault()}`, `onCopy`/`onCut` preventDefault, or `addEventListener('paste'` returning false on password, OTP or verification code inputs. `autoComplete="off"` or `autocomplete="off"` on login/password/username inputs, or on the login form. Drupal: `hook_form_user_login_form_alter` / `hook_form_alter` setting `'#attributes' => ['autocomplete' => 'off']` on `name`/`pass`. Split OTP inputs (6 separate `maxLength={1}` fields) with no paste handling that spreads the pasted code. Math or text CAPTCHAs (`What is 3 + 4`, distorted text) shown on login or password reset. Missing or invalid tokens on personal fields (jsx-a11y/autocomplete-valid, on in recommended): login should use `autoComplete="username"`/`"current-password"`, sign-up `"new-password"`, OTP `"one-time-code"`, address fields `"street-address"`, `"postal-code"`, `"email"`, `"tel"`.

**Why:** Blocking paste and autofill forces people to memorise or retype passwords and codes, which password-manager users and people with cognitive disabilities cannot do reliably. It fails 3.3.8 (F109) and often weakens security by pushing users to simpler passwords.

**Fix:** Remove paste and autofill blockers. Use correct tokens: `<input type="password" autoComplete="current-password">`, `<input autoComplete="one-time-code" inputMode="numeric">`. For split OTP fields, handle `onPaste` by spreading the digits across fields. For authentication CAPTCHAs use object recognition with a non-cognitive alternative, or invisible/risk-based checks (Turnstile, reCAPTCHA v3).

**Not a finding when:** 3.3.8 does not cover creating a username or account, so paste blocking or CAPTCHA on a registration form is bad practice but not a 3.3.8 failure (W3C says so explicitly). CAPTCHAs on contact, comment or search forms are not authentication either (report as 1.1.1/best practice at most). `autoComplete="off"` on search boxes, one-off coupon codes, or admin configuration fields is not an authentication issue. `autoComplete="new-password"` is correct on registration and password-change forms. Object-recognition and personal-content CAPTCHAs are allowed at AA. Email magic links, passkeys and OS-level authentication need no cognitive test and are fine. Browsers largely ignore autocomplete=off on password fields, so a missing token matters more for 1.3.5 (name/email/address fields) than for login. Flag only authentication steps and personal-data fields.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html · https://www.w3.org/WAI/WCAG22/Techniques/failures/F109 · https://www.w3.org/WAI/WCAG22/Understanding/identify-input-purpose.html · https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/autocomplete-valid.md

### A11Y-23 · Form errors and required state shown only visually, not linked to the field

**Severity:** medium · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 3.3.1 (A), 1.3.1 (A), 4.1.2 (A), 1.4.1 (A) · **Applies to:** React/JSX forms in Next.js 14-16 (react-hook-form, Formik, Server Actions); custom Drupal Twig form templates and client-side validation JS

**Signals:** JSX: `{errors.email && <span className="error">...</span>}` next to an input with no `aria-invalid={!!errors.email}` and no `aria-describedby` pointing at the error id. Required fields marked only with a red `*` or class, with no `required`/`aria-required`. Error summary rendered on submit without focus or `role="alert"`. `noValidate` on the form with custom validation that shows only red borders (color alone, 1.4.1). Drupal: custom form-element Twig overrides that drop `{{ errors }}` or attributes core adds. Custom JS validation in Drupal behaviors that only toggles a CSS class.

**Why:** Screen reader users are not told which field failed or why, and color-only error styling misses users with low vision or color blindness. It repeats on every form built from the shared field component.

**Fix:** `<input id={id} aria-invalid={!!err} aria-describedby={err ? `${id}-error` : undefined} required />` with `<p id={`${id}-error`}>{err.message}</p>`. On submit failure, move focus to the first invalid field or to an error summary with role="alert". In Drupal, use `$form_state->setErrorByName()` and keep core's form-element template variables.

**Not a finding when:** Drupal Form API with `#required` and `setErrorByName` outputs required markers and error messages; core marks invalid fields with aria-invalid (drupal.org/i/2047075), but linking the inline error text to the field through aria-describedby is not something to assume (drupal.org/i/3083103), so do not claim either way for stock core forms. Only custom templates and JS validation need a check. Form libraries or design-system Field components (Radix Form, React Aria TextField, MUI TextField with helperText/error) wire this internally, so check the component before flagging. Native `required` plus browser validation is acceptable.

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html · https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html · https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA21 · https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html · https://www.drupal.org/project/drupal/issues/3083103

### A11Y-24 · Unexpected focus moves or context changes: autoFocus in shared components, select/radio onChange that navigates or submits

**Severity:** low · **Area:** a11y · **Taxonomy:** WCAG 2.2 SC 3.2.2 (A) for onChange submits; 2.4.3 (A) as best practice for autofocus · **Applies to:** All versions

**Signals:** `onChange` on a `<select>` or radio that submits the form or navigates (`router.push` / `form.submit()` / `window.location =` inside onChange) with no submit button (3.2.2 On Input). Drupal: `#ajax` with `'event' => 'change'` that reloads a large part of the page, or JS auto-submitting exposed Views filters on change. `autoFocus` on inputs in page-level or shared components, search bars in headers, or newsletter blocks (jsx-a11y/no-autofocus, on in recommended). Drupal: `'#attributes' => ['autofocus' => 'autofocus']` on non-dialog forms. `useEffect(() => ref.current.focus(), [])` in a component that renders on every page or in a list.

**Why:** Changing context on select change sends keyboard users away before they have picked an option, because arrow keys fire change events in some browsers. Autofocus skips the page heading and landmarks for screen reader users and can scroll the viewport unexpectedly, but WCAG has no explicit failure for page-load autofocus, so it is a best-practice finding.

**Fix:** Trigger navigation or full submits from an explicit button. When auto-apply on change is kept, update results in place, keep focus on the control, and announce the result (A11Y-11). Remove autoFocus except inside a freshly opened dialog or on a page whose only purpose is that input (login, search).

**Not a finding when:** autoFocus inside a modal the user just opened is correct (see A11Y-09). Drupal core's own user login form sets autofocus on the username, so do not flag core output. Drupal core AJAX on change that updates a dependent field in place, without moving focus, is fine. Filter changes that update results in place without navigation are allowed if the user was told beforehand or the change is announced. Focus moved to an inline error or step heading after a user action is correct (see A11Y-10, A11Y-23).

**Sources:** https://www.w3.org/WAI/WCAG22/Understanding/on-input.html · https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html · https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/blob/main/docs/rules/no-autofocus.md

### A11Y-25 · Viewport blocks zoom

**Severity:** medium · **Area:** a11y

**Check:** Viewport that blocks zoom: `<meta name="viewport" content="... user-scalable=no">` or `maximum-scale=1`, and Next.js `export const viewport = { userScalable: false, maximumScale: 1 }` (WCAG 1.4.4 Resize Text, 1.4.10 Reflow). Very detectable from a diff. https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html and https://nextjs.org/docs/app/api-reference/functions/generate-viewport

### A11Y-26 · Skip link or main landmark dropped in a layout override

**Severity:** medium · **Area:** a11y

**Check:** Bypass blocks and landmarks (2.4.1): a new html.html.twig, page.html.twig or app/layout.tsx that drops the skip link or the `<main>` landmark, or duplicate `<nav>`/`<aside>` regions without distinct aria-label. Core html.html.twig already outputs a skip link to #main-content, so only flag overrides. https://www.w3.org/WAI/WCAG22/Understanding/bypass-blocks.html and https://www.w3.org/WAI/ARIA/apg/practices/landmark-regions/

### A11Y-27 · Content revealed on hover only

**Severity:** medium · **Area:** a11y

**Check:** Content on hover or focus (1.4.13, 2.1.1): tooltips, mega menus and dropdowns revealed by CSS `:hover` or `onMouseEnter` only, with no `:focus`/`:focus-within`/`onFocus` equivalent, not dismissable with Escape, or that vanish when the pointer moves onto them. https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus.html

### A11Y-28 · Colour-only meaning or literal low-contrast colours

**Severity:** medium · **Area:** a11y

**Check:** Colour-only meaning and literal low-contrast colours in the diff (1.4.1, 1.4.3, 1.4.11): new hard-coded text/background hex pairs, light-grey placeholder or disabled-looking text tokens, and state shown only by colour (red border for error, green for success) without text or icon. Only literal values are checkable; report the ratio if both colours are literal. https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html and https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html

### A11Y-29 · Data tables without header semantics

**Severity:** low · **Area:** a11y

**Check:** Data table semantics (1.3.1): tables built from divs or grids for tabular data, `<table>` without `<th>` and `scope`, layout tables, and Drupal `#type => 'table'` without `#header`; also `<th>` used for styling only. https://www.w3.org/WAI/tutorials/tables/ and https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html
