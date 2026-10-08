# ExamLeaf Next.js frontend: security review (read-only)

A review of `examleaf-frontend/` at commit `b10bde1` (Phase 8D build half), made on 8 October 2026 (IST) by reading the code and by testing the production build of 16:38 (the standalone output, `NODE_ENV=production`) on `http://localhost:3003` in front of the Django backend on 8103: the process of the first hour from the clean tree, later restarts of the same tree (after the Django pages were removed at 16:59, commit `b6b8d06`) and, from 17:46, a snapshot of `git HEAD` (`3c37394`) because another agent's unfinished edit stopped the working tree from starting. The API and allauth paths the frontend uses were the same throughout. The code read is the frontend's tree at the start of the review. Every claim below was verified in the code or by a request; nothing under `examleaf-frontend/` or `examleaf-web/` was edited, and no real payment, Turnstile, Google or email provider was contacted except where said (S3). The Lighthouse side is [audit-nextjs-lighthouse.md](audit-nextjs-lighthouse.md), the accessibility side [audit-nextjs-accessibility.md](audit-nextjs-accessibility.md).

## 1. Result in brief

The foundations are right: a per-request nonce with `'strict-dynamic'` and no `unsafe-inline` or `unsafe-eval` for scripts, every inline script carrying the right nonce, `frame-ancestors 'none'`, no token or secret in any browser storage (the session is an HttpOnly cookie, the CSRF token is checked end to end), personal pages and their client-side navigation requests `no-store`, a service worker that keeps nothing but the offline page and the hashed static files, a data cache that holds only public answers, honest error states that leak nothing, `noindex` on every private route, and an unprivileged, read-only container with no `.env`, no sources and no browser source maps.

What is wrong is found where two parts meet. Two findings are serious:

