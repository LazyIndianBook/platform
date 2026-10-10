# ExamLeaf Next.js frontend: accessibility audit (WCAG 2.2 AA)

![Component](../assets/badges/component-website.svg) ![Status](../assets/badges/status-archive.svg) ![For developers](../assets/badges/audience-developers.svg)

The accessibility audit (WCAG 2.2 AA) of the Next.js frontend at Phase 8D's build half, 8 October 2026: axe on 38 pages
and states, and a manual keyboard, zoom and motion pass. It is kept as a record; Phase 8F worked through its findings
(the [Changelog](../../examleaf-web/CHANGELOG.md), "Phase 8F review fixes").

Automated checks (axe-core) on 38 pages and states, and a manual keyboard, zoom and motion pass with real key presses. Measured on 8 October 2026 (IST) on the production build of `examleaf-frontend/` at commit `b10bde1` (Phase 8D build half). Nothing under `examleaf-frontend/` or `examleaf-web/` was edited. The scores and bytes are in [audit-nextjs-lighthouse.md](audit-nextjs-lighthouse.md) (Lighthouse's accessibility score is 100 on every page and in every run; everything below is what its rules cannot see), the security review in [audit-nextjs-security.md](audit-nextjs-security.md). The Django site's pass is [audit-accessibility.md](audit-accessibility.md); its findings F1 to F14 are cited where the same fault came across to the new frontend.

**Contents**

- [1. Result in brief](#1-result-in-brief)
- [2. How it was tested](#2-how-it-was-tested)
- [3. Findings](#3-findings)
- [4. Checked and fine](#4-checked-and-fine)
- [5. Record per page](#5-record-per-page)
- [6. Not testable here](#6-not-testable-here)
- [7. How to re-run](#7-how-to-re-run)

## 1. Result in brief

The markup is in good shape: one `h1` and no skipped heading level on all 38 pages, landmarks everywhere, no image without `alt`, no interactive node without a name in Chrome's accessibility tree, every one of the 73 form controls labelled, no duplicate id and no broken `aria-*` reference, a skip link that works and puts focus in `main`, focus moved to the new page's `h1` after a client-side navigation, a visible focus ring on every one of the 867 Tab stops walked (lowest contrast 3.58:1), forms whose errors are named, linked and focused, an OTP field that is one real input, a toast region that exists before its messages, and no motion at all under `prefers-reduced-motion: reduce`. axe-core 4.14 reports violations of two rules only, on 6 of the 38 pages (section 5).

What fails is **behaviour and layout that automated rules do not see**. Of the Django audit's faults the home hero at 320 px (F5), the text-spacing overflow beside the cart badge (F11) and the strips that do not scroll to the focused item (F8) came across; the toast that covered focused links was fixed, and the Menu's tab order, right on the Django site, is wrong here (F3). The serious ones are new:

| # | Severity | Finding | Pages | WCAG 2.2 |
|---|---|---|---|---|
| F1 | High | Keyboard focus is thrown to the top of the page after every inline action: the cart's copies stepper loses focus on each press (the next Enter does nothing), and so do Remove's dialog, Save my details, Delete my account, Add an address and the toast's Dismiss | `/cart/`, account pages, any page with a busy button | 2.4.3 (A), 2.1.1 (A) |
| F2 | High | `/shop/` is 583 px wide at every phone width (320 to 414): the subject tabs' `<fieldset>` cannot shrink, so the page scrolls sideways | `/shop/` | 1.4.10 (AA) |
| F3 | High | With the menu open, Tab from the Menu button skips the menu: its links come before the button in the page and are reached only with Shift+Tab | every page under 900 px | 2.4.3 (A), 1.3.2 (A) |
| F4 | High | The "added to cart" toast is dismissed about 300 ms after it appears (the navigation it was raised for clears it), so no one sees or hears it; same for "Saved to your record." | product page, edit marks | 4.1.3 (AA) |
| F5 | Medium | The home page is 338 px wide at 320 px (the hero), as in the Django audit | `/` | 1.4.10 (AA) |
| F6 | Medium | Dialogs: the cart's Remove does not give focus back (Escape, Keep it, a click outside: focus goes to the page start); at 320 × 256 (400 % zoom) both dialogs are cut off at the top and bottom and do not scroll | `/cart/`, order page | 2.4.3 (A), 1.4.10 (AA) |
| F7 | Medium | The 30 paper cards of every book page have an accessible name that leaves out their visible "70 marks · 3 hours" (axe `label-content-name-mismatch`, serious) | `/books/<slug>/` | 2.5.3 (A) |
| F8 | Medium | Keyboard focus lands on a card or chip that is mostly outside the scrolling strip, which does not scroll to it (home tiles: 61 of 274 px visible; account navigation chips) | `/`, every account page | 2.4.7 (AA), 2.4.11 (AA, intent) |
| F9 | Medium | Error messages that are not tied to a field or not announced: login with nothing typed, the coupon box, summary links without a field name; the checkout form uses the browser's own validation | login, `/cart/`, `/checkout/` | 3.3.1 (A), 4.1.3 (AA), 2.4.4 (A) |
| F10 | Low | axe's `scrollable-region-focusable` on 40 to 42 solution blocks (a false positive of `content-visibility: auto` with `overflow-x: auto`) and one real one: the revision tables' scroll boxes | `/s/<code>/`, `/revision/` | 2.1.1 (A) |
| F11 | Low | Text spacing and 320 px: the Menu button overflows by 4 px on every page with a cart badge; the cart's total by 2 px at 320 px | cart badge pages, `/cart/` | 1.4.12 (AA), 1.4.10 (AA) |
| F12 | Low | The 404 page's title changes after load ("ExamLeaf · ExamLeaf"; "Your order" on an unknown order link) | 404 pages | 2.4.2 (A) |
| F13 | Low | Toasts: the Dismiss button is 20 × 20 px, an obsolete toast stays beside the newer one, the region is last in the page | any toast | 2.5.8 (AA), 4.1.3 |
| F14 | Low | Smaller: `aria-labelledby` on a plain `div`; a re-authentication message that asks a password-less account for its password; the cover fan's tab order against its visual order; indistinguishable device rows | checkout, account pages, `/` | 4.1.2, 3.3.x, 2.4.3 |

Severity: High = a keyboard or small-screen user cannot do a core thing or the page breaks; Medium = fails in some cases or hurts assistive-technology users; Low = best practice or a pass with a caveat.

## 2. How it was tested

- **Pages (38 pages and states).** Anonymous: `/`, `/about/`, `/books/physics-2027/`, `/shop/`, the Physics product, `/shop/school-orders/`, `/orders/lookup/`, `/contact/`, the four legal pages, `/revision/`, `/s/PHY-E01/` (the open sample) and `/s/PHY-E02/` (the register wall), `/account/login/`, `/account/signup/`, `/account/password/reset/`, the 404, `/offline/`, `/c/<token>/` and `/orders/t/<token>/` with unknown tokens. Signed in (`*`): `/account/`, `/account/record/`, `/account/orders/`, one order, `/account/details/`, `/account/addresses/`, `/account/security/`, `/account/2fa/`, `/account/privacy/`, `/account/teacher/`, `/cart/`, `/checkout/`, one pay page, `/revision/`, both papers. The signed-in pages as a temporary non-staff student, logged in through the frontend's own email-code form; one order (awaiting payment), one saved address, one marks attempt and a cart existed; all were deleted at the end.
- **Engines.** axe-core 4.14.0 (the engine of `@axe-core/cli`, driven through Puppeteer 25.12 so that states could be reached; nothing was downloaded) with the rule tags wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa and best-practice, at 375 px; Lighthouse 13.5's accessibility category; Chrome's accessibility tree for names and roles (zero unnamed interactive nodes); a **probe after every Tab press** that records the focused element, its accessible name and role, its box, whether the viewport shows all of it, whether another element covers it (`elementFromPoint` at five points), its outline and the ring's contrast against the background behind it.
- **Browsers.** Headless Chrome 154 (real key events through the DevTools protocol: Tab, Shift+Tab, Enter, Space, Escape, typing) for every repeatable walk, and the Claude browser pane (a second Chromium, real key presses, 375 × 812 mobile emulation) to confirm F1 (the cart stepper), F3 (the menu's order) and F2 (the shop's width). Not covered: a screen reader (VoiceOver, NVDA, TalkBack): announcements below are inferred from the accessibility tree and ARIA semantics; Safari and Firefox.
- **Sizes and states.** 375 px wide at 2x unless stated; 640 px as the proxy for 200 % zoom of a 1280 px window and 320 px for 400 % (WCAG 1.4.10); 320 × 256 for a dialog at 400 %. Reduced motion emulated through the DevTools protocol. The contact form was reached by starting the backend with `SUPPORT_EMAIL` set (the frontend shows no form while the support address is empty); the clip player could not be exercised (section 6).
- **Servers.** The frontend: the production build of 16:38 (standalone output, port 3003) for every test. The backend on 8103: the process of the Lighthouse runs until about 17:05, then a restart with `SUPPORT_EMAIL` set (the tree after the Django pages were removed at 16:59, commit `b6b8d06`), and from 17:46 a snapshot of `git HEAD` (`3c37394`) because another agent's unfinished edit made the working tree fail to start. The API and allauth paths the frontend uses were the same in all three.
- **Evidence images** are in [audit-evidence-nextjs/](audit-evidence-nextjs/).

## 3. Findings

### F1. Focus is thrown to the top of the page after every inline action (High)

- **Where.** The copies stepper of `/cart/` (`CopiesStepper` buttons "One copy fewer/more of …"): with the keyboard on "One copy more of ExamLeaf Physics Sample Papers 2027", Enter takes the copies from 1 to 2 and `document.activeElement` is `body`; a second Enter changes nothing because nothing has focus. Reproduced in headless Chrome and, with real key presses, in the Claude browser pane (2 to 3, then `BODY`, a second Enter left it at 3). The user must Tab from the top of the page again for each copy; a screen-reader user is returned to the start of the document.
- **Same fault elsewhere.** Save my details (`/account/details/`), Delete my account (the form is replaced by the "will be deleted" alert), Add an address (the form opens, focus is on `body`), the toast's Dismiss, Download my data, Apply (coupon), and the cart's Remove dialog, also after a confirmed removal (F6): after each, `document.activeElement` is `body`.
- **Cause.** `Button` turns `busy` into `disabled` (`src/components/ui/button.tsx`: `disabled={disabled || busy}`) and the cart disables every control while a call is in flight (`disabled={busy !== null}` on the steppers, the number box and Remove). A button that becomes disabled while it has focus loses it, and nothing puts it back.
- **WCAG.** 2.4.3 Focus Order (A), and 2.1.1 Keyboard (A) for the repeated operation.
- **Fix.** Do not disable the control that has focus: use `aria-disabled="true"` plus `aria-busy` and ignore the click while busy (a CSS `:disabled`-like look through `aria-disabled:`), which `Button` already styles; or keep `disabled` and restore focus (`ref.current?.focus()`) in `finally`. For forms that replace themselves (Add an address, Delete my account) move focus to the new content's heading or first field.

### F2. `/shop/` scrolls sideways at every phone width (High)

- **Where.** `/shop/`: `document.documentElement.scrollWidth` is **583 px** at 414, 390, 375, 360, 340 and 320 px wide (the viewport stays 375). The subject tabs (`src/components/ui/tabs.tsx`) are a `<fieldset>` around a `div.flex.overflow-x-auto`; a fieldset's `min-width` is `min-content`, so it grows to its 567 px of tabs and the row's own scrolling never starts (`scrollWidth` 567, `clientWidth` 567); the page absorbs the overflow. A phone shows the left 375 px and the user can pan into blank space (the browser lets them zoom out to the 582 px layout). Evidence: [shop-375-sideways-scroll.jpg](audit-evidence-nextjs/shop-375-sideways-scroll.jpg) (the red line is the viewport's edge). The Django page had its tabs scrolling inside their own box.
- **WCAG.** 1.4.10 Reflow (AA): at 320 CSS px vertical-scrolling content must not need horizontal scrolling.
- **Fix.** `min-w-0` (or `min-width: 0`) on the `<fieldset>` in `Tabs`, so that the row scrolls inside itself; check that the checked tab is scrolled into view.

### F3. The opened menu is skipped by Tab (High)

- **Where.** Every page under 900 px, `Drawer` in `src/components/ui/drawer.tsx`: the `<nav id="site-menu">` is rendered before the `<button aria-expanded aria-controls="site-menu">`. With real keys on `/`: Tab, Tab, Tab reaches **Menu** (button, `aria-expanded="false"`; ring 8.16:1); Enter opens it (the label becomes **Close**, `aria-expanded="true"`, the four links appear); the next Tab goes to **Buy the books**, in the page, not to **Shop**. The menu's links are reached only by Shift+Tab, in reverse (Register, Log in, Find your order, Shop). Same at 320 px and in the Claude pane. The Django audit's menu order (F4) was right once open.
- **What works.** Escape closes the menu and returns focus to the button (also when focus was on a link inside); Space and Enter both toggle; a click outside closes it; following a link closes it and puts focus on the new page's `h1`.
- **WCAG.** 2.4.3 Focus Order (A), 1.3.2 Meaningful Sequence (A).
- **Fix.** Put the button before the `nav` in the markup (on wide screens `order` or a flex row puts it where it is now; the button is hidden there), or move focus to the first link when it opens (and back on close).

### F4. The "added to cart" toast lives about 300 ms (High)

- **Where.** `AddToCart` calls `toast.success("<title> is in your cart.")` and then `router.push("/cart/")`; `Toaster` (`src/components/ui/toaster.tsx`) runs `toast.dismiss()` whenever the pathname changes ("until the next page"), which includes the navigation the toast was raised for. Recorded on `/shop/physics-sample-papers-2027/` (signed in): toast added at 75 ms, the page changes at 177 ms, the toast is removed at 383 ms. Two seconds after the click the cart page shows no toast. `MarksForm`'s edit path (`toast.success("Saved to your record."); router.push("/account/record/")`) does the same. Toasts raised without a navigation (Save my details, Delete my account) stay as designed.
- **The live region itself is right.** `section[aria-live="polite"][aria-relevant="additions text"][aria-label="Messages alt+T"]` is in the page from load (after the footer), the toast is added inside it; the text is "X is in your cart." But the message disappears almost at once and no one sees it.
- **WCAG.** 4.1.3 Status Messages (AA): the confirmation of a user action is not presented.
- **Fix.** Dismiss only the toasts that existed before the navigation (remember their ids when the pathname changes), or raise the toast after the navigation (a one-time flash through the cart page).

### F5. The home page is 338 px wide at 320 px (Medium)

- **Where.** `/` at 320 px (400 % zoom): `scrollWidth` 338; the hero's eyebrow, `h1`, the "30 papers in each book" row and the lead all end at x = 330 ("Buy the books" is cut off). The same 338 as the Django audit's F2(b): the cover fan (about 314 px) forces its row's width. Evidence: [home-320-overflow.jpg](audit-evidence-nextjs/home-320-overflow.jpg). 375 px and 640 px are fine.
- **WCAG.** 1.4.10 Reflow (AA).
- **Fix.** As verified for the Django page: below 900 px the hero's grid must not wrap (`flex-wrap: nowrap`) and the fan gets `overflow-x: clip`.

### F6. Dialogs: focus is not returned (cart), and they are cut off at 400 % zoom (Medium)

- **What works.** Both dialogs (`/cart/` Remove, an order's Cancel) are Radix dialogs: role `dialog`, named by their title ("Remove this book?", "Cancel this order?"), described, opened on the safe button ("Keep it", "Keep the order"), focus trapped (Tab cycles Close, Keep, the destructive button), the page behind is `aria-hidden` and `pointer-events: none`, Escape closes.
- **Focus return (cart).** After Escape, "Keep it" or a click outside, `document.activeElement` is `body` on the cart; the order page's Cancel dialog puts focus back on its button. The cart's dialog is controlled by state and has no `DialogTrigger`, and Radix returns focus to the trigger it knows. After a confirmed Remove (Tab to the dialog's Remove, Enter) the cart is empty and focus is on `body` too.
- **Cut off at 400 % zoom.** At 320 × 256 the cart's dialog is 262 px tall (top −3 px, bottom 259) and the order's Cancel dialog 318 px (top −31, bottom 287): the title and the Close button are above the viewport and "Cancel the order" is partly below it, and a fixed dialog cannot scroll (`fixed top-1/2 … -translate-y-1/2`, no `max-height`). Evidence: [dialog-cancel-order-320x256.jpg](audit-evidence-nextjs/dialog-cancel-order-320x256.jpg), [dialog-cart-remove-320x256.jpg](audit-evidence-nextjs/dialog-cart-remove-320x256.jpg).
- **WCAG.** 2.4.3 (A); 1.4.10 Reflow (AA).
- **Fix.** Return focus: wrap the Remove button as the `DialogTrigger` (or set `onCloseAutoFocus` to focus a stored element, and the next line's Remove or the list after a confirmed removal). Fit: `max-h-[calc(100dvh-2rem)] overflow-y-auto` on `DialogContent`.

### F7. The paper cards' names leave out their visible text (Medium)

- **Where.** `/books/<slug>/`, the 30 cards (`a[data-slot="card"]`): `aria-label="Paper E-02, Easy: open the solutions"` while the card shows "E-02 / 70 marks · 3 hours" (and "Open to everyone" on the open one). axe: `label-content-name-mismatch`, serious, 30 nodes per book page.
- **WCAG.** 2.5.3 Label in Name (A): a voice-control user who says what they see ("70 marks") has no match.
- **Fix.** Include the visible text in the name ("E-02, 70 marks, 3 hours: Easy, open the solutions") or drop the `aria-label` and let the content name the link.

### F8. Focus lands on a card or chip that is mostly out of view (Medium)

- **Where.** (a) The home page's subject strip under 768 px: the Physics tile is fully visible, **Chemistry has 61 of 274 px showing** (`scrollLeft` stays 0), Mathematics is scrolled in, Biology again shows 61 px; `div.tiles-strip` does not scroll to the focused tile. (b) The account navigation chips under 900 px (`/account/*`): on focus "Details" shows 19 of 79 px, "Log-in and security" 128 of 165, "Teacher access" 84 of 135. Chrome scrolls a scroll box to reveal a focused element only when the element is **entirely** outside it (the Django audit's F1 and F5 found the same).
- **WCAG.** 2.4.7 Focus Visible (AA, the ring is cut); 2.4.11 Focus Not Obscured (Minimum) (AA, not entirely hidden, so a failure of intent).
- **Fix.** A `focusin` handler on the strips: `e.target.scrollIntoView({ block: "nearest", inline: "nearest" })`; or lay the four tiles out in a grid on phones.

### F9. Errors that are not tied to a field or not announced (Medium)

Forms tested with an invalid submit (nothing valid was ever submitted): login (phone, email and password forms), sign-up, contact, order lookup, school quotation, marks (empty and over full marks), addresses, details, teacher access, mobile number, email change, password set, delete account (unticked), coupon, checkout (new address).

What works, on all of them but the exceptions below: every invalid control has `aria-invalid="true"` and an `aria-describedby` whose ids resolve to the help and the error; one summary (`role="alert"`, "There is a problem") takes focus; each summary link goes to a control that exists and moves focus to it (`#phone`, `#full_name`, `#consent`, …); sign-up, contact, marks, details, account forms put the field's name before the message ("Full name: Enter your full name.").

- **Login with nothing typed** (phone and email forms): "Enter your email address or your mobile number." appears in the summary with no link and no `aria-invalid` control; the API's message belongs to `login`, which is not the form's field (3.3.1). It also names the other method than the one on screen.
- **Login, a wrong phone or email**: the same message is attached to the hidden password form's field too (`#login` is `aria-invalid` inside the closed fold).
- **Summary link text without the field's name**: the password-login form's link reads "This field is required." (no `labels` passed to `ErrorSummary`); the Django audit's F8 (2.4.4).
- **The coupon box** (`/cart/`): "Type the code first." sits under the field (`aria-invalid`, `aria-describedby` set) but has no `role` and there is no summary, so it is not announced and focus stays on Apply (4.1.3).
- **Checkout address form**: `noValidate` is false, so the browser's own bubbles ("Please fill out this field", in the browser's language) replace the summary: no `aria-invalid`, no summary, none of the site's wording (3.3.1 is met by the bubble; the pattern differs from every other form).
- **Raw API words** in the contact, address and teacher forms: "This field may not be blank." (a copy matter, 3.3.3).
- **Fix.** Map the `login` message to the visible field in the form's `error` prop; pass `labels` to the password form's `ErrorSummary`; give `FieldError` a `role="alert"` when it appears without a summary; set `noValidate` on the checkout form and use the shared summary.

### F10. axe's scrollable regions (Low)

- **`/s/<code>/`: 40 to 42 violations, a false positive.** axe 4.14 reports `scrollable-region-focusable` on every `article.question` (serious). `.question` has `overflow-x: auto` and `content-visibility: auto`; with the content-visibility forced to `visible` the rule passes, and the questions do not overflow at 375, 320 or 640 px (`scrollWidth` equals `clientWidth` for all 55), Tab never stops on one. The count appears only when axe's other rules have rendered the skipped blocks. Remove `overflow-x: auto` from `.question` (the tables and the maths have their own scroll boxes) to silence it and to spare the page 55 scroll containers.
- **`/revision/`: 1 real violation.** The chapters tables' `div.table-wrap` (inside the collapsed subject `<details>`) scrolls sideways at 375 px and has no `tabindex`, role or name (it is `div[data-slot="table-wrap"]` with the table's `<caption>` inside). Chrome makes a scroller focusable on its own, Safari does not. Add `tabindex="0" role="region" aria-labelledby=<caption id>` (WCAG 2.1.1).

### F11. Text spacing and 320 px (Low)

- With the WCAG 1.4.12 overrides (line height 1.5, letter spacing .12em, word spacing .16em) the page scrolls sideways by 4 px on `/cart/`, `/checkout/`, `/account/` and the order page: the Menu button (`button.inline-flex`, right edge 379 px) is pushed out of the header row once the cart badge is showing (the Django audit's F2(a)). At 320 px the cart's total (`dd.num`) ends at 322 px, so `/cart/` is 322 px wide.
- **Fix.** Let the brand shrink (`min-width: 0; overflow: hidden`) or hide the "Cart" word at that width; `min-width: 0` on the cart summary's rows.

### F12. The 404 page's title changes after load (Low)

- `/no-such-page-xyz/`: the server sends `<title>Page not found · ExamLeaf</title>`; after hydration `document.title` becomes `ExamLeaf · ExamLeaf`; on `/orders/t/<unknown>/` (a 404 page too) it becomes `Your order · ExamLeaf`. `/s/<unknown>/` and `/shop/<unknown>/` keep the right title. The segment's own metadata is applied to the not-found boundary on the client. WCAG 2.4.2 Page Titled (A). Fix: return the 404 title from the segment's `generateMetadata` when the lookup fails, or set it in `not-found.tsx`'s client part.

### F13. Toasts (Low)

- The Dismiss button is **20 × 20 px**, inside a focusable toast (`li[tabindex=0]`), so the 24 px spacing exception does not hold (2.5.8, AA). Give it 24 px or more (`[data-close-button]`).
- Toasts do not time out, by design, so an obsolete one stays: after Delete my account then Keep my account both "Your account will be deleted in 7 days" and "Your account stays" are on screen.
- The region comes after the footer in the page (Alt+T focuses it; Tab reaches the toast only after the whole footer). With a toast showing at the bottom of a phone the Tab walk found no covered stop: the Django audit's F3 is fixed by `html:has([data-sonner-toast]) { scroll-padding-bottom: 120px }`.

### F14. Smaller items (Low)

- **`aria-labelledby` on a generic `div`** (the order summary card on `/checkout/`, `div[data-slot="card"][aria-labelledby="order-title"]`): axe "needs review" `aria-prohibited-attr`; use a `section` or `role="region"` (4.1.2).
- **Re-authentication.** `/account/privacy/`, Download my data after 5 minutes without a password on the account: the summary says "Confirm it is you: enter your password, or log in again." and the warning "Log in again first" follows; the account has no password to enter. Show only the second.
- **The home page's cover fan** sits above the hero text on a phone but after its buttons in the page: four tab stops (the covers) come after "See a sample paper", and the same four books have eight tab stops (covers and tiles).
- **Devices** (`/account/security/`, "Where you are logged in"): with several sessions of the same browser the rows read alike ("Chrome on macOS, 127.0.0.x, since 8 Oct 2026, last seen 8 Oct 2026": dates, no times), and only "Log out the other devices" is offered; the error line of that card has no `role`.
- **No `lang` change is needed**: every page is `lang="en"`; no Bengali or Assamese text was found.

## 4. Checked and fine

| Check | Result |
|---|---|
| Skip link | First Tab on every page; 176 × 49 px at the top left with a ring (3.94:1); Enter goes to `main#main` (`tabindex="-1"`, now the active element) and the next Tab is inside `main`. The Django audit's F10 is fixed |
| Focus after client-side navigation | `RouteFocus` puts focus on the new page's `h1` (menu link to `/shop/`: `h1 "Buy the books"`); Next's route announcer is present |
| Focus order | Sensible on every page: skip link, brand, (cart), Menu, content in reading order, footer; 867 Tab stops walked on 38 pages. The exceptions are F3, F8 and the cover fan (F14). The solutions pages have 26 stops anonymous and 34 signed in (the marks form's date field takes four presses: day, month, year, picker) |
| Focus visible | An indicator on every stop. Lowest ring contrast 3.58:1 (home tiles, book and product pages), 3.94:1 on most pages, 4.11:1 on cards and form controls, 8.16:1 on the header, 10.8:1 on the footer; the hero's buttons wear `rgb(143, 214, 148)` on `rgb(7, 18, 43)`, about 10:1 (axe cannot read the gradient) |
| Nothing hides the focus | The header is `position: relative`, not sticky; the only sticky things are table headers inside scroll boxes and the solutions rail from 900 px; with a toast showing at the bottom of a phone no Tab stop was covered (`scroll-padding-bottom: 120px`) |
| Menu drawer | `aria-expanded` and `aria-controls` follow the state; the name changes from Menu to Close; Escape closes and returns focus to the button, also from a link inside; Enter and Space toggle; outside click and navigation close; at 320 px the label is visually hidden and the 44 × 44 button keeps its name (F3 for the order) |
| Forms | Labels, `aria-invalid`, `aria-describedby` with ids that resolve, a focused `role="alert"` summary with working links, field names in most summaries (F9 for the exceptions); required fields have `required` and an `aria-hidden` star; `autocomplete` tokens `name`, `email`, `tel-national`, `bday`, `new-password`, `current-password`, `username`, `address-level2`, `postal-code`, `one-time-code`, `off` for what should not be remembered; 73 controls, none unlabelled |
| OTP field | One real `<input id="code" name="code" autocomplete="one-time-code" inputmode="numeric" maxlength="6" pattern="^\d+$" aria-label="6-digit code">` over six drawn boxes (the accessibility tree has one textbox, "6-digit code"); the visible label "Code" is contained in the name (2.5.3); focused on arrival; the ring is drawn on the active box (outline 2 px); typing, Backspace and a six-digit value behave; "Log in" stays disabled until six digits and nothing is submitted by itself; a wrong code gives "Incorrect code." in the summary and under the field (`aria-invalid`, `aria-describedby="code-help code-error"`, link `#code`) |
| Toast region | `section[aria-live=polite][aria-relevant="additions text"][aria-label="Messages alt+T"]` exists from load, Alt+T focuses it, the toast's Dismiss works with Enter and is reachable by Tab (F4, F13 for what is wrong) |
| Headings and landmarks | One `h1` and no skipped level on all 38 pages, none empty; landmarks `banner`, `navigation` "Main", `main`, `contentinfo`, the toaster's region "Messages alt+T", `navigation` "Breadcrumb" on product, book, solutions and revision, `navigation` "My account" on every account page, `complementary` "On this paper", "Your course"; the offline page has only `main` |
| Page titles | Specific and unique ("Log in", "Register", "Your cart", "Order EL-2026-000003", "Physics Sample Paper E-01: solutions"); the same page signed in and out shares one (F12 for the 404) |
| Names | Zero unnamed interactive nodes in the accessibility tree on all 38 pages; icon-only controls named ("ExamLeaf home", "Cart, 3 books", "One copy more of …", "Dismiss", "Close"); images have `alt` (covers "Cover of …", decorative ones `alt=""`); icons are `aria-hidden`; the authenticator's QR code is `svg[role=img][aria-label="QR code of the key, for the authenticator app"]` with the key written out in groups beside it |
| Targets | All at least 24 × 24 px except the 22 × 22 native checkboxes and radios, which sit inside 44 px label rows (pass); "Home" breadcrumb 39 × 44, footer "Terms" 41 × 44; the toast's Dismiss is 20 × 20 (F13) |
| Contrast | axe: no `color-contrast` violation on any page; its "needs review" items (the hero's gradient, the account chips, the stepper's numbers, KaTeX spans) were checked by sampling the rendered pixels behind every text node of 14 pages: no text below its minimum (median ratio 7.5:1 or more; the outliers were rotated seal text and collapsed content) |
| Reduced motion | With `prefers-reduced-motion: reduce`: 0 running animations and 0 elements with a transition or animation on all nine pages checked (against 0 to 4 elements without the preference: tile and cover lift, accordion chevron, the stepper's bar, the toasts); the busy spinner has no animation; view transitions still start on a morph navigation (a tile to its book) but their `animation` is `none`, so the page changes at once |
| 200 % zoom (640 px) | No sideways scroll and no clipped text on any of the 25 pages tried; the clipped boxes found are by design (a cover that bleeds out of a subject tile) |
| Language | `<html lang="en">` on every page |
| Disclosures | The FAQ, the paper's instructions and the revision tables are native `<details>`: `summary` is a Tab stop and Enter and Space open it |

## 5. Record per page

axe-core 4.14 at 375 px (wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, best-practice) and the Tab walk; `*` = signed in. "Probe findings" counts the walk's flags: 24 "not fully in the viewport after focus" (the home tiles and the account chips of F8, plus tall textareas and scroll boxes that Chrome focuses with part of them below the fold, which are not faults), 4 "partly covered" at one of five sample points (the overlapping covers of the home fan, two inline links whose 44 px boxes touch: not faults) and 1 "moves back up the page" (the cover fan, F14). No stop lacked a focus indicator, none had a ring below 3:1, none lacked a name. The solutions pages' walk in this scan ended early (after axe had run); their real stop counts are 26 (anonymous) and 34 (signed in).

| Page | Tab stops | axe violations | axe "needs review" | Lowest focus-ring contrast | Probe findings |
|---|---:|---|---|---:|---|
| `/` | 38 | none | color-contrast (11) | 3.58:1 | 5 |
| `/about/` | 19 | none | none | 3.94:1 | none |
| `/books/physics-2027/` | 53 | **label-content-name-mismatch (30)** | none | 3.58:1 | none |
| `/shop/` | 30 | none | none | 3.94:1 | 1 |
| `/shop/physics-sample-papers-2027/` | 29 | none | none | 3.58:1 | 1 |
| `/shop/school-orders/` | 35 | none | none | 3.94:1 | none |
| `/orders/lookup/` | 20 | none | none | 3.94:1 | none |
| `/contact/` | 25 | none | none | 3.94:1 | 1 |
| `/privacy/`, `/terms/`, `/refunds/`, `/shipping/` | 17 to 21 | none | none | 3.94:1 | none |
| `/revision/` | 26 | **scrollable-region-focusable (1)** | none | 3.94:1 | 1 |
| `/s/PHY-E01/` (anonymous) | 26 | scrollable-region-focusable (42, false positive) | color-contrast (258, KaTeX) | 3.94:1 | none |
| `/s/PHY-E02/` (anonymous: the register wall) | 22 | none | none | 3.94:1 | none |
| `/account/login/` | 23 | none | none | 3.94:1 | none |
| `/account/signup/` | 30 | none | none | 3.94:1 | none |
| `/account/password/reset/` | 19 | none | none | 3.94:1 | none |
| 404 | 23 | none | none | 3.94:1 | none |
| `/offline/` | 1 | none | none | 4.11:1 | none |
| `/c/<token>/` (unknown token), `/orders/t/<token>/` (unknown) | 19, 24 | none | none | 3.94:1 | none |
| `/account/` * | 27 | none | color-contrast (6) | 3.94:1 | 3 |
| `/account/record/` * | 25 | none | color-contrast (6) | 3.94:1 | 3 |
| `/account/orders/` * | 21 | none | color-contrast (6) | 3.94:1 | 3 |
| `/account/orders/<n>/` * | 24 | none | color-contrast (6) | 3.94:1 | 3 |
| `/account/details/` * | 26 | none | color-contrast (6) | 3.94:1 | 2 |
| `/account/addresses/` * | 21 | none | color-contrast (5) | 3.94:1 | 2 |
| `/account/security/` * | 27 | none | color-contrast (4) | 3.94:1 | 1 |
| `/account/2fa/` * | 18 | none | color-contrast (4) | 3.94:1 | 1 |
| `/account/privacy/` * | 20 | none | color-contrast (3) | 3.94:1 | 1 |
| `/account/teacher/` * | 19 | none | color-contrast (2) | 3.94:1 | none |
| `/cart/` * | 27 | none | none | 3.94:1 | none |
| `/checkout/` * | 23 | none | aria-prohibited-attr (1) | 3.94:1 | none |
| `/checkout/<n>/pay/` * | 22 | none | color-contrast (2) | 3.94:1 | none |
| `/revision/` * | 30 | **scrollable-region-focusable (1)** | none | 3.94:1 | 1 |
| `/s/PHY-E01/`, `/s/PHY-E02/` * | 34 | scrollable-region-focusable (42, 40; false positive) | color-contrast (258, 166; KaTeX) | 3.94:1 | none |

States reached beyond the pages (axe found nothing further on them): the menu open (375 and 320 px), the cart's Remove dialog and an order's Cancel dialog open, the login's code step and its wrong-code error, the authenticator's QR code after "Set up the authenticator app" (`/account/2fa/`: no violation, 5 contrast items to review), the deletion requested and kept (`/account/privacy/`), the log-in-again alert, the signed-in devices list (four sessions: no violation).

What the build half asked the review to look at first:

| Item | Result |
|---|---|
| The contact form | Reached with `SUPPORT_EMAIL` set. Labelled (Your name, Email address, Message), `aria-describedby` help ("We reply to this address.", "Up to 2,000 characters."), an empty send gives a focused summary with three working links and `aria-invalid` on all three; words are the API's ("This field may not be blank.", F9). Without a support address the page shows no form |
| The devices list and its button | A list of sessions (browser and system from the user agent, "This device" badge, address `127.0.0.x`, dates) and "Log out the other devices" (226 × 44 px); no axe finding; F14 for the alike rows |
| The QR code's `role="img"` | Present, named, with the key as text beside it; 176 × 176 px; axe passes |
| The Coming soon badges | 51 on `/revision/`, plain text "Coming soon" in a badge; contrast passes; the tables' scroll boxes are F10 |
| The Log in again alert | `role="status"` warning, plus the summary's duplicate sentence (F14) |
| Focus landing on the h1 after navigation | Works (section 4) |

## 6. Not testable here

- **The hls.js player.** No chapter has a published revision or a free clip in the development database (`learn/chapters/` gives `has_revision: false`, `free_preview: null` for all 51), and no ffmpeg exists to make one, so a clip could not be played. By the code (`src/components/revision/islands.tsx`, `HlsVideo`): a native `<video controls playsInline preload="metadata" aria-label={clip.title}>` (the browser's own controls are keyboard-operable: Space, arrows, F), a `<figcaption>` with the title, a `role="alert"` with "Load it again" when playback fails. **Gap:** the API's clip carries `notes` / `notes_html` ("Transcript or notes") but the player shows neither, and there is no `<track>`: a prerecorded clip with speech will need captions and a transcript (WCAG 1.2.1 Audio-only and Video-only, 1.2.2 Captions, 1.2.3 Audio Description or Media Alternative, all A) once clips exist.
- **A screen reader.** Roles, names and live regions were read from the accessibility tree.
- **Safari and Firefox.** The scroll-box findings (F10) and the focus handling of disabled buttons (F1) may differ.

## 7. How to re-run

Build and start the frontend and a seeded Django as in [audit-nextjs-lighthouse.md](audit-nextjs-lighthouse.md) section 2, create a non-staff student with `manage.py shell` and sign it in through the email-code form, then drive headless Chrome with Puppeteer and inject `axe-core` (`axe.run(document, { runOnly: { type: "tag", values: [...] } })`); the Tab walk is a loop of `page.keyboard.press("Tab")` with a probe of `document.activeElement` after each press. The scripts of every test above are in [audit-scripts/nextjs/](audit-scripts/nextjs/README.md) (`a11y-*.mjs`, `contrast.mjs`, `inpage.mjs`). The student and everything it made (cart, address, order, marks, sessions) were deleted at the end.
