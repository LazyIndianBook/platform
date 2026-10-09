# ExamLeaf frontend

The Next.js frontend of ExamLeaf (Phase 8, `docs/examleaf-phase8-nextjs-plan.md`): App Router, TypeScript (strict),
React Server Components, Tailwind CSS v4 with the ExamLeaf token layer, shadcn/ui restyled to the design system,
a typed client of the Django REST API v1 and allauth.headless. The Django backend (`../examleaf-web/`) stays the
authority for every rule (prices, stock, payments, permissions, what is open); this app shows what it answers.

Versions: Next.js 16.4 (Turbopack), React 19, Tailwind CSS 4, Node 20.9 or later (the Docker image and CI use Node 24
LTS; Node 20 is past its end of life).

## Local setup

1. The backend, from `../examleaf-web/` (its README), on port 8100, trusting the frontend's origin and host:

   ```sh
   SITE_URL=http://localhost:3000 CSRF_TRUSTED_ORIGINS=http://localhost:3000 USE_X_FORWARDED_HOST=1 \
     .venv/bin/python manage.py runserver 8100
   ```

   `SITE_URL` makes the links in emails (password reset, parent's link) point at the frontend; `USE_X_FORWARDED_HOST`
   lets the frontend's server-side calls carry the site's host (as Caddy does in production). On SQLite (the default
   database) add `DATABASE_URL='sqlite:////<path>/examleaf-web/db.sqlite3?transaction_mode=IMMEDIATE&timeout=20'`
   (a space in the path as `%20`): allauth.usersessions writes on every signed-in request, and SQLite's default
   transactions then answer "database is locked" to the frontend's parallel calls.

2. The frontend:

   ```sh
   cp .env.example .env.local
   npm install
   npm run dev            # http://localhost:3000
   ```

   Open http://localhost:3000 only (not 8100): the browser must stay on one origin for the session and CSRF cookies.
   In development `src/proxy.ts` passes Django's paths (`/api/`, `/_allauth/`, `/static/`, `/qr/` … the list in
   `src/lib/site.ts`) to `API_INTERNAL_BASE`; in production Caddy does it.

## Environment

