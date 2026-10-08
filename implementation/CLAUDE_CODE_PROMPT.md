# Prompt for Claude Code: implement the ExamLeaf "Answer Script" redesign

Copy everything below the line into Claude Code, run from the root of `LazyIndianBook/platform`. First put the downloaded `implementation/` folder at the repo root, so that `implementation/design/`, `implementation/examleaf-frontend/` and `implementation/README_IMPLEMENTATION.md` exist.

---

You are implementing a full visual redesign of the ExamLeaf frontend (`examleaf-frontend/`, Next.js 16, App Router, TypeScript strict, Tailwind 4, restyled shadcn components). The Django backend (`examleaf-web/`) stays the authority for every rule. **Do not change backend behaviour, API contracts, business rules, permissions or entitlements.** This is a presentation change, plus a short list of small UI additions that use endpoints which already exist.

## Sources of truth, in this order

1. **The design files** in `implementation/design/*.dc.html`. Open them in a browser (they run as they are; `support.js` sits beside them). These are high-fidelity: match the colours, type, spacing, borders and copy exactly. Each screen is a `[data-screen-label]` element. `ExamLeaf Redesign - Index.dc.html` maps every route to its screen and lists what is open.
   - `ExamLeaf A - Components.dc.html`: tokens, type scale, the margin grid, every component and its states, and the motion rules
   - `ExamLeaf A - Public.dc.html`, `Shop.dc.html`, `Auth.dc.html`, `Account.dc.html`: the desktop pages
   - `ExamLeaf A - Phone.dc.html`, `Phone all pages.dc.html`: the 390-wide layouts
   - `ExamLeaf A - States.dc.html`, `Gaps and edge pages.dc.html`: secondary states and the missing pages
   - `ExamLeaf A - Learning (LMS).dc.html`: PROPOSED web revision course. **Build it behind a flag only; see step 6.**
2. **`implementation/README_IMPLEMENTATION.md`**: the file-by-file status, a route table describing the markup pass each page needs, the edge-case table and the tokens.
3. **`implementation/examleaf-frontend/`**: drop-in files already written against `main` (globals.css, fonts.ts, ui components, header, footer, account nav, home, book page, solutions.css, product card, marks form). They have **not** been compiled or tested. Review them, apply them, then make them pass.
4. The existing repo docs, which remain binding where the design doesn't override them: `docs/design/motion.md`, the accessibility rules in `docs/design/direction.md` (targets of at least 44 px, contrast, no hover-only actions), the security model in `examleaf-frontend/README.md` (CSP, caching rules, `?next=` safety, pay pages loaded in full) and the gap register G1–G25 in `docs/design/coverage-matrix.md`.

## The design in one paragraph

The design takes its look from the student's **answer booklet**. Every page sits on a paper background (`#F8F5EE`) with a **red double rule** (`3px double #B3342A`). Section numbers, question numbers and paper codes hang in a 120 px margin to its left. Marks hang in a ~112 px column on the right, aligned to the row they belong to. Headings, questions and solutions are set in **Source Serif 4**, the interface in **Public Sans**, and codes and marks in **IBM Plex Mono**. **Hind Siliguri** stays in every font stack for Assamese and Bangla (no letter-spacing or uppercase on that text). Navy `#0B2A5B` is the only action colour. Red ink is used only for marks, ticks, the margin, the stamp and one emphasis per screen, never for errors (errors use `#B42318` with an icon and words). Corners are 4 px; there are no soft shadows and no gradients. Signed-in pages are quieter: no stamps, smaller type, nothing moves. Under 900 px the margin collapses to the double rule at the left edge, numbers move inline, and marks stay right-aligned on their own row.

## Steps (commit after each; keep the build green)

1. **Baseline.** Create the branch `design/answer-script`. Run `cd examleaf-frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build` and record the results. Start the seeded backend (`scripts/e2e-backend.sh`) and run `npm run test:e2e`. Save screenshots of `/`, `/books/physics-2027/`, `/s/PHY-E01/`, `/shop/`, `/cart/`, `/checkout/`, `/account/login/` and `/account/` at 1280 and 390 as the "before" set.
2. **Foundation.** Copy `implementation/examleaf-frontend/` over `examleaf-frontend/`. Make lint, typecheck and the unit tests pass:
   - Where a test asserts old markup (for example `<mark>` from `Marker`, or `rounded-pill` on badges), update the assertion. Never change behaviour to satisfy a test.
   - Keep every component's exported API compatible, so pages you haven't touched still compile.
   - If `next/font/google` can't download at build time, switch the three families to `localFont`. The README explains how; add the OFL licence files.
   - Confirm the CSP still allows the fonts (`font-src 'self'`).
