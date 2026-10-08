# ExamLeaf frontend: implementing Direction A, "Answer Script"

This package holds the code changes for `LazyIndianBook/platform/examleaf-frontend`, along with the plan for the remaining pages. The designs are in the `.dc.html` files at the project root, and `ExamLeaf Redesign - Index.dc.html` lists every route with its screen.

## Status: what's in this package, and what hasn't been checked

**Included: drop-in files, written against the source at `main` (8 Oct 2026)**

| File | Change | API of the file |
|---|---|---|
| `src/app/globals.css` | Full token swap to Direction A (paper, ink, red ink, navy). Adds the `Sheet` grid, the `marked-row` and `label-mono` utilities, and the two signature motions. The old class names (`.tile`, `.q-rule`, `.seal`, `.marker`, `.cover`, `.stage`, `.prose`, `.table-wrap`) are kept but restyled. | Same token names, plus new ones (`--red-ink`, `--paper-2`, `--rule-soft`, `--font-read`, `--font-mono`, `--margin-col`, `--marks-col`) |
| `src/app/fonts.ts` | Source Serif 4, Public Sans and IBM Plex Mono through `next/font/google`, which self-hosts them at build time. Hind Siliguri stays local in every font stack. | `fontVariables` is the same; `poppins` is kept as an alias |
| `src/components/ui/button.tsx` | Radius 4, Public Sans 700, navy primary, ink-outline secondary | unchanged |
| `src/components/ui/badge.tsx` | Square chips. Adds the `stamp` variant and the order-status variants (`awaiting`, `paid`, `progress`, `shipped`, `delivered`, `closed`), plus `STATUS_VARIANT` | additive |
| `src/components/ui/card.tsx` | Hairline sheet, no shadow, ink border on hover (no lift) | unchanged |
| `src/components/ui/band.tsx` | `QRule` in the margin's voice; `Marker` is now red italic `<em>`. Adds `Sheet`, `MarkedRow` and `Marks` | additive (`Marker` renders `<em>` instead of `<mark>`) |
| `src/components/ui/subject-tile.tsx` | Subject row: cover, serif name, mono figures | unchanged props |
| `src/components/ui/qr-card.tsx` | Paper masthead: mono eyebrow, serif title, a ruled row of facts, and the red stamp | unchanged props |
| `src/components/site/brand.tsx`, `site-header.tsx`, `nav-links.tsx`, `site-footer.tsx` | Paper header (Books · Shop · Revision course added to the nav) and the ink footer | unchanged props |
| `src/components/account/account-nav.tsx` | Margin list with a red dot. Chips on phones scroll with `scrollLeft` instead of `scrollIntoView` | unchanged |
| `src/app/(public)/s/[code]/solutions.css` | Questions and solutions in the serif, a red margin line on solutions, and the marking-step Marks column in red mono with ✓ | same class names |
| `src/app/(public)/page.tsx` | Home rebuilt on `Sheet` (Q.1–Q.5 and the closing band) | same data and fallbacks |
| `src/app/(public)/books/[slug]/page.tsx` | Book page on `Sheet`: hero (margin set to the subject code, marks `[30] [70] [3h]`), one sheet per tier, paper cells, "OPEN TO EVERYONE" in red mono, "(out of stock)" on buy buttons | same data, metadata, JSON-LD, 404 and Unavailable |
| `src/components/shop/product-card.tsx` | Flat product card: cover, mono kind label, serif title, subject chip, Out of stock as a red label | unchanged exports |
| `src/components/account/marks-form.tsx` | The circled score appears after the server confirms. A **draft in sessionStorage** survives a log-in round trip after a 401 and is cleared on success. Mono inputs, date limited to today | unchanged exports and validation |
| `src/components/ui/price.tsx`, `stepper.tsx`, `timeline.tsx`, `alert.tsx`, `empty-state.tsx` | Serif prices with the saving in green; the stepper's current step in red ink; a hairline timeline with "done/now/next" for screen readers; square alerts; empty states with a mono glyph | unchanged props (`EmptyState art` still accepted) |

**Not verified.** I couldn't run your repo from here, so `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` and `npm run test:e2e` haven't been run against these files. Treat them as a reviewed first commit, not a merged release. Expect the following:
- **Unit-test updates:** `ui.test.tsx` may check `rounded-pill` on badges or `<mark>` for `Marker`. Update those assertions to the new markup; the behaviour is unchanged.
- **Playwright screenshot baselines:** these will all change. Regenerate them after a visual review.
- **CSP:** `next/font/google` fonts are served from your own origin, so `font-src 'self'` still holds. Check `src/lib/security/csp.ts` after the build.

## How to apply