| Variable                         | Where   | What                                                                                    |
| -------------------------------- | ------- | --------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_SITE_URL`           | build   | the public address: canonical URLs, Open Graph, sitemap, the host sent to Django        |
| `API_INTERNAL_BASE`              | runtime | Django for server components (`http://web:8000` in compose)                             |
| `INTERNAL_API_TOKEN`             | runtime | the secret shared with Django (compose, from `.env`): sent with every server-side call  |
| `NEXT_PUBLIC_API_BASE`           | build   | the browser's API base; empty = same origin (always, behind Caddy)                      |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID`    | build   | 8B's pay page; Razorpay's hosts are in the CSP of the two pay pages only                |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | build   | Turnstile's hosts in the CSP (the widget's key itself comes from `GET /api/v1/config/`) |
| `NEXT_PUBLIC_MEDIA_HOST`         | build   | the public media host (`media.examleaf.in`) for `img-src`/`connect-src`                 |

`NEXT_PUBLIC_*` values are compiled into the build. No feature flag is hard-coded: log-in methods, Google, passkeys,
SMS, Turnstile, the shop, consent mode and support contacts come from `GET /api/v1/config/` (`getConfig()` on the
server, `useConfig()` in client components).

## The API boundary

- **Browser → Django**, same origin: `/api/v1/` and `/_allauth/browser/v1/` with the session cookie and
  `X-CSRFToken` from the `csrftoken` cookie on every unsafe method (`src/lib/api/client.ts`, `src/lib/auth/headless.ts`).
- **Server components → Django**, internal network (`src/lib/api/server.ts`): `serverApi` (openapi-fetch, typed from
  `openapi.json`) with `X-Forwarded-Host`/`-Proto` set to the site's. Every call speaks for the visitor: their
  address (`X-Forwarded-For`, as Caddy gave it) and browser (`User-Agent`, which allauth.usersessions records for Log-in
  and security's devices) go with it, and `INTERNAL_API_TOKEN` (`X-Internal-Token`) makes Django believe the address,
  so its throttles count each visitor, never this server as one anonymous client. Two cache rules, nothing in between:
  - public catalogue and content: `...publicFetch("books")`: Next's data cache by URL alone (`unstable_cache`, so the
    visitor's headers do not split it), 60 s, tagged (`revalidateTag("books")` refreshes it early), only a 200 kept, no
    cookies sent;
  - anything personal: `...(await personalFetch())`: the visitor's cookies too, `cache: "no-store"`
    (`anonymousFetch()`: the same without cookies, for an order by its emailed link).
- **Errors**: every failure becomes one `ApiError` (`status`, `code`, `message`, `fields`), from DRF's and
  allauth.headless's formats alike, and status 0 when Django cannot be reached (`unwrap()`; `error.unavailable` →
  the page renders `<Unavailable/>`, which throws the "cannot be reached" error that `error.tsx` shows, so the answer
  is a 500 and never a 200 page; never stale or invented data). The session check tells an outage from a log-out
  (`requireUser()` throws the same error rather than sending anyone to log in), and while Django's `/health/web/`
  fails the visitor's own pages get a 503 with `Retry-After` from `src/proxy.ts`. A refusal because a parent's consent is awaited
  gets `code: "consent_pending"` (the API's words are its only mark), and `ErrorSummary` then offers the parent's
  link again. In the browser every 401 of `api` sends the visitor to log in and back (`sessionMiddleware`).
- **Caching of pages**: the visitor's own pages (`isPersonalPage()` in `src/lib/site.ts`: `/account/`, `/cart/`,
  `/checkout/`, `/orders/`, `/c/`, and `/s/` and `/revision/` once a session exists) keep Next's
  `private, no-cache, no-store`; every other page is `private, no-cache` (`src/proxy.ts`): the browser may keep it
  for back and forward, no shared cache may (each page carries the header's signed-in state and its own nonce).
- **Pagination**: `pageInfo()` / `pageParam()` in `src/lib/api/pagination.ts` and the `Pagination` component.
- **Cancellation**: pass `signal` in an openapi-fetch call's options (`api.GET(path, { params, signal })`).

```ts
// server component, public data
const book = await unwrap(
  serverApi.GET("/api/v1/books/{slug}/", { params: { path: { slug } }, ...publicFetch("books") }),
);
// server component, personal data
const cart = await unwrap(serverApi.GET("/api/v1/cart/", await personalFetch()));
// client component: a 401 sends the visitor to log in and back (session expiry)
const order = await personal(api.GET("/api/v1/orders/{number}/", { params: { path: { number } }, signal }));
```

### Regenerate the API types

With the backend running on 8100: `npm run api:snapshot` (saves `openapi.json`, committed) then `npm run api:types`
(writes `src/lib/api/schema.d.ts`). Commit both; `npm run typecheck` shows what the change broke.

## Authentication

`src/lib/auth/headless.ts` wraps allauth.headless's browser client: `auth.session()`, `login()`, `requestCode()` /
`confirmCode()` (email or SMS), `passkeyLogin()`, `startProviderLogin("google", callback)`, `signup()` (the student
details, consent, Turnstile token), `verifyEmail()`, `requestPasswordReset()` / `resetPassword()`, `reauthenticate()`,
`mfaAuthenticate()` / `passkeyAuthenticate()`, `logout()`. Every answer is 200 (signed in) or 401 with the pending
flow; `nextRoute(result, next)` says where to go (the destination, or `/account/verify-email/`,
`/account/2fa/authenticate/`, `/account/reauthenticate/`, the sign-up form after Google). `?next=` is kept only for a
path on this site (`safeNext()`); `withNext("/account/login/", path)` builds the links.

Server side, `getSessionUser()` (once per request) and `requireUser(path)` (redirects to log in with `next`) in
`src/lib/auth/session.ts`. Pages: `/account/login/` (SMS code first when SMS is on, email code, Google, passkey,
password), `/account/signup/`, `/account/verify-email/`, `/account/password/reset/`,
`/account/password/reset/key/<key>/` (the emailed link), `/account/reauthenticate/`, `/account/2fa/authenticate/`,
`/account/logout/`.

### Impersonation

A member of ExamLeaf's support can sign in as a customer from the staff console (`../examleaf-admin/`: a reason and a
ticket, logged and the owners told; never a member of staff or a student under 18). The console gives them a link to
`/account/impersonate/?token=…`, a token of 15 minutes; the page sends it once (`POST /api/v1/account/impersonate/`,
answered `{until, user}`) and opens `/account/`, or says plainly that the link is not valid, has expired or was used
(the 400's words). While the account manifest (`GET /api/v1/account/`, its `impersonation: {until, by} | null`, read
once per request by the root layout: `getImpersonation()`) says so, a band above every page that cannot be dismissed
says "A support colleague is viewing this account as <their masked email> until <time>", in the information colours,
with End (`DELETE /api/v1/account/impersonate/`, then `/account/login/`). The actions such a session may not take are
drawn disabled with the reason (`WhileImpersonated`, `src/components/site/impersonation.tsx`): ordering and paying,
cancelling an order, the address book's changes, the email address, mobile number, password, Google link and
passkeys, two-step log-in, the parent's link, the data download, keeping or deleting the account. The backend refuses
them anyway (403 `impersonating`); the page only says so first. Until the backend publishes the endpoint and the
manifest's field, the manifest reads as no impersonation and `e2e/impersonation.spec.ts` skips (its probe answers 404).

## Design system

Direction A, "Answer Script" (the design files in `../implementation/design/*.dc.html`, one `[data-screen-label]` per
screen; `scripts/design-shot.mjs` screenshots one artboard headlessly; the implementation report is
`../docs/design/answer-script-implementation.md`). Every page sits on paper (`#F8F5EE`) with a red double rule
(`3px double #B3342A`): section and question numbers and paper codes hang in a 120 px margin to its left, marks in a
~112 px column on the right (`Sheet`, `MarkedRow`, `Marks` in `src/components/ui/band.tsx`; `.sheet`, `.marked-row`,
`.label-mono` in `globals.css`); under 900 px the margin collapses to the rule at the left edge. Source Serif 4 sets
headings, questions, solutions and prices, Public Sans the interface, IBM Plex Mono codes and marks; Hind Siliguri stays
in every stack for Assamese and Bangla (`src/app/fonts.ts`: every family is self-hosted from `src/app/fonts/`, with its
OFL licence beside it, so a build needs nothing from the network and `font-src 'self'` holds; the files are subsets
made with fontTools from the official variable fonts: Latin, the rupee sign, arrows, ticks and superscripts, the serif
and the sans keeping their weight axis from 400 to 700, the serif in a text cut for reading and a display cut, its
optical size 60, for h1, h2 and the display sizes). Navy is the only action colour; red ink is for marks, ticks, the
margin, the stamp and one emphasis per screen, never for errors.

Tokens in `src/app/globals.css` (mapped into Tailwind's theme: `bg-primary`, `text-muted-foreground`, `font-head`,
`font-mono`, `rounded-btn`, the `nav:` / `max-nav:` 900 px breakpoint), components in `src/components/ui/` (Button,
Field, Input, Select, Checkbox, Radio, Switch, OtpInput, Card, Badge, Alert, Toaster, Dialog, Drawer, Tabs, Accordion,
Skeleton, Table, Breadcrumb, Pagination, Stepper, Progress, SubjectTile, Band/NightBand/QRule/Marker/Sheet/MarkedRow/
Marks, CoverStage, CoverPicture/NoCover, Price, EmptyState, Timeline, QrCard, SubmitButton, Morph) and the site's
frame in `src/components/site/`. Motion follows `docs/design/motion.md`: transform and opacity only, 150/220/360 ms,
everything inside `prefers-reduced-motion: no-preference`; nothing animates on load except the checkout stepper and
the order timeline, and reading content never moves. Two signature moments: a saved score's red circle
(`[data-mark-landed]`, played once after the server confirms the save) and the current question number turning red as
its row reaches the top of the screen (`animation-timeline: view()`, colour only, static elsewhere). The view
transitions of client-side navigation are React's `<ViewTransition>` (`Morph`: a Home or 404 row's cover into its
book's cover, a product card's cover into the product page's; only such a pair animates, so a form's answer changes
the page at once, and reduced motion stills it); toasts rise in as motion.md f says and leave at once. Dialogs are the
browser's own `<dialog>` (`showModal`), toasts our own few lines (6 s, paused on hover and focus). After a client-side
navigation focus moves to the new page's h1 (`RouteFocus`, in the root layout).

