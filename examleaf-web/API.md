# ExamLeaf API (v1)

The REST API behind the ExamLeaf app: the public catalogue (boards, subjects, books, papers), the solutions (for a
signed-in student with a confirmed email address, as on the website, or for everyone while the site's solutions are
open), the student's record of attempts, the account with its data rights (Download my data, Delete my account), the
shop (books, categories, collections, cart, addresses, orders, payment with Razorpay's mobile SDK, invoices) and the
revision course (chapters, clips, quiz, flash cards, a pass plan, book codes), and for staff the insights (forecasts,
print runs, item analysis, cohorts, fraud signals). Code: `api/` (`auth.py`, `views.py`, `serializers.py`, `shop.py`,
`learn.py`) and `insights/api.py`, settings: `examleaf/api_settings.py`, URLs: `api/urls.py` under
`examleaf/api_urls.py`.

## Contents

[Conventions](#conventions) · [Endpoints](#endpoints) · [Authentication](#authentication-from-the-app) ·
[Frontend integration guide](#frontend-integration-guide) · [Profile and data rights](#profile-and-data-rights) ·
[Catalogue and solutions](#catalogue-and-solutions) · [Attempts](#attempts) · [Store catalogue](#store-catalogue) ·
[Shop](#shop) · [Revision course](#revision-course) · [Site](#site-configuration-and-legal-pages) ·
[Insights (staff)](#insights-staff) · [ERPNext sync (staff)](#erpnext-sync-staff) ·
[Support (staff)](#support-staff) · [Lists](#lists) ·
[Staff API](#staff-api) · [Errors](#errors) ·
[Rate limits](#rate-limits) · [CORS](#cors) ·
[Versioning](#versioning) · [Operations](#operations)

[Shop](#shop) · [Revision course](#revision-course) · [Shipping (staff)](#shipping-staff) ·
[Site](#site-configuration-and-legal-pages) · [Lists](#lists) ·
[Errors](#errors) · [Rate limits](#rate-limits) · [CORS](#cors) · [Versioning](#versioning) · [Operations](#operations)

## Conventions

- Base URL: `https://<domain>/api/v1/`. Every path ends with `/`; a path without it answers 404 (no redirect).
- JSON only, both ways (`Content-Type: application/json`); anything else gets 415 (request) or 406 (`Accept`). The PDF
  downloads of the shop answer whatever `Accept` says.
- Dates are ISO 8601, times with the Indian offset (`2026-10-15T10:00:00+05:30`), except `due` (revise-again) and
  `access_expiration` and `refresh_expiration` (token refresh), which are UTC and end in `Z`; marks and other decimals
  are strings (`"52.5"`); money is a decimal string in rupees (`"299.00"`), except Razorpay's own `amount`, an integer
  in paise.
- OpenAPI 3 schema: `/api/schema/` (YAML; `?format=json` for JSON). Swagger UI: `/api/docs/`. Redoc: `/api/redoc/`.
  Both pages are served by the site itself (drf-spectacular-sidecar), so the Content-Security-Policy stays strict.
- `X-Request-ID`: send a UUID and it comes back in the response and in the server's log lines (otherwise the server
  makes one). Quote it when reporting a problem.
- Examples use `curl`; the answer follows as `# status body`. `$ACCESS` is an access token.

## Endpoints

Paths are under `/api/v1/` except those of the last three rows. Who: **anyone** needs no sign-in; **signed in** needs a
valid access token (or the website's session); **confirmed** also needs a confirmed email address; a permission
(`staff.view_parcels` …) is the [Staff API](#staff-api)'s rule: a member of staff with an authenticator app holding
it, on the panel's session (or an API key), on the admin host only. **Shop open**: while
`SHOP_OPEN=0` (before the launch) changing the cart, checkout and payment answer 403
`{"detail": "The shop opens soon."}` except for staff; reading stays possible.

| Method | Path | Who | What |
|---|---|---|---|
| POST | `auth/registration/` | anyone | sign up; emails a code |
| POST | `auth/registration/verify-email/` | anyone | the emailed code; answers with the tokens and the profile |
| POST | `auth/phone/code/` | anyone | log in by SMS: asks for a code for a confirmed mobile number |
| POST | `auth/phone/confirm/` | anyone | the texted code; answers with the tokens and the profile |
| POST | `auth/login/` | anyone | email and password; answers with the tokens and the profile |
| POST | `auth/logout/` | anyone | the refresh token, refused from then on |
| POST | `auth/token/refresh/` | anyone | new access and refresh tokens |
| POST | `auth/token/verify/` | anyone | check a token |
| POST | `auth/password/reset/` | anyone | forgotten password: emails a link |
| POST | `auth/password/reset/confirm/` | anyone | the new password, with the `uid` and `token` of that link |
| POST | `auth/password/change/` | signed in | a new password |
| POST | `auth/exchange/` | an allauth.headless app session (`X-Session-Token`) | the JWT pair and the profile, after a log-in through `/_allauth/app/v1/` |
| GET PUT PATCH | `me/` | signed in | the profile; changeable: `full_name`, `phone`, `class_level`, `board`, `district`, `sms_updates` |
| POST | `me/export/` | signed in | Download my data (`password`, or a log-in in the last 5 minutes): everything kept about the user |
| GET | `me/export/summary/` | signed in | what Download my data holds: each part with its count (no password) |
| POST DELETE | `me/deletion/` | signed in | Delete my account (`password`, or a log-in in the last 5 minutes), due in 7 days; DELETE cancels |
| GET POST | `me/teacher/` | confirmed | teacher access: its status; ask for it (once) |
| POST | `me/parent-consent/` | signed in | the parent's link to confirm, again (while `consent_pending`) |
| GET POST | `me/tickets/` | signed in; POST confirmed | My requests: the customer's support tickets (number, status, dates); POST asks a new one ([Support (staff)](#support-staff)) |
| POST DELETE | `account/impersonate/` | anyone with the panel's token | a member of staff logged in as the customer: open the session (`{"token"}`), end it ([Profile and data rights](#profile-and-data-rights)) |
| GET | `me/record/` (`?subject=&tier=`) | confirmed | My record in figures: averages per tier and subject, each paper's best and latest attempt |
| GET | `me/learning/` | confirmed | the learning dashboard: what is open, progress per subject and chapter, the clip to continue with, revise-again counts, the plan's next three days, the streak |
| GET | `boards/`, `boards/<id>/` | anyone | the boards |
| GET | `subjects/` (`?board=`), `subjects/<id>/` | anyone | the subjects |
| GET | `books/`, `books/<slug>/` | anyone | books with their published papers |
| GET | `papers/`, `papers/<code>/` | anyone | papers: marks, time, instructions, `web_url`, `solutions_url` |
| GET | `papers/<code>/solutions/` | confirmed (anyone while solutions are open, and for a book's open sample) | the questions in order, each with its solution |
| GET | `qr/<code>/` | anyone | a scanned code (any case) to its paper and `solutions_url` |
| GET POST | `attempts/` | confirmed | the student's own record; POST saves an attempt |
| GET PUT PATCH DELETE | `attempts/<id>/` | confirmed | one attempt |
| GET | `products/`, `products/<slug>/` | anyone | the books and courses on sale: prices, pictures, a bundle's books, categories, attributes |
| GET | `categories/`, `categories/<slug>/` | anyone | the shop's category tree, in tree order |
| GET | `collections/`, `collections/<slug>/` | anyone | hand-picked lists of products, in the staff's order |
| GET | `cart/` | confirmed, or a visitor | the account's cart, or the visitor's guest cart (`?state=` adds the shipping) |
| POST | `cart/` | a visitor, shop open | a new guest cart and its `token`, for clients without cookies (`X-Cart-Token`) |
| POST | `cart/items/` | confirmed or a visitor, shop open | add copies of a book |
| PUT PATCH DELETE | `cart/items/<slug>/` | confirmed or a visitor, shop open | set the copies; remove the book |
| POST DELETE | `cart/coupon/` | confirmed or a visitor, shop open | use a coupon code; remove it |
| GET | `shipping/` | anyone | the delivery rates: a fee per group of states, free from a value |
| GET | `shipping/quote/` (`?pin=` or `?state=`, `?amount=`) | anyone | the delivery fee for a PIN code or state (the caller's cart, or an amount), with the PIN code's states and districts |
| GET POST | `addresses/` | confirmed | saved delivery addresses |
| GET PUT PATCH DELETE | `addresses/<id>/` | confirmed | one address |
| GET POST | `orders/` | confirmed; POST also shop open, and a visitor may POST | the customer's orders; POST is the checkout (a visitor's too) |
| GET | `orders/<number>/` | confirmed | one order |
| POST | `orders/<number>/cancel/` | confirmed | cancel (an online payment is refunded); also while the shop is closed |
| POST | `orders/<number>/payment/`, `orders/<number>/payment/confirm/` | confirmed, shop open | the options for Razorpay's SDK; its answer, checked |
| GET | `orders/<number>/invoice/`, `orders/<number>/credit-notes/<id>/` | confirmed | PDF files, not JSON |
| POST | `orders/lookup/` | anyone | a guest's order link, emailed by number and email |
| GET | `orders/t/<token>/` | anyone with the link | the order of the link in its emails, read-only |
| POST | `orders/t/<token>/payment/`, `orders/t/<token>/payment/confirm/` | anyone with the link, shop open | a guest's order: Razorpay's options; its answer, checked |
| POST | `orders/t/<token>/cancel/` | anyone with the link | cancel, as the link's page does (an online payment is refunded) |
| GET | `orders/t/<token>/invoice/`, `orders/t/<token>/credit-notes/<id>/` | anyone with the link | PDF files, not JSON |
| GET POST | `products/<slug>/reviews/` | anyone; POST confirmed buyers | approved reviews and their average; write one |
| POST | `products/<slug>/stock-alert/` | signed in | "email me when it is back", to the account's address |
| POST | `quotes/` | anyone | a school's or bookseller's request for a quotation |
| GET | `learn/chapters/` (`?subject=`), `learn/chapters/<id>/` | anyone (flags for the signed-in user) | the revision course: every chapter with Board marks, previous-year questions, whether its revision is out, its free clip, what is open; one published chapter with its clips |
| GET | `learn/clips/<id>/` | confirmed | a clip's HLS and poster links (10 minutes), notes, questions |
| POST | `learn/clips/<id>/progress/` | confirmed | how far it was watched |
| GET | `learn/quiz/?chapter=` | confirmed | one-mark quiz items (no answers) |
| POST | `learn/quiz/<id>/attempt/` | confirmed | an answer, checked on the server |
| GET | `learn/flash-cards/?chapter=` | confirmed | flash cards |
| POST | `learn/flash-cards/<id>/review/` | confirmed | "I knew it" or not |
| GET | `learn/plan/` | confirmed | the day-by-day pass plan and the minimum to pass |
| GET | `learn/revise-again/` | confirmed | wrong answers due again |
| POST | `learn/redeem/` | confirmed | a book code |
| GET | `learn/entitlements/` | confirmed | what the user may watch |
| GET PUT PATCH | `learn/settings/` | confirmed | exam date, minutes a day, the daily reminder |
| POST DELETE | `devices/` | signed in | the app's Firebase installation ID, for the reminder |
| GET | `config/` | anyone | what the server has switched on: log-in methods, Turnstile, the shop, consent mode, maintenance |
| GET | `pages/`, `pages/<slug>/` | anyone | the legal pages: Markdown, the website's HTML, version, last change |
| POST | `contact/` | anyone | the contact form: a support ticket, its number emailed to the sender |
| GET | `insights/forecasts/`, `insights/print-runs/`, `insights/backtests/` | `staff.view_insights` | the newest demand forecast (`?product=<slug>`, `?district=all` or a district), print-run advice, backtest |
| GET | `insights/item-stats/` (`?chapter=`), `insights/chapter-stats/`, `insights/cohorts/`, `insights/code-activation/` | `staff.view_insights` | the quiz's item analysis, chapter accuracy, cohorts, book codes per batch and district: aggregates only |
| GET | `insights/delivery/`, `insights/fraud-signals/` (`?open=1`), `insights/offers/` | `staff.view_insights` | days in transit per courier and district, fraud signals, what coupons and offers did |
| POST | `insights/fraud-signals/<id>/acknowledge/` | `staff.acknowledge_signal` | looked at and handled: it leaves `?open=1` |

| GET | `shipping/orders/<number>/quote/` (`?weight_g=`) | `staff.book_parcel` | the couriers for an order's parcel, ranked, with India Post's price for a prepaid order ([Shipping (staff)](#shipping-staff)) |
| GET POST | `shipping/shipments/` | `staff.view_parcels`; POST `staff.book_parcel` | parcels (`?status=&carrier=&courier_company_id=&order=&search=`); POST books one: with a courier of the quote (202) or sent by hand (201) |
| GET | `shipping/shipments/<id>/`, `shipping/shipments/<id>/events/` | `staff.view_parcels` | a parcel with its timeline, exceptions, charges and COD remittance; its timeline |
| GET POST | `shipping/shipments/<id>/label/` | `staff.book_parcel` | the label's PDF (not JSON); POST fetches it |
| POST | `shipping/shipments/<id>/pickup/`, `…/cancel/`, `…/photo/`; `…/ndr-action/` | `staff.book_parcel`; `staff.act_on_exception` | ask the courier to collect it; cancel the booking before that; the parcel's photograph (multipart); act on a failed delivery |
| POST | `shipping/manifest/` | `staff.book_parcel` | the handover list of booked parcels: the courier's PDF |
| GET POST | `shipping/exceptions/`, `shipping/exceptions/<id>/resolve/` | `staff.view_parcels`; POST `staff.act_on_exception` | what parcels need from staff, by deadline; resolve or dismiss one |
| GET POST | `shipping/cod/`, `shipping/charges/`; `shipping/cod/<id>/reconcile/` | `staff.view_cod`; POST `staff.reconcile_cod` (re-authenticated) | COD remittances; the courier account's charges and reversals; a remittance matched with the bank's credit |
| GET POST PATCH | `shipping/pickup-locations/`, `shipping/pickup-locations/sync/` | `staff.view_parcels`; changes `staff.manage_pickup_locations` | our pickup addresses; read them from the courier account |
| GET | `/api/schema/`, `/api/docs/`, `/api/redoc/` | anyone | the OpenAPI schema, Swagger UI, Redoc |
| any | `/_allauth/app/v1/…`, `/_allauth/browser/v1/…` | anyone; the account and authenticator endpoints need the signed-in session | allauth.headless: log-in, sign-up, codes, passkeys, Google, second step, email, phone, password, re-authentication, signed-in devices (`auth/sessions`); its OpenAPI file `/_allauth/openapi.json` (and `.yaml`) |
| POST | `/api/hooks/parcel-events/` | the courier, with its token in `x-api-key` | Shiprocket's tracking webhook ([Shipping (staff)](#shipping-staff)); not in the OpenAPI schema |
| POST | `/api/hooks/support-mail/` | the forwarder, with its token in `X-Support-Mail-Token` | an email to the support address ([Support (staff)](#support-staff)); not in the OpenAPI schema |
| any | `staff/…` | staff only (the panel's session, or an API key), on the admin host | the Admin Control Panel: [Staff API](#staff-api) |

## Authentication from the app

The app uses JWT: a short-lived **access** token in every request (`Authorization: Bearer <access>`) and a
long-lived **refresh** token to get new ones. The website's own pages can call the API with their session cookie
instead (with the `X-CSRFToken` header on POST, PUT, PATCH and DELETE).

| Token | Lifetime | Setting |
|---|---|---|
| access | 15 minutes | `JWT_ACCESS_MINUTES` |
| refresh | 30 days | `JWT_REFRESH_DAYS` |

**Sign up** with the same fields and rules as the website's form: class (10 or 12), board (an id from `boards/`),
date of birth, and the consent box (`consent: true`) for everyone; under 18 also a parent's or guardian's name and
phone or email (the parent ticks the consent). The answer carries a `verification_token`; a 6-digit code is
emailed. Signing up with an address that already has an account gets the same answer (its owner gets an email), so
nobody can find out who is registered.

```sh
curl -X POST https://examleaf.in/api/v1/auth/registration/ -H 'Content-Type: application/json' -d '{
  "full_name": "Rahul Das", "email": "rahul@example.com",
  "password1": "Brahmaputra-2027", "password2": "Brahmaputra-2027",
  "class_level": 12, "board": 1, "district": "Kamrup", "date_of_birth": "2010-05-14",
  "parent_name": "Anita Das", "parent_contact": "98640 12345", "consent": true}'
# 201 {"detail": "Verification e-mail sent.", "verification_token": "q3k9w0d8m2..."}
# 400 {"parent_name": ["Required for a student under 18."], "parent_contact": ["Required for a student under 18."]}
```

**Confirm the address** with the token and the code. The answer is the same as a log-in: tokens and the profile.
Three wrong codes, or 15 minutes, end the token: then log in again for a new code.

```sh
curl -X POST https://examleaf.in/api/v1/auth/registration/verify-email/ -H 'Content-Type: application/json' \
  -d '{"verification_token": "q3k9w0d8m2...", "code": "483920"}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "user": {"id": 7, "email": "rahul@example.com", "roles": ["STUDENT"], ...}}
```

**Log in** with email and password. A member of staff, and an account that has an authenticator app or a passkey, get no
tokens from `auth/login/`, `auth/phone/confirm/` or `auth/registration/verify-email/`: 403
`{"detail": "This account logs in with a second step (an authenticator app or a passkey): log in through /_allauth/app/v1/, which asks for it, then POST auth/exchange/ for the tokens."}`
(see the Frontend integration guide). If the address is not confirmed yet, the answer is
`400 {"detail": "E-mail is not verified.", "verification_token": "..."}` and a new code is emailed (at most one every 10
seconds, 5 an hour and 10 a day per address; over that, 429): show the code screen and continue with verify-email.

```sh
curl -X POST https://examleaf.in/api/v1/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email": "rahul@example.com", "password": "Brahmaputra-2027"}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "user": {...}}
```

**Log in with a code by SMS** (no password), for a student who confirmed a mobile number (on the website's My account,
or through allauth.headless's `account/phone`: see the [Frontend integration guide](#frontend-integration-guide)).
`auth/phone/code/` takes the number as people type it ("98640 12345", "+91 98640 12345", "098640 12345") and texts a
6-digit code if an account confirmed that number; every other Indian mobile number gets the same answer and no SMS.
`auth/phone/confirm/` takes the token and the code and answers as a log-in. A wrong code is `400 {"code": [...]}`; three
wrong codes, or 3 minutes, end the token: `400 {"verification_token": ["Expired. Ask for a new code."]}`. At most 3
codes an hour per number (however it is typed) and 30 an hour per client address: 429 above it. A number that has had
its SMS for the hour or the day gets 429
`{"detail": "Too many messages have gone to this number: try again tomorrow, or log in with your email."}` (see "Rate
limits"). `404` while SMS are off (`SMS_BACKEND=console` on a server).

```sh
curl -X POST https://examleaf.in/api/v1/auth/phone/code/ -H 'Content-Type: application/json' -d '{"phone": "98640 12345"}'
# 200 {"detail": "If this number is on an account, we have texted it a code.", "verification_token": "x8f2k1..."}
# 400 {"phone": ["Enter a 10-digit Indian mobile number."]}
curl -X POST https://examleaf.in/api/v1/auth/phone/confirm/ -H 'Content-Type: application/json' \
  -d '{"verification_token": "x8f2k1...", "code": "483920"}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "user": {...}}
```

**Refresh** when a request answers 401 with `"code": "token_not_valid"` (or a little before the access token runs out).
A 401 with `"code": "password_changed"` or `"user_inactive"` means that the password was changed or the account closed:
log in again, do not refresh. Every refresh returns a **new refresh token** and the old one stops working: always store
the new one, and send one refresh at a time.

```sh
curl -X POST https://examleaf.in/api/v1/auth/token/refresh/ -H 'Content-Type: application/json' -d '{"refresh": "eyJ..."}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "access_expiration": "...Z", "refresh_expiration": "...Z"}      401: log in again
```

**Log out** by sending the refresh token, which is then refused for good; forget both tokens in the app.

```sh
curl -X POST https://examleaf.in/api/v1/auth/logout/ -H 'Content-Type: application/json' -d '{"refresh": "eyJ..."}'
```

**Passwords.** `auth/password/change/` (signed in: `old_password`, `new_password1`, `new_password2`) and a password
reset end every token of the account, on every device: log in again afterwards. The owner is told by email, as on the
website. `auth/password/reset/` (`email`) always answers 200 and emails a link to the website's "new password" page,
`<SITE_URL>/account/password/reset/key/<uid>-<token>/`; an app that opens such links itself can post `uid`, `token`,
`new_password1` and `new_password2` to `auth/password/reset/confirm/`. When an account deletion is carried out
(seven days after the request), every token of the account ends too.

Log-in, log-out, sign-up, verify-email, the SMS code endpoints and password reset ignore the `Authorization` header,
so an expired token left in it does no harm there.

## Frontend integration guide

Every frontend (the website, `../examleaf-frontend/`, and the app) does what the site does through these endpoints
and allauth.headless (Django serves no page of its own); the server stays the authority for every rule (prices, stock, payments, permissions, what is open)
and frontends show what it answers.

**Feature flags.** Read `GET config/` at start-up: log-in methods, Google, passkeys, SMS, Turnstile's site key, the
shop, cash on delivery, the lowest delivery fee, whether the solutions need an account, the parent's consent mode, the
support contacts. Never hard-code one.

**Authentication boundaries.**

| Client | Signs in through | Then calls API v1 with |
|---|---|---|
| The website (Next.js, on the same origin) | `/_allauth/browser/v1/` (the session cookie; `X-CSRFToken` from the `csrftoken` cookie on every POST, PUT, PATCH, DELETE) | the same cookie and header |
| The app | `/_allauth/app/v1/` (header `X-Session-Token`), then `POST auth/exchange/` once signed in | `Authorization: Bearer <access>`, refreshed with `auth/token/refresh/` |
| The app, legacy-compatible | `auth/login/`, `auth/registration/`, `auth/phone/…` (dj-rest-auth, kept working) | the same Bearer tokens |

The browser client is same-origin only: `/_allauth/` answers no CORS (only `/api/` does, for Bearer tokens). The app
client sends no cookie and no CSRF token. allauth.headless's own OpenAPI file is `/_allauth/openapi.json` (or `.yaml`);
its answers are `{"status": 200, "data": {...}, "meta": {...}}`, and a `401` lists in `data.flows` what comes next
(`"is_pending": true` marks the step due). Keep any `meta.session_token` an answer carries (it changes at log-in) and
send it as `X-Session-Token`; `410` means the session is gone: start again. `auth/exchange/` answers like a log-in
(`access`, `refresh`, `user`); without a finished log-in (a code or a second step still due), 401; a member of staff
without an authenticator app, 403. The session stays (allauth's account endpoints need it): at log-out
`DELETE /_allauth/app/v1/auth/session` and `POST auth/logout/` with the refresh token.

**Flows** (the app's paths; the browser's are the same under `/_allauth/browser/v1/`, with the cookie instead):

1. *Code by email:* `POST auth/code/request {"email"}` → 401, `login_by_code` pending →
   `POST auth/code/confirm {"code"}` → 200 → `POST /api/v1/auth/exchange/`.
2. *Phone* (`config/` `sms`): the same with `{"phone": "98640 12345"}` (any Indian format) and the texted code. Adding or
   changing the number (signed in): `POST account/phone {"phone"}` → 202 and an SMS → `POST auth/phone/verify {"code"}`.
   A number is never taken at sign-up.
3. *Passkey:* `GET auth/webauthn/login` → `data.request_options` (the challenge; relying party: the host of SITE_URL,
   `examleaf.in`) → the platform's passkey API → `POST auth/webauthn/login {"credential"}` → exchange. Passkeys are added
   through `account/authenticators/webauthn`; an app needs its association with the domain (Android `assetlinks.json`,
   iOS web credentials).
4. *Google* (`config/` `google`): the app posts a Google ID token issued for the server's client ID,
   `POST auth/provider/token {"provider": "google", "process": "login", "token": {"client_id": "<GOOGLE_CLIENT_ID>", "id_token": "..."}}`;
   a browser posts the form `auth/provider/redirect` (`provider`, `callback_url`, `process`). A new student then gets
   `provider_signup` pending: `POST auth/provider/signup` with the student details (6).
5. *Second step* (staff, and anyone with an authenticator app): `POST auth/login {"email", "password"}` → 401,
   `mfa_authenticate` pending → `POST auth/2fa/authenticate {"code"}` (the app's code or a recovery code) → exchange.
   Staff without an app set one up first: `GET account/authenticators/totp` (404 with `meta.secret`, `meta.totp_url`)
   → `POST account/authenticators/totp {"code"}`.
6. *Sign-up:* `POST auth/signup` with `email`, `password`, `full_name`, `class_level`, `board` (an id), `date_of_birth`,
   `consent` and, under 18, `parent_name` and `parent_contact`: the website's rules, consent record and emails → 401,
   `verify_email` pending → `POST auth/email/verify {"key": "<the emailed code>"}` → exchange.

**Turnstile.** While `config/` gives a site key, send the widget's token as `turnstile` with `auth/signup`,
`auth/code/request`, `quotes/` and `contact/`, and a visitor's `cart/coupon/` and `orders/` (400 without it). The legacy endpoints
do not ask for it.

**Errors, pages, limits.** API v1 errors are DRF's ([Errors](#errors)); allauth.headless's are
`{"status": 400, "errors": [{"message", "code", "param"}]}`. Lists are paginated ([Lists](#lists)). Over a limit the
answer is 429. DRF's limits, checkout, order lookup, reviews, back-in-stock alerts, quotations and the parent's link
send `Retry-After` in seconds; allauth's (codes, password reset, wrong passwords) answer `{"detail": "..."}` without it,
and allauth.headless answers `{"status": 429}` without it ([Rate limits](#rate-limits)).

**Caching.** The public catalogue (boards, subjects, books, papers, categories, collections, legal pages) is cached on
the server for 15 minutes and answers `Cache-Control: max-age=900`, to signed-in callers too; `config/` answers
`public, max-age=300`; open solutions answer `public, max-age=300` to a visitor who is not signed in and `private` to a
signed-in user. The other answers of a signed-in session, `orders/t/<token>/` and everything under `/_allauth/` answer
`Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private`: never keep them.

## Profile and data rights

`me/` is the signed-in user: `id`, `email`, `full_name`, `phone`, `class_level`, `board` (an id), `district`,
`date_of_birth`, `parent_name`, `parent_contact`, `consent_at`, `roles` (a list of names, `["STUDENT"]`) and
`deletion_due_at` (set while a deletion waits). Changeable: `full_name`, `phone`, `class_level`, `board`, `district`
(and `sms_updates`, below).
The email address, date of birth and parent details are read-only here (the email changes after a code, on the website
or through allauth.headless's `account/email`; the others decide the consent rules).

`me/export/` is Download my data: the website's JSON file (profile, addresses, attempts, orders, consent records, the
course's data, the signed-in devices and the rest; README.md "Personal data"). `me/deletion/` is Delete my account.
Both ask for the password, as the website does; five wrong ones in an hour end the user's refresh tokens and answer
429 (see "Rate limits"). Instead of it (`password` left out or empty), a browser session that logged in or
re-authenticated in the last 5 minutes will do (allauth's records of the session, `ACCOUNT_REAUTHENTICATION_TIMEOUT`):
allauth.headless's `POST /_allauth/browser/v1/auth/reauthenticate {"password"}` or `auth/2fa/reauthenticate {"code"}`,
or a new log-in, which is the way for an account without a password (a Google sign-up: `auth/provider/redirect`
again). Otherwise `403 {"detail": "Confirm it is you: enter your password, or log in again.", "code":
"reauthentication_required"}`. A password sent is always checked (and counted). The app's Bearer tokens carry no
session: the app sends the password.

`GET me/export/summary/` says what the file holds without making it, and without the password: each part in the file's
order, in the website's words, `[{"key": "profile", "label": "Your details: …", "count": 9}, {"key": "attempts",
"label": "Marks saved in My record", "count": 12}, …]` (`count`: a list's records, the lists' total of a part made of
lists, else 1 or 0; the profile counts its filled-in details, as the website's page does).

```sh
curl -X POST https://examleaf.in/api/v1/me/deletion/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"password": "Brahmaputra-2027"}'
# 201 {"status": "pending", "requested_at": "...", "due_at": "..."}      200 with the same body if one already waits
curl -X DELETE https://examleaf.in/api/v1/me/deletion/ -H "Authorization: Bearer $ACCESS"
# 204      404 {"detail": "No account deletion is waiting."}
```

`me/` also has `consent_pending` (true while a parent's confirmation is awaited, `PARENTAL_CONSENT_MODE=verified`),
`login_phone` and `login_phone_verified` (the mobile number for log-in by SMS; read-only here, it changes through
allauth.headless's `account/phone` with a code) and `sms_updates` (order updates by SMS, changeable; true only with a
confirmed number: `400 {"sms_updates": ["Confirm a mobile number first: the updates go to it."]}`).

**Signed-in devices** (allauth.usersessions): every log-in through allauth (a browser's cookie session, the app's
`X-Session-Token` session; not the API's Bearer tokens) is listed by allauth.headless's
`GET /_allauth/browser/v1/auth/sessions` (the app: `/_allauth/app/v1/auth/sessions`):
`{"status": 200, "data": [{"id": 12, "ip": "203.0.113.7", "user_agent": "Mozilla/5.0 (Linux; Android 14) …",
"created_at": 1791431400.5, "last_seen_at": 1791435000.1, "is_current": true}, …]}` (Unix seconds; `last_seen_at`: the
latest request, `USERSESSIONS_TRACK_ACTIVITY`). `DELETE` on the same path with `{"sessions": [<ids>]}` ends those
sessions and answers the list left: Sign out the others sends every id but the current one's (the current one's logs
this browser out: 401). The API gives the address and the browser whole: show `203.0.113.x` and the browser's name. A
server that calls the API with a visitor's cookie forwards the visitor's `User-Agent` and `X-Forwarded-For`: each
request rewrites the session's. The rows are in Download my data (`sessions`), go with the account, and those of ended
sessions are dropped nightly. The website's server forwards both on every call, cookie or not, with the shared secret
`INTERNAL_API_TOKEN` in `X-Internal-Token`: only with it does the API take that `X-Forwarded-For` as the client's
address (`examleaf.middleware.FrontendClientMiddleware`), for the device list, axes, allauth's limits and every
throttle, so the anonymous limits count each visitor and never the website's server as one client.

**Teacher access** (`me/teacher/`, as on My account): `POST` asks for it once with `school_name`, `district` and
`subject` (201; again: 400); `GET` answers the request with `verified` and `verified_at` (404 until asked). Staff check
with the school; a verified teacher gets the `TEACHER` role in `me/`.

**A parent's link, again** (`me/parent-consent/`, while `consent_pending`): `parent_contact`, the one on record or a
corrected email address or mobile number (not the student's own), gets a new link to confirm; one link per ten minutes
(429), 404 when no consent is awaited.

```sh
curl -X POST https://examleaf.in/api/v1/me/teacher/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"school_name": "Cotton Collegiate H.S. School", "district": "Kamrup Metro", "subject": "Physics"}'
# 201 {"school_name": "Cotton Collegiate H.S. School", ..., "verified": false, "verified_at": null, "created": "..."}
curl -X POST https://examleaf.in/api/v1/me/parent-consent/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"parent_contact": "anita@example.com"}'
# 200 {"detail": "We have sent anita@example.com a link to confirm."}      429 within ten minutes of the last one
```

**A member of staff logged in as the customer** (research 2.7; the panel's `staff/users/<id>/impersonate/` gives the
token, with a reason and a ticket, never for staff or a student under 18). The website's page for it posts the token:
`POST account/impersonate/ {"token": "…"}` (no sign-in: the token is the credential; 20 an hour per client address,
`API_THROTTLE_IMPERSONATE`). Once per token, within its 15 minutes, while the member of staff may and is still signed
in to the panel where they asked for it: `200 {"until": "…", "user": {"id": 42, "email": "ra•••@example.com"}}`, and
the browser is logged in as the customer in a new session (whatever it was signed in as before), which ends at
`until`; otherwise `400 {"token": ["This link to log in as the customer is not valid: used, expired, ended or
forged."]}`. It is not the customer's own log-in: their last log-in and authentication records stay theirs.
While it lasts:

- allauth.headless's `auth/session` (the website's every page) gives the user `impersonation`: `{"until", "by"}` (the
  member of staff's masked address), null in any other session: show the banner on every page.
- Every payment, address, password, email, second-factor, consent and deletion change answers `403 {"code":
  "impersonating"}` (placing and paying for orders under `orders/`, `addresses/`, `auth/password/`, `me/deletion/`,
  `me/export/`, `me/parent-consent/`, allauth.headless's `account/…` and `auth/password|2fa|webauthn|reauthenticate…`);
  reading is the point.
- Each request is an audit event by the member of staff on behalf of the customer (`impersonation.request`, its
  method, path and answer's status), beside `user.impersonation_accepted` and `…_ended`.
- The customer's own device list (`auth/sessions`) shows the session as "Staff (support) until 10:45".
- It ends at `until`, with `DELETE account/impersonate/` (204; 404 when nothing is open), when the panel ends it
  (`…/impersonate/end/`), when that panel session signs out or ends, or when the customer ends it in their device
  list: the next request answers `401 {"code": "impersonation_ended"}` under `/api/` and `/_allauth/` (any other page
  goes on signed out).

## Catalogue and solutions

Only published papers appear, as on the website. The QR codes in the books encode `<SITE_URL>/s/<CODE>/`: the app reads
the code from the scanned address and asks `qr/<code>/`.

- **Boards**: `id`, `name`, `short_name`, `state`. **Subjects**: `id`, `name`, `code` (`PHY`, `CHE`, `MAT`, `BIO`),
  `board` (its short name), `class_level` (a number).
- **Books**: `id`, `slug`, `title`, `edition`, `cover` (a picture URL, or null), `subject`, and `papers` (`code`, `tier`,
  `number`, `title`, `is_published`, `is_sample`).
- **Papers** and **`qr/<code>/`**: `code`, `tier` (`E`, `M`, `H`), `number`, `title`, `book` (its slug), `subject` (its
  code), `full_marks`, `pass_marks`, `time_text`, `header` (the instruction lines and allotment tables), `is_published`,
  `is_sample` (the book's open sample: its solutions need no account), `web_url` (the page the QR code opens) and
  `solutions_url`.

```sh
curl https://examleaf.in/api/v1/books/physics-2027/
curl 'https://examleaf.in/api/v1/papers/?subject=1&tier=H&ordering=number'
curl -H "Authorization: Bearer $ACCESS" https://examleaf.in/api/v1/papers/PHY-E01/solutions/
```

`papers/<code>/solutions/` answers a plain list (not paginated) of the paper's questions in order. A question has
Markdown with `$…$` maths; `solution.html` is rendered by the site, with the maths left for KaTeX; `is_alternative`
marks the OR choice of the question before it; `number` is what the book prints:

```sh
curl -H "Authorization: Bearer $ACCESS" https://examleaf.in/api/v1/papers/PHY-E01/solutions/
# 200 [{"order": 17, "label": "2(b)", "number": "2(b)", "part_label": "",
#       "group_label": "2. Answer any ten questions from the following as directed : `2×10=20`", "is_alternative": false,
#       "text": "Give reason why the potential energy of a system of two positive point charges is always positive.",
#       "table": "", "options": [], "marks": "2",
#       "solution": {"markdown": "| Step | Marks |\n|---|---|\n| The charges repel each other, ... | 1 |\n...",
#                    "html": "<div class=\"table-scroll\"><table class=\"steps\">..."}}, ...]
```

When the site's solutions are open (`SOLUTIONS_REQUIRE_LOGIN=0`), and always for a book's open sample (`is_sample`, one
paper per book, E-01 unless staff choose another), `papers/<code>/solutions/` answers everyone
(`Cache-Control: public, max-age=300` for a visitor who is not signed in, `private` for a signed-in user); saving
attempts still needs an account. Otherwise it needs a signed-in student with a confirmed email address (401 without a
token; 403 `{"detail": "Confirm your email address first."}` with an unconfirmed one).

## Attempts

A student's own marks for a published paper: `paper` (its code), `marks_obtained` (0 to the paper's full marks, one
decimal place), `date` (default today), `time_taken_minutes`, `notes` (at most 2,000 characters); the answer adds `id`,
`subject`, `tier`, `full_marks`, `percent`, `created` and `modified`. The paper of an attempt cannot change. Filters:
`?subject=<id>&tier=E|M|H`; ordering by `date`, `marks_obtained`, `created`. At most 20 new attempts of one paper a day
(400 with the reason). While a parent's consent is awaited (`PARENTAL_CONSENT_MODE=verified`, a student under 18) no
attempt can be saved (400). Teachers cannot see their students' attempts yet: nothing links a student to a teacher (see
the TODO in `api/views.py`).

```sh
curl -X POST https://examleaf.in/api/v1/attempts/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"paper": "PHY-E01", "marks_obtained": "52.5", "time_taken_minutes": 170, "notes": "revise optics"}'
# 201 {"id": 31, "paper": "PHY-E01", "subject": "PHY", "tier": "E", "date": "2026-10-08", "marks_obtained": "52.5",
#      "full_marks": 70, "percent": 75, "time_taken_minutes": 170, "notes": "revise optics", ...}
# 400 {"marks_obtained": ["Enter marks from 0 to 70."]}
```

**My record in figures** (`me/record/`, confirmed; `?subject=<id>&tier=E|M|H` as `attempts/`): `count`, `tiers` (the
tiers attempted, Easy to Hard: `tier`, `label`, `count`, `average`: the mean of the attempts' percentages rounded, as
My record shows it), `subjects` (by name: `id`, `code`, `name`, `count`, `average`) and `papers` (by code: `paper`,
`title`, `count`, `best`: the most marks, the latest of equals, and `latest`, both attempts as above).

```sh
curl https://examleaf.in/api/v1/me/record/ -H "Authorization: Bearer $ACCESS"
# 200 {"count": 3, "tiers": [{"tier": "E", "label": "Easy", "count": 2, "average": 62}, {"tier": "M", ...}],
#      "subjects": [{"id": 1, "code": "PHY", "name": "Physics", "count": 3, "average": 65}],
#      "papers": [{"paper": "PHY-E01", "title": "...", "count": 2, "best": {"id": 31, ..., "percent": 75},
#                  "latest": {"id": 32, ..., "percent": 50}}, ...]}
```

## Store catalogue

The shop's catalogue, public and read-only. Pictures are on the media domain (`https://media.examleaf.in/products/…`,
cached a year, a new upload gets a new name) once the site uses its buckets, under
`https://examleaf.in/shop/media/products/…` before. A picture (`cover`, null without one, and each of `images`) is
`{"sources": {"image/avif": {"<width>": "<url>", …}, "image/webp": {…}}, "src", "width", "height", "alt"}`: the AVIF
and WebP sizes django-pictures makes (a cover cut to 2/3), by width in pixels, for a `<picture>`'s `<source srcset>`s
(AVIF first), and the uploaded original (`src`, with its `width` and `height`) for the `<img>`. The worker makes the
sizes a moment after an upload (404 until then). A cover's `alt` is "Cover of <title>"; a card next to the title can
use `alt=""`.

- **Products**: `slug`, `title`, `kind` (`sample-papers`, `solutions`, `bundle`, `digital`), `subject` (code), `book` (its
  slug in `books/`), `isbn`, `pages`, `description` (Markdown), `cover` and `images` (above), `mrp`, `price`,
  `saving_percent`, `gst_rate`, `hsn_code`, `in_stock` (whether copies can be ordered; a bundle needs each of its
  books; always true for a digital product and for a bundle of digital products only; the number of copies is not given), `bundle_items` (`product`, `title`,
  `quantity`), `categories` (slugs), `attributes` (`code`, `name`, `value`: what the product's type defines, e.g.
  edition year, language, board), `related` (slugs of the products shown with it), `web_url`, and for the page's
  `<head>`: `meta_title` and `meta_description` (what staff wrote for search engines; `""` when nothing is written:
  the website then uses the title, and its own sentence) and `og_image` (the link preview, 1200×630, the cover with the
  title; null until the worker has made it). The old slug of a renamed product answers `301` with `Location:
  …/api/v1/products/<new slug>/` and `{"redirect_to": "<new slug>"}` for a client that does not follow redirects (the
  website's `/shop/<old slug>/` redirects too); once that product is off sale, 404.
- **Categories**: `slug`, `name`, `description` (Markdown), `depth` (1 at the top), `parent` (the slug of the category
  above it, null at the top), `web_url`.
- **Collections**: `slug`, `name`, `description`, `products` (slugs, in order; products off sale left out), `web_url`.

Filters on `products/`: `?kind=`, `?subject=<id>`, `?search=` (title), `?ordering=title|price`, `?category=<slug>` (its
sub-categories included), `?collection=<slug>`, and `?attr_<code>=<value>` for any attribute, several combined with AND
(at most five in a request: 400). Values are compared as the attribute keeps them: numbers as numbers
(`?attr_year=2027.0` finds 2027), text and choices in any case, yes/no attributes as `yes`/`no` (`true`, `false`, `1`,
`0` too). An unknown attribute, or a value of the wrong kind, finds nothing. Categories and collections are cached for
15 minutes, as the books are.

```sh
curl 'https://examleaf.in/api/v1/products/?category=class-12&attr_language=Assamese&attr_year=2027'
curl https://examleaf.in/api/v1/categories/
# 200 {"count": 4, ..., "results": [{"slug": "books", "name": "Books", "description": "", "depth": 1, "parent": null,
#      "web_url": "https://examleaf.in/shop/category/books/"}, {"slug": "class-12", ..., "depth": 2, "parent": "books"}, ...]}
curl https://examleaf.in/api/v1/products/physics-sample-papers-2027/
# 200 {"slug": "physics-sample-papers-2027", ..., "cover": {"sources": {"image/avif": {"200": ".../2_3/200w.avif", ...},
#      "image/webp": {...}}, "src": "https://media.examleaf.in/products/physics-2027.jpg", "width": 1600,
#      "height": 2400, "alt": "Cover of ..."}, ..., "meta_title": "...", "meta_description": "...",
#      "og_image": "https://media.examleaf.in/og/physics-sample-papers-2027.jpg"}
curl -i https://examleaf.in/api/v1/products/physics-sample-papers-2026/      # renamed since
# 301 Location: https://examleaf.in/api/v1/products/physics-sample-papers-2027/
#     {"redirect_to": "physics-sample-papers-2027"}
```

**Digital products** (`kind` `digital`: a revision pass, alone or in a bundle with a book) have no stock and ship
nothing: the cart keeps one of each (quantity 1); a cart of digital products only (a bundle of digital products counts
too) has no shipping; cash on delivery answers 400
(`"Cash on delivery is for printed books: please pay online for the course."`). Once paid, the course opens in the
buyer's account (`GET learn/entitlements/`) and an order of digital products only reads "delivered" at once; cancelling
it, or a full refund, closes the course again.

## Shop

The website's shop, for the app: the same prices, stock, coupons, offers, shipping rates, emails and order pages.
Customer data (cart, addresses, orders) needs a signed-in account with a confirmed email address; another customer's
address or order answers 404. Visitors without an account have a guest cart and check out as guests (see "Guests"
below); a signed-in user whose email address is not confirmed still gets 403 for the cart. While the shop is closed (`SHOP_OPEN=0`) the endpoints that change the cart, check out or pay answer 403 (see "Endpoints");
products, the cart, addresses and orders can still be read, and an order can still be cancelled.

**Cart**: every answer is the whole cart at today's prices: `items` (`product`, `title`, `price`, `quantity`, `total`),
`count`, `coupon`, `coupon_problem` (why the coupon does not apply now), `subtotal`, `savings`, `discount`, `shipping`
(null unless `?state=AS`, a two-letter state code, is given), `total`, `problems` (books off sale or short of stock,
which stop the checkout). `savings` is a list of `{"label", "amount"}`: the coupon ("Coupon WELCOME10") and each
automatic offer by its name ("Board 2027 offer"), and "Discount" on orders made by staff; `discount` is their sum.
Offers apply by themselves, after the coupon (no code to type), as soon as they apply.

```sh
curl -X POST https://examleaf.in/api/v1/cart/items/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"product": "physics-sample-papers-2027", "quantity": 2}'    # adds 2 copies (at most 20 of a book)
curl -X PATCH https://examleaf.in/api/v1/cart/items/physics-sample-papers-2027/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"quantity": 1}'   # sets the copies; 0, or DELETE, removes the book
curl -X POST 'https://examleaf.in/api/v1/cart/coupon/?state=AS' -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"code": "welcome10"}'
# 200 {"items": [...], "count": 3, "coupon": "WELCOME10", "coupon_problem": null, "subtotal": "897.00",
#      "savings": [{"label": "Coupon WELCOME10", "amount": "89.70"}, {"label": "Board 2027 offer", "amount": "80.73"}],
#      "discount": "170.43", "shipping": "0.00", "total": "726.57", "problems": []}
# 400 {"code": ["This code cannot be applied to this cart."]}   whatever the reason: unknown, expired, used up, too
#     small a cart; 10 codes an hour per user (429 after)
```

**Addresses**: `id`, `name`, `phone` (a 10-digit Indian mobile number; answered as `+919864012345`), `line1`, `line2`,
`city`, `district`, `state` (two-letter code, `AS`), `pin` (6 digits), `is_default` (one address at most), `created`,
`modified`. Once the India Post directory is loaded, the state must be the PIN code's
(`400 {"state": ["PIN code 781001 is in Assam."]}`; PIN codes missing from the directory are not checked). To fill in
the district and state from a PIN code, call `GET shipping/quote/?pin=781001` (below); a few PIN codes lie in two
states.

**Shipping**: `GET shipping/` (anyone, `Cache-Control: public, max-age=300`) lists the delivery rates the checkout
uses: `rates` (`name`, `states`, two-letter codes, `[]` for every state no other rate names; `fee`; `free_above`, the
value of books from which it ships free, or null), and `fee_from` and `free_above`, the lowest of each (null without
rates; `config/` repeats these two as `shipping`). The fee is flat per order: there is no weight. Courses alone ship
free.
`GET shipping/quote/` (anyone; never cached) is the checkout's delivery step: `?pin=` (6 digits) and/or `?state=`
(a two-letter code; 400 when it is not the PIN code's) and optionally `?amount=` (rupees of books after discounts;
without it, the caller's cart: the account's, or a visitor's by the session or `X-Cart-Token`). The answer: `pin`,
`states` and `districts` (the PIN code's in the India Post directory, `[]` when it is not there or none is loaded),
`state` (the one the fee is for: `?state=`, or the PIN code's only state; null when unknown or when the PIN code lies
in two states: ask), `amount`, `fee` (null while `state` is), `free_above` (that state's rate's). The cart's own
`?state=` gives the same fee inside the cart's totals.

```sh
curl 'https://examleaf.in/api/v1/shipping/quote/?pin=781001'
# 200 {"pin": "781001", "states": ["AS"], "districts": ["Kamrup Metro"], "state": "AS", "amount": "299.00",
#      "fee": "40.00", "free_above": "499.00"}
```

**Checkout**: `POST orders/` with `address` (an id from `addresses/`) and `payment_method` (`razorpay`, or `cod` when
the site offers cash on delivery) makes an order from the cart; the address is copied into it. An online order is
`pending` until paid; a cash-on-delivery order is placed at once and the cart emptied. Cash on delivery is for orders
worth at most ₹1,500 (`SHOP_COD_MAX_VALUE`, shipping included), and at most two such orders on their way per account.
Refusals (empty cart, sold out, a coupon that no longer applies, cash on delivery not offered or over those limits) are
`400 {"non_field_errors": ["..."]}`; an account whose parent has not yet
confirmed it (`PARENTAL_CONSENT_MODE=verified`) gets 403. Checkouts are limited to 10 per 10 minutes per client
address, the website's included (429).

An order: `number`, `created`, `placed_at`, `status` (`pending`, `paid`, `packed`, `shipped`, `delivered`, `cancelled`,
`refunded`), `status_label` (as the website shows it: "awaiting payment", "placed (pay on delivery)", ...),
`payment_method` (`razorpay`, `cod`, or `offline`: a bank transfer or UPI payment that staff recorded, for school
orders), `total`, `items` (`product`, `title`, `hsn_code`, `gst_rate`, `mrp`, `unit_price`, `quantity`, `line_total`),
`email`, `shipping_address` (an object of strings: `name`, `phone` as `+919864012345`, `line1`, `line2`, `city`,
`district`, `state`, `pin`), `subtotal`, `savings` (as in the cart), `discount`, `shipping_fee`, `coupon_code`,
`timeline` (`status`, the label the website shows: "ordered", then "paid", "packed", …; `at`), `shipments` (`courier`,
`tracking_number`, `tracking_url`, `shipped_at`, `delivered_at`), `refunds` (`amount`, `status`, `reason`, `created`,
`processed_at`), `can_cancel`, `can_pay`, `invoice` (`number`, `created`, `url`; null until the PDF exists),
`credit_notes` (the same with `amount`), `web_url`, `is_digital` (courses only, a bundle of courses included: nothing
to pack or ship, delivered once paid) and `has_shipping` (books to deliver, so the address, `shipping_fee` and
`shipments` concern it: always the opposite of `is_digital`). The list (`orders/`, newest first, `?status=`) gives only
`number`, `created`, `placed_at`, `status`, `status_label`, `payment_method`, `total`, the `items` as text,
`is_digital` and `has_shipping`; `orders/t/<token>/` gives both too.

**Paying** with Razorpay's mobile SDK (Android `com.razorpay:checkout`, iOS `razorpay-pod`):

1. `POST orders/<number>/payment/` returns the SDK's options: `key`, `order_id` (Razorpay's order, the same on every
   call), `amount` (paise), `currency`, `name`, `description`, `prefill`, `notes`, `theme`, and `test_mode`. 503:
   Razorpay cannot be reached, try again later; 400 when the order is not waiting for an online payment (`can_pay`
   is false) or its coupon has been used up meanwhile.
2. Open the SDK with those options. On success it returns `razorpay_order_id`, `razorpay_payment_id` and
   `razorpay_signature`: `POST` them to `orders/<number>/payment/confirm/`. The answer is the order, `paid` (and the
   cart is emptied), or still `pending` for a few minutes when Razorpay could not be asked: Razorpay's webhook to the
   site completes it, so read `orders/<number>/` again. A wrong signature:
   `400 {"non_field_errors": ["We could not confirm this payment. ..."]}`.
3. When the SDK reports a failure or the customer closes it, send nothing: the order stays pending and can be paid
   again from step 1. Online orders left unpaid for two days are cancelled.

```sh
curl -X POST https://examleaf.in/api/v1/orders/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"address": 12, "payment_method": "razorpay"}'
# 201 {"number": "EL-2026-000123", "status": "pending", "status_label": "awaiting payment", "total": "638.00", ...}
curl -X POST https://examleaf.in/api/v1/orders/EL-2026-000123/payment/ -H "Authorization: Bearer $ACCESS"
# 200 {"key": "rzp_live_...", "order_id": "order_N5...", "amount": 63800, "currency": "INR", ..., "test_mode": false}
curl -X POST https://examleaf.in/api/v1/orders/EL-2026-000123/payment/confirm/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' \
  -d '{"razorpay_order_id": "order_N5...", "razorpay_payment_id": "pay_N5...", "razorpay_signature": "9c1f..."}'
# 200 {"number": "EL-2026-000123", "status": "paid", ...}
```

**Cancel**: `POST orders/<number>/cancel/` while `can_cancel` (pending or paid); an online payment is refunded in full
(5–7 working days; the order lists the refund, then turns `refunded`). Later: 400, see the Refund Policy.

**Invoices and credit notes** are PDF files: `GET orders/<number>/invoice/` and `orders/<number>/credit-notes/<id>/`
(the `url`s in the order) answer `application/pdf` as a download whatever the `Accept` header; 404 (JSON) until the
file exists. Each refund of an invoiced order gets a credit note.

**Guests** (visitors without an account), as on the website:

- *Their cart* is a guest cart, held one of two ways. A browser on the site's origin (the website, or a web frontend
  served from the same origin) uses the session cookie: the first `POST cart/items/` makes the cart and the
  `sessionid` cookie, and every change (`POST`, `PUT`, `PATCH`, `DELETE`) carries `X-CSRFToken` from the `csrftoken`
  cookie (403 `{"detail": "CSRF Failed: ..."}` without it; allauth.headless's `GET /_allauth/browser/v1/auth/session`
  sets the cookie). A client without cookies calls `POST cart/` once: `201` with the empty cart and its `token`, shown
  this once; it sends `X-Cart-Token: <token>` with every cart call, `orders/` (checkout) and `shipping/quote/`, and
  needs no CSRF token. The token lasts 30 days (only its hash is kept); an expired or unknown one answers
  `404 {"detail": "This cart has expired: start a new one (POST cart/)."}`. Signed in, `POST cart/` answers 400.
- *Log-in* brings the guest cart into the account's (quantities add up; the coupon carries over unless the account's
  cart has one): by itself for the session (the website's log-in and allauth.headless's browser client alike); a
  client with a token sends `X-Cart-Token` along with its first signed-in cart call (any of them), which merges it
  once.
- *Coupons* (`POST cart/coupon/`): a visitor sends Turnstile's token as `turnstile` while `config/` gives a site key
  (400 `{"turnstile": [...]}` without it), and tries at most 10 codes an hour per client address, the website's cart
  page included (429 after, and while the count cannot be read).
- *Checkout* (`POST orders/`, the guest cart): `email` (the order's emails go there), `shipping_address` (`name`,
  `phone`, `line1`, `line2`, `city`, `district`, `state`, `pin`: the rules of `addresses/`, the PIN code's state
  included once the directory is loaded; errors as `{"shipping_address": {"pin": [...]}}`), `payment_method`
  (`razorpay`: cash on delivery is for signed-in accounts with a confirmed email address, `400 {"non_field_errors":
  ["Cash on delivery is for accounts with a confirmed email address: log in, or pay online."]}`), and `turnstile`
  while the bot check is on. A course needs an account (400 "Please log in first: the course opens in your
  account."). 10 checkouts per 10 minutes per client address, the website's and the accounts' included. The answer,
  `201`, is the order as `orders/t/<token>/` shows it plus its `token`, given only here and in the order's emails:
  keep it for the status page (`orders/t/<token>/`) and the payment.
- *Paying* a guest's order: `POST orders/t/<token>/payment/` (Razorpay's options, as `orders/<number>/payment/`; on
  the web, the options of checkout.js) and `POST orders/t/<token>/payment/confirm/` with Checkout's
  `razorpay_order_id`, `razorpay_payment_id` and `razorpay_signature`: the order (as `orders/t/<token>/`), `paid`, and
  the visitor's guest cart (the session's, or `X-Cart-Token`'s) emptied; the same errors and limits as an account's.
  An account's order answers 404 there (its owner pays it signed in).

```sh
curl -X POST https://examleaf.in/api/v1/cart/
# 201 {"items": [], "count": 0, ..., "total": "0.00", "problems": [], "token": "q9Xr...43 characters"}
curl -X POST https://examleaf.in/api/v1/cart/items/ -H "X-Cart-Token: $CART" -H 'Content-Type: application/json' \
  -d '{"product": "physics-sample-papers-2027"}'
curl -X POST https://examleaf.in/api/v1/orders/ -H "X-Cart-Token: $CART" -H 'Content-Type: application/json' -d '{
  "email": "rahul@example.com", "payment_method": "razorpay", "turnstile": "0.Zx...",
  "shipping_address": {"name": "Rahul Das", "phone": "98640 12345", "line1": "House 12, Zoo Road", "line2": "",
                       "city": "Guwahati", "district": "Kamrup Metro", "state": "AS", "pin": "781024"}}'
# 201 {"number": "EL-2026-000124", "status": "pending", "can_pay": true, ..., "web_url": "https://examleaf.in/orders/t/k2Lm.../",
#      "token": "k2Lm..."}
curl -X POST https://examleaf.in/api/v1/orders/t/k2Lm.../payment/
# 200 {"key": "rzp_live_...", "order_id": "order_N6...", "amount": 30910, ...}
```

*The order's lookup* (a guest who has lost the link): `POST orders/lookup/` with `number` and `email` never
returns the order. If a guest order has that number and email address, the link to it is emailed to that address;
the answer is always `200 {"detail": "If an order matches, we have emailed you a link."}`. Orders of accounts are
left out (their owners sign in). Limited to 10 an hour per client address (`API_THROTTLE_ORDER_LOOKUP`), and to 10 an
hour per email address and per order number from any address; 429 also while the limits cannot be counted.

**The order's link**: every email about an order carries `https://examleaf.in/orders/t/<token>/`, a secret of 22
characters per order. The website's page shows the order without signing in (status, books, address, tracking,
refunds; no payment), its PDFs (`/orders/t/<token>/invoice/`, `/orders/t/<token>/credit-notes/<id>/`) and, while the
order is pending or paid, a cancel button (`POST /orders/t/<token>/cancel/`). A frontend or an app that opens such
links does the same through the API, without signing in (an `Authorization` header is ignored; nothing is cached):
`GET orders/t/<token>/` is the order as `orders/<number>/` gives it, with `invoice.url` and `credit_notes[].url` by the
link (`orders/t/<token>/invoice/`, `orders/t/<token>/credit-notes/<id>/`: PDFs, no account needed), `can_pay` true
only for a guest's order awaiting payment (paid through `orders/t/<token>/payment/`) and `web_url` the link itself;
`POST orders/t/<token>/cancel/` cancels while `can_cancel` (pending or paid; an online payment is refunded in full;
later, 400 as for an account's order), also while the shop is closed, and answers the order. The token comes from the
email, or from a guest's checkout.

**Reviews** (`products/<slug>/reviews/`): `GET` (anyone) answers the approved reviews, newest first (`rating`, `text`,
`status`, `created`; "Verified buyer", never a name), their `average` (one decimal, null without reviews), `count` and
`can_review` (the signed-in user may write one). `POST` (confirmed) with `rating` (1 to 5) and `text` (optional, 1,000
characters at most): only from a buyer whose order of the product was delivered, one each (403 otherwise); it shows
once staff have read it (`"status": "pending"`).

**Back in stock** (`products/<slug>/stock-alert/`): `POST` (signed in, no body) asks for one email, to the account's own
address, when a product out of stock has copies again; the answer is the same whatever the stock. A visitor's address is
not taken: it could be anyone's.

**School and bulk orders** (`quotes/`, the website's form at `/shop/school-orders/`): `school`, `contact_name`, `email`,
`phone` (a 10-digit Indian mobile number), `gstin` (optional), `delivery_pin`, `note` (optional) and `items`
(`[{"product": "<slug>", "quantity": 120}]`, books on sale: courses, and bundles with a course, are left out), with
`turnstile` while the bot check is on. Staff are emailed and send a quotation; the answer is
`201 {"number": "QT-2026-00012", "detail": "Thank you: we will email you a quotation."}`.

```sh
curl https://examleaf.in/api/v1/products/physics-sample-papers-2027/reviews/
# 200 {"average": "4.5", "count": 2, "can_review": false, "results": [{"rating": 5, "text": "...", "status": "approved", ...}]}
curl -X POST https://examleaf.in/api/v1/products/physics-sample-papers-2027/reviews/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"rating": 5, "text": "Every answer step by step."}'
# 201 {"rating": 5, "text": "Every answer step by step.", "status": "pending", "created": "..."}
curl -X POST https://examleaf.in/api/v1/products/chemistry-sample-papers-2027/stock-alert/ -H "Authorization: Bearer $ACCESS"
# 200 {"detail": "We will email rahul@example.com once, when ExamLeaf Chemistry Sample Papers 2027 is back in stock."}
curl https://examleaf.in/api/v1/orders/t/q3k9w0d8m2xYz7AbC1dE4f/
# 200 {"number": "EL-2026-000123", "status": "shipped", ..., "can_pay": false, "web_url": "https://examleaf.in/orders/t/q3k9.../"}
```

## Revision course

Short revision videos per chapter (10 to 15 minutes in clips of a few minutes: concepts, tricks, shortcuts, formulas,
question patterns, common mistakes, previous-year questions), flash cards and a one-mark quiz, for the app only. Code:
`learn/` (models, ffmpeg, plan) and `api/learn.py`.

**What is open.** A subject opens with the code printed in the book (`learn/redeem/`), by buying the course in the shop
(a digital product, opened when paid) or by a staff grant; a code or a purchase lasts a year (`LEARN_ACCESS_DAYS`), a
grant until the day staff set (or with no end), and staff accounts have every subject open. Free for everyone signed in
(`LEARN_FREE_PREVIEW`): the first clip of every revision, any clip an editor marked as a free preview, and the flash
cards of each subject's first chapter; the quiz is not free. These endpoints need a confirmed email address, not only a
sign-in. While a parent's confirmation is awaited (`consent_pending`, `PARENTAL_CONSENT_MODE=verified`, a student under
18) everything that saves something (progress, quiz answers, card reviews, a book code, settings, a device) answers 403
`{"detail": "A parent or guardian has not confirmed this account yet."}`; reading, and taking a device off, still work.
Anything else answers `403 {"detail": "Unlock this subject with the code printed in your book."}`; chapters and clip
lists say beforehand (`entitled`, `free`, `locked`, `free_cards`).

`learn/chapters/` lists every chapter (public; `entitled`, `free_cards` and `progress` describe the signed-in user,
and `progress` is null signed out); `?subject=<id>` narrows them, `?ordering=` sorts by `number`, `weight` or
`frequency`. `has_revision` says whether its revision is published (`revision_status`: `published`, or `none`, also
for a revision still in draft): false is "coming soon", with no clips, minutes or free cards. `free_preview` is the id
of its free clip (`learn/clips/<id>/` for anyone signed in, without a call for the chapter first), null when none.
`learn/chapters/<id>/` answers a chapter with a published revision only (404 otherwise).

```sh
curl 'https://examleaf.in/api/v1/learn/chapters/?subject=1'
# 200 {"count": 14, ..., "results": [{"id": 3, "subject": 1, "number": 1, "title": "Electric Charges and Fields",
#      "weight": "4.5", "frequency": 23, "must_do": "...", "must_do_html": "<p>...</p>", "has_revision": true,
#      "revision_status": "published", "clips": 6, "minutes": 13, "free_preview": 41, "entitled": false,
#      "free_cards": true, "progress": null}, ...]}      progress: % of its clips watched (signed in)
curl https://examleaf.in/api/v1/learn/chapters/3/
# 200 {..., "revision": {"title": "Electric charges in 13 minutes", "target_minutes": 12, "clips": [{"id": 41,
#      "order": 1, "title": "Coulomb's law in one picture", "kind": "concept", "duration": 140, "free": true,
#      "locked": false, "completed": false}, ...]}, "flash_cards": 12, "quiz_items": 9}
```

`weight` is the chapter's share of the Board's marks (a unit's marks shared by its chapters) and `frequency` the
number of questions the Board asked on it in past papers. `kind`: `concept`, `trick`, `shortcut`, `formula`,
`pattern`, `mistake`, `pyq`.

**Playing a clip.** `learn/clips/<id>/` gives `hls_url` (the HLS master playlist: 480×854 at about 700 kbps and 720×1280
at about 1.5 Mbps, AAC sound, 4-second segments; give it to ExoPlayer/Media3 or AVPlayer as it is), `poster_url` and
`expires_at`. The links work for 10 minutes (with `LEARN_PUBLIC_VIDEO=1` and a bucket they never expire and `expires_at`
is null); a clip started within them plays to the end. On a 403 from a link, ask for the clip again. Also `notes` and
`notes_html` (Markdown and HTML, `$…$` maths for KaTeX), `questions` (the Board-style questions it prepares for:
`paper`, `label`, `web_url`), `seconds_watched`, `completed`. Send progress now and then and at the end; `completed`
once true stays true.

```sh
curl https://examleaf.in/api/v1/learn/clips/41/ -H "Authorization: Bearer $ACCESS"
# 200 {"id": 41, "chapter": 3, "order": 1, "title": "...", "kind": "concept", "duration": 140, "notes": "...",
#      "notes_html": "...", "questions": [{"paper": "PHY-E01", "label": "1(a)", "web_url": "https://examleaf.in/s/PHY-E01/"}],
#      "hls_url": "https://examleaf.in/learn/hls/NDE:1v2Lk.../master.m3u8", "poster_url": ".../poster.jpg",
#      "expires_at": "2026-10-15T10:10:00+05:30", "seconds_watched": 0, "completed": false}
curl -X POST https://examleaf.in/api/v1/learn/clips/41/progress/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"seconds_watched": 140, "completed": true}'
# 200 {"seconds_watched": 140, "completed": true}
```

**Quiz and flash cards** are listed per chapter (`?chapter=<id>` is required: 400 without it). Quiz items carry `id`,
`chapter`, `kind` (`mcq`, `true_false`, `fill_blank`), `text`, `text_html` and `options` (multiple choice), never the
answer. An answer is checked on the server: the option's number from 1, `true`/`false`, or the word(s) of the blank
(case, punctuation and a leading "a", "an" or "the" do not matter). Every answer is kept for the plan and revise-again;
an account keeps at most 1,000 quiz answers and 1,000 card reviews a day (429
`{"detail": "That is a day's worth of answers: carry on tomorrow."}`). Flash cards: `id`, `chapter`, `order`, `front`,
`back` (and their `_html`); after turning one over, send whether the student knew it.

```sh
curl 'https://examleaf.in/api/v1/learn/quiz/?chapter=3' -H "Authorization: Bearer $ACCESS"
curl -X POST https://examleaf.in/api/v1/learn/quiz/77/attempt/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"answer": "2"}'
# 200 {"correct": false, "right_answer": "(iv) Radio waves", "explanation": "", "explanation_html": ""}
curl -X POST https://examleaf.in/api/v1/learn/flash-cards/12/review/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"known": false}'
# 201
```

**The pass plan** (`learn/plan/`): from today until the day before the exam, the clips not yet watched, packed into days
of the student's minutes (a clip longer than that gets a day of its own). Chapters come by priority: Board marks ×
previous-year questions (at least 1) × (1 + the share of the student's wrong quiz answers in the chapter), so weak
chapters move up. Parameters: `exam_date` and `minutes` (10 to 300) override the saved settings; `subject` (repeat it
for several) defaults to the subjects open to the student, or all. `not_scheduled` lists the ids of chapters that did
not fit. `minimum_to_pass` gives per subject the chapters with the most marks per minute of video until they are worth
1.5 times the pass marks, each with its clips of the quickest kinds (`pyq`, `formula`, `shortcut`, `trick`). 400 without
an exam date after today.

```sh
curl 'https://examleaf.in/api/v1/learn/plan/?exam_date=2027-02-20&minutes=30' -H "Authorization: Bearer $ACCESS"
# 200 {"exam_date": "2027-02-20", "days_left": 135, "minutes_per_day": 30,
#      "days": [{"date": "2026-10-08", "minutes": 28, "clips": [{"id": 41, "chapter": 3, "title": "...",
#                "kind": "concept", "duration": 140}, ...]}, ...],
#      "not_scheduled": [],
#      "minimum_to_pass": [{"subject": 1, "pass_marks": 21, "marks": "32.0", "chapters": [{"id": 9, "number": 9,
#          "title": "Ray Optics and Optical Instruments", "weight": "7.0", "minutes": 14, "marks_per_minute": "0.50",
#          "clips": [...]}, ...]}]}
```

**Revise again** (`learn/revise-again/`): the quiz items and flash cards (of published revisions the student may still
open) the student got wrong, due again 1 day after the wrong answer, then 3 and 7 days after each right one (a wrong one
starts again at 1 day); after the third right answer they leave the list. Each has the item's fields and `due` (UTC,
ending in `Z`), the longest waiting first: `{"quiz_items": [...], "flash_cards": [...]}`.

**Book codes** (`learn/redeem/`, `{"code": "7KQM-3XPA-9TRW"}`, any case, spaces or dashes) answer the entitlement (`id`,
`subject`, `subject_name`, `source` (`book_code`, `purchase` or `grant`), `valid_until` (a date; null: no end),
`created`; `subject` null: every subject). A code works once; the same student sending it again gets the same answer.
Refusals are `400 {"code": ["..."]}` (not 12 letters and digits, not valid, used already). At most 5 tries an hour per
user and per client address (429). `learn/entitlements/` lists them all, newest first, expired ones too.

**Settings** (`learn/settings/`): `exam_date` (null until set), `minutes_per_day` (10 to 300, default 30),
`reminders` (the daily reminder at 18:00, off until turned on).

**Learning** (`me/learning/`, the website's Learning page; `Learning` in the schema): the signed-in student's own
course in one answer, from the rows the course keeps (no table of its own), `Cache-Control: private, no-store`, and
readable while a parent's confirmation is awaited. `entitlements`: those open today (as `learn/entitlements/`).
`subjects`: each subject open to the student or whose clips they watched, with `entitled`, `clips_watched` of
`clips_total` (processed clips of published revisions), `minutes_watched` (at most each clip's length),
`quiz_answers`, `quiz_accuracy` (% right; null before an answer), `last_activity` (the latest clip watched or quiz
answer), and the same per published chapter in `chapters`. `continue_watching`: the next unwatched clip of the revision
watched last (of the one before, when that one is done): `clip` (`free`, `locked`: neither free nor open, so
`learn/clips/<id>/` answers 403; `seconds_watched`), `revision`, `chapter`; null before any clip. `revise_again`:
`due_today` (or before) and `later`, the counts of `learn/revise-again/`. `plan`: the first three days of
`learn/plan/` for the exam date and minutes saved in `learn/settings/`; without an exam date after today, or with
nothing left to plan, `days` is empty and `hint` says why (empty otherwise). `streak`: `days` in a row with a clip
watched, a quiz answer or a card review, up to today (`today` true) or yesterday, and `last_day` (a clip counts on the
day it was last watched). `consent_pending`, and `has_app_links` (`config/` has a store link).

```sh
curl https://examleaf.in/api/v1/me/learning/ -H "Authorization: Bearer $ACCESS"
# 200 {"entitlements": [{"id": 4, "subject": 1, "subject_name": "Physics", "source": "book_code", ...}],
#      "subjects": [{"id": 1, "code": "PHY", "name": "Physics", "entitled": true, "clips_watched": 5, "clips_total": 18,
#                    "minutes_watched": 12, "quiz_answers": 4, "quiz_accuracy": 25, "last_activity": "...",
#                    "chapters": [{"id": 3, "number": 1, "title": "Electric Charges and Fields", "clips_watched": 4, ...}]}],
#      "continue_watching": {"clip": {"id": 42, "order": 2, "title": "...", "kind": "concept", "duration": 140,
#          "free": false, "locked": false, "seconds_watched": 30}, "revision": {"id": 5, "title": "..."},
#          "chapter": {"id": 3, "subject": 1, "subject_name": "Physics", "number": 1, "title": "..."}},
#      "revise_again": {"due_today": 2, "later": 1},
#      "plan": {"exam_date": "2027-02-20", "days_left": 135, "minutes_per_day": 30, "days": [...], "hint": ""},
#      "streak": {"days": 4, "today": true, "last_day": "2026-10-08"}, "consent_pending": false, "has_app_links": false}
```

**Devices** (`devices/`): after log-in, and whenever Firebase gives a new one,
`POST {"token": "<Firebase installation ID>", "platform": "android"}` (or `ios`): the ID of
`FirebaseInstallations.getId()`, which Firebase Cloud Messaging addresses messages to (firebase-admin 7.7 sends to it;
the old registration tokens are deprecated). An ID registered by another account moves to this one (a shared phone); an
account keeps its 5 newest devices. At log-out `DELETE` with `{"token": "..."}` (204). Reminders are sent only while the
server has `FCM_SERVICE_ACCOUNT_JSON`; IDs Firebase no longer knows are dropped.

## Shipping (staff)

The packing room's and the shipping desk's endpoints (`shipping/api.py`; the app: `shipping/README.md`), for the
admin panel, on the [Staff API](#staff-api)'s rules: the panel's session (with the CSRF token on changes) or an API
key, on the admin host only (404 elsewhere), each action its permission (`staff.view_parcels` to read;
`staff.book_parcel` to quote, book, fetch and read labels, schedule pickups, manifests, photographs and cancellations;
`staff.act_on_exception` for failed deliveries and resolving exceptions; `staff.view_cod` and `staff.reconcile_cod`
for cash on delivery and the courier's charges; `staff.manage_pickup_locations`), otherwise `403 {"code":
"permission_denied"}`; staff without an authenticator app: `{"code": "mfa_setup_required"}`. A PACKER's parcels are
those of the orders to pack and on their way. Every change is an audit event (`shipping.booked`,
`shipping.shipped_by_hand`, `shipping.label_requested`, `shipping.pickup_scheduled`, `shipping.manifested`,
`shipping.cancelled`, `shipping.photo_added`, `shipping.ndr_action` with the names of the details changed,
`shipping.exception_resolved` or `_dismissed`, `payment.cod_reconciled`, `shipping.pickup_location_saved`,
`shipping.pickup_locations_synced`), targeting the order. These endpoints are tagged `shipping (staff)` in the
schema. Money is in rupees as decimal strings; a refusal (ours or the courier's) is `400 {"non_field_errors":
["..."]}`, a courier that cannot be reached `503 {"detail": "The courier could not be reached: try again in a few
minutes."}`.

- **Quote** `GET shipping/orders/<number>/quote/` (`?weight_g=` as weighed; else the books' weights and the packing):
  `couriers`, the top three by the research's rule (none without COD for a COD order, none blocked or out of area; first
  the cheapest rated 4 or more that deliver within 7 days, ties to Shiprocket's own pick; each with `rate`,
  `etd_days`, `rating`, `cod`, `cod_charges`, `rto_charges`, `recommended`), `india_post` (prepaid orders: Book Post,
  and Gyan Post once confirmed), `weight_g`, and `stale` with `error` when Shiprocket could not be asked within 3
  seconds (its last answer for that parcel; answers are kept 10 minutes).
- **Book** `POST shipping/shipments/` `{"order": "EL-2026-000123", "courier_company_id": 51, "courier_name": "...",
  "quoted_rate": "63.25", "weight_g": 420}` (optional: `length_cm`, `breadth_cm`, `height_cm` together, a flyer by
  default; `pickup_location`, the default one otherwise): `202` with the parcel, booked by a task (its `detail.status`
  becomes `booked`, its `tracking_number` the AWB; then its label is fetched). For a packed order, or a shipped one
  whose parcel came back or was lost (a re-shipment); never two parcels on their way for one order; never a test
  order with the live account; never a COD parcel whose cash to collect is not the order's total. **Sent by hand**
  (India Post, a courier without an API): `{"order": "...", "courier": "India Post", "tracking_number": "EA123456789IN"}`
  (and `tracking_url`): `201`, the order shipped at once, the customer emailed, as the admin's "Mark shipped".
- **Parcels** `GET shipping/shipments/` (`?status=booked&carrier=shiprocket&courier_company_id=51&order=<number>`,
  `?search=` an AWB, an order number or our reference; `?ordering=-pk`): `id`, `order`, `courier`, `tracking_number`,
  `tracking_url`, `shipped_at`, `delivered_at` and `detail` (null for a parcel typed by hand in the admin before the
  shipping app): `carrier`, `status`, `reference`, the carrier's ids, `courier_company_id`, `courier_name`,
  `weight_g` and the dimensions, `charged_weight_g`, `quoted_rate`, `cod_amount`, `declared_value`, `last_event_at`,
  `pickup_location`, `pickup_date`, `manifested_at`, `has_label`, `has_photo`. One parcel (`shipping/shipments/<id>/`)
  adds `events` (the timeline), `exceptions`, `charges` and `cod_remittance`.
- **The packing room**: `GET shipping/shipments/<id>/label/` the label's PDF, kept with us (any `Accept`; 404 until
  fetched), `POST` the same address fetches it (202); `POST …/pickup/` `{"date": "2026-10-10"}` (optional) asks the
  courier to collect it (`{"pickup_date": ...}`); `POST shipping/manifest/` `{"shipments": [ids]}` gives
  `{"url": ...}`, the courier's handover list; `POST …/photo/` (multipart, `photo`, an image of 5 MB at most) keeps
  the photograph of the parcel on the scale; `POST …/cancel/` cancels the booking until the courier is out for pickup.
- **Failed deliveries** `POST shipping/shipments/<id>/ndr-action/` `{"action": "re-attempt", "comments": "...",
  "deferred_date": "2026-10-15", "phone": "9864012345", "address1": "...", "address2": "..."}` (`action`:
  `re-attempt`, `return` or `fake-attempt`): sent to the courier, noted on the parcel's NDR exception (what was done
  and which details changed, not the details).
- **Exceptions** `GET shipping/exceptions/` (`?state=open&kind=ndr&shipment=<id>`, `?ordering=due_at`): `kind`
  (`pickup_problem`, `ndr`, `rto`, `lost`, `partial`, `weight_dispute`, `cod_overdue`, `no_movement`), `shipment`,
  `order`, `due_at`, `state`, `data` (the reason and attempts of a failed delivery, our weight and the courier's of a
  dispute, ...), `resolution`; `POST shipping/exceptions/<id>/resolve/` `{"resolution": "...", "dismiss": false}`.
- **Money** `GET shipping/cod/` (`?state=expected|overdue|remitted|mismatch|not_expected`): COD remittances with the
  expected and remitted amounts, days and UTR; `GET shipping/charges/` (`?kind=&shipment=`): the courier account's
  statement lines (a reversal is negative). `POST shipping/cod/<id>/reconcile/` `{"utr": "...", "amount": "598.00",
  "on": "2026-10-23"}` (`on`: today by default; `staff.reconcile_cod`, re-authenticated in the last 5 minutes)
  matches a remittance with the bank's credit: the amount expected makes it `remitted` and settles the parcel's COD
  exception; another amount makes it `mismatch` with an exception; a parcel that owes no cash is a 400.
- **Pickup locations** `GET POST PATCH shipping/pickup-locations/`: our pickup addresses by Shiprocket's nickname (a new
  default replaces the old one); `POST shipping/pickup-locations/sync/` reads them from the courier account.

```sh
curl https://examleaf.in/api/v1/shipping/orders/EL-2026-000123/quote/ -b "sessionid=..."
# 200 {"couriers": [{"courier_company_id": 51, "courier_name": "Xpressbees Surface", "rate": "63.25", "etd_days": 7,
#      "rating": 4.1, "cod": true, "cod_charges": "25.96", "rto_charges": "63.25", "recommended": true}, ...],
#      "india_post": [], "weight_g": 650, "stale": false, "error": ""}
curl -X POST https://examleaf.in/api/v1/shipping/shipments/ -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..." \
  -H "Content-Type: application/json" -d '{"order": "EL-2026-000123", "courier_company_id": 51, "weight_g": 650}'
# 202 {"id": 41, "order": "EL-2026-000123", "courier": "Xpressbees", "tracking_number": "", ...,
#      "detail": {"carrier": "shiprocket", "status": null, "reference": "EL-2026-000123", "cod_amount": "598.00", ...}}
```

**The couriers' webhook** `POST /api/hooks/parcel-events/` is Shiprocket's, not the API's: it authenticates with the
static token we generate (`x-api-key`), compared in constant time with the enabled account's current token or, for 24
hours after a rotation, the previous one; a missing or wrong token, or none set, is `403
{"detail": "Unknown or missing token."}`. A good one is `200 {"detail": "Received."}` at once: the raw body is kept
(once per SHA-256) and processed by a task. 300 a minute per client address (`API_THROTTLE_PARCEL_EVENTS`).

## Site configuration and legal pages

`config/` (anyone, `Cache-Control: public, max-age=300`) is what this server has switched on, for frontends to follow
rather than hard-code: `auth` (`login_methods`, `login_by_code`, `sms`, `google`, `passkeys`, `turnstile_site_key`,
null while the bot check is off), `shop` (`open`, `cod`, `cod_max_value`, `currency`), `shipping` (`fee_from`,
`free_above`: the lowest delivery fee and free-delivery value of `shipping/`, null without rates),
`solutions_require_login`,
`parental_consent` (`declared` or `verified`) and `support` (`email`: `SUPPORT_EMAIL`, else `SELLER_EMAIL`; `phone`:
`SELLER_PHONE`; each null while it still holds a `[placeholder]`) and `app_links` (`android`, `ios`: the app's pages on
Google Play and the App Store, `APP_LINK_ANDROID` and `APP_LINK_IOS`; null until set) and `web_course` (`WEB_COURSE`,
off by default: whether the website draws the revision course's chapter, flash-card and quiz pages, which read the
same `learn/` endpoints as the app; off, the website shows the course's outline and points to the app) and
`maintenance` (`on`; `banner`, its text or null: show it; the server still answers, webhooks and staff work on).
`shop.open`, `shop.cod`, `parental_consent`, `web_course` and `maintenance` are the Admin Control Panel's values when
it has set them (`staff/settings/`), the environment's otherwise; the server's own checks read the same values (carts
and checkout refused while the shop is closed, cash on delivery, a parent's consent). allauth.headless's
`/_allauth/<client>/v1/config` adds allauth's own view (the providers, the authenticator types, `usersessions`).

`pages/` and `pages/<slug>/` (anyone; cached 15 minutes) are the legal and policy pages, `privacy`, `terms`, `refunds`,
`shipping` and `contact`: `slug`, `title`, `version` (consent records keep the privacy notice's), `updated` (the last
change, as in the page's history), `markdown`, `html` (the website's rendering; a `[placeholder]` still to fill in is
marked `<mark class="placeholder">`) and `web_url`.

`contact/` (anyone) is the website's contact form: `name` (80 characters at most), `email` (we reply to it), `message`
(2,000 at most) and `turnstile` while the bot check is on. The message becomes a support ticket (its number in
the acknowledgement emailed to the sender: [Support (staff)](#support-staff)), linked to the account whose
confirmed address sent it; with `SUPPORT_COPY_TO_EMAIL` the support address also gets it, `Reply-To` the sender. `200 {"detail": "Thank you: your message is on its way to us. We reply by
email."}`; 400 with the fields' errors; 429 after 5 an hour per client address, the website's form included (and while
the count cannot be read); `503 {"detail": "The contact form is not set up yet: please write to us by email."}` while
the support address is still a `[placeholder]` (`support.email` of `config/` is null then: show no form). `website` is
a honeypot: a form never sends it (a message with it is thanked and dropped).

```sh
curl https://examleaf.in/api/v1/config/
# 200 {"auth": {"login_methods": ["email", "phone"], "login_by_code": true, "sms": true, "google": true, "passkeys": true,
#      "turnstile_site_key": "0x4AAAAAAA..."}, "shop": {"open": true, "cod": true, "cod_max_value": "1500.00",
#      "currency": "INR"}, "shipping": {"fee_from": "40.00", "free_above": "499.00"},
#      "solutions_require_login": true, "parental_consent": "verified",
#      "support": {"email": "help@examleaf.in", "phone": null}, "app_links": {"android": null, "ios": null},
#      "web_course": false, "maintenance": {"on": false, "banner": null}}
curl https://examleaf.in/api/v1/pages/privacy/
# 200 {"slug": "privacy", "title": "Privacy Policy", "version": "2026-10-08", "updated": "...", "markdown": "...",
#      "html": "<h2>...", "web_url": "https://examleaf.in/privacy/"}
```

## Insights (staff)

`insights/…` (code: `insights/api.py`; the jobs behind them: `insights/README.md`) gives the Admin Control Panel what
the nightly jobs worked out, on the [Staff API](#staff-api)'s rules: the panel's session or an API key (never the
app's JWT), on the admin host only, `staff.view_insights` (FINANCE, MARKETING, ADMIN, the owners, AUDITOR) to read;
without it `403 {"code": "permission_denied"}`, signed out 401. `POST insights/fraud-signals/<id>/acknowledge/`
(`staff.acknowledge_signal`: ADMIN and the owners) marks a signal looked at and handled, once (again: the same
answer), as the admin's action does; the audit log keeps who (`insights.signal_acknowledged`). Each answer is the rows
of the job's newest run (or newest day), paginated as every list, with four fields more about how they were made:

| Field | What it is |
|---|---|
| `method` | the method, in words ("seasonal naive by week of season × damped growth …") |
| `data_as_of` | when the job read its data (Indian offset); null before any run |
| `backtest` | for `forecasts/`, `print-runs/` and `backtests/`: the newest backtest of every title together, 4 weeks ahead (`horizon_weeks`, `wape`, `mase_vs_seasonal_naive`, `shown`, `n_weeks`, `data_as_of`); null otherwise or before two seasons of sales |
| `shown` | false while a prediction has not beaten the seasonal naive in the backtest: the panel hides it or labels it untested; true for counts |

and every row has `n`, the sample behind it (copies of history, weeks tested, learners, parcels, orders, a signal's
count). Learner data are aggregates only: groups under 5 give `n` with null shares, and no row names, counts or ranks
a student.

| Path | Rows |
|---|---|
| `forecasts/` | per title and week from this week to the exam: `product` (slug), `title`, `district` (null: every district together; `?district=all` gives each district, `?district=<name>` one), `week_start`, `p10`, `p50`, `p90`, `n`; `?product=<slug>` for one title |
| `print-runs/` | per title with a print cost: `net_price`, `unit_cost`, `salvage` (rupees, strings), `critical_ratio`, `target_quantity`, `supply`, `recommended_quantity` (to print now), `reprint_trigger_units`, `weeks_of_cover` (null: it outlasts the season), `projected_leftover`, `level` (`ok`, `watch`, `act`), `alert`, `n` |
| `backtests/` | per title (`product` null: every title together) and horizon: `horizon_weeks`, `wape`, `mase_vs_seasonal_naive`, `shown`, `n` |
| `item-stats/` | per quiz item (`?chapter=<id>`): `item`, `chapter`, `kind`, `text`, `n`, `p` and `discrimination` (null below 30 learners), `flags` (`low_discrimination`, `too_easy`, `too_hard`, `distractor_<option>`) |
| `chapter-stats/` | per chapter: `chapter`, `subject`, `number`, `title`, `mean_accuracy`, `trend`, `n` |
| `cohorts/` | per cohort and week: `cohort_month`, `source` (`book_code`, `purchase`, `grant`), `week_index`, `active_share`, `churned_share`, `n` |
| `code-activation/` | per batch (`district` null) and district: `batch`, `district`, `printed` (on the batch's row), `redeemed`, `redeemed_7d`, `n` |
| `delivery/` | per courier and district (null: everywhere): `courier`, `district`, `median_days`, `p90_days`, `n` |
| `fraud-signals/` | every signal, newest first (`?open=1`: not acknowledged): `id`, `kind`, `label`, `subject` (a keyed hash, or `all`), `window_start`, `window_end`, `details`, `created`, `acknowledged_at`, `n` |
| `offers/` | per coupon (`coupon`: its code) or offer (`offer`: its name): `period_start`, `period_end`, `orders`, `revenue`, `discount_cost`, `period_orders`, `baseline_orders`, `baseline_revenue`, `interval_low`, `interval_high` (95 % interval of orders while it ran ÷ the same weeks last season), `note`, `n` |

```sh
curl https://admin.examleaf.in/api/v1/insights/forecasts/?product=physics-sample-papers-2027 -b "sessionid=…"
# 200 {"method": "seasonal naive by week of season × damped growth (season to date ÷ the same weeks last season)",
#      "data_as_of": "2026-11-03T01:15:02+05:30", "backtest": {"horizon_weeks": 4, "wape": 0.31,
#      "mase_vs_seasonal_naive": 0.82, "shown": true, "n_weeks": 48, "data_as_of": "2026-11-03T01:00:01+05:30"},
#      "shown": true, "count": 15, "next": null, "previous": null,
#      "results": [{"product": "physics-sample-papers-2027", "title": "ExamLeaf Physics Sample Papers 2027",
#                   "district": null, "week_start": "2026-11-05", "p10": 24.0, "p50": 40.0, "p90": 60.0, "n": 1210}, ...]}
```

## ERPNext sync (staff)

`/api/v1/staff/erp/…` (code: `erp/api.py`; the sync itself: [erp/README.md](erp/README.md)) is the panel's view of
the ERPNext sync: the outbox, its dead letters, the nightly reconciliation, the pull's cursors and the status. It is
part of the [Staff API](#staff-api) and keeps all its rules: the admin host only, a member of staff with a second
factor (or an API key with `erp.view_sync`), each action's catalogued permission (area "ERP sync"), every refusal an
`authz_fail` event, cursor pages newest first, `Cache-Control: no-store`. Read-only but for three actions, each an
audit event:

| Method | Path (under `/api/v1/staff/erp/`) | Permission | What |
|---|---|---|---|
| GET | `status/` | `erp.view_sync` | the switches (`enabled`, `flows`, `pull_stock`, `pull_b2b`, `stock_projection`, each the panel's flag if set, else the environment's), the ERPNext `account` and its `circuit`, the `outbox` by state, `oldest_waiting_at` and `_seconds`, `held_aggregates` (held by a dead row), the `cursors`, the `last_reconciliation` |
| GET | `outbox/`, `outbox/<id>/` | `erp.view_sync` | every row (`?state=pending|sending|sent|failed|dead|discarded&event=&aggregate_type=order|product|settlement&aggregate_id=<order number or product id>&examleaf_ref=`): `event`, `examleaf_ref`, `sequence` in its aggregate, `idempotency_key`, `payload` (what goes: no personal data), `state`, `attempts`, `next_at`, `last_error`, `sent_at`, `response` (ERPNext's answer), `dead_letter` (its IntegrationFailure's id) |
| GET | `dead-letters/`, `dead-letters/<id>/` | `erp.view_sync` | the dead rows (`?event=&aggregate_type=&aggregate_id=`): each holds its aggregate's later rows |
| POST | `dead-letters/<id>/replay/` | `erp.replay_sync` (high: a re-authentication within 5 minutes) | sent again now, from its first try (`erp.replay`); 404 once it is not dead |
| POST | `dead-letters/<id>/discard/` `{"reason": "Made by hand in ERPNext."}` | `erp.replay_sync` (high) | given up, with the reason (`erp.discard`): its aggregate goes on |
| GET | `reconciliations/`, `reconciliations/<id>/` | `erp.view_sync` | the nightly runs (`?date=&state=running|done|failed`): `date`, `state`, `platform_totals`, `erp_totals`, `differences_count`, `error`; one with its `differences` |
| GET | `differences/`, `differences/<id>/` | `erp.view_sync` | what did not match (`?run=&kind=invoices|credit_notes|payments|settlements|deliveries|stock|missing&open=true`): `key` (what it is about: a total, a payment mode, an item code, a document's reference), `platform_value`, `erp_value`, `note`, `resolved_at`, `resolved_by` |
| POST | `differences/<id>/resolve/` `{"note": "…"}` | `erp.resolve_difference` | resolved with what was done (`erp.resolve`); `400 {"non_field_errors": ["Resolved already."]}` the second time |
| GET | `cursors/` | `erp.view_sync` | how far the 15-minute pull has read each doctype (`modified_after`, `last_name`, `rows_read`, `last_run_at`, `last_error`) |

The initial load is a staff job: `POST /api/v1/staff/jobs/` `{"kind": "erp_initial_load", "params":
{"invoices_from": "2026-04-01"}, "dry_run": true}` (`erp.run_initial_load`, high; the owners are told when one writes
rows): its `result` is `{"written": {event: rows}, "flows_off": [...]}`. The switches are feature flags:
`PUT /api/v1/staff/flags/ERP_SYNC_INVOICES/` `{"value": false, "reason": "…"}` (`staff.manage_flags`), `null` back to
the environment's.

```sh
curl https://admin.examleaf.in/api/v1/staff/erp/status/ -b "sessionid=..."
# 200 {"enabled": true, "mode": "erpnext", "flows": {"catalogue": true, "invoices": true, "payments": true,
#      "deliveries": true, "settlements": true}, "pull_stock": true, "pull_b2b": true, "stock_projection": false,
#      "account": {"id": 3, "label": "ERPNext (live), erp-sync@", "mode": "live", "circuit": "closed", ...},
#      "outbox": {"pending": 2, "sending": 0, "sent": 1840, "failed": 0, "dead": 1, "discarded": 0},
#      "oldest_waiting_at": "2026-10-09T10:15:03+05:30", "oldest_waiting_seconds": 42, "held_aggregates": 1,
#      "cursors": [...], "last_reconciliation": {"id": 9, "date": "2026-10-08", "state": "done", "differences": 0, ...}}
```

**ERPNext's webhook** `POST /api/hooks/erp-events/` is ERPNext's, not the API's: it carries `X-Frappe-Webhook-Signature`,
the base64 HMAC-SHA256 of the raw body with the ERPNext account's webhook secret (the current one, or for 24 hours
after a rotation the previous one), checked in constant time. A missing or wrong signature, no enabled account, or
`ERP_ENABLED` off: `403 {"detail": "Unknown or missing signature."}`, kept without its body. Otherwise
`200 {"detail": "Received."}` at once; the body (`{doctype, name, modified, examleaf_ref, event}`) is kept once per
SHA-256 and read again by a task. 600 a minute per client address (`API_THROTTLE_ERP_EVENTS`).

## Support (staff)

`/api/v1/staff/support/…` (code: `support/api.py`; the app: [support/README.md](support/README.md)) is the Support
module's API: the tickets with their legal clocks, the conversation, the actions on the customer's orders and course,
the saved replies and the module's numbers. It keeps every rule of the [Staff API](#staff-api): the admin host only, a
member of staff with a second factor (an API key reads only), each action's catalogued permission (area "Support"),
every refusal an `authz_fail` event, cursor pages, `Cache-Control: no-store`; the schema tags it `support (staff)`.
The tickets reach each person through their scope: a SALES member's are the order, payment and school-order tickets, a
content editor's the content errors (`ticket_category`). Opening a ticket, revealing its requester's details,
downloading a file and looking a person up by email or phone are `sensitive_read` events (the lookup's keyed hash,
never the query); every change is an audit event (`support.ticket_logged`, `support.changed` with the masked fields,
`support.replied`, `support.noted`, `support.assigned`, `support.status`, `support.reopened`, `support.acknowledged`,
`support.action` with the action's name, `support.clock_breached`, `support.saved_reply_*`), naming the ticket by its
number and never its requester.

| Method | Path (under `/api/v1/staff/support/`) | Permission | What |
|---|---|---|---|
| GET | `tickets/` (`?status=&open=&waiting=&mine=&unassigned=&overdue=&category=&priority=&source=&language=&assignee=&test=&q=`) | `support.view_ticket` | the queue, the next legal deadline first (`next_due_at`); `q`: a ticket's or an order's number, an email address or a mobile number; spam only with `status=spam`; on a live site a test order's tickets only with `test=true` |
| POST | `tickets/` (`source`, `nch_docket`, `name`, `email`, `phone`, `category`, `priority`, `subject`, `message`, `received_at`, `order`) | `staff.handle_ticket` | log a call, a WhatsApp message, an NCH complaint (its docket) or an email (201, the ticket); its clocks run from `received_at` (never ahead, within a year) |
| GET | `tickets/<number>/` (or its id) | `support.view_ticket` | the ticket with `clocks`, `closing_fields`, `transitions`, `messages`, the `sidebar` (each part by the reader's permissions, null otherwise) and the `saved_replies` filled for it, its language first |
| PATCH | `tickets/<number>/` | `staff.handle_ticket` | sort and correct it: category, priority, language, subject, source and NCH docket, `order` (a number), `record` (a paper's code), the requester's `name`, `email`, `phone`; a new category or source sets the clocks again from when it came |
| POST | `tickets/<number>/messages/` (`direction`: `out` or `note`, `body`, `channel`, `mentions`) | a reply `staff.handle_ticket`; a note `support.note_ticket` | a reply (`channel` `email`: sent in the customer's thread; `phone`, `whatsapp`, `nch`: recorded), or an internal note naming colleagues (each an inbox item) |
| POST | `tickets/<number>/assign/` (`assignee`, null: nobody), `…/claim/` | `staff.handle_ticket` | given to someone who handles tickets and may see this one; to yourself |
| POST | `tickets/<number>/status/` (`status`, `resolution`, `order`, `record`) | `staff.handle_ticket` | moved on as `transitions` allows; resolving or closing asks for the category's `closing_fields` (field errors otherwise) |
| POST | `tickets/<number>/reopen/` | `staff.handle_ticket` | a resolved or closed ticket back to open (counted) |
| POST | `tickets/<number>/acknowledge/` (`note`) | `staff.handle_ticket` | the acknowledgement sent again; with `note`, recorded as given another way |
| POST | `tickets/<number>/reveal/` (`show`: `email`, `phone`; `reason`) | `staff.reveal_contact` (re-authenticated; 30 an hour) | the requester's details, logged |
| GET | `tickets/<number>/attachments/<id>/` | `support.view_ticket` | a file of the conversation: the file, or 302 to the private bucket's link signed for 5 minutes |
| POST | `tickets/<number>/refund/` (`order`, `amount` or `lines` `[{item, quantity}]`, `reason`; `Idempotency-Key`) | `staff.refund_order` | through `order.refund`: 201 run within your `refund_inr`, 202 waiting for FINANCE above it, 400 when it failed |
| POST | `tickets/<number>/cancel/` (`order`, `reason`; `Idempotency-Key`) | `shop.change_order` | cancel an order: one paid online through its refund (as above), another at once (200 `{order, status}`) |
| POST | `tickets/<number>/resend-invoice/`, `…/resend-confirmation/` (`order`) | `staff.handle_ticket` | the shop's own email again, to the order's address |
| POST | `tickets/<number>/extend-access/` (`entitlement`, `days` 1 to 365, `reason`) | `learn.change_entitlement` | course access extended from its end (or today) |
| POST | `tickets/<number>/book-code/` (`code`) | `learn.view_bookcode` | a book code looked up by its digest (never kept): `{found, batch, subject, redeemed, by_requester, line}` |
| POST | `tickets/<number>/data-request/` (`kind`, `summary`) | `staff.handle_data_request` | a data request from a grievance or privacy ticket (201, the request), received when the ticket was |
| GET POST PUT PATCH DELETE | `saved-replies/` (`?language=&bin=`), `saved-replies/<id>/`, `saved-replies/<id>/restore/` | `support.view_savedreply`; `add_`, `change_`, `delete_savedreply` | the saved replies (`variables`: those its text uses); a delete puts one in the bin for 30 days, restore/ takes it out |
| GET | `summary/` (`?days=` 1 to 366, 30) | `support.view_ticket` | the period's volume by category and source, the median first response and resolution (hours), the breaches; the backlog and the overdue now (spam and test orders left out) |
| GET | `agents/` | `support.view_ticket` | who a ticket may be given to or a note may name: `{id, name, handles}` |

The grievance register is a staff job: `POST /api/v1/staff/jobs/` `{"kind": "grievance_export", "params": {"from":
"2026-10-01", "until": "2026-10-31"}}` (`staff.export_grievances`, high; above your `export_rows` it waits for an
approver), its file a dated CSV with no personal data beyond the ticket's number and category.

```sh
curl "https://admin.examleaf.in/api/v1/staff/support/tickets/?open=true" -b "sessionid=..."
# 200 {"next": null, "previous": null, "results": [{"id": 4103, "number": "SR-2026-000103", "subject": "Books arrived
#      damaged", "source": "email", "category": "order", "status": "open", "requester": {"name": "Riya Das",
#      "email": "ri•••@example.com", "phone": "••••••2210", "user": 7101}, "next_due_at": "2026-10-05T14:00:00+05:30",
#      "clock": "due", "overdue": true, "due_breached": true, ...}, ...]}
curl -X POST https://admin.examleaf.in/api/v1/staff/support/tickets/SR-2026-000103/messages/ \
  -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..." -H "Content-Type: application/json" \
  -d '{"direction": "out", "body": "We have refunded the two books.", "channel": "email"}'
# 201 {"id": 7012, "direction": "out", "channel": "email", "author": 9003, "author_name": "Rahul Saikia", ...}
curl -X POST https://admin.examleaf.in/api/v1/staff/support/tickets/SR-2026-000103/status/ \
  -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..." -H "Content-Type: application/json" \
  -d '{"status": "resolved"}'
# 400 {"resolution": ["Say what was done."]}
```

**My requests** (the customer's side, API v1): `GET /api/v1/me/tickets/` (signed in) lists the account's tickets and
those sent from one of its confirmed email addresses before, newest first, 50 a page: `number`, `subject`,
`category` and `category_label`, `status` and `status_label` (the customer's words: received, being looked at,
waiting for your reply …), `order`, `received_at`, `acknowledged_at`, `answer_by` (the latest we answer by),
`resolved_at`, `closed_at`; never staff's notes nor who works on it. `POST` (a confirmed email address; 10 an hour)
`{"category": "payment", "subject": "...", "message": "...", "order": "EL-2026-000123"}` (the order one of the
account's, optional) makes one: 201 with it, acknowledged by email with its number. The contact form (`contact/`)
makes one too, for anyone.

```sh
curl https://examleaf.in/api/v1/me/tickets/ -H "Authorization: Bearer eyJ..."
# 200 {"count": 1, "next": null, "previous": null, "results": [{"number": "SR-2026-000114", "subject": "Refund not
#      received", "category": "payment", "category_label": "payment or refund", "status": "open",
#      "status_label": "being looked at", "order": "EL-2026-000131", "received_at": "...", "answer_by": "...", ...}]}
```

**The support mailbox's hook** `POST /api/hooks/support-mail/` is the forwarder's, not the API's (an SES receipt
rule's Lambda, or Cloudflare's Email Routing worker): the raw message (`message/rfc822`) or SES's receipt notification,
with the `support_mail` integration account's webhook token in `X-Support-Mail-Token` (constant time; the previous
token too for 24 hours after a rotation). A missing or wrong token, or no enabled account: `403 {"detail": "Unknown
or missing token."}`, kept without its body; more than `SUPPORT_MAIL_MAX_BYTES` (10 MB): 413. Otherwise `200
{"detail": "Received."}` at once: the body is kept once per SHA-256 and read by a task, which drops our own mail,
auto-replies, bounces and lists, and threads the rest by the thread id in its headers, a known Message-ID, or the
`[SR-…]` number from the requester's own address. 120 a minute per client address (`API_THROTTLE_SUPPORT_MAIL`).

## Lists

Lists are paginated: `{"count": 120, "next": "<url>", "previous": null, "results": [...]}`, 50 a page, `?page=2`,
`?page_size=` up to 200. This holds for every list endpoint (boards, subjects, books, papers, attempts, products,
categories, collections, addresses, orders, the course's chapters, quiz items, flash cards and entitlements); `pages/`
is a paginated list too (ordering `slug`, `title`); `papers/<code>/solutions/`, the plan, revise-again and a product's
reviews (`{average, count, can_review, results}`) are not paginated. `?search=` searches books (title, subject), papers
(code, title) and products (title); `?ordering=` sorts (`-number` for descending): papers by `code`, `number`, `tier`;
books by `id`, `title`; boards and subjects by `id`, `name`; attempts by `date`, `marks_obtained`, `created`; products
by `title`, `price`; chapters by `number`, `weight`, `frequency`; orders and addresses by `created`. Filters: papers
`?book=<slug>&subject=<id>&tier=`, books `?subject=<id>`, subjects `?board=<id>`, products
`?kind=&subject=<id>&category=&collection=&attr_<code>=`, attempts `?subject=<id>&tier=`, orders `?status=`, chapters
`?subject=<id>`. The catalogue (boards, subjects, books, papers, categories, collections) is cached on the server for 15
minutes.

## Staff API

`/api/v1/staff/…` is the Admin Control Panel's (`staff/api.py`; the model, the approvals and the audit log:
[staff/README.md](staff/README.md)). The panel draws what it answers and decides nothing: every call is checked again.

- **Where.** On the admin host only (`ADMIN_HOSTS`, `admin.examleaf.in`): on any other host every path here is
  `404 {"detail": "Not found."}`, signed in or not. Empty in development: every host.
- **Who.** A member of staff on the panel's own session (same origin, the session cookie and `X-CSRFToken` on POST,
  PUT, PATCH and DELETE), signed in with a second factor; or an integration with an API key,
  `Authorization: Api-Key elk_<prefix>_<secret>`, holding only the `view_` permissions it was made with. Never the app's
  JWT. Without either: `401 {"code": "not_authenticated"}` (`WWW-Authenticate: Api-Key`); a member of staff without
  an authenticator app or a passkey: `403 {"code": "mfa_setup_required"}`.
- **What.** Each endpoint names the permission it needs for each method (the tables; `app_label.codename`); without
  it, `403 {"detail": "You need the permission staff.approve_refund (Approve refunds above the maker's limit).",
  "code": "permission_denied"}`, recorded in the audit log as `authz_fail`. Objects outside the person's scope (a
  subject, an order status, a school, a work queue) are not found (404, never a 403 that would tell they exist). High
  and critical permissions (`catalogue/` says which) need a log-in or a re-authentication in the last 5 minutes,
  through allauth.headless (`auth/reauthenticate` with the password, `auth/2fa/reauthenticate` with a code,
  `auth/webauthn/reauthenticate` with a passkey): otherwise `403 {"code": "reauthentication_required", "flows":
  [{"id": "reauthenticate"}, {"id": "mfa_reauthenticate"}]}` (allauth's flow ids); re-authenticate, then send the
  request again. An action that needs a second person is never a 403: it answers 202 with the change request (`id`,
  `status` "pending", `checker`), or with the job and its `change_request_id`.
- **Errors** carry `detail` and `code`, but 400's: `{"field": ["…"]}` (`non_field_errors` for the request as a whole,
  `params` for a job's); 401 `not_authenticated`, `authentication_failed` (an API key refused), `session_idle`,
  `session_expired`;
  403 `permission_denied`, `reauthentication_required`, `break_glass_reason_required`, `mfa_setup_required`,
  `impersonating`, `link_expired` (a job's file); 404 `not_found` (also every path on a host other than the admin
  host); 405 `method_not_allowed`; 429 `throttled`.
- **The session's limits.** After the person's idle limit without a request (`idle_timeout_s` in `session/`: 15 minutes
  for OWNER, ADMIN, FINANCE and PACKER, 30 for the others, the shortest of their roles') or 8 hours after the log-in
  the session ends: `401 {"code": "session_idle"}` or `{"code": "session_expired"}`; log in again. Do not poll in the
  background: every request counts as activity.
- **Answers** are JSON (an audit export: JSON lines), never cached (`Cache-Control: no-store`). Lists are cursor pages,
  newest first: `{"next": "<url>", "previous": "<url>", "results": [...]}` (`?cursor=` from those links, `?page_size=` up
  to 200; no count: `inbox/count/` gives the inbox's). Filters are query parameters, listed per endpoint below;
  a yes-or-no one takes `true` or `false` (`1` or `0`).
- **Money actions and approvals** go through `change-requests/`. Send an `Idempotency-Key` header (any unique text): the
  same key answers the first request again instead of making a second one. 201: it ran at once, within your limits
  (`limits` in `session/`); 202: it waits for a second person (`status` "pending"); 400 with `detail`: it ran and
  failed (its preconditions no longer held).
- **Personal data is masked** (`ra•••@example.com`, `••••••2345`, `203.0.113.x`); opening a customer and revealing a
  detail are recorded (`sensitive_read`).

| Method | Path (under `/api/v1/staff/`) | Permission | What |
|---|---|---|---|
| GET | `session/` | any member of staff | the manifest: user, roles with expiry, permissions, scopes, limits, flags (and `test_mode` off production), `policies_due`, the re-authentication window, the idle and absolute limits, `impersonating`, `break_glass`, `manifest_version` |
| POST | `session/reason/` (`reason`) | a break-glass session | its reason, once, before anything else; the owners are told |
| GET | `catalogue/` | any member of staff | every catalogued permission (label, area, risk, reauth, approval, alert) and every role (permissions, limits, scopes, conflicts, members) |
| GET | `inbox/` (`?kind=&mine=&done=&snoozed=`), `inbox/count/` | `staff.view_inbox` | what waits: items assigned to you, or to nobody and needing a permission you hold; open and overdue counts |
| POST | `inbox/<id>/done/`, `…/snooze/` (`until`), `…/assign/` (`assignee`) | `staff.view_inbox` | act on one |
| GET | `audit/` (`?actor=&action=&action_prefix=&target_type=&target_id=&outcome=&since=&until=&request_id=&ip=&chain=&permission=&break_glass=&change_request=`), `audit/<id>/` | `staff.view_auditlog` (AUDITOR, OWNER) | the audit log; each read is itself an event; `break_glass` marks a break-glass account's events and an owner's override |
| POST | `audit/export/` (`filters`) | `staff.export_auditlog` | 200: JSON lines with the hashes, up to 5,000 rows within your `export_rows`; more: 202 and a job (`jobs/`), approved first by ADMIN above your `export_rows` |
| GET | `jobs/` (`?mine=&state=&kind=`), `jobs/<id>/` | `staff.view_job` | your background jobs (everyone's with `staff.view_system`): `state`, `done` of `total`, the rows' `errors`, `result`, `result_url` |
| POST | `jobs/` (`kind`, `params`, `dry_run`) | the kind's own: `staff.export_auditlog`; a bulk action's action's (`staff.refund_order` …) | 202: the job, queued (`change_request_id` when above your `export_rows` or `bulk_rows`) |
| POST | `jobs/<id>/cancel/` | `staff.view_job`, your own job | stop it: at once while queued (its approval withdrawn), at its next row while running |
| GET | `jobs/<id>/result/?token=` | `staff.view_job`, your own job | its file (`result_url`, a link signed for 5 minutes): 200 the file, or 302 to the private bucket's own signed link |
| GET | `change-requests/` (`?status=&action=&mine=&awaiting=`), `change-requests/<id>/` | `staff.view_changerequest` | approvals: payload, its SHA-256, rule, approvals, result |
| POST | `change-requests/` (`action`, `target`, `payload`, `reason`) | `staff.add_changerequest` and the action's own | ask: `order.refund`, `order.offline_payment`, `product.price`, `coupon.create` |
| POST | `change-requests/<id>/approve/` (`payload_sha256`, `comment`, `override`), `…/reject/` (`comment`) | the action's checker (re-authenticated): FINANCE for money, ADMIN for roles, staff second factors, erasures and exports, the owners for any | approve the payload you read (its hash); reject, or withdraw your own |
| POST | `change-requests/<id>/execute/` | its maker or a checker (re-authenticated) | run the stored payload, once |
| GET POST PATCH DELETE | `saved-views/` (`?list_key=`), `saved-views/<id>/` | `staff.view_savedview`, `add_`, `change_`, `delete_` | your saved lists' filters, columns and sort; `role` shares one with a role you hold |
| GET | `settings/`, `settings/<key>/` | `staff.view_sitesetting` | the site's switches: in effect, the environment's, where from, changes to come; one switch's history |
| PUT | `settings/<key>/` (`value`, `reason`, `effective_from`) | `staff.manage_settings`; `MAINTENANCE_*`: `staff.toggle_maintenance` | `SHOP_OPEN`, `SHOP_COD_ENABLED`, `PARENTAL_CONSENT_MODE`, `WEB_COURSE`, `MAINTENANCE_MODE`, `MAINTENANCE_BANNER`; null: back to the environment's |
| GET | `flags/`, `flags/<KEY>/` | `staff.view_featureflag` | the feature flags; one flag's history |
| PUT | `flags/<KEY>/` (`value`, `reason`, `effective_from`) | `staff.manage_flags` | switch one (null: off) |
| GET | `api-keys/`, `api-keys/<id>/` | `staff.view_apikey` | integrations' keys: prefix, permissions, sponsor, expiry, last use; never the secret |
| POST | `api-keys/` (`name`, `scopes`, `expires_at`, `allowed_ips`, `sponsor`), `api-keys/<id>/revoke/` | `staff.manage_api_keys` (OWNER) | make one (the whole key in this answer only), revoke one |
| GET | `people/`, `people/<id>/`, `people/invites/` | `staff.view_staff` | the staff: roles with who gave them, why, until when; scopes; second factor; invitations |
| POST | `people/invite/` (`email`, `role`, `reason`) | `staff.assign_role` (OWNER) | an invitation (a privileged role: 202, ADMIN or another owner approves first) |
| DELETE | `people/invites/<id>/` | `staff.assign_role` | revoke an invitation |
| POST | `people/<id>/roles/` (`role`, `expires_at`, `reason`) | `staff.assign_role` (OWNER) | give a role (SSD: 400; a privileged role, or one for yourself: 202, ADMIN or another owner approves) |
| DELETE | `people/<id>/roles/<ROLE>/` (`?reason=`) | `staff.assign_role` | take a role away, at once |
| POST DELETE | `people/<id>/scopes/` (`kind`, `value`, `expires_at`), `people/<id>/scopes/<scope>/` | `staff.assign_role` | narrow a person to a subject, board and class, order status, warehouse, school or work queue |
| POST | `people/<id>/end-sessions/` | `staff.assign_role` | sign them out everywhere (sessions ended, refresh tokens blacklisted) |
| POST | `people/<id>/reset-mfa/` (`reason`) | `staff.reset_user_mfa` | a staff member's second factor reset: 202, ADMIN or an owner approves |
| POST | `people/<id>/offboard/` (`reason`) | `staff.assign_role` | in one step: deactivated, roles, grants and scopes gone, sessions ended, API keys revoked, requests expired, work unassigned |
| GET | `access-review/` | `staff.view_staff` | each member: roles, scopes, last log-in, dormant, second factor, action permissions unused in 90 days |
| POST | `invites/accept/` (`token`; signed out also `full_name`, `password`) | the invitation's token | the one endpoint for people not yet staff |
| GET | `users/` (`?q=&class_level=&board=&is_active=`), `users/<id>/` | `accounts.view_user` | customers, contacts masked; opening one is logged |
| POST | `users/<id>/reveal/` (`show`, `reason`) | `staff.reveal_contact` (re-authenticated; 30 an hour) | `email`, `phone`, `login_phone`, `parent_contact`, `parent_name`, `date_of_birth` |
| POST | `users/<id>/suspend/`, `…/unsuspend/` (`reason`) | `staff.suspend_user` | suspended: signed out, told by email |
| POST | `users/<id>/unlock/` | `staff.unlock_user` | lift a lock-out after failed log-ins |
| POST | `users/<id>/resend-verification/` | `staff.resend_verification` | the parent's consent link again, while it waits |
| POST | `users/<id>/end-sessions/` | `staff.end_user_sessions` | sign them out everywhere |
| POST | `users/<id>/password-reset/` | `staff.initiate_password_reset` | allauth's reset email to the account's address |
| POST | `users/<id>/reset-mfa/` (`reason`) | `staff.reset_user_mfa` | 202: another person approves |
| POST | `users/<id>/impersonate/` (`reason`, `ticket`), `…/impersonate/end/` (`token`) | `staff.impersonate_user` | a 15-minute token that the website's `account/impersonate/` takes once, from a browser on the website's host (never staff or a child); its end, which ends the website's session too |
| GET | `data-requests/` (`?status=&kind=&user=&assignee=&overdue=`), `data-requests/<id>/` | `staff.view_datarequest` | the requests queue, with its clocks |
| POST PATCH | `data-requests/`, `data-requests/<id>/` | `staff.handle_data_request` | record one; change its notes, assignee, details |
| POST | `data-requests/<id>/acknowledge/`, `…/verify-identity/` (`note`), `…/close/` (`outcome`, `response`) | `staff.handle_data_request` | its steps |
| GET | `data-requests/<id>/response/`, `data-requests/<id>/erasure-report/` | `staff.view_datarequest` | the answer's text with the contact block; the erasure's dry run |
| POST | `data-requests/<id>/erase/` (`reason`) | `staff.handle_data_request` (re-authenticated) | 202: the erasure waits for `staff.approve_erasure`; 400 with the dry run while something stops it |
| POST | `data-requests/<id>/export/` | `staff.export_personal_data` | an access request's data, emailed to the account's own address (202) |
| GET | `incidents/` (`?kind=&open=`), `incidents/<id>/` | `staff.view_incident` | the breach register with its clocks |
| POST PATCH | `incidents/`, `incidents/<id>/`, `incidents/<id>/close/` | `staff.manage_incident` | file one (the owners are told), record its reports, close it |
| GET POST PATCH DELETE | `processors/`, `processors/<id>/` | `staff.view_processorrecord`, `add_`, `change_`, `delete_` | the processor register |
| GET POST | `notes/` (`?target_type=&target_id=`, both; POST `target_type`, `target_id`, `body`, `pinned`) | `staff.view_note`, `staff.add_note`, and the record's own `view_` (in your scope: else 404) | notes on a record (`shop.order`, `accounts.user` …, by its id), pinned first, all of them: its timeline's; the audit log names the record and the note's number, never its body |
| GET POST | `policies/ack/` (`?user=`: someone else's, with `staff.view_staff`; POST `policy`, `version`) | any member of staff | your acknowledgements of the policies (`STAFF_POLICIES`), each version once (201, again 200; not the version in force: 400) |
| GET | `system/` | `staff.view_system` | health checks, Celery's queues and failed tasks, webhooks, email suppressions, the SMS log, the last backup, maintenance, the audit chain's last check |
| POST | `system/reconcile/` (`order`) | `staff.replay_webhook` | ask Razorpay what became of an online order's payment |

**The manifest** (`session/`, `Cache-Control: no-store`). Keep it in memory, never in `localStorage`; fetch it again after
any 403 and whenever `manifest_version` changes. `user.is_superuser` true is a break-glass account (no roles, every
permission, no limits, the shortest idle limit; every event of its session is marked): show it a banner.
`break_glass` is null for everyone else; for a break-glass session `{"reason_required", "reason", "ends_at"}`: while
`reason_required` is true ask why and `POST session/reason/` `{"reason": "…"}` (10 to 500 characters, once: the
answer is the same object), before which every other staff call answers `403 {"code": "break_glass_reason_required"}`
(the manifest and `catalogue/` excepted); `ends_at` is its log-in plus 2 hours (`STAFF_BREAK_GLASS_HOURS`), the end
however busy. `policies_due` lists the policies' versions (`STAFF_POLICIES`) the person has not acknowledged,
`[{"policy": "acceptable_use", "version": "2026-10"}]`: show them, and `POST policies/ack/` `{"policy", "version"}`
each once read (research 6: before the rest of the panel).

```sh
curl https://examleaf.in/api/v1/staff/session/ -b "sessionid=…"
# 200 {"user": {"id": 7, "email": "support@examleaf.in", "full_name": "…", "is_superuser": false},
#      "roles": [{"name": "SUPPORT", "expires_at": null, "granted_by": 1}],
#      "permissions": ["accounts.view_user", …, "staff.reveal_contact", "staff.view_inbox"],
#      "scopes": {"ticket_queue": ["data_request"]}, "role_scopes": {},
#      "limits": {"refund_inr": 1000, "offline_inr": 0, "discount_percent": 0, "export_rows": 100, "bulk_rows": 50},
#      "flags": {"ERP_SYNC_ORDERS": false}, "policies_due": [], "reauth_valid_until": "2026-10-09T10:05:00Z",
#      "idle_timeout_s": 1800,
#      "absolute_expires_at": "2026-10-09T17:59:00Z", "impersonating": null, "break_glass": null,
#      "manifest_version": "3f9a1c0d2b7e4a55"}
```

`flags.test_mode` is `true` only off production (`STAFF_TEST_MODE`, `DEBUG`'s by default): show the TEST band; absent,
it is production. `impersonating` is `{"user_id", "email" (masked), "until"}` while this session's token from
`users/<id>/impersonate/` lasts (15 minutes, or until `…/impersonate/end/`): show the banner. Open the website's
page that posts the token to `/api/v1/account/impersonate/` (API.md "Profile and data rights"): the website's session
it opens ends with this panel session, at the token's time, or with `…/impersonate/end/`.

**Jobs** (`jobs/`, `staff/jobs.py`) are the background work started from the panel: `audit_export` (`params`:
`{"filters": {…}}`, the audit list's) and `bulk_action` (`params`: `{"action": "order.refund", "targets": ["EL-2026-…",
…], "payload": {}, "reason": "…"}`; the actions of `change-requests/`, each target run as its own request through the
same permission, scope, limits and approval, with an idempotency key per job and target). Above your `export_rows` or
`bulk_rows` (`limits`) the job waits for ADMIN's approval (`change_request_id`, a change request `job.run` whose payload
shows the filters or targets); `dry_run` checks every row and changes nothing. `state` is `queued`, `running`, `done`,
`failed` or `cancelled`; `done` of `total` counts the rows (saved about once a second: poll every few seconds);
`errors` lists the rows that failed, `[{"id": "EL-NOPE", "label": "EL-NOPE", "message": "No such order …"}]` (`id`
null: the job's own failure), the first 1,000; `result` sums them up (`{"rows": 4}`; a bulk action's `{"outcomes":
{"executed": 2, "pending": 1, "refused": 1}, "waiting": [change request ids]}`). `result_url` is for the job's starter
only, valid 5 minutes (read the job again for a new one); the file is kept a week. Each step is an audit event
(`job.requested`, `job.started`, `job.done`, `job.failed`, `job.cancelled`, `job.stopped`, `job.result_downloaded`).

**A refund** above the maker's limit waits for finance; the approver sends back the hash of the payload they read, and
the stored payload runs:

```sh
curl -X POST https://examleaf.in/api/v1/staff/change-requests/ -H 'Idempotency-Key: 4f0c…' -d '{"action": "order.refund",
  "target": "EL-2026-000123", "payload": {"amount": "2500.00"}, "reason": "The parcel came damaged"}'
# 202 {"id": 12, "status": "pending", "payload": {"order": "EL-2026-000123", "amount": "2500.00", "cancel": false},
#      "payload_sha256": "9b1e…", "amount": "2500.00", "rule": "A refund of ₹2,500.00 is above the limit of ₹1,000.",
#      "checker": "staff.approve_refund", "expires_at": "…", "approvals": [], …}
curl -X POST https://examleaf.in/api/v1/staff/change-requests/12/approve/ -d '{"payload_sha256": "9b1e…"}'
# 200 {"id": 12, "status": "approved", …}       403: not an approver, or the maker      400: another payload
curl -X POST https://examleaf.in/api/v1/staff/change-requests/12/execute/
# 200 {"id": 12, "status": "executed", "result": {"refund": 31, "amount": "2500.00", "status": "pending"}, …}
```

An order not shipped yet is cancelled (its stock back) and refunded in full (`"cancel": true`); a shipped one is refunded
by the amount, at most what was paid. If the order changed between the request and its run (shipped meanwhile, a refund
under way), the run fails (`status` "failed", `result.error`) instead of doing something else.

**Customers.** `users/?q=` finds an email address (exactly), a mobile number (any Indian format) or three letters or
more of a name. A customer's `status` is `active`, `suspended`, `pending_deletion` or `erased`; `consent` is `adult`,
`declared`, `pending` (a parent's link awaited) or `verified`; the detail adds `locked`, `mfa`, `teacher`, the masked
`parent_contact`, the latest orders, consents and devices.

```sh
curl -X POST https://examleaf.in/api/v1/staff/users/42/reveal/ -d '{"show": ["phone"], "reason": "Calling back about EL-2026-000123"}'
# 200 {"phone": "+919864012345"}      403 {"code": "reauthentication_required"}      429 after 30 an hour
```

**Data requests** carry `ack_due_at` (48 hours after `received_at`) and `due_at` (a month; 90 days for the DPDP
rights from 13 May 2027; a grievance or complaint keeps the month), with `ack_overdue` and `overdue`. An erasure's dry
run lists `erase` (what goes, with counts), `keep` (what stays, why, until when), `blocks` and `can_erase`.
**Incidents** carry `cert_in_due` (6 hours after `detected_at`) and `board_due` (72 hours), with `cert_in_overdue` and
`board_overdue` until `cert_in_reported_at` and `board_report_at` are set.

**API keys.** A key is made by an owner for one integration, with `view_` permissions only, for 12 months at most
(default), optionally from some addresses (`allowed_ips`, CIDR); its answer holds `key` once. Requests with it carry
`Authorization: Api-Key <key>`; they are throttled per key, recorded as a service in the audit log, refused anything that
needs a re-authentication, and get 401 when the key is revoked, expired, forged or used from elsewhere.

### Every staff endpoint and field

Generated from the OpenAPI schema and the views' own permission maps (`manage.py staff_api_reference`; a test fails
when this differs from the code). Paths are under `/api/v1/`: the staff API's, the shipping app's staff endpoints
and the insights', `{id}` an object's id. "Answers" are the successful ones; the errors are those above (400, 401,
403, 404, 405, 429). A field is (required) in a request, (null) when it may be null, (read-only) in answers only; a
`…Request` is what a POST, PUT or PATCH takes, a `Paginated…List` a page: a cursor page under `staff/`, a numbered one
(`count`, `?page=`) under `shipping/` and `insights/`.

<!-- staff-api-reference -->
| Method | Path | Permission | Query | Body | Answers |
|---|---|---|---|---|---|
| GET | `insights/backtests/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedBacktestList` |
| GET | `insights/chapter-stats/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedChapterStatList` |
| GET | `insights/code-activation/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedCodeActivationList` |
| GET | `insights/cohorts/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedCohortStatList` |
| GET | `insights/delivery/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedDeliveryStatList` |
| GET | `insights/forecasts/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedForecastList` |
| GET | `insights/fraud-signals/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedFraudSignalList` |
| POST | `insights/fraud-signals/{id}/acknowledge/` | `staff.acknowledge_signal` |  |  | 200 `FraudSignal` |
| GET | `insights/item-stats/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedItemStatList` |
| GET | `insights/offers/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedOfferStatList` |
| GET | `insights/print-runs/` | `staff.view_insights` | `page`, `page_size` |  | 200 `PaginatedPrintRunAdviceList` |
| GET | `shipping/charges/` | `staff.view_cod` | `kind`, `ordering`, `page`, `page_size`, `search`, `shipment` |  | 200 `PaginatedShipmentChargeList` |
| GET | `shipping/charges/{id}/` | `staff.view_cod` |  |  | 200 `ShipmentCharge` |
| GET | `shipping/cod/` | `staff.view_cod` | `ordering`, `page`, `page_size`, `search`, `state` |  | 200 `PaginatedCodRemittanceList` |
| GET | `shipping/cod/{id}/` | `staff.view_cod` |  |  | 200 `CodRemittance` |
| POST | `shipping/cod/{id}/reconcile/` | `staff.reconcile_cod` |  | `CodReconcileRequest` | 200 `CodRemittance` |
| GET | `shipping/exceptions/` | `staff.view_parcels` | `kind`, `ordering`, `page`, `page_size`, `search`, `shipment`, `state` |  | 200 `PaginatedShippingExceptionList` |
| GET | `shipping/exceptions/{id}/` | `staff.view_parcels` |  |  | 200 `ShippingException` |
| POST | `shipping/exceptions/{id}/resolve/` | `staff.act_on_exception` |  | `ResolveRequest` | 200 `ShippingException` |
| POST | `shipping/manifest/` | `staff.book_parcel` |  | `ManifestRequestRequest` | 200 `Manifest` |
| GET | `shipping/orders/{number}/quote/` | `staff.book_parcel` | `weight_g` |  | 200 `QuoteResult` |
| GET | `shipping/pickup-locations/` | `staff.view_parcels` | `ordering`, `page`, `page_size`, `search` |  | 200 `PaginatedPickupLocationList` |
| POST | `shipping/pickup-locations/` | `staff.manage_pickup_locations` |  | `PickupLocationRequest` | 201 `PickupLocation` |
| POST | `shipping/pickup-locations/sync/` | `staff.manage_pickup_locations` |  |  | 200 `[PickupLocation]` |
| GET | `shipping/pickup-locations/{id}/` | `staff.view_parcels` |  |  | 200 `PickupLocation` |
| PUT | `shipping/pickup-locations/{id}/` | `staff.manage_pickup_locations` |  | `PickupLocationRequest` | 200 `PickupLocation` |
| PATCH | `shipping/pickup-locations/{id}/` | `staff.manage_pickup_locations` |  | `PatchedPickupLocationRequest` | 200 `PickupLocation` |
| GET | `shipping/shipments/` | `staff.view_parcels` | `carrier`, `courier_company_id`, `order`, `ordering`, `page`, `page_size`, `search`, `status` |  | 200 `PaginatedParcelList` |
| POST | `shipping/shipments/` | `staff.book_parcel` |  | `BookRequest` | 201 `Parcel`; 202 `Parcel` |
| GET | `shipping/shipments/{id}/` | `staff.view_parcels` |  |  | 200 `ParcelHistory` |
| POST | `shipping/shipments/{id}/cancel/` | `staff.book_parcel` |  |  | 200 `Parcel` |
| GET | `shipping/shipments/{id}/events/` | `staff.view_parcels` |  |  | 200 `[ShipmentEvent]` |
| GET | `shipping/shipments/{id}/label/` | `staff.book_parcel` |  |  | 200 `application/pdf` |
| POST | `shipping/shipments/{id}/label/` | `staff.book_parcel` |  |  | 202 `Detail` |
| POST | `shipping/shipments/{id}/ndr-action/` | `staff.act_on_exception` |  | `NdrActionRequest` | 200 `ShippingException` |
| POST | `shipping/shipments/{id}/photo/` | `staff.book_parcel` |  | `PhotoRequest` | 200 `Parcel` |
| POST | `shipping/shipments/{id}/pickup/` | `staff.book_parcel` |  | `PickupRequestRequest` | 200 `PickupResult` |
| GET | `staff/access-review/` | `staff.view_staff` |  |  | 200 `[AccessRow]` |
| GET | `staff/api-keys/` | `staff.view_apikey` | `cursor`, `page_size` |  | 200 `PaginatedApiKeyList` |
| POST | `staff/api-keys/` | `staff.manage_api_keys` |  | `ApiKeyRequest` | 201 `ApiKey` |
| GET | `staff/api-keys/{id}/` | `staff.view_apikey` |  |  | 200 `ApiKey` |
| POST | `staff/api-keys/{id}/revoke/` | `staff.manage_api_keys` |  |  | 200 `ApiKey` |
| GET | `staff/audit/` | `staff.view_auditlog` | `action`, `action_prefix`, `actor`, `actor_type`, `break_glass`, `chain`, `change_request`, `cursor`, `ip`, `outcome`, `page_size`, `permission`, `request_id`, `since`, `target_id`, `target_type`, `until` |  | 200 `PaginatedAuditEventList` |
| POST | `staff/audit/export/` | `staff.export_auditlog` |  | `ExportRequest` | 200 `application/x-ndjson`; 202 `Job` |
| GET | `staff/audit/{id}/` | `staff.view_auditlog` |  |  | 200 `AuditEvent` |
| GET | `staff/catalogue/` | any member of staff |  |  | 200 `StaffCatalogue` |
| GET | `staff/change-requests/` | `staff.view_changerequest` | `action`, `awaiting`, `cursor`, `mine`, `page_size`, `status` |  | 200 `PaginatedChangeRequestList` |
| POST | `staff/change-requests/` | `staff.add_changerequest` |  | `AskRequest` | 200 `ChangeRequest`; 201 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/change-requests/{id}/` | `staff.view_changerequest` |  |  | 200 `ChangeRequest` |
| POST | `staff/change-requests/{id}/approve/` | `staff.view_changerequest` |  | `ApproveRequest` | 200 `ChangeRequest` |
| POST | `staff/change-requests/{id}/execute/` | `staff.view_changerequest` |  |  | 200 `ChangeRequest`; 400 `ChangeRequest` |
| POST | `staff/change-requests/{id}/reject/` | `staff.view_changerequest` |  | `CommentRequest` | 200 `ChangeRequest` |
| GET | `staff/data-requests/` | `staff.view_datarequest` | `assignee`, `cursor`, `kind`, `overdue`, `page_size`, `status`, `user` |  | 200 `PaginatedDataRequestListList` |
| POST | `staff/data-requests/` | `staff.handle_data_request` |  | `DataRequestRequest` | 201 `DataRequest` |
| GET | `staff/data-requests/{id}/` | `staff.view_datarequest` |  |  | 200 `DataRequest` |
| PATCH | `staff/data-requests/{id}/` | `staff.handle_data_request` |  | `PatchedDataRequestRequest` | 200 `DataRequest` |
| POST | `staff/data-requests/{id}/acknowledge/` | `staff.handle_data_request` |  |  | 200 `DataRequest` |
| POST | `staff/data-requests/{id}/close/` | `staff.handle_data_request` |  | `CloseRequest` | 200 `DataRequest` |
| POST | `staff/data-requests/{id}/erase/` | `staff.handle_data_request` |  | `ReasonRequest` | 202 `ChangeRequest`; 400 `ErasureReport` |
| GET | `staff/data-requests/{id}/erasure-report/` | `staff.view_datarequest` |  |  | 200 `ErasureReport` |
| POST | `staff/data-requests/{id}/export/` | `staff.export_personal_data` |  |  | 202 `Detail` |
| GET | `staff/data-requests/{id}/response/` | `staff.view_datarequest` |  |  | 200 `ResponseText` |
| POST | `staff/data-requests/{id}/verify-identity/` | `staff.handle_data_request` |  | `VerifyIdentityRequest` | 200 `DataRequest` |
| GET | `staff/erp/cursors/` | `erp.view_sync` | `cursor`, `page_size` |  | 200 `PaginatedErpCursorList` |
| GET | `staff/erp/dead-letters/` | `erp.view_sync` | `aggregate_id`, `aggregate_type`, `cursor`, `event`, `page_size` |  | 200 `PaginatedErpOutboxList` |
| GET | `staff/erp/dead-letters/{id}/` | `erp.view_sync` |  |  | 200 `ErpOutbox` |
| POST | `staff/erp/dead-letters/{id}/discard/` | `erp.replay_sync` |  | `ErpDiscardRequest` | 200 `ErpOutbox` |
| POST | `staff/erp/dead-letters/{id}/replay/` | `erp.replay_sync` |  |  | 200 `ErpOutbox` |
| GET | `staff/erp/differences/` | `erp.view_sync` | `cursor`, `kind`, `open`, `page_size`, `run` |  | 200 `PaginatedErpDifferenceList` |
| GET | `staff/erp/differences/{id}/` | `erp.view_sync` |  |  | 200 `ErpDifference` |
| POST | `staff/erp/differences/{id}/resolve/` | `erp.resolve_difference` |  | `ErpResolveRequest` | 200 `ErpDifference` |
| GET | `staff/erp/outbox/` | `erp.view_sync` | `aggregate_id`, `aggregate_type`, `cursor`, `event`, `examleaf_ref`, `page_size`, `state` |  | 200 `PaginatedErpOutboxList` |
| GET | `staff/erp/outbox/{id}/` | `erp.view_sync` |  |  | 200 `ErpOutbox` |
| GET | `staff/erp/reconciliations/` | `erp.view_sync` | `cursor`, `date`, `page_size`, `state` |  | 200 `PaginatedErpRunList` |
| GET | `staff/erp/reconciliations/{id}/` | `erp.view_sync` |  |  | 200 `ErpRunDetail` |
| GET | `staff/erp/status/` | `erp.view_sync` |  |  | 200 `ErpStatus` |
| GET | `staff/flags/` | `staff.view_featureflag` |  |  | 200 `[Flag]` |
| GET | `staff/flags/{key}/` | `staff.view_featureflag` |  |  | 200 `[SwitchRow]` |
| PUT | `staff/flags/{key}/` | `staff.manage_flags` |  | `SwitchChangeRequest` | 200 `SwitchRow` |
| GET | `staff/inbox/` | `staff.view_inbox` | `cursor`, `done`, `kind`, `mine`, `page_size`, `snoozed` |  | 200 `PaginatedInboxItemList` |
| GET | `staff/inbox/count/` | `staff.view_inbox` |  |  | 200 `InboxCount` |
| POST | `staff/inbox/{id}/assign/` | `staff.view_inbox` |  | `AssignRequest` | 200 `InboxItem` |
| POST | `staff/inbox/{id}/done/` | `staff.view_inbox` |  |  | 200 `InboxItem` |
| POST | `staff/inbox/{id}/snooze/` | `staff.view_inbox` |  | `SnoozeRequest` | 200 `InboxItem` |
| GET | `staff/incidents/` | `staff.view_incident` | `cursor`, `kind`, `open`, `page_size` |  | 200 `PaginatedIncidentList` |
| POST | `staff/incidents/` | `staff.manage_incident` |  | `IncidentRequest` | 201 `Incident` |
| GET | `staff/incidents/{id}/` | `staff.view_incident` |  |  | 200 `Incident` |
| PATCH | `staff/incidents/{id}/` | `staff.manage_incident` |  | `PatchedIncidentRequest` | 200 `Incident` |
| POST | `staff/incidents/{id}/close/` | `staff.manage_incident` |  |  | 200 `Incident` |
| POST | `staff/invites/accept/` | none: the invitation's token |  | `AcceptRequest` | 200 `Detail` |
| GET | `staff/jobs/` | `staff.view_job` | `cursor`, `kind`, `mine`, `page_size`, `state` |  | 200 `PaginatedJobList` |
| POST | `staff/jobs/` | `staff.add_job` (by the key or the body: see the table above) |  | `JobStartRequest` | 202 `Job` |
| GET | `staff/jobs/{id}/` | `staff.view_job` |  |  | 200 `Job` |
| POST | `staff/jobs/{id}/cancel/` | `staff.view_job` |  |  | 200 `Job` |
| GET | `staff/jobs/{id}/result/` | `staff.view_job` | `token` |  | 200 `application/octet-stream`; 302 |
| GET | `staff/notes/` | `staff.view_note` | `target_id`, `target_type` |  | 200 `[Note]` |
| POST | `staff/notes/` | `staff.add_note` |  | `NoteRequest` | 201 `Note` |
| GET | `staff/people/` | `staff.view_staff` | `cursor`, `page_size` |  | 200 `PaginatedPersonList` |
| POST | `staff/people/invite/` | `staff.assign_role` |  | `InviteRequest` | 201 `StaffInvite`; 202 `ChangeRequest` |
| GET | `staff/people/invites/` | `staff.view_staff` | `cursor`, `page_size` |  | 200 `PaginatedStaffInviteList` |
| DELETE | `staff/people/invites/{invite}/` | `staff.assign_role` |  |  | 204 |
| GET | `staff/people/{id}/` | `staff.view_staff` |  |  | 200 `Person` |
| POST | `staff/people/{id}/end-sessions/` | `staff.assign_role` |  |  | 200 `Ended` |
| POST | `staff/people/{id}/offboard/` | `staff.assign_role` |  | `ReasonRequest` | 200 `Offboarded` |
| POST | `staff/people/{id}/reset-mfa/` | `staff.reset_user_mfa` |  | `ReasonRequest` | 202 `ChangeRequest` |
| POST | `staff/people/{id}/roles/` | `staff.assign_role` |  | `GrantRequest` | 200 `Person`; 202 `ChangeRequest` |
| DELETE | `staff/people/{id}/roles/{role}/` | `staff.assign_role` |  |  | 200 `Person` |
| POST | `staff/people/{id}/scopes/` | `staff.assign_role` |  | `ScopeAddRequest` | 201 `Scope` |
| DELETE | `staff/people/{id}/scopes/{scope}/` | `staff.assign_role` |  |  | 204 |
| GET | `staff/policies/ack/` | any member of staff | `user` |  | 200 `[PolicyAcknowledgement]` |
| POST | `staff/policies/ack/` | any member of staff |  | `PolicyAcknowledgementRequest` | 200 `PolicyAcknowledgement`; 201 `PolicyAcknowledgement` |
| GET | `staff/processors/` | `staff.view_processorrecord` | `cursor`, `page_size` |  | 200 `PaginatedProcessorList` |
| POST | `staff/processors/` | `staff.add_processorrecord` |  | `ProcessorRequest` | 201 `Processor` |
| GET | `staff/processors/{id}/` | `staff.view_processorrecord` |  |  | 200 `Processor` |
| PUT | `staff/processors/{id}/` | `staff.change_processorrecord` |  | `ProcessorRequest` | 200 `Processor` |
| PATCH | `staff/processors/{id}/` | `staff.change_processorrecord` |  | `PatchedProcessorRequest` | 200 `Processor` |
| DELETE | `staff/processors/{id}/` | `staff.delete_processorrecord` |  |  | 204 |
| GET | `staff/saved-views/` | `staff.view_savedview` | `cursor`, `list_key`, `page_size` |  | 200 `PaginatedSavedViewList` |
| POST | `staff/saved-views/` | `staff.add_savedview` |  | `SavedViewRequest` | 201 `SavedView` |
| GET | `staff/saved-views/{id}/` | `staff.view_savedview` |  |  | 200 `SavedView` |
| PUT | `staff/saved-views/{id}/` | `staff.change_savedview` |  | `SavedViewRequest` | 200 `SavedView` |
| PATCH | `staff/saved-views/{id}/` | `staff.change_savedview` |  | `PatchedSavedViewRequest` | 200 `SavedView` |
| DELETE | `staff/saved-views/{id}/` | `staff.delete_savedview` |  |  | 204 |
| GET | `staff/session/` | any member of staff |  |  | 200 `StaffManifest` |
| POST | `staff/session/reason/` | any member of staff |  | `BreakGlassReasonRequest` | 200 `StaffBreakGlass` |
| GET | `staff/settings/` | `staff.view_sitesetting` |  |  | 200 `[Setting]` |
| GET | `staff/settings/{key}/` | `staff.view_sitesetting` (by the key or the body: see the table above) |  |  | 200 `[SwitchRow]` |
| PUT | `staff/settings/{key}/` | `staff.manage_settings` (by the key or the body: see the table above) |  | `SwitchChangeRequest` | 200 `Setting` |
| GET | `staff/support/agents/` | `support.view_ticket` |  |  | 200 `[Agent]` |
| GET | `staff/support/saved-replies/` | `support.view_savedreply` | `bin`, `cursor`, `language`, `page_size` |  | 200 `PaginatedSavedReplyList` |
| POST | `staff/support/saved-replies/` | `support.add_savedreply` |  | `SavedReplyRequest` | 201 `SavedReply` |
| GET | `staff/support/saved-replies/{id}/` | `support.view_savedreply` |  |  | 200 `SavedReply` |
| PUT | `staff/support/saved-replies/{id}/` | `support.change_savedreply` |  | `SavedReplyRequest` | 200 `SavedReply` |
| PATCH | `staff/support/saved-replies/{id}/` | `support.change_savedreply` |  | `PatchedSavedReplyRequest` | 200 `SavedReply` |
| DELETE | `staff/support/saved-replies/{id}/` | `support.delete_savedreply` |  |  | 204 |
| POST | `staff/support/saved-replies/{id}/restore/` | `support.delete_savedreply` |  |  | 200 `SavedReply` |
| GET | `staff/support/summary/` | `support.view_ticket` | `days` |  | 200 `SupportSummary` |
| GET | `staff/support/tickets/` | `support.view_ticket` | `assignee`, `category`, `cursor`, `language`, `mine`, `open`, `overdue`, `page_size`, `priority`, `q`, `source`, `status`, `test`, `unassigned`, `waiting` |  | 200 `PaginatedTicketList` |
| POST | `staff/support/tickets/` | `staff.handle_ticket` |  | `TicketCreateRequest` | 201 `TicketDetail` |
| GET | `staff/support/tickets/{number}/` | `support.view_ticket` |  |  | 200 `TicketRecord` |
| PATCH | `staff/support/tickets/{number}/` | `staff.handle_ticket` |  | `PatchedTicketChangeRequest` | 200 `TicketDetail` |
| POST | `staff/support/tickets/{number}/acknowledge/` | `staff.handle_ticket` |  | `AcknowledgeRequest` | 200 `Ticket` |
| POST | `staff/support/tickets/{number}/assign/` | `staff.handle_ticket` |  | `TicketAssignRequest` | 200 `Ticket` |
| GET | `staff/support/tickets/{number}/attachments/{attachment}/` | `support.view_ticket` |  |  | 200 `application/octet-stream`; 302 |
| POST | `staff/support/tickets/{number}/book-code/` | `learn.view_bookcode` |  | `BookCodeLookupRequest` | 200 `CodeAnswer` |
| POST | `staff/support/tickets/{number}/cancel/` | `shop.change_order` (by the key or the body: see the table above) |  | `CancelRequest` | 200 `TicketOrderCancelled`; 201 `ChangeRequest`; 202 `ChangeRequest`; 400 `ChangeRequest` |
| POST | `staff/support/tickets/{number}/claim/` | `staff.handle_ticket` |  |  | 200 `Ticket` |
| POST | `staff/support/tickets/{number}/data-request/` | `staff.handle_data_request` |  | `DataRequestStartRequest` | 201 `DataRequest` |
| POST | `staff/support/tickets/{number}/extend-access/` | `learn.change_entitlement` |  | `ExtendRequest` | 200 `AccessExtended` |
| POST | `staff/support/tickets/{number}/messages/` | `staff.handle_ticket` (by the key or the body: see the table above) |  | `MessageCreateRequest` | 201 `Message` |
| POST | `staff/support/tickets/{number}/refund/` | `staff.refund_order` |  | `RefundRequest` | 200 `ChangeRequest`; 201 `ChangeRequest`; 202 `ChangeRequest`; 400 `ChangeRequest` |
| POST | `staff/support/tickets/{number}/reopen/` | `staff.handle_ticket` |  |  | 200 `Ticket` |
| POST | `staff/support/tickets/{number}/resend-confirmation/` | `staff.handle_ticket` |  | `OrderActionRequest` | 200 `Detail` |
| POST | `staff/support/tickets/{number}/resend-invoice/` | `staff.handle_ticket` |  | `OrderActionRequest` | 200 `Detail` |
| POST | `staff/support/tickets/{number}/reveal/` | `staff.reveal_contact` |  | `TicketRevealRequest` | 200 `TicketRevealed` |
| POST | `staff/support/tickets/{number}/status/` | `staff.handle_ticket` |  | `StatusRequest` | 200 `Ticket` |
| GET | `staff/system/` | `staff.view_system` |  |  | 200 `StaffSystem` |
| POST | `staff/system/reconcile/` | `staff.replay_webhook` |  | `ReconcileRequest` | 200 `Reconciled` |
| GET | `staff/users/` | `accounts.view_user` | `board`, `class_level`, `cursor`, `is_active`, `page_size`, `q` |  | 200 `PaginatedCustomerList` |
| GET | `staff/users/{id}/` | `accounts.view_user` |  |  | 200 `CustomerDetail` |
| POST | `staff/users/{id}/end-sessions/` | `staff.end_user_sessions` |  |  | 200 `SessionsEnded` |
| POST | `staff/users/{id}/impersonate/` | `staff.impersonate_user` |  | `ImpersonateRequest` | 200 `Impersonation` |
| POST | `staff/users/{id}/impersonate/end/` | `staff.impersonate_user` |  | `TokenRequest` | 204 |
| POST | `staff/users/{id}/password-reset/` | `staff.initiate_password_reset` |  |  | 200 `Detail` |
| POST | `staff/users/{id}/resend-verification/` | `staff.resend_verification` |  |  | 200 `Detail` |
| POST | `staff/users/{id}/reset-mfa/` | `staff.reset_user_mfa` |  | `ReasonRequest` | 202 `ChangeRequest` |
| POST | `staff/users/{id}/reveal/` | `staff.reveal_contact` |  | `RevealRequest` | 200 `Revealed` |
| POST | `staff/users/{id}/suspend/` | `staff.suspend_user` |  | `ReasonRequest` | 200 `Customer` |
| POST | `staff/users/{id}/unlock/` | `staff.unlock_user` |  |  | 200 `Unlocked` |
| POST | `staff/users/{id}/unsuspend/` | `staff.suspend_user` |  | `ReasonRequest` | 200 `Customer` |

- **AcceptRequest**: `token` string (required); `full_name` string; `password` string
- **AccessExtended**: `entitlement` integer (required); `valid_until` date (required)
- **AccessRow**: `id` integer (required); `email` email (required); `roles` [string] (required); `grants` [object] (required); `scopes` object (required); `last_login` date-time (required, null); `dormant` boolean (required); `mfa` boolean (required); `permissions` integer (required); `unused` [string] (required); `last_used` object (required)
- **AcknowledgeRequest**: `note` string
- **ActorTypeEnum**: one of `staff`, `user`, `service`, `system`, `anonymous`
- **Agent**: `id` integer (required); `name` string (required); `handles` boolean (required)
- **ApiKey**: `id` integer (required, read-only); `name` string (required); `prefix` string (required, read-only); `key` string (required, null, read-only); `scopes` any; `sponsor` integer; `created_by` integer (required, null, read-only); `created` date-time (required, read-only); `expires_at` date-time; `allowed_ips` any; `last_used_at` date-time (required, null, read-only); `last_used_ip` string (required, null, read-only); `revoked_at` date-time (required, null, read-only); `revoked_by` integer (required, null, read-only)
- **ApiKeyRequest**: `name` string (required); `scopes` any; `sponsor` integer; `expires_at` date-time; `allowed_ips` any
- **Approval**: `user` integer (required); `decision` DecisionEnum (required); `comment` string; `created` date-time
- **ApproveRequest**: `payload_sha256` string (required); `comment` string; `override` boolean
- **AskActionEnum**: one of `order.refund`, `order.offline_payment`, `product.price`, `coupon.create`
- **AskRequest**: `action` AskActionEnum (required); `target` string (required); `payload` object (required); `reason` string (required)
- **AssignRequest**: `assignee` integer (required, null)
- **Attachment**: `id` integer (required, read-only); `name` string (required, read-only); `content_type` string (required, read-only); `size` integer (required, read-only)
- **AuditEvent**: `id` integer (required, read-only); `chain` ChainEnum; `ts` date-time (required); `actor_id` integer (null); `actor_type` ActorTypeEnum (required); `actor_roles` any; `on_behalf_of` integer (null); `break_glass` boolean; `action` string (required); `permission` string; `target_type` string; `target_id` string; `target_label` string; `outcome` AuditOutcomeEnum; `reason` string; `change_request_id` integer (null); `request_id` string; `ip` string (null); `user_agent` string; `session_hash` string; `changes` any; `details` any; `prev_hash` string (required); `hash` string (required)
- **AuditOutcomeEnum**: one of `success`, `denied`, `failed`
- **Backtest**: `product` string (required, read-only); `horizon_weeks` integer (required); `wape` double (null); `mase_vs_seasonal_naive` double (null); `shown` boolean; `n` integer (required, read-only)
- **BlankEnum**: null
- **BookCodeLookupRequest**: `code` string (required)
- **BookRequest**: `order` string (required, null); `courier_company_id` integer; `courier_name` string; `quoted_rate` decimal (null); `weight_g` integer; `length_cm` integer; `breadth_cm` integer; `height_cm` integer; `pickup_location` integer (null); `courier` CourierEnum; `tracking_number` string; `tracking_url` any
- **BreakGlassReasonRequest**: `reason` string (required)
- **CancelRequest**: `order` string; `reason` string (required)
- **CarrierEnum**: one of `manual`, `shiprocket`
- **ChainEnum**: one of `general`, `money`
- **ChangeRequest**: `id` integer (required, read-only); `action` string (required); `label` string (required, read-only); `target_type` string; `target_id` string; `target_label` string; `payload` any; `payload_sha256` string (required); `amount` decimal (null); `maker` integer (required); `reason` string (required); `rule` string; `status` ChangeRequestStatusEnum; `expires_at` date-time (required); `overridden` boolean; `checker` string (required, read-only); `approvals` [Approval] (required, read-only); `result` any (null); `executed_by` integer (null); `executed_at` date-time (null); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **ChangeRequestStatusEnum**: one of `pending`, `approved`, `rejected`, `expired`, `executed`, `failed`
- **ChannelEnum**: one of `email`, `letter`, `phone`, `form`, `in_person`, `board`
- **ChapterStat**: `chapter` integer (required); `subject` integer (required, read-only); `number` integer (required, read-only); `title` string (required, read-only); `mean_accuracy` double (null); `trend` double (null); `n` integer (required, read-only)
- **ClassLevelEnum**: one of `10`, `12`
- **Clock**: `name` string (required); `kind` string (required); `due` date-time (required); `rule` string (required); `stopped_at` date-time (required, null); `breached` boolean (required)
- **CloseRequest**: `outcome` DataRequestOutcomeEnum (required); `response` string (required)
- **CodReconcileRequest**: `utr` string (required); `amount` decimal (required); `on` date
- **CodRemittance**: `id` integer (required, read-only); `shipment` integer (required, read-only); `order` string (required, read-only); `expected_amount` decimal (required, read-only); `expected_on` date (required, read-only); `remitted_amount` decimal (required, null, read-only); `utr` string (required, read-only); `remitted_at` date (required, null, read-only); `state` CodRemittanceStateEnum (required, read-only); `checked_at` date-time (required, null, read-only)
- **CodRemittanceStateEnum**: one of `expected`, `overdue`, `remitted`, `mismatch`, `not_expected`
- **CodeActivation**: `batch` string (required); `district` string (null); `printed` integer (null); `redeemed` integer (required); `redeemed_7d` integer (required); `n` integer (required, read-only)
- **CodeAnswer**: `found` boolean (required); `batch` string; `subject` string; `redeemed` boolean; `by_requester` boolean; `line` string (required)
- **CodeRow**: `batch` string (required); `subject` string (required); `redeemed_at` date-time (required)
- **CohortStat**: `cohort_month` date (required); `source` EntitlementSourceEnum (required); `week_index` integer (required); `active_share` double (null); `churned_share` double (null); `n` integer (required)
- **CommentRequest**: `comment` string
- **ConsentRow**: `event` string (required); `method` string (required); `by_parent` boolean (required); `verified_at` date-time (required, null); `notice_version` string (required); `created` date-time (required)
- **CourierEnum**: one of `India Post`, `Delhivery`, `Blue Dart`, `Ekart`, `DTDC`, `Xpressbees`, `Other`
- **Customer**: `id` integer (required, read-only); `email` string (required, read-only); `phone` string (required, read-only); `full_name` string (required); `class_level` any (null); `board` string (required, read-only); `district` string; `under_18` boolean (required, read-only); `status` string (required, read-only); `consent` string (required, read-only); `email_verified` boolean (required, read-only); `login_phone_verified` boolean; `created` date-time (required, read-only); `last_login` date-time (null)
- **CustomerDetail**: `id` integer (required, read-only); `email` string (required, read-only); `phone` string (required, read-only); `full_name` string (required); `class_level` any (null); `board` string (required, read-only); `district` string; `under_18` boolean (required, read-only); `status` string (required, read-only); `consent` string (required, read-only); `email_verified` boolean (required, read-only); `login_phone_verified` boolean; `created` date-time (required, read-only); `last_login` date-time (null); `roles` [string] (required, read-only); `locked` boolean (required, read-only); `mfa` [string] (required, read-only); `teacher` string (required, read-only); `parent_contact` string (required, read-only); `orders` [object] (required, read-only); `consents` [object] (required, read-only); `sessions` [object] (required, read-only); `deletion_due_at` string (required, null, read-only)
- **DataRequest**: `id` integer (required, read-only); `kind` DataRequestKindEnum (required); `channel` ChannelEnum (required); `user` integer (null); `requester` string (required); `summary` string (required); `identity_verified` boolean (required, read-only); `identity_note` string (required, read-only); `verified_by` integer (required, null, read-only); `verified_at` date-time (required, null, read-only); `received_at` date-time; `ack_due_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `ack_overdue` boolean (required, read-only); `due_at` date-time (required, read-only); `overdue` boolean (required, read-only); `status` DataRequestStatusEnum (required, read-only); `assignee` integer (null); `notes` string; `details` any; `outcome` DataRequestOutcomeEnum (required, read-only); `response` string (required, read-only); `closed_at` date-time (required, null, read-only); `closed_by` integer (required, null, read-only); `created_by` integer (required, null, read-only)
- **DataRequestKindEnum**: one of `access`, `correction`, `erasure`, `nomination`, `grievance`, `complaint`
- **DataRequestList**: `id` integer (required, read-only); `kind` DataRequestKindEnum (required); `channel` ChannelEnum (required); `user` integer (null); `requester` string (required, read-only); `summary` string (required); `identity_verified` boolean (required, read-only); `identity_note` string (required, read-only); `verified_by` integer (required, null, read-only); `verified_at` date-time (required, null, read-only); `received_at` date-time; `ack_due_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `ack_overdue` boolean (required, read-only); `due_at` date-time (required, read-only); `overdue` boolean (required, read-only); `status` DataRequestStatusEnum (required, read-only); `assignee` integer (null); `notes` string; `details` any; `outcome` DataRequestOutcomeEnum (required, read-only); `response` string (required, read-only); `closed_at` date-time (required, null, read-only); `closed_by` integer (required, null, read-only); `created_by` integer (required, null, read-only)
- **DataRequestOutcomeEnum**: one of `done`, `refused`, `withdrawn`
- **DataRequestRequest**: `kind` DataRequestKindEnum (required); `channel` ChannelEnum (required); `user` integer (null); `requester` string (required); `summary` string (required); `received_at` date-time; `assignee` integer (null); `notes` string; `details` any
- **DataRequestStartRequest**: `kind` DataRequestKindEnum (required); `summary` string
- **DataRequestStatusEnum**: one of `new`, `acknowledged`, `closed`
- **DecisionEnum**: one of `approve`, `reject`
- **DeliveryStat**: `courier` string (required); `district` string (null); `median_days` double (required); `p90_days` double (required); `n` integer (required)
- **Detail**: `detail` string (required)
- **DeviceRow**: `kind` string (required); `label` string (required); `ip` string (required); `last_seen` date-time (required, null)
- **Ended**: `sessions` integer (required); `tokens` integer (required)
- **EntitlementRow**: `id` integer (required); `subject` string (required); `source` string (required); `reference` string (required); `valid_until` date (required, null); `active` boolean (required)
- **EntitlementSourceEnum**: one of `book_code`, `purchase`, `grant`
- **ErasureReport**: `erase` [object] (required); `keep` [object] (required); `blocks` [string] (required); `can_erase` boolean (required); `notes` [string] (required)
- **ErpAccountStatus**: `id` integer (required); `label` string (required); `mode` string (required); `circuit` string (required); `last_success_at` date-time (required, null); `last_error` string (required)
- **ErpCursor**: `id` integer (required, read-only); `doctype` string (required, read-only); `modified_after` string (required, read-only); `last_name` string (required, read-only); `rows_read` integer (required, read-only); `last_run_at` date-time (required, null, read-only); `last_error` string (required, read-only)
- **ErpCursorStatus**: `doctype` string (required); `modified_after` string (required); `last_run_at` date-time (required, null); `error` string (required)
- **ErpDifference**: `id` integer (required, read-only); `run` integer (required, read-only); `kind` ErpDifferenceKindEnum (required, read-only); `key` string (required, read-only); `platform_value` string (required, read-only); `erp_value` string (required, read-only); `note` string (required, read-only); `resolved_at` date-time (required, null, read-only); `resolved_by` integer (required, null, read-only)
- **ErpDifferenceKindEnum**: one of `invoices`, `credit_notes`, `payments`, `settlements`, `deliveries`, `stock`, `missing`
- **ErpDiscardRequest**: `reason` string (required)
- **ErpOutbox**: `id` integer (required, read-only); `aggregate_type` string (required, read-only); `aggregate_id` string (required, read-only); `sequence` integer (required, read-only); `event` string (required, read-only); `examleaf_ref` string (required, read-only); `model` string (required, read-only); `object_id` string (required, read-only); `idempotency_key` string (required, read-only); `payload` any (required, null, read-only); `state` ErpOutboxStateEnum (required, read-only); `attempts` integer (required, read-only); `next_at` date-time (required, read-only); `last_error` string (required, read-only); `created` date-time (required, read-only); `sent_at` date-time (required, null, read-only); `response` any (required, null, read-only); `dead_letter` integer (required, null, read-only)
- **ErpOutboxStateEnum**: one of `pending`, `sending`, `sent`, `failed`, `dead`, `discarded`
- **ErpReconciliationStateEnum**: one of `running`, `done`, `failed`
- **ErpResolveRequest**: `note` string (required)
- **ErpRun**: `id` integer (required, read-only); `date` date (required, read-only); `state` ErpReconciliationStateEnum (required, read-only); `platform_totals` any (required, read-only); `erp_totals` any (required, read-only); `differences_count` integer (required, read-only); `started_at` date-time (required, read-only); `finished_at` date-time (required, null, read-only); `error` string (required, read-only)
- **ErpRunDetail**: `id` integer (required, read-only); `date` date (required, read-only); `state` ErpReconciliationStateEnum (required, read-only); `platform_totals` any (required, read-only); `erp_totals` any (required, read-only); `differences_count` integer (required, read-only); `started_at` date-time (required, read-only); `finished_at` date-time (required, null, read-only); `error` string (required, read-only); `differences` [ErpDifference] (required, read-only)
- **ErpRunStatus**: `id` integer (required); `date` date (required); `state` string (required); `differences` integer (required); `open_differences` integer (required); `finished_at` date-time (required, null)
- **ErpStatus**: `enabled` boolean (required); `mode` string (required); `flows` object (required); `pull_stock` boolean (required); `pull_b2b` boolean (required); `stock_projection` boolean (required); `account` ErpAccountStatus (required, null); `outbox` object (required); `oldest_waiting_at` date-time (required, null); `oldest_waiting_seconds` integer (required, null); `held_aggregates` integer (required); `cursors` [ErpCursorStatus] (required); `last_reconciliation` ErpRunStatus (required, null)
- **ExportRequest**: `filters` object
- **ExtendRequest**: `entitlement` integer (required); `days` integer (required); `reason` string (required)
- **Flag**: `key` string (required); `value` any (required); `effective_from` date-time (required); `changed_by` integer (required, null); `reason` string (required)
- **Forecast**: `product` string (required, read-only); `title` string (required, read-only); `district` string (null); `week_start` date (required); `p10` double (required); `p50` double (required); `p90` double (required); `n` integer (required, read-only)
- **FraudSignal**: `id` integer (required, read-only); `kind` FraudSignalKindEnum (required); `label` string (required, read-only); `subject` string (required); `window_start` date-time (required); `window_end` date-time (required); `details` any; `created` date-time (required, read-only); `acknowledged_at` date-time (null); `n` integer (required, read-only)
- **FraudSignalKindEnum**: one of `codes_failed_account`, `codes_failed_ip`, `codes_failed_spike`, `codes_per_account`, `accounts_per_code`, `shared_phone`, `shared_address`
- **GrantRequest**: `role` RoleEnum (required); `expires_at` date-time (null); `reason` string (required)
- **ImpersonateRequest**: `reason` string (required); `ticket` string (required)
- **Impersonation**: `token` string (required); `expires_at` date-time (required)
- **InboxCount**: `open` integer (required); `overdue` integer (required)
- **InboxItem**: `id` integer (required, read-only); `kind` InboxKindEnum (required); `title` string (required); `target_type` string; `target_id` string; `permission` string (required); `assignee` integer (null); `due_at` date-time (null); `overdue` boolean (required, read-only); `snoozed_until` date-time (null); `done_at` date-time (null); `done_by` integer (null); `data` any; `created` date-time
- **InboxKindEnum**: one of `approval`, `teacher_request`, `deletion_request`, `data_request`, `incident`, `failed_job`, `failed_webhook`, `sync_failed`, `reconciliation`, `shipping_exception`, `dead_letter`, `failed_event`, `integration_down`, `ticket_due`, `ticket_breach`, `ticket_mention`
- **Incident**: `id` integer (required, read-only); `title` string (required); `kind` IncidentKindEnum (required); `detected_at` date-time; `noticed_by` integer (required, null, read-only); `description` string; `systems` string; `data_categories` string; `people_affected` integer (null); `children_affected` boolean; `cert_in_due` date-time (required, read-only); `cert_in_overdue` boolean (required, read-only); `cert_in_reported_at` date-time (null); `cert_in_reference` string; `board_due` date-time (required, read-only); `board_overdue` boolean (required, read-only); `board_notified_at` date-time (null); `board_report_at` date-time (null); `board_reference` string; `notice_text` string; `notices_sent` integer; `notices_sent_at` date-time (null); `actions` string; `root_cause` string; `closed_at` date-time (required, null, read-only); `closed_by` integer (required, null, read-only); `created` date-time (required, read-only)
- **IncidentKindEnum**: one of `data_breach`, `data_leak`, `unauthorised_access`, `malicious_code`, `application_attack`, `denial_of_service`, `loss_of_access`, `other`
- **IncidentRequest**: `title` string (required); `kind` IncidentKindEnum (required); `detected_at` date-time; `description` string; `systems` string; `data_categories` string; `people_affected` integer (null); `children_affected` boolean; `cert_in_reported_at` date-time (null); `cert_in_reference` string; `board_notified_at` date-time (null); `board_report_at` date-time (null); `board_reference` string; `notice_text` string; `notices_sent` integer; `notices_sent_at` date-time (null); `actions` string; `root_cause` string
- **InviteRequest**: `email` email (required); `role` RoleEnum (required); `reason` string (required)
- **ItemStat**: `item` integer (required); `chapter` integer (required, read-only); `kind` string (required, read-only); `text` string (required, read-only); `n` integer (required); `p` double (null); `discrimination` double (null); `flags` any
- **Job**: `id` integer (required, read-only); `kind` JobKindEnum (required, read-only); `state` JobStateEnum (required, read-only); `dry_run` boolean (required, read-only); `params` any (required, read-only); `done` integer (required, read-only); `total` integer (required, read-only); `errors` [JobError] (required, read-only); `result` any (required, read-only); `result_url` string (required, null, read-only); `change_request_id` integer (required, null, read-only); `cancel_requested` boolean (required, read-only); `started_by` integer (required, null, read-only); `created` date-time (required, read-only); `started_at` date-time (required, null, read-only); `finished_at` date-time (required, null, read-only)
- **JobError**: `id` any (required, null); `label` string (required); `message` string (required)
- **JobKindEnum**: one of `audit_export`, `bulk_action`, `erp_initial_load`, `grievance_export`
- **JobStartRequest**: `kind` JobKindEnum (required); `params` object; `dry_run` boolean
- **JobStateEnum**: one of `queued`, `running`, `done`, `failed`, `cancelled`
- **LevelEnum**: one of `ok`, `watch`, `act`
- **Manifest**: `url` uri (required)
- **ManifestRequestRequest**: `shipments` [integer] (required)
- **Message**: `id` integer (required, read-only); `direction` TicketDirectionEnum (required, read-only); `channel` TicketChannelEnum (required, read-only); `author` integer (required, null, read-only); `author_name` string (required, read-only); `automatic` boolean (required, read-only); `body` string (required, read-only); `sent_at` date-time (required, read-only); `mentions` [integer] (required, read-only); `attachments` [Attachment] (required, read-only); `other_sender` boolean (required, read-only); `dropped` [string] (required, read-only)
- **MessageCreateDirectionEnum**: one of `out`, `note`
- **MessageCreateRequest**: `direction` MessageCreateDirectionEnum (required); `body` string (required); `channel` any; `mentions` [integer]
- **NdrActionActionEnum**: one of `re-attempt`, `return`, `fake-attempt`
- **NdrActionRequest**: `action` NdrActionActionEnum (required); `comments` string (required); `deferred_date` date; `phone` string; `address1` string; `address2` string
- **Note**: `id` integer (required, read-only); `target_type` string (required); `target_id` string (required); `author` integer (required, read-only); `body` string (required); `pinned` boolean; `created` date-time (required, read-only)
- **NoteRequest**: `target_type` string (required); `target_id` string (required); `body` string (required); `pinned` boolean
- **NullEnum**: null
- **Offboarded**: `roles` [string] (required); `scopes` integer (required); `api_keys` integer (required); `change_requests` integer (required); `sessions` integer (required); `tokens` integer (required)
- **OfferStat**: `coupon` string (required, read-only); `offer` string (required, read-only); `period_start` date (required); `period_end` date (required); `orders` integer (required); `revenue` decimal (required); `discount_cost` decimal (required); `period_orders` integer (required); `baseline_orders` integer (required); `baseline_revenue` decimal (required); `interval_low` double (null); `interval_high` double (null); `note` string (required); `n` integer (required, read-only)
- **OrderActionRequest**: `order` string
- **OrderLine**: `id` integer (required); `title` string (required); `quantity` integer (required); `unit_price` string (required); `discount` string (required, null)
- **OrderPayment**: `method` string (required); `paid_with` string (required); `status` string (required); `amount` string (required); `razorpay_order_id` string (required, null); `razorpay_payment_id` string (required, null); `created` date-time (required)
- **OrderRefund**: `amount` string (required); `status` string (required); `razorpay_refund_id` string (required, null); `created` date-time (required)
- **OrderShipment**: `courier` string (required); `tracking_number` string (required); `tracking_url` string (required); `shipped_at` date-time (required); `delivered_at` date-time (required, null)
- **PaginatedApiKeyList**: `next` uri (null); `previous` uri (null); `results` [ApiKey] (required)
- **PaginatedAuditEventList**: `next` uri (null); `previous` uri (null); `results` [AuditEvent] (required)
- **PaginatedBacktestList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [Backtest] (required)
- **PaginatedChangeRequestList**: `next` uri (null); `previous` uri (null); `results` [ChangeRequest] (required)
- **PaginatedChapterStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ChapterStat] (required)
- **PaginatedCodRemittanceList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [CodRemittance] (required)
- **PaginatedCodeActivationList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [CodeActivation] (required)
- **PaginatedCohortStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [CohortStat] (required)
- **PaginatedCustomerList**: `next` uri (null); `previous` uri (null); `results` [Customer] (required)
- **PaginatedDataRequestListList**: `next` uri (null); `previous` uri (null); `results` [DataRequestList] (required)
- **PaginatedDeliveryStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [DeliveryStat] (required)
- **PaginatedErpCursorList**: `next` uri (null); `previous` uri (null); `results` [ErpCursor] (required)
- **PaginatedErpDifferenceList**: `next` uri (null); `previous` uri (null); `results` [ErpDifference] (required)
- **PaginatedErpOutboxList**: `next` uri (null); `previous` uri (null); `results` [ErpOutbox] (required)
- **PaginatedErpRunList**: `next` uri (null); `previous` uri (null); `results` [ErpRun] (required)
- **PaginatedForecastList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [Forecast] (required)
- **PaginatedFraudSignalList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [FraudSignal] (required)
- **PaginatedInboxItemList**: `next` uri (null); `previous` uri (null); `results` [InboxItem] (required)
- **PaginatedIncidentList**: `next` uri (null); `previous` uri (null); `results` [Incident] (required)
- **PaginatedItemStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ItemStat] (required)
- **PaginatedJobList**: `next` uri (null); `previous` uri (null); `results` [Job] (required)
- **PaginatedOfferStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [OfferStat] (required)
- **PaginatedParcelList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [Parcel] (required)
- **PaginatedPersonList**: `next` uri (null); `previous` uri (null); `results` [Person] (required)
- **PaginatedPickupLocationList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [PickupLocation] (required)
- **PaginatedPrintRunAdviceList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [PrintRunAdvice] (required)
- **PaginatedProcessorList**: `next` uri (null); `previous` uri (null); `results` [Processor] (required)
- **PaginatedSavedReplyList**: `next` uri (null); `previous` uri (null); `results` [SavedReply] (required)
- **PaginatedSavedViewList**: `next` uri (null); `previous` uri (null); `results` [SavedView] (required)
- **PaginatedShipmentChargeList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ShipmentCharge] (required)
- **PaginatedShippingExceptionList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ShippingException] (required)
- **PaginatedStaffInviteList**: `next` uri (null); `previous` uri (null); `results` [StaffInvite] (required)
- **PaginatedTicketList**: `next` uri (null); `previous` uri (null); `results` [Ticket] (required)
- **Parcel**: `id` integer (required, read-only); `order` string (required, read-only); `courier` CourierEnum (required, read-only); `tracking_number` string (required, read-only); `tracking_url` uri (required, read-only); `shipped_at` date-time (required, read-only); `delivered_at` date-time (required, null, read-only); `detail` ParcelDetail (required, null, read-only)
- **ParcelDetail**: `carrier` CarrierEnum (required, read-only); `account` integer (required, null, read-only); `status` any (required, null, read-only); `reference` string (required, read-only); `external_order_id` string (required, read-only); `external_shipment_id` string (required, read-only); `courier_company_id` integer (required, null, read-only); `courier_name` string (required, read-only); `weight_g` integer (required, null, read-only); `length_cm` integer (required, null, read-only); `breadth_cm` integer (required, null, read-only); `height_cm` integer (required, null, read-only); `charged_weight_g` integer (required, null, read-only); `quoted_rate` decimal (required, null, read-only); `cod_amount` decimal (required, null, read-only); `declared_value` decimal (required, null, read-only); `last_event_at` date-time (required, null, read-only); `pickup_location` integer (required, null, read-only); `pickup_date` date (required, null, read-only); `manifested_at` date-time (required, null, read-only); `has_label` boolean (required, read-only); `has_photo` boolean (required, read-only)
- **ParcelHistory**: `id` integer (required, read-only); `order` string (required, read-only); `courier` CourierEnum (required, read-only); `tracking_number` string (required, read-only); `tracking_url` uri (required, read-only); `shipped_at` date-time (required, read-only); `delivered_at` date-time (required, null, read-only); `detail` ParcelDetail (required, null, read-only); `events` [ShipmentEvent] (required, read-only); `exceptions` [ShippingException] (required, read-only); `charges` [ShipmentCharge] (required, read-only); `cod_remittance` CodRemittance (required, null, read-only)
- **ParcelStatusEnum**: one of `booked`, `pickup_problem`, `in_transit`, `out_for_delivery`, `delivered`, `delivery_failed`, `returning`, `returned`, `lost_or_damaged`, `cancelled`, `partial`
- **PastTicket**: `number` string (required); `subject` string (required); `category` string (required); `status` string (required); `received_at` date-time (required)
- **PatchedDataRequestRequest**: `kind` DataRequestKindEnum; `channel` ChannelEnum; `user` integer (null); `requester` string; `summary` string; `received_at` date-time; `assignee` integer (null); `notes` string; `details` any
- **PatchedIncidentRequest**: `title` string; `kind` IncidentKindEnum; `detected_at` date-time; `description` string; `systems` string; `data_categories` string; `people_affected` integer (null); `children_affected` boolean; `cert_in_reported_at` date-time (null); `cert_in_reference` string; `board_notified_at` date-time (null); `board_report_at` date-time (null); `board_reference` string; `notice_text` string; `notices_sent` integer; `notices_sent_at` date-time (null); `actions` string; `root_cause` string
- **PatchedPickupLocationRequest**: `nickname` string; `address` string; `city` string; `state` string; `pin_code` string; `phone` string; `is_default` boolean; `active` boolean
- **PatchedProcessorRequest**: `name` string; `purpose` string; `data_categories` string; `country` string; `contract_signed_on` date (null); `contract_ends_on` date (null); `active` boolean; `notes` string
- **PatchedSavedReplyRequest**: `title` string; `language` TicketLanguageEnum; `body` string
- **PatchedSavedViewRequest**: `role` string; `list_key` string; `name` string; `filters` any; `columns` any; `sort` any
- **PatchedTicketChangeRequest**: `category` any; `priority` TicketPriorityEnum; `language` TicketLanguageEnum; `source` TicketSourceEnum; `nch_docket` string; `subject` string; `name` string; `email` any; `phone` string; `order` string; `record` string
- **Person**: `id` integer (required, read-only); `email` email (required); `full_name` string (required); `is_active` boolean; `is_superuser` boolean; `roles` [string] (required, read-only); `grants` [object] (required, read-only); `scopes` [Scope] (required, read-only); `mfa` boolean (required, read-only); `last_login` date-time (null); `created` date-time (required, read-only)
- **PhotoRequest**: `photo` binary (required)
- **PickupLocation**: `id` integer (required, read-only); `nickname` string (required); `address` string; `city` string; `state` string; `pin_code` string (required); `phone` string; `is_default` boolean; `active` boolean; `external_id` string (required, read-only)
- **PickupLocationRequest**: `nickname` string (required); `address` string; `city` string; `state` string; `pin_code` string (required); `phone` string; `is_default` boolean; `active` boolean
- **PickupRequestRequest**: `date` date
- **PickupResult**: `pickup_date` date (required, null)
- **PolicyAcknowledgement**: `id` integer (required, read-only); `user` integer (required, read-only); `policy` string (required); `version` string (required); `acknowledged_at` date-time (required, read-only)
- **PolicyAcknowledgementRequest**: `policy` string (required); `version` string (required)
- **PostalPrice**: `service` string (required); `label` string (required); `price` decimal (required)
- **PrintRunAdvice**: `product` string (required, read-only); `title` string (required, read-only); `net_price` decimal (required); `unit_cost` decimal (required); `salvage` decimal (required); `critical_ratio` double (required); `target_quantity` integer (required); `supply` integer (required); `recommended_quantity` integer (required); `reprint_trigger_units` integer (required); `weeks_of_cover` double (null); `projected_leftover` integer (required); `level` LevelEnum; `alert` string; `n` integer (required, read-only)
- **Processor**: `id` integer (required, read-only); `name` string (required); `purpose` string (required); `data_categories` string (required); `country` string (required); `contract_signed_on` date (null); `contract_ends_on` date (null); `active` boolean; `notes` string
- **ProcessorRequest**: `name` string (required); `purpose` string (required); `data_categories` string (required); `country` string (required); `contract_signed_on` date (null); `contract_ends_on` date (null); `active` boolean; `notes` string
- **Quote**: `courier_company_id` integer (required); `courier_name` string (required); `rate` decimal (required); `etd_days` integer (required, null); `rating` double (required, null); `cod` boolean (required); `cod_charges` decimal (required); `rto_charges` decimal (required); `recommended` boolean (required)
- **QuoteResult**: `couriers` [Quote] (required); `india_post` [PostalPrice] (required); `weight_g` integer (required); `stale` boolean (required); `error` string (required)
- **ReasonRequest**: `reason` string (required)
- **ReconcileRequest**: `order` string (required)
- **Reconciled**: `order` string (required); `paid` boolean (required, null)
- **RefundLineRequest**: `item` integer (required); `quantity` integer (required)
- **RefundRequest**: `order` string; `amount` decimal (null); `lines` [RefundLineRequest]; `reason` string (required)
- **Requester**: `name` string (required); `email` string (required); `phone` string (required); `user` integer (required, null)
- **ResolveRequest**: `resolution` string (required); `dismiss` boolean
- **ResponseText**: `subject` string (required); `body` string (required)
- **RevealRequest**: `show` [ShowEnum] (required); `reason` string (required)
- **Revealed**: `email` string (null); `phone` string (null); `login_phone` string (null); `parent_contact` string (null); `parent_name` string (null); `date_of_birth` string (null)
- **RoleEnum**: one of `ADMIN`, `AUDITOR`, `CONTENT_EDITOR`, `FINANCE`, `MARKETING`, `OWNER`, `PACKER`, `REVIEWER`, `SALES`, `SALES_REP`, `SUPPORT`
- **SavedReply**: `id` integer (required, read-only); `title` string (required); `language` TicketLanguageEnum; `body` string (required); `variables` [string] (required, read-only); `created_by` integer (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `deleted_at` date-time (required, null, read-only)
- **SavedReplyRequest**: `title` string (required); `language` TicketLanguageEnum; `body` string (required)
- **SavedReplyText**: `id` integer (required); `title` string (required); `language` string (required); `text` string (required)
- **SavedView**: `id` integer (required, read-only); `owner` integer (required, read-only); `role` string; `list_key` string (required); `name` string (required); `filters` any; `columns` any; `sort` any; `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **SavedViewRequest**: `role` string; `list_key` string (required); `name` string (required); `filters` any; `columns` any; `sort` any
- **Scope**: `id` integer (required, read-only); `kind` ScopeKindEnum (required); `value` string (required); `granted_by` integer (required, null, read-only); `created` date-time (required, read-only); `expires_at` date-time (null)
- **ScopeAddRequest**: `kind` ScopeKindEnum (required); `value` string (required); `expires_at` date-time (null)
- **ScopeKindEnum**: one of `subject`, `board_class`, `order_status`, `warehouse`, `school`, `ticket_queue`, `ticket_category`
- **SessionsEnded**: `sessions` integer (required); `tokens` integer (required)
- **Setting**: `key` string (required); `label` string (required); `kind` any (required); `permission` string (required); `value` any (required); `environment` any (required); `source` SettingSourceEnum (required); `effective_from` date-time (required, null); `changed_by` integer (required, null); `reason` string (required); `scheduled` [object] (required)
- **SettingSourceEnum**: one of `environment`, `database`
- **ShipmentCharge**: `id` integer (required, read-only); `shipment` integer (required, null, read-only); `kind` ShipmentChargeKindEnum (required, read-only); `amount` decimal (required, read-only); `charged_weight_g` integer (required, null, read-only); `awb` string (required, read-only); `description` string (required, read-only); `statement_line_id` string (required, read-only); `charged_at` date-time (required, read-only)
- **ShipmentChargeKindEnum**: one of `freight`, `freight_reversal`, `cod`, `cod_reversal`, `rto_freight`, `rto_freight_reversal`, `excess_weight`, `excess_weight_reversal`, `other`
- **ShipmentEvent**: `source` ShipmentEventSourceEnum (required); `carrier_code` string; `carrier_label` string; `status` any (null); `occurred_at` date-time (required); `location` string; `activity` string
- **ShipmentEventSourceEnum**: one of `webhook`, `poll`, `manual`
- **ShippingException**: `id` integer (required, read-only); `kind` ShippingExceptionKindEnum (required, read-only); `shipment` integer (required, read-only); `order` string (required, read-only); `due_at` date-time (required, read-only); `state` ShippingExceptionStateEnum (required, read-only); `reference` string (required, read-only); `data` any (required, read-only); `resolution` string (required, read-only); `resolved_at` date-time (required, null, read-only); `resolved_by` integer (required, null, read-only); `created` date-time (required, read-only)
- **ShippingExceptionKindEnum**: one of `pickup_problem`, `ndr`, `rto`, `lost`, `partial`, `weight_dispute`, `cod_overdue`, `no_movement`
- **ShippingExceptionStateEnum**: one of `open`, `resolved`, `dismissed`
- **ShowEnum**: one of `email`, `phone`, `login_phone`, `parent_contact`, `parent_name`, `date_of_birth`
- **Sidebar**: `account` Customer (required, null); `orders` [SidebarOrder] (required, null); `entitlements` [EntitlementRow] (required, null); `codes` [CodeRow] (required, null); `devices` [DeviceRow] (required, null); `tickets` [PastTicket] (required, null); `consents` [ConsentRow] (required, null)
- **SidebarOrder**: `number` string (required); `status` string (required); `status_label` string (required); `total` string (required); `payment_method` string (required); `created` date-time (required); `placed_at` date-time (required, null); `is_test` boolean (required); `refund_mode` string (required); `refund_warning` string (required); `linked` boolean (required); `payments` [OrderPayment] (required); `refunds` [OrderRefund] (required); `shipments` [OrderShipment] (required); `invoice` string (required, null); `credit_notes` [string] (required); `items` [OrderLine] (required)
- **SnoozeRequest**: `until` date-time (required)
- **StaffBreakGlass**: `reason_required` boolean (required); `reason` string (required, null); `ends_at` date-time (required)
- **StaffCatalogue**: `permissions` [object] (required); `roles` [object] (required)
- **StaffImpersonating**: `user_id` integer (required); `email` string (required); `until` date-time (required)
- **StaffInvite**: `id` integer (required, read-only); `email` string (required, read-only); `role` string (required); `invited_by` integer (null); `created` date-time; `expires_at` date-time (required); `accepted_at` date-time (null); `accepted_by` integer (null); `revoked_at` date-time (null)
- **StaffManifest**: `break_glass` StaffBreakGlass (required, null); `user` StaffUser (required); `roles` [object] (required); `permissions` [string] (required); `scopes` object (required); `role_scopes` object (required); `limits` object (required); `flags` object (required); `policies_due` [object] (required); `reauth_valid_until` date-time (required, null); `idle_timeout_s` integer (required); `absolute_expires_at` date-time (required); `impersonating` StaffImpersonating (required, null); `manifest_version` string (required)
- **StaffSystem**: `health` any (required); `celery` any (required); `webhooks` any (required); `email` any (required); `sms` any (required); `backups` any (required); `maintenance` any (required); `audit` any (required)
- **StaffUser**: `id` integer (required); `email` email (required); `full_name` string (required); `is_superuser` boolean (required)
- **StatusRequest**: `status` TicketStatusEnum (required); `resolution` string; `order` string; `record` string
- **SupportSummary**: `since` date (required); `until` date (required); `received` integer (required); `by_category` object (required); `by_source` object (required); `first_response_hours` double (required, null); `resolution_hours` double (required, null); `backlog` object (required); `overdue` integer (required); `breaches` object (required)
- **SwitchChangeRequest**: `value` any (required, null); `reason` string (required); `effective_from` date-time
- **SwitchRow**: `key` string (required); `value` any (required); `effective_from` date-time (required); `changed_by` integer (required, null); `reason` string (required); `created` date-time (required)
- **Ticket**: `id` integer (required, read-only); `number` string (required, read-only); `subject` string (required, read-only); `source` TicketSourceEnum (required, read-only); `nch_docket` string (required, read-only); `category` any (required, read-only); `priority` TicketPriorityEnum (required, read-only); `status` TicketStatusEnum (required, read-only); `language` TicketLanguageEnum (required, read-only); `requester` Requester (required, read-only); `assignee` integer (required, null, read-only); `order` string (required, null, read-only); `received_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `first_response_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `closed_at` date-time (required, null, read-only); `ack_due_at` date-time (required, read-only); `due_at` date-time (required, read-only); `next_due_at` date-time (required, read-only); `ack_breached` boolean (required, read-only); `due_breached` boolean (required, read-only); `overdue` boolean (required, read-only); `clock` string (required, null, read-only); `is_test` boolean (required, read-only); `reopened_count` integer (required, read-only); `message_count` integer (required, read-only); `last_message_at` date-time (required, null, read-only)
- **TicketAssignRequest**: `assignee` integer (required, null)
- **TicketCategoryEnum**: one of `order`, `payment`, `book_code`, `qr_solutions`, `content_error`, `school_order`, `privacy_request`, `grievance`
- **TicketChannelEnum**: one of `web`, `email`, `phone`, `whatsapp`, `sms`, `nch`, `panel`
- **TicketCreateRequest**: `source` TicketLoggedSourceEnum (required); `nch_docket` string; `name` string; `email` any; `phone` string; `category` any; `priority` TicketPriorityEnum; `subject` string (required); `message` string (required); `received_at` date-time; `order` string
- **TicketDetail**: `id` integer (required, read-only); `number` string (required, read-only); `subject` string (required, read-only); `source` TicketSourceEnum (required, read-only); `nch_docket` string (required, read-only); `category` any (required, read-only); `priority` TicketPriorityEnum (required, read-only); `status` TicketStatusEnum (required, read-only); `language` TicketLanguageEnum (required, read-only); `requester` Requester (required, read-only); `assignee` integer (required, null, read-only); `order` string (required, null, read-only); `received_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `first_response_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `closed_at` date-time (required, null, read-only); `ack_due_at` date-time (required, read-only); `due_at` date-time (required, read-only); `next_due_at` date-time (required, read-only); `ack_breached` boolean (required, read-only); `due_breached` boolean (required, read-only); `overdue` boolean (required, read-only); `clock` string (required, null, read-only); `is_test` boolean (required, read-only); `reopened_count` integer (required, read-only); `message_count` integer (required, read-only); `last_message_at` date-time (required, null, read-only); `data_request` integer (required, null, read-only); `record` string (required, null, read-only); `resolution` string (required, read-only); `complaint_copy_sent_at` date-time (required, null, read-only); `ack_held` boolean (required, read-only); `redress_due_at` date-time (required, null, read-only); `nch_due_at` date-time (required, null, read-only); `dpdp_due_at` date-time (required, null, read-only); `it_due_at` date-time (required, null, read-only); `clocks` [Clock] (required, read-only); `closing_fields` [string] (required, read-only); `transitions` [string] (required, read-only); `messages` [Message] (required, read-only)
- **TicketDirectionEnum**: one of `in`, `out`, `note`
- **TicketLanguageEnum**: one of `as`, `bn`, `en`
- **TicketLoggedSourceEnum**: one of `phone`, `whatsapp`, `nch`, `email`
- **TicketOrderCancelled**: `order` string (required); `status` string (required)
- **TicketPriorityEnum**: one of `low`, `medium`, `high`, `urgent`
- **TicketRecord**: `id` integer (required, read-only); `number` string (required, read-only); `subject` string (required, read-only); `source` TicketSourceEnum (required, read-only); `nch_docket` string (required, read-only); `category` any (required, read-only); `priority` TicketPriorityEnum (required, read-only); `status` TicketStatusEnum (required, read-only); `language` TicketLanguageEnum (required, read-only); `requester` Requester (required, read-only); `assignee` integer (required, null, read-only); `order` string (required, null, read-only); `received_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `first_response_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `closed_at` date-time (required, null, read-only); `ack_due_at` date-time (required, read-only); `due_at` date-time (required, read-only); `next_due_at` date-time (required, read-only); `ack_breached` boolean (required, read-only); `due_breached` boolean (required, read-only); `overdue` boolean (required, read-only); `clock` string (required, null, read-only); `is_test` boolean (required, read-only); `reopened_count` integer (required, read-only); `message_count` integer (required, read-only); `last_message_at` date-time (required, null, read-only); `data_request` integer (required, null, read-only); `record` string (required, null, read-only); `resolution` string (required, read-only); `complaint_copy_sent_at` date-time (required, null, read-only); `ack_held` boolean (required, read-only); `redress_due_at` date-time (required, null, read-only); `nch_due_at` date-time (required, null, read-only); `dpdp_due_at` date-time (required, null, read-only); `it_due_at` date-time (required, null, read-only); `clocks` [Clock] (required, read-only); `closing_fields` [string] (required, read-only); `transitions` [string] (required, read-only); `messages` [Message] (required, read-only); `sidebar` Sidebar (required, read-only); `saved_replies` [SavedReplyText] (required, read-only)
- **TicketReplyChannelEnum**: one of `email`, `phone`, `whatsapp`, `nch`
- **TicketRevealFieldEnum**: one of `email`, `phone`
- **TicketRevealRequest**: `show` [TicketRevealFieldEnum] (required); `reason` string (required)
- **TicketRevealed**: `email` string (required, null); `phone` string (required, null)
- **TicketSourceEnum**: one of `form`, `email`, `phone`, `whatsapp`, `nch`
- **TicketStatusEnum**: one of `new`, `open`, `waiting_customer`, `waiting_third_party`, `resolved`, `closed`, `spam`
- **TokenRequest**: `token` string (required)
- **Unlocked**: `attempts_cleared` integer (required)
- **VerifyIdentityRequest**: `note` string (required)
<!-- /staff-api-reference -->

## Errors

DRF's standard format, always JSON:

| Status | Body |
|---|---|
| 400 | the fields' errors: `{"marks_obtained": ["Enter marks from 0 to 70."]}`; others (and the shop's rules) under `non_field_errors`; `{"detail": "Bad request."}` for a request Django refuses before the API sees it (a host name that is not served) |
| 401 | `{"detail": "Authentication credentials were not provided."}`; a bad or expired token: `{"detail": "Given token not valid for any token type", "code": "token_not_valid", "messages": [...]}` (refresh it); `"code": "password_changed"` or `"user_inactive"` (the password was changed, the account closed: log in again); a staff session ended: `"code": "session_idle"` or `"session_expired"` (log in again) |
| 403 | `{"detail": "Confirm your email address first."}` (or another reason; `"The shop opens soon."` while the shop is closed; `"Unlock this subject with the code printed in your book."` for a locked course; `"A parent or guardian has not confirmed this account yet."` for what the course saves while `consent_pending`); `"code": "reauthentication_required"` (re-authenticate, then send it again), `"mfa_setup_required"` (staff: set up a second factor), `"impersonating"` (a payment, password or account change while staff are logged in as the customer) |
| 404 | `{"detail": "No Paper matches the given query."}`, `{"detail": "Not found."}` (also anything under `staff/` on a host other than the admin host) |
| 405, 406, 415 | `{"detail": "..."}` |
| 413 | `{"detail": "The request body is too large."}` (over 1 MB, `DATA_UPLOAD_MAX_MEMORY_SIZE`) |
| 429 | `{"detail": "..."}`: DRF's limits say "Request was throttled. Expected available in 38 seconds." and carry a `Retry-After` header; allauth's (codes, password reset, wrong passwords) have their own text and no `Retry-After`; allauth.headless answers `{"status": 429}` |
| 500 | `{"detail": "Server error."}`; reported to Sentry, with the request ID in `X-Request-ID` (the site's own pages show an error page) |
| 503 | `{"detail": "The payment service could not be reached."}` (or "Online payment is not set up yet."), from `orders/<number>/payment/`: try again; `{"detail": "The courier could not be reached: try again in a few minutes."}` from `shipping/` (staff) |

## Rate limits

Counted in the cache (Redis in production), per client address for anonymous requests and per user once signed in:

| Scope | Default | Setting |
|---|---|---|
| anonymous | 200 a minute | `API_THROTTLE_ANON` |
| signed in | 600 a minute | `API_THROTTLE_USER` |
| log-in, log-out, sign-up, codes (`verify-email`, `phone/code`, `phone/confirm`), passwords, data export and its summary, deletion | 30 a minute | `API_THROTTLE_AUTH` |
| guests' order lookup (`orders/lookup/`), per client address | 10 an hour | `API_THROTTLE_ORDER_LOOKUP` |
| starting and confirming payments (`orders/<number>/payment/…`, `orders/t/<token>/payment/…`) | 30 a minute | `API_THROTTLE_PAYMENT` |
| coupon codes tried (`POST cart/coupon/`), per user (a visitor: per client address) | 10 an hour | `API_THROTTLE_COUPON` |
| book codes tried (`POST learn/redeem/`), per user (`learn_redeem`) and per client address (`learn_redeem_address`) | 5 an hour each | `API_THROTTLE_LEARN_REDEEM`, `API_THROTTLE_LEARN_REDEEM_ADDRESS` |
| quiz answers (`POST learn/quiz/<id>/attempt/`), per user (`learn_quiz`) | 600 an hour | `API_THROTTLE_LEARN_QUIZ` |
| guests' order lookup, per email address and per order number (any address) | 10 an hour | fixed |
| checkout (`POST orders/`, accounts' and visitors'), per client address, the website's included | 10 in 10 minutes | fixed |
| a visitor's coupon codes (`POST cart/coupon/`), per client address, the website's cart page included | 10 an hour | fixed |
| reviews (`POST products/<slug>/reviews/`), per client address, the website's included | 5 an hour | fixed |
| back-in-stock alerts (`POST products/<slug>/stock-alert/`), per client address, the website's included | 10 an hour | fixed |
| quotation requests (`POST quotes/`), per client address, the website's included | 5 an hour | fixed |
| the couriers' webhook (`POST /api/hooks/parcel-events/`), per client address | 300 a minute | `API_THROTTLE_PARCEL_EVENTS` |
| the support mailbox's hook (`POST /api/hooks/support-mail/`), per client address | 120 a minute | `API_THROTTLE_SUPPORT_MAIL` |
| new requests from My requests (`POST me/tickets/`), per account | 10 an hour | `API_THROTTLE_SUPPORT_REQUEST` |
| the staff API (`staff/…`), per member of staff or API key | 600 a minute | `STAFF_THROTTLE` |
| customer searches (`GET staff/users/`), the support queue and its book-code lookups | 60 a minute | `STAFF_THROTTLE_SEARCH` |
| reveals of a customer's details, and impersonation tokens (`staff/users/<id>/reveal/`, `…/impersonate/`, `staff/support/tickets/<number>/reveal/`) | 30 an hour | `STAFF_THROTTLE_REVEAL` |
| audit-log exports (`staff/audit/export/`) | 10 an hour | `STAFF_THROTTLE_EXPORT` |
| money actions and approvals (`staff/change-requests/` asked, approved, run; role grants, invitations, offboarding; a ticket's refund and cancel) | 120 an hour | `STAFF_THROTTLE_MONEY` |
| staff invitations accepted (`staff/invites/accept/`), per client address | 10 an hour | `STAFF_THROTTLE_INVITE` |
| a member of staff logged in as a customer, opened or ended (`account/impersonate/`), per client address | 20 an hour | `API_THROTTLE_IMPERSONATE` |

The rows marked "fixed" are counted by the shop itself and refuse (429) while the cache cannot be read (Redis down); the others
let requests through meanwhile. `auth/exchange/`, `me/parent-consent/` count in the log-in scope (`API_THROTTLE_AUTH`).
allauth.headless (`/_allauth/`) has allauth's limits only, the website's (`ACCOUNT_RATE_LIMITS` and the per-account
ones below): its answers over them are 429 too.

A whole classroom often shares one address: raise the limits rather than lower them (above all
`API_THROTTLE_LEARN_REDEEM_ADDRESS` before a teacher has a class redeem their codes together). django-axes still locks an
account for 15 minutes after 10 failed log-ins from one address, through the API too.

The website's limits, counted together with it:

- **log-in:** after 5 failed log-ins of one account in 5 minutes, or 10 failed log-ins in a minute from one client
  address (whatever the accounts), even the right password gets 400 "Too many failed login attempts. Try again later."
  until the window has passed;
- **password reset:** 5 emails a minute per email address and 20 requests a minute per client address
  (`auth/password/reset/` answers 429 above them);
- **codes by email** (sign-up, log-in): 3 log-in codes an hour per address and 30 an hour per client address; an address
  gets a confirmation code at most every 10 seconds, 5 an hour and 10 a day (429 above them);
- **codes by SMS** (`auth/phone/code/`): 3 an hour per number and 30 an hour per client address (429 above it); a texted
  code is tried 3 times and lasts 3 minutes. Whatever the kind, one number gets at most 5 SMS an hour and 10 a day and
  one account 20 a day, and the day's `SMS_DAILY_CAP` is shared out between log-in codes (70 %), order updates (30 %)
  and parents' links (10 %). A code over a limit is not sent: 429
  `{"detail": "Too many messages have gone to this number: try again tomorrow, or log in with your email."}`. The caps
  are counted in the database, so also while Redis is down;
- **tries of a code** (every emailed or texted code): 3 per code and 15 minutes, counted in the cache so that requests
  sent together cannot get more, and 60 an hour per client address (a classroom shares that one); over them
  `400 {"code": ["Too many tries for this code: ask for a new one."]}`;
- **passwords of a signed-in user** (`auth/password/change/`, `me/export/`, `me/deletion/`): after 5 wrong ones in an
  hour every refresh token of the user is revoked (the app must log in again once the access token expires) and these
  answer 429 until the hour is over;
- **attempts:** at most 20 new attempts of one paper a day (400 with the reason); notes at most 2,000 characters. While
  a parent's consent is awaited (`PARENTAL_CONSENT_MODE=verified`, a student under 18) no attempt can be saved (400).

## CORS

None is needed by the app, the website or a web frontend served from the site's own origin (the Next.js frontend: Caddy
in production, its proxy in development). A web client on another origin must be listed in `CORS_ALLOWED_ORIGINS`;
only `/api/` answers CORS requests, without cookies (send the access token; a visitor's cart: `X-Cart-Token`). allauth.headless's browser client is for
the site's own origin: `/_allauth/` answers no CORS request; an app client needs none (no browser).

## Versioning

The version is in the path (`/api/v1/`). Within v1, changes only add: new endpoints, new fields in answers, new
optional parameters; clients must ignore fields they do not know. Removing or renaming a field, changing a type or a
meaning, or a new required parameter makes a v2, served beside v1 until the app versions that use v1 are retired (at
least six months, announced in the app). `ALLOWED_VERSIONS` in `examleaf/api_settings.py` lists the versions served.

## Operations

- Refresh tokens and their blacklist are kept in the database; `api.tasks.flush_expired_tokens` (celery beat, 04:30; the
  entry was made by the migration `api/migrations/0001_flush_expired_tokens_daily.py` and is editable in the admin under
  Periodic tasks) deletes the expired ones.
- The tokens are signed with `JWT_SIGNING_KEY`, or `SECRET_KEY` while it is unset: rotating it logs every app out.
- There is no health endpoint under `/api/` (it was open to anyone); the uptime monitor uses `/health/`.
- Tests: `api/tests.py`, `api/test_phone.py` and `api/test_security.py` (sign-up rules, codes, tokens, gated solutions,
  attempts, data rights, query counts, limits, body size, CORS, schema validity), `shop/test_api.py` (products, cart,
  addresses, checkout, payment and a bad signature, cancellation, the PDFs, other customers' orders, cash on delivery,
  lookup and its limit), `shop/test_catalogue.py` and `shop/test_offers.py` (categories, collections, attributes and their
  filters, digital products, offers in the cart's answer), `shop/test_security.py` (order links, test and live mode,
  limits, refunds) and `learn/test_api.py` (locks and free previews, signed links, progress, quiz, cards, plan, codes
  and their limits, devices, reminders), `api/test_headless.py` (allauth.headless: codes by email and SMS to the JWT
  pair, a mobile number added with its code, the second step and staff without an authenticator, a passkey's
  challenge, Google listed only with its keys,
  sign-up with the student details, the website's links in emails), `api/test_contract.py` (config, legal pages,
  teacher access, a parent's link, SMS updates, the contact form), `shop/test_api_contract.py` (reviews, back in
  stock, quotations, the order's link, shipping) and `shop/test_api_guest.py` (a visitor's cart by session and CSRF or
  by `X-Cart-Token`, coupons, checkout, payment, cancel and PDFs by the link, the cart joining the account's at log-in). `manage.py spectacular --validate --fail-on-warn --file schema.yml` checks the schema; the
  operations are tagged by area (`api/schema.py`).