| # | Severity | Finding | Where | Verified |
|---|---|---|---|---|
| S1 | High | **Open redirect after log-in**: `?next=/..//host/path` passes `safeNext()` (which returns the protocol-relative `//host/path`), so after a genuine log-in the browser goes to another site | `src/lib/auth/next-url.ts`, used by the log-in, code and sign-in forms | unit vectors and end to end in Chrome |
| S2 | High | **Razorpay's CSP allowance is lost on client-side navigation**: the policy is per document, and every normal path into the pay page (cart, checkout, "Pay now") is a client-side navigation, so Razorpay's frame, connection and image are blocked and the payment window cannot open | `src/lib/security/csp.ts`, `cart-view.tsx`, `checkout-form.tsx`, `order-view.tsx` | Razorpay stubbed: blocked after soft navigation, allowed after a hard load |
| S3 | Medium | Razorpay's `checkout.js` loads as soon as the pay page renders (before Pay, and even when the API answers 503) and writes `rzp_*` identifiers to the browser; the privacy notice says "only the cookies the site needs" and names neither Razorpay's storage nor Turnstile nor Google | `pay-button.tsx`; `examleaf-web/pages/drafts/privacy.md` | the real script observed |
| S4 | Medium | Every anonymous server-side API call shares one DRF throttle bucket (the frontend's own address); a burst of 320 requests for pages that do not exist used it up (29 of them got Django's 429), and for about a minute every uncached anonymous page, the 404 check included, answered "cannot be reached" | `src/lib/api/server.ts` | burst test |
| S5 | Medium | A backend outage looks like a log-out (`/account/*` redirects a signed-in visitor to log in), and every "unavailable" state is HTTP 200 and indexable | `src/lib/auth/session.ts`, `Unavailable` | backend stopped |
| S6 | Low | After Log out, Back restores the signed-in public page (header, cart count) from the back/forward cache: public pages are `private, no-cache`, not `no-store` | `src/proxy.ts` | Chrome |
| S7 | Low | A malformed percent-encoding in any path (`/s/%E0%A4%A/`) answers a plain-text `500 Internal Server Error` with none of the site's headers | Next's router, `decodeURIComponent` in `/s/[code]/page.tsx` | curl |
| S8 | Low | `npm audit --omit=dev`: 4 low (one KaTeX advisory through two nested copies of 0.16.47); `trust` is not set, so not exploitable; two KaTeX versions are bundled | `package.json` | `npm audit` |
| S9 | Low | Order, consent and password-reset tokens in URL paths are written to Django's access log (and, by default, Caddy's) | logging | Django log |
| S10 | Low | The CSP is coupled to build-time settings in ways that fail quietly (Turnstile's hosts, Razorpay on every `/checkout/**` page) | `csp.ts` | code and unit run |
| S11 | Info | The app client (`/_allauth/app/v1/`) and the token exchange are reachable on the site's origin; the frontend never calls them and the exchange refuses a browser session | Caddy, `DJANGO_PREFIXES` | curl |
| S12 | Info | `Cross-Origin-Opener-Policy: same-origin` and `Permissions-Policy: payment=(self)` against Razorpay's popups and Payment Request: to be checked with a real window | `next.config.ts` | not testable here |
| S13 | Info | The consent-pending marker is the API's wording; the frontend forwards `X-Forwarded-For` and `User-Agent` as received | `errors.ts`, `server.ts` | code |

Severity: High = exploitable or breaks a core flow; Medium = real and bounded; Low = hardening; Info = to know.

## 2. The brief's checklist

| Item | Verdict | Section |
|---|---|---|
| CSP header per route: nonce present, `strict-dynamic`, Razorpay only on checkout routes, Turnstile only when configured, no `unsafe-inline` for scripts | **Passes per document**; but Razorpay's allowance does not reach a page entered by client-side navigation (S2); Razorpay is on all of `/checkout/**` (S10); Turnstile only when the build has its key (S10) | 3.1 |
| `Cache-Control` on personal against public routes, including client-side navigation requests and prefetch of personal routes | **Passes**: personal routes and their RSC requests `no-store`, public `private, no-cache`; prefetches `no-store`, identical with and without a session, no personal data. One side effect: S6 | 3.2 |
| The service worker's cache rules | **Passes**: only the offline page, two icons and `/_next/static/**`; never a page, an RSC request, the API | 3.3 |
| Redirects list; open-redirect safety of `next` | **Fails for `next`** (S1); the 25 rules of `next.config.ts` and the slash redirect are safe | 3.4 |
| Cookie handling; no token in localStorage | **Passes**: nothing of ours in any storage; Razorpay's own keys appear after the pay page (S3) | 3.5 |
| CSRF header on mutations | **Passes**: `api` and `call()` add it to every unsafe method; enforced end to end | 3.5 |
| The headless exchange not exposed to the browser | **Passes** (the frontend never calls it; it refuses a browser session) | 3.5, S11 |
| Error pages leak nothing | **Passes** with S5 and S7 (soft 200 states; a bare 500) | 3.6 |
| `noindex` on private routes | **Passes** | 3.7 |
| Personal data in metadata, JSON-LD, logs | **Passes** (S9 for tokens in Django's logs) | 3.8 |
| The consent wording matching | The sign-up, parent and consent-panel wording matches the Django site word for word; the privacy notice does not match what the pay page does (S3) | 3.9 |
| The `/api/health/` route | **Passes**: process check only, `no-store`, no data; not reachable through Caddy | 3.10 |
| Dockerfile user and image contents | **Passes**: user `node`, read-only root, no `.env`, no sources, no browser source maps (192 KB of server maps stay in the image) | 3.11 |
| `npm audit --omit=dev` | 4 low (S8) | 3.12 |
| `User-Agent` and `X-Forwarded-For` forwarding | Works as intended; trust boundary is Caddy (S13) | 3.13 |

## 3. Evidence by area

### 3.1 Content-Security-Policy

`src/proxy.ts` gives every page that is not a static file or a prefetch a fresh nonce (`base64` of a random UUID, 10 of 10 requests distinct, the same URL twice differs) and the policy of `src/lib/security/csp.ts`. Seen on the production build:

| Route class | script-src | other differences |
|---|---|---|
| every page, including 404 and the offline page | `'self' 'nonce-<nonce>' 'strict-dynamic'` | none of `'unsafe-inline'`, `'unsafe-eval'` (the latter only when `NODE_ENV=development`), no host |
| `/checkout/**` (address form, pay and done pages, an account's and a guest's) | the same + `https://checkout.razorpay.com` | `frame-src` + `api.razorpay.com`, `checkout.razorpay.com`; `connect-src` + `api.razorpay.com`, `lumberjack.razorpay.com`; `img-src` + `cdn.razorpay.com` |
| every page when the build has `NEXT_PUBLIC_TURNSTILE_SITE_KEY` (not set here; shown by running `buildCsp`) | + `https://challenges.cloudflare.com` | `frame-src` + the same host |
| https builds (run through `buildCsp`) | | `upgrade-insecure-requests`; the media host in `img-src`, `connect-src`, `media-src` |

The rest, the same everywhere: `default-src 'self'`; `style-src 'self' 'unsafe-inline'` (documented: KaTeX writes style attributes, as on the Django site); `img-src 'self' data: blob:`; `font-src 'self'`; `connect-src 'self'`; `media-src 'self' blob:`; `frame-src 'self'`; `worker-src 'self'`; `manifest-src 'self'`; `object-src 'none'`; `base-uri 'self'`; `form-action 'self' https://accounts.google.com` (the log-in with Google redirects through a form post, and `form-action` covers redirects); `frame-ancestors 'none'`.

Checks on the HTML of ten routes (anonymous and signed in): every `<script>` carries the header's nonce except `type="application/ld+json"` data blocks (0 without, 0 with another); no inline event handler, no `javascript:` URL; the only external host in any page is `checkout.razorpay.com` on the pay page; the `Link: …preload` headers carry the nonce. The other headers come from `next.config.ts` on **every** response (page, file, route handler, 404, the image optimiser, Django's answers proxied in development): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(self)`; `Strict-Transport-Security: max-age=31536000` only when `NEXT_PUBLIC_SITE_URL` is https (code; the test build is http). The one exception is the bare 500 of S7. No `Server`, `X-Powered-By` or `Via` header.

**The limit of this design is S2:** a CSP belongs to the document that was loaded, and client-side navigation does not load one.

### 3.2 Cache-Control, RSC requests and prefetch

Headers of the HTML request, of the browser's own client-side navigation requests (`?_rsc=` with `RSC: 1`, captured from Chrome, not replayed from guesses), and of the router's prefetch (`Next-Router-Prefetch: 1`, `Next-Router-Segment-Prefetch: /_tree`):

| Response | Cache-Control | Notes |
|---|---|---|
| Public pages (`/`, `/shop/`, product, `/books/`, legal, `/contact/`, 404), anonymous or signed in | `private, no-cache` | the header carries the signed-in state and the cart count, so no shared cache may keep them |
| `/revision/` and `/s/<code>/` | without a session cookie `private, no-cache`; **with** one `private, no-cache, no-store, max-age=0, must-revalidate` | solutions and entitlements are the visitor's |
| `/account/**` (login and sign-up pages too), `/cart/`, `/checkout/**`, `/orders/**` (the lookup too), `/c/**` | `private, no-cache, no-store, max-age=0, must-revalidate` | anonymous requests as well |
| Client-side navigation (RSC) of a public page | `private, no-cache` | `Vary: rsc, next-router-state-tree, next-router-prefetch, next-router-segment-prefetch, Accept-Encoding`; `text/x-component` |
| Client-side navigation (RSC) of a personal page, signed in or out | `private, no-cache, no-store, max-age=0, must-revalidate` | the signed-in answer holds the page's data (the order number), the anonymous one only the redirect to log in |
| Prefetch of any route | `private, no-cache, no-store, max-age=0, must-revalidate`, no CSP (the matcher leaves prefetches to Next) | 1.8 to 3.5 KB (`/cart/` 13.8 KB): the route's static shell; **byte-identical with and without the session cookie** for `/cart/`, `/account/record/`, `/account/orders/`, `/account/details/` and the public routes; the only personal-looking text is an order number that is part of the URL asked for |
| `/offline/` | `public, max-age=3600` | self-contained, no personal data |
| `sitemap.xml`, `robots.txt`, `manifest.webmanifest` | `public, max-age=0, must-revalidate` | |
| `/sw.js` | `no-cache` | a new release is picked up at once |
| `/api/health/` | `no-store` | |
| `/_next/static/**` | `public, max-age=31536000, immutable` | hashed names |

Prefetching personal routes is therefore safe: the account links in the header and the account navigation prefetch `/cart/`, `/account/record/`, `/account/orders/`, `/account/details/`, and each answer is the loading shell, not the visitor's data, and is never stored by a cache. (It is traffic: Lighthouse file, L8.)

**What the server keeps.** The Next data cache on disk (`.next/cache/fetch-cache`, a tmpfs in compose) held 60 entries after the whole session, all public API answers (`books/`, `qr/<code>/`, `products/`, `papers/<code>/solutions/` of the open sample, `config/`, `pages/<slug>/`): none contains the signed-in student's email, name, order number, a session or CSRF value. The code keeps to it: `publicFetch()` sends no cookies; `personalFetch()` sends them with `cache: "no-store"`; `getSolutions()` and `getReviews()` choose the personal call whenever a session exists.

**S6, the side effect.** Public pages are `private, no-cache`, which lets Chrome keep them in the back/forward cache. Signed in on `/shop/` (header "Cart 2 · Shop · My record · Account · Log out"), Log out, then Back: the page is restored from the back/forward cache (a script variable set before logging out survived) with the signed-in header and the cart count. No personal data is in it, and a click on Account is refused by the server; on a shared computer the next person still sees the last user's cart count. Fix: send `no-store` on every page while a `sessionid` cookie exists (the rule `isPersonalPage(path, hasSession)` already does it for `/s/` and `/revision/`; make `hasSession` true for all), or reload on a `pageshow` with `persisted`.

### 3.3 The service worker and browser storage

`public/sw.js`, registered only in production with `scope: "/"` and `?release=<build time>`:

- It answers nothing for non-GET, other origins, or `/account/`, `/cart/`, `/checkout/`, `/orders/`, `/api/`, `/_allauth/`, `/c/` (it does not call `respondWith`; the browser goes to the network).
- Navigations: network only, the offline page when there is none. `/_next/static/**`: cache first, filled from the network. Nothing else (so not `?_rsc=` requests, not images, not the API).
- One cache per release, older ones deleted on activation.

After a signed-in session through ten pages (home, shop, `/account/`, `/cart/`, a pay page, both papers, `/revision/`, an order, the lookup, a 404) the cache held 32 entries: `/offline/`, `/icon.svg`, `/icon-192.png` and 29 `/_next/static/**` files; no document, no `_rsc`, nothing under `/account/` or `/api/`. A solution does not outlive a log-out: it was never stored. (A personal path is not covered by the offline page either: offline, `/account/` shows the browser's own error page.)

Browser storage after that session: **no token or session value of ours** in `localStorage`, `sessionStorage` or IndexedDB (grep of `src/`: no use of any of the three; no `Authorization`, `Bearer`, JWT or `X-Session-Token` anywhere). `document.cookie` shows `csrftoken`. The keys that were there came from Razorpay's own script (S3): `rzp_device_id`, `rzp_checkout_anon_id` (localStorage), `__rzp_risk` (sessionStorage), the cookie `rzp_unified_session_id`.

### 3.4 Redirects and `next`

**`next` (S1).** `safeNext()` (`src/lib/auth/next-url.ts`) refuses a value that does not start with `/`, starts with `//`, contains `\`, parses to another origin, or points at the log-in, sign-up or log-out pages. It then returns `url.pathname + url.search + url.hash` of the *normalised* URL. Results of running the file itself:

| `next` | Returned | |
|---|---|---|
| `/account/`, `/s/PHY-E02/#record`, `/checkout/` | unchanged | fine |
| `//evil.com`, `///evil.com`, `/\evil.com`, `/\t/evil.com`, `https://evil.com`, `javascript:alert(1)`, `data:…`, `\\evil.com` | `/` | refused |
| `/%09/evil.com`, `/%5Cevil.com`, `/%2F%2Fevil.com`, `/@evil.com`, `/?x=1#//evil.com`, `/a%0d%0aSet-Cookie:x=1` | unchanged (a path on this site) | fine |
| **`/..//evil.com`, `/.//evil.com`, `/././/evil.com`, `/a/..//evil.com`, `/%2e%2e//evil.com`, `/..///evil.com`, `/account/../..//evil.com`** | **`//evil.com`, `///evil.com`** | **another site** |

The raw check `startsWith("//")` runs before the URL parser removes the dot segments; the origin check passes because the parser resolves against the base; the result begins with `//`, which a browser reads as `https://evil.com/`. **End to end:** `http://localhost:3003/account/login/?next=/..//attacker.invalid/phish`, a genuine email-code log-in, then `window.location.assign(safeNext(next))`: the browser requested `GET http://attacker.invalid/phish` as a navigation (and `/.//attacker.invalid/phish` the same), ending on Chrome's error page for the unresolvable name. The server-side `redirect(withNext(...))` is not affected (`withNext` would pass the unsafe value on as `?next=%2F%2Fevil.com`, which the next `safeNext` refuses). The consumers of the unsafe path are `login-form.tsx` (`window.location.assign(safeNext(next))`), `code-forms.tsx`, `use-auth-action.ts` (through `nextRoute`).

**`next.config.ts` redirects.** 25 rules (24 Django page addresses and `/favicon.ico`), all `permanent: false` (307), destinations fixed paths of this site or `/api/v1/…`; the captured segments only fill path segments, never the start of a destination (`/account/record/add/%2F%2Fevil.com/` goes to `/s/%2F%2Fevil.com/#record`, the invoice rules to `/api/v1/orders/<segment>/invoice/`). No loop, at most two hops (the second is the log-in for an anonymous visitor). Every documented redirect was requested anonymous and signed in, and answers as `parity-nextjs.md` says ([audit-nextjs-parity.md](audit-nextjs-parity.md)).

**The slash redirect** in `proxy.ts` builds its target from `SITE_URL`, not from the Host header (`Host: evil.example` gets `Location: /privacy/`), and Next collapses `//host` paths to `/host` before the proxy runs, so `//evil.com` is not an open redirect there either.

### 3.5 Cookies, CSRF and the authentication boundary

- **Cookies.** `sessionid`: HttpOnly, `SameSite=Lax`, `Path=/`; `csrftoken`: readable by script (the browser client needs to read it), `SameSite=Lax`. Django makes both `Secure` when `DEBUG` is off (`SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True`, `settings.py`); the test run is http. The frontend sets no cookie of its own.
- **CSRF header on mutations.** Every browser mutation goes through the shared `api` client (`csrfMiddleware` sets `X-CSRFToken` on any method but GET, HEAD and OPTIONS) or `call()` in `src/lib/auth/headless.ts` (same rule, for allauth.headless) or `ensureCsrfCookie()`; the eight `fetch(` calls of `src/` are those clients, the server-side ones and the cookie primer. Through the frontend's origin to Django: `POST cart/coupon/` without the header gives `403 CSRF Failed: CSRF token missing.`; with the token and `Origin: http://evil.example` gives `403 … Origin checking failed`; allauth.headless `DELETE …/auth/session` without the header gives 403; with token and right origin the request reaches the view (400 for the test coupon). The one Next server action (`/c/[token]` "I agree") relies on Next's Origin check; its call to Django goes without a CSRF header, which is fine for the anonymous parent it is for (DRF enforces CSRF only for a session user; a parent who is also signed in as a student in that browser would get a 403: a function, not a security issue).
- **Ownership.** Another customer's order answers 404 both through the page (`/account/orders/<n>/`) and through the API; `/account/**` and `/checkout/<n>/pay/` call `requireUser()` before anything; token pages (`/orders/t/<token>/`, `/c/<token>/`, `/checkout/t/<token>/…`) send no cookie to the API for the order and cache nothing.
- **The headless exchange.** `src/` never refers to `/_allauth/app/`, `auth/exchange/`, JWTs or `X-Session-Token`; every allauth call is `/_allauth/browser/v1`. `POST /api/v1/auth/exchange/` with only the browser's session cookie and a valid CSRF token answers **401** (it takes the app client's `X-Session-Token`). Both the app client and the exchange are reachable on the site's origin by design (S11).

### 3.6 Error pages and leakage

| Case | What the visitor gets |
|---|---|
| Unknown route, unknown book, product, paper, order link | the branded 404 (status 404, `noindex`); no detail |
| Backend stopped (public pages in the data cache) | served from the cache; the uncached ones show "ExamLeaf cannot be reached just now" with "Try again" (status 200: S5); no host, port, stack or error text in any response (grepped); the Next process logs `fetch failed … ECONNREFUSED ::1:8103` to stderr (an internal address, no personal data) |
| Backend throttling (429) | the same "cannot be reached" state (S4) |
| A page that throws | `error.tsx` / `global-error.tsx` show fixed words and the error's `digest` as "Reference:" (not triggered in the test; production Next strips the message) |
| Malformed percent-encoding | a bare `Internal Server Error` (S7) |
| `/_next/static/**.map`, `/.env`, `/package.json`, `/server.js`, `/_next/data/…`, `/api/` | 404 (the `.env` redirect to `/.env/` and then 404) |
| `/_next/image?url=https://evil.example/x.png` | 400; local paths are optimised |

### 3.7 Indexing

`robots` meta `noindex, nofollow` (`noindex, follow` on the lookup) on every private route: `/account/**` (login, sign-up, password pages, the security pages), `/cart/`, `/checkout/**`, `/orders/t/**`, `/c/**`; the 404 and the offline page `noindex`; `/s/**`, `/revision/`, the shop, the books and the legal pages are indexable. `robots.txt` disallows `/admin/ /account/ /cart/ /checkout/ /orders/ /api/ /_allauth/ /health/ /c/`. No `X-Robots-Tag` anywhere (the meta is enough for HTML). The 404 carries two robots tags (`noindex` from Next and the page's own). One caveat: the "unavailable" states of public pages keep the page's indexable metadata (S5).

### 3.8 Personal data in metadata, JSON-LD and logs

- **Metadata.** Titles and descriptions are fixed text or public catalogue data; the one dynamic private title is "Order <number>" (the number is already in the URL; the page is `noindex`). Open Graph on private pages is the site default.
- **JSON-LD.** Organization (the support address only when the config has one), Book, Product with its offer, BreadcrumbList on public pages and on `/s/`, `/revision/`: nothing personal; `<` is escaped (`<`) so no text can close the script.
- **Raw HTML.** One `dangerouslySetInnerHTML`: the legal pages' HTML from the API (`src/app/(public)/[page]/page.tsx`); the backend renders it with markdown-it with raw HTML off (links with `javascript:` are refused by the library), staff-authored, and the nonce CSP would stop a script anyway. The solutions' and products' Markdown goes through react-markdown with `skipHtml`.
- **Logs.** The Next server prints nothing per request and, in the test, only the outage's connection errors; no cookie, email or token. The Django access log has no cookie or email, but it does hold the tokens of the URLs (S9).

### 3.9 Consent wording

| Text | Django (`accounts/signup.py`, templates) | Frontend | Match |
|---|---|---|---|
| The consent box | "I have read the privacy notice and I agree that ExamLeaf may keep these details so that I can use the free solutions. If I am under 18, my parent or guardian reads the notice and ticks this box." | `signup-form.tsx` line 30 | identical |
| Under-18 notes at sign-up | "We send your parent or guardian a link to confirm your account. Until they do, you can read the solutions but not save marks or order books." / "Your parent or guardian reads the privacy notice and ticks the box below for you." | `signup-form.tsx` | identical |
| The parent's page | `parent_consent.html`: what ExamLeaf keeps, "I am their parent or guardian, and I agree", "If you do not agree, you need not do anything…" | `/c/[token]/page.tsx` | identical |
| The consent panel | `my_account.html`: Waiting / Confirmed, "agreed to the privacy notice for you", "Deleting your account (below) withdraws the consent" | `/account/privacy/page.tsx` | identical |
| The privacy notice against the frontend | "We use only the cookies the site needs to work: one that keeps you logged in and one that protects forms against misuse"; "no analytics or tracking scripts"; providers: hosting, backup, email, Razorpay, MSG91, Firebase, courier, error reporting | the pay page loads Razorpay's script, which stores identifiers (S3); Cloudflare Turnstile (when keys are set) and Google log-in are used and not named | **does not match** (S3) |

### 3.10 `/api/health/`

`GET /api/health/` answers `{"status":"ok"}` with `Cache-Control: no-store`: the process only, no version, no uptime, no dependency state (a Django outage must not restart the frontend). Caddy sends `/api/*` to Django, so the route is not reachable from outside; the container's `HEALTHCHECK` calls `127.0.0.1:3000/api/health/` directly. Nothing to fix.

### 3.11 Dockerfile and image

- **User and runtime.** Three stages on `node:24-alpine`; the last runs `USER node` (unprivileged), `NODE_ENV=production`, `HOSTNAME=0.0.0.0`; the compose service has `read_only: true`, tmpfs for `/tmp` and `/app/.next/cache`, `cap_drop: [ALL]`, `no-new-privileges`, no published port (only Caddy reaches it). `HEALTHCHECK` is the process check above.
- **Contents of what the last stage copies** (`.next/standalone`, `.next/static`, `public`, checked on the same output): 56 MB, `server.js`, a traced `node_modules` (46 MB), `.next/server`; **no** `.env*`, `.git`, keys, `src/`, `e2e/`, tests or `openapi.json` (`.dockerignore` excludes `.env*`, `.next`, `node_modules`, tests, the Dockerfile); `package.json` lists the dev dependencies' names (metadata only).
- **Source maps.** None for the browser (`.next/static` holds 0 `.map` files, no `sourceMappingURL` in any served script, `/_next/static/**.map` answers 404); 48 server-side maps (192 KB) sit in `.next/server`, are not served, and are only useful to someone who is already inside the container; delete them in the image if you want it lean.
- Not done: `docker build` (the base image would be downloaded); the build half records a successful build (331 MB) and a running container as `node`.

### 3.12 Dependencies

`npm audit --omit=dev`: **4 low-severity**, all one advisory, GHSA-238p-pmpm-9mq7 ("KaTeX: existing prototype pollution can bypass trust restrictions", `katex` 0.11.0 to 0.18.1), reached through `rehype-katex` and `micromark-extension-math` (hence `remark-math`), each of which has its own `node_modules/katex` at **0.16.47**. The top-level `katex` is 0.19.0. The advisory concerns KaTeX's `trust` option, which `markdown.tsx` leaves at its default (`{ throwOnError: false, strict: "ignore" }`), so the vulnerable path is not used; the content is staff-written. `npm audit fix --force` would install `rehype-katex@1.2.0`, a breaking downgrade: do not run it. See S8 for the real fix. No high or critical advisory.

### 3.13 `User-Agent` and `X-Forwarded-For`

`personalFetch()` forwards the visitor's cookies, `X-Forwarded-For` and `User-Agent` to Django so that allauth.usersessions records the browser and address of the device (the security page's "Where you are logged in"). Checked: a request with a spoofed `User-Agent` renamed the session's device ("Safari on iOS"); a spoofed `X-Forwarded-For` was ignored by Django in this setup (no proxy count configured, so it used the socket's address). In production `PROXY_COUNT=1` makes Django trust the last `X-Forwarded-For` entry, which is Caddy's own (Caddy replaces what an outside client sends), and the frontend has no published port; so the address shown is the real one **as long as Next is reachable only through Caddy**. A published port would let anyone choose the address that appears on the device list and that rate limits count for server-rendered requests. `publicFetch()` forwards nothing, which is S4's cause.

## 4. Findings in detail

### S1. Open redirect after log-in through `?next=` (High)

- **Where.** `safeNext()` in `src/lib/auth/next-url.ts`, called with the raw `?next=` of the log-in page by `LoginForm` (`window.location.assign(safeNext(next))`), `code-forms.tsx` and `useAuthAction` (through `nextRoute`); the sign-up, verify-email, reauthenticate and password pages use the same function.
- **Evidence.** Section 3.4: `/..//host`, `/.//host`, `/././/host`, `/a/..//host`, `/%2e%2e//host`, `/..///host` all return `//host` (or `///host`), a network-path reference. End to end, with a harmless unresolvable host: a log-in link `…/account/login/?next=/..//attacker.invalid/phish` followed by a genuine email-code log-in made Chrome request `GET http://attacker.invalid/phish` as a navigation.
- **Impact.** A phishing link on the real log-in page (`examleaf.in/account/login/?next=…`) that, after the victim logs in correctly, lands on a page of the attacker's choosing which can say "your session expired, enter your card or your parent's phone number". It needs a click on a crafted link and a log-in, and it uses the site's own trust.
- **Fix.** Check the *normalised* result, not only the raw input:
  ```ts
  const path = url.pathname + url.search + url.hash;
  if (path.startsWith("//") || path.startsWith("/\\")) return fallback; // dot segments can leave a network-path reference
  return path;
  ```
  and add the vectors above to `src/lib/lib.test.ts` (the existing tests have the `//` and `\` cases only). `new URL(path, origin).origin === origin` on the returned value is a good last assertion.

### S2. Razorpay's CSP allowance is lost on client-side navigation (High)

- **Where.** `RAZORPAY_ROUTES = /^\/checkout\//` in `src/lib/security/csp.ts` adds Razorpay's hosts to the policy of a `/checkout/**` *document*. But a policy belongs to the document that was loaded, and the paths into the pay page are client-side navigations: `cart-view.tsx` (`<Link href="/checkout/">`), `checkout-form.tsx` (`router.push("/checkout/<n>/pay/")` and the guest's `/checkout/t/<token>/pay/`), `order-view.tsx` (the `Pay now` link of an order page and of a guest's `/orders/t/<token>/`). A visitor who reached the site on `/shop/` or `/` keeps that page's policy (no Razorpay hosts) through the whole journey.
- **Evidence.** With Razorpay stubbed (the payment options answered by a fake, `checkout.js` replaced by a stub that does what the real one does on `open()`: a frame from `api.razorpay.com`, a beacon to `lumberjack.razorpay.com`, an image from `cdn.razorpay.com`; no request left the machine): starting on `/account/orders/<n>/` and following **Pay now** (a soft navigation, one document) the script loaded (`'strict-dynamic'` trusts the script `next/script` inserts) and on Pay the browser reported `frame-src blocked https://api.razorpay.com`, `connect-src blocked https://lumberjack.razorpay.com/stub`, `img-src blocked https://cdn.razorpay.com/stub.png`, with the matching console errors; the frame element existed but its content was refused. Loading `/checkout/<n>/pay/` directly (a hard load) gave no violation and all four requests went through. The e2e tests mock `checkout.js` and so cannot see it; the build half lists "the real window with keys" as unchecked.
- **Impact.** For the journey every customer takes, the Razorpay window shows nothing and online payment fails; a reload of the pay page (which is a hard load) makes it work, which hides the fault from anyone who tries twice. High because it blocks revenue; nothing is exposed.
- **Fix.** Either make every entry into `/checkout/**` a document load: a plain `<a href="/checkout/">` for the cart's Checkout, `window.location.assign(...)` instead of `router.push` for the pay and done pages in `checkout-form.tsx`, a plain `<a>` for the order page's `Pay now` (they are few); or give up the route rule and allow the four Razorpay hosts in `frame-src`, `connect-src` and `img-src` on every route (the script stays route-bound by nonce); the second is simpler and weakens the policy by four reputable payment hosts. Then test once with Razorpay's test keys in a window opened from the cart.

### S3. Razorpay loads before the click and leaves identifiers; the privacy notice does not say so (Medium)

- **Where.** `PayButton` (`src/components/shop/pay-button.tsx`) renders `<Script src="https://checkout.razorpay.com/v1/checkout.js">` in its first render (state `loading`), so the script is fetched and run when the pay page appears, before the visitor presses Pay, and it stays loaded when the API then answers 503 (not set up) or 400 (not payable).
- **Evidence.** After visiting the pay page signed in, with the real script (it was fetched from Razorpay's CDN on each visit to the pay page before the stubbed test: a handful of GETs of a public file, the review's only third-party contact), the browser held `localStorage` `rzp_device_id` and `rzp_checkout_anon_id`, `sessionStorage` `__rzp_risk` and the cookie `rzp_unified_session_id` (not HttpOnly). The privacy notice draft (`examleaf-web/pages/drafts/privacy.md`) says "We use only the cookies the site needs to work: one that keeps you logged in and one that protects forms against misuse" and "no analytics or tracking scripts", lists Razorpay only as processing payments, and lists neither Cloudflare Turnstile (its script and frame load on sign-up, log-in, coupons, checkout, contact and quotations when its key is set) nor Google log-in.
- **Fix.** Render the `<Script>` only in the `ready` state, or load it on the Pay click (insert it with the page's nonce, then open); and say in the notice what the pay page stores (Razorpay's device and risk identifiers) and name Turnstile and Google when they are on. With a DPDP-minded notice for students, the second is the one that matters.

### S4. All anonymous server-side calls count against one address (Medium)

- **Where.** `publicFetch()` (`src/lib/api/server.ts`) sends no client address (it must not: the answer is cached and shared), so Django's `AnonRateThrottle` (200 a minute per address) sees the frontend's own address for every anonymous server-rendered request, including the uncached ones: a lookup of a paper, product or book that does not exist is a Django call and a 404 that the Next data cache does not keep.
- **Evidence.** 320 requests for `/s/NOPE-<n>/` in 7.5 s: Django answered the first 291 with 404 and the last 29 with **429**, which the frontend showed as the "cannot be reached" state; straight after, `/s/NOPE-after/` and `/shop/no-such-product/` answered **200 "cannot be reached"** instead of 404, `/` (cached) was fine, and a browser's anonymous API call from the same address got `429 Request was throttled. Expected available in 29 seconds.` (in this development setup everything shares 127.0.0.1; in production the browser's own calls arrive with Caddy's `X-Forwarded-For` and have their own buckets, the server-side ones do not).
- **Impact.** Anyone can make the site show "cannot be reached" for every anonymous page that is not already in the 60-second cache (new products, a paper opened for the first time, config refreshes, the 404 check) for a minute at a time, at 200 requests a minute. Turnstile and the other limits do not apply to page loads.
- **Fix.** Give the frontend its own throttle identity: a shared-secret header that the API's throttle classes recognise (skip, or a high separate rate), or the compose network's address excluded from the anonymous scope; show a 429 as "busy, try again" rather than "cannot be reached"; and let the 404 of an unknown code be cached for a few seconds.

### S5. A backend outage looks like a log-out, and error states answer 200 (Medium)

- **Where.** `getSessionUser()` (`src/lib/auth/session.ts`) returns `null` for any failure ("the backend is down: the page renders as for a visitor"), and `requireUser()` turns `null` into a redirect to log in. The `Unavailable` and `ShopProblem` states are ordinary page output.
- **Evidence.** With the backend stopped, a signed-in visitor opening `/account/` or an order got `307 → /account/login/?next=…` (the log-in page then offers a code form that cannot work); `/cart/`, `/checkout/`, `/orders/t/<token>/` and an uncached product answered **200** "ExamLeaf cannot be reached just now", with the page's normal `robots` and `Cache-Control: private, no-cache`.
- **Impact.** Users think they were logged out and retry or reset passwords during an incident; a crawler that hits a product during an outage records a 200 "cannot be reached" page for a real URL (public pages keep their indexable metadata).
- **Fix.** Make `getSessionUser()` say "unreachable" (throw or a third value) so `requireUser()` renders `Unavailable` for it; add `robots: noindex` to the unavailable states of public pages; where a status matters, let an `error.tsx` boundary answer (500) instead of rendering the state with 200, or return 503 + `Retry-After` from a route handler for the few pages that crawlers see.

### S6. Back after Log out shows the signed-in page (Low)

Section 3.2. Fix: `no-store` for every page while a `sessionid` cookie exists, or a `pageshow` handler that reloads when `event.persisted`.

### S7. A bad escape in a path is a bare 500 (Low)

- **Where.** `/s/%E0%A4%A/`, `/books/%E0%A4%A/`, `/shop/%E0%A4%A/`, `/orders/t/%E0%A4%A/`, `/c/%E0%A4%A/` and even `/%E0%A4%A/` answer `500` with `Content-Type: text/plain`, body `Internal Server Error`, none of the site's security headers, and nothing in the Next log. `decodeURIComponent(code)` is called unguarded in `src/app/(public)/s/[code]/page.tsx`; the other routes fail inside Next's router before the proxy runs.
- **Impact.** No leak. A crawler or a scanner sending bad escapes gets 500s that look like outages in monitoring.
- **Fix.** Guard the call (`try { … } catch { notFound() }`); have Caddy answer 400 for invalid percent-encoding before it reaches Next.

### S8. KaTeX: one advisory, two versions (Low)

Section 3.12. Fix: add to `package.json`
```json
"overrides": { "katex": "$katex" }
```
so that `rehype-katex` and `micromark-extension-math` use the top-level 0.19.0 (one copy, no advisory, and the HTML the server renders then comes from the same KaTeX version as the stylesheet and fonts the page serves: today the markup is made by 0.16.47 and styled by 0.19.0's CSS), rebuild, and compare a page with many formulas.

### S9. Tokens in URL paths reach the access logs (Low)

- **Where.** The emailed links carry their secret in the path: `/orders/t/<token>/`, `/c/<token>/`, `/checkout/t/<token>/pay/`, `/account/password/reset/key/<key>/`; the frontend calls `/api/v1/orders/t/<token>/` and `/api/v1/parent-consent/<token>/`.
- **Evidence.** The Django access log of this review holds 10 lines with an order token and 18 with a parent-consent path; Caddy's `log { format json }` (`Caddyfile`) writes `request.uri` and has no filter. Cookies and email addresses are not in any access line. The browser side is right: `Referrer-Policy: same-origin` keeps the URL from other sites, and the page's metadata repeats it (`referrer: "same-origin"` on the order page).
- **Fix.** A Caddy log filter that replaces the secret part (`request>uri` with a `regexp` replacement for `/orders/t/`, `/c/`, `/checkout/t/`, `/key/`) and the same for Django's log; tokens are also valid for a limited time, which bounds the exposure.

### S10. The CSP depends on build settings that fail quietly (Low)

- **Turnstile.** The CSP adds `challenges.cloudflare.com` only when `NEXT_PUBLIC_TURNSTILE_SITE_KEY` was set at **build** time, while the widget's own key comes from `GET /api/v1/config/` at **run** time. If the backend has Turnstile keys and the frontend was built without the variable (the README lists it as a build argument), the script still loads (it is inserted by a trusted script, as in S2) but its frame is refused, no token is ever produced and sign-up, code requests, coupons, checkout and quotations fail with the server's "bot check" message. Same mechanism as S2, not exercised here (no keys). Fix: read the flag at run time in the proxy (a non-`NEXT_PUBLIC_` variable the compose file also sets) or allow the host when `config` says Turnstile is on.
- **Razorpay's reach.** The allowance is on all of `/checkout/**`, including the address form and the done pages that never load Razorpay; `/checkout/<n>/pay/` and `/checkout/t/<token>/pay/` are enough (and S2 may change the rule).
- **Styles.** `style-src 'unsafe-inline'`, documented (KaTeX's style attributes); it lets injected CSS through, which with `img-src` limited to this origin and the media host leaves little to exfiltrate.

### S11. App client and token exchange on the site's origin (Info)

`/_allauth/app/v1/` and `/api/v1/auth/exchange/` answer on the site's origin (`POST …/app/v1/auth/login` with nothing gives 400) because Caddy sends `/_allauth/*` and `/api/*` to Django for the mobile app. The frontend never refers to either (grep), and the exchange needs the app client's `X-Session-Token`: a browser session cookie plus CSRF token gets 401. Nothing to fix in the frontend; if the app should not share the website's origin, give it its own host.

### S12. COOP and Permissions-Policy against Razorpay (Info)

`Cross-Origin-Opener-Policy: same-origin` severs `window.opener` for popups a page opens (Razorpay's bank pages for some methods open one) and `Permissions-Policy: payment=(self)` keeps a cross-origin frame from using the Payment Request API (UPI and wallet shortcuts in the Razorpay frame). Both are copied from the Django site's headers, so the same behaviour is expected, but neither could be tried without a real window: check one UPI and one card payment in test mode when S2 is fixed.

### S13. Two inputs to trust (Info)

- **Consent by words.** `toApiError()` marks a refusal as `consent_pending` with `/parent or guardian has not confirmed/i`. It matches the two wordings the API sends to the frontend ("A parent or guardian has not confirmed this account yet." for orders and the course, "Your parent or guardian has not confirmed your account yet: …" for marks) and not the service layer's third ("This student's parent has not confirmed the account yet: no order until they do.", not reachable through the API today). A `code` in the API's 403 would replace the match.
- **`X-Forwarded-For` and `User-Agent`.** Section 3.13: right behind Caddy, spoofable if Next's port were published.

## 5. What this review did not cover

- **A real Razorpay window, Turnstile and Google log-in** (no keys here): S2 and S10 were shown with stubs; the real window needs a test-mode payment.
- **HTTPS**: HSTS, `Secure` cookies, `upgrade-insecure-requests` and Caddy's headers were read in code and run through `buildCsp`, not served.
- **The container**: the Dockerfile and the standalone output were read and listed; the image was not built (the base image would have to be pulled).
- **Passkeys and the second step** of staff log-in, a real parent link, the emailed links' expiry, the staff admin.
- **Load**: S4 shows the shape, not the capacity.

The scripts behind the evidence (`sec-*.mjs`, the unit runs of `safeNext` and `buildCsp`, `outage.sh`) are in [audit-scripts/nextjs/](audit-scripts/nextjs/README.md).