Dependencies beyond the framework: `hls.js` (8C, the free clips) and `lean-qr` (3.5 KB gzipped, no dependencies:
the authenticator app's QR code drawn in the browser from its `otpauth://` link, which holds the secret and so never
goes to an image service; `qrcode` would be about ten times the size with `pngjs` and `yargs`).

## Routes

- `(public)`: `/`, `/books/<slug>/`, `/s/<code>/`, `/c/<token>/` (a parent's link), `/about/`, the legal pages
  (`/privacy/`, `/terms/`, `/refunds/`, `/shipping/`, `/contact/`), `/offline/`.
- `(shop)`: `/shop/`, `/shop/<slug>/`, `/shop/category/<slug>/`, `/shop/collection/<slug>/`, `/shop/school-orders/`,
  `/cart/`, `/checkout/` (`<number>/pay/`, `<number>/done/`, `t/<token>/pay/`, `t/<token>/done/`), `/orders/`
  (`<number>/`, `lookup/`, `t/<token>/`).
- `(auth)`: `/account/login/` (Google's refused or cancelled sign-in lands here with `?error=`), `/account/signup/`,
  `/account/verify-email/`, `/account/password/reset/` (`key/<key>/`, `done/`: the new password is saved, Log in keeps
  `next`), `/account/reauthenticate/`, `/account/2fa/authenticate/`, `/account/logout/`, `/account/inactive/`,
  `/account/impersonate/` (the staff console's link: "Impersonation" above).
- `(account)`: `/account/`, `/account/record/` (`<id>/edit/`), `/account/learning/` (8E: `GET me/learning/`: the
  clip to continue with, the next three days and the exam date, the revise-again counts, progress per subject and
  chapter, what is open, the streak), `/account/orders/` (`<number>/`), `/account/details/`, `/account/addresses/`,
  `/account/security/`, `/account/2fa/`, `/account/privacy/`, `/account/teacher/`; and `/revision/` (public, with
  the signed-in student's parts; `#chapters`, `#plan` and `#app` are its sections). Behind `config.web_course`
  (`WEB_COURSE` in Django, off by default; every one of these answers 404 while it is off): the revision course on the
  web, `/revision/<subject>/<chapter>/` (the chapter's clips, notes and the Board's questions; the book-code form when
  it is locked), `…/cards/` (flash cards), `…/quiz/` (checked by the server, question by question) and
  `/account/learning/revise-again/` (what is due again, and the course settings).

## Add a route

Server component by default: `src/app/(public)/<path>/page.tsx` (public), `(auth)` (sign-in pages, noindex) or
`(account)/account/` (signed-in pages: its layout redirects to log in, marks them noindex and draws the account's
navigation; their data through `src/lib/api/account.ts`, `settle()` sending an ended session to log in and back).
A signed-in page goes in `(account)/account/(streamed)/`, behind the placeholder (`loading.tsx`), unless it can be
missing (`notFound()`, as an order or a saved attempt): once the placeholder has streamed the answer is a 200, so such
a page sits outside the group and answers a real 404. Django's old page addresses (allauth's, `/account/data/`,
invoices…) redirect to their new homes in `next.config.ts` (`docs/design/parity-nextjs.md`).
Export `metadata = pageMetadata({ title, path })` (`noindex: true` for private pages), fetch with `serverApi` +
`publicFetch`/`personalFetch`, render `<Unavailable/>` when the API cannot answer and an `EmptyState` when there is
nothing. Client components only for interaction; account forms through `useAction()`
(`src/components/account/use-action.ts`) and allauth's account endpoints through `account.*`
(`src/lib/auth/account.ts`: a 401 goes to log in, or to type the password again, and back). Paths end with `/`.

## Security

`src/proxy.ts` (Next 16's name for `middleware.ts`) gives every page a fresh nonce and its Content-Security-Policy
(`src/lib/security/csp.ts`: scripts by nonce with `'strict-dynamic'`, Razorpay only on the pay pages
`/checkout/<n>/pay/` and `/checkout/t/<token>/pay/`, Turnstile only when its key is set, `frame-ancestors 'none'`,
`form-action 'self' https://accounts.google.com`); `next.config.ts` adds the other headers Django sends. A policy
belongs to the document that was loaded, so the pay pages are always entered by a full load (the checkout form
uses `location.assign`, the order page's Pay now is a plain `<a>`, and `PayButton` reloads once a pay page whose
document began elsewhere); Razorpay's `checkout.js` is inserted only when Pay is pressed (`loadRazorpay`). Every page reads the session, so every page is rendered per request; the
visitor's own pages are answered `private, no-cache, no-store`, the others `private, no-cache` ("Caching of pages"
above). The service worker (`public/sw.js`) keeps only the offline page and the build's static files, never a page or
anything under `/account/`, `/cart/`, `/checkout/`, `/orders/`, `/api/`, `/_allauth/`.

## Tests and build

```sh
npm run lint && npm run format:check && npm run typecheck
npm test                 # Vitest: components and the API, auth and security layers
npm run build            # standalone output in .next/standalone
npm run test:e2e         # Playwright smoke tests (Chromium); see playwright.config.ts
```

The smoke tests start a seeded Django (`scripts/e2e-backend.sh`: the 13 test papers committed in
`examleaf-web/content/fixtures/papers/`, so no checkout of the books repository; the shop's catalogue with 100 copies
of each book, an open sample) and `npm run start` unless both already run; to reuse a running backend, point
`DJANGO_LOG` at its log (the tests read the emailed codes there). With `DJANGO_DATABASE_URL` on SQLite (CI's fresh
database) `playwright.config.ts` adds `transaction_mode=IMMEDIATE&timeout=20`. `e2e/states.spec.ts` starts a second
Django with a setting switched (`SHOP_OPEN=0`; then cash on delivery, Turnstile's always-pass test keys with the
widget mocked in the browser, `SUPPORT_EMAIL`, `PARENTAL_CONSENT_MODE=verified`) and a second `next start` in front
of it, on ports 20 and 21 above `E2E_API_PORT` and `E2E_WEB_PORT`. CI runs all of this in the `frontend` job of
`.github/workflows/ci.yml`; to run it as CI does: a fresh SQLite file in `DJANGO_DATABASE_URL`, `npm run build`,
then `CI=1 npm run test:e2e`.

## Deploy

`Dockerfile`: multi-stage, standalone output, the unprivileged `node` user, a health check on `/api/health/` (the
process only). `../examleaf-web/docker-compose.yml` builds it as the `frontend` service (`NEXT_PUBLIC_*` as build
arguments from `.env`: `DOMAIN`, `RAZORPAY_KEY_ID`, `TURNSTILE_SITE_KEY`, `PUBLIC_MEDIA_DOMAIN`). Caddy sends Django's
paths to `web:8000` and every other path to `PAGES_UPSTREAM`, whose default is now `frontend:3000`: the Django
server-rendered pages were removed on 8 October 2026. Set `PAGES_UPSTREAM=web:8000` only to serve an older backend
image that still has them.
