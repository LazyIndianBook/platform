# ExamLeaf: accessibility audit (WCAG 2.2 AA)

Manual keyboard and zoom pass, plus axe-core on states Lighthouse does not reach. Measured on 8 October 2026 (IST) on a copy of the working tree at commit `ba0b9dd` (redesign stages 2a and 2b). Nothing under `examleaf-web/` was edited. The Lighthouse side (scores, performance) is in [audit-lighthouse.md](audit-lighthouse.md); Lighthouse's accessibility score is 100 on every page, and everything below is what its automated rules cannot see.

## 1. Result in brief

The markup is in very good shape: one `h1` and no skipped levels on all ten pages, landmarks everywhere, no image without `alt`, no unnamed control, every field labelled with `aria-invalid` and `aria-describedby` after a failed submit, a working skip link, a native `<dialog>` that traps and restores focus, a visible focus ring on every one of the 263 Tab stops measured (lowest contrast 3.58:1), and no animation at all under `prefers-reduced-motion: reduce`. axe-core 4.14 found one violation in 19 page states.

What fails is mostly **layout at narrow widths and a few interaction details**:

| # | Severity | Finding | Pages | WCAG 2.2 |
|---|---|---|---|---|
| F1 | High | The cart table does not fit at 375 px: Copies and Amount are off-screen, and the focused stepper button is 27 of 44 px visible | `/cart/` | 1.4.10, 2.4.7, 2.4.11 (intent) |
| F2 | High | At 320 px (400 % zoom) the header overflows when the cart badge shows (Menu cut off, sideways scroll), and the home hero is 18 px too wide | every page with a cart badge; `/` | 1.4.10 (AA) |
| F3 | High | The toast is fixed to the bottom of a phone screen and entirely covers the focused footer links, coupon field and Apply button | `/cart/` after Add to cart, any page with a message | 2.4.11 (AA) |
| F4 | Medium | Menu is a hidden checkbox: Enter does nothing, no `aria-expanded`, announced as "Menu, checkbox, not checked", Escape does not close it | every page under 900 px | 4.1.2, 2.1.1 |
| F5 | Medium | Home subject strip: keyboard focus lands on a card of which 61 of 274 px are visible; the strip does not scroll | `/` under 768 px (also at 200 % zoom) | 2.4.7, 2.4.11 (intent) |
| F6 | Medium | Toasts are in the page at load inside an `aria-live` list, so most screen readers say nothing; the dismiss control is a `<summary>` ("Dismiss, expanded") | any page with a message | 4.1.3 |
| F7 | Medium | Checkout: the payment-method error is detached from its radios and its summary link goes to `#` | `/checkout/` | 3.3.1, 1.3.1, 4.1.2 |
| F8 | Medium | Every error summary reads "This field is required." once per field, without the field's name | login, register, checkout | 2.4.4, 3.3.1 |
| F9 | Low | Solutions: the marks-table scroll box is focusable with no name or role (axe violation) | `/s/<CODE>/` | 2.1.1, 4.1.2 |
| F10 | Low | `main#main`, the skip link's target, has no `tabindex="-1"` | all | 2.4.1 |
| F11 | Low | Ambiguous links: "Choose a subject" twice on home, "change" twice on My account | `/`, `/account/` | 2.4.4 |
| F12 | Low | Login field "Email or mobile number" uses `autocomplete="email"` | `/account/login/` | 1.3.5 |
| F13 | Low | Text sizes are in `px`, so the browser's default text size is ignored (zoom works) | all | 1.4.4 (advisory) |
| F14 | Low | A few targets are 24 to 43 px (all pass the 24 px minimum): "change" link 51x26, breadcrumb links 34x44, footer links 41 to 43x44 | account, product, footer | 2.5.8 (passes), 2.5.5 (AAA) |

Severity: High = fails an AA criterion or hides part of a core flow (cart, checkout, navigation); Medium = fails in some cases or hurts assistive-technology users; Low = best practice or a pass with a caveat.

## 2. How it was tested

