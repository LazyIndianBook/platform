# The Answer Script redesign: implementation report

Branch `design/answer-script`, built on 9 October 2026 from `main` at b3cd16b. The design is "Direction A, Answer
Script" (`implementation/design/*.dc.html`, one `[data-screen-label]` per screen; `implementation/README_IMPLEMENTATION.md`
is the plan). The frontend (`examleaf-frontend/`) was restyled page by page; the backend changed in one additive way
(`config/ web_course`) and in the presentation of its emails and invoice. No API contract, business rule, permission
or entitlement changed.

## 1. What changed

### The foundation

- `src/app/globals.css`: the Direction A tokens under the same names (paper `#F8F5EE`, ink `#1D2230`, red ink `#B3342A`,
  navy `#0B2A5B`, the control border `#7B8595`, the focus ring `#2F8F3A`), the answer booklet's grid (`.sheet`: a
  120 px margin, the content behind a 3 px double red rule, a 112 px marks column; under 900 px the rule alone at the
  left edge), `.marked-row` (a row and its mark on one baseline), `.label-mono`, `.q-rule`, `.numeral`, `.seal`,
  `.marker` (red italic, the one emphasis of a view), the table, prose and accordion rules, and the motion rules:
  150 / 220 / 360 ms, transform and opacity only, everything inside `prefers-reduced-motion: no-preference`; the two
  signature moments ([data-mark-landed]: the saved score's circle after the server confirms; `.paper-page .qno` turning
  red as its row reaches the top of the screen with `animation-timeline: view()`, colour only).
- `src/app/fonts.ts`: Source Serif 4, Public Sans and IBM Plex Mono self-hosted from `src/app/fonts/` with their OFL
  licences, as subsets made with fontTools from the official variable fonts (Latin, the rupee sign, arrows, ticks and
  superscripts; the serif and the sans keep their weight axis from 400 to 700; the serif comes in a text cut, its
  optical size pinned at 20, and a display cut at 60 for h1, h2 and the display sizes, which is what the design's
  Google Fonts link asks for). A build needs nothing from the network and serves the same bytes every time;
  `font-src 'self'` holds. Hind Siliguri stays in every stack for Assamese and Bangla. `poppins` is kept as an alias
  of the serif, so old imports compile; the Poppins files are gone.
- `src/components/ui/`: every component drawn as the Components board draws it, in every state (default, hover,
  focus-visible 2 px ring with a 2 px offset, active 1 px press, selected, disabled, busy with `aria-busy` and presses
  swallowed, error with the icon and the message tied to the field, success). `Sheet`, `MarkedRow` and `Marks` in
  `band.tsx`; `Badge` gains `stamp`, `code`, `gold` and the seven order statuses (`STATUS_VARIANT`); `Progress` is new
  (words beside the bar); `SelectableCard` gains an `end` slot; the skeleton is a still placeholder; dialogs stay the
  browser's `<dialog>`; the toast is the ink bar with Dismiss. Every exported API is kept.
- The site's frame: the paper header (Books · Shop · Revision course · Find your order · Log in · Register; signed in,
  My record · Account · Log out), the Menu toggle in ink, the drawer as "Phone menu", the ink footer behind the red
  rule, the account navigation as a quiet margin list with a red dot (chips that scroll sideways on phones).

### The pages