3. **Shared components.** Restyle the remaining `src/components/ui/*` to match the Components file, keeping each one's API: field, input, input-otp, choice, native-select, tabs, accordion, table, breadcrumb, pagination, dialog, drawer, toaster, skeleton (a still placeholder, no shimmer), cover, morph and submit-button. Every state needs a design: default, hover, focus-visible (2 px `#2F8F3A` ring with a 2 px offset), active (1 px press), selected, disabled, busy (spinner, `aria-busy`, presses swallowed), error (red border, icon and text tied to the field with `aria-describedby`) and success.
4. **Pages, in this order.** For each route, follow its row in the README's route table and its screen in the design files. Use `Sheet`, `MarkedRow` and `Marks` from `components/ui/band.tsx`.
   1. The public pages: `/s/[code]` (signed-in page, logged-out wall, printing), `/c/[token]`, `/about`, `/[page]` (including the `/shipping/` rates from `GET shipping/`), `/contact`, `not-found`, `error`, `/offline`.
   2. The shop: `/shop/` with category and collection, product, school orders, cart with coupon (`cart/coupon`), checkout with PIN autofill and the delivery step, pay, done (pending, failed and confirmed), order (by token and by account) with credit notes and the "Your papers" block, and order lookup.
   3. Sign-in: login (methods from config, the NEXT chip for `?next=`), code entry, signup with the under-18 path and Turnstile, verify email, password reset and new password, reauthenticate, 2FA, logout. Also build the pages G2, G4, G18 and G23 say are missing: reset done, account inactive, Google login cancelled, Google login error.
   4. The student area: `/account/` overview, record with filters and an honest no-match state, record edit (all four fields), learning, orders, details, addresses, security (devices, passkeys), 2FA setup and recovery codes, privacy (`me/export/summary` before the download; deletion confirmed by typing the email address), teacher (request → checking → verified; **there is no view of students**, G14) and `/revision/`.
   5. The phone layout for every page above, from the two phone files.
   6. The email templates in `examleaf-web` (order confirmation, log-in code, parent consent, shipped, password reset) and the GST invoice PDF styling, **only** if they are rendered from templates you can restyle without changing their data. If unsure, leave them and list them as follow-ups.
5. **States and resilience. Every page must handle the following:**
   - **Backend down:** `<Unavailable/>` and a real 5xx, never stale or made-up data.
   - **Session expired (401):** go to log in and come back with `next`. Text the user typed comes back (see the sessionStorage draft in `marks-form.tsx`, and reuse that pattern in checkout and the address forms).
   - **Parent consent pending:** the form is disabled and says why, with "Send the link again".
   - **Too many tries (429):** say when they can try again; never retry automatically.
   - **Validation error (400):** an error summary that links to each field, plus the message on the field itself.
   - **Slow request:** the button is busy and a second press sends nothing.
   - **Empty data:** one next step; a filter that matches nothing says so.
   - **Payment not yet confirmed:** the "We're confirming your payment" state. **Never show PAID or success before the server confirms.**
   - **Reduced motion:** no movement; presses and focus rings still work.
   - **Small screens:** at 320 px and 400 % zoom, nothing scrolls sideways; tables scroll inside their own box.
   - **Print:** the solutions page prints cleanly (rules in `solutions.css`).
6. **The proposed web revision course (LMS).** Build the chapter, flash cards, quiz, revise-again and course-settings screens from `ExamLeaf A - Learning (LMS).dc.html`. Use only the existing endpoints (`learn/chapters`, `clips`, `flash-cards`, `quiz`, `revise-again`, `plan`, `settings`, `redeem`, and progress). Put all of it behind a config flag that is **off by default** (for example `web_course` in `GET /api/v1/config/`; if adding the flag needs a backend change, add the smallest backward-compatible one and document it). Quiz answers are checked only by the server; show right or wrong only after its reply. The API decides what is open; the page never does. Don't build the AI answer checker: it isn't implemented in the backend.
7. **Motion.** Use only what `globals.css` defines: transform and opacity, 150/220/360 ms, the enter easing, and everything inside `prefers-reduced-motion: no-preference`. There are two signature moments: the saved score's red circle (`data-mark-landed`, after the server confirms) and the current question number turning red as you scroll (`animation-timeline: view()`, colour only). Nothing animates on load except the checkout stepper and the order timeline. Reading content never moves.
8. **Tests.**
   - Add or update unit tests for every changed component state: busy, error, disabled, the consent-blocked marks form, and restoring the draft.
   - Extend Playwright with: the logged-out solutions wall keeping `next`; saving marks (circle shown only after the 201); the checkout pending and failed states; the coupon being applied and refused; the record filter that matches nothing; the teacher request states; and 320 px with no sideways scroll on every page in the smoke list.
   - Regenerate the visual baselines after a human-quality review against the design files.
9. **Verify and report.** Run lint, typecheck, unit, build and e2e. Run axe (or the repo's audit scripts in `docs/design/audit-scripts/`) and Lighthouse on `/`, `/s/PHY-E01/`, `/shop/` and `/account/`, mobile preset, against the budgets in `docs/design/audit-nextjs-lighthouse.md`: LCP ≤ 2.5 s, CLS ≤ 0.1, and JavaScript no heavier than before.
   - Take "after" screenshots matching the "before" set.
   - Write `docs/design/answer-script-implementation.md` with what changed, the before and after screenshots, the test results with their numbers, and a clear list of what is **implemented and verified**, what is **implemented but not verified**, and what is **blocked** (and on what).

## Guardrails

- Change only the frontend unless a step above says otherwise. Don't touch payments, Razorpay loading or the CSP beyond what fonts need, caching rules, `proxy.ts` security logic or the auth flows' logic.
- Don't add dependencies without saying why. Don't use a component library's look as the identity. Don't use emoji, gradients, glow or blur.
- Keep copy as written in the design files and the existing pages. Where the design shows sample data (labelled SAMPLE DATA), wire the real API fields instead; never ship sample values.
- Keep every existing URL. Private pages stay `noindex`. Structured data stays accurate.
- If something in the design conflicts with how the API actually behaves, follow the API, make the UI honest about it, and note it in the report.
- Work route by route, with small commits. Run the full checks before you say anything is done.