- Pages: `/`, `/account/login/`, `/account/signup/`, `/shop/`, `/shop/physics-sample-papers-2027/`, `/cart/`, `/checkout/`, `/s/PHY-E01/`, `/account/`, `/privacy/`, plus the real 404 page. The cart, checkout, solutions and account pages as a temporary non-staff student (deleted afterwards).
- Server: a snapshot copy of the tree on `runserver` (dev settings, debug toolbar removed, `Cross-Origin-Opener-Policy` off for Lighthouse's sake; see the Lighthouse file). A second, production-like instance served the 404 page.
- Browsers: the Claude browser pane (Chrome 152 with a 375x812 and a 320x640 viewport) with real key presses for the Tab, Enter, Space and Escape checks that matter; and headless Chrome 154 driven by Puppeteer for the repeatable walks, with a probe after every Tab press that records the focused element, its accessible name and role (from Chrome's accessibility tree), its box, whether anything covers it (`elementFromPoint`), its outline and the ring's contrast against the background behind it.
- 375 px wide, 2x, unless stated. Zoom: 640 px wide as the proxy for 200 % of a 1280 px window; 320 px for 400 % (WCAG 1.4.10).
- Reduced motion: `prefers-reduced-motion: reduce` emulated through the DevTools protocol (`matchMedia` cannot be toggled from script), plus a walk through every rule of the stylesheet.
- axe-core 4.14.0 (wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa and best-practice rules) on the ten pages at 375 px, home, shop and product at 1280 px, and on states: menu open, Remove dialog open, login, register and checkout after an invalid submit (nothing was saved: no account, no order), cart with a toast.
- Not covered: a real screen reader (VoiceOver, NVDA, TalkBack): announcements below are inferred from Chrome's accessibility tree and ARIA semantics; Safari and Firefox; orders and order pages, invoices, the `/learn/` player, the admin, emails.
- Evidence images are in [audit-evidence/](audit-evidence/).

## 3. Findings

### F1. Cart table does not fit at 375 px (High)

- Page: `/cart/`. Element: `div.table-wrap > table.cart-table`. `static/css/site.css` line 987 gives the table `min-width: 560px` and `.line` `min-width: 260px`; the scroll box is 341 px wide at 375 px. Only the Book column and the first 27 px of the stepper show; the Copies box and the Amount are behind a horizontal scroll with no cue beyond a thin scrollbar. See [a11y-cart-375-clipped.jpg](audit-evidence/a11y-cart-375-clipped.jpg).
- Keyboard: in these tests Chrome scrolled a scroll box to reveal a focused element only when the element was **entirely** outside it. "One copy fewer" (x=348, 44 px wide) is focused with 27 px showing and `.table-wrap.scrollLeft` stays 0; the next stop, the Copies box, is fully hidden so the box scrolls then. Same result in Chrome 152 (real key presses) and 154 headless.
- WCAG: 1.4.10 Reflow (the data-table exception is arguable for a cart; it is a usability failure either way), 2.4.7 Focus Visible and 2.4.11 Focus Not Obscured (the ring is cut off; strictly "not entirely hidden", so a failure of intent).
- Fix: below about 640 px lay each cart line out as a card instead of a scrolling table (book on the first row, copies and amount on the second), keeping the table semantics with explicit `role="table|row|cell"` if `display` is changed. As a cheap safety net for every scroll box on the site, add to `static/js/site.js`:
  ```js
  document.addEventListener("focusin", (e) => {
    if (e.target.closest(".tiles-strip, .table-wrap, .table-scroll")) e.target.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  ```
  Verified in the browser: with this handler the stepper button and the second home tile are fully visible when focused.

### F2. Reflow at 320 px: header and home hero (High)

- Pages and elements: (a) every page while the cart badge shows, which is any visitor with something in the cart (checked on cart, checkout, solutions and account): `header.nav > .container` holds brand (154 px) + cart link (66) + Menu (99) + gaps = 335 px in a 288 px box at 320 px. `label.nav-toggle` ends at x=352, the page scrolls sideways by 32 px and the button reads "Men" ([a11y-header-320-menu-clipped.jpg](audit-evidence/a11y-header-320-menu-clipped.jpg)). At 375 px the row has 8 px to spare, so 1.4.12 text-spacing overrides push it 4 px wide on the same pages. (b) Home at 320 px: `p.hero-eyebrow`, `h1`, `div.hero-count`, `p.lead`, `a.btn` and `div.stage` all end at x=330 (scrollWidth 338); "Buy the books" is cut off ([a11y-home-320-hero-overflow.jpg](audit-evidence/a11y-home-320-hero-overflow.jpg)). Cause, found by trial: at 899.98 px and below `.hero-grid` becomes a column but keeps `flex-wrap: wrap`, so its single line is as wide as the widest item (the cover fan, about 314 px) and every child is stretched to that width.
- WCAG: 1.4.10 Reflow (AA, vertical scrolling content at 320 CSS px must not need two-dimensional scrolling).
- Fixes, each checked in the browser (scrollWidth equals the viewport width afterwards):
  - Header: under 340 px hide the wordmark, `@media (max-width: 339.98px) { .nav .brand > span { display: none } }` (the link keeps `aria-label="ExamLeaf home"`); or hide the words "Menu" and "Close" there; or let the brand shrink (`.nav .brand { min-width: 0; overflow: hidden }`).
  - Home hero: `@media (max-width: 899.98px) { .hero-grid { flex-wrap: nowrap } .stage { overflow-x: clip } }` gives scrollWidth 320 at 320 px, 375 at 375 px and no change at 768 px.
- The other pages (login, register, shop, product, privacy) pass at 320 px.

### F3. Toast covers focused elements on phones (High)

- Page: any page showing a message, most often `/cart/` right after Add to cart. Element: `ul.toast` (`position: fixed`, bottom of the viewport under 768 px, 114 px tall, no timeout). Nothing reserves its space when focus scrolls into view (the product page's `.buybar` does: `scroll-padding-bottom: 120px`).
- Evidence: tabbing from the top of `/cart/` with the toast showing, "Privacy" and "Terms" (footer) are 5/5 sample points covered, the footer brand link 5/5, "Contact", the coupon box and Apply 4/5. In the Claude browser the real Tab path put "Privacy" at y=705 to 749 under a toast at 682 to 796 ([a11y-toast-covers-focused-footer-link.jpg](audit-evidence/a11y-toast-covers-focused-footer-link.jpg)). On desktop (toast top right) nothing is covered.
- WCAG: 2.4.11 Focus Not Obscured (Minimum) (AA, new in 2.2).
- Fix, verified (no covered stop afterwards): `@media (max-width: 767.98px) { html:has(.toast) { scroll-padding-bottom: 140px } }`. Optionally let the toast time out or sit above the content instead of over it.

### F4. Menu is a hidden checkbox (Medium)

- Pages: all, under 900 px. Element: `input#nav-check.nav-check[aria-label=Menu][aria-controls=site-menu]` with the visible `label.nav-toggle` (`aria-hidden`).
- Evidence (real key presses in Chrome 152): the third Tab reaches it (the focus ring is drawn on the label, 8.2:1). **Enter does nothing; Space opens it** and the label turns into "Close"; **Escape does not close it** and focus stays where it was. Chrome's accessibility tree: role `checkbox`, name "Menu", checked false, no `aria-expanded`. Tab order while open is right (Shop, Find your order, Log in, Register, then the page).
- WCAG: 4.1.2 Name, Role, Value (a disclosure announced as a checkbox; `aria-expanded` is not allowed on a checkbox); 2.1.1 Keyboard is met through Space only.
- Fix (not tested): keep the CSS-only checkbox as the no-JavaScript path; in `static/js/site.js` hide it and its label and insert a real `<button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-menu">` that flips the checkbox, mirrors `aria-expanded`, closes on Escape and returns focus to the button. Enter and Space then both work and the state is announced.

### F5. Home subject strip: focus on a mostly hidden card (Medium)

- Page: `/` under 768 px, which includes 200 % zoom of a desktop window (640 px). Element: `div.tiles.tiles-strip > a.tile` (`overflow-x: auto; scroll-snap-type: x mandatory`, tiles 80 % wide). With the keyboard, the Physics tile is fully visible, Chemistry has 61 of 274 px showing (`scrollLeft` 0), Mathematics is scrolled fully into view, Biology again shows 61 px. Same cause as F1: Chrome only scrolls when the element is entirely hidden. Turning snapping off does not change it. [a11y-home-tile-focus-offscreen.jpg](audit-evidence/a11y-home-tile-focus-offscreen.jpg)
- WCAG: 2.4.7, 2.4.11 (intent).
- Fix: the `focusin` handler of F1 (verified: Chemistry then sits at x=16, fully visible), or stack the four tiles in a 2x2 grid on phones instead of a strip.

### F6. Toasts are not announced reliably (Medium)

- Pages: any with a message. Markup: `<ul class="toast" aria-live="polite"><li><details class="toast-item success" open><summary class="btn btn-ghost btn-icon" aria-label="Dismiss">...</summary>...<p>Name is in your cart.</p></details></li></ul>`, rendered by the server before `<main>`.
- A live region announces changes after it exists; text that is already inside it when the page loads is usually not read. The dismiss control's role in Chrome is a disclosure triangle named "Dismiss", "expanded". Enter and Space both collapse it (checked), so it is operable.
- Order: in the page the toast comes straight after the header, so on a phone Tab goes from the header to the toast at the bottom of the screen and back to the top of the content. Acceptable for a message that is announced first, which is one more reason to give it a role.
- WCAG: 4.1.3 Status Messages (AA).
- Fix: put `role="status"` on each `<li>` for success and info and `role="alert"` for error and warning (and drop `aria-live` from the `ul`), or inject the messages after load; rename the control "Dismiss message".

### F7. Checkout: payment-method error is detached (Medium)

- Page: `/checkout/` after a submit with nothing chosen. The error summary has one link, `<a href="#">This field is required.</a>`; the `fieldset.choice` has no `aria-describedby`; the error `<p class="field-error">` has no `id`; the radios carry `aria-invalid="true"`. Django leaves `id_for_label` empty for a radio group, so `_form_errors.html` builds `href="#"`. Every other field on this page and on login and register is wired correctly (`aria-describedby` resolves to the error text, the summary link resolves to the field).
- WCAG: 3.3.1 Error Identification, 1.3.1, 4.1.2, 2.4.4.
- Fix: in `templates/_form_errors.html` link to `#{{ field.auto_id }}_0` for radio groups (or to the fieldset's id); in `templates/shop/checkout.html` give the payment error an `id` and add `aria-describedby` to the `<fieldset>`.

### F8. Error summaries do not name the field (Medium)

- Pages: login (password form), register, checkout. `templates/_form_errors.html` prints `<a href="#id_x">{{ error }}</a>`, so the list reads "This field is required." six times ([a11y-checkout-error-summary.jpg](audit-evidence/a11y-checkout-error-summary.jpg)). Each field's own error, beside it, is fine; the summary is what a screen-reader user lands on first.
- WCAG: 2.4.4 Link Purpose, 3.3.1.
- Fix: `<a href="#{{ field.id_for_label }}">{{ field.label }}: {{ error }}</a>`. Moving focus to the summary after a failed submit (it has `role="alert"`, which is read on load) is optional.

### F9 to F14 (Low)

- **F9** `div.table-scroll` inside `#q-2n > .solution` on `/s/PHY-E01/` (axe `scrollable-region-focusable`; Chrome makes the box focusable on its own, Safari does not; the stop has no role or name). Fix: `tabindex="0" role="region" aria-label="Marking scheme"` on `.table-scroll`.
- **F10** `<main id="main">` in `templates/base.html`: add `tabindex="-1"`. Today, activating the skip link scrolls to `#main` and the next Tab lands inside `main` (checked), but the active element stays `body`, and Safari and older Firefox may not move the reading position.
- **F11** `templates/home.html` has two "Choose a subject" links to `/shop/` (Sample Papers and Solutions cards); `templates/my_account.html` has "change" for the email and for the password. Add `aria-label="Choose a subject: Sample Papers"`, `aria-label="Change email"` or hidden text.
- **F12** `templates/account/login.html`: with SMS on, `id_login` is labelled "Email or mobile number" but carries `autocomplete="email"` (allauth's default); pass `form.login|attr:"autocomplete:username"` to `_field.html` like the other fields do.
- **F13** Body text is `font: 400 17px/1.7` and most sizes are `px`. Browser zoom works (checked with 640 px and 320 px viewports), but a larger default text size set in the browser, Android or iOS has no effect. Use `rem` for body and heading sizes.
- **F14** Smallest targets, all at least 24 px: "change" link 51x26, breadcrumb links 34x44, footer "About" 43x44 and "Terms" 41x44. The 22x22 native checkboxes and radios sit inside labels that are far larger. Raising the 26 px link to 44 px is cheap (`min-height: 44px`).

## 4. Checked and fine

| Check | Result |
|---|---|
| Focus order | Sensible on all ten pages: skip link, brand, (cart), Menu, content in reading order, footer. The only backwards jumps are footer columns. Date inputs take four Tab presses (day, month, year, picker), as expected. |
| Focus visible | An indicator on every one of the 263 stops (outline 2 px, offset 2 px). Ring contrast against the background behind it: lowest 3.58:1 (home tiles and product page), 3.94:1 or more everywhere else, 8.2:1 on the night header. The Menu's ring is drawn on its label. |
| Nothing under the sticky header | The header is `position: relative`, not sticky: nothing sits over the top. The things that can cover focus are the fixed toast (F3) and the product page's sticky buy bar, which `scroll-padding-bottom: 120px` handles (no covered stop found). |
| Skip link | First Tab on every page, 176x49 px at top left with a ring (see [a11y-skip-link-first-tab.jpg](audit-evidence/a11y-skip-link-first-tab.jpg)); Enter goes to `#main` and the next Tab is inside `main` (F10 for the caveat). |
| Remove dialog (`/cart/`) | Native `<dialog>` with `aria-labelledby`: focus moves to Close, Tab and Shift+Tab stay inside (the browser's own UI is the only other stop), the page behind is covered and inert, Escape closes it and focus returns to the Remove button; "Keep it" does the same ([a11y-cart-dialog.jpg](audit-evidence/a11y-cart-dialog.jpg)). Without JavaScript the Remove button just submits. |
| Form errors | After an invalid submit of login, register, checkout and the coupon box: every invalid control has `aria-invalid="true"` and `aria-describedby` naming its help and error text (all ids resolve), the summary has `role="alert"` and working links. Exceptions: F7, F8. Required fields have `required`; the asterisk is `aria-hidden`. |
| Toasts | `aria-live="polite"` is present but see F6. Dismiss works with Enter and Space. |
| Headings | One `h1` per page, no skipped level, none empty: home h1 then h2 and h3; shop h1, h2, h3 for products; account has h2 sections and an h3 for Addresses; footer headings are h2. |
| Landmarks | banner, `nav` "Main", `main`, contentinfo on every page; `nav` "Breadcrumb" on product and solutions; `aside` labelled "Summary", "Your order", "On this paper"; My account has labelled regions. |
| Images | No `img` without `alt`. Covers on home and product have text ("Cover of ..."); decorative ones (tiles, cart and card thumbnails, the cover fan) have `alt=""`. All icons are `aria-hidden`. |
| Names of icon-only controls | Zero unnamed interactive nodes in Chrome's accessibility tree on all ten pages: "ExamLeaf home", "Cart, 1 book", "Menu", "Dismiss", "Close", "One copy fewer", "One copy more". |
| 200 % zoom (640 px) | No sideways scroll and no clipped text on any of the ten pages. Clipped boxes found are by design (the cover that bleeds out of a tile, step words hidden visually at narrow widths). 320 px: see F2. |
| Text spacing (1.4.12) | Line height 1.5, letter spacing .12em, word spacing .16em: no clipped text on any page; a 4 px sideways overflow on the pages with a cart badge (F2). |
| Reduced motion | Every `animation` and `transition` rule (eight) and `@view-transition` sits inside `@media (prefers-reduced-motion: no-preference)`. With `reduce` emulated: 0 running animations and 0 elements with a transition or animation on all ten pages, against 1 to 19 elements with `no-preference`. Hover on `.stage-cover`, `.card-interactive` and `.btn` starts a transition only with `no-preference`. Still instant under `reduce`: `.btn:active { translate: 0 1px }` and the accordion chevron's rotation (states, not motion). Nothing animates by itself, and no scroll-behavior is set. |
| Contrast beyond axe | axe leaves the home hero "needs review" (gradient). Sampling the rendered pixels behind every text element at 375 and 1280 px: lowest 5.07:1 (white on the green "Easy" chip), muted text on the hero 7.3:1 (needs 4.5:1), large numerals 7.8:1 or more. |
| Target size | All targets at least 24x24 px (2.5.8); see F14. |
| Autocomplete (1.3.5) | `name`, `email`, `tel-national`, `address-line1`, `address-line2`, `address-level1`, `address-level2`, `postal-code`, `bday`, `new-password`, `current-password`, `one-time-code` (first of the six code boxes); F12 for the one exception. |
| Accessible authentication (3.3.8) | Log-in by code: from `static/js/account.js` and the template, the six boxes take a pasted code and the first has `autocomplete="one-time-code"`; passkey and password are alternatives (Google too when its keys are set). Not exercised with a real code. |
| Language | `<html lang="en">` on every page; no Bengali or Assamese text found on these pages, so no `lang` on parts was needed. |
| Titles | Unique and specific on every page ("Log in", "Register", "Your cart", "Checkout"...). |
| 404 page (production-like) | h1 "We could not find that page", four landmarks, axe: no violations. |

## 5. Record per page

| Page | Tab stops | First Tab stop | Lowest focus-ring contrast | Headings (h1, then levels used) | axe 4.14 at 375 px |
|---|---:|---|---:|---|---|
| `/` | 33 | Skip to the content | 3.58:1 | "Sample papers with free solutions"; h1 h2 h3 | no violations |
| `/account/login/` | 22 | Skip to the content | 3.94:1 | "Log in"; h1 h2 | no violations |
| `/account/signup/` | 12 | Skip to the content | 3.94:1 | "Register"; h1 h2 | no violations |
| `/shop/` | 29 | Skip to the content | 3.94:1 | "Buy the books"; h1 h2 h3 | no violations |
| `/shop/physics-sample-papers-2027/` | 28 | Skip to the content | 3.58:1 | "ExamLeaf Physics Sample Papers 2027"; h1 h2 h3 | no violations |
| `/cart/` (signed in) | 27 | Skip to the content | 3.94:1 | "Your cart"; h1 h2 | no violations |
| `/checkout/` (signed in) | 30 | Skip to the content | 3.94:1 | "Checkout"; h1 h2 | no violations |
| `/s/PHY-E01/` (signed in) | 30 | Skip to the content | 3.94:1 | "Physics: solutions"; h1 h2 | scrollable-region-focusable (1) |
| `/account/` (signed in) | 36 | Skip to the content | 3.94:1 | "My account"; h1 h2 h3 | no violations |
| `/privacy/` | 16 | Skip to the content | 3.94:1 | "Privacy Policy"; h1 h2 | no violations |

axe-core 4.14.0 on states (375 px unless stated). "Needs review" are items axe cannot decide: colour over gradients or images (the home hero was checked by pixel sampling), the `select` boxes with an arrow image, the decorative cover placeholders, KaTeX's glyphs, and the shop's subject-filter labels (checked by hand: 13.4:1 selected, 5.55:1 not).

| State | Violations | Needs review |
|---|---|---|
| home at 375 | none | color-contrast (12) |
| login at 375 | none | none |
| signup at 375 | none | color-contrast (2) |
| shop at 375 | none | color-contrast (27) |
| product at 375 | none | none |
| cart at 375 | none | none |
| checkout at 375 | none | color-contrast (1) |
| paper at 375 | scrollable-region-focusable (1) | color-contrast (288) |
| account at 375 | none | none |
| privacy at 375 | none | none |
| home at 1280 | none | color-contrast (12) |
| shop at 1280 | none | color-contrast (25) |
| product at 1280 | none | none |
| home at 375 menu open | none | color-contrast (12) |
| cart at 375 dialog open | none | color-contrast (1) |
| login at 375 errors | none | none |
| signup at 375 errors | none | color-contrast (2) |
| checkout at 375 errors | none | color-contrast (1) |
| cart at 375 toast | none | color-contrast (1) |

## 6. Reproduce

Copy the tree, start `runserver --noreload` with a settings wrapper that removes `debug_toolbar` and sets `SECURE_CROSS_ORIGIN_OPENER_POLICY = None`, create a throwaway student and a session with `Client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")`, then use Chrome at 375 px: Tab from the top of each page. The fixes marked "verified" were injected through `<style>` and a `focusin` listener on the live page and measured with `scrollWidth`, `getBoundingClientRect` and `elementFromPoint`.