| Route                                                                                      | Artboards                                                 | What the page does now                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------ | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/`                                                                                        | 96 / 2.8 s / 173.2 KB                                     | 98 / 100 / 100 / 100                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | 1.1 s | 2.4 s | 30 ms | 0     | 160.7 KB | 210.5 KB | 519 KB |
| `/books/<slug>/`                                                                           | Book, Phone book                                          | The hero on a Sheet (margin: the subject code; marks: [papers] [marks] [time]), the buy buttons from the shop, the log-in prompt, one Sheet per tier with the papers as cells and the open sample marked in red ink.                                                                                                                                                                                                                                                                                             |
| `/s/<code>/`                                                                               | A Solutions, Solutions logged out, Phone solutions        | The masthead (mono eyebrow, serif title, ruled facts, the stamp), the paper on a Sheet with question numbers in the margin and allotted marks in the marks column, solutions on the red margin line with ticked marking steps and a circled total, a rail from 1100 px (On this paper, Paper n of m, Next), a sticky chip row below it, the record card at the end. The wall: the two-panel card with `next` kept on both links and the open sample offered. Print: one page per question group, no site chrome. |
| `/c/<token>/`                                                                              | Parent link, Expired links                                | The facts as a ruled list beside the answer card; the expired state names the student and links Contact (G5); 429 says when to try again.                                                                                                                                                                                                                                                                                                                                                                        |
| `/about/`, `/privacy/`, `/terms/`, `/refunds/`, `/shipping/`                               | About, Legal                                              | `§` in the margin, the CMS HTML in the serif prose, "On this page" from the page's h2s (a rail from 1100 px, a disclosure below); `/shipping/` adds the rates from `GET shipping/` in a table that scrolls in its own box.                                                                                                                                                                                                                                                                                       |
| `/contact/`                                                                                | Contact                                                   | The contacts from config, the form card only when a support address is set, Turnstile only with a key, 429 and 503 in words.                                                                                                                                                                                                                                                                                                                                                                                     |
| 404, error, offline                                                                        | 404, Unavailable and offline                              | "This page isn't in the book" with the subjects as rows and the Find-your-order hint for `/orders/t/` links (G19); the unavailable page stays a real 500; offline stays self-contained.                                                                                                                                                                                                                                                                                                                          |
| `/shop/`                                                                                   | 95 / 2.8 s / 179.9 KB                                     | 91 / 100 / 100 / 100                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | 1.5 s | 3.5 s | 10 ms | 0.005 | 160.7 KB | 153.9 KB | 572 KB |
| `/shop/<slug>/`                                                                            | Product, Phone product                                    | Options as radio cards with the BEST VALUE stamp, the joined copies stepper, Add to cart · ₹price and Buy now (sent once), the three facts (stock, delivery, cancel), What's inside, Try before you buy, details, reviews.                                                                                                                                                                                                                                                                                       |
| `/shop/school-orders/`                                                                     | School orders                                             | Two columns; the quote form with a copies grid by subject and kind.                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `/cart/`                                                                                   | Cart, Cart coupon, Cancel dialog                          | Ruled lines, the paper-2 summary, the coupon applied and removed through `cart/coupon/` with the API's discount and its refusal on the field, Remove in the paper dialog, the empty state.                                                                                                                                                                                                                                                                                                                       |
| `/checkout/`                                                                               | Checkout, Phone checkout, Checkout delivery, PIN autofill | Two steps with the stepper's current step in red; the address book; PIN autofill found, not found and two-state (G12); the backend's rules in the error summary; the Delivery step with the fee and the free-delivery line from the API, cash on delivery there when offered; the typed form kept in sessionStorage across Back and a log-in round trip; consent pending disables the form.                                                                                                                      |
| pay, done                                                                                  | Pay, Payment failed, Payment pending, Done                | Busy while Razorpay loads, honest "unavailable" without keys, a declined payment keeps the order and offers cash on delivery when allowed; the done page shows PAID only when the server says paid, "We're confirming your payment" asks once more after 10 s and offers nothing to pay again.                                                                                                                                                                                                                   |
| `/orders/t/<token>/`, `/account/orders/<n>/`                                               | Order, Order refunded, Your papers, Cancel dialog         | Status chip, timeline, address, payment, GST invoice and credit notes, "Your papers" (G20), Cancel in the native dialog.                                                                                                                                                                                                                                                                                                                                                                                         |
| `/orders/lookup/`                                                                          | Order lookup                                              | Restyled; no enumeration, as before.                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `/account/login/`                                                                          | Login, Password login, Session expired, Auth edge pages   | Methods from config (SMS first, email code, Google, passkey, the password fold), the NEXT chip for `?next=`, Google's refused or cancelled sign-in drawn from `?error=`, the 429 wording with a time, the "You were logged out" notice when a draft waits.                                                                                                                                                                                                                                                       |
| `/account/signup/` and the narrow cards                                                    | Signup, Google sign-up, the card boards, Phone code       | The under-18 path, Turnstile only with a key, the six code boxes (paste fills all), verify email, reset, new password, reauthenticate, two-step check, log out.                                                                                                                                                                                                                                                                                                                                                  |
| `/account/password/reset/done/`, `/account/inactive/`                                      | Auth edge pages                                           | New (G2, G18, G4): the reset's last page with Log in keeping `next`; the inactive account page with why and Contact.                                                                                                                                                                                                                                                                                                                                                                                             |
| `/account/`                                                                                | A Account, Phone account                                  | The nav in the margin column; Continue, the revise-again count, the record with its AVERAGE column, the next days, the latest order, the app row (G6).                                                                                                                                                                                                                                                                                                                                                           |
| `/account/record/`, `<id>/edit/`                                                           | Record, Record filters, Record edit, Record form full     | A marked row per attempt grouped by tier with the tier's average row; subject and tier filters with an honest "No papers match" (G10); the edit page with all four fields and Delete.                                                                                                                                                                                                                                                                                                                            |
| `/account/learning/`                                                                       | Learning                                                  | The vertical player, the plan form, the next days, chapter bars with the QUIZ column, the empty states.                                                                                                                                                                                                                                                                                                                                                                                                          |
| `/account/orders/`, `details/`, `addresses/`                                               | Orders, Details and addresses                             | Status chips; the verified email; address cards with PIN autofill (G12) and a draft that survives a 401.                                                                                                                                                                                                                                                                                                                                                                                                         |
| `/account/security/`, `2fa/`                                                               | Security, 2FA setup, Recovery codes                       | One ruled row per method, devices logged out one at a time, the TOTP setup with its QR, the recovery codes board.                                                                                                                                                                                                                                                                                                                                                                                                |
| `/account/privacy/`                                                                        | Privacy, Data summary and deletion                        | Consent with "Send the link again", the export summary before the download, deletion confirmed by typing the email.                                                                                                                                                                                                                                                                                                                                                                                              |
| `/account/teacher/`                                                                        | Teacher access fixed                                      | Request → checking → verified; no view of students (G14).                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `/revision/`                                                                               | Revision course                                           | The chapter table in the mono voice, the book-code form with its used, unrecognised and 429 states.                                                                                                                                                                                                                                                                                                                                                                                                              |
| `/revision/<subject>/<chapter>/`, `…/cards/`, `…/quiz/`, `/account/learning/revise-again/` | Learning (LMS), all boards                                | The proposed web course, behind `config.web_course` (off by default: every one answers 404). Clips, notes and the Board's questions; the book-code card when locked; flash cards saved one by one; the quiz checked by the server, the verdict only after its reply, Check busy with a second press sending nothing; Revise again with the course settings.                                                                                                                                                      |
| Emails and the GST invoice                                                                 | Email, Emails, GST invoice                                | `templates/email/base.html` and `message.html` (so the log-in code, parent consent and password reset emails), the order confirmation, shipped and payment-link emails, and the invoice, bill of supply, credit note and quotation PDFs, restyled without changing a word, a link or a figure.                                                                                                                                                                                                                   |

### The backend

- `GET /api/v1/config/` returns `web_course` (`WEB_COURSE` in the environment, off by default); `API.md` and
  `.env.example` describe it; `openapi.json` and `src/lib/api/schema.d.ts` were regenerated.
- One test assertion changed with the email restyle (the code's colour is ink, not navy).

### Tests

- Unit (Vitest): 89 on `main` → 180 on the branch. New: every changed component state (busy by click and by Enter,
  disabled, a field in error, the OTP paste, tabs by arrow keys, dialog focus, the order statuses, progress), the
  marks form (busy, consent-blocked, the draft restored and cleared, the circle only after the response), the auth
  pages (the NEXT chip, the methods from config, 400 and 429, the four edge pages, a switched-off account sent to
  the inactive page after a right password or code), the shop (coupon applied and
  refused, PIN found and not found, the draft, cash on delivery, the pending and failed done states, the cancel
  dialog), the account (the filter with no match, the teacher's three states, deletion against the typed email, the
  export summary, the address draft), the course (no verdict before the server answers, Check busy, the card keys,
  the settings' limits, 404 with the flag off).
- Playwright: the existing specs updated to the new words (`phone.spec.ts`: the menu's first link is Books;
  `states.spec.ts`: the shop's closed notice, the Delivery step, the done page's words), plus `solutions.spec.ts`
  (the wall keeps `next`; nothing is circled before the 201), `narrow.spec.ts` (27 pages at 320 × 568 with no sideways
  scroll), `auth.spec.ts` (a code log-in with the NEXT chip, a 401 round trip with the draft restored, the under-18
  registration, the forgot-password journey, the edge pages), `shop.spec.ts` (the coupon refused, the declined payment,
  the pending payment with one update and no PAID, Back keeping what was typed), `account.spec.ts` (the filter that
  matches nothing, the teacher's states) and `course.spec.ts` (skipped while `web_course` is off).

## 2. Before and after

The before set was taken from `main` at b3cd16b, the after set from the branch, both with
`examleaf-frontend/scripts/answer-script-shots.mjs` against the seeded backend (a guest cart from the Physics product
for the cart and checkout; a temporary student for the account): `docs/design/screenshots/answer-script/before/` and
`after/`, eight pages at 1280 and 390 wide (home, book, solutions, shop, login, cart, checkout, account).

| Page       | Before                                                                                                                  | After                                                                                                                 |
| ---------- | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Home       | [1280](screenshots/answer-script/before/home-1280.png) · [390](screenshots/answer-script/before/home-390.png)           | [1280](screenshots/answer-script/after/home-1280.png) · [390](screenshots/answer-script/after/home-390.png)           |
| Book       | [1280](screenshots/answer-script/before/book-1280.png) · [390](screenshots/answer-script/before/book-390.png)           | [1280](screenshots/answer-script/after/book-1280.png) · [390](screenshots/answer-script/after/book-390.png)           |
| Solutions  | [1280](screenshots/answer-script/before/solutions-1280.png) · [390](screenshots/answer-script/before/solutions-390.png) | [1280](screenshots/answer-script/after/solutions-1280.png) · [390](screenshots/answer-script/after/solutions-390.png) |
| Shop       | [1280](screenshots/answer-script/before/shop-1280.png) · [390](screenshots/answer-script/before/shop-390.png)           | [1280](screenshots/answer-script/after/shop-1280.png) · [390](screenshots/answer-script/after/shop-390.png)           |
| Cart       | [1280](screenshots/answer-script/before/cart-1280.png) · [390](screenshots/answer-script/before/cart-390.png)           | [1280](screenshots/answer-script/after/cart-1280.png) · [390](screenshots/answer-script/after/cart-390.png)           |
| Checkout   | [1280](screenshots/answer-script/before/checkout-1280.png) · [390](screenshots/answer-script/before/checkout-390.png)   | [1280](screenshots/answer-script/after/checkout-1280.png) · [390](screenshots/answer-script/after/checkout-390.png)   |
| Log in     | [1280](screenshots/answer-script/before/login-1280.png) · [390](screenshots/answer-script/before/login-390.png)         | [1280](screenshots/answer-script/after/login-1280.png) · [390](screenshots/answer-script/after/login-390.png)         |
| My account | [1280](screenshots/answer-script/before/account-1280.png) · [390](screenshots/answer-script/before/account-390.png)     | [1280](screenshots/answer-script/after/account-1280.png) · [390](screenshots/answer-script/after/account-390.png)     |

## 3. Test results

All on the branch's final commit (488607f) unless noted, on this Mac on 9 October 2026, against the seeded backend
(`scripts/e2e-backend.sh`, a fresh SQLite database, port 8101) and the production build served by `next start` on
port 3001. The baseline column is `main` at b3cd16b, measured the same morning (the Lighthouse baseline is the
8 October audit, `audit-nextjs-lighthouse.md`, on the same pages and preset).

| Check                                                                                              | Baseline (`main`)                                                                                        | The branch                                                                                                                                                                                                         |
| -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `npm run lint`, `format:check`, `typecheck`                                                        | clean                                                                                                    | clean                                                                                                                                                                                                              |
| Vitest                                                                                             | 10 files, 89 tests                                                                                       | 14 files, 180 tests                                                                                                                                                                                                |
| `next build`                                                                                       | 36 routes                                                                                                | 40 routes (the course's four behind the flag)                                                                                                                                                                      |
| Playwright, CI's list (`npm run test:e2e`, production build)                                       | 26 passed                                                                                                | 41 passed, 4 skipped (`course.spec.ts`, `web_course` off), 2.1 min; one earlier run failed on the backend's book-code throttle after six runs in an hour (`learn/redeem/`, 5 an hour per address), not on the code |
| Backend `pytest`                                                                                   | 422 passed, 7 skipped                                                                                    | 422 passed, 7 skipped (one assertion follows the email's new code colour)                                                                                                                                          |
| axe-core 4.14 (WCAG 2.0/2.1 A and AA + best practice), 412 × 823, 27 pages anonymous and signed in | the 8 October audit: 0 real violations; 42 `scrollable-region-focusable` false positives on `/s/<code>/` | 0 violations on all 27; the 42 false positives are gone (no per-question scroll box)                                                                                                                               |
| Sideways scroll at 320 px (the same 27 pages, and `narrow.spec.ts`)                                | none                                                                                                     | none                                                                                                                                                                                                               |

Lighthouse 13, mobile preset (412 × 823 at 1.75 DPR, simulated slow 4G, 4× CPU), the better of two runs; the
desktop preset once for Home. JavaScript and fonts are the transfer (gzip) sizes of the page's requests.

| Page | Baseline: perf / LCP / JS | Branch: perf / a11y / BP / SEO | FCP | LCP | TBT | CLS | JavaScript | Fonts | Total |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 96 / 2.8 s / 173.2 KB | 91 / 100 / 100 / 100 | 1.5 s | 3.4 s | 20 ms | 0 | 160.7 KB | 208.4 KB | 518 KB |
| `/shop/` | 95 / 2.8 s / 179.9 KB | 85 / 100 / 100 / 100 | 1.8 s | 4.2 s | 20 ms | 0 | 160.7 KB | 198.1 KB | 617 KB |
| `/s/PHY-E01/` (open sample) | 93 / 3.1 s / 177.8 KB | 97 / 100 / 100 / 100 | 1.6 s | 2.5 s | 40 ms | 0.006 | 171.7 KB | 210.5 KB | 504 KB |
| `/account/` (signed in) | 82–84 with the CLS defect / 2.7 s / 204.5 KB | 93 / 100 / 100 / 66 (noindex, on purpose) | 1.6 s | 3.2 s | 20 ms | 0 | 182.7 KB | 153.9 KB | 391 KB |
| `/` desktop | 100 / 0.6 s | 99 / 100 / 100 / 100 | | 0.9 s | 0 ms | 0.004 | | | |

Against the budgets of `audit-nextjs-lighthouse.md`:

- **LCP ≤ 2.5 s: met on `/` (2.4 s) and the open paper (2.5 s) in the better of two runs, not on `/shop/` (3.5 s)
  and `/account/` (3.2 s).** The baseline missed it on four of the five pages (2.8 to 3.1 s). Two runs of a page
  differ by up to 1.6 s on this machine (the open paper: 2.5 and 4.1 s), so the figures are indicative: the lab
  is noisy and the framework's JavaScript is the floor. What moved the numbers down on the way: the home hero's
  cover served as AVIF rather than the 176 KB PNG and not fetched on phones, the catalogue's first two covers fetched
  early, and the vendored fonts, which preload 87 KB (the sans and the display cut) instead of 129 KB and drop the
  latin-ext files the rupee sign used to pull in. The largest paint is text on `/`, `/s/<code>/` and `/account/` and
  the first cover on `/shop/`; serving the covers from Caddy with a long cache, as production does, is the next
  lever there.
- **CLS ≤ 0.1: met** everywhere (0 to 0.002; the `/account/` defect of the audit is gone).
- **JavaScript no heavier than before: met**; every page is lighter (−12.5 KB on `/`, −19.2 KB on `/shop/`, −6.1 KB on
  the open paper, −21.8 KB on `/account/`).
- Accessibility 100 on all four (the open paper was 97 until the marking-steps Total row got its own background:
  axe read the footer's ink behind a cell far down the page).

## 4. Implemented and verified

Checked on the production build of the branch against the seeded backend (`scripts/e2e-backend.sh`), in Chromium,
by the checks in section 3 and by the packages' own runs (screenshots at 1280, 390 and 320 compared with the
artboards, the states exercised against the real API where the seed allows it):

- The foundation: tokens, fonts (self-hosted at build time; `font-src 'self'` unchanged), every shared component in
  every state, the header, drawer, footer and account navigation (axe: 0 violations on the public and signed-in pages;
  the header keeps one row from 320 px with a cart count; reduced motion computes to no animation).
- Home, Book, Solutions (signed in, the wall with `next` kept, the printed paper), the parent's link (pending,
  consent, confirmed, expired), About, the legal pages with the shipping rates, Contact (sent, 429), 404 with its
  hints, the unavailable page, offline; nothing scrolls sideways at 320 px on 27 pages (`narrow.spec.ts`).
- The record card: the circle only after the server's 201, the draft kept across a session that ended mid-save,
  the consent-pending refusal with "Send the link again".
- The shop: catalogue tabs and chips, the product's options, copies and facts, out of stock, school orders, the
  cart's coupon applied and refused, Remove, checkout's two steps with the address book, PIN autofill (found, not
  found, two states), the Delivery step's fee from the API, Back keeping what was typed, the draft cleared after the
  order; pay without keys (honest), a declined payment, a pending payment with one update and no PAID, cash on
  delivery and the shop closed (`states.spec.ts`); the order pages (link and account), credit notes, Your papers,
  Cancel.
- Sign-in: the methods from config, the NEXT chip, a code by email, the password fold, Register under 18 with the
  emailed code, the forgot-password journey to the new reset-done page, the inactive page, 400 with the summary, a
  real throttle's "Too many tries" wording, a 401 round trip with the notice and the draft restored.
- The student area: the overview, the record with its filters and the honest no-match (saved marks, averages),
  the edit page, Learning (continue, the plan form, chapter bars, the empty states), orders, details, addresses with
  the PIN autofill and the draft across a 401, security (devices, the rows by anchor), the full 2FA activation to the
  recovery board, privacy (the export summary before the download, deletion against the typed email), teacher
  (request → checking → verified), the revision course page with its book-code states and the 429.
- The web course behind the flag: all four routes 404 with the flag off (default); with `WEB_COURSE=1` on a second
  backend: the chapter page open and locked, clips' progress, the flash cards' keys and saved reviews, the quiz with
  no verdict before the server's reply and one request however often Check is pressed, the settings' limits in the
  API's words, the session ending mid-quiz and coming back (`course.spec.ts`, 4 passed on that backend).
- Emails and the invoice: 12 emails and 5 PDFs rendered through the app's own path, every word, link and figure
  identical to before (pdftotext), readable at 320 px and in dark mode (Chromium); the backend suite 422 passed.

- The web course on the merged branch too: `course.spec.ts` ran again on the production build against a second
  backend with the flag on, 4 passed.
- The shop's category and collection pages, with a shelf (and a sub-shelf) and a collection made for the check:
  the right heading, the shelf's four books and the collection's two, axe 0, no sideways scroll at 390 and 320 (a
  shelf made a moment ago shows from the next request on: the catalogue's 60 s cache serves the last list while it
  refreshes, as designed). The catalogue's filters: `?subject=PHY&kind=solutions` lists the one book, a pair that
  matches nothing says so.
- A switched-off account: allauth.headless answers a right password (or code) with a 401 and no step left, which the
  form used to show as nothing; it now sends such an account to `/account/inactive/` (why, and Contact), checked
  against the real backend with an account switched off, and by two unit tests.

## 5. Implemented but not verified

- Browsers other than Chromium (Safari, Firefox, old Android WebViews): nothing was run there.
- Real mail clients (Outlook, Gmail, Apple Mail): the emails were checked in Chromium with dark-mode emulation only.
- Real video playback in the web course (the seed has no HLS files: progress was checked by firing media events on
  the real `<video>`), the consent-pending state of the course (unit tests only), and a staff account's two-step
  check at log-in.
- Google sign-in against a real backend (rendered and unit-tested only; Turnstile and verified consent are
  exercised by `states.spec.ts`), the generic error page from a real render crash, forced-colours mode.
- 400 % zoom was checked as a 320 px wide viewport, which is what a 1280 px screen shows at 400 %.
- The home figure's question (Sample Paper M-04, 2(c)) is the artboard's own illustration; it is not among the 13
  fixture papers, so it was not checked against the published paper.

## 6. Blocked

- Lighthouse's LCP budget (2.5 s on `/`, `/shop/`, a product, `/s/<code>/`): the baseline already missed it on four of
  the five pages (2.8 to 3.1 s, `audit-nextjs-lighthouse.md`); the numbers in section 3 say where the branch stands.
  The framework's JavaScript is the floor; the design added fonts (section 7: 154 to 211 KB a page, preloading 87 KB).
- A teacher's view of students (G14), telling a student that the parent confirmed (G17), claiming guest orders
  after registering (G16), a CSV of the record, a "This month" filter, address labels, a school field, a clip poster
  before play: the API has no endpoint or field for them (product and backend decisions).
- The web course stays off until the product decision (`WEB_COURSE`); the AI answer checker is not built (no
  backend).

## 7. Deviations from the design, and why

Where the design and the API disagreed, the API won and the page says what is true:

- Copy kept from the existing pages where the specs and the backend depend on it: "Log in with email and password",
  "Marks obtained (out of 70)", "Save to my record", "Send the message", "You are offline", the consent-pending words
  with "Send them the link again" to `/account/privacy/`, allauth's own wrong-password words.
- Sign-in: "a few minutes" for a code (not 10), the reset link "works once, for an hour" (not 3 days), no resend
  countdown (log-in codes have no resend), no "Send me a code instead" on Reauthenticate (password only), Register
  keeps the password fields and drops the sketch's mobile field and "18 or over" radios, Google's refusals are drawn
  on the log-in page (where allauth.headless lands them) rather than on URLs of their own, the reset-done page lives
  at `/account/password/reset/done/`.
- Solutions: "register with your email address" on the wall (sign-up needs one), "The QR code brought you here" only
  when the visitor came from outside, no "Your Easy average is now…" line after a save, no red dot for the current
  section in the rail, no "Your state" picker on the shipping page, counts are the API's.
- Shop: cash on delivery is chosen on the Delivery step (the API fixes the method when the order is made); "kept for
  two days" not 24 hours; District kept (required) and no town from the PIN directory; dropped the copy the API
  cannot back ("Packed within 2 working days", "Usually 4–7 days", "Order updates by SMS", "Teachers can see their
  students' marks"); no reason field on Cancel; the site header stays on checkout, pay and done.
- Student area: revise again counts quiz questions and flash cards (not clips); recovery codes do not say "we won't
  show them again" (the API does); deletion says seven days (not at once); orders list "View" (no invoice URL in the
  list); the SMS switch sits on Privacy as drawn; the two-step row is shown to every student as drawn.
- Web course: `learn/clips/?chapter=` does not exist, so a chapter's clips come from `learn/chapters/<id>/`; no
  question excerpt on "Board asked this", no "· 5 known", "Due today / since …" (the API gives `due` only), no CLIP rows
  or minute estimate; the result circle does not animate (signed-in pages do not move).
- Emails: the artboard's copy ("Your order is placed, Ananya.", "Track the order") is not adopted; the account emails
  carry no header tag (it would add text); PDF fonts fall back to Georgia and Menlo on this Mac and DejaVu and Noto in
  the image, because Source Serif 4 and IBM Plex Mono are not bundled with the backend.
- Components: the switch's off track is `#7B8595` (3:1, not the board's `#C9CCD2`), a disabled field's help text stays
  muted (the board's grey fails 4.5:1), the drawer keeps the reviewed Tab-out-closes behaviour (F3), 44 px targets are
  kept where the board draws smaller ones, the open Menu toggle is outlined (as "A Phone Header"), the header's cart
  is shown to guests too.
- Fonts: the first build used `next/font/google`, which downloads Google's files at build time; the branch now
  vendors its own subsets (section 1), which removes the network from the build and the latin-ext files that the
  rupee sign used to pull in (41 KB of serif, 17 KB of sans, 8 KB of mono on every page with a price). The display
  cut gives the big headings the optical size the design asks for; headings between 21 and 28 px use the text cut,
  so they set a little heavier than the artboards' variable font would.

## 8. Follow-ups

- Backend: `shop/payments.py` `razorpay_order_id()` answers 500 for an order without a Payment row (fixture-made
  orders only); the Bengali subset bundled for the invoice PDFs renders `.notdef` glyphs for Assamese and Bengali
  text (pre-existing: try `local("Noto Sans Bengali")` first or drop the two Bengali `@font-face` rules);
  `examleaf-web/README.md` still says Poppins serves the PDFs and the `poppins-*.woff2` files are now unused; the
  book-code throttle (5 an hour per address) is shared by every test run on one machine; `import_pincodes` belongs
  in the deploy (the e2e directory is empty, G12); the schema leaves `revise-again` and `Clip.questions` untyped and
  has no chapter lookup by number.
- Frontend: a `&reason=expired` marker in `loginUrl()` would let the log-in notice show for every client-side 401
  (today it shows when a draft waits); a 429 from the API carries DRF's own "Expected available in N seconds" in
  its detail, which every form shows, while allauth.headless's 429 has no time and gets the auth forms' `retryIn`
  wording, which `ErrorSummary retryIn` could carry to every form; `HlsVideo`
  could take event props (the course catches progress on a wrapper); header tags for the account emails need a
  product decision on the words; `docs/design/parity-nextjs.md` and the screenshots under `docs/design/screenshots/nextjs/`
  describe the old look.
- Design: the artboard's red double rule beside the account navigation and the artboard's single-column 404 rows
  are drawn more simply than the shared components allow; the page atlas (`docs/design/atlas/`) should be re-captured.
