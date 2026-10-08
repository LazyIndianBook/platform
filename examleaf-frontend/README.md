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
   lets the frontend's server-side calls carry the site's host (as Caddy does in production).

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
| `NEXT_PUBLIC_API_BASE`           | build   | the browser's API base; empty = same origin (always, behind Caddy)                      |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID`    | build   | 8B's pay page; Razorpay's hosts are in the CSP of `/checkout/*` only                    |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | build   | Turnstile's hosts in the CSP (the widget's key itself comes from `GET /api/v1/config/`) |
| `NEXT_PUBLIC_MEDIA_HOST`         | build   | the public media host (`media.examleaf.in`) for `img-src`/`connect-src`                 |

`NEXT_PUBLIC_*` values are compiled into the build. No feature flag is hard-coded: log-in methods, Google, passkeys,
SMS, Turnstile, the shop, consent mode and support contacts come from `GET /api/v1/config/` (`getConfig()` on the
server, `useConfig()` in client components).

## The API boundary

- **Browser → Django**, same origin: `/api/v1/` and `/_allauth/browser/v1/` with the session cookie and
  `X-CSRFToken` from the `csrftoken` cookie on every unsafe method (`src/lib/api/client.ts`, `src/lib/auth/headless.ts`).
- **Server components → Django**, internal network (`src/lib/api/server.ts`): `serverApi` (openapi-fetch, typed from
  `openapi.json`) with `X-Forwarded-Host`/`-Proto` set to the site's. Two cache rules, nothing in between:
  - public catalogue and content: `...publicFetch("books")`: Next's data cache, 60 s, tagged (`revalidateTag("books")`
    refreshes it early), no cookies sent;
  - anything personal: `...(await personalFetch())`: the visitor's cookies and address forwarded, `cache: "no-store"`.
- **Errors**: every failure becomes one `ApiError` (`status`, `code`, `message`, `fields`), from DRF's and
  allauth.headless's formats alike, and status 0 when Django cannot be reached (`unwrap()`; `error.unavailable` →
  the page renders `<Unavailable/>`, never stale or invented data).
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

## Design system

Tokens in `src/app/globals.css` (from `docs/design/tokens.css`, mapped into Tailwind's theme: `bg-primary`,
`text-muted-foreground`, `font-head`, `shadow-card`, `rounded-btn`, the `nav:` / `max-nav:` 900 px breakpoint),
fonts in `src/app/fonts.ts`, components in `src/components/ui/` (Button, Field, Input, Select, Checkbox, Radio,
Switch, OtpInput, Card, Badge, Alert, Toaster, Dialog, Drawer, Tabs, Accordion, Skeleton, Table, Breadcrumb,
Pagination, Stepper, SubjectTile, Band/NightBand/QRule/Marker, CoverStage, CoverPicture/NoCover, Price,
EmptyState, Timeline, QrCard, SubmitButton) and the site's frame in `src/components/site/`. Motion follows
`docs/design/motion.md`: transform and opacity only, everything inside `prefers-reduced-motion: no-preference`.

## Add a route

Server component by default: `src/app/(public)/<path>/page.tsx` (public), `(auth)` (sign-in pages, noindex) or
`(account)` (signed-in pages; its layout redirects to log in). Export `metadata = pageMetadata({ title, path })`
(`noindex: true` for private pages), fetch with `serverApi` + `publicFetch`/`personalFetch`, render
`<Unavailable/>` when the API cannot answer and an `EmptyState` when there is nothing. Client components only for
interaction. Paths end with `/`.

## Security

`src/proxy.ts` (Next 16's name for `middleware.ts`) gives every page a fresh nonce and its Content-Security-Policy
(`src/lib/security/csp.ts`: scripts by nonce with `'strict-dynamic'`, Razorpay only on `/checkout/*`, Turnstile only
when its key is set, `frame-ancestors 'none'`, `form-action 'self' https://accounts.google.com`); `next.config.ts`
adds the other headers Django sends. Every page reads the session, so every page is rendered per request and answered
`Cache-Control: private, no-store`. The service worker (`public/sw.js`) keeps only the offline page and the build's
static files, never a page or anything under `/account/`, `/cart/`, `/checkout/`, `/orders/`, `/api/`, `/_allauth/`.

## Tests and build

```sh
npm run lint && npm run format:check && npm run typecheck
npm test                 # Vitest: components and the API, auth and security layers
npm run build            # standalone output in .next/standalone
npm run test:e2e         # Playwright smoke tests (Chromium); see playwright.config.ts
```

The smoke tests start a seeded Django (`scripts/e2e-backend.sh`) and `npm run start` unless both already run; to
reuse a running backend, point `DJANGO_LOG` at its log (the tests read the emailed codes there). CI runs all of this
in the `frontend` job of `.github/workflows/ci.yml`.

## Deploy

`Dockerfile`: multi-stage, standalone output, the unprivileged `node` user, a health check on `/api/health/` (the
process only). `../examleaf-web/docker-compose.yml` builds it as the `frontend` service (`NEXT_PUBLIC_*` as build
arguments from `.env`: `DOMAIN`, `RAZORPAY_KEY_ID`, `TURNSTILE_SITE_KEY`, `PUBLIC_MEDIA_DOMAIN`). Caddy sends Django's
paths to `web:8000` and every other path to `PAGES_UPSTREAM`: `web:8000` (the Django pages) until the frontend covers
them after packages 8B to 8D, then `PAGES_UPSTREAM=frontend:3000` in `.env` and `docker compose up -d caddy`.
