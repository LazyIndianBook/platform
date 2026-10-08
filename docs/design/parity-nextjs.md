# Parity: the Django site's routes in the Next.js frontend

Package 8D's parity check (`docs/examleaf-phase8-nextjs-plan.md`) against section 3.1 of `coverage-matrix.md`: every public and student route of the Django site, where the Next.js frontend (`examleaf-frontend/`) answers it, checked on 2026-10-08 against the frontend's working tree and the backend at `533b784`. Statuses: **built** (same path, a page of the frontend), **redirected** (same path, a redirect in `next.config.ts` to where the frontend answers it now), **API** (a form post of the Django page: the frontend's page calls the API instead, so the path needs no page), **Django** (stays with Django behind its Caddy prefix), **not built** (with the reason).

Paths in `src/app/`: `(public)`, `(shop)`, `(account)` and `(auth)` are route groups; `(account)/account/(streamed)/` holds the account pages that wait behind the placeholder (`loading.tsx`), the two that can be missing (an order, a saved attempt) sit outside it so that they answer a real 404.

## A. Discover

| Django route | Next.js route | Status | Notes |
|---|---|---|---|
| `/` | `(public)/page.tsx` | built | Organization JSON-LD; the tiles morph into the book's cover (`Morph`) |
| `/books/<slug>/` | `(public)/books/[slug]/` | built | Book and BreadcrumbList JSON-LD |
| `/s/<code>/` | `(public)/s/[code]/` | built | any case → the printed code; the marks form is an island in `#record`; `private, no-store` once a session exists |
| `/qr/<code>.png` | | Django | `/qr/` prefix |
| `/about/` | `(public)/about/` | built | |
| `/privacy/` `/terms/` `/refunds/` `/shipping/` `/contact/` | `(public)/[page]/` | built | the API's HTML; Contact adds the support address and the form (POST `contact/`, Turnstile while on) once `config/` gives the address |
| `/offline/` | `app/offline/route.ts` | built | self-contained; Try again asks for the page again |
| `/revision/` | `(account)/revision/` | built | public and indexed; every chapter (Coming soon without a revision), the free clip by `free_preview`, store links from `config/` `app_links` |

## B. Buy

| Django route | Next.js route | Status | Notes |
|---|---|---|---|
| `/shop/` (`?kind=`) | `(shop)/shop/` | built | `?kind=` dropped (Django's page had no control for it); subject tabs by CSS |
| `/shop/category/<slug>/` | `(shop)/shop/category/[slug]/` | built | |
| `/shop/collection/<slug>/` | `(shop)/shop/collection/[slug]/` | built | |
| `/shop/<slug>/` | `(shop)/shop/[slug]/` | built | a renamed product's old slug redirects (the API's 301 `redirect_to` → 308); pictures with their AVIF/WebP sizes; `meta_title`, `meta_description`, `og_image` |
| `/shop/<slug>/review/` (POST) | | API | `products/<slug>/reviews/` from the product page |
| `/shop/<slug>/stock-alert/` (POST) | | API | `products/<slug>/stock-alert/` |
| `/shop/school-orders/` | `(shop)/shop/school-orders/` | built | |
| `/shop/pin/<pin>/` | | API | the old page's JSON; the checkout uses `shipping/quote/?pin=` |
| `/shop/media/<path>` | | Django | media |
| `/cart/` | `(shop)/cart/` | built | the shop-closed notice above the cart |
| `/cart/add/<id>/` (POST) | | API | `cart/items/` |
| `/checkout/` | `(shop)/checkout/` | built | the shop-closed notice; cash on delivery with its terms when `config/` offers it; the PIN directory's state check |
| `/checkout/<n>/pay/` | `(shop)/checkout/[number]/pay/` | built | and a guest's `/checkout/t/<token>/pay/` |
| `/checkout/<n>/paid/` (POST) | | API | `orders/<n>/payment/confirm/` |
| `/checkout/<n>/done/` | `(shop)/checkout/[number]/done/` | built | and a guest's `/checkout/t/<token>/done/` |

## C. After the order

| Django route | Next.js route | Status | Notes |
|---|---|---|---|
| `/account/orders/` | `(account)/account/(streamed)/orders/` | built | in the account's frame (side navigation) |
| `/account/orders/<n>/` | `(account)/account/orders/[number]/` | built | another customer's or a wrong number: a real 404; courses only by the API's `is_digital` |
| `/account/orders/<n>/cancel/` (POST) | | API | `orders/<n>/cancel/` |
| `/account/orders/<n>/invoice/` | → `/api/v1/orders/<n>/invoice/` | redirected | old emails |
| `/account/orders/<n>/credit-notes/<id>/` | → `/api/v1/orders/<n>/credit-notes/<id>/` | redirected | |
| `/orders/lookup/` | `(shop)/orders/lookup/` | built | |
| `/orders/t/<token>/` | `(shop)/orders/t/[token]/` | built | |
| `/orders/t/<token>/cancel/` (POST) | | API | `orders/t/<token>/cancel/` |
| `/orders/t/<token>/invoice/` | → `/api/v1/orders/t/<token>/invoice/` | redirected | |
| `/orders/t/<token>/credit-notes/<id>/` | → `/api/v1/orders/t/<token>/credit-notes/<id>/` | redirected | |
| `/account/addresses/add/`, `/account/addresses/<id>/` | → `/account/addresses/` | redirected | add, change and delete on one page |
| `/account/addresses/<id>/delete/` (POST) | | API | `addresses/<id>/` |

The frontend also answers `/orders/` and `/orders/<n>/` (redirects to My orders or the lookup).

## D. Record

| Django route | Next.js route | Status | Notes |
|---|---|---|---|
| `/account/record/` | `(account)/account/(streamed)/record/` | built | averages from `me/record/`, attempts 50 a page |
| `/account/record/add/<code>/` | → `/s/<code>/#record` | redirected | the form is on the solutions page |
| `/account/record/<id>/edit/` | `(account)/account/record/[id]/edit/` | built | a missing attempt: a real 404 |

## E. Account and data rights

| Django route | Next.js route | Status | Notes |
|---|---|---|---|
| `/account/` | `(account)/account/(streamed)/` | built | |
| `/account/teacher/` | `(account)/account/(streamed)/teacher/` | built | |
| `/account/data/` | → `/account/privacy/#data` | redirected | what the file holds from `me/export/summary/`; the password, or a log-in in the last 5 minutes for an account without one |
| `/account/delete/` | → `/account/privacy/#delete` | redirected | as Download my data |
| `/account/delete/cancel/` (POST) | | API | `DELETE me/deletion/` (Keep my account) |
| `/account/parent-consent/` (POST) | | API | `me/parent-consent/` |
| `/account/sms-updates/` (POST) | | API | `PATCH me/` |
| `/c/<token>/` | `(public)/c/[token]/` | built | works without script |

The frontend adds `/account/details/`, `/account/addresses/`, `/account/security/` (with the signed-in devices and Log out the other devices) and `/account/privacy/`, which Django kept on My account.

## F. Sign-in and recovery

| Django route | Next.js route | Status | Notes |
|---|---|---|---|
| `/account/login/` | `(auth)/account/login/` | built | |
| `/account/signup/` | `(auth)/account/signup/` | built | |
| `/account/logout/` | `(auth)/account/logout/` | built | |
| `/account/inactive/` | | not built | allauth.headless refuses a switched-off account on the log-in form itself, in its words |
| `/account/reauthenticate/` | `(auth)/account/reauthenticate/` | built | the password; an account without one logs in again |
| `/account/email/` | → `/account/security/#change-email` | redirected | |
| `/account/confirm-email/` | → `/account/verify-email/` | redirected | the 6-digit code page |
| `/account/password/change/`, `/account/password/set/` | → `/account/security/#change-password` | redirected | |
| `/account/password/reset/` | `(auth)/account/password/reset/` | built | |
| `/account/password/reset/done/` | → `/account/password/reset/` | redirected | the page says the email went |
| `/account/password/reset/key/<uid>-<key>/` | `(auth)/account/password/reset/key/[key]/` | built | `HEADLESS_FRONTEND_URLS` |
| `/account/password/reset/key/done/` | → `/account/login/` | redirected | |
| `/account/login/code/`, `/account/login/code/confirm/` | → `/account/login/` | redirected | the code is asked for and typed on the log-in page |
| `/account/phone/verify/`, `/account/phone/change/` | → `/account/security/#mobile-number` | redirected | the texted code is typed in the card |
| `/account/2fa/` | `(account)/account/(streamed)/2fa/` | built | the authenticator app (with its QR code, drawn in the browser) and the recovery codes |
| `/account/2fa/authenticate/` | `(auth)/account/2fa/authenticate/` | built | |
| `/account/2fa/reauthenticate/`, `/account/2fa/webauthn/reauthenticate/` | | not built | headless's `mfa_reauthenticate` is sent to `/account/reauthenticate/`, which asks for the password only: a staff account without one cannot pass it (staff log in with a password) |
| `/account/2fa/totp/activate/`, `/deactivate/` | → `/account/2fa/` | redirected | |
| `/account/2fa/recovery-codes/` (+ `generate/`, `download/`) | → `/account/2fa/` | redirected | shown, made again and saved as a file there |
| `/account/2fa/webauthn/` (+ `add/`, `keys/<id>/remove/`, `keys/<id>/edit/`) | → `/account/security/#passkeys` | redirected | renaming a passkey is not built (8C, on purpose) |
| `/account/2fa/webauthn/login/` | | API | headless `auth/webauthn/login` |
| `/account/3rdparty/login/cancelled/`, `/error/` | → `/account/login/` | redirected | a failed Google log-in lands on `/account/login/?error=…` |
| `/account/3rdparty/signup/` | → `/account/signup/` | redirected | the sign-up page finishes the pending provider sign-up |
| `/account/3rdparty/` | → `/account/security/#google` | redirected | |
| `/account/google/login/` (+ `callback/`, `token/`) | | Django | `/account/google/` prefix |
| `/account/register/` | → `/account/signup/` | redirected | |
| `/account/social/…` (5 routes) | | not built | Django's own redirects to the old `/account/3rdparty/…` pages; nothing links to them |

## G. Staff, H. System, I. Development

| Django route | Next.js route | Status | Notes |
|---|---|---|---|
| `/learn/preview/<clip>/` | | Django | staff player |
| `/admin/…` | | Django | |
| `/robots.txt` | `app/robots.ts` | built | |
| `/sitemap.xml` | `app/sitemap.ts` | built | the fixed pages, books and products |
| `/manifest.webmanifest` | `app/manifest.ts` | built | |
| `/sw.js` | `public/sw.js` | built | the offline page and the build's static files only |
| `/favicon.ico` | → `/favicon-32.png` | redirected | |
| `/health/`, `/health/web/` | | Django | `/api/health/` is the frontend process's own check |
| `/shop/webhooks/razorpay/` | | Django | |
| `/learn/hls/<token>/<file>` | | Django | |
| `/__debug__/…` | | Django | development only |

## Django-only routes that stay

Behind Caddy's Django prefixes (`src/lib/site.ts` `DJANGO_PREFIXES`, the Caddyfile): the admin (`/admin/`), the webhooks (`/shop/webhooks/`, `/anymail/`), health (`/health/`), media (`/shop/media/`, the storage's signed URLs), the staff clip player and its files (`/learn/preview/`, `/learn/hls/`), the Google OAuth callback (`/account/google/`), the QR PNGs (`/qr/`), the static files (`/static/`), the APIs (`/api/v1/`, `/api/schema/`, `/api/docs/`, `/api/redoc/`, `/_allauth/`) and `/sitemap-django.xml`.