1. Branch: `git switch -c design/answer-script`.
2. Copy `implementation/examleaf-frontend/` over the repo's `examleaf-frontend/`. Only the files listed above are replaced.
3. Run `npm ci && npm run lint && npm run typecheck && npm test`, and fix any assertions as described above.
4. Run `npm run build`. It needs internet for `next/font/google`; see "Fonts offline" below if that's a problem.
5. Run `npm run test:e2e` against the seeded backend (`scripts/e2e-backend.sh`).
6. Do a visual review at 1280, 900, 390 and 320 wide, and at 400 % zoom, against the `.dc.html` artboards.
7. Deploy to staging, run Lighthouse on the budget pages (`/`, `/s/PHY-E01/`, `/shop/`, `/account/`) and compare with `docs/design/audit-nextjs-lighthouse.md`.

**Fonts offline:** download the woff2 files for Source Serif 4 (400, 600, 700, italic 600), Public Sans (400, 600, 700) and IBM Plex Mono (500, 600) into `src/app/fonts/`, together with their OFL licences. Then replace the three `next/font/google` calls with `localFont`, the way `hind` is set up.

## The remaining pages

Most pages change with no markup edits, because they read the tokens and the shared components (Button, Card, Badge, Field, Alert, Table, Accordion, Stepper, Timeline, EmptyState, Price, Breadcrumb). The table says which need a markup pass and what to change. The "Design" column names the artboard (`data-screen-label`) in the files at the project root.

| Route | Design | Markup pass |
|---|---|---|
| `/books/<slug>/` | Public · Book | Wrap the hero and each tier in `Sheet` (margins `PHY`, `E`, `M`, `H`; marks `[30] [70] [3h]`). Paper cells: `CardLink` showing code, "70 marks · 3 hours" and the "OPEN TO EVERYONE" label in red mono |
| `/s/<code>/` | Public · A Solutions, Solutions logged out, Phone solutions | Masthead comes from `QrCard`. Put the content in a `Sheet` with the margin set to the short code. Allotted marks are already `.marks`. Logged-out wall: the two-panel card ("Register once to open every solution, free", with `next` kept). Move `MarksForm` to the end of the paper as the "Record your marks" card |
| `/c/<token>/` | Public · Parent link; Gaps · Expired links | Two columns: the facts as a ruled `<dl>`, and the answer card. The expired state gets the Contact link (G5) |
| `/about/`, `/[page]/` | Public · About, Legal | `Sheet` with margin `§`. CMS HTML goes inside `.prose`, which is now in the serif. The side rail lists the page's h2s. `/shipping/` adds the rates table from `GET shipping/` (Gaps · Shipping rates) |
| `/contact/` | Public · Contact | Two columns: the contacts as a ruled list from config, and the form card (Turnstile only when its key is set) |
| `not-found`, `error`, `/offline/` | Public · 404, Unavailable and offline | `Sheet` with margin `404`/`!`. 404 lists the subjects as `SubjectTile`. Wrong `/orders/t/` links get the "Find your order" hint (G19) |
| `/shop/` and its category and collection pages | Shop · Catalogue | Subject tabs plus kind chips (closes G13). `ProductCard`: no lift, mono kind label, serif title. The no-cover card uses the subject base colour |
| `/shop/<slug>/` | Shop · Product; States · out of stock | Product options are radio cards (`choice.tsx`), with the "BEST VALUE" `Badge variant="stamp"`. The three-cell facts row (stock, delivery, cancel) |
| `/shop/school-orders/` | Shop · School orders | Two columns; the quote form has a copies-per-book grid |
| `/cart/` | Shop · Cart; Gaps · Cart coupon | Lines as ruled rows. The summary sits in a `paper-2` side column. Add a coupon field (`POST/DELETE cart/coupon/`) that shows the API's discount and its refusal |
| `/checkout/` | Shop · Checkout; States · Delivery step; Gaps · PIN autofill | Stepper bar in red for the current step. PIN autofill shows its found and not-found states (G12). Entered values are kept on Back |
| `/checkout/…/pay/`, `/done/` | Shop · Pay, Done; States · payment failed, pending | **Never show PAID before the server confirms.** The pending state is "We're confirming your payment". The failed state keeps the order and offers cash on delivery when config allows it. Pay pages keep loading fully (CSP S2) |
| `/orders/t/<token>/`, `/account/orders/<n>/` | Shop · Order; Gaps · Order refunded, Your papers | Timeline, address, payment, GST invoice, credit notes, and Cancel (a `<dialog>`). The "Your papers" block (G20) links to the open sample |
| `/orders/lookup/` | Shop · Order lookup | Unchanged behaviour (no enumeration) |
| `(auth)/*` | Auth · Login, Signup, cards; States · Password login, Google sign-up, Session expired; Gaps · Auth edge pages | Show the `next` destination as a "NEXT" chip. Methods come from config. Write the missing pages: reset done (G2/G18), inactive (G4), social cancelled and error (G23) |
| `/account/` | Account · overview | Continue clip, revise-again count, record table with an AVERAGE column, next days, latest order |
| `/account/record/`, `<id>/edit/` | Account · Record, Record edit; Gaps · Record form, filters | Use `MarkedRow` per paper with the tier averages as rows. Filters with an honest empty state (G10). The form has all four fields (date, marks with one decimal, minutes, what to revise) |
| `/account/learning/` | Account · Learning | Vertical player (hls.js, existing), plan, chapter bars with a QUIZ column |
| `/account/details/`, `addresses/`, `security/`, `2fa/`, `privacy/`, `teacher/` | Account · their artboards; Gaps · Teacher access, Data summary and deletion; States · Recovery codes | Teacher is request → checking → verified (G14). Privacy shows `me/export/summary` before the download. Deletion asks the user to type their email |
| `/revision/` | Account · Revision course | Chapter table with marks in the mono voice; the book-code form shows used and unrecognised states |

## The revision course on the web (proposed, needs a product decision)

These screens are in `ExamLeaf A - Learning (LMS).dc.html`. They use only endpoints that already exist, so the backend owns every rule and the frontend draws what it answers.

- `/revision/<subject>/<chapter>/`: `learn/chapters/<id>/` and `learn/clips/?chapter=`. Play with `HlsVideo`; progress goes through the existing Progress endpoint. Locked clips show the book-code form (`learn/redeem/`) and a link to the shop.
- `/revision/<subject>/<chapter>/cards/`: `learn/flash-cards/`. Each answer is saved as a card review. Space turns a card; 1 and 2 answer it.
- `/revision/<subject>/<chapter>/quiz/`: `learn/quiz/`. **Answers are checked on the server**, and the right/wrong state and explanation appear only after the server replies. The Check button is busy while the answer is in flight, and pressing it twice doesn't send two answers.
- `/account/learning/revise-again/`: `learn/revise-again/`. Course settings use `learn/settings/` (exam date, 10–300 minutes a day, daily reminder).
- Entitlement is checked by the API for every clip and card. The page never decides what is open.
- Put all of this behind a config flag such as `config.web_course` until the product decision is made.

## Edge cases every page must handle

| Condition | What to do |
|---|---|
| Backend unreachable (status 0) | `<Unavailable/>` and a real 5xx, never stale or made-up data. The visitor's own pages get a 503 with Retry-After from `proxy.ts` |
| Session ended (401) | Go to log in with `next`, and keep what the user typed in that tab (sessionStorage) until they come back |
| Consent pending | Disable the form and say why, with "Send the link again" (`me/parent-consent/`) |
| Throttled (429) | Say when to try again; never retry automatically |
| Validation (400) | Error summary at the top linking to each field, plus the message on the field itself |
| Slow request | Busy state on the button; no second send |
| Empty data | `EmptyState` with one next step; a filter that matches nothing says so |
| Payment unknown | The pending state, with one update; no PAID stamp and no second payment |
| Reduced motion | No motion; the press offset and focus ring stay |
| 320 px, 400 % zoom | No sideways scrolling: tables scroll inside their own box, the sheet margin collapses |
| Assamese or Bangla text | Hind Siliguri, line-height 1.8, no tracking or uppercase (handled in `:lang`) |
| Print (`/s/<code>/`) | `solutions.css` print rules: no site chrome, one page per question group |

## Design tokens (Direction A)

- **Colours:** paper `#F8F5EE` · paper 2 `#F1ECE1` · card `#FFFFFF` · ink `#1D2230` · muted text `#5B6170` · rule `#DCD4C4` · soft rule `#E6DFD1` · red ink `#B3342A` (on ink band `#E0786E`) · navy action `#0B2A5B` · leaf `#1A6E30` · control border `#7B8595` · focus `#2F8F3A` · error `#B42318` · tiers `#1B7F3B` / `#1A5FB4` / `#A0272D` · subjects `#0F3560` / `#134043` / `#2E1D65` / `#124931`
- **Type:** display serif 600 at 44–76 px (line-height 0.98) · h1 34–56 · h2 28–44 · reading serif 19/1.7 · UI Public Sans 17/15/14 · labels Plex Mono 12–15 with +0.05em tracking
- **Layout:** margin 120 · content · marks 112. Under 900 px, a 12 px double rule at the edge. Container 1200. Radius 4 (chips 3). Targets at least 44
- **Motion:** 150 / 220 / 360 ms with `cubic-bezier(.2,.7,.2,1)`, transform and opacity only. Signature moments: the saved score's red circle (`data-mark-landed`, after the server confirms), and the current question number turning red as you scroll (scroll-linked, colour only)

## Assets

The cover images (`examleaf-web/static/img/<subject>-{240,320,480}.{avif,webp}`) and the leaf mark are unchanged. There's no new imagery.
