# ExamLeaf API (v1)

The REST API behind the ExamLeaf app: the public catalogue (boards, subjects, books, papers), the solutions (for a
signed-in student with a confirmed email address, as on the website, or for everyone while the site's solutions are
open), the student's record of attempts, the account with its data rights (Download my data, Delete my account), the
shop (books, categories, collections, cart, addresses, orders, payment with Razorpay's mobile SDK, invoices) and the
revision course (chapters, clips, quiz, flash cards, a pass plan, book codes), and for staff the Admin Control Panel's
API (`/api/v1/staff/…`, on the admin host only: the [Staff API](#staff-api) and a section for each module) and the
insights (forecasts, print runs, item analysis, cohorts, fraud signals). Code: `api/` (`auth.py`, `views.py`,
`serializers.py`, `shop.py`, `learn.py`), `insights/api.py` and the staff API's, which each module keeps beside its
models (its section names the file); settings: `examleaf/api_settings.py`, URLs: `api/urls.py` under
`examleaf/api_urls.py`.

## Contents

[Conventions](#conventions) · [Endpoints](#endpoints) · [Authentication](#authentication-from-the-app) ·
[Frontend integration guide](#frontend-integration-guide) · [Profile and data rights](#profile-and-data-rights) ·
[Catalogue and solutions](#catalogue-and-solutions) · [Attempts](#attempts) · [Store catalogue](#store-catalogue) ·
[Shop](#shop) · [Revision course](#revision-course) · [Shipping (staff)](#shipping-staff) ·
[Site](#site-configuration-and-legal-pages) · [Insights (staff)](#insights-staff) ·
[ERPNext sync (staff)](#erpnext-sync-staff) · [Tax (staff)](#tax-staff) ·
[Legal and privacy (staff)](#legal-and-privacy-staff) · [Orders (staff)](#orders-staff) ·
[Connections (staff)](#connections-staff) · [Templates (staff)](#templates-staff) · [Content (staff)](#content-staff) ·
[Support (staff)](#support-staff) · [Finance (staff)](#finance-staff) ·
[Home and reports (staff)](#home-and-reports-staff) · [Catalogue (staff)](#catalogue-staff) ·
[Course (staff)](#course-staff) · [Customers (staff)](#customers-staff) · [Lists](#lists) · [Staff API](#staff-api) ·
[Errors](#errors) · [Rate limits](#rate-limits) · [CORS](#cors) · [Versioning](#versioning) ·
[Operations](#operations)

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

Paths are under `/api/v1/` except those that start with a slash. Who: **anyone** needs no sign-in; **signed in** needs a
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
| GET PUT DELETE | `me/nominee/` | signed in | the person's nominee (DPDP s.14): who acts for them after death or incapacity |
| POST | `me/consent/withdraw/` | signed in | withdraw a marketing consent (`purpose`, `channel`); its processors are told to stop |
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
| POST | `reports/` | anyone | report a mistake in a solution, a question, a quiz item or a clip ([Catalogue and solutions](#catalogue-and-solutions)) |
| GET | `errata/?book=<slug>` | anyone | a book's published errata: the mistakes confirmed or fixed, with the printings |
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
| POST | `orders/<number>/returns/` | confirmed | ask to send books back, within `SHOP_RETURN_DAYS` of delivery; also while the shop is closed |
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
| GET | `config/` | anyone | what the server has switched on: log-in methods, Turnstile, the shop, consent mode, maintenance; the e-commerce disclosures and the dark-pattern certificate |
| GET | `pages/`, `pages/<slug>/` | anyone | the legal pages: Markdown, the website's HTML, version, last change |
| GET | `pages/<slug>/versions/` | anyone | a legal page's versions: number, in force from, what changed, the one waiting for its day |
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
| POST | `/api/hooks/erp-events/` | ERPNext, with its signature in `X-Frappe-Webhook-Signature` | ERPNext's doorbell for a document that changed ([ERPNext sync (staff)](#erpnext-sync-staff)); not in the OpenAPI schema |
| POST | `/api/hooks/sms-events/` | MSG91, with the connections page's token in `X-Webhook-Token` | MSG91's delivery reports ([Connections (staff)](#connections-staff)); not in the OpenAPI schema |
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

**A child's deletion waits for the parent.** A student under 18 who asks to delete their account (`me/deletion/`) is
erased once their parent or guardian confirms: the parent gets an email with the same signed link as their consent
(`/c/<token>/`; a parent known by a mobile number alone is called by staff, who record the confirmation with its
evidence). That link's `GET parent-consent/<token>/` then carries `deletion` (`{"requested_at", "due_at",
"confirmed"}`, null otherwise), and `POST parent-consent/<token>/ {"confirm": "deletion"}` is the confirmation (once;
recorded as the parent's withdrawal in the consent ledger). Until it comes, the deletion waits past its seven days.

**My nominee** (`me/nominee/`, DPDP s.14: who acts for the person after their death or incapacity): `GET` (404 while
none), `PUT {"name", "contact", "relation"}` (`contact` an email address or an Indian mobile number, not the person's
own; 201 made, 200 changed; refused once a claim has proved it), `DELETE` (204). Staff see it with the contact masked.

**Withdrawing a marketing consent** (`POST me/consent/withdraw/ {"purpose": "marketing", "channel": "email"}`;
`channel` `email`, `sms` or `whatsapp`, empty for every one), as easily as it was given (s.6(4)): `201 {"purpose",
"channel", "withdrawn_at", "detail"}` and a line in the consent ledger; the same again answers `200` with the first
withdrawal. Each processor that holds marketing data is told to stop (a task in the panel's inbox). No account is
marketed to without a marketing consent in force, nor any under 18 whatever it says (`accounts.audiences`).

Download my data (`me/export/`, and its summary) also holds `nominee` and `recipients`: who processes the data for
ExamLeaf (the processor register's name, purpose, kinds of data and country of each, DPDP s.11(1)(b)).
`me/nominee/` and `me/consent/withdraw/` are throttled as the other data rights (`API_THROTTLE_AUTH`) and refused while
a member of staff is logged in as the customer.

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
token; 403 `{"detail": "Confirm your email address first."}` with an unconfirmed one). A question no longer in the
books repository is left out (the panel keeps it); a change made in the panel shows only once a reviewer publishes it.

**Report a mistake** `POST reports/` (anyone; a signed-in reader is kept as the reporter, a verified teacher's report
marked): `kind` is `solution` or `question` (with `paper`, its code, and `question`, its label), `quiz_item` (with
`quiz_item`, its id) or `clip` (with `clip`, its id); `category` one of `wrong_answer`, `typo`, `marks`, `unclear`,
`display`, `other`; optional `step` (a solution's marking step, 1 for the first), `printing` (the print run read: the
printed QR code's `?printing=`, letters, digits and hyphens), `note` (1,000 characters) and `email` (to be told once
when it is fixed; deleted then, or when the report is rejected). Turnstile's token (`turnstile`) while the bot check is
on, as for the contact form; at most 5 an hour and 20 a day per client address (429); a filled-in `website` (a
honeypot) is thanked and dropped; a note that reads as spam (a link, markup, one character over and over) is kept out
of the staff's queue and deleted after 30 days. **Errata** `GET errata/?book=<slug>` (anyone; `Cache-Control: public,
max-age=300`; paginated as the other lists): the mistakes staff confirmed or fixed and chose to publish, in paper and
question order, each with `paper`, `question`, `step`, `category`, `printing`, `state` (`confirmed`, `fixed_online`,
`fixed_in_printing`), `fixed_in` (the printing that carries the fix), `fixed_at` and `reported_on`.

```sh
curl -X POST https://examleaf.in/api/v1/reports/ -H "Content-Type: application/json" -d '{"kind": "solution",
  "paper": "PHY-E01", "question": "2(c)", "step": 2, "printing": "PHY-2027-1", "category": "wrong_answer",
  "note": "The current should be 0.5 A, not 5 A.", "turnstile": "0.Zx..."}'
# 201 {"reference": 31, "detail": "Thank you: we will check it, and fix it if it is wrong."}
# 400 {"question": ["No such question on that paper."]}      429 above 5 an hour or 20 a day
```

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
  title; null until the worker has made it). `prior_price` (from `SHOP_PRIOR_PRICE_FROM`, 1 January 2027: the lowest selling
  price of the 30 days before the current price was set, when the current one is lower; null otherwise, the
  website's "Lowest price in the 30 days before this reduction"). The old slug of a renamed product answers `301` with `Location:
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
Offers apply by themselves, after the coupon (no code to type), as soon as they apply. A coupon may cover some
products or categories only (its minimum order reckoned on them), be for a first order, or not stack (then no offer
beside it); a school's single-use code (`CCHS-7KQ2MZRX`) is typed as a coupon's code is, `coupon` then the code
typed, and the order made with it takes it (a second order with it: 400 "This code has been used."; a cancelled
order frees it).

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
to pack or ship, delivered once paid), `has_shipping` (books to deliver, so the address, `shipping_fee` and
`shipments` concern it: always the opposite of `is_digital`), `returns` (each `number`, `status`, `status_label` as
the website words it, `reason`, `created`, `lines` with `product`, `title` and `quantity`, `decision_note`,
`return_courier` and `return_awb`), `can_return` and `return_until` (the last moment to ask; null until delivered). The list (`orders/`, newest first, `?status=`) gives only
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

**Return**: `POST orders/<number>/returns/` `{"lines": [{"product": "physics-sample-papers", "quantity": 1}],
"reason": "damaged", "note": "The cover was torn."}` while `can_return` (delivered, within `SHOP_RETURN_DAYS`, 15 by
default, of its delivery, and no return of it under way): `product` as the order's `items` name it, `reason` one of
`damaged`, `misprint`, `wrong_item`, `late`, `not_as_described`, `other`. `201` with the order, its `returns` listing the new
one (`requested`); staff answer within two working days by email, and the order's `returns` follow it (approved, the
courier and AWB to send it with, received, refunded). 400 with the reason otherwise: not delivered yet, after the
window, more copies than were bought or than are left to send back. Only the signed-in owner of the order sees
`can_return` true; a guest's order link shows the state, and a guest asks by email.

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

`disclosures` are the e-commerce disclosures the E-Commerce Rules (r.4) ask the site to show, as the panel keeps them
(Legal and privacy, Disclosures): `legal_name`, `registered_address`, `operating_address`, `care_phone`, `care_email`,
`care_hours`, `grievance_officer`, `grievance_designation`, `grievance_contact`, `nodal_contact` (resident in India),
`returns_page` (the slug of the return and refund terms' page), `dpdp_contact` (who answers questions about personal
data), `rights_text` (how to make a request about one's data), `nch_status` (`not_joined`, `applied`, `member`) and
`nch_since`; each null while not set yet (or still a `[placeholder]`). CERT-In's point of contact is never here. The
footer shows the legal name and the Grievance Officer, the contact page all of them. `dark_pattern_certificate` is the
dark-pattern self-audit's certificate in force (`{"year", "text", "effective_from"}`, from its day on), to display
prominently; null until one is.

`pages/` and `pages/<slug>/` (anyone; cached 15 minutes) are the legal and policy pages, `privacy`, `terms`, `refunds`,
`shipping` and `contact`: `slug`, `title`, `version` (consent records keep the privacy notice's), `updated` (the last
change, as in the page's history), `markdown`, `html` (the website's rendering; a `[placeholder]` still to fill in is
marked `<mark class="placeholder">`) and `web_url`; `number` (the version in force, counted: "Version 2"),
`effective_from` (in force from that day) and `summary` (what it changed). `pages/<slug>/versions/` (anyone; cacheable
15 minutes) lists every version newest first, `[{"number", "version", "effective_from", "summary", "in_force",
"upcoming"}]`: one published for a later day comes first, `upcoming`, and is in force from its day.

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

## Tax (staff)

`/api/v1/staff/tax/…` (code: `shop/staff_tax.py`; the rules: `shop/tax.py`, [shop/README.md](shop/README.md) "Tax") is
the panel's tax desk: the HSN and SAC master with its dated rates, the products that disagree with it, the
storefront's invoices and credit notes, Table 13, the threshold monitor's card, the tax calendar and the GSTR-1 job.
It is part of the [Staff API](#staff-api) and keeps all its rules: the admin host only, a member of staff with a
second factor (or an API key with the `view_` permissions), each action's catalogued permission (area "Tax"), every
refusal an `authz_fail` event, cursor pages, `Cache-Control: no-store`. FINANCE and the owners write; AUDITOR reads.
Each change is an audit event: `tax.code_added`, `tax.rate_added`, `tax.document_cancelled` (with the reason),
`tax.gstr1_exported` (counts only); opening a document's PDF, which names the buyer, is a `sensitive_read`. A
document's address is its number with dashes for its slashes (`EL-2026-27-00001`). Money is in rupees as decimal
strings; a refusal is `400 {"field": ["…"]}` or `{"non_field_errors": ["…"]}`.

| Method | Path (under `/api/v1/staff/tax/`) | Permission | What |
|---|---|---|---|
| GET | `hsn/` (`?kind=hsn\|sac&taxability=&q=`), `hsn/<code>/` | `shop.view_hsncode` | the master by code: `today` (the rate, taxability, from and notification in force today; null when none), `next_change` (a rate set to start later), `products`; one code adds `rates` (its history oldest first, each with `until`: its own end or the day before the next) and `linked` (its products, each with its `problem`) |
| POST | `hsn/` `{"code", "kind", "description", "uqc", "first_rate": {…}}` | `shop.change_hsncode` | a code new to the master with its first rate: 201 the code; a SAC code begins with 99, an HSN code never does |
| POST | `hsn/<code>/rates/` `{"rate", "taxability", "effective_from", "effective_to", "notification", "serial", "note"}` | `shop.change_hsncode` | a new dated rate: after the code's latest start (`400 {"effective_from": [...]}` otherwise: the history is never rewritten); a taxable rate above 0, the others at 0 |
| GET | `problems/` (`?all=true`: off-sale products too) | `shop.view_hsncode` | the products whose GST disagrees with the master today, with why (not on the master, no rate that day, another rate, a course with a goods code, too few HSN digits; a bundle's component, or its treatment's rate): the catalogue's red chip |
| GET | `documents/` (`?kind=invoice\|credit_note&series=&document_type=&month=YYYY-MM&financial_year=&cancelled=&test=&search=`) | `shop.view_documentseries` | invoices (by default) or credit notes, newest first: `key`, `number`, `series`, `financial_year`, `serial`, `document_type`, `date`, `order`, `against` (a note's invoice), `place_of_supply`, `total`, `taxable_value`, `exempt_value`, `tax_amount`, `cancelled_at`, `cancel_reason`, `has_pdf`; the test series only with `?test=true` |
| GET | `documents/<number>/`, `documents/<number>/pdf/` | `shop.view_documentseries` | one with its `title`, `lines` (code, rate, amount, taxable value, tax; a split bundle's components with its title), `charges` (the shipping by rate), `round_off`, `checks` (what Rule 46 asks that it misses) and `credit_notes`; its PDF as issued (audited) |
| POST | `documents/<number>/cancel/` `{"reason"}` | `staff.cancel_document` (high: a re-authentication within 5 minutes) | it keeps its number and leaves the returns, its PDF made again marked cancelled; an invoice's credit notes are cancelled first; the order and its refunds are left as they are |
| GET | `series/` (`?financial_year=2026-27&month=YYYY-MM`) | `shop.view_documentseries` | Table 13: each real series of the year (or month): `nature`, `first` and `last` number, `total`, `cancelled`, `next_number`; with `series_from` and `prefixes` (the settings) |
| GET | `thresholds/` | `shop.view_taxthreshold` | the card: the latest night's lines (`value`, `limit`, `crossed`; `count` for the documents' lines), `previous_turnover`, `qrmp`, `hsn_digits`, `basis` |
| GET | `calendar/` (`?month=YYYY-MM`) | `shop.view_taxthreshold` | the month's due dates (`key`, `title`, `covers`, `due`, `applies`, `note`, `past`) and the lines crossed this year |
| POST | `gstr1/` `{"month": "YYYY-MM", "months": 1\|3, "dry_run": false}` | `staff.run_gstr1` | the GSTR-1 export as a job: 202 the job (`jobs/<id>/`); its file, the Offline Tool's CSVs zipped, through its `result_url`; above the starter's `export_rows` it waits for ADMIN first (`change_request_id`). The same job is `POST jobs/` `{"kind": "gstr1_export", "params": {...}}` |

```sh
curl https://admin.examleaf.in/api/v1/staff/tax/hsn/4820/ -b "sessionid=..."
# 200 {"code": "4820", "kind": "hsn", "description": "Exercise books, graph books, laboratory notebooks and notebooks",
#      "uqc": "NOS", "today": {"rate": "0.00", "taxability": "exempt", "effective_from": "2025-09-22",
#      "notification": "10/2025-Central Tax (Rate)"}, "next_change": null, "products": 0,
#      "rates": [{"rate": "12.00", "effective_from": "2017-07-01", "until": "2025-09-21", ...},
#                {"rate": "0.00", "taxability": "exempt", "effective_from": "2025-09-22", "until": null,
#                 "notification": "10/2025-Central Tax (Rate)", "serial": "130", ...}], "linked": []}
curl -X POST https://admin.examleaf.in/api/v1/staff/tax/documents/EL-2026-27-00042/cancel/ -b "sessionid=...; csrftoken=..." \
  -H "X-CSRFToken: ..." -H "Content-Type: application/json" -d '{"reason": "Issued twice for one parcel."}'
# 200 {"key": "EL-2026-27-00042", "number": "EL/2026-27/00042", "cancelled_at": "2026-10-09T15:02:11+05:30", ...}
```

The checkout (`POST /api/v1/orders/`, [Shop](#shop)) takes an optional `billing_state` (a state code) for a cart of
courses alone: the place of supply on its invoice (else the address's state, else Assam); a cart with books refuses a
state other than its delivery address's (`400 {"non_field_errors": ["Books are taxed in the state they are delivered
to: …"]}`).

## Legal and privacy (staff)

`/api/v1/staff/privacy/…` (code: `staff/privacy_api.py`; the duties behind it: `staff/README.md` "Legal and
privacy") is the panel's Legal and privacy module beside the data requests, incidents and processors of the
[Staff API](#staff-api), on all its rules: the admin host only, a member of staff with a second factor (or an API key
for the reads), each action's catalogued permission (area "Privacy"), a re-authentication for the high ones
(`staff.manage_holds`, `staff.manage_compliance`, `staff.manage_settings`, `staff.reveal_contact`), every refusal an
`authz_fail`, `Cache-Control: no-store`, cursor pages newest first. Every change is an audit event, and none names a
person: accounts by their number, orders by theirs.

| Method | Path (under `/api/v1/staff/`) | Permission | What |
|---|---|---|---|
| GET | `privacy/cockpit/` | `staff.view_datarequest` | every clock the rules start, as `clocks` rows, the overdue first: a data request's 48 hours and its month (90 days for the DPDP rights from 13 May 2027), a breach's 6 hours (CERT-In) and 72 hours (the Board), a complaint's 48 hours, month and NCH 30 days (from the support app's tickets when it is installed: `support`), the parents' consents awaited, a child's deletion waiting for the parent, the year's dark-pattern self-audit; each with `rule`, `due_at`, `overdue` and the record behind it (`target_type`, `target_id`, `account`); `counts` of each kind; `consents` by the privacy notice's version; `dark_pattern`; `calendar` (1 January and 13 May 2027, the self-audit, the quarterly access review and restore drill); `inbox` (the processors' tasks open) |
| GET | `privacy/retention/` | `staff.view_datarequest` | the retention schedule (`examleaf/retention.py`): each kind of record's `minimum` today, `changes_on` and `next_minimum`, its `source`, what is kept (`keep`, `keep_days`, `trim_days`) and `enforced_by` |
| GET POST | `privacy/holds/` (`?active=&reason=&user=&target_type=`), `privacy/holds/<id>/` | `accounts.view_legalhold`; `staff.manage_holds` to put one | a legal hold on an account (`user`) or one record (`target_type` `shop.order`, `shop.invoice`, `shop.creditnote`, `shop.payment`, `shop.refund` or `staff.datarequest`, `target_id` its number or id), `reason` (`dispute`, `chargeback`, `claim`, `investigation`, `other`), `note`, `until` (today or later; none: until released); the answer's `target_label` names it by number |
| POST | `privacy/holds/<id>/release/` (`reason`) | `staff.manage_holds` | released, with why; `400` the second time |
| GET | `privacy/nominees/<user>/` | `accounts.view_user` | the customer's nominee (`null` while none), its `contact` masked; a `sensitive_read` event |
| POST | `privacy/nominees/<user>/reveal/` (`reason`) | `staff.reveal_contact` | the nominee's contact, with a reason (30 an hour, `staff_reveal`) |
| POST | `privacy/deletions/<id>/parent-confirmation/` (`evidence_ref`) | `staff.handle_data_request` | a child's deletion confirmed by the parent by phone or letter: recorded with where the evidence is (never the document); `400` for an adult's, a deletion not waiting, or one confirmed already |
| GET | `privacy/policies/`, `privacy/policies/<slug>/` | `pages.view_page` | the legal pages: the version in force (`number`, `version`, `effective_from`, `summary`), the one `scheduled` for a later day, `placeholders` left; one page adds its `markdown` and every version |
| GET | `privacy/policies/<slug>/versions/<number>/diff/` | `pages.view_page` | a version against the one before it: `lines` of a unified diff (`hunk`, `added`, `removed`, `context`), `added` and `removed` counts, `title_changed` |
| POST | `privacy/policies/<slug>/publish/` (`markdown`, `summary`, `title`, `effective_from`) | `pages.change_page` | a new version, numbered: in force today (at once) or from a later day (`scheduled`, in force that night just after midnight); never backdated; `400` for the text in force |
| POST | `privacy/policies/<slug>/cancel-scheduled/` (`reason`) | `pages.change_page` | the version waiting for its day withdrawn |
| GET PUT | `privacy/disclosures/` (PUT `values` `{KEY: value}`, `reason`) | `staff.view_sitesetting`; `staff.manage_settings` | the disclosures, the site settings of the group `disclosures` (each with `value`, `environment`, `source`, `public`, `max_length`) and their `history`; PUT saves the changed ones together with one reason (each a `setting.changed` event; `null` back to settings.py's), `400` field by field, or `Nothing changed.` |
| GET POST PATCH | `privacy/dark-pattern-audits/`, `privacy/dark-pattern-audits/<id>/` | `staff.view_darkpatternaudit`; `staff.manage_compliance` | the yearly self-audit: `year`, `rows` (the 13 patterns, each `{pattern, label, finding, fix}`), `certificate_text`, `effective_from`; one a year; a completed one is not changed (`400`) |
| POST | `privacy/dark-pattern-audits/<id>/complete/` (`effective_from`) | `staff.manage_compliance` | completed once every row has its finding and fix and the certificate its text: shown on the website (`config/`'s `dark_pattern_certificate`) from `effective_from` (today by default); the year's inbox reminder closes |
| GET POST | `privacy/dark-pattern-audits/<id>/file/` (POST multipart `file`: PDF, PNG or JPEG, 5 MB at most) | `staff.view_darkpatternaudit`; `staff.manage_compliance` | the signed certificate, kept in the private storage |

The erasure's dry run (`data-requests/<id>/erasure-report/`) gives each kept row a `kind` (`books`, `processing_logs`,
`legal_hold`, `intermediary`, `consent`, `statistics`, `by_hand`, `test`) and its `line` in words: "kept until 31 March
2035: 1 invoice of 2026-27 with the order behind it, for GST and the Companies Act (8 financial years, or 72 months after
the year's annual return)". A legal hold on the account or a child's deletion without the parent's confirmation is in
`blocks`, and the erasure waits for it (the nightly purge too). The processor register's rows say whether the processor
keeps personal data (`holds_personal_data`), holds marketing lists (`holds_marketing_data`) and what to ask of it
(`erasure_action`): an erasure done, or a marketing consent withdrawn, opens a task in the inbox for each.

```sh
curl https://admin.examleaf.in/api/v1/staff/privacy/holds/ -b "sessionid=…; csrftoken=…" -H "X-CSRFToken: …" \
  -H "Content-Type: application/json" -d '{"target_type": "shop.order", "target_id": "EL-2026-000123", "reason": "chargeback"}'
# 201 {"id": 7, "user": null, "target_type": "shop.order", "target_id": "41", "target_label": "Order EL-2026-000123",
#      "reason": "chargeback", "note": "", "until": null, "active": true, "created": "…", "created_by": 3, …}
```

## Orders (staff)

`/api/v1/staff/orders/…` (code: `shop/staff_orders.py`, the jobs `shop/order_jobs.py`; the module:
[shop/README.md](shop/README.md)) is the panel's Orders module, on the [Staff API](#staff-api)'s rules: the admin host
only, a member of staff with a second factor (or an API key with `shop.view_order`), each action its permission
(`shop.view_order` to read; `shop.add_order` for a staff order; `shop.change_order` to cancel, hold, release, tag,
message again, send or cancel a payment link and make or resend the invoice; `staff.pack_order` to pack, send by
hand, deliver and print; `staff.refund_order`; `staff.record_offline_payment`; `staff.handle_return` to ask for,
approve or decline a return and send its label; `staff.receive_return` to receive and inspect it;
`staff.approve_refund` for bank refunds), every refusal an `authz_fail` event, cursor pages newest first (the packing
queue oldest first). A PACKER sees the orders to pack and on their way only (paid, packed, shipped, and
cash-on-delivery orders placed): others answer 404. Contacts are masked (the record's `customer` and
`address.phone`; the packing slip and label print them); opening a child's order is a `sensitive_read` event.
Test-mode orders (test keys on the live site) are left out of every list, count and the packing queue unless
`?livemode=false` asks for them (`is_test` marks them). Every change is an audit event targeting the order
(`order.held`, `order.released`, `order.tagged`, `order.packed`, `shipping.shipped_by_hand`, `order.delivered`,
`order.cancelled`, `order.notified`, `order.payment_link_sent`, `order.payment_link_cancelled`,
`order.documents_regenerated`, `order.invoice_sent`, `order.packing_slip_printed`, `order.label_printed`,
`order.pick_list_printed`, `order.documents_printed`, `order.return_requested`, `order.return_approved`,
`order.return_declined`, `order.return_label_sent`, `order.return_received`, `order.return_inspected`,
`order.return_photo_added`, `order.restocked`, `refund.paid`, `order.exported`, and the approvals' own). A refusal is
the shop's words, `400 {"non_field_errors": ["..."]}`.

- **The list** `GET orders/` (`?status=&method=razorpay|cod|offline&courier=&created_from=2026-10-01&created_to=
  &shipping=<parcel status>|none&tag=school&hold=true&risk=high&livemode=`, and the panel's tabs `?tab=to_pack|
  shipped|returns|cancelled|drafts`): `id`, `number`, `created`, `placed_at`, `status`, `status_label`,
  `payment_method`, `total`, `items` (as text), `customer` (masked), `courier`, `parcel`, `tags`, `held`, `hold_reason`,
  `risk_bucket`, `is_test`, `is_cod`, `has_returns`, `staff_order`, `livemode`. `?q=` finds an order by its number, an
  invoice's or credit note's number, an email address, a phone's last digits (4 or more), an AWB, a book code, or a
  name (3 letters or more); a search for a person (email, phone, name, book code) is a `customer.lookup` event holding
  the query's keyed hash and how many it found, never the query. Saved views: `saved-views/` with `list_key: "orders"`.
- **The record** `GET orders/<number>/` (or the order's `id`, as the inbox and the audit trail name it): the row's
  fields and `subtotal`, `discount`, `shipping_fee`, `coupon_code`, `savings`, `address`, `lines` (each with its
  `invoiced` value, what a refund of it is worth, and its `refunded` and `returnable` copies), `payments` (`refundable`,
  `older_than_6_months`), `refunds`, `documents` (the invoice and credit notes: `ready`, `url`), `shipments` with their
  last scan, `returns`, `hold`, `risk_reasons`, `quote`, `created_by`, `actions` (what you may do now; the one `primary`
  is the header's button), `refund` (the refund dialog's facts: the payment, `refundable`, `shipping_left`, `methods`,
  `cancels`, `payment_age_days`, `warnings`), `erp` (its ERPNext documents) and `timeline` (status changes and holds,
  payments, refunds, parcels and scans, messages, notes, returns, ERPNext; the audit events too for whoever reads the
  audit log, itself an `audit.read` event).
- **Moves** `POST orders/<number>/pack/`, `ship/` `{"courier": "India Post", "tracking_number": "EA123456789IN"}`
  (sent by hand; a courier booking is the shipping app's), `deliver/`; `hold/` `{"reason": "address to check"}` (out of
  the packing queue; an inbox item), `release/`; `tags/` `{"add": ["school"], "remove": []}` (ten at most, lower case);
  `notify/` `{"kind": "shipped"}` (the message again, when it is still true; an SMS due between 21:00 and 08:00 waits
  for the morning); `invoice/regenerate/` (202: what is missing of its invoice and credit notes, made by the worker)
  and `invoice/resend/`; `payment-link/` `{"action": "send"|"cancel"}` (a staff order waiting for its payment; 503
  while Razorpay cannot be reached). `cancel/` `{"reason": "...", "customer_requested": false}`: not sent yet, unpaid
  or cash on delivery, it is cancelled at once; paid online, it goes through the refund's approval (`201` run, or
  `202` above your refund limit); a cash-on-delivery parcel back undelivered is cancelled with its copies back
  (`"restock": false` if damaged) and its invoice credited (a credit note, no money moving).
- **Refunds** `POST orders/<number>/refunds/` `{"lines": [{"item": 812, "quantity": 1}], "shipping": "40.00",
  "restock": true, "method": "source"|"bank", "speed": "normal"|"optimum", "payee": {"upi": "name@bank"} or
  {"account": "...", "ifsc": "...", "name": "..."}, "customer_agreed": true, "return": 7, "reason": "Damaged"}`
  (`Idempotency-Key` header: the same key answers the first request again, 200). The amount is the lines' invoiced
  values (their share of the coupon and offers taken off) and the shipping asked (at most what is left of it); no
  lines and no shipping: what is left of the payment. Within your `refund_inr` it runs at once (`201`, the change
  request `executed`); above it `202` and FINANCE approves (`staff.approve_refund`); `warnings` holds the 6-month
  warning (Razorpay may refuse a normal refund of an older payment). Back to the source through Razorpay (5–7 working
  days; `optimum` is instant where the bank allows, for a fee); by bank or UPI for cash on delivery and transfers (and
  an online payment with `customer_agreed`): the payee is encrypted, shown masked (`payee_masked`), and the refund
  waits for FINANCE's transfer (an inbox item due in `SHOP_BANK_REFUND_DAYS`). `POST orders/refunds/<id>/payee/`
  `{"reason": "..."}` shows the account to FINANCE (a `sensitive_read` event); `POST orders/refunds/<id>/mark-paid/`
  `{"utr": "..."}` marks it transferred: the refund processed, the customer told, the credit note made, once (the
  second time: 400).
- **Returns** `POST orders/<number>/returns/` `{"lines": [{"item": 812, "quantity": 1}], "reason": "misprint",
  "note": "..."}` (staff for the customer; no window), `GET orders/returns/` (`?status=&open=true&order=&reason=
  &by_customer=`), `orders/returns/<id>/` (with `note` and `next`, its possible moves), then `POST …/approve/`,
  `…/decline/` `{"note": "why"}`, `…/label/` `{"courier": "...", "awb": "..."}` (`staff.handle_return`) and
  `…/receive/`, `…/inspect/` `{"outcome": "restocked"|"damaged"}`, `…/photos/` (multipart `photo`, five at most;
  `GET …/photos/<index>/`) (`staff.receive_return`). A new return is an inbox item due in 48 hours; the customer is
  emailed at each step; its refund is `refunds/` with `"return": <id>` (its lines; a restocked return's copies are not
  added twice).
- **Staff orders** `POST orders/` `{"channel": "phone"|"whatsapp"|"school"|"email", "lines": [{"product": "<slug>",
  "quantity": 2}], "email": "...", "address": {...}, "discount": "50.00", "shipping": null, "send_link": true,
  "note": "...", "reason": "..."}` (`Idempotency-Key` too): priced as the checkout prices (offers included; the
  address's PIN code checked against its state), through the approval `order.staff_discount`: within your
  `discount_percent` of the books it is made at once (`201`, the change request's `result.order` its number, the
  payment link emailed); beyond it, or for a ₹0 total, `202` and nothing exists until FINANCE (`staff.approve_discount`)
  approves. Before asking, `POST orders/preview/` with the lines, the address's `state`, the `email`, the `discount`
  and the `shipping` answers what it would be (`lines`, `subtotal`, `offers`, `discount`, `percent` of the books after
  the offers, `shipping`, `total`, your `limit`, `approval`: the rule's words, or null when it would be made at once,
  and `problems`: sold out, off sale); nothing is stored. `GET orders/products/?q=` (`shop.view_product`) finds books on
  sale for its lines by title, slug or ISBN (20 at most). Its payment comes through the link, or
  `POST orders/<number>/offline-payment/` `{"reference": "UTR...", "reason": "..."}` (the approval
  `order.offline_payment`). The owners get the week's staff orders and their discounts
  by email on Mondays at 08:00.
- **Quotes** `GET orders/quotes/`, `orders/quotes/<id>/` (the schools' quotation requests, contacts masked),
  `GET orders/quotes/<id>/quotation/` (its PDF once made), `POST orders/quotes/<id>/convert/` `{"address": {...},
  "send_link": true}`: a staff order of its books with its discount and shipping, once (the quote keeps its order;
  refused while one waits for approval).
- **The packing room** `GET orders/packing/`: the orders to pack (paid, or placed to pay on delivery; not held, not a
  test order, not courses alone), oldest first, each with `pick` (its books once, with their copies), `weight_g`,
  `destination`, `is_cod` and its `risk_bucket`. PDFs (any `Accept`): `GET orders/<number>/documents/packing-slip/`
  (A4: its books with ISBN and copies, the school or class, its number as a QR code), `…/documents/label/` (4×6 inches,
  for a parcel sent by hand), `POST orders/pick-list/` `{"orders": ["EL-2026-000123", ...]}` (each book once, with its
  copies and orders); `GET orders/<number>/invoice/` and `…/credit-notes/<id>/` (`shop.view_invoice`,
  `shop.view_creditnote`).
- **In bulk** through `POST jobs/` (202, then poll the job): `{"kind": "orders_pack", "params": {"targets":
  ["EL-2026-000123", ...]}}`, `orders_print` (`"document": "packing_slip"|"label"|"invoices"`: one PDF),
  `orders_cancel` (`"reason"`; 250 orders at most; paid online ones go through their refund's approval) and
  `orders_export` (`{"filters": {...}}`, the list's filters but `q`: a CSV, a line per row, with the GST split;
  `shop.export_order`). Each row is done or failed on its own (`errors`); above your `bulk_rows` or `export_rows` an
  approver passes the job first.

A cash-on-delivery order is scored when placed (`insights/jobs/risk.py`: the PIN code's and district's returned
parcels, the customer's earlier returns matched by keyed hashes, a first COD order, its value, an address no courier
could find, the PIN code's directory): `risk_bucket` and `risk_reasons` on the order; a high score holds it for a
payment check while `SHOP_COD_HIGH_RISK_HOLD` is on (an inbox item; release it once confirmed).

```sh
curl "https://admin.examleaf.in/api/v1/staff/orders/?tab=to_pack&risk=high" -b "sessionid=..."
# 200 {"next": null, "previous": null, "results": [{"number": "EL-2026-000123", "status": "pending",
#      "status_label": "placed (pay on delivery)", "payment_method": "cod", "total": "1198.00", "held": true,
#      "hold_reason": "payment check", "risk_bucket": "high", "customer": {"id": 52, "name": "Rahul Das",
#      "email": "ra•••@example.com", "phone": "••••••2345", "is_minor": false}, "tags": [], "is_cod": true, ...}]}
curl -X POST https://admin.examleaf.in/api/v1/staff/orders/EL-2026-000123/refunds/ -b "sessionid=...; csrftoken=..." \
  -H "X-CSRFToken: ..." -H "Idempotency-Key: 6f1c..." -H "Content-Type: application/json" \
  -d '{"lines": [{"item": 812, "quantity": 1}, {"item": 813, "quantity": 1}], "reason": "Damaged in transit"}'
# 202 {"id": 31, "action": "order.refund", "status": "pending", "amount": "1710.00",
#      "rule": "A refund of ₹1,710.00 is above the limit of ₹1,000.", "warnings": [], ...}
```
## Connections (staff)

`/api/v1/staff/connections/…` (code: `integrations/api.py` and `integrations/connections.py`; the model and the
precedence of the keys: [integrations/README.md](integrations/README.md)) is the connections page: one card per
integration, its connection test, its credentials, mode, circuit and webhooks, its events, calls and dead letters. The
[Staff API](#staff-api)'s rules apply. `<provider>` is one of `razorpay`, `shiprocket`, `manual`, `msg91`, `whatsapp`,
`ses`, `storage`, `error_tracker`, `google`, `erpnext`; another: 404. Every change is an audit event
(`connection.tested`, `.credentials_replaced`, `.credentials_refused`, `.mode_changed`, `.circuit_opened`,
`.circuit_reset`, `.webhook_rotated`, `.event_replayed`, `.events_replayed`, `.dead_letter_replayed`,
`.dead_letter_discarded`) and every change of a connection emails the owners.

| Method | Path (under `/api/v1/staff/connections/`) | Permission | What |
|---|---|---|---|
| GET | `` (the list), `<provider>/` | `integrations.view_integrationaccount` (OWNER, ADMIN, FINANCE, AUDITOR) | the cards: `status` (connected, degraded, expired, disabled, not_configured), `mode` in force (off, test, live), `source` of the keys (panel, environment, none) and the environment's keys' last four characters (`held`), the `accounts` (mode, in use, each credential's last four characters, who set them and when, `rotate_in_days`, the access token's `token_in_hours`, the webhook token's last four), `last_success_at`, `last_error`, `last_test`, `circuit`, `calls` (24 hours and 7 days, errors, `p90_ms`), the `fields` Replace asks for, `modes`, the `overlap_warning`, the `actions` that apply, and the provider's `extra` (Razorpay's webhook health and silence, MSG91's SMS sent and held and delivery reports, SES's bounce and complaint rates against 5 % and 0.1 % and the suppressions, the buckets, Google's staff domain, the error tracker's host, ERPNext's sync) |
| POST | `<provider>/test/` | `staff.manage_connections` (OWNER, ADMIN; high) | one harmless authenticated read with the keys in force (Razorpay one payment, Shiprocket the wallet, MSG91 the balance, SES the sending quota, the buckets' heads, ERPNext the ping; Google and the error tracker: their settings), logged and kept on its account: `{"ok", "message", "card"}`; `ok` false is a test that ran and failed |
| POST | `<provider>/credentials/` (`mode`, `credentials` {the card's `fields`}, `reason`) | `staff.manage_connections` (high) | the new keys tested first, in the same call, and kept only if the test passes (400 `{"credentials": ["The new credentials did not pass the test: …"]}` otherwise, the old ones kept); never answered: `{"ok", "message", "card"}`. Razorpay and MSG91 while the environment's keys are in force: the first keys must be of the mode in force and take over at once (Razorpay's webhook secret carried over) |
| POST | `<provider>/mode/` (`mode` off, test or live, `reason`) | `staff.manage_connections` (high) | the account of that mode used (its keys needed), the others switched off; off switches them all off |
| POST | `<provider>/circuit/` (`action` open or reset, `reason`) | `staff.manage_connections` (high) | Shiprocket's and ERPNext's: held open (calls wait until reset), or reset (calls go through, its inbox item done) |
| GET | `<provider>/webhooks/` | `integrations.view_integrationaccount` | our address to paste (`url`), `auth` (token, signature, basic_and_sns), `header`, the token's last four characters, `rotated_at`, `previous_valid_until` (24 hours after a rotation), the week's events by state, `last_event_at`, `silent` (nothing for `INTEGRATION_WEBHOOK_SILENCE_HOURS` while in use) |
| POST | `<provider>/webhooks/rotate/` (`reason`) | `staff.manage_connections` (high) | a new token (32 random bytes), answered once: `{"token", "webhooks"}`; the previous one still accepted for 24 hours. SES's is the environment's (400); Razorpay's while its keys are the environment's (400) |
| GET | `<provider>/events/` (`?state=accepted|duplicate|rejected|failed`) | `integrations.view_inboundevent` | the webhooks received, newest first, the body as a redacted `body_excerpt` |
| POST | `<provider>/events/<id>/replay/`, `<provider>/events/replay-failed/` (`since`) | `staff.replay_webhook` (MEDIUM) | processed again (a rejected one: 400); every failed one since then, 500 at a time (`{"replayed", "more"}`) |
| GET | `<provider>/calls/` (`?operation=&failed=true`) | `integrations.view_integrationcall` | the calls made to it, newest first: `operation`, `status_code` (null: no answer), `duration_ms`, `error`, the redacted `excerpt` |
| GET | `<provider>/failures/` (`?state=open|replayed|discarded&operation=`) | `integrations.view_integrationfailure` | its dead letters (and its app's tasks' that failed before knowing the account); ERPNext's name their outbox row (`erp_outbox`) |
| POST | `<provider>/failures/<id>/replay/`, `…/discard/` (`reason`) | `staff.replay_webhook`; ERPNext's `erp.replay_sync` (high) | run again once, or given up with the reason; ERPNext's through the sync's own replay and discard (`erp.replay`, `erp.discard`); dealt with already: 400 |

```sh
curl -X POST https://admin.examleaf.in/api/v1/staff/connections/razorpay/credentials/ -b "sessionid=..." \
  -H "X-CSRFToken: ..." -d '{"mode": "live", "credentials": {"key_id": "rzp_live_...", "key_secret": "..."},
  "reason": "Rotated after the quarterly review"}'
# 200 {"ok": true, "message": "Connected with the live keys: Razorpay answered (1 payment read).", "card": {...,
#      "source": "panel", "accounts": [{"mode": "live", "enabled": true, "held": {"key_id": "…AbCd",
#      "key_secret": "…9f2c"}, "rotate_in_days": 90, ...}]}}
# 400 {"credentials": ["The new credentials did not pass the test: Razorpay (live) payments: HTTP 401: ..."]}
```

**MSG91's delivery reports** `POST /api/hooks/sms-events/` are MSG91's, not the API's: the token generated on the
connections page (`msg91/webhooks/rotate/`) in the `X-Webhook-Token` header, compared in constant time with the current
one and, for 24 hours after a rotation, the previous one. A missing or wrong token: `403`, kept without its body. A body
without a report: `400`. Otherwise `200 {"detail": "Received."}` at once; the reports (JSON, or a form's `data` field:
`[{"requestId", "report": [{"number", "status", "desc", "date"}]}]`) are kept once per body and once per report (their
request ids, numbers' last digits and statuses, hashed) and written on their SMS by a task: `delivered`, `pending`,
`failed` or `rejected`, with MSG91's words when it failed ("Template Id not found on DLT"). 300 a minute per client
address (`API_THROTTLE_SMS_EVENTS`).

**SES's tracking webhook** `POST /anymail/amazon_ses/tracking/` is anymail's, each SNS message's signature verified
first (its `SigningCertURL` on `sns.<region>.amazonaws.com` only, fetched once a day; SignatureVersion 1 or 2) and its
topic `SES_SNS_TOPIC_ARN` when set; a message that fails: 400. It exists with `ANYMAIL_WEBHOOK_SECRET`'s basic auth,
`SES_SNS_TOPIC_ARN`, or both.

## Templates (staff)

`/api/v1/staff/templates/…` (code: `ops/staff_api.py`; [ops/README.md](ops/README.md)) is the message templates'
registry: what the site sends by SMS, email and (Phase D) WhatsApp, as registered with DLT and MSG91. The
[Staff API](#staff-api)'s rules apply; never deleted (deactivate one). Not paginated.

| Method | Path (under `/api/v1/staff/templates/`) | Permission | What |
|---|---|---|---|
| GET | `` (`?channel=&language=&approval_state=&event=&category=`), `<id>/` | `ops.view_messagetemplate` (ADMIN, MARKETING, AUDITOR, OWNER) | `event`, `channel`, `language`, `text` with DLT's `{#var#}`, `subject`, `variables` (`name`, `type` numeric, alphanumeric, url, urlott, cbn or email, `max_length` up to 30, `about`), `dlt_template_id`, `pe_id`, `header` and `header_suffix`, `msg91_id`, `whatsapp_name`, `category`, `approval_state`, `last_used_at`, `days_unused`, `self_certified_on`, `warnings` |
| POST | `` | `ops.add_messagetemplate` | one added (`template.created`); an SMS for one of the kinds the site sends; one per event, channel and language |
| PATCH | `<id>/` | `ops.change_messagetemplate` | changed (`template.changed`, its `changes`); what it is for stays (`event`, `channel`, `language`: 400); approved: an SMS needs its `msg91_id`, WhatsApp its name |
| POST | `<id>/test/` (`variables` {name: value}) | `ops.change_messagetemplate` (10 an hour) | sent to your own confirmed mobile number or email address only (a value not given: a sample of its type): `{"sent", "to" (masked), "detail"}`; WhatsApp: 400 |

`ops.sms` sends a kind with the approved SMS template's `msg91_id` when there is one, the environment's
`MSG91_TEMPLATE_<KIND>` otherwise, and writes its `last_used_at`. Each night an approved SMS template unused for 75
days (DLT deactivates one at 90) and an approved template whose yearly self-certification is due open inbox items.
## Content (staff)

`/api/v1/staff/content/…` (code: `content/staff_api.py`; the workflow: [content/README.md](content/README.md)) is the
panel's content module: books and papers, the drafts of questions and solutions and their review, the mistakes
readers report, the errata, the imports from the books repository and the legal deposits. It is part of the
[Staff API](#staff-api) and keeps all its rules (the admin host, a second factor or an API key, each action's
catalogued permission, every refusal an `authz_fail` event, cursor pages, `Cache-Control: no-store`), and every list
and record is narrowed to the person's subjects: a CONTENT_EDITOR narrowed to PHY reaches PHY's books, papers,
questions, solutions, reviews, reports and deposits, and another subject's record is a 404. Books and papers change at
once; a question's or a solution's text never does: a change goes to the record's `draft`, a second person reviews and
publishes it, and the site shows the live text until then. Every change is an audit event targeting the record
(`content.book_created`, `content.book_changed`, `content.paper_published` / `_unpublished` / `_changed`,
`content.draft_saved`, `content.question_changed`, `content.draft_discarded`, `content.submitted`,
`content.review_approved`, `content.review_needs_changes`, `content.published`, `content.rolled_back`,
`content.version_restored`, `content.report_received`, `content.report_confirm` / `_reject` / `_fix_online` /
`_fix_in_printing` / `_reopen`, `content.report_changed`, `content.reporter_told`, `content.item_flagged`,
`content.imported`, `content.legal_deposit_recorded`), never with a reader's address. These endpoints are tagged
`content (staff)` in the schema; a refusal is `400 {"non_field_errors": ["..."]}` in words.

| Method | Path (under `/api/v1/staff/content/`) | Permission | What |
|---|---|---|---|
| GET | `summary/` | `content.view_errorreport` | the module's home: `reports_open` (`total`, `by_category`), `reviews_waiting`, `reviews_mine`, `drafts`, `legal_deposits_missing`, `last_import`; each part `null` for whoever may not see it |
| GET POST PATCH | `books/`, `books/<id>/` | `content.view_book`; POST `content.add_book`; PATCH `content.change_book` | books (`?subject=PHY&board=&class_level=&format=print|ebook`): `isbn` (13 digits; its check digit checked when it is set or changed, hyphens may be typed), `format`, `edition`, `published_on` and `deposit_due_on` (the legal deposit's clock), `papers`; one adds `missing_deposits` (the libraries still to send to) |
| GET PATCH | `papers/`, `papers/<id>/` | `content.view_paper`; PATCH `content.change_paper` | papers by code (`?subject=&board=&class_level=&book=&tier=&is_published=&changed=true&q=`), with `questions`, `drafts`, `is_published` and `is_sample`; one adds `header_json` and `tree` (each question in order with its state, a preview and its solution's state). The PATCH changes the title, marks, time and instructions; never the code (it is in the printed QR code), nor whether the paper is on the site (below) |
| POST | `papers/<id>/publish/` `{"is_published": false}`, `{"is_sample": true}` | `staff.publish_paper` | the paper on the site or off it (every solution behind its printed code with it), the book's open sample or not (one per book: it moves from the book's other paper, both audited) |
| GET | `papers/<id>/qr/` (`?printing=PHY-2027-2`) | `content.view_paper` | `{"url", "png"}`: the address the code prints, with the print run when one is named, and the code as a data URL; `400 {"code": "site_url_not_public"}` while `SITE_URL` is not a public https address |
| GET PATCH | `questions/`, `questions/<id>/`, `solutions/`, `solutions/<id>/` | `content.view_question` / `_solution`; PATCH `content.change_question` / `_solution` | the live text and its `draft` (`state` `published`, `draft` or `in_review`; `draft_by`, `published_at`, `published_by`, the open `review`; `?paper=&book=&subject=&state=&changed=true`). PATCH writes the draft (a question's `text_md`, `table_md`, `options_json`, `marks_text`, `group_label`, `part_label`, `is_alternative`; a solution's `body_md`) after the LaTeX check (`400 {"body_md": ["Line 3: ..."]}`); a question's `order`, `label` and `tags` change at once. A field typed back to its live value leaves the draft; a draft changed while it waits for review withdraws the review |
| POST | `questions/<id>/submit/`, `solutions/<id>/submit/` (`{"assignee": <id>}` optional); `…/discard/` | `content.change_question` / `_solution` | the draft to a reviewer: `201` with the review, and an inbox item for the subject's reviewers (or the one named); the draft dropped and its review withdrawn |
| POST | `questions/<id>/rollback/`, `solutions/<id>/rollback/` | `staff.publish_paper` | the last publish from the panel undone: the text before it live again, the text it published back in the draft; refused once the live text changed since (an import, a later publish) |
| GET POST | `<books|papers|questions|solutions>/<id>/history/`, `…/history/<history_id>/restore/` | the record's view; restore its change | the versions, newest first, each with its `changes` (`field`, `before`, `after`, `lines` of `{"op": "equal" | "delete" | "insert", "text"}`); a restore puts a book's or a paper's fields back at once, a question's or a solution's text into its draft |
| GET | `reviews/`, `reviews/<id>/` | `content.view_reviewtask` | the queue, oldest first (`?mine=true`: waiting for me, open, for me or nobody, never my own edit; `?submitted=true`; `?open=true|false`; `?subject=&paper=&state=&stage=`); one adds `draft`, `previous`, `comments`, `changes` (the draft against the live text; once published, the text it replaced against it) and `yours` |
| POST | `reviews/<id>/approve/` `{"comment"}`, `…/needs-changes/` `{"comment", "field"}`, `…/publish/` `{"comment"}` | `staff.publish_paper` | a reviewer's decision; never by whoever edited or submitted the draft (`403 {"code": "own_edit"}`); a publish approves on the way and refuses a draft changed since it was submitted |
| GET PATCH | `reports/`, `reports/<id>/` | `content.view_errorreport`; PATCH `staff.triage_report` | the reported mistakes, oldest first; the open ones (reported, confirmed) unless `?state=` says (`?category=&subject=&printing=&teacher=true&paper=&book=`); spam never shows. One adds `linked` (the question and solution as the site shows them now) and `handled_by`; the reporter's address is masked. PATCH `{"staff_note", "public"}` (`public`: on the errata) |
| POST | `reports/<id>/confirm/`, `…/reject/` `{"staff_note"}`, `…/fix-online/`, `…/fix-in-printing/` `{"fixed_in": "PHY-2027-2"}`, `…/reopen/`; `…/tell/` | `staff.triage_report` | one step of the triage: reported, then confirmed or rejected, then fixed online, then fixed in a printing; a rejection reopened. `tell/` emails the reporter once that it is fixed, then forgets their address |
| GET | `errata/` | `content.view_errorreport` | confirmed and fixed mistakes, per book and printing (`?book=<slug or id>&printing=&public=`) |
| GET | `imports/` | `content.view_paper` | the imports, newest first: staff jobs of kind `content_import`, within the person's subjects |
| GET POST | `legal-deposits/`, `legal-deposits/<id>/`, `legal-deposits/<id>/proof/`, `legal-deposits/missing/` | `content.view_legaldeposit`; POST `content.add_legaldeposit` | the copies sent to the four libraries (`?book=&library=`); POST `{"book", "library", "sent_on", "proof", "edition", "erp_delivery_note"}` (`edition`: the book's when left out; JSON, or multipart with `proof_file`, a PDF, JPEG, PNG or WebP of 5 MB at most); `proof/` the scan; `missing/` the published books whose edition some library has not received, with `due_on` and `overdue` |

An import is a staff job: `POST /api/v1/staff/jobs/` `{"kind": "content_import", "params": {"subject": "physics",
"commit": ""}, "dry_run": true}` (`staff.import_content`, high: a re-authentication within 5 minutes) reads the books
repository (`commit`: a commit's hash, read with `git archive`; empty, the folder as it is; `"fixtures": true`, the test
papers, on a test site only), compares it with the database and writes nothing. Its `result` is `{"subject", "commit",
"source", "papers", "questions", "counts": {"created", "updated", "unchanged", "unmatched", "removed"}, "rows":
{outcome: [labels]}}`. The apply names it, `{"params": {..., "dry_run_job": 41}, "dry_run": false}`, for the same
subject and commit within 24 hours, and refuses to run if the repository moved since; it writes each paper in its own
transaction, only what changed, and unpublishes a question gone from the repository rather than deleting it.

```sh
curl https://admin.examleaf.in/api/v1/staff/content/reviews/?mine=true -b "sessionid=..."
# 200 {"next": null, "previous": null, "results": [{"id": 17, "label": "PHY-E01 2(c), solution", "kind": "solution",
#      "target_id": 412, "subject": "PHY", "paper": 3, "stage": "check", "state": "in_progress", "submitted_by": 9,
#      "edited_by": 9, ..., "fields_changed": ["body_md"], "yours": false}]}
curl -X POST https://admin.examleaf.in/api/v1/staff/content/reviews/17/publish/ -b "sessionid=...; csrftoken=..." \
  -H "X-CSRFToken: ..." -H "Content-Type: application/json" -d '{"comment": ""}'
# 200 {"id": 17, "state": "approved", "stage": "publish", "published_by": 12, ...}      403 {"code": "own_edit"}
```

The daily tasks: `content.tasks.flag_items` (02:20) turns the quiz's item analysis (`insights.ItemStat` with flags)
into reports of category `item_analysis`, once per item and not again within 30 days of one closed;
`content.tasks.purge_spam` (04:10) deletes spam reports after 30 days; `content.tasks.check_legal_deposits` (07:00)
keeps one inbox item per published book whose deposits are not all made, due `CONTENT_LEGAL_DEPOSIT_DAYS` after its
publication.
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

## Finance (staff)

`/api/v1/staff/finance/…` (code: `shop/staff_finance.py`, the settlements `shop/settlements.py`; the module:
[shop/README.md](shop/README.md#finance)) is the panel's Finance module: payments and the stuck ones, refunds and
offline payments with the change requests waiting for FINANCE, payment links (a staff order's, a B2B invoice's of
ERPNext), Razorpay's settlements and their lines, Finance today, and a document's copy in ERPNext. It keeps every rule
of the [Staff API](#staff-api): the admin host only, a member of staff with a second factor (an API key reads only),
each action's catalogued permission, every refusal an `authz_fail` event, cursor pages, `Cache-Control: no-store`; the
schema tags it `finance (staff)`. What it does not do is Orders' (the refund itself and its approval through
`order.refund`, a bank refund marked paid, an offline payment recorded: [Orders (staff)](#orders-staff)), Tax's (the
documents register: [Tax (staff)](#tax-staff)), the shipping app's (cash on delivery's remittances) and ERPNext's
(payouts, purchases, the bank, closing a period: the console links them). Test-mode rows (the other mode's keys) are
left out of every list and count unless `?livemode=false` asks for them (`is_test` marks them); a refusal is the
shop's words, `400 {"non_field_errors": ["..."]}`; 503 while Razorpay cannot be asked (nothing changed). The audit
events: `payment.reconciled`, `order.payment_link_sent`, `order.payment_link_cancelled`, `payment.link_made`,
`payment.link_cancelled`, `payment.link_paid`, `payment.link_reconciled`, `payment.link_posted`,
`payment.settlements_fetched`, `payment.settlement_matched`, `payment.settlement_mismatched`,
`payment.settlement_posted` and `payment.settlement_line_matched` (its note the event's reason), on the money chain.

| Method | Path (under `/api/v1/staff/finance/`) | Permission | What |
|---|---|---|---|
| GET | `today/` | `shop.view_payment`, else `staff.view_cod` | what waits, a row a duty (`key`, `count`, `oldest` day, `amount`, `configured`): refunds to approve, bank refunds to transfer, offline payments to approve, stuck payments, B2B payments to post, settlement lines not matched, settlements that do not match, cash on delivery receivable, overdue and mismatched, credit notes the cut-off refused, the sync's differences, disputes (`configured: false`); each row only for whoever may see its records, test mode left out |
| GET | `payments/` (`?status=&method=&stuck=&created_from=&created_to=&livemode=&q=`) | `shop.view_payment` | newest first, with Razorpay's ids, `stuck`, `is_link`, and once settled its `fee`, `tax` and `settlement`; `q`: an order's number, Razorpay's `pay_`, `order_` or `plink_` id, an offline reference |
| GET | `payments/<id>/` | `shop.view_payment` | the row and the order's facts, `refunds`, `webhooks` (seen in the last 7 days), `last_webhook` (its allowed fields only), `timeline` (the audit events too for whoever reads the log); a child's order's payment is a `sensitive_read` |
| POST | `payments/<id>/reconcile/` | `staff.replay_webhook` | Razorpay asked again about the payment's order: a captured payment recorded, an authorised one captured first (the late-authorised case), a second one refunded; `{paid, detail, changes: {what: [before, after]}, payment}`; an offline or cash payment, or one of the other mode's keys, refused |
| GET | `offline-payments/` (`?state=waiting\|recorded&livemode=&q=`) | `shop.view_payment` | the payments received by transfer or UPI; `waiting`: the `order.offline_payment` change requests waiting for FINANCE (approved at `change-requests/<id>/approve/`) |
| GET | `refunds/` (`?state=waiting\|pending\|processed\|failed&method=source\|bank\|none&livemode=&q=`) | `shop.view_refund` | refunds with the method, speed, ARN, the transfer's UTR, the credit note and who asked; `waiting`: the `order.refund` change requests waiting for FINANCE |
| GET | `payment-links/` (`?kind=order\|invoice&state=sent\|paid\|cancelled\|expired&livemode=&q=`) | `shop.view_payment` | the staff orders' links (the default) or the B2B invoices': amount, state, address, Razorpay's ids, sent, expiry (15 days), paid, who made it; a B2B one's ERPNext entry once posted |
| POST | `payment-links/` (`order` or `invoice`, `action`: `send`\|`cancel`) | `shop.change_order` | an order's link (a staff order waiting for its online payment) made once and emailed, later the same again, or cancelled; a B2B invoice's (its copy in the platform with something outstanding) made (201, its address in `url` for staff to send) or the open one answered (200), or cancelled |
| POST | `payment-links/invoices/<id>/reconcile/` | `staff.replay_webhook` | a B2B link asked of Razorpay again (its webhook lost) |
| POST | `payment-links/invoices/<id>/posted/` (`erp_name`) | `staff.reconcile_settlements` | a paid B2B link's Payment Entry, posted in ERPNext by hand, recorded (its inbox item done); once |
| GET | `settlements/` (`?state=fetched\|matched\|posted\|mismatched&date_from=&date_to=&livemode=&q=`) | `shop.view_settlement` | Razorpay's settlements, newest day first: `settlement_id`, `date`, `utr`, `gross`, `fees`, `tax` (GST on the fees), `adjustments`, `net`, `state`, `problem`, `matched_at`, `posted_at`; `q`: the `setl_` id or the UTR |
| GET | `settlements/<id>/` | `shop.view_settlement` | with `counts` (lines, unmatched, by type) and `erp` (its Journal Entry's outbox row: state, attempts, last error, ERPNext's name) |
| GET | `settlements/<id>/lines/` (`?matched=&type=payment\|refund\|adjustment`) | `shop.view_settlementline` | its lines in Razorpay's order: `entity_id`, `amount`, `fee` (without its GST), `tax`, `credit`, `debit`, the `payment`, `refund` or B2B `link` it is, `matched`, `matched_by` (empty: by Razorpay's id), `note` |
| POST | `settlements/<id>/match/` (`line`, one of `payment`, `refund`, `accept: true`; `note`) | `staff.reconcile_settlements` | a line matched by hand to a payment (of its amount, no other line's) or a refund of the settlement's mode, or an adjustment accepted as it is; the settlement evaluated again (matched and posted once nothing is left); a posted settlement refused (correct ERPNext's entry by hand) |
| POST | `settlements/fetch/` (`day`, `dry_run`) | `staff.reconcile_settlements` | a day of Razorpay's settlements (India, from 2020, today at the latest) fetched, matched and posted as a job (`settlement_fetch`): 202 with the job, its result the counts; the same as `POST jobs/ {"kind": "settlement_fetch", "params": {"day": ...}}` |
| GET | `documents/<number>/erp/` (dashes for its slashes) | `shop.view_invoice` | an invoice's or credit note's copy in ERPNext: `state` (`mirrored`, `waiting`, `failed`, `dead`, `discarded`, `not_sent`, `off`, `test`), its doctype and name there, its outbox rows |

The nightly runs: `shop-reconcile-payments` (02:30: the online orders still awaiting their payment 10 minutes on,
staff orders' links included, then the B2B invoices' open links, asked of Razorpay) and `shop-fetch-settlements`
(03:15: yesterday's settlements, then those matched while `ERP_SYNC_SETTLEMENTS` was off posted once), each
`single_run`. A stuck payment is an online one created
or authorised `SHOP_STUCK_PAYMENT_MINUTES` (15) ago that reached Razorpay on an order still unpaid (a link only once
past its life), or one captured on an order still pending. A B2B invoice's payment cannot go through ERPNext's
contract (`create_payment_entry` takes only the platform's own invoices): it opens a `b2b_payment` inbox item, FINANCE
posts the Payment Entry in ERPNext and records its name with `posted/`.

```sh
curl -X POST https://admin.examleaf.in/api/v1/staff/finance/payments/9101/reconcile/ \
  -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..."
# 200 {"paid": true, "detail": "Razorpay had the payment: the order is paid now; payment 9101 recorded as captured.",
#      "changes": {"order": ["pending", "paid"], "payment 9101": ["authorized", "captured"]}, "payment": {...}}
curl -X POST https://admin.examleaf.in/api/v1/staff/finance/settlements/2/match/ \
  -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..." -H "Content-Type: application/json" \
  -d '{"line": 23, "payment": 9101, "note": "Its webhook was lost; Razorpay was asked again."}'
# 200 {"id": 23, "type": "payment", "entity_id": "pay_...", "matched": true, "matched_by": "Anita Baruah", ...}
curl -X POST https://admin.examleaf.in/api/v1/staff/finance/settlements/fetch/ \
  -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..." -H "Content-Type: application/json" \
  -d '{"day": "2026-10-09"}'
# 202 {"id": 812, "kind": "settlement_fetch", "state": "queued", ...}
```

## Home and reports (staff)

`/api/v1/staff/home/` and `/api/v1/staff/reports/…` (code: `insights/staff_home.py` and `insights/staff_api.py`; the
numbers: `insights/metrics.py` and `insights/reports.py`; the rules: [insights/README.md](insights/README.md) "Home and
Reports") are the panel's Home and its reports. They keep every rule of the [Staff API](#staff-api): the admin host
only, a member of staff with a second factor (an API key reads no Home card: it holds no role), every refusal an
`authz_fail` event, `Cache-Control: no-store`; the schema tags them `home (staff)` and `reports (staff)`; the reports
have a throttle of their own (`STAFF_THROTTLE_REPORTS`, 60 a minute). Four rules hold for every number:

- **One definition.** Each card and each report says in words what it counts (`definition`, and every report column's)
  and when it was worked out (`as_of`); the Django admin's dashboard counts the same way.
- **Test mode is left out.** On a live site an order made with test keys is in no number (`test_mode` false); a site
  running on test keys counts everything and says `test_mode: true`. Home says how many test orders it left out
  (`test_orders_left_out`).
- **Nobody is named.** No row of any report has a user, a learner, an address or a contact: counts and sums only. A
  cell standing on fewer than `INSIGHTS_MIN_CELL` (10) orders or people, or `INSIGHTS_MIN_CELL_CLASS` (5) learners of a
  chapter, has its numbers null and `hidden: true, under: 10`, and no total includes the cells it hides.
- **Periods are India's days.** `from` and `to` are days (`YYYY-MM-DD`, both included); by default the 30 days to
  today (90 for settlements); never after today, never backwards, at most 13 months: `400 {"to": ["Not after today."]}`.

**`GET home/`** (any member of staff; `?period=today|week|month`, `week` by default) answers the cards of the person's
roles whose permissions they hold, in the order of `insights.metrics.SPECS`: `{as_of, period, test_mode,
test_orders_left_out, cards}`. A card is `{key, label, group, unit, value, definition, as_of, period, href, test_mode,
comparison, error}`: `group` is `measure` (a total over the period, with `comparison` `{previous, difference,
percent, period}` against the period of the same length before it) or `queue` (what waits for a person, as it stands
now); `unit` is `inr` (a decimal string) or `count`; `href` is the console's list or report it counts, already
filtered. A card that could not be worked out has `value: null` and an `error`; one whose source module is not
installed is left out.

| Card (`key`) | Group | Roles | Needs | Counts |
|---|---|---|---|---|
| `net_revenue` | measure, ₹ | OWNER, ADMIN, FINANCE, AUDITOR | `staff.view_insights`, `shop.view_payment`, `shop.view_refund` | the payments first captured in the period less the refunds processed in it, shipping and GST included; a cash-on-delivery order when its parcel is delivered and the courier has the cash |
| `orders_placed` | measure | OWNER, ADMIN, AUDITOR | `shop.view_order` | orders placed in the period, paid online or to pay on delivery, not cancelled or refunded in full since |
| `codes_redeemed` | measure | OWNER, ADMIN, AUDITOR | `staff.view_insights`, `learn.view_bookcode` | book codes a student entered in the app in the period |
| `active_learners` | measure (7 days) | OWNER, ADMIN, AUDITOR | `staff.view_insights`, `learn.view_progress` | customers' accounts with a clip watched, a quiz answer or a flash card in the last 7 days: a count, never a list; staff left out |
| `orders_to_pack` | queue | OWNER, ADMIN, SALES, SALES_REP, PACKER | `shop.view_order` | paid or to pay on delivery, not packed and not on hold: the Orders list's "To pack" tab |
| `quotes_open` | queue | OWNER, ADMIN, SALES, SALES_REP | `shop.view_quoterequest` | quotation requests waiting for a quotation (status `new`) |
| `refunds_to_approve` | queue | OWNER, FINANCE | `staff.approve_refund` | `order.refund` change requests above the asker's limit, pending and not past their time, other than your own |
| `bank_refunds_to_pay` | queue | OWNER, FINANCE | `staff.approve_refund` | refunds by bank or UPI waiting for FINANCE to transfer and mark them paid |
| `cod_overdue` | queue | OWNER, ADMIN, FINANCE | `staff.view_cod` | cash-on-delivery remittances more than `SHIPPING_COD_GRACE_DAYS` working days past the day they were expected |
| `tickets_due`, `tickets_breached` | queue | OWNER, ADMIN, SUPPORT | `support.view_ticket` | open tickets whose next legal deadline falls later today; open tickets already past one (the list's "Overdue" tab) |
| `reports_open`, `items_flagged` | queue | OWNER, ADMIN, CONTENT_EDITOR, REVIEWER | `content.view_errorreport` | reported mistakes waiting for triage, within the person's subjects; those the item analysis flagged |
| `settlement_items_unmatched` | queue | OWNER, ADMIN, FINANCE, AUDITOR | `shop.view_settlement` | lines of Razorpay's settlements that match no payment and no refund of ours |

**`GET reports/`** (`staff.view_insights`) lists the reports: `{test_mode, reports: [{key, label, summary, page, api,
needs, available, configured}]}`; `available` is whether the person holds every permission in `needs`, `configured`
false while a report's source (the settlements) is not set up. Each report is a `GET` with its filters in the query,
a `403 permission_denied` naming the missing permission, and the answer `{report, definition, columns: [{key, label,
definition}], as_of, test_mode, period: {start, end, days} | null, …}` and its own parts:

| Path (under `/api/v1/staff/reports/`) | Permission | Filters | What it adds |
|---|---|---|---|
| `sales/` | `staff.view_insights`, `shop.view_orderitem` | `from`, `to`, `by` (`product`, `subject`, `class`, `board`, `edition`, `none`), `grain` (`none`, `day`, `week`, `month`) | `by`, `grain`, `totals` and `rows` `{key, label, period_start, orders, units, gross, discount, net}`; more than 5,000 rows: 400, narrow it |
| `sales-by-place/` | same | `from`, `to`, `level` (`state`, `district`, `pin`), `state` (a code: `AS`) | `minimum`, `hidden_rows`, `totals_shown` (the rows shown only) and `rows` `{hidden, under, level, state, state_name, district, pin, label, orders, units, net}` |
| `codes/` | `staff.view_insights`, `learn.view_bookcode` | `batch` | `rows` per batch `{batch, printed, sold, activated, activated_7d, revoked, activation_rate}` (`sold` and `revoked` null until the course module records them) and `districts` `{hidden, under, district, redeemed, redeemed_7d}` |
| `course-health/` | `staff.view_insights`, `learn.view_progress` | `subject`, `chapter`, `grain` (`day`, `week`, `month`) | `computed_at` (the nightly job's), `subjects`, `series` (learners, clips, quiz answers and accuracy, flash cards and lapses per period, with 7- and 28-day smoothing for days), `codes_by_week`, `rows` (the chapters over 28 days) |
| `cod/` | `staff.view_insights`, `staff.view_cod` | `from`, `to` | `rows` (what is outstanding by how late), `remitted` `{count, expected, received, difference}`, `by_courier` |
| `settlements/` | `staff.view_insights` (and `shop.view_settlement` once the Finance module sets settlements up) | `from`, `to` | `configured`, `note`, `rows` `{reference, date, gross, fees, tax, refunds, net, utr, state}`; `configured: false` and no rows while there is no Settlement |
| `print-run/` (`POST`) | `staff.view_insights`, `shop.view_product` | body `{product, net_price, unit_cost, salvage}` | the newsvendor sum recomputed (below) |

The cohorts, forecasts, print runs and backtests stay [Insights (staff)](#insights-staff)'s endpoints, which now also
hide a cohort week under 10 learners and a district under 10 redemptions (`hidden`, `under`).

`POST reports/print-run/` recomputes the print run of one title from the net price, the print cost and the salvage
the person types, with `insights.stats`: the critical ratio Cu ÷ (Cu + Co), the demand at that percentile from the
newest forecast from now to the exam, less the copies in stock and on order. Net 195, cost 60 and salvage 5 give
`critical_ratio` 0.7105, the 71st percentile. `target_quantity` and `recommended_quantity` are null while there is no
forecast for the title (`note` says so); `shown` is false while the forecast has not beaten the seasonal naive.
Nothing is stored: the nightly advice (`insights/print-runs/`) is unchanged.

**Exports.** Any report as a file is a staff job: `POST /api/v1/staff/jobs/` `{"kind": "report_export", "params":
{"report": "sales", "filters": {"from": "2026-10-01", "to": "2026-10-07", "by": "subject"}}}`
(`staff.export_report`, high: FINANCE, AUDITOR, ADMIN and the owners, who also need the report's own permissions;
above your `export_rows` it waits for an approver). `report` is a key of `reports/`, or `cohorts` or `forecasts` (the
insights' own); an unknown filter is a 400. The file is a CSV in the private storage, linked by the job's `result_url`
for 5 minutes at a time and kept a week: a hidden cell reads "fewer than 10", text a spreadsheet would run as a formula
is written as text, and the last row has the member of staff's number and the time. The audit event is
`report.exported` with the report, its filters and its row count.

```sh
curl "https://admin.examleaf.in/api/v1/staff/home/?period=month" -b "sessionid=…"
# 200 {"as_of": "2026-10-09T18:42:10+05:30", "period": {"start": "2026-09-10", "end": "2026-10-09", "days": 30,
#      "key": "month", "label": "The last 30 days"}, "test_mode": false, "test_orders_left_out": 2, "cards": [
#      {"key": "net_revenue", "label": "Net revenue", "group": "measure", "unit": "inr", "value": "184250.00",
#       "definition": "Money received less money returned in the period …",
#       "href": "/reports/sales/?from=2026-09-10&to=2026-10-09", "test_mode": false, "error": "",
#       "comparison": {"previous": "151900.00", "difference": "+32350.00", "percent": "+21.3", ...}, ...}, ...]}
curl "https://admin.examleaf.in/api/v1/staff/reports/sales-by-place/?level=district&state=AS" -b "sessionid=…"
# 200 {"report": "sales-by-place", "minimum": 10, "hidden_rows": 3, "totals_shown": {"orders": 212, "units": 340,
#      "net": "98450.00"}, "rows": [{"hidden": false, "under": null, "label": "Kamrup Metro", "orders": 61, ...},
#      {"hidden": true, "under": 10, "label": "Dhemaji", "orders": null, "units": null, "net": null, ...}], ...}
curl -X POST https://admin.examleaf.in/api/v1/staff/reports/print-run/ -b "sessionid=…; csrftoken=…" \
  -H "X-CSRFToken: …" -H "Content-Type: application/json" \
  -d '{"product": "physics-sample-papers-2027", "net_price": "195.00", "unit_cost": "60.00", "salvage": "5.00"}'
# 200 {"critical_ratio": 0.7105, "percentile": 71, "target_quantity": 1240, "supply": 540,
#      "recommended_quantity": 700, "range": {"p10": 820, "p50": 1010, "p90": 1380, "weeks": 18}, ...}
```

## Catalogue (staff)

`/api/v1/staff/catalogue/…` (code: `shop/staff_catalogue.py`; the rules: `shop/catalogue.py`, `shop/pricing.py`,
`shop/copy_rules.py`, `shop/barcode.py`, the jobs `shop/catalogue_jobs.py`; [shop/README.md](shop/README.md)
"Catalogue") is the Catalogue module's API: products by section with their chips, a product's parts each behind its
own permission, coupons and offers through their approvals with the dark-pattern guardrails, the shipping rates, the
shelves, stock by hand, versions, the prior price, the EAN-13 barcode, and the import and export as jobs. It keeps
every rule of the [Staff API](#staff-api): the admin host only, a member of staff with a second factor (an API key
reads only), each action's catalogued permission (area "Catalogue"), every refusal an `authz_fail` event, cursor
pages, `Cache-Control: no-store`; the schema tags it `catalogue (staff)` (the bare `catalogue/` stays the permissions'
catalogue). A product's parts: the page's fields `shop.change_product` (CONTENT_EDITOR, SALES), the MRP and selling
price `staff.change_price` (SALES) through the approval `product.price` (beyond the maker's `discount_percent` off the
MRP FINANCE approves), the HSN or SAC code and a bundle's treatment `staff.change_product_tax` (FINANCE), stock
`staff.set_stock` (SALES). Coupons and offers are MARKETING's and SALES's (`coupon.create`, `coupon.change`,
`offer.create`, `offer.change`: a deeper discount beyond the maker's limit waits for FINANCE). Every change is an
audit event (`catalogue.product_created`, `catalogue.product_changed` with the fields, `catalogue.stock_set`,
`catalogue.bundle_changed`, `catalogue.picture_*`, `catalogue.cover_changed`, `catalogue.rate_*`,
`catalogue.category_*`, `catalogue.collection_*`, `catalogue.type_*`, `catalogue.attribute_*`, `catalogue.import_uploaded`, `catalogue.imported`,
`catalogue.exported`, `coupon.codes_made`) and a version in the record's history (products, coupons, offers and
shipping rates: who, when, the change request's reason). Money is in rupees as decimal strings; a refusal is `400
{"field": ["…"]}` or `{"non_field_errors": ["…"]}`.

| Method | Path (under `/api/v1/staff/catalogue/`) | Permission | What |
|---|---|---|---|
| GET | `products/` (`?q=&kind=&category=&collection=&published=&stock=out\|low\|in_stock&tax_problem=&incomplete=`) | `shop.view_product` | the list with its chips: `tax_problem` (`""` when the GST agrees with the master today), `courier_problem` (`""` when the courier can be quoted), `stock_state`, `available`; `q` finds a title's words, a slug or an ISBN's digits |
| GET | `products/<slug>/` | `shop.view_product` | by section: identity, `prices` (with the `prior_price` the website shows), `tax` (the master's rate today, `next_change`, the chip's words), physical (`weight_grams`, `length_cm`, `width_cm`, `height_cm`, `packaging`, `courier_problem`), `stock_info` (`stock`, `available`, `state`, `low_stock`, `reserved`, `awaiting_payment`, `alerts`), `cover` and `images`, `bundle_items`, SEO, `old_slugs`, `barcode`, `waiting` (its price changes waiting for approval) |
| POST | `products/` | `shop.add_product` (a price below the MRP: `staff.change_price` too) | a new product: `title`, `slug`, `kind`, `mrp` at least; something to post needs `weight_grams` above 0 and `packaging` (a flyer by default) or its dimensions; made at its MRP and off sale unless `is_active`; a `price` below the MRP follows through `product.price`: 201 `{"product", "price_change"}` |
| PATCH | `products/<slug>/` | the parts given: `shop.change_product`, `staff.change_price` (`mrp`, `price`, with `reason`), `staff.change_product_tax` (`hsn`, `tax_treatment`, `tax_note`, `tax_note_date`) | the page's fields save at once (200 the product); a price within your limit too; beyond it 202 `{"price_change", "slug"}` with the rest saved; `stock` is refused here (`stock/`); a renamed slug keeps the old one (`old_slugs`: the shop redirects it); the kind is fixed once sold; an ISBN once per kind |
| POST | `products/<slug>/pictures/` (multipart `image`, `alt`, `position`, `as_cover`) | `shop.add_productimage` (`as_cover`: `shop.change_product`) | a picture (JPEG, PNG or WebP, 2 MB and 4096 px at most), its sizes made by the worker; 201 the product |
| PATCH DELETE | `products/<slug>/pictures/<id>/` (`alt`, `position`) | `shop.change_productimage`, `shop.delete_productimage` | its description and place; or taken off |
| PUT | `products/<slug>/bundle/` `{"lines": [{"product": "<slug>", "quantity": 1}]}` | `shop.change_product` | a bundle's books all at once (1 to 50, each once, no bundle in a bundle); refused once orders have taken its copies from stock (a return gives back the books it holds) |
| POST | `products/<slug>/stock/` `{"stock", "reason", "expected"}` | `staff.set_stock` | a book's copies set by hand (audited); `expected`, the count you read: 400 when orders changed it meanwhile; a bundle's and a course's: 400 |
| GET | `products/<slug>/history/` | `shop.view_product` | its versions, newest first: `changes` (`field`, `before`, `after`), `by`, `by_name`, `at`, `reason` |
| GET | `products/<slug>/prior-price/?price=` | `shop.view_product` | what that selling price would show if set now: `lowest_in_30_days`, `prior_price` (null when not lower, or before `applies_from`), `window_from`, `applies`; nothing changes |
| GET | `products/<slug>/barcode.svg/` | `shop.view_product` | its ISBN as an EAN-13 barcode (SVG, 37.29 mm wide), for the printer and the packing slip; 404 without a valid ISBN-13 |
| GET | `stock/` (`?q=&state=&published=`), `stock-alerts/` | `shop.view_product`; `shop.view_stockalert` | the books' copies, the fewest first, with `reserved` (orders placed, not yet shipped) and `awaiting_payment` (orders not yet paid), test orders left out on a live site; the back-in-stock requests by product (`requests`, `last_asked`: never who) |
| GET POST | `coupons/` (`?q=&state=live\|scheduled\|ended\|inactive&kind=&single_use=`) | `shop.view_coupon`; `shop.add_coupon` | the coupons with their `state`, `uses`, codes; a new one `{"code", "value", …, "reason"}`: the change request, 201 executed within your limit, 202 waiting beyond it |
| GET PATCH | `coupons/<code>/` | `shop.view_coupon`; `shop.change_coupon` | one coupon; the fields that change and `reason`: 200, or 202 when the discount gets deeper beyond your limit; the code never changes |
| GET | `coupons/<code>/codes/` (`?used=&job=`), `coupons/<code>/history/` | `shop.view_couponcode`; `shop.view_coupon` | its single-use codes (used, `order`'s number, never who); its versions |
| GET POST | `offers/` (`?q=&state=&scope=&combinable=`) | `shop.view_offer`; `shop.add_offer` | the automatic offers; a new one `{"name", "value", …, "reason"}` (201, or 202 beyond your limit) |
| GET PATCH | `offers/<id>/`, `offers/<id>/history/` | `shop.view_offer`; `shop.change_offer` | one offer and its versions (its scope's products, categories and collections among the changes); a change as for coupons |
| GET POST | `shipping-rates/` | `shop.view_shippingrate`; `shop.add_shippingrate` | the delivery rates; a new one `{"name", "states", "fee", "free_above", "is_active", "reason"}`: no state in two active rates, one rate at most for every other state |
| GET PATCH | `shipping-rates/<id>/`, `shipping-rates/<id>/history/` | `shop.view_shippingrate`; `shop.change_shippingrate` | one rate and its versions; a change applies to carts at once |
| GET POST | `categories/` | `shop.view_category`; `shop.add_category` | the tree in tree order (`depth`, `parent`, `products`); a new one under `parent` (or at the top) |
| GET PATCH | `categories/<slug>/` | `shop.view_category`; `shop.change_category` | its name, address and description |
| POST | `categories/<slug>/move/` `{"target": "<slug>" or null, "position": "first-child\|last-child\|left\|right"}` | `shop.change_category` | it moves with what is under it (never under itself); the whole tree back |
| GET POST PATCH | `collections/`, `collections/<slug>/` | `shop.view_collection`; `add_`, `change_collection` | hand-picked lists: name, description, `is_active`, `position`, `products` (slugs, in order) |
| GET POST PATCH | `product-types/`, `product-types/<id>/`; `product-types/<id>/attributes/`, `…/attributes/<id>/` | `shop.view_producttype`; `add_`, `change_producttype`; `add_`, `change_attribute` | the types and their attributes; an attribute's code fixed once products have values for it, its kind changed only when every value fits |
| GET | `summary/`, `options/` | `shop.view_product` | the module's home (`incomplete`, `tax_problems`, `low_stock`, `out_of_stock`, `stock_alerts`, `approvals`, `prior_price_applies`); the forms' choices |
| POST | `import/` (multipart `file`, a CSV in the admin's export format, 2 MB and 2,000 rows at most) | `shop.import_product` (ADMIN) | the file kept and its dry run started: 202 the job (`product_import`, `dry_run`), whose `result` counts `created`, `updated`, `unchanged`, `errors`, `prices_waiting` and lists each row that changes something |

The import's apply is `POST jobs/` `{"kind": "product_import", "params": {"file": "<the dry run's file>",
"dry_run_job": <its id>}}`: the same person's finished dry run of the same bytes, within 24 hours, once. Each row goes
through the rules above in its own transaction (a price through `product.price`, a new product made at its MRP);
stock and the GST rate are never imported. The export is `POST jobs/` `{"kind": "product_export", "params":
{"filters": {…the list's…}}}` (`shop.export_product`; above your `export_rows` an approver first), cells that would
start a formula escaped. A school's single-use codes are `POST jobs/` `{"kind": "coupon_codes", "params": {"coupon":
"<code>", "count": 300, "prefix": "CCHS", "note": "<the school's name>"}}` (`shop.add_couponcode`; the coupon
single-use first; above your `bulk_rows` an approver first): `PREFIX-XXXXXXXX` codes (no 0, O, 1, I or L), and a CSV of
them for the school through the job's `result_url`.

```sh
curl "https://admin.examleaf.in/api/v1/staff/catalogue/products/?incomplete=1" -b "sessionid=..."
# 200 {"next": null, "previous": null, "results": [{"slug": "physics-sample-papers-2027", "title": "...", "kind":
#      "sample-papers", "mrp": "349.00", "price": "299.00", "stock": 40, "available": 40, "stock_state": "in_stock",
#      "tax_problem": "", "courier_problem": "No weight: weigh one copy, in grams.", ...}]}
curl "https://admin.examleaf.in/api/v1/staff/catalogue/products/physics-sample-papers-2027/prior-price/?price=249" \
  -b "sessionid=..."
# 200 {"price": "249.00", "lowest_in_30_days": "279.00", "prior_price": "279.00", "window_from": "2027-01-04T10:00:00+05:30",
#      "applies": true, "applies_from": "2027-01-01"}
curl -X PATCH https://admin.examleaf.in/api/v1/staff/catalogue/products/physics-sample-papers-2027/ \
  -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..." -H "Content-Type: application/json" \
  -d '{"price": "199.00", "weight_grams": 320, "reason": "The board-exam offer"}'
# 202 {"price_change": {"id": 812, "action": "product.price", "status": "pending", ...}, "slug": "physics-..."}
```

The storefront's product (`GET /api/v1/products/…`, [Store catalogue](#store-catalogue)) gains `prior_price`; the
cart's coupon (`POST cart/coupon/`) takes a school's single-use code as it takes a coupon's code.
## Course (staff)

`/api/v1/staff/course/…` (code: `learn/staff_api.py`, its rules in `learn/course.py` and `learn/codes.py`; the app:
[learn/README.md](learn/README.md)) is the panel's Course module: a subject's outline and its row actions, a
revision's review and its publish now or at a time, the 30-day bin, the quiz bank with its item analysis, access to
the course, the print runs' book codes with their lookup and report, and one learner's page for support. It keeps
every rule of the [Staff API](#staff-api): the admin host only, a second factor or an API key, each action's
catalogued permission (area "Course"), every refusal an `authz_fail` event, cursor pages, `Cache-Control: no-store`;
the schema tags it `course (staff)`. A CONTENT_EDITOR or a REVIEWER narrowed to subjects reaches those subjects'
chapters, revisions, clips, cards, items, entitlements and print runs; another subject's record is a 404. Every change
is an audit event targeting the record (`course.chapter_changed`, `course.revision_changed`, `_submitted`,
`_approved`, `_needs_changes`, `_scheduled`, `_published`, `_unpublished`, `course.clip_changed`,
`course.card_changed`, `course.item_changed`, `course.moved`, `course.deleted`, `course.restored`, `course.purged`,
`course.clip_retried`, `course.item_flagged`, `course.entitlement_granted`, `_extended`, `_revoked`,
`course.batch_requested`, `course.codes_made`, `course.batch_dispatched`, `course.batch_voided`,
`course.code_voided`, `course.code_lookup`, `course.device_signed_out`). A book code is never kept nor logged: it is
read by its digest and named in the audit trail by its keyed hash (`code_hash`). A search by email is a
`customer.lookup` event with the query's keyed hash; a learner's page, and a code's redeemer shown by the lookup, are
`sensitive_read` events (`child: true` for a minor). A refusal is `400` in words, on its field or in
`non_field_errors`.

| Method | Path (under `/api/v1/staff/course/`) | Permission | What |
|---|---|---|---|
| GET | `subjects/` | `learn.view_chapter` | the subjects with chapters, each counted: `chapters`, `published`, `in_review`, `scheduled`, `clips`, `failed`, `cards`, `items`, `bin` |
| GET | `subjects/<id>/outline/` | `learn.view_chapter` | its chapters by number, each with `must_do`, its `revision` (`status`, `target_minutes`, the `minutes` of its ready clips, `publish_at`, its clips in order with `processing`, `reason` in words and `free`), its `cards` and `items` in order (`flagged`: the item's open report in the content triage); `completion_rule`, `free_preview` |
| PATCH | `chapters/<id>/` (`must_do`) | `learn.change_chapter` | the chapter's must-do note (Markdown) |
| GET PATCH | `revisions/<id>/` (`title`, `target_minutes` 1 to 60) | `learn.view_revision`; PATCH `learn.change_revision` | a revision with its chapter, `status`, `submitted_by`, `reviewer`, `publish_at`, `minutes`, its `clips`, the `cards` and `items` that go live with it, and `transitions`: the moves the reader may make now |
| POST | `revisions/<id>/submit/` | `learn.change_revision` | a draft sent to review: an inbox item (kind `review`) for the subject's reviewers |
| POST | `revisions/<id>/approve/` `{"comment"}`, `…/needs-changes/` `{"comment"}`, `…/publish/` `{"publish_at"}`, `…/unpublish/` | `staff.publish_course` | approved; sent back to draft (the comment required: an inbox item for whoever submitted it); published now (a ready clip needed) or at `publish_at` (to come, within a year: approved, and published by the five-minute task); back to draft. Never by whoever submitted it: `403 {"code": "own_edit"}` |
| GET PATCH DELETE | `clips/<id>/`, `cards/<id>/`, `items/<id>/` | `learn.view_`, `change_`, `delete_` + `clip`, `flashcard`, `quizitem` | one row (a binned one too, with `bin_until`). PATCH its fields, as the admin's form checks them: a clip's `title`, `kind`, `notes`, `is_free_preview`, `tags`; a card's `front`, `back`, `tags`; an item's `kind`, `text`, `options`, `answer`, `explanation`, `topic`, `marks`, `difficulty`, `bloom`, `tags`. DELETE puts it in the bin (200, its row of the bin): the app and the website stop showing it at once |
| POST | `<clips|cards|items>/<id>/move/` `{"to": "first" | "last" | "before" | "after", "target": <id>}` | the row's `change_` | the row moved among its siblings (a revision's clips, a chapter's cards or items), their `order` written again densely in one transaction: the keyboard's path for every drag |
| POST | `<clips|cards|items>/<id>/restore/` | the row's `change_` | out of the bin within 30 days, back at its place among its siblings |
| POST | `clips/<id>/retry/` | `learn.change_clip` | a failed clip, or one processing for over an hour, processed again from its uploaded video |
| GET | `bin/?kind=clips|cards|items` | the kind's `view_` | the bin, newest first: `title`, `chapter`, `deleted_at`, `bin_until` (then the nightly purge deletes the row and a clip's files) |
| GET | `items/` (`?subject=&chapter=&kind=&marks=&topic=&tag=&source=book|app&difficulty=&bloom=` (`none`: not set) `&flags=any|low_discrimination|too_easy|too_hard|distractor&n_too_small=&flagged=&q=`) | `learn.view_quizitem` | the quiz bank by subject, chapter and order: each item's metadata, `source` (the book question it came from) and `stats` from the nightly item analysis (`n`, `p`, `discrimination`, `flags`, `computed_at`; `n_too_small` under 30 learners: N/A) |
| GET | `items/<id>/history/` | `learn.view_quizitem` | its versions, newest first, each with `changes` (`field`, `before`, `after`) |
| POST | `items/<id>/flag/` `{"note"}` | `staff.triage_report` | "needs checking": a report of category `item_analysis` in the content triage (201), or the one open already (200, `created: false`) |
| GET POST | `entitlements/` (`?subject=PHY|ALL&source=&state=active|ended|revoked&user=&q=`), `entitlements/<id>/` | `learn.view_entitlement`; POST `learn.add_entitlement` | access: `user` (`id`, `name`, the email masked, `is_minor`), `subject`, `source`, `valid_until`, `state`, `can_extend`, `can_revoke`; one adds `history`. `q` is an account's whole email address (a `customer.lookup`; throttled as `staff_search`). POST `{"user", "subject", "valid_until", "reason", "reference"}` grants; a closed or staff account, a day gone or more than two years ahead, or open access that covers it already is refused |
| POST | `entitlements/<id>/extend/` `{"days", "reason"}`, `…/revoke/` `{"reason"}` | `learn.change_entitlement` | 1 to 365 days from its end (or today); access ending yesterday, `revoked_at` set. Progress is never touched: access given again finds it |
| GET POST | `codes/batches/` (`?subject=PHY|ALL&state=generating|failed|ready|dispatched|void&q=`), `codes/batches/<key>/` | `learn.view_codebatch`; POST `staff.make_book_codes` | print runs (`key`: the label, or `~` and the id for a label from before the panel): `printed`, `codes`, `redeemed`, `void`, `state`, `product`, `job`; one adds `redeemed_by_week`, `signals` (its fraud signals), `activation_rate`, `file_until` and `generation` (the job: its `result_url` for its starter until the file goes). POST `{"label", "subject", "count", "product": "<slug>", "note"}`: 202 `{"batch", "job"}` |
| POST | `codes/batches/<key>/dispatched/` `{"at"}` | `learn.change_codebatch` | the books left (once, once its codes are made; `at` empty: now) |
| POST | `codes/batches/<key>/void/` `{"reason"}` | `staff.void_book_codes` | every unused code of the run voided (`{"batch", "voided"}`), its printer's file deleted, the owners told |
| POST | `codes/void/` `{"code", "reason"}` | `staff.void_book_codes` | one unused code voided (a redeemed one refused: revoke its access instead) |
| POST | `codes/lookup/` `{"code"}` | `learn.view_bookcode` (`STAFF_THROTTLE_CODE_LOOKUP`, 120 an hour) | the code in one `line`: `state` (unknown, unused, redeemed, void), `batch`, `batch_state`, `subject`, `redeemed_at`, `redeemed_by` (`id`, the email masked, `is_minor`), `voided_at` |
| GET | `codes/report/` | `learn.view_codebatch` | per print run: `printed`, `sold` (its book's copies sold online), `activated`, `revoked`, `void`, `activation_rate`, `districts` (each under `min_cell`, 10, hidden: `hidden: true`, no number); `totals`; `definitions` of each number |
| GET | `learners/<user>/` | `learn.view_entitlement` (the account within `accounts.view_user`'s reach; a staff account is a 404) | one learner's course: `logged: true`, `summary_only` (a child, or an unknown age: counts and `last_active_week` only, never a time), `summary`, `entitlements`, `codes` (null without `learn.view_bookcode`), `devices`, `chapters` (progress, quiz answers and accuracy, card reviews), `tickets` (null without `support.view_ticket`) |
| POST | `learners/<user>/devices/<id>/sign-out/` | `staff.end_user_sessions` | a phone taken off the account (204): no reminder reaches it until the app registers it again |

No endpoint lists learners or orders them by a score: a learner is reached one at a time, from a ticket, an access row
or a code.

The jobs: a print run's codes are made by `POST course/codes/batches/` as a staff job of kind `code_batch`
(`staff.make_book_codes`, high, the owners alerted): the codes' digests kept and the codes written once into the
printer's file (CSV: `code`, `batch`, `subject`), its starter's to download for 24 hours, then deleted by the hourly
purge; a run whose job failed is made again by `POST /api/v1/staff/jobs/` `{"kind": "code_batch", "params":
{"batch": <id>}}`. The bulk actions are `bulk_action` jobs naming `item_metadata` (`{"topic", "marks", "difficulty",
"bloom", "tags_add", "tags_remove"}`, the fields to change only), `entitlement.grant` (targets: account ids; `{"subject",
"valid_until", "reference"}`), `entitlement.extend` (`{"days"}`) or `entitlement.revoke`, a dry run first; above the
starter's `bulk_rows` the job waits for an approver.

```sh
curl -X POST https://admin.examleaf.in/api/v1/staff/course/codes/lookup/ -b "sessionid=...; csrftoken=..." \
  -H "X-CSRFToken: ..." -H "Content-Type: application/json" -d '{"code": "7kqm 3xpa 9trw"}'
# 200 {"state": "redeemed", "line": "Redeemed on 20 Sep 2026 by account #7101: batch PHY-2027-1 (Physics).",
#      "batch": "PHY-2027-1", "batch_state": "dispatched", "subject": "Physics", "redeemed_at": "...",
#      "redeemed_by": {"id": 7101, "email": "ri•••@example.com", "is_minor": true}, "voided_at": null}
curl -X POST https://admin.examleaf.in/api/v1/staff/course/clips/506/move/ -b "sessionid=...; csrftoken=..." \
  -H "X-CSRFToken: ..." -H "Content-Type: application/json" -d '{"to": "before", "target": 504}'
# 200 {"id": 506, "order": 1, ...}
```

The tasks: `learn.tasks.publish_due` (every 5 minutes) publishes the approved revisions whose time has come (one with
no ready clip waits, an inbox item says so); `learn.tasks.purge_bin` (04:30) deletes the rows 30 days in the bin and a
clip's video and HLS files with them; `learn.tasks.purge_code_files` (hourly) deletes the printers' files after 24
hours; `insights.tasks.code_fraud_rules` (hourly) runs the book codes' fraud rules (failed codes per account, address
and device, a spike, resale, a shared photo, a run redeemed before it was dispatched), each signal an inbox item of
kind `fraud_signal` and the urgent ones emailed to `INSIGHTS_ALERT_EMAILS` within the hour.
## Customers (staff)

`/api/v1/staff/users/…` (code: `staff/customers_api.py` for the endpoints, `staff/customers.py` for the rules; the
app: [staff/README.md](staff/README.md) "Phase B: customers") is the Customers module's API: the list with its tabs and
badges, a customer's record with its merged timeline and what they bought, the students under 18 waiting for a parent,
a parent's consent recorded by hand, and bulk actions on accounts. It adds to `UserViewSet` of the [Staff API](#staff-api)
(the reveal with a reason, suspend, unlock, the password reset, impersonation: all as they were) and keeps every rule of
it: the admin host only, a member of staff with a second factor (an API key reads only), each action's catalogued
permission (area "Customers"), every refusal an `authz_fail` event, cursor pages, `Cache-Control: no-store`; the schema
tags it `customers (staff)`. A customer outside the reader's scope is a 404.

What a read leaves in the log: opening a record (`users/<id>/`), its timeline and its commerce summary are each one
`sensitive_read` event (`details.what`: `record`, `timeline`, `commerce`; `details.child`: true for a student under 18).
A search for a person (`users/?q=`: an email address, a mobile number or its last digits, three letters of a name) is
one `customer.lookup` event with the query's keyed hash and the number found (`kind`, `found`, `list`), never the words;
less than that finds nobody and is no lookup, and browsing the tabs is none. Test-mode orders are in no row and no number
on a live site. No lifetime-value forecast, RFM group or churn score exists for anyone.

| Method | Path (under `/api/v1/staff/`) | Permission | What |
|---|---|---|---|
| GET | `users/` (`?kind=students\|parents\|guests&q=&class_level=&board=&is_active=`) | `accounts.view_user` | the customers, newest first, each with the badges: `email_verified`, `login_phone_verified`, `age_band` (`under_13`, `13_17`, `adult`, `unknown`), `consent` and `consent_method` (`declared`, `email_link`, `sms_link`, `adult_account`, `digilocker`, `staff_manual`), `teacher`, `mfa_on`, `status`, `locked`. `kind`: students (a class level, or under 18), parents (adult accounts a student named as their parent's contact by a verified email address or log-in number: not proof of parenthood), guests (see below) |
| GET | `users/?kind=guests` (`&q=`) | `accounts.view_user`; the rows are orders: `shop.view_order` | buyers without an account, one row for each email address (lower case): `id` (their newest order's), `name`, masked `email` and `phone`, `orders` (how many), `last_order` (its number), `last_order_at`; another row shape, still masked and paged |
| GET | `users/<id>/` | `accounts.view_user` | the record: the badges and the detail (`roles`, `mfa`, masked `parent_contact`, latest `orders`, `consents` with `purpose`, `channel`, `evidence_ref`, `verified_by`, `sessions`, `deletion_due_at`), `parent_link` (a student under 18's consent link: `sent`, `last_at`, `expires_at`, `expired`, `today`, `daily_limit`) and `linked` (a student's parent account, an adult's students: `{id, full_name, relation}`) |
| GET | `users/<id>/timeline/` (`?kind=order,ticket&before=`) | `accounts.view_user` (each part by its own records' view permission) | one list of what happened to the account, newest first: `{child, rows: [{at, kind, label, href}], next_before, withheld}`; 200 rows at most, `?before=` (the last answer's `next_before`) for the older ones; `kind` narrows it (400 for an unknown one) |
| GET | `users/<id>/commerce/` | `shop.view_order` | what they bought: `orders`, `kept`, `cancelled`, `returns`, `rtos`, and for an adult `spent`, `refunded`, `lifetime_value` (spent less refunded: a record, no forecast), `average_order`, `first_order_at`, `last_order_at`, up to ten saved `addresses` (masked) and the orders' `tags`; a student under 18 (`child` true): the counts only, the rest null |
| GET | `users/consent-pending/` | `accounts.view_user` | the students under 18 waiting for a parent, the first registered first: `parent_contact` (masked) and `parent_channel` (`email`, `sms`), `links_sent`, `last_link_at`, `link_expires_at` (the last link works 7 days), `link_expired`, `links_today` of `daily_limit` (3 to one address or number), `blocking` (the account only reads until the parent confirms), `email_verified` (their own) |
| POST | `users/<id>/consent/verify/` (`method`, `evidence_ref`, `reason`) | `staff.verify_consent` (high; re-authenticated) | a parent's consent recorded by hand: `method` `staff_manual`, `adult_account` or `digilocker`; `evidence_ref` says where the evidence is (a ticket's number, a letter's date; an email address or a number is refused: never the document, never a contact); 201 the consent's record; the account's flag clears and the parent is told by email. 400 for an adult, an erased account, a student whose deletion waits for the parent, a consent already confirmed |
| POST | `users/<id>/resend-verification/` | `staff.resend_verification` | the parent's link again while consent is pending: 429 beyond 3 a day to one address or number, 400 for a text outside 08:00 to 21:00 India time (an email goes at any hour) |
| POST | `jobs/` `{"kind": "bulk_action", "params": {"action": "user.suspend", "targets": ["7101", ...], "payload": {}, "reason": "…"}, "dry_run": true}` | the action's: `staff.suspend_user` for `user.suspend` and `user.unsuspend`, `staff.end_user_sessions` for `user.end_sessions`, `staff.resend_verification` for `user.resend_consent` | a bulk action on accounts, by their ids (never a deletion): see below |

```sh
curl "https://admin.examleaf.in/api/v1/staff/users/?kind=students&q=baruah" -b "sessionid=..."
# 200 {"next": null, "previous": null, "results": [{"id": 7104, "email": "ar•••@example.com", "phone": "", "full_name":
#      "Arjun Baruah", "class_level": 12, "board": "ASSEB", "under_18": true, "status": "active", "consent": "pending",
#      "email_verified": true, "login_phone_verified": false, "age_band": "13_17", "consent_method": "",
#      "teacher": "none", "mfa_on": false, "locked": false, ...}]}
curl "https://admin.examleaf.in/api/v1/staff/users/7104/timeline/?kind=sms,consent" -b "sessionid=..."
# 200 {"child": true, "rows": [{"at": "2026-10-08T10:00:00+05:30", "kind": "sms", "label": "SMS (parent consent): Sent,
#      Delivered", "href": null}, ...], "next_before": null, "withheld": []}
curl -X POST https://admin.examleaf.in/api/v1/staff/users/7104/consent/verify/ \
  -b "sessionid=...; csrftoken=..." -H "X-CSRFToken: ..." -H "Content-Type: application/json" \
  -d '{"method": "staff_manual", "evidence_ref": "Ticket 4416", "reason": "Her mother called and showed her account."}'
# 201 {"id": 88, "event": "given", "method": "staff_manual", "by_parent": true, "verified_at": "...", "verified_by": 9003,
#      "evidence_ref": "Ticket 4416", "notice_version": "2026-10-01", "created": "..."}
# 400 {"evidence_ref": ["Say where the evidence is (a ticket's number, a letter's date), not a contact's details."]}
```

**The timeline's parts** are `order`, `payment`, `refund`, `code` (book codes redeemed), `access` (course access
opened), `course`, `ticket`, `sms` (the account's `SmsLog`), `email` (the order emails), `consent`, `note` and `staff`
(the audit log's events about the account). Each is shown to a reader who may see its records (`shop.view_order`,
`shop.view_payment`, `shop.view_refund`, `learn.view_bookcode`, `learn.view_entitlement`, `support.view_ticket`,
`ops.view_smslog`, `accounts.view_consentrecord`, `staff.view_note`, `staff.view_auditlog`) and the rest are named in
`withheld`; reading the `staff` part is itself an `audit.read` event. A row's `label` is numbers and codes in words
(never an address or a number) and its `href` the console's page for the thing (`/orders/EL-…/`, `/support/tickets/SR-…/`,
`/course/learners/<id>/`). For a student under 18 the course is one row in counts (the chapters opened and the week they
were last active): never a trail of what they watched or answered; an adult's adds the clips completed by week.

**Bulk actions on accounts** are `bulk_action` jobs ([Staff API](#staff-api) "Background jobs"): `user.suspend`,
`user.unsuspend`, `user.end_sessions` and `user.resend_consent`, `targets` the accounts' ids as text or numbers, no
`payload`, a `reason` (saved with each account's event). `dry_run: true` validates every row and changes nothing: the
job's `result` is `{"outcomes": {"valid": 12, "refused": 1}, "waiting": [], "minors": 3, "approval": "…" or null}` and its
`errors` list each refused row with the reason (no such customer, already suspended, no consent pending …). `minors`
counts the students under 18 among the targets and `approval` says, in words, whether the real run will wait for an
approver: above your `bulk_rows`, and whatever the count when a student under 18's account is among them. The run then
answers 202 with the job waiting on its change request (`change_request_id`, checker `staff.approve_export`). Each row is
its own audit event (`user.suspended`, `user.unsuspended`, `user.sessions_ended`, `user.verification_resent`) with you as
the actor, and the batch's `job.*` events name the action.

**Left out:** `users/<id>/change-email/`. allauth's code-by-email verification keeps its state in the session of the
request that started it, so a change started by staff cannot be completed by the customer, and staff alone must never
complete one; it is no thin wrapper over the existing flows. A customer changes their address on their account page.

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
  403 `permission_denied`, `reauthentication_required`, `break_glass_reason_required`, `passkey_required`,
  `mfa_setup_required`, `impersonating`, `link_expired` (a job's file); 404 `not_found` (also every path on a host other than the admin
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
- **Jobs** (`jobs/`) run in the background and are followed through `jobs/<id>/`: `state`, `done` of `total`, the rows'
  `errors`, `result` and `result_url`, a link signed for 5 minutes. The kinds: `audit_export` (below), `bulk_action`
  (`params.action` one of the change requests' actions or of the customers' and the course's account actions:
  [Customers (staff)](#customers-staff), [Course (staff)](#course-staff)), `erp_initial_load` ([ERPNext sync
  (staff)](#erpnext-sync-staff)), `gstr1_export` ([Tax (staff)](#tax-staff)), `orders_pack`, `orders_print`,
  `orders_cancel` and `orders_export` ([Orders (staff)](#orders-staff)), `content_import` ([Content
  (staff)](#content-staff)), `grievance_export` ([Support (staff)](#support-staff)), `settlement_fetch` ([Finance
  (staff)](#finance-staff)), `report_export` ([Home and reports (staff)](#home-and-reports-staff)), `coupon_codes`,
  `product_import` and `product_export` ([Catalogue (staff)](#catalogue-staff)) and `code_batch` ([Course
  (staff)](#course-staff)). Each kind asks for its own permission, and above the starter's `export_rows` or
  `bulk_rows` a change request (`job.run`) waits for an approver first.
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
| POST | `change-requests/` (`action`, `target`, `payload`, `reason`) | `staff.add_changerequest` and the action's own | ask: `order.refund`, `order.offline_payment`, `product.price`, `coupon.create`, `coupon.change`, `offer.create`, `offer.change` |
| POST | `change-requests/<id>/approve/` (`payload_sha256`, `comment`, `override`), `…/reject/` (`comment`) | the action's checker (re-authenticated): FINANCE for money, ADMIN for roles, staff second factors, erasures and exports, the owners for any | approve the payload you read (its hash); reject, or withdraw your own |
| POST | `change-requests/<id>/execute/` | its maker or a checker (re-authenticated) | run the stored payload, once |
| GET POST PATCH DELETE | `saved-views/` (`?list_key=`), `saved-views/<id>/` | `staff.view_savedview`, `add_`, `change_`, `delete_` | your saved lists' filters, columns and sort; `role` shares one with a role you hold |
| GET | `settings/`, `settings/<key>/` | `staff.view_sitesetting` | the site's switches: in effect, the environment's, where from, changes to come; one switch's history |
| PUT | `settings/<key>/` (`value`, `reason`, `effective_from`) | `staff.manage_settings`; `MAINTENANCE_*`: `staff.toggle_maintenance` | `SHOP_OPEN`, `SHOP_COD_ENABLED`, `PARENTAL_CONSENT_MODE`, `WEB_COURSE`, `MAINTENANCE_MODE`, `MAINTENANCE_BANNER`; null: back to the environment's |
| GET | `flags/`, `flags/<KEY>/` | `staff.view_featureflag` | the feature flags; one flag's history |
| PUT | `flags/<KEY>/` (`value`, `reason`, `effective_from`) | `staff.manage_flags` | switch one (null: off; a known switch, the ERP ones: back to the environment's, and true or false only) |
| GET | `settings/<key>/history/`, `flags/<KEY>/history/` | `staff.view_sitesetting`, `staff.view_featureflag` | every value it was given, newest first: who, when, why, from when |
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
| GET | `people/roles/` (`?language=en`) | `staff.view_staff` | the role catalogue: each role's card (`for`, `cannot`), capabilities by area with their risk, limits, scopes, conflicts, ERPNext role profiles, passkey, idle limit, active members |
| GET | `people/<id>/access/` | `staff.view_staff` | the Access tab: roles with who gave them, when, why, until when (`source` admin: given in the Django admin), scopes, limits, idle limit, every permission by area with `last_used` for the high and critical ones (a year of the audit log), open change requests about or by them, second factors, `passkey_required`, ERPNext profiles |
| POST | `people/<id>/roles/preview/` (`role`, `action` grant or revoke) | `staff.view_staff` | what it would change, nothing changed: `gains`, `losses` (by area), `limits`, `scopes`, `idle_timeout_s`, `conflicts` and `blocked` (SSD), `needs_approval`, `rule`, `checker`, `passkey_needed`, `erp_profiles` before and after |
| GET | `people/<id>/offboarding/` | `staff.view_staffoffboarding` | their latest offboarding's checklist: each step's `kind` (auto: done by the panel; manual: ticked by hand), `state` (done, todo, not_needed), `detail`, `done_at`, `done_by`; 404 never offboarded |
| POST | `people/<id>/offboarding/tick/` (`step`, `state`, `note`) | `staff.assign_role` (OWNER, re-authenticated) | a manual step ticked (a panel's step: 400); the last one finishes it and its inbox item |
| GET | `people/<id>/erp/` | `staff.view_staff` | the ERPNext user they should have from their roles: `role_profiles`, `by_role`, `enabled`, `erp_in_use` (applied by hand in ERPNext) |
| GET | `people/me/sessions/` | any member of staff | your own sessions (the website's too): `browser`, `system`, `place` (the address cut short), `created_at`, `last_seen_at`, `current` |
| POST | `people/me/sessions/<id>/end/`, `people/me/sessions/end-others/` | any member of staff | 204: one other session ended (this one: 400, sign out instead); every other one and the app's refresh tokens: `{"sessions", "tokens"}` |
| POST | `invites/accept/` (`token`; signed out also `full_name`, `password`) | the invitation's token | the one endpoint for people not yet staff |
| GET | `users/` (`?kind=&q=&class_level=&board=&is_active=`), `users/<id>/` | `accounts.view_user` | customers with their badges, contacts masked; opening one is logged; the rest of the module: [Customers (staff)](#customers-staff) |
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
| GET | `system/sync/`, `system/sync/links/?q=` | `erp.view_sync` | the sync monitor: the outbox per flow and state with each switch, the newest dead letters, ERPNext's calls back of 7 days, the last week's reconciliations; a link found by reference, ERPNext name or id (3 characters at least) |
| GET | `system/backups/` | `staff.view_system` | each source's newest backup in the bucket (`name`, `at`, `size`, `sha256`, `encrypted`), `stale` past `BACKUP_STALE_HOURS`, the retention, `last_proven`, the drills |
| GET POST | `system/backups/drills/` (`performed_on`, `engine`, `backup`, `result`, `duration_minutes`, `notes`) | `staff.view_restoredrill`; POST `staff.manage_system` (high) | the restore drills; one recorded |
| GET | `system/logs/` | `staff.view_system` | the log inventory with `meets_retention`, the retention in force, the clock against the database's (`LOG_TIME_SOURCE`), the CERT-In contact |
| GET | `system/dependencies/` | `staff.view_system` | CI's last pip-audit and npm audit report: open `advisories` by severity, a critical one's 7-day `due`, `stale` past 8 days, the versions |
| GET | `system/hardening/` | `staff.view_system` | the admin host's checks, each `ok` (null: not testable here), `detail` and `fix` |
| GET | `system/scripts/` | `staff.view_scriptinventory` | the checkout's and the console's sign-in's scripts: each page's last check and the scripts seen (src or inline, SHA-256, first and last seen, `current`) |

**The manifest** (`session/`, `Cache-Control: no-store`). Keep it in memory, never in `localStorage`; fetch it again after
any 403 and whenever `manifest_version` changes. `user.is_superuser` true is a break-glass account (no roles, every
permission, no limits, the shortest idle limit; every event of its session is marked): show it a banner.
`break_glass` is null for everyone else; for a break-glass session `{"reason_required", "reason", "ends_at"}`: while
`reason_required` is true ask why and `POST session/reason/` `{"reason": "…"}` (10 to 500 characters, once: the
answer is the same object), before which every other staff call answers `403 {"code": "break_glass_reason_required"}`
(the manifest and `catalogue/` excepted); `ends_at` is its log-in plus 2 hours (`STAFF_BREAK_GLASS_HOURS`), the end
however busy. `policies_due` lists the policies' versions (`STAFF_POLICIES`) the person has not acknowledged,
`[{"policy": "acceptable_use", "version": "2026-10"}]`: show them, and `POST policies/ack/` `{"policy", "version"}`
each once read (research 6: before the rest of the panel). `steps` lists what the session must do first:
`["passkey_required"]` for a member of `STAFF_PASSKEY_ROLES` (OWNER, ADMIN, FINANCE) without a passkey or security
key, who adds one on the website's `/account/security/`; meanwhile every staff call but the manifest, `catalogue/` and
their own sessions answers `403 {"code": "passkey_required"}` (the Django admin sends them there too). `offer_end_sessions`
is true once after a second factor was added, removed or reset (on the website): offer `POST people/me/sessions/end-others/`.

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
`declared`, `pending` (a parent's link awaited) or `verified`; the detail adds `mfa`, the masked `parent_contact`, the
latest orders, consents and devices. The list's tabs, the badges, the timeline, the spending summary, the children
waiting for a parent, a parent's consent recorded by hand and the bulk actions are in [Customers
(staff)](#customers-staff).

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
| GET | `staff/catalogue/categories/` | `shop.view_category` |  |  | 200 `[CatalogueCategory]` |
| POST | `staff/catalogue/categories/` | `shop.add_category` |  | `CatalogueCategoryWriteRequest` | 201 `CatalogueCategory` |
| GET | `staff/catalogue/categories/{slug}/` | `shop.view_category` |  |  | 200 `CatalogueCategory` |
| PATCH | `staff/catalogue/categories/{slug}/` | `shop.change_category` |  | `PatchedCatalogueCategoryWriteRequest` | 200 `CatalogueCategory` |
| POST | `staff/catalogue/categories/{slug}/move/` | `shop.change_category` |  | `CatalogueCategoryMoveRequest` | 200 `[CatalogueCategory]` |
| GET | `staff/catalogue/collections/` | `shop.view_collection` | `cursor`, `page_size` |  | 200 `PaginatedCatalogueCollectionList` |
| POST | `staff/catalogue/collections/` | `shop.add_collection` |  | `CatalogueCollectionWriteRequest` | 201 `CatalogueCollection` |
| GET | `staff/catalogue/collections/{slug}/` | `shop.view_collection` |  |  | 200 `CatalogueCollection` |
| PATCH | `staff/catalogue/collections/{slug}/` | `shop.change_collection` |  | `PatchedCatalogueCollectionWriteRequest` | 200 `CatalogueCollection` |
| GET | `staff/catalogue/coupons/` | `shop.view_coupon` | `cursor`, `kind`, `page_size`, `q`, `single_use`, `state` |  | 200 `PaginatedCatalogueCouponList` |
| POST | `staff/catalogue/coupons/` | `shop.add_coupon` |  | `CatalogueCouponWriteRequest` | 201 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/catalogue/coupons/{code}/` | `shop.view_coupon` |  |  | 200 `CatalogueCoupon` |
| PATCH | `staff/catalogue/coupons/{code}/` | `shop.change_coupon` |  | `PatchedCatalogueCouponWriteRequest` | 200 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/catalogue/coupons/{code}/codes/` | `shop.view_couponcode` | `cursor`, `job`, `used` |  | 200 `CatalogueCodePage` |
| GET | `staff/catalogue/coupons/{code}/history/` | `shop.view_coupon` | `cursor`, `page_size` |  | 200 `CatalogueVersionPage` |
| POST | `staff/catalogue/import/` | `shop.import_product` |  | `CatalogueImportUploadRequest` | 202 `Job` |
| GET | `staff/catalogue/offers/` | `shop.view_offer` | `combinable`, `cursor`, `page_size`, `q`, `scope`, `state` |  | 200 `PaginatedCatalogueOfferList` |
| POST | `staff/catalogue/offers/` | `shop.add_offer` |  | `CatalogueOfferWriteRequest` | 201 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/catalogue/offers/{id}/` | `shop.view_offer` |  |  | 200 `CatalogueOffer` |
| PATCH | `staff/catalogue/offers/{id}/` | `shop.change_offer` |  | `PatchedCatalogueOfferWriteRequest` | 200 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/catalogue/offers/{id}/history/` | `shop.view_offer` | `cursor`, `page_size` |  | 200 `CatalogueVersionPage` |
| GET | `staff/catalogue/options/` | `shop.view_product` |  |  | 200 `CatalogueOptions` |
| GET | `staff/catalogue/product-types/` | `shop.view_producttype` |  |  | 200 `[CatalogueProductType]` |
| POST | `staff/catalogue/product-types/` | `shop.add_producttype` |  | `CatalogueTypeNameRequest` | 201 `CatalogueProductType` |
| GET | `staff/catalogue/product-types/{id}/` | `shop.view_producttype` |  |  | 200 `CatalogueProductType` |
| PATCH | `staff/catalogue/product-types/{id}/` | `shop.change_producttype` |  | `PatchedCatalogueTypeRenameRequest` | 200 `CatalogueProductType` |
| POST | `staff/catalogue/product-types/{id}/attributes/` | `shop.add_attribute` |  | `CatalogueAttributeDefRequest` | 201 `CatalogueProductType` |
| PATCH | `staff/catalogue/product-types/{id}/attributes/{attribute}/` | `shop.change_attribute` |  | `PatchedCatalogueAttributeDefRequest` | 200 `CatalogueProductType` |
| GET | `staff/catalogue/products/` | `shop.view_product` | `category`, `collection`, `cursor`, `incomplete`, `kind`, `page_size`, `published`, `q`, `stock`, `tax_problem` |  | 200 `PaginatedCatalogueProductRowList` |
| POST | `staff/catalogue/products/` | `shop.add_product` |  | `CatalogueProductWriteRequest` | 201 `CatalogueProductMade` |
| GET | `staff/catalogue/products/{slug}/` | `shop.view_product` |  |  | 200 `CatalogueProduct` |
| PATCH | `staff/catalogue/products/{slug}/` | `shop.change_product` (by the key or the body: see the table above) |  | `PatchedCatalogueProductWriteRequest` | 200 `CatalogueProduct`; 202 `CatalogueProductPriceWaiting` |
| GET | `staff/catalogue/products/{slug}/barcode.svg/` | `shop.view_product` |  |  | 200 `image/svg+xml` |
| PUT | `staff/catalogue/products/{slug}/bundle/` | `shop.change_product` |  | `CatalogueBundleLinesRequest` | 200 `CatalogueProduct` |
| GET | `staff/catalogue/products/{slug}/history/` | `shop.view_product` | `cursor`, `page_size` |  | 200 `CatalogueVersionPage` |
| POST | `staff/catalogue/products/{slug}/pictures/` | `shop.add_productimage` |  | `CataloguePictureUploadRequest` | 201 `CatalogueProduct` |
| PATCH | `staff/catalogue/products/{slug}/pictures/{picture}/` | `shop.change_productimage` (by the key or the body: see the table above) |  | `PatchedCataloguePictureChangeRequest` | 200 `CatalogueProduct`; 204 |
| DELETE | `staff/catalogue/products/{slug}/pictures/{picture}/` | `shop.delete_productimage` (by the key or the body: see the table above) |  |  | 200 `CatalogueProduct`; 204 |
| GET | `staff/catalogue/products/{slug}/prior-price/` | `shop.view_product` | `price` |  | 200 `CataloguePriorPrice` |
| POST | `staff/catalogue/products/{slug}/stock/` | `staff.set_stock` |  | `CatalogueStockSetRequest` | 200 `CatalogueProduct` |
| GET | `staff/catalogue/shipping-rates/` | `shop.view_shippingrate` | `cursor`, `page_size` |  | 200 `PaginatedCatalogueShippingRateList` |
| POST | `staff/catalogue/shipping-rates/` | `shop.add_shippingrate` |  | `CatalogueShippingRateWriteRequest` | 201 `CatalogueShippingRate` |
| GET | `staff/catalogue/shipping-rates/{id}/` | `shop.view_shippingrate` |  |  | 200 `CatalogueShippingRate` |
| PATCH | `staff/catalogue/shipping-rates/{id}/` | `shop.change_shippingrate` |  | `PatchedCatalogueShippingRateWriteRequest` | 200 `CatalogueShippingRate` |
| GET | `staff/catalogue/shipping-rates/{id}/history/` | `shop.view_shippingrate` | `cursor`, `page_size` |  | 200 `CatalogueVersionPage` |
| GET | `staff/catalogue/stock-alerts/` | `shop.view_stockalert` | `cursor`, `page_size` |  | 200 `PaginatedCatalogueAlertRowList` |
| GET | `staff/catalogue/stock/` | `shop.view_product` | `cursor`, `page_size`, `published`, `q`, `state` |  | 200 `PaginatedCatalogueStockRowList` |
| GET | `staff/catalogue/summary/` | `shop.view_product` |  |  | 200 `CatalogueSummary` |
| GET | `staff/change-requests/` | `staff.view_changerequest` | `action`, `awaiting`, `cursor`, `mine`, `page_size`, `status` |  | 200 `PaginatedChangeRequestList` |
| POST | `staff/change-requests/` | `staff.add_changerequest` |  | `AskRequest` | 200 `ChangeRequest`; 201 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/change-requests/{id}/` | `staff.view_changerequest` |  |  | 200 `ChangeRequest` |
| POST | `staff/change-requests/{id}/approve/` | `staff.view_changerequest` |  | `ApproveRequest` | 200 `ChangeRequest` |
| POST | `staff/change-requests/{id}/execute/` | `staff.view_changerequest` |  |  | 200 `ChangeRequest`; 400 `ChangeRequest` |
| POST | `staff/change-requests/{id}/reject/` | `staff.view_changerequest` |  | `CommentRequest` | 200 `ChangeRequest` |
| GET | `staff/connections/` | `integrations.view_integrationaccount` |  |  | 200 `[ConnectionCard]` |
| GET | `staff/connections/{provider}/` | `integrations.view_integrationaccount` |  |  | 200 `ConnectionCard` |
| GET | `staff/connections/{provider}/calls/` | `integrations.view_integrationcall` | `cursor`, `failed`, `operation`, `page_size` |  | 200 `PaginatedCallList` |
| POST | `staff/connections/{provider}/circuit/` | `staff.manage_connections` |  | `CircuitActionRequest` | 200 `ConnectionCard` |
| POST | `staff/connections/{provider}/credentials/` | `staff.manage_connections` |  | `CredentialsRequest` | 200 `TestResult` |
| GET | `staff/connections/{provider}/events/` | `integrations.view_inboundevent` | `cursor`, `page_size`, `state` |  | 200 `PaginatedInboundEventList` |
| POST | `staff/connections/{provider}/events/replay-failed/` | `staff.replay_webhook` |  | `ReplayFailedRequest` | 200 `Replayed` |
| POST | `staff/connections/{provider}/events/{id}/replay/` | `staff.replay_webhook` |  |  | 200 `InboundEvent` |
| GET | `staff/connections/{provider}/failures/` | `integrations.view_integrationfailure` | `cursor`, `operation`, `page_size`, `state` |  | 200 `PaginatedFailureList` |
| POST | `staff/connections/{provider}/failures/{id}/discard/` | `staff.replay_webhook` (by the key or the body: see the table above) |  | `DiscardRequest` | 200 `Failure` |
| POST | `staff/connections/{provider}/failures/{id}/replay/` | `staff.replay_webhook` (by the key or the body: see the table above) |  |  | 200 `Failure` |
| POST | `staff/connections/{provider}/mode/` | `staff.manage_connections` |  | `ModeRequest` | 200 `ConnectionCard` |
| POST | `staff/connections/{provider}/test/` | `staff.manage_connections` |  |  | 200 `TestResult` |
| GET | `staff/connections/{provider}/webhooks/` | `integrations.view_integrationaccount` |  |  | 200 `WebhookInfo` |
| POST | `staff/connections/{provider}/webhooks/rotate/` | `staff.manage_connections` |  | `ConnectionReasonRequest` | 200 `Rotated` |
| GET | `staff/content/books/` | `content.view_book` | `board`, `class_level`, `cursor`, `format`, `page_size`, `subject` |  | 200 `PaginatedContentBookList` |
| POST | `staff/content/books/` | `content.add_book` |  | `ContentBookRequest` | 201 `ContentBookDetail` |
| GET | `staff/content/books/{id}/` | `content.view_book` |  |  | 200 `ContentBookDetail` |
| PATCH | `staff/content/books/{id}/` | `content.change_book` |  | `PatchedContentBookRequest` | 200 `ContentBookDetail` |
| GET | `staff/content/books/{id}/history/` | `content.view_book` | `cursor`, `page_size` |  | 200 `ContentVersionPage` |
| POST | `staff/content/books/{id}/history/{history_id}/restore/` | `content.change_book` |  |  | 200 `object` |
| GET | `staff/content/errata/` | `content.view_errorreport` | `book`, `cursor`, `page_size`, `printing`, `public` |  | 200 `PaginatedContentErratumList` |
| GET | `staff/content/imports/` | `content.view_paper` | `cursor`, `page_size` |  | 200 `PaginatedJobList` |
| GET | `staff/content/legal-deposits/` | `content.view_legaldeposit` | `book`, `cursor`, `library`, `page_size` |  | 200 `PaginatedLegalDepositList` |
| POST | `staff/content/legal-deposits/` | `content.add_legaldeposit` |  | `LegalDepositRequest` | 201 `LegalDeposit` |
| GET | `staff/content/legal-deposits/missing/` | `content.view_legaldeposit` |  |  | 200 `[MissingDeposit]` |
| GET | `staff/content/legal-deposits/{id}/` | `content.view_legaldeposit` |  |  | 200 `LegalDeposit` |
| GET | `staff/content/legal-deposits/{id}/proof/` | `content.view_legaldeposit` |  |  | 200 `application/octet-stream`; 302 |
| GET | `staff/content/papers/` | `content.view_paper` | `board`, `book`, `changed`, `class_level`, `cursor`, `is_published`, `page_size`, `q`, `subject`, `tier` |  | 200 `PaginatedContentPaperList` |
| GET | `staff/content/papers/{id}/` | `content.view_paper` |  |  | 200 `ContentPaperDetail` |
| PATCH | `staff/content/papers/{id}/` | `content.change_paper` |  | `PatchedContentPaperDetailRequest` | 200 `ContentPaperDetail` |
| GET | `staff/content/papers/{id}/history/` | `content.view_paper` | `cursor`, `page_size` |  | 200 `ContentVersionPage` |
| POST | `staff/content/papers/{id}/history/{history_id}/restore/` | `content.change_paper` |  |  | 200 `object` |
| POST | `staff/content/papers/{id}/publish/` | `staff.publish_paper` |  | `PaperPublishRequest` | 200 `ContentPaperDetail` |
| GET | `staff/content/papers/{id}/qr/` | `content.view_paper` | `printing` |  | 200 `PaperQr` |
| GET | `staff/content/questions/` | `content.view_question` | `book`, `changed`, `cursor`, `is_published`, `page_size`, `paper`, `q`, `state`, `subject` |  | 200 `PaginatedContentQuestionList` |
| GET | `staff/content/questions/{id}/` | `content.view_question` |  |  | 200 `ContentQuestionDetail` |
| PATCH | `staff/content/questions/{id}/` | `content.change_question` |  | `PatchedQuestionUpdateRequest` | 200 `ContentQuestionDetail` |
| POST | `staff/content/questions/{id}/discard/` | `content.change_question` |  |  | 200 `ContentQuestionDetail` |
| GET | `staff/content/questions/{id}/history/` | `content.view_question` | `cursor`, `page_size` |  | 200 `ContentVersionPage` |
| POST | `staff/content/questions/{id}/history/{history_id}/restore/` | `content.change_question` |  |  | 200 `object` |
| POST | `staff/content/questions/{id}/rollback/` | `staff.publish_paper` |  |  | 200 `ContentQuestionDetail` |
| POST | `staff/content/questions/{id}/submit/` | `content.change_question` |  | `ContentSubmitRequest` | 201 `ContentOpenReview` |
| GET | `staff/content/reports/` | `content.view_errorreport` | `book`, `category`, `cursor`, `page_size`, `paper`, `printing`, `state`, `subject`, `teacher` |  | 200 `PaginatedContentReportList` |
| GET | `staff/content/reports/{id}/` | `content.view_errorreport` |  |  | 200 `ContentReportDetail` |
| PATCH | `staff/content/reports/{id}/` | `staff.triage_report` |  | `PatchedContentReportUpdateRequest` | 200 `ContentReportDetail` |
| POST | `staff/content/reports/{id}/confirm/` | `staff.triage_report` |  | `ContentTransitionRequest` | 200 `ContentReportDetail` |
| POST | `staff/content/reports/{id}/fix-in-printing/` | `staff.triage_report` |  | `ContentTransitionRequest` | 200 `ContentReportDetail` |
| POST | `staff/content/reports/{id}/fix-online/` | `staff.triage_report` |  | `ContentTransitionRequest` | 200 `ContentReportDetail` |
| POST | `staff/content/reports/{id}/reject/` | `staff.triage_report` |  | `ContentTransitionRequest` | 200 `ContentReportDetail` |
| POST | `staff/content/reports/{id}/reopen/` | `staff.triage_report` |  | `ContentTransitionRequest` | 200 `ContentReportDetail` |
| POST | `staff/content/reports/{id}/tell/` | `staff.triage_report` |  |  | 200 `ContentReportDetail` |
| GET | `staff/content/reviews/` | `content.view_reviewtask` | `cursor`, `mine`, `open`, `page_size`, `paper`, `stage`, `state`, `subject`, `submitted` |  | 200 `PaginatedContentReviewList` |
| GET | `staff/content/reviews/{id}/` | `content.view_reviewtask` |  |  | 200 `ContentReviewDetail` |
| POST | `staff/content/reviews/{id}/approve/` | `staff.publish_paper` |  | `ContentDecisionRequest` | 200 `ContentReviewDetail` |
| POST | `staff/content/reviews/{id}/needs-changes/` | `staff.publish_paper` |  | `NeedsChangesRequest` | 200 `ContentReviewDetail` |
| POST | `staff/content/reviews/{id}/publish/` | `staff.publish_paper` |  | `ContentDecisionRequest` | 200 `ContentReviewDetail` |
| GET | `staff/content/solutions/` | `content.view_solution` | `book`, `changed`, `cursor`, `page_size`, `paper`, `state`, `subject` |  | 200 `PaginatedContentSolutionList` |
| GET | `staff/content/solutions/{id}/` | `content.view_solution` |  |  | 200 `ContentSolutionDetail` |
| PATCH | `staff/content/solutions/{id}/` | `content.change_solution` |  | `PatchedSolutionUpdateRequest` | 200 `ContentSolutionDetail` |
| POST | `staff/content/solutions/{id}/discard/` | `content.change_solution` |  |  | 200 `ContentSolutionDetail` |
| GET | `staff/content/solutions/{id}/history/` | `content.view_solution` | `cursor`, `page_size` |  | 200 `ContentVersionPage` |
| POST | `staff/content/solutions/{id}/history/{history_id}/restore/` | `content.change_solution` |  |  | 200 `object` |
| POST | `staff/content/solutions/{id}/rollback/` | `staff.publish_paper` |  |  | 200 `ContentSolutionDetail` |
| POST | `staff/content/solutions/{id}/submit/` | `content.change_solution` |  | `ContentSubmitRequest` | 201 `ContentOpenReview` |
| GET | `staff/content/summary/` | `content.view_errorreport` |  |  | 200 `ContentSummary` |
| GET | `staff/course/bin/` | `learn.view_clip` (by the key or the body: see the table above) | `cursor`, `kind`, `page_size` |  | 200 `PaginatedCourseBinRowList` |
| GET | `staff/course/cards/{id}/` | `learn.view_flashcard` |  |  | 200 `CourseCard` |
| PATCH | `staff/course/cards/{id}/` | `learn.change_flashcard` |  | `PatchedCourseCardRequest` | 200 `CourseCard` |
| DELETE | `staff/course/cards/{id}/` | `learn.delete_flashcard` |  |  | 200 `CourseBinRow` |
| POST | `staff/course/cards/{id}/move/` | `learn.change_flashcard` |  | `CourseMoveRequest` | 200 `CourseCard` |
| POST | `staff/course/cards/{id}/restore/` | `learn.change_flashcard` |  |  | 200 `CourseCard` |
| PATCH | `staff/course/chapters/{id}/` | `learn.change_chapter` |  | `PatchedCourseChapterRequest` | 200 `CourseChapter` |
| GET | `staff/course/clips/{id}/` | `learn.view_clip` |  |  | 200 `CourseClip` |
| PATCH | `staff/course/clips/{id}/` | `learn.change_clip` |  | `PatchedCourseClipRequest` | 200 `CourseClip` |
| DELETE | `staff/course/clips/{id}/` | `learn.delete_clip` |  |  | 200 `CourseBinRow` |
| POST | `staff/course/clips/{id}/move/` | `learn.change_clip` |  | `CourseMoveRequest` | 200 `CourseClip` |
| POST | `staff/course/clips/{id}/restore/` | `learn.change_clip` |  |  | 200 `CourseClip` |
| POST | `staff/course/clips/{id}/retry/` | `learn.change_clip` |  |  | 200 `CourseClip` |
| GET | `staff/course/codes/batches/` | `learn.view_codebatch` | `cursor`, `page_size`, `q`, `state`, `subject` |  | 200 `PaginatedCourseBatchList` |
| POST | `staff/course/codes/batches/` | `staff.make_book_codes` |  | `CourseBatchCreateRequest` | 202 `CourseBatchStarted` |
| GET | `staff/course/codes/batches/{label}/` | `learn.view_codebatch` |  |  | 200 `CourseBatchDetail` |
| POST | `staff/course/codes/batches/{label}/dispatched/` | `learn.change_codebatch` |  | `CourseDispatchedRequest` | 200 `CourseBatch` |
| POST | `staff/course/codes/batches/{label}/void/` | `staff.void_book_codes` |  | `CourseVoidRequest` | 200 `CourseBatchVoided` |
| POST | `staff/course/codes/lookup/` | `learn.view_bookcode` |  | `CourseCodeRequest` | 200 `CourseCodeLookup` |
| GET | `staff/course/codes/report/` | `learn.view_codebatch` |  |  | 200 `CourseReport` |
| POST | `staff/course/codes/void/` | `staff.void_book_codes` |  | `CourseCodeVoidRequest` | 200 `CourseCodeVoided` |
| GET | `staff/course/entitlements/` | `learn.view_entitlement` | `cursor`, `page_size`, `q`, `source`, `state`, `subject`, `user` |  | 200 `PaginatedCourseEntitlementList` |
| POST | `staff/course/entitlements/` | `learn.add_entitlement` |  | `CourseGrantRequest` | 201 `CourseEntitlement` |
| GET | `staff/course/entitlements/{id}/` | `learn.view_entitlement` |  |  | 200 `CourseEntitlementDetail` |
| POST | `staff/course/entitlements/{id}/extend/` | `learn.change_entitlement` |  | `CourseExtendRequest` | 200 `CourseEntitlement` |
| POST | `staff/course/entitlements/{id}/revoke/` | `learn.change_entitlement` |  | `CourseReasonRequest` | 200 `CourseEntitlement` |
| GET | `staff/course/items/` | `learn.view_quizitem` | `bloom`, `chapter`, `cursor`, `difficulty`, `flagged`, `flags`, `kind`, `marks`, `n_too_small`, `page_size`, `q`, `source`, `subject`, `tag`, `topic` |  | 200 `PaginatedCourseItemRowList` |
| GET | `staff/course/items/{id}/` | `learn.view_quizitem` |  |  | 200 `CourseItem` |
| PATCH | `staff/course/items/{id}/` | `learn.change_quizitem` |  | `PatchedCourseItemRequest` | 200 `CourseItem` |
| DELETE | `staff/course/items/{id}/` | `learn.delete_quizitem` |  |  | 200 `CourseBinRow` |
| POST | `staff/course/items/{id}/flag/` | `staff.triage_report` |  | `CourseFlagRequest` | 200 `CourseFlagAnswer`; 201 `CourseFlagAnswer` |
| GET | `staff/course/items/{id}/history/` | `learn.view_quizitem` |  |  | 200 `[CourseVersion]` |
| POST | `staff/course/items/{id}/move/` | `learn.change_quizitem` |  | `CourseMoveRequest` | 200 `CourseItem` |
| POST | `staff/course/items/{id}/restore/` | `learn.change_quizitem` |  |  | 200 `CourseItem` |
| GET | `staff/course/learners/{user}/` | `learn.view_entitlement` |  |  | 200 `CourseLearner` |
| POST | `staff/course/learners/{user}/devices/{device}/sign-out/` | `staff.end_user_sessions` |  |  | 204 |
| GET | `staff/course/revisions/{id}/` | `learn.view_revision` |  |  | 200 `CourseRevision` |
| PATCH | `staff/course/revisions/{id}/` | `learn.change_revision` |  | `PatchedCourseRevisionRequest` | 200 `CourseRevision` |
| POST | `staff/course/revisions/{id}/approve/` | `staff.publish_course` |  | `CourseCommentRequest` | 200 `CourseRevision` |
| POST | `staff/course/revisions/{id}/needs-changes/` | `staff.publish_course` |  | `CourseCommentRequest` | 200 `CourseRevision` |
| POST | `staff/course/revisions/{id}/publish/` | `staff.publish_course` |  | `CoursePublishRequest` | 200 `CourseRevision` |
| POST | `staff/course/revisions/{id}/submit/` | `learn.change_revision` |  |  | 200 `CourseRevision` |
| POST | `staff/course/revisions/{id}/unpublish/` | `staff.publish_course` |  |  | 200 `CourseRevision` |
| GET | `staff/course/subjects/` | `learn.view_chapter` |  |  | 200 `[CourseSubject]` |
| GET | `staff/course/subjects/{subject}/outline/` | `learn.view_chapter` |  |  | 200 `CourseOutline` |
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
| GET | `staff/finance/documents/{number}/erp/` | `shop.view_invoice` |  |  | 200 `FinanceDocumentErp` |
| GET | `staff/finance/offline-payments/` | `shop.view_payment` | `cursor`, `livemode`, `page_size`, `q`, `state` |  | 200 `PaginatedFinanceRequestRowList` |
| GET | `staff/finance/payment-links/` | `shop.view_payment` | `cursor`, `kind`, `livemode`, `page_size`, `q`, `state` |  | 200 `PaginatedFinanceLinkList` |
| POST | `staff/finance/payment-links/` | `shop.change_order` |  | `FinanceLinkAskRequest` | 200 `FinanceLinkAnswer`; 201 `FinanceLinkAnswer` |
| POST | `staff/finance/payment-links/invoices/{id}/posted/` | `staff.reconcile_settlements` |  | `FinanceLinkPostedRequest` | 200 `FinanceLinkAnswer` |
| POST | `staff/finance/payment-links/invoices/{id}/reconcile/` | `staff.replay_webhook` |  |  | 200 `FinanceLinkAnswer` |
| GET | `staff/finance/payments/` | `shop.view_payment` | `created_from`, `created_to`, `cursor`, `livemode`, `method`, `page_size`, `q`, `status`, `stuck` |  | 200 `PaginatedFinancePaymentList` |
| GET | `staff/finance/payments/{id}/` | `shop.view_payment` |  |  | 200 `FinancePaymentDetail` |
| POST | `staff/finance/payments/{id}/reconcile/` | `staff.replay_webhook` |  |  | 200 `FinanceReconciled` |
| GET | `staff/finance/refunds/` | `shop.view_refund` | `cursor`, `livemode`, `method`, `page_size`, `q`, `state` |  | 200 `PaginatedFinanceRequestRowList` |
| GET | `staff/finance/settlements/` | `shop.view_settlement` | `cursor`, `date_from`, `date_to`, `livemode`, `page_size`, `q`, `state` |  | 200 `PaginatedFinanceSettlementList` |
| POST | `staff/finance/settlements/fetch/` | `staff.reconcile_settlements` |  | `FinanceFetchRequest` | 202 `Job` |
| GET | `staff/finance/settlements/{id}/` | `shop.view_settlement` |  |  | 200 `FinanceSettlementDetail` |
| POST | `staff/finance/settlements/{id}/match/` | `staff.reconcile_settlements` |  | `FinanceMatchRequest` | 200 `FinanceSettlementLine` |
| GET | `staff/finance/settlements/{settlement}/lines/` | `shop.view_settlementline` | `cursor`, `matched`, `page_size`, `type` |  | 200 `PaginatedFinanceSettlementLineList` |
| GET | `staff/finance/today/` | `staff.view_cod` (by the key or the body: see the table above) |  |  | 200 `FinanceToday` |
| GET | `staff/flags/` | `staff.view_featureflag` |  |  | 200 `[Flag]` |
| GET | `staff/flags/{key}/` | `staff.view_featureflag` |  |  | 200 `[SwitchRow]` |
| PUT | `staff/flags/{key}/` | `staff.manage_flags` |  | `SwitchChangeRequest` | 200 `SwitchRow` |
| GET | `staff/flags/{key}/history/` | `staff.view_featureflag` |  |  | 200 `[SwitchRow]` |
| GET | `staff/home/` | any member of staff | `period` |  | 200 `Home` |
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
| GET | `staff/orders/` | `shop.view_order` | `courier`, `created_from`, `created_to`, `cursor`, `hold`, `livemode`, `method`, `page_size`, `q`, `risk`, `shipping`, `status`, `tab`, `tag` |  | 200 `PaginatedOrderRowList` |
| POST | `staff/orders/` | `shop.add_order` |  | `StaffOrderRequest` | 201 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/orders/packing/` | `shop.view_order` | `cursor`, `page_size` |  | 200 `PaginatedPackingRowList` |
| POST | `staff/orders/pick-list/` | `staff.pack_order` |  | `PickListRequest` | 200 `application/pdf` |
| POST | `staff/orders/preview/` | `shop.add_order` |  | `StaffOrderPreviewAskRequest` | 200 `StaffOrderPreview` |
| GET | `staff/orders/products/` | `shop.view_product` | `q` |  | 200 `[ProductPick]` |
| GET | `staff/orders/quotes/` | `shop.view_quoterequest` | `cursor`, `page_size`, `status` |  | 200 `PaginatedQuoteRowList` |
| GET | `staff/orders/quotes/{id}/` | `shop.view_quoterequest` |  |  | 200 `QuoteDetail` |
| POST | `staff/orders/quotes/{id}/convert/` | `shop.change_quoterequest` |  | `QuoteConvertRequest` | 201 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/orders/quotes/{id}/quotation/` | `shop.view_quoterequest` |  |  | 200 `application/pdf` |
| POST | `staff/orders/refunds/{id}/mark-paid/` | `staff.approve_refund` |  | `RefundMarkPaidRequest` | 200 `OrderRefund` |
| POST | `staff/orders/refunds/{id}/payee/` | `staff.approve_refund` |  | `RefundPayeeReasonRequest` | 200 `RefundPayee` |
| GET | `staff/orders/returns/` | `shop.view_returnrequest` | `by_customer`, `cursor`, `open`, `order`, `page_size`, `reason`, `status` |  | 200 `PaginatedReturnRowList` |
| GET | `staff/orders/returns/{id}/` | `shop.view_returnrequest` |  |  | 200 `ReturnDetail` |
| POST | `staff/orders/returns/{id}/approve/` | `staff.handle_return` |  |  | 200 `ReturnDetail` |
| POST | `staff/orders/returns/{id}/decline/` | `staff.handle_return` |  | `ReturnDeclineRequest` | 200 `ReturnDetail` |
| POST | `staff/orders/returns/{id}/inspect/` | `staff.receive_return` |  | `ReturnInspectRequest` | 200 `ReturnDetail` |
| POST | `staff/orders/returns/{id}/label/` | `staff.handle_return` |  | `ReturnLabelRequest` | 200 `ReturnDetail` |
| POST | `staff/orders/returns/{id}/photos/` | `staff.receive_return` |  | `ReturnPhotoRequest` | 200 `ReturnDetail` |
| GET | `staff/orders/returns/{id}/photos/{index}/` | `shop.view_returnrequest` |  |  | 200 `image/*` |
| POST | `staff/orders/returns/{id}/receive/` | `staff.receive_return` |  |  | 200 `ReturnDetail` |
| GET | `staff/orders/{number}/` | `shop.view_order` |  |  | 200 `OrderDetail` |
| POST | `staff/orders/{number}/cancel/` | `shop.change_order` |  | `OrderCancelRequest` | 200 `OrderRow`; 201 `ChangeRequest`; 202 `ChangeRequest` |
| GET | `staff/orders/{number}/credit-notes/{note}/` | `shop.view_creditnote` |  |  | 200 `application/pdf` |
| POST | `staff/orders/{number}/deliver/` | `staff.pack_order` |  |  | 200 `OrderRow` |
| GET | `staff/orders/{number}/documents/label/` | `staff.pack_order` |  |  | 200 `application/pdf` |
| GET | `staff/orders/{number}/documents/packing-slip/` | `staff.pack_order` |  |  | 200 `application/pdf` |
| POST | `staff/orders/{number}/hold/` | `shop.change_order` |  | `OrderHoldReasonRequest` | 200 `OrderRow` |
| GET | `staff/orders/{number}/invoice/` | `shop.view_invoice` |  |  | 200 `application/pdf` |
| POST | `staff/orders/{number}/invoice/regenerate/` | `shop.change_order` |  |  | 202 `OrderDocumentsQueued` |
| POST | `staff/orders/{number}/invoice/resend/` | `shop.change_order` |  |  | 200 `OrderInvoiceSent` |
| POST | `staff/orders/{number}/notify/` | `shop.change_order` |  | `OrderNotifyRequest` | 200 `OrderNotified` |
| POST | `staff/orders/{number}/offline-payment/` | `staff.record_offline_payment` |  | `OrderOfflinePaymentRequest` | 201 `ChangeRequest`; 202 `ChangeRequest` |
| POST | `staff/orders/{number}/pack/` | `staff.pack_order` |  |  | 200 `OrderRow` |
| POST | `staff/orders/{number}/payment-link/` | `shop.change_order` |  | `OrderPaymentLinkRequest` | 200 `OrderPaymentLinkSent` |
| POST | `staff/orders/{number}/refunds/` | `staff.refund_order` |  | `OrderRefundAskRequest` | 201 `OrderRefundAsked`; 202 `OrderRefundAsked` |
| POST | `staff/orders/{number}/release/` | `shop.change_order` |  |  | 200 `OrderRow` |
| POST | `staff/orders/{number}/returns/` | `staff.handle_return` |  | `ReturnAskRequest` | 201 `ReturnDetail` |
| POST | `staff/orders/{number}/ship/` | `staff.pack_order` |  | `OrderShipRequest` | 200 `OrderRow` |
| POST | `staff/orders/{number}/tags/` | `shop.change_order` |  | `OrderTagsRequest` | 200 `OrderRow` |
| GET | `staff/people/` | `staff.view_staff` | `cursor`, `page_size` |  | 200 `PaginatedPersonList` |
| POST | `staff/people/invite/` | `staff.assign_role` |  | `InviteRequest` | 201 `StaffInvite`; 202 `ChangeRequest` |
| GET | `staff/people/invites/` | `staff.view_staff` | `cursor`, `page_size` |  | 200 `PaginatedStaffInviteList` |
| DELETE | `staff/people/invites/{invite}/` | `staff.assign_role` |  |  | 204 |
| GET | `staff/people/me/sessions/` | any member of staff |  |  | 200 `[OwnSession]` |
| POST | `staff/people/me/sessions/end-others/` | any member of staff |  |  | 200 `OwnSessionsEnded` |
| POST | `staff/people/me/sessions/{session}/end/` | any member of staff |  |  | 204 |
| GET | `staff/people/roles/` | `staff.view_staff` | `language` |  | 200 `[RoleCatalogue]` |
| GET | `staff/people/{id}/` | `staff.view_staff` |  |  | 200 `Person` |
| GET | `staff/people/{id}/access/` | `staff.view_staff` |  |  | 200 `Access` |
| POST | `staff/people/{id}/end-sessions/` | `staff.assign_role` |  |  | 200 `Ended` |
| GET | `staff/people/{id}/erp/` | `staff.view_staff` |  |  | 200 `ErpMirror` |
| POST | `staff/people/{id}/offboard/` | `staff.assign_role` |  | `ReasonRequest` | 200 `Offboarded` |
| GET | `staff/people/{id}/offboarding/` | `staff.view_staffoffboarding` |  |  | 200 `Offboarding` |
| POST | `staff/people/{id}/offboarding/tick/` | `staff.assign_role` |  | `OffboardingTickRequest` | 200 `Offboarding` |
| POST | `staff/people/{id}/reset-mfa/` | `staff.reset_user_mfa` |  | `ReasonRequest` | 202 `ChangeRequest` |
| POST | `staff/people/{id}/roles/` | `staff.assign_role` |  | `GrantRequest` | 200 `Person`; 202 `ChangeRequest` |
| POST | `staff/people/{id}/roles/preview/` | `staff.view_staff` |  | `RolePreviewRequestRequest` | 200 `RolePreview` |
| DELETE | `staff/people/{id}/roles/{role}/` | `staff.assign_role` |  |  | 200 `Person` |
| POST | `staff/people/{id}/scopes/` | `staff.assign_role` |  | `ScopeAddRequest` | 201 `Scope` |
| DELETE | `staff/people/{id}/scopes/{scope}/` | `staff.assign_role` |  |  | 204 |
| GET | `staff/policies/ack/` | any member of staff | `user` |  | 200 `[PolicyAcknowledgement]` |
| POST | `staff/policies/ack/` | any member of staff |  | `PolicyAcknowledgementRequest` | 200 `PolicyAcknowledgement`; 201 `PolicyAcknowledgement` |
| GET | `staff/privacy/cockpit/` | `staff.view_datarequest` |  |  | 200 `Cockpit` |
| GET | `staff/privacy/dark-pattern-audits/` | `staff.view_darkpatternaudit` | `cursor`, `page_size` |  | 200 `PaginatedDarkPatternAuditList` |
| POST | `staff/privacy/dark-pattern-audits/` | `staff.manage_compliance` |  | `DarkPatternAuditRequest` | 201 `DarkPatternAudit` |
| GET | `staff/privacy/dark-pattern-audits/{id}/` | `staff.view_darkpatternaudit` |  |  | 200 `DarkPatternAudit` |
| PATCH | `staff/privacy/dark-pattern-audits/{id}/` | `staff.manage_compliance` |  | `PatchedDarkPatternAuditRequest` | 200 `DarkPatternAudit` |
| POST | `staff/privacy/dark-pattern-audits/{id}/complete/` | `staff.manage_compliance` |  | `CompleteRequest` | 200 `DarkPatternAudit` |
| GET | `staff/privacy/dark-pattern-audits/{id}/file/` | `staff.view_darkpatternaudit` |  |  | 200 `application/octet-stream` |
| POST | `staff/privacy/dark-pattern-audits/{id}/file/` | `staff.manage_compliance` |  | `CertificateFileRequest` | 200 `DarkPatternAudit` |
| POST | `staff/privacy/deletions/{id}/parent-confirmation/` | `staff.handle_data_request` |  | `ParentConfirmationRequest` | 200 `PrivacyDeletionConfirmed` |
| GET | `staff/privacy/disclosures/` | `staff.view_sitesetting` |  |  | 200 `Disclosures` |
| PUT | `staff/privacy/disclosures/` | `staff.manage_settings` |  | `DisclosuresChangeRequest` | 200 `Disclosures` |
| GET | `staff/privacy/holds/` | `accounts.view_legalhold` | `active`, `cursor`, `page_size`, `reason`, `target_type`, `user` |  | 200 `PaginatedLegalHoldList` |
| POST | `staff/privacy/holds/` | `staff.manage_holds` |  | `HoldCreateRequest` | 201 `LegalHold` |
| GET | `staff/privacy/holds/{id}/` | `accounts.view_legalhold` |  |  | 200 `LegalHold` |
| POST | `staff/privacy/holds/{id}/release/` | `staff.manage_holds` |  | `ReleaseRequest` | 200 `LegalHold` |
| GET | `staff/privacy/nominees/{user}/` | `accounts.view_user` |  |  | 200 `AccountNominee` |
| POST | `staff/privacy/nominees/{user}/reveal/` | `staff.reveal_contact` |  | `RevealReasonRequest` | 200 `PrivacyNomineeContact` |
| GET | `staff/privacy/policies/` | `pages.view_page` |  |  | 200 `[Policy]` |
| GET | `staff/privacy/policies/{slug}/` | `pages.view_page` |  |  | 200 `PolicyDetail` |
| POST | `staff/privacy/policies/{slug}/cancel-scheduled/` | `pages.change_page` |  | `ReleaseRequest` | 200 `PolicyDetail` |
| POST | `staff/privacy/policies/{slug}/publish/` | `pages.change_page` |  | `PublishRequest` | 200 `PolicyDetail` |
| GET | `staff/privacy/policies/{slug}/versions/{number}/diff/` | `pages.view_page` |  |  | 200 `PolicyDiff` |
| GET | `staff/privacy/retention/` | `staff.view_datarequest` |  |  | 200 `[RetentionRule]` |
| GET | `staff/processors/` | `staff.view_processorrecord` | `cursor`, `page_size` |  | 200 `PaginatedProcessorList` |
| POST | `staff/processors/` | `staff.add_processorrecord` |  | `ProcessorRequest` | 201 `Processor` |
| GET | `staff/processors/{id}/` | `staff.view_processorrecord` |  |  | 200 `Processor` |
| PUT | `staff/processors/{id}/` | `staff.change_processorrecord` |  | `ProcessorRequest` | 200 `Processor` |
| PATCH | `staff/processors/{id}/` | `staff.change_processorrecord` |  | `PatchedProcessorRequest` | 200 `Processor` |
| DELETE | `staff/processors/{id}/` | `staff.delete_processorrecord` |  |  | 204 |
| GET | `staff/reports/` | `staff.view_insights` |  |  | 200 `ReportIndex` |
| GET | `staff/reports/cod/` | `staff.view_insights` and `staff.view_cod` | `from`, `to` |  | 200 `ReportCod` |
| GET | `staff/reports/codes/` | `staff.view_insights` and `learn.view_bookcode` | `batch` |  | 200 `ReportCodes` |
| GET | `staff/reports/course-health/` | `staff.view_insights` and `learn.view_progress` | `chapter`, `grain`, `subject` |  | 200 `ReportHealth` |
| POST | `staff/reports/print-run/` | `staff.view_insights` and `shop.view_product` |  | `ReportPrintRunRequestRequest` | 200 `ReportPrintRun` |
| GET | `staff/reports/sales-by-place/` | `staff.view_insights` and `shop.view_orderitem` | `from`, `level`, `state`, `to` |  | 200 `ReportPlace` |
| GET | `staff/reports/sales/` | `staff.view_insights` and `shop.view_orderitem` | `by`, `from`, `grain`, `to` |  | 200 `ReportSales` |
| GET | `staff/reports/settlements/` | `staff.view_insights` and `shop.view_settlement` | `from`, `to` |  | 200 `ReportSettlements` |
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
| GET | `staff/settings/{key}/history/` | `staff.view_sitesetting` |  |  | 200 `[SwitchRow]` |
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
| POST | `staff/support/tickets/{number}/cancel/` | `shop.change_order` (by the key or the body: see the table above) |  | `TicketCancelRequest` | 200 `TicketOrderCancelled`; 201 `ChangeRequest`; 202 `ChangeRequest`; 400 `ChangeRequest` |
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
| GET | `staff/system/backups/` | `staff.view_system` |  |  | 200 `Backups` |
| GET | `staff/system/backups/drills/` | `staff.view_restoredrill` |  |  | 200 `RestoreDrill` |
| POST | `staff/system/backups/drills/` | `staff.manage_system` |  | `RestoreDrillRequest` | 201 `RestoreDrill` |
| GET | `staff/system/dependencies/` | `staff.view_system` |  |  | 200 `Dependencies` |
| GET | `staff/system/hardening/` | `staff.view_system` |  |  | 200 `[HardeningRow]` |
| GET | `staff/system/logs/` | `staff.view_system` |  |  | 200 `Logs` |
| POST | `staff/system/reconcile/` | `staff.replay_webhook` |  | `ReconcileRequest` | 200 `Reconciled` |
| GET | `staff/system/scripts/` | `staff.view_scriptinventory` |  |  | 200 `Scripts` |
| GET | `staff/system/sync/` | `erp.view_sync` |  |  | 200 `Sync` |
| GET | `staff/system/sync/links/` | `erp.view_sync` | `q` |  | 200 `[ErpLink]` |
| GET | `staff/tax/calendar/` | `shop.view_taxthreshold` | `month` |  | 200 `TaxCalendar` |
| GET | `staff/tax/documents/` | `shop.view_documentseries` | `cancelled`, `cursor`, `document_type`, `financial_year`, `kind`, `month`, `page_size`, `search`, `series`, `test` |  | 200 `PaginatedTaxDocumentList` |
| GET | `staff/tax/documents/{number}/` | `shop.view_documentseries` |  |  | 200 `TaxDocumentDetail` |
| POST | `staff/tax/documents/{number}/cancel/` | `staff.cancel_document` |  | `CancelRequest` | 200 `TaxDocument` |
| GET | `staff/tax/documents/{number}/pdf/` | `shop.view_documentseries` |  |  | 200 `application/pdf` |
| POST | `staff/tax/gstr1/` | `staff.run_gstr1` |  | `Gstr1Request` | 202 `Job` |
| GET | `staff/tax/hsn/` | `shop.view_hsncode` | `cursor`, `kind`, `page_size`, `q`, `taxability` |  | 200 `PaginatedHsnCodeList` |
| POST | `staff/tax/hsn/` | `shop.change_hsncode` |  | `NewHsnCodeRequest` | 201 `HsnCodeDetail` |
| GET | `staff/tax/hsn/{code}/` | `shop.view_hsncode` |  |  | 200 `HsnCodeDetail` |
| POST | `staff/tax/hsn/{code}/rates/` | `shop.change_hsncode` |  | `NewHsnRateRequest` | 201 `HsnCodeDetail` |
| GET | `staff/tax/problems/` | `shop.view_hsncode` | `all` |  | 200 `[TaxProblem]` |
| GET | `staff/tax/series/` | `shop.view_documentseries` | `financial_year`, `month` |  | 200 `SeriesRegister` |
| GET | `staff/tax/thresholds/` | `shop.view_taxthreshold` |  |  | 200 `ThresholdCard` |
| GET | `staff/templates/` | `ops.view_messagetemplate` | `approval_state`, `category`, `channel`, `event`, `language` |  | 200 `[Template]` |
| POST | `staff/templates/` | `ops.add_messagetemplate` |  | `TemplateRequest` | 201 `Template` |
| GET | `staff/templates/{id}/` | `ops.view_messagetemplate` |  |  | 200 `Template` |
| PATCH | `staff/templates/{id}/` | `ops.change_messagetemplate` |  | `PatchedTemplateRequest` | 200 `Template` |
| POST | `staff/templates/{id}/test/` | `ops.change_messagetemplate` |  | `TestSendRequest` | 200 `TestSent` |
| GET | `staff/users/` | `accounts.view_user` | `board`, `class_level`, `cursor`, `is_active`, `kind`, `page_size`, `q` |  | 200 `PaginatedCustomerRowList` |
| GET | `staff/users/consent-pending/` | `accounts.view_user` | `cursor`, `page_size` |  | 200 `PaginatedCustomerConsentPendingList` |
| GET | `staff/users/{id}/` | `accounts.view_user` |  |  | 200 `CustomerDetail` |
| GET | `staff/users/{id}/commerce/` | `shop.view_order` |  |  | 200 `CustomerCommerce` |
| POST | `staff/users/{id}/consent/verify/` | `staff.verify_consent` |  | `CustomerConsentVerifyRequest` | 201 `CustomerConsentRecord` |
| POST | `staff/users/{id}/end-sessions/` | `staff.end_user_sessions` |  |  | 200 `SessionsEnded` |
| POST | `staff/users/{id}/impersonate/` | `staff.impersonate_user` |  | `ImpersonateRequest` | 200 `Impersonation` |
| POST | `staff/users/{id}/impersonate/end/` | `staff.impersonate_user` |  | `TokenRequest` | 204 |
| POST | `staff/users/{id}/password-reset/` | `staff.initiate_password_reset` |  |  | 200 `Detail` |
| POST | `staff/users/{id}/resend-verification/` | `staff.resend_verification` |  |  | 200 `Detail` |
| POST | `staff/users/{id}/reset-mfa/` | `staff.reset_user_mfa` |  | `ReasonRequest` | 202 `ChangeRequest` |
| POST | `staff/users/{id}/reveal/` | `staff.reveal_contact` |  | `RevealRequest` | 200 `Revealed` |
| POST | `staff/users/{id}/suspend/` | `staff.suspend_user` |  | `ReasonRequest` | 200 `Customer` |
| GET | `staff/users/{id}/timeline/` | `accounts.view_user` | `before`, `kind` |  | 200 `CustomerTimeline` |
| POST | `staff/users/{id}/unlock/` | `staff.unlock_user` |  |  | 200 `Unlocked` |
| POST | `staff/users/{id}/unsuspend/` | `staff.suspend_user` |  | `ReasonRequest` | 200 `Customer` |

- **AcceptRequest**: `token` string (required); `full_name` string; `password` string
- **Access**: `id` integer (required); `email` email (required); `full_name` string (required); `is_active` boolean (required); `is_superuser` boolean (required); `last_login` date-time (required, null); `roles` [AccessRole] (required); `scopes` [AccessScope] (required); `role_scopes` object (required); `limits` object (required); `idle_timeout_s` integer (required); `permissions` integer (required); `capabilities` [CapabilityArea] (required); `pending` [AccessPending] (required); `second_factors` SecondFactors (required); `passkey_required` boolean (required); `erp_profiles` [string] (required)
- **AccessExtended**: `entitlement` integer (required); `valid_until` date (required)
- **AccessPending**: `id` integer (required); `action` string (required); `status` ChangeRequestStatusEnum (required); `target_label` string (required); `about_them` boolean (required); `by_them` boolean (required); `created` date-time (required); `expires_at` date-time (required)
- **AccessRole**: `name` RoleEnum (required); `source` AccessRoleSourceEnum (required); `granted_by` integer (required, null); `granted_at` date-time (required, null); `expires_at` date-time (required, null); `reason` string (required)
- **AccessRoleSourceEnum**: one of `panel`, `admin`
- **AccessRow**: `id` integer (required); `email` email (required); `roles` [string] (required); `grants` [object] (required); `scopes` object (required); `last_login` date-time (required, null); `dormant` boolean (required); `mfa` boolean (required); `permissions` integer (required); `unused` [string] (required); `last_used` object (required)
- **AccessScope**: `id` integer (required); `kind` ScopeKindEnum (required); `value` string (required); `granted_by` integer (required, null); `created` date-time (required); `expires_at` date-time (required, null)
- **AccountNominee**: `user` integer (required); `nominee` PrivacyNominee (required, null)
- **AccountRow**: `id` integer (required); `mode` IntegrationModeEnum (required); `enabled` boolean (required); `label` string (required); `held` object (required); `unreadable` boolean (required); `credentials_updated_at` date-time (required, null); `credentials_updated_by` integer (required, null); `rotate_by` date (required, null); `rotate_in_days` integer (required, null); `token_expires_at` date-time (required, null); `token_in_hours` double (required, null); `webhook_token` string (required); `webhook_rotated_at` date-time (required, null)
- **AcknowledgeRequest**: `note` string
- **Actions**: `test` boolean (required); `credentials` boolean (required); `mode` boolean (required); `circuit` boolean (required); `webhooks` boolean (required)
- **ActorTypeEnum**: one of `staff`, `user`, `service`, `system`, `anonymous`
- **Advisory**: `id` string (required); `ecosystem` string (required); `project` string (required); `package` string (required); `version` string (required); `severity` SeverityEnum (required); `title` string (required); `url` string (required); `fixed_in` string (required); `first_seen` date (required); `due` date (required, null); `overdue` boolean (required)
- **Agent**: `id` integer (required); `name` string (required); `handles` boolean (required)
- **ApiKey**: `id` integer (required, read-only); `name` string (required); `prefix` string (required, read-only); `key` string (required, null, read-only); `scopes` any; `sponsor` integer; `created_by` integer (required, null, read-only); `created` date-time (required, read-only); `expires_at` date-time; `allowed_ips` any; `last_used_at` date-time (required, null, read-only); `last_used_ip` string (required, null, read-only); `revoked_at` date-time (required, null, read-only); `revoked_by` integer (required, null, read-only)
- **ApiKeyRequest**: `name` string (required); `scopes` any; `sponsor` integer; `expires_at` date-time; `allowed_ips` any
- **Approval**: `user` integer (required); `decision` DecisionEnum (required); `comment` string; `created` date-time
- **ApproveRequest**: `payload_sha256` string (required); `comment` string; `override` boolean
- **AskActionEnum**: one of `order.refund`, `order.offline_payment`, `product.price`, `coupon.create`, `coupon.change`, `offer.create`, `offer.change`, `entitlement.grant`, `entitlement.extend`, `entitlement.revoke`, `item_metadata`
- **AskRequest**: `action` AskActionEnum (required); `target` string (required); `payload` object (required); `reason` string (required)
- **AssignRequest**: `assignee` integer (required, null)
- **Attachment**: `id` integer (required, read-only); `name` string (required, read-only); `content_type` string (required, read-only); `size` integer (required, read-only)
- **AttributeKindEnum**: one of `text`, `number`, `choice`, `boolean`
- **AuditEvent**: `id` integer (required, read-only); `chain` ChainEnum; `ts` date-time (required); `actor_id` integer (null); `actor_type` ActorTypeEnum (required); `actor_roles` any; `on_behalf_of` integer (null); `break_glass` boolean; `action` string (required); `permission` string; `target_type` string; `target_id` string; `target_label` string; `outcome` AuditOutcomeEnum; `reason` string; `change_request_id` integer (null); `request_id` string; `ip` string (null); `user_agent` string; `session_hash` string; `changes` any; `details` any; `prev_hash` string (required); `hash` string (required)
- **AuditOutcomeEnum**: one of `success`, `denied`, `failed`
- **AuditRow**: `pattern` PatternEnum (required); `label` string (required, read-only); `finding` string (required); `fix` string (required)
- **AuditRowRequest**: `pattern` PatternEnum (required); `finding` string (required); `fix` string (required)
- **Backtest**: `product` string (required, read-only); `horizon_weeks` integer (required); `wape` double (null); `mase_vs_seasonal_naive` double (null); `shown` boolean; `n` integer (required, read-only)
- **BackupFile**: `name` string (required); `at` date-time (required); `size` integer (required); `sha256` string (required); `encrypted` boolean (required)
- **BackupSource**: `key` string (required); `label` string (required); `prefix` string (required); `latest` BackupFile (required, null); `age_hours` double (required, null); `stale` boolean (required); `error` string (required)
- **Backups**: `configured` boolean (required); `bucket` string (required); `sources` [BackupSource] (required); `stale` boolean (required); `unreadable` boolean (required); `stale_hours` integer (required); `retention_days` integer (required); `checked_at` date-time (required); `last_proven` Proven (required, null); `drills` [RestoreDrill] (required)
- **BeforeAfterProfiles**: `before` [string] (required); `after` [string] (required)
- **BeforeAfterSeconds**: `before` integer (required); `after` integer (required)
- **BlankEnum**: null
- **BookCodeLookupRequest**: `code` string (required)
- **BookFormatEnum**: one of `print`, `ebook`
- **BookRequest**: `order` string (required, null); `courier_company_id` integer; `courier_name` string; `quoted_rate` decimal (null); `weight_g` integer; `length_cm` integer; `breadth_cm` integer; `height_cm` integer; `pickup_location` integer (null); `courier` CourierEnum; `tracking_number` string; `tracking_url` any
- **BreakGlassReasonRequest**: `reason` string (required)
- **Bucket**: `alias` string (required); `bucket` string (required)
- **Call**: `id` integer (required, read-only); `mode` string (required, read-only); `operation` string (required, read-only); `method` string (required, read-only); `path` string (required, read-only); `status_code` integer (required, null, read-only); `duration_ms` integer (required, read-only); `provider_request_id` string (required, read-only); `error` string (required, read-only); `excerpt` string (required, read-only); `created` date-time (required, read-only)
- **Calls**: `day` integer (required); `day_errors` integer (required); `week` integer (required); `week_errors` integer (required); `p90_ms` integer (required, null)
- **CancelRequest**: `reason` string (required)
- **Capability**: `perm` string (required); `label` string (required); `area` string (required); `risk` RiskEnum (required); `reauth` boolean (required); `approval` boolean (required); `alert` boolean (required); `last_used` date-time (null)
- **CapabilityArea**: `area` string (required); `permissions` [Capability] (required)
- **CarrierEnum**: one of `manual`, `shiprocket`
- **CatalogueAlertRow**: `product` string (required); `title` string (required); `requests` integer (required); `last_asked` date-time (required); `available` integer (required)
- **CatalogueAttribute**: `code` string (required); `name` string (required); `kind` string (required); `choices` [string] (required); `value` string (required, null)
- **CatalogueAttributeDef**: `id` integer (required, read-only); `name` string (required); `code` string (required); `kind` AttributeKindEnum; `choices` string; `position` integer; `values` integer (required, read-only)
- **CatalogueAttributeDefRequest**: `name` string (required); `code` string (required); `kind` AttributeKindEnum; `choices` string; `position` integer
- **CatalogueBookStockEnum**: one of `out`, `low`, `in_stock`
- **CatalogueBundleLine**: `product` string (required); `title` string (required); `kind` string (required); `quantity` integer (required); `stock` integer (required); `weight_grams` integer (required)
- **CatalogueBundleLineRequest**: `product` string (required); `quantity` integer (required)
- **CatalogueBundleLinesRequest**: `lines` [CatalogueBundleLineRequest] (required)
- **CatalogueCategory**: `id` integer (required, read-only); `slug` string (required); `name` string (required); `description` string; `depth` integer (required, read-only); `parent` string (required, null, read-only); `products` integer (required, read-only)
- **CatalogueCategoryMoveRequest**: `target` string (required, null); `position` CategoryMoveEnum (required)
- **CatalogueCategoryWriteRequest**: `name` string (required); `slug` string (required); `description` string; `parent` string (null)
- **CatalogueChange**: `field` string (required); `before` any (required, null); `after` any (required, null)
- **CatalogueCode**: `code` string (required); `note` string (required); `job` integer (required, null); `created` date-time (required); `used` boolean (required); `used_at` date-time (required, null); `order` string (required, null)
- **CatalogueCodeBatch**: `job` integer (required, null); `note` string (required); `made` integer (required); `used` integer (required); `created` date-time (required)
- **CatalogueCodeCounts**: `made` integer (required); `used` integer (required); `batches` [CatalogueCodeBatch] (required)
- **CatalogueCodePage**: `next` uri (required, null); `previous` uri (required, null); `results` [CatalogueCode] (required)
- **CatalogueCollection**: `id` integer (required, read-only); `slug` string (required); `name` string (required); `description` string; `is_active` boolean; `position` integer; `products` [string] (required, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **CatalogueCollectionWriteRequest**: `slug` string (required); `name` string (required); `description` string; `is_active` boolean; `position` integer; `products` [string]
- **CatalogueCoupon**: `id` integer (required, read-only); `code` string (required, read-only); `kind` DiscountKindEnum (required, read-only); `value` decimal (required, read-only); `min_order` decimal (required, read-only); `valid_from` date-time (required, read-only); `valid_until` date-time (required, null, read-only); `max_uses` integer (required, null, read-only); `max_uses_per_customer` integer (required, null, read-only); `is_active` boolean (required, read-only); `description` string (required, read-only); `note` string (required, read-only); `include_products` [string] (required, read-only); `include_categories` [string] (required, read-only); `exclude_products` [string] (required, read-only); `exclude_categories` [string] (required, read-only); `first_order_only` boolean (required, read-only); `stackable` boolean (required, read-only); `single_use` boolean (required, read-only); `state` CatalogueTermStateEnum (required, read-only); `uses` integer (required, read-only); `codes` CatalogueCodeCounts (required, read-only); `waiting` [CatalogueWaiting] (required, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **CatalogueCouponWriteRequest**: `code` string; `kind` DiscountKindEnum; `value` decimal; `min_order` decimal; `valid_from` date-time (null); `valid_until` date-time (null); `max_uses` integer (null); `max_uses_per_customer` integer (null); `is_active` boolean; `description` string; `note` string; `include_products` [string]; `include_categories` [string]; `exclude_products` [string]; `exclude_categories` [string]; `first_order_only` boolean; `stackable` boolean; `single_use` boolean; `reason` string (required)
- **CatalogueImage**: `id` integer (required); `src` uri (required); `width` integer (required, null); `height` integer (required, null); `alt` string (required); `position` integer (required)
- **CatalogueImportUploadRequest**: `file` binary (required)
- **CatalogueNamed**: `slug` string (required); `name` string (required)
- **CatalogueOffer**: `id` integer (required, read-only); `name` string (required, read-only); `banner` string (required, read-only); `kind` DiscountKindEnum (required, read-only); `value` decimal (required, read-only); `scope` OfferScopeEnum (required, read-only); `products` [string] (required, read-only); `categories` [string] (required, read-only); `collections` [string] (required, read-only); `min_quantity` integer (required, read-only); `min_value` decimal (required, read-only); `valid_from` date-time (required, read-only); `valid_until` date-time (required, null, read-only); `max_uses` integer (required, null, read-only); `max_uses_per_customer` integer (required, null, read-only); `combinable` boolean (required, read-only); `is_active` boolean (required, read-only); `show_countdown` boolean (required, read-only); `state` CatalogueTermStateEnum (required, read-only); `uses` integer (required, read-only); `waiting` [CatalogueWaiting] (required, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **CatalogueOfferWriteRequest**: `name` string; `banner` string; `kind` DiscountKindEnum; `value` decimal; `scope` OfferScopeEnum; `products` [string]; `categories` [string]; `collections` [string]; `min_quantity` integer; `min_value` decimal; `valid_from` date-time (null); `valid_until` date-time (null); `max_uses` integer (null); `max_uses_per_customer` integer (null); `combinable` boolean; `is_active` boolean; `show_countdown` boolean; `reason` string (required)
- **CatalogueOption**: `value` string (required); `label` string (required)
- **CatalogueOptions**: `kinds` [CatalogueOption] (required); `packaging` [CatalogueOption] (required); `tax_treatments` [CatalogueOption] (required); `subjects` [CatalogueOption] (required); `books` [CatalogueOption] (required); `product_types` [CatalogueOption] (required); `categories` [CatalogueOption] (required); `collections` [CatalogueOption] (required); `hsn_codes` [CatalogueOption] (required, null); `states` [CatalogueOption] (required)
- **CataloguePicture**: `src` uri (required); `width` integer (required, null); `height` integer (required, null)
- **CataloguePictureUploadRequest**: `image` binary (required); `alt` string; `position` integer; `as_cover` boolean
- **CataloguePrices**: `mrp` decimal (required); `price` decimal (required); `saving_percent` integer (required); `prior_price` decimal (required, null); `prior_price_applies` boolean (required); `prior_price_from` date (required)
- **CataloguePriorPrice**: `price` decimal (required); `lowest_in_30_days` decimal (required); `prior_price` decimal (required, null); `window_from` date-time (required); `applies` boolean (required); `applies_from` date (required)
- **CatalogueProduct**: `id` integer (required, read-only); `slug` string (required, read-only); `title` string (required, read-only); `kind` ProductKindEnum (required, read-only); `is_active` boolean (required, read-only); `subject` CatalogueSubject (required, null, read-only); `book` CatalogueNamed (required, null, read-only); `isbn` string (required, read-only); `pages` integer (required, null, read-only); `description` string (required, read-only); `product_type` CatalogueTypeRef (required, null, read-only); `attributes` [CatalogueAttribute] (required, read-only); `categories` [CatalogueNamed] (required, read-only); `collections` [CatalogueNamed] (required, read-only); `related` [string] (required, read-only); `old_slugs` [string] (required, read-only); `web_url` string (required, read-only); `prices` CataloguePrices (required, read-only); `hsn` string (required, null, read-only); `hsn_code` string (required, read-only); `gst_rate` decimal (required, read-only); `tax_treatment` TaxTreatmentEnum (required, read-only); `tax_note` string (required, read-only); `tax_note_date` date (required, null, read-only); `tax` CatalogueTax (required, read-only); `weight_grams` integer (required, read-only); `length_cm` integer (required, null, read-only); `width_cm` integer (required, null, read-only); `height_cm` integer (required, null, read-only); `packaging` any (required, read-only); `courier_problem` string (required, read-only); `stock_info` CatalogueStock (required, read-only); `cover` CataloguePicture (required, null, read-only); `images` [CatalogueImage] (required, read-only); `bundle_items` [CatalogueBundleLine] (required, read-only); `seo_title` string (required, read-only); `seo_description` string (required, read-only); `barcode` boolean (required, read-only); `waiting` [CatalogueWaiting] (required, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **CatalogueProductMade**: `product` CatalogueProduct (required); `price_change` ChangeRequest (required, null)
- **CatalogueProductPriceWaiting**: `price_change` ChangeRequest (required); `slug` string (required)
- **CatalogueProductRow**: `id` integer (required, read-only); `slug` string (required, read-only); `title` string (required, read-only); `kind` ProductKindEnum (required, read-only); `is_active` boolean (required, read-only); `mrp` decimal (required, read-only); `price` decimal (required, read-only); `saving_percent` integer (required, read-only); `stock` integer (required, read-only); `available` integer (required, read-only); `stock_state` CatalogueStockStateEnum (required, read-only); `hsn_code` string (required, read-only); `gst_rate` decimal (required, read-only); `tax_problem` string (required, read-only); `courier_problem` string (required, read-only); `cover` CataloguePicture (required, null, read-only); `categories` [string] (required, read-only); `modified` date-time (required, read-only)
- **CatalogueProductType**: `id` integer (required, read-only); `name` string (required); `attributes` [CatalogueAttributeDef] (required, read-only); `products` integer (required, read-only)
- **CatalogueProductWriteRequest**: `title` string (required); `slug` string (required); `kind` ProductKindEnum (required); `is_active` boolean; `subject` integer (null); `book` string (null); `isbn` string; `pages` integer (null); `description` string; `product_type` integer (null); `attributes` object; `categories` [string]; `related` [string]; `weight_grams` integer; `length_cm` integer (null); `width_cm` integer (null); `height_cm` integer (null); `packaging` any; `seo_title` string; `seo_description` string; `hsn` string (null); `tax_treatment` TaxTreatmentEnum; `tax_note` string; `tax_note_date` date (null); `mrp` decimal (required); `price` decimal; `reason` string
- **CatalogueRate**: `rate` decimal (required); `taxability` string (required); `effective_from` date (required); `notification` string (required)
- **CatalogueShippingRate**: `id` integer (required, read-only); `name` string (required, read-only); `states` any (required, read-only); `fee` decimal (required, read-only); `free_above` decimal (required, null, read-only); `is_active` boolean (required, read-only)
- **CatalogueShippingRateWriteRequest**: `name` string (required); `states` [CatalogueStatesEnum]; `fee` decimal (required); `free_above` decimal (null); `is_active` boolean; `reason` string
- **CatalogueStatesEnum**: one of `AN`, `AP`, `AR`, `AS`, `BR`, `CH`, `CT`, `DH`, `DL`, `GA`, `GJ`, `HP`, `HR`, `JH`, `JK`, `KA`, `KL`, `LA`, `LD`, `MH`, `ML`, `MN`, `MP`, `MZ`, `NL`, `OR`, `PB`, `PY`, `RJ`, `SK`, `TG`, `TN`, `TR`, `UP`, `UT`, `WB`
- **CatalogueStock**: `stock` integer (required); `available` integer (required); `state` string (required); `low_stock` integer (required); `reserved` integer (required); `awaiting_payment` integer (required); `alerts` integer (required); `last_alert` date-time (required, null)
- **CatalogueStockRow**: `id` integer (required, read-only); `slug` string (required, read-only); `title` string (required, read-only); `kind` ProductKindEnum (required, read-only); `is_active` boolean (required, read-only); `stock` integer (required, read-only); `reserved` integer (required, read-only); `awaiting_payment` integer (required, read-only); `state` CatalogueBookStockEnum (required, read-only); `alerts` integer (required, read-only)
- **CatalogueStockSetRequest**: `stock` integer (required); `reason` string (required); `expected` integer
- **CatalogueStockStateEnum**: one of `none`, `out`, `low`, `in_stock`
- **CatalogueSubject**: `id` integer (required); `label` string (required)
- **CatalogueSummary**: `products` integer (required); `incomplete` integer (required); `tax_problems` integer (required); `low_stock` integer (required); `out_of_stock` integer (required); `low_stock_line` integer (required); `stock_alerts` integer (required, null); `approvals` integer (required); `prior_price_applies` boolean (required); `prior_price_from` date (required)
- **CatalogueTax**: `today` CatalogueRate (required, null); `next_change` CatalogueRate (required, null); `problem` string (required)
- **CatalogueTermStateEnum**: one of `live`, `scheduled`, `ended`, `inactive`
- **CatalogueTypeNameRequest**: `name` string (required)
- **CatalogueTypeRef**: `id` integer (required); `name` string (required)
- **CatalogueVersion**: `id` integer (required); `at` date-time (required); `by` integer (required, null); `by_name` string (required); `reason` string (required); `type` ContentVersionTypeEnum (required); `changes` [CatalogueChange] (required)
- **CatalogueVersionPage**: `next` uri (required, null); `previous` uri (required, null); `results` [CatalogueVersion] (required)
- **CatalogueWaiting**: `id` integer (required); `action` string (required); `status` string (required); `rule` string (required); `payload` any (required); `created` date-time (required)
- **CategoryMoveEnum**: one of `first-child`, `last-child`, `left`, `right`
- **CertificateFileRequest**: `file` binary (required)
- **ChainEnum**: one of `general`, `money`
- **ChangeRequest**: `id` integer (required, read-only); `action` string (required); `label` string (required, read-only); `target_type` string; `target_id` string; `target_label` string; `payload` any; `payload_sha256` string (required); `amount` decimal (null); `maker` integer (required); `reason` string (required); `rule` string; `status` ChangeRequestStatusEnum; `expires_at` date-time (required); `overridden` boolean; `checker` string (required, read-only); `approvals` [Approval] (required, read-only); `result` any (null); `executed_by` integer (null); `executed_at` date-time (null); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **ChangeRequestStatusEnum**: one of `pending`, `approved`, `rejected`, `expired`, `executed`, `failed`
- **ChannelEnum**: one of `email`, `letter`, `phone`, `form`, `in_person`, `board`
- **ChapterStat**: `chapter` integer (required); `subject` integer (required, read-only); `number` integer (required, read-only); `title` string (required, read-only); `mean_accuracy` double (null); `trend` double (null); `n` integer (required, read-only)
- **Circuit**: `state` CircuitStateEnum (required); `held_open` boolean (required); `opened_at` date-time (required, null); `failures` integer (required)
- **CircuitActionEnum**: one of `open`, `reset`
- **CircuitActionRequest**: `reason` string (required); `action` CircuitActionEnum (required)
- **CircuitStateEnum**: one of `closed`, `open`, `half_open`
- **ClassLevelEnum**: one of `10`, `12`
- **ClipKindEnum**: one of `concept`, `trick`, `shortcut`, `formula`, `pattern`, `mistake`, `pyq`
- **ClipProcessingEnum**: one of `uploaded`, `processing`, `ready`, `failed`
- **Clock**: `kind` ClockKindEnum (required); `label` string (required); `rule` string (required); `started_at` date-time (required, null); `due_at` date-time (required, null); `overdue` boolean (required); `target_type` string (required); `target_id` string (required); `target_label` string (required); `account` integer (required, null)
- **ClockCount**: `open` integer (required); `overdue` integer (required)
- **ClockKindEnum**: one of `data_request_ack`, `data_request_answer`, `incident_cert_in`, `incident_board`, `complaint_ack`, `complaint_redress`, `complaint_nch`, `parent_consent`, `deletion_parent`, `dark_pattern_audit`
- **CloseRequest**: `outcome` DataRequestOutcomeEnum (required); `response` string (required)
- **Cockpit**: `now` date-time (required); `clocks` [Clock] (required); `counts` object (required); `support` PrivacyCockpitSupport (required); `consents` [PrivacyConsentVersion] (required); `dark_pattern` PrivacyDarkPatternState (required); `calendar` [PrivacyCalendarItem] (required); `inbox` integer (required)
- **CodReconcileRequest**: `utr` string (required); `amount` decimal (required); `on` date
- **CodRemittance**: `id` integer (required, read-only); `shipment` integer (required, read-only); `order` string (required, read-only); `expected_amount` decimal (required, read-only); `expected_on` date (required, read-only); `remitted_amount` decimal (required, null, read-only); `utr` string (required, read-only); `remitted_at` date (required, null, read-only); `state` CodRemittanceStateEnum (required, read-only); `checked_at` date-time (required, null, read-only)
- **CodRemittanceStateEnum**: one of `expected`, `overdue`, `remitted`, `mismatch`, `not_expected`
- **CodeActivation**: `batch` string (required); `district` string (null); `printed` integer (null); `redeemed` integer (required); `redeemed_7d` integer (required); `n` integer (required, read-only); `hidden` boolean (required, read-only); `under` integer (required, null, read-only)
- **CodeAnswer**: `found` boolean (required); `batch` string; `subject` string; `redeemed` boolean; `by_requester` boolean; `line` string (required)
- **CodeRow**: `batch` string (required); `subject` string (required); `redeemed_at` date-time (required)
- **CohortStat**: `cohort_month` date (required); `source` EntitlementSourceEnum (required); `week_index` integer (required); `active_share` double (null); `churned_share` double (null); `n` integer (required); `hidden` boolean (required, read-only); `under` integer (required, null, read-only)
- **CommentRequest**: `comment` string
- **CompleteRequest**: `effective_from` date
- **Conflict**: `roles` [string] (required); `text` string (required)
- **ConnectionCard**: `provider` ConnectionProviderEnum (required); `name` string (required); `kind` ConnectionKindEnum (required); `status` ConnectionStatusEnum (required); `mode` ConnectionModeEnum (required); `source` ConnectionSourceEnum (required); `held` object (required); `accounts` [AccountRow] (required); `last_success_at` date-time (required, null); `last_error_at` date-time (required, null); `last_error` string (required); `last_test` LastTest (required); `circuit` Circuit (required); `calls` Calls (required); `fields` [string] (required); `optional` [string] (required); `modes` [IntegrationModeEnum] (required); `overlap_warning` string (required); `actions` Actions (required); `extra` Extra (required)
- **ConnectionKindEnum**: one of `email`, `erp`, `errors`, `payments`, `shipping`, `sign_in`, `sms`, `storage`, `whatsapp`
- **ConnectionModeEnum**: one of `off`, `test`, `live`
- **ConnectionProviderEnum**: one of `razorpay`, `shiprocket`, `manual`, `msg91`, `whatsapp`, `ses`, `storage`, `error_tracker`, `google`, `erpnext`
- **ConnectionReasonRequest**: `reason` string (required)
- **ConnectionSourceEnum**: one of `panel`, `environment`, `none`
- **ConnectionStatusEnum**: one of `connected`, `degraded`, `expired`, `disabled`, `not_configured`
- **ConsentRow**: `event` string (required); `method` string (required); `by_parent` boolean (required); `verified_at` date-time (required, null); `notice_version` string (required); `created` date-time (required)
- **ConsentVerifyMethodEnum**: one of `staff_manual`, `adult_account`, `digilocker`
- **Contact**: `contact` string (required); `source` ContactSourceEnum (required); `placeholder` boolean (required)
- **ContactSourceEnum**: one of `panel`, `environment`
- **ContentBook**: `id` integer (required, read-only); `title` string (required); `subject` integer (required); `subject_code` string (required, read-only); `edition` string; `slug` string (required); `cover` string; `isbn` string; `format` BookFormatEnum; `published_on` date (null); `deposit_due_on` date (required, null, read-only); `papers` integer (required, read-only)
- **ContentBookDetail**: `id` integer (required, read-only); `title` string (required); `subject` integer (required); `subject_code` string (required, read-only); `edition` string; `slug` string (required); `cover` string; `isbn` string; `format` BookFormatEnum; `published_on` date (null); `deposit_due_on` date (required, null, read-only); `papers` integer (required, read-only); `missing_deposits` [string] (required, read-only)
- **ContentBookRequest**: `title` string (required); `subject` integer (required); `edition` string; `slug` string (required); `cover` string; `isbn` string; `format` BookFormatEnum; `published_on` date (null)
- **ContentChange**: `field` string (required); `before` any (required, null); `after` any (required, null); `lines` [ContentLine] (required)
- **ContentComment**: `author` integer (required, null); `text` string (required); `at` date-time (required); `field` string (required)
- **ContentDecisionRequest**: `comment` string
- **ContentErratum**: `id` integer (required, read-only); `book` integer (required, null, read-only); `paper_code` string (required, null, read-only); `question_label` string (required, null, read-only); `step` integer (required, null, read-only); `category` ErrorReportCategoryEnum (required, read-only); `printing` string (required, read-only); `state` ErrorReportStateEnum (required, read-only); `fixed_in` string (required, read-only); `fixed_at` date-time (required, null, read-only); `public` boolean (required, read-only); `created` date-time (required, read-only)
- **ContentHeader**: `lines` [string]; `allotment` [string]
- **ContentHeaderRequest**: `lines` [string]; `allotment` [string]
- **ContentLine**: `op` ContentLineOpEnum (required); `text` string (required)
- **ContentLineOpEnum**: one of `equal`, `delete`, `insert`
- **ContentLinked**: `paper_id` integer (required, null); `question_id` integer (required, null); `solution_id` integer (required, null); `question_text` string; `solution_text` string; `solution_state` string (null); `title` string
- **ContentOpenReview**: `id` integer (required, read-only); `state` ReviewTaskStateEnum (required, read-only); `stage` ReviewTaskStageEnum (required, read-only); `assignee` integer (required, null, read-only); `submitted_by` integer (required, null, read-only); `created` date-time (required, read-only)
- **ContentPaper**: `id` integer (required, read-only); `code` string (required, read-only); `title` string (required); `book` integer (required, read-only); `book_title` string (required, read-only); `subject_code` string (required, read-only); `tier` TierEnum (required); `number` integer (required); `full_marks` integer (required); `pass_marks` integer (required); `time_text` string (required); `is_published` boolean; `is_sample` boolean; `questions` integer (required, read-only); `drafts` integer (required, read-only)
- **ContentPaperDetail**: `id` integer (required, read-only); `code` string (required, read-only); `title` string (required); `book` integer (required, read-only); `book_title` string (required, read-only); `subject_code` string (required, read-only); `tier` TierEnum (required); `number` integer (required); `full_marks` integer (required); `pass_marks` integer (required); `time_text` string (required); `is_published` boolean (required, read-only); `is_sample` boolean (required, read-only); `questions` integer (required, read-only); `drafts` integer (required, read-only); `header_json` ContentHeader; `tree` [ContentTreeQuestion] (required, read-only)
- **ContentQuestion**: `id` integer (required, read-only); `paper` integer (required, read-only); `paper_code` string (required, read-only); `order` integer (required, read-only); `label` string (required, read-only); `number` string (required, read-only); `marks_text` string (required, read-only); `is_published` boolean (required, read-only); `state` ContentStateEnum (required, read-only); `preview` string (required, read-only); `solution` integer (required, null, read-only)
- **ContentQuestionDetail**: `id` integer (required, read-only); `paper` integer (required, read-only); `paper_code` string (required, read-only); `order` integer (required, read-only); `label` string (required, read-only); `number` string (required, read-only); `marks_text` string (required, read-only); `is_published` boolean (required, read-only); `state` ContentStateEnum (required, read-only); `preview` string (required, read-only); `solution` integer (required, null, read-only); `text_md` string (required, read-only); `table_md` string (required, read-only); `options_json` any (required, read-only); `group_label` string (required, read-only); `part_label` string (required, read-only); `is_alternative` boolean (required, read-only); `tags` [string] (required, read-only); `draft` any (required, read-only); `draft_by` integer (required, null, read-only); `published_at` date-time (required, null, read-only); `published_by` integer (required, null, read-only); `review` object (required, null, read-only)
- **ContentReport**: `id` integer (required, read-only); `kind` string (required, read-only); `target_id` integer (required, read-only); `subject` string (required, null, read-only); `paper` integer (required, null, read-only); `paper_code` string (required, null, read-only); `question` integer (required, null, read-only); `question_label` string (required, null, read-only); `step` integer (required, null, read-only); `printing` string (required, read-only); `category` ErrorReportCategoryEnum (required, read-only); `note` string (required, read-only); `email` string (required, read-only); `reporter` integer (required, null, read-only); `teacher_verified` boolean (required, read-only); `state` ErrorReportStateEnum (required, read-only); `fixed_in` string (required, read-only); `fixed_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `staff_note` string (required, read-only); `reporter_told_at` date-time (required, null, read-only); `public` boolean (required, read-only); `created` date-time (required, read-only); `can_tell` boolean (required, read-only)
- **ContentReportDetail**: `id` integer (required, read-only); `kind` string (required, read-only); `target_id` integer (required, read-only); `subject` string (required, null, read-only); `paper` integer (required, null, read-only); `paper_code` string (required, null, read-only); `question` integer (required, null, read-only); `question_label` string (required, null, read-only); `step` integer (required, null, read-only); `printing` string (required, read-only); `category` ErrorReportCategoryEnum (required, read-only); `note` string (required, read-only); `email` string (required, read-only); `reporter` integer (required, null, read-only); `teacher_verified` boolean (required, read-only); `state` ErrorReportStateEnum (required, read-only); `fixed_in` string (required, read-only); `fixed_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `staff_note` string (required, read-only); `reporter_told_at` date-time (required, null, read-only); `public` boolean (required, read-only); `created` date-time (required, read-only); `can_tell` boolean (required, read-only); `handled_by` integer (required, null, read-only); `linked` ContentLinked (required, read-only)
- **ContentReview**: `id` integer (required, read-only); `label` string (required, read-only); `kind` string (required, read-only); `target_id` integer (required, read-only); `subject` string (required, null, read-only); `paper` integer (required, null, read-only); `stage` ReviewTaskStageEnum (required, read-only); `state` ReviewTaskStateEnum (required, read-only); `assignee` integer (required, null, read-only); `submitted_by` integer (required, null, read-only); `edited_by` integer (required, null, read-only); `approved_by` integer (required, null, read-only); `approved_at` date-time (required, null, read-only); `published_by` integer (required, null, read-only); `published_at` date-time (required, null, read-only); `rolled_back_by` integer (required, null, read-only); `rolled_back_at` date-time (required, null, read-only); `created` date-time (required, read-only); `fields_changed` [string] (required, read-only); `yours` boolean (required, read-only)
- **ContentReviewDetail**: `id` integer (required, read-only); `label` string (required, read-only); `kind` string (required, read-only); `target_id` integer (required, read-only); `subject` string (required, null, read-only); `paper` integer (required, null, read-only); `stage` ReviewTaskStageEnum (required, read-only); `state` ReviewTaskStateEnum (required, read-only); `assignee` integer (required, null, read-only); `submitted_by` integer (required, null, read-only); `edited_by` integer (required, null, read-only); `approved_by` integer (required, null, read-only); `approved_at` date-time (required, null, read-only); `published_by` integer (required, null, read-only); `published_at` date-time (required, null, read-only); `rolled_back_by` integer (required, null, read-only); `rolled_back_at` date-time (required, null, read-only); `created` date-time (required, read-only); `fields_changed` [string] (required, read-only); `yours` boolean (required, read-only); `draft` any (required, read-only); `previous` any (required, read-only); `comments` [ContentComment] (required, read-only); `changes` [ContentChange] (required, read-only); `question` integer (required, null, read-only)
- **ContentSolution**: `id` integer (required, read-only); `question` integer (required, read-only); `question_label` string (required, read-only); `paper` integer (required, read-only); `paper_code` string (required, read-only); `state` ContentStateEnum (required, read-only); `preview` string (required, read-only)
- **ContentSolutionDetail**: `id` integer (required, read-only); `question` integer (required, read-only); `question_label` string (required, read-only); `paper` integer (required, read-only); `paper_code` string (required, read-only); `state` ContentStateEnum (required, read-only); `preview` string (required, read-only); `question_text` string (required, read-only); `marks_text` string (required, read-only); `body_md` string (required, read-only); `draft` any (required, read-only); `draft_by` integer (required, null, read-only); `published_at` date-time (required, null, read-only); `published_by` integer (required, null, read-only); `review` object (required, null, read-only)
- **ContentStateEnum**: one of `draft`, `in_review`, `published`
- **ContentSubmitRequest**: `assignee` integer (null)
- **ContentSummary**: `reports_open` ReportsOpen (required); `reviews_waiting` integer (required, null); `reviews_mine` integer (required, null); `drafts` integer (required, null); `legal_deposits_missing` [MissingDeposit] (required, null); `last_import` Job (required, null)
- **ContentTransitionRequest**: `staff_note` string; `fixed_in` string
- **ContentTreeQuestion**: `id` integer (required, read-only); `order` integer (required, read-only); `label` string (required, read-only); `number` string (required, read-only); `group_label` string (required, read-only); `part_label` string (required, read-only); `is_alternative` boolean (required, read-only); `marks_text` string (required, read-only); `is_published` boolean (required, read-only); `state` ContentStateEnum (required, read-only); `preview` string (required, read-only); `solution` ContentTreeSolution (required, null, read-only)
- **ContentTreeSolution**: `id` integer (required, read-only); `state` ContentStateEnum (required, read-only)
- **ContentVersion**: `id` integer (required); `at` date-time (required); `by` integer (required, null); `reason` string (required, null); `type` ContentVersionTypeEnum (required); `changes` [ContentChange] (required)
- **ContentVersionPage**: `next` uri (required, null); `previous` uri (required, null); `results` [ContentVersion] (required)
- **ContentVersionTypeEnum**: one of `+`, `~`, `-`
- **CourierEnum**: one of `India Post`, `Delhivery`, `Blue Dart`, `Ekart`, `DTDC`, `Xpressbees`, `Other`
- **CourseBatch**: `id` integer (required, read-only); `key` string (required, read-only); `label` string (required, read-only); `subject` string (required, null, read-only); `product` CourseBatchProduct (required, null, read-only); `printed` integer (required, read-only); `codes` integer (required, read-only); `redeemed` integer (required, read-only); `void` integer (required, read-only); `state` CourseBatchStateEnum (required, read-only); `note` string (required, read-only); `created` date-time (required, read-only); `generated_at` date-time (required, null, read-only); `generated_by` CoursePerson (required, null, read-only); `dispatched_at` date-time (required, null, read-only); `voided_at` date-time (required, null, read-only); `void_reason` string (required, read-only); `job` CourseBatchJob (required, null, read-only)
- **CourseBatchCreateRequest**: `label` string (required); `subject` string (required); `count` integer (required); `product` string (required); `note` string
- **CourseBatchDetail**: `id` integer (required, read-only); `key` string (required, read-only); `label` string (required, read-only); `subject` string (required, null, read-only); `product` CourseBatchProduct (required, null, read-only); `printed` integer (required, read-only); `codes` integer (required, read-only); `redeemed` integer (required, read-only); `void` integer (required, read-only); `state` CourseBatchStateEnum (required, read-only); `note` string (required, read-only); `created` date-time (required, read-only); `generated_at` date-time (required, null, read-only); `generated_by` CoursePerson (required, null, read-only); `dispatched_at` date-time (required, null, read-only); `voided_at` date-time (required, null, read-only); `void_reason` string (required, read-only); `job` CourseBatchJob (required, null, read-only); `redeemed_by_week` [CourseWeek] (required, read-only); `signals` [CourseBatchSignal] (required, read-only); `activation_rate` double (required, null, read-only); `file_until` string (required, null, read-only); `generation` Job (required, null, read-only)
- **CourseBatchJob**: `id` integer (required); `state` string (required); `done` integer (required); `total` integer (required)
- **CourseBatchProduct**: `id` integer (required); `slug` string (required); `title` string (required)
- **CourseBatchSignal**: `id` integer (required, read-only); `kind` FraudSignalKindEnum (required, read-only); `label` string (required, read-only); `count` integer (required, read-only); `window_start` date-time (required, read-only); `window_end` date-time (required, read-only); `created` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only)
- **CourseBatchStarted**: `batch` CourseBatch (required); `job` Job (required)
- **CourseBatchStateEnum**: one of `generating`, `failed`, `ready`, `dispatched`, `void`
- **CourseBatchVoided**: `batch` CourseBatch (required); `voided` integer (required)
- **CourseBinChapter**: `id` integer (required); `number` integer (required); `title` string (required); `subject` string (required)
- **CourseBinRow**: `id` integer (required); `kind` CourseRowKindEnum (required); `title` string (required); `chapter` CourseBinChapter (required); `revision` integer (required, null); `deleted_at` date-time (required); `bin_until` date-time (required)
- **CourseCard**: `id` integer (required, read-only); `chapter` integer (required, read-only); `order` integer (required, read-only); `front` string (required); `back` string (required); `tags` [string]; `deleted_at` date-time (required, null, read-only); `bin_until` string (required, null, read-only)
- **CourseChapter**: `id` integer (required, read-only); `subject` integer (required, read-only); `number` integer (required, read-only); `title` string (required, read-only); `weight` decimal (required, read-only); `frequency` integer (required, read-only); `must_do` string
- **CourseClip**: `id` integer (required, read-only); `revision` CourseClipRevision (required, read-only); `order` integer (required, read-only); `title` string (required); `kind` ClipKindEnum; `notes` string; `is_free_preview` boolean; `free` boolean (required, read-only); `tags` [string]; `processing` ClipProcessingEnum (required, read-only); `processing_label` string (required, read-only); `reason` string (required, read-only); `error_detail` string (required, read-only); `processing_since` date-time (required, read-only); `stuck` boolean (required, read-only); `can_retry` boolean (required, read-only); `has_video` boolean (required, read-only); `duration` integer (required, read-only); `poster_url` string (required, null, read-only); `player_url` string (required, null, read-only); `questions` [CourseClipQuestion] (required, read-only); `deleted_at` date-time (required, null, read-only); `bin_until` string (required, null, read-only); `completion_rule` string (required, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **CourseClipQuestion**: `id` integer (required); `paper` string (required); `label` string (required)
- **CourseClipRevision**: `id` integer (required); `title` string (required); `status` CourseRevisionStatusEnum (required); `chapter` integer (required); `chapter_number` integer (required); `chapter_title` string (required); `subject` integer (required); `subject_code` string (required)
- **CourseCodeLookup**: `state` CourseCodeStateEnum (required); `line` string (required); `batch` string (required, null); `batch_state` any (required, null); `subject` string (required, null); `redeemed_at` date-time (required, null); `voided_at` date-time (required, null); `redeemed_by` CourseCodeRedeemer (required, null)
- **CourseCodeRedeemer**: `id` integer (required); `email` string (required); `is_minor` boolean (required)
- **CourseCodeRequest**: `code` string (required)
- **CourseCodeStateEnum**: one of `unknown`, `unused`, `redeemed`, `void`
- **CourseCodeVoidRequest**: `code` string (required); `reason` string (required)
- **CourseCodeVoided**: `id` integer (required); `batch` string (required); `voided_at` date-time (required)
- **CourseCommentRequest**: `comment` string
- **CourseDispatchedRequest**: `at` date-time (null)
- **CourseEntitlement**: `id` integer (required, read-only); `user` CourseLearnerRef (required, read-only); `subject` string (required, null, read-only); `subject_name` string (required, read-only); `source` EntitlementSourceEnum (required, read-only); `reference` string (required, read-only); `valid_until` date (required, null, read-only); `note` string (required, read-only); `state` CourseEntitlementStateEnum (required, read-only); `revoked_at` date-time (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `can_extend` boolean (required, read-only); `can_revoke` boolean (required, read-only)
- **CourseEntitlementDetail**: `id` integer (required, read-only); `user` CourseLearnerRef (required, read-only); `subject` string (required, null, read-only); `subject_name` string (required, read-only); `source` EntitlementSourceEnum (required, read-only); `reference` string (required, read-only); `valid_until` date (required, null, read-only); `note` string (required, read-only); `state` CourseEntitlementStateEnum (required, read-only); `revoked_at` date-time (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `can_extend` boolean (required, read-only); `can_revoke` boolean (required, read-only); `history` [CourseVersion] (required, read-only)
- **CourseEntitlementStateEnum**: one of `active`, `ended`, `revoked`
- **CourseExtendRequest**: `days` integer (required); `reason` string (required)
- **CourseFlagAnswer**: `report` integer (required); `created` boolean (required)
- **CourseFlagRequest**: `note` string
- **CourseGrantRequest**: `user` integer (required); `subject` string (required); `valid_until` date (null); `reason` string (required); `reference` string
- **CourseItem**: `id` integer (required, read-only); `chapter` CourseItemChapter (required, read-only); `order` integer (required, read-only); `kind` QuizItemKindEnum (required); `text` string (required); `options` any; `answer` string (required); `explanation` string; `topic` string; `marks` integer; `difficulty` any; `bloom` any; `tags` [string]; `source` CourseItemSource (required, null, read-only); `stats` CourseItemStats (required, read-only); `flagged` integer (required, null, read-only); `deleted_at` date-time (required, null, read-only); `bin_until` string (required, null, read-only)
- **CourseItemChapter**: `id` integer (required); `number` integer (required); `title` string (required); `subject` string (required)
- **CourseItemRow**: `id` integer (required, read-only); `chapter` CourseItemChapter (required, read-only); `order` integer (required, read-only); `kind` QuizItemKindEnum (required, read-only); `text` string (required, read-only); `topic` string (required, read-only); `marks` integer (required, read-only); `difficulty` any (required, read-only); `bloom` any (required, read-only); `tags` [string]; `source` CourseItemSource (required, null, read-only); `stats` CourseItemStats (required, read-only); `flagged` integer (required, null, read-only)
- **CourseItemSource**: `question` integer (required); `paper` string (required); `label` string (required)
- **CourseItemStats**: `n` integer (required, null); `p` double (required, null); `discrimination` double (required, null); `flags` [string] (required); `computed_at` date-time (required, null); `n_too_small` boolean (required)
- **CourseLearner**: `logged` boolean (required); `user` CourseLearnerUser (required); `summary_only` boolean (required); `summary` CourseLearnerSummary (required); `entitlements` [CourseEntitlement] (required); `codes` [CourseLearnerCode] (required, null); `devices` [CourseLearnerDevice] (required); `chapters` [CourseLearnerChapter] (required); `tickets` [CourseLearnerTicket] (required, null)
- **CourseLearnerChapter**: `id` integer (required); `subject` string (required); `number` integer (required); `title` string (required); `clips_watched` integer (required); `clips_total` integer (required); `minutes_watched` integer (required); `quiz_answers` integer (required); `quiz_accuracy` integer (required, null); `card_reviews` integer (required); `cards_known` integer (required)
- **CourseLearnerCode**: `id` integer (required); `batch` string (required); `subject` string (required); `redeemed_at` date-time (required)
- **CourseLearnerDevice**: `id` integer (required); `platform` string (required); `added` date-time (required, null); `last_seen` date-time (required, null); `last_seen_week` date (required, null)
- **CourseLearnerRef**: `id` integer (required); `name` string (required); `email` string (required); `is_minor` boolean (required)
- **CourseLearnerSummary**: `clips_watched` integer (required); `minutes_watched` integer (required); `quiz_answers` integer (required); `quiz_accuracy` integer (required, null); `card_reviews` integer (required); `last_active` date-time (required, null); `last_active_week` date (required, null)
- **CourseLearnerTicket**: `number` string (required); `subject` string (required); `category` string (required); `status` string (required); `received_at` date-time (required)
- **CourseLearnerUser**: `id` integer (required); `name` string (required); `email` string (required); `is_minor` boolean (required); `is_active` boolean (required)
- **CourseMoveEnum**: one of `first`, `last`, `before`, `after`
- **CourseMoveRequest**: `to` CourseMoveEnum (required); `target` integer (null)
- **CourseOutline**: `subject` CourseOutlineSubject (required); `chapters` [CourseOutlineChapter] (required); `completion_rule` string (required); `free_preview` boolean (required)
- **CourseOutlineCard**: `id` integer (required); `order` integer (required); `front` string (required)
- **CourseOutlineChapter**: `id` integer (required); `number` integer (required); `title` string (required); `weight` decimal (required); `frequency` integer (required); `must_do` string (required); `revision` CourseOutlineRevision (required, null); `cards` [CourseOutlineCard] (required); `items` [CourseOutlineItem] (required)
- **CourseOutlineClip**: `id` integer (required); `order` integer (required); `title` string (required); `kind` ClipKindEnum (required); `duration` integer (required); `processing` ClipProcessingEnum (required); `reason` string (required); `is_free_preview` boolean (required); `free` boolean (required)
- **CourseOutlineItem**: `id` integer (required); `order` integer (required); `kind` QuizItemKindEnum (required); `text` string (required); `difficulty` string (required); `flagged` integer (required, null)
- **CourseOutlineRevision**: `id` integer (required); `title` string (required); `status` CourseRevisionStatusEnum (required); `target_minutes` integer (required); `minutes` integer (required); `publish_at` date-time (required, null); `clips` [CourseOutlineClip] (required)
- **CourseOutlineSubject**: `id` integer (required); `code` string (required); `name` string (required)
- **CoursePerson**: `id` integer (required); `name` string (required)
- **CoursePublishRequest**: `publish_at` date-time (null)
- **CourseReasonRequest**: `reason` string (required)
- **CourseReport**: `computed_at` date-time (required); `min_cell` integer (required); `definitions` object (required); `totals` CourseReportTotals (required); `rows` [CourseReportRow] (required)
- **CourseReportCell**: `district` string (required); `activated` integer (required, null); `hidden` boolean (required)
- **CourseReportRow**: `batch` CourseBatch (required); `printed` integer (required); `sold` integer (required, null); `activated` integer (required); `revoked` integer (required); `void` integer (required); `activation_rate` double (required, null); `districts` [CourseReportCell] (required)
- **CourseReportTotals**: `printed` integer (required); `sold` integer (required); `activated` integer (required); `revoked` integer (required); `void` integer (required); `activation_rate` double (required, null)
- **CourseRevision**: `id` integer (required, read-only); `chapter` CourseRevisionChapter (required, read-only); `title` string (required); `target_minutes` integer; `status` CourseRevisionStatusEnum (required, read-only); `status_label` string (required, read-only); `submitted_by` CoursePerson (required, null, read-only); `submitted_at` date-time (required, null, read-only); `reviewer` CoursePerson (required, null, read-only); `publish_at` date-time (required, null, read-only); `minutes` integer (required, read-only); `clips` [CourseOutlineClip] (required, read-only); `cards` integer (required, read-only); `items` integer (required, read-only); `transitions` [CourseTransitionEnum] (required, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **CourseRevisionChapter**: `id` integer (required); `number` integer (required); `title` string (required); `subject` integer (required); `subject_code` string (required)
- **CourseRevisionStatusEnum**: one of `draft`, `published`, `review`, `approved`
- **CourseRowKindEnum**: one of `clips`, `cards`, `items`
- **CourseSubject**: `id` integer (required); `code` string (required); `name` string (required); `chapters` integer (required); `published` integer (required); `in_review` integer (required); `scheduled` integer (required); `clips` integer (required); `failed` integer (required); `cards` integer (required); `items` integer (required); `bin` integer (required)
- **CourseTransitionEnum**: one of `submit`, `approve`, `needs_changes`, `publish`, `unpublish`
- **CourseVersion**: `id` integer (required); `at` date-time (required); `by` integer (required, null); `type` CourseVersionTypeEnum (required); `reason` string (required, null); `changes` [object] (required)
- **CourseVersionTypeEnum**: one of `+`, `~`, `-`
- **CourseVoidRequest**: `reason` string (required)
- **CourseWeek**: `week` date (required); `redeemed` integer (required)
- **CredentialsRequest**: `reason` string (required); `mode` IntegrationModeEnum (required); `credentials` object (required)
- **Customer**: `id` integer (required, read-only); `email` string (required, read-only); `phone` string (required, read-only); `full_name` string (required); `class_level` any (null); `board` string (required, read-only); `district` string; `under_18` boolean (required, read-only); `status` string (required, read-only); `consent` string (required, read-only); `email_verified` boolean (required, read-only); `login_phone_verified` boolean; `created` date-time (required, read-only); `last_login` date-time (null); `age_band` string (required, read-only); `consent_method` string (required, read-only); `teacher` string (required, read-only); `mfa_on` boolean (required, read-only); `locked` boolean (required, read-only)
- **CustomerCommerce**: `child` boolean (required); `orders` integer (required); `kept` integer (required); `cancelled` integer (required); `returns` integer (required); `rtos` integer (required); `spent` decimal (required, null); `refunded` decimal (required, null); `lifetime_value` decimal (required, null); `average_order` decimal (required, null); `first_order_at` date-time (required, null); `last_order_at` date-time (required, null); `addresses` [CustomerCommerceAddress] (required, null); `tags` [CustomerCommerceTag] (required, null)
- **CustomerCommerceAddress**: `city` string (required); `district` string (required); `state` string (required); `pin` string (required); `phone` string (required); `is_default` boolean (required)
- **CustomerCommerceTag**: `name` string (required); `orders` integer (required)
- **CustomerConsentPending**: `id` integer (required, read-only); `full_name` string (required); `class_level` any (null); `board` string (required, read-only); `created` date-time (required, read-only); `age_band` string (required, read-only); `email_verified` boolean (required, read-only); `parent_contact` string (required, read-only); `parent_channel` string (required, read-only); `blocking` boolean (required, read-only); `links_sent` integer (required, read-only); `last_link_at` date-time (required, null, read-only); `link_expires_at` string (required, null, read-only); `link_expired` boolean (required, read-only); `links_today` integer (required, read-only); `daily_limit` integer (required, read-only)
- **CustomerConsentRecord**: `id` integer (required); `event` string (required); `method` string (required); `by_parent` boolean (required); `verified_at` date-time (required); `verified_by` integer (required, null); `evidence_ref` string (required); `notice_version` string (required); `created` date-time (required)
- **CustomerConsentVerifyRequest**: `method` ConsentVerifyMethodEnum (required); `evidence_ref` string (required); `reason` string (required)
- **CustomerDetail**: `id` integer (required, read-only); `email` string (required, read-only); `phone` string (required, read-only); `full_name` string (required); `class_level` any (null); `board` string (required, read-only); `district` string; `under_18` boolean (required, read-only); `status` string (required, read-only); `consent` string (required, read-only); `email_verified` boolean (required, read-only); `login_phone_verified` boolean; `created` date-time (required, read-only); `last_login` date-time (null); `age_band` string (required, read-only); `consent_method` string (required, read-only); `teacher` string (required, read-only); `mfa_on` boolean (required, read-only); `locked` boolean (required, read-only); `roles` [string] (required, read-only); `mfa` [string] (required, read-only); `parent_contact` string (required, read-only); `orders` [object] (required, read-only); `consents` [object] (required, read-only); `sessions` [object] (required, read-only); `deletion_due_at` string (required, null, read-only); `parent_link` CustomerParentLink (required, null, read-only); `linked` [CustomerLinked] (required, read-only)
- **CustomerGuest**: `id` integer (required); `name` string (required, read-only); `email` string (required, read-only); `phone` string (required, read-only); `orders` integer (required, read-only); `last_order` string (required); `last_order_at` string (required, null, read-only)
- **CustomerLinked**: `id` integer (required); `full_name` string (required); `relation` string (required)
- **CustomerParentLink**: `sent` integer (required); `last_at` date-time (required, null); `expires_at` date-time (required, null); `expired` boolean (required); `today` integer (required); `daily_limit` integer (required)
- **CustomerRow**: any
- **CustomerTimeline**: `child` boolean (required); `rows` [CustomerTimelineRow] (required); `next_before` string (required, null); `withheld` [string] (required)
- **CustomerTimelineRow**: `at` date-time (required); `kind` string (required); `label` string (required); `href` string (required, null)
- **DarkPatternAudit**: `id` integer (required, read-only); `year` integer (required); `rows` [AuditRow]; `certificate_text` string; `effective_from` date (null); `completed_at` date-time (required, null, read-only); `completed_by` integer (required, null, read-only); `created` date-time (required, read-only); `created_by` integer (required, null, read-only); `has_file` boolean (required, read-only)
- **DarkPatternAuditRequest**: `year` integer (required); `rows` [AuditRowRequest]; `certificate_text` string; `effective_from` date (null)
- **DataRequest**: `id` integer (required, read-only); `kind` DataRequestKindEnum (required); `channel` ChannelEnum (required); `user` integer (null); `requester` string (required); `summary` string (required); `identity_verified` boolean (required, read-only); `identity_note` string (required, read-only); `verified_by` integer (required, null, read-only); `verified_at` date-time (required, null, read-only); `received_at` date-time; `ack_due_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `ack_overdue` boolean (required, read-only); `due_at` date-time (required, read-only); `overdue` boolean (required, read-only); `status` DataRequestStatusEnum (required, read-only); `assignee` integer (null); `notes` string; `details` any; `outcome` DataRequestOutcomeEnum (required, read-only); `response` string (required, read-only); `closed_at` date-time (required, null, read-only); `closed_by` integer (required, null, read-only); `created_by` integer (required, null, read-only)
- **DataRequestKindEnum**: one of `access`, `correction`, `erasure`, `nomination`, `grievance`, `complaint`
- **DataRequestList**: `id` integer (required, read-only); `kind` DataRequestKindEnum (required); `channel` ChannelEnum (required); `user` integer (null); `requester` string (required, read-only); `summary` string (required); `identity_verified` boolean (required, read-only); `identity_note` string (required, read-only); `verified_by` integer (required, null, read-only); `verified_at` date-time (required, null, read-only); `received_at` date-time; `ack_due_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `ack_overdue` boolean (required, read-only); `due_at` date-time (required, read-only); `overdue` boolean (required, read-only); `status` DataRequestStatusEnum (required, read-only); `assignee` integer (null); `notes` string; `details` any; `outcome` DataRequestOutcomeEnum (required, read-only); `response` string (required, read-only); `closed_at` date-time (required, null, read-only); `closed_by` integer (required, null, read-only); `created_by` integer (required, null, read-only)
- **DataRequestOutcomeEnum**: one of `done`, `refused`, `withdrawn`
- **DataRequestRequest**: `kind` DataRequestKindEnum (required); `channel` ChannelEnum (required); `user` integer (null); `requester` string (required); `summary` string (required); `received_at` date-time; `assignee` integer (null); `notes` string; `details` any
- **DataRequestStartRequest**: `kind` DataRequestKindEnum (required); `summary` string
- **DataRequestStatusEnum**: one of `new`, `acknowledged`, `closed`
- **DeadLetterStateEnum**: one of `open`, `replayed`, `discarded`
- **DecisionEnum**: one of `approve`, `reject`
- **DeliveryStat**: `courier` string (required); `district` string (null); `median_days` double (required); `p90_days` double (required); `n` integer (required)
- **Dependencies**: `available` boolean (required); `path` string (required); `generated_at` date-time (required, null); `age_days` integer (required, null); `stale` boolean (required); `commit` string (required); `counts` object (required); `advisories` [Advisory] (required); `versions` object (required); `error` string (required)
- **Detail**: `detail` string (required)
- **DeviceRow**: `kind` string (required); `label` string (required); `ip` string (required); `last_seen` date-time (required, null)
- **DiscardRequest**: `reason` string (required)
- **DisclosureHistory**: `key` string (required); `value` any (required); `effective_from` date-time (required); `changed_by` integer (required, null); `reason` string (required); `created` date-time (required)
- **DisclosureSetting**: `key` string (required); `label` string (required); `kind` any (required); `max_length` integer (required); `public` boolean (required); `value` any (required); `environment` any (required); `source` SettingSourceEnum (required); `effective_from` date-time (required, null); `changed_by` integer (required, null); `reason` string (required)
- **Disclosures**: `settings` [DisclosureSetting] (required); `history` [DisclosureHistory] (required)
- **DisclosuresChangeRequest**: `values` object (required); `reason` string (required)
- **DiscountKindEnum**: one of `percent`, `fixed`
- **EmailFigures**: `rates` EmailRates (required); `suppressed` integer (required); `suppressions_synced` date-time (required, null); `topic_restricted` boolean (required); `webhook_secret_set` boolean (required)
- **EmailRates**: `sent` integer (required); `delivered` integer (required); `bounced` integer (required); `complained` integer (required); `bounce_rate` double (required, null); `complaint_rate` double (required, null); `bounce_limit` double (required); `complaint_limit` double (required)
- **Ended**: `sessions` integer (required); `tokens` integer (required)
- **EntitlementRow**: `id` integer (required); `subject` string (required); `source` string (required); `reference` string (required); `valid_until` date (required, null); `active` boolean (required)
- **EntitlementSourceEnum**: one of `book_code`, `purchase`, `grant`
- **ErasureErase**: `part` string (required); `what` string (required); `count` integer (required)
- **ErasureKeep**: `kind` ErasureKeepKindEnum (required); `part` string (required); `what` string (required); `count` integer (required); `why` string (required); `until` date (required, null); `line` string (required)
- **ErasureKeepKindEnum**: one of `books`, `processing_logs`, `legal_hold`, `intermediary`, `consent`, `statistics`, `by_hand`, `test`
- **ErasureReport**: `erase` [ErasureErase] (required); `keep` [ErasureKeep] (required); `blocks` [string] (required); `can_erase` boolean (required); `notes` [string] (required)
- **ErpAccountStatus**: `id` integer (required); `label` string (required); `mode` string (required); `circuit` string (required); `last_success_at` date-time (required, null); `last_error` string (required)
- **ErpCursor**: `id` integer (required, read-only); `doctype` string (required, read-only); `modified_after` string (required, read-only); `last_name` string (required, read-only); `rows_read` integer (required, read-only); `last_run_at` date-time (required, null, read-only); `last_error` string (required, read-only)
- **ErpCursorStatus**: `doctype` string (required); `modified_after` string (required); `last_run_at` date-time (required, null); `error` string (required)
- **ErpDifference**: `id` integer (required, read-only); `run` integer (required, read-only); `kind` ErpDifferenceKindEnum (required, read-only); `key` string (required, read-only); `platform_value` string (required, read-only); `erp_value` string (required, read-only); `note` string (required, read-only); `resolved_at` date-time (required, null, read-only); `resolved_by` integer (required, null, read-only)
- **ErpDifferenceKindEnum**: one of `invoices`, `credit_notes`, `payments`, `settlements`, `deliveries`, `stock`, `missing`
- **ErpDiscardRequest**: `reason` string (required)
- **ErpHealth**: `enabled` boolean (required); `waiting` integer (required); `dead` integer (required); `oldest_waiting_seconds` integer (required, null); `last_reconciliation` ReconciliationLine (required, null); `key_present` boolean (required); `webhook_secret_set` boolean (required)
- **ErpLink**: `examleaf_ref` string (required); `model` string (required); `object_id` string (required); `doctype` string (required); `name` string (required); `synced_at` date-time (required)
- **ErpMirror**: `email` email (required); `enabled` boolean (required); `role_profiles` [string] (required); `by_role` [ErpRole] (required); `erp_in_use` boolean (required)
- **ErpOutbox**: `id` integer (required, read-only); `aggregate_type` string (required, read-only); `aggregate_id` string (required, read-only); `sequence` integer (required, read-only); `event` string (required, read-only); `examleaf_ref` string (required, read-only); `model` string (required, read-only); `object_id` string (required, read-only); `idempotency_key` string (required, read-only); `payload` any (required, null, read-only); `state` ErpOutboxStateEnum (required, read-only); `attempts` integer (required, read-only); `next_at` date-time (required, read-only); `last_error` string (required, read-only); `created` date-time (required, read-only); `sent_at` date-time (required, null, read-only); `response` any (required, null, read-only); `dead_letter` integer (required, null, read-only)
- **ErpOutboxStateEnum**: one of `pending`, `sending`, `sent`, `failed`, `dead`, `discarded`
- **ErpReconciliationStateEnum**: one of `running`, `done`, `failed`
- **ErpResolveRequest**: `note` string (required)
- **ErpRole**: `role` RoleEnum (required); `profiles` [string] (required)
- **ErpRun**: `id` integer (required, read-only); `date` date (required, read-only); `state` ErpReconciliationStateEnum (required, read-only); `platform_totals` any (required, read-only); `erp_totals` any (required, read-only); `differences_count` integer (required, read-only); `started_at` date-time (required, read-only); `finished_at` date-time (required, null, read-only); `error` string (required, read-only)
- **ErpRunDetail**: `id` integer (required, read-only); `date` date (required, read-only); `state` ErpReconciliationStateEnum (required, read-only); `platform_totals` any (required, read-only); `erp_totals` any (required, read-only); `differences_count` integer (required, read-only); `started_at` date-time (required, read-only); `finished_at` date-time (required, null, read-only); `error` string (required, read-only); `differences` [ErpDifference] (required, read-only)
- **ErpRunStatus**: `id` integer (required); `date` date (required); `state` string (required); `differences` integer (required); `open_differences` integer (required); `finished_at` date-time (required, null)
- **ErpStatus**: `enabled` boolean (required); `mode` string (required); `flows` object (required); `pull_stock` boolean (required); `pull_b2b` boolean (required); `stock_projection` boolean (required); `account` ErpAccountStatus (required, null); `outbox` object (required); `oldest_waiting_at` date-time (required, null); `oldest_waiting_seconds` integer (required, null); `held_aggregates` integer (required); `cursors` [ErpCursorStatus] (required); `last_reconciliation` ErpRunStatus (required, null)
- **ErrorReportCategoryEnum**: one of `wrong_answer`, `typo`, `marks`, `unclear`, `display`, `other`, `item_analysis`
- **ErrorReportStateEnum**: one of `reported`, `confirmed`, `rejected`, `fixed_online`, `fixed_in_printing`
- **ErrorsFigures**: `host` string (required)
- **ExportRequest**: `filters` object
- **ExtendRequest**: `entitlement` integer (required); `days` integer (required); `reason` string (required)
- **Extra**: `webhook` RazorpayHealth; `sms` SmsFigures; `email` EmailFigures; `storage` StorageFigures; `google` GoogleFigures; `errors` ErrorsFigures; `erp` ErpHealth; `phase` string
- **Failure**: `id` integer (required, read-only); `account` integer (required, null, read-only); `operation` string (required, read-only); `task_name` string (required, read-only); `args` any (required, read-only); `attempts` integer (required, read-only); `last_error` string (required, read-only); `state` DeadLetterStateEnum (required, read-only); `discard_reason` string (required, read-only); `resolved_at` date-time (required, null, read-only); `resolved_by` integer (required, null, read-only); `created` date-time (required, read-only); `erp_outbox` integer (required, null, read-only)
- **FinanceDocumentErp**: `number` string (required); `kind` TaxDocumentKindEnum (required); `state` FinanceDocumentErpStateEnum (required); `doctype` string (required, null); `name` string (required, null); `synced_at` date-time (required, null); `outbox` [object] (required)
- **FinanceDocumentErpStateEnum**: one of `mirrored`, `waiting`, `failed`, `dead`, `discarded`, `not_sent`, `off`, `test`
- **FinanceFetchRequest**: `day` date (required); `dry_run` boolean
- **FinanceLineRef**: `id` integer (required); `order` string (required, null); `amount` decimal (required, null)
- **FinanceLink**: `kind` FinanceLinkKindEnum (required); `id` integer (required); `order` string (required, null); `invoice` string (required, null); `amount` decimal (required, null); `state` FinanceLinkStateEnum (required); `url` string (required); `razorpay_link_id` string (required); `razorpay_payment_id` string (required, null); `sent_at` date-time (required); `last_sent_at` date-time (required, null); `expires_at` date-time (required); `paid_at` date-time (required, null); `created_by` string (required); `posted_at` date-time (required, null); `erp_name` string (required); `livemode` boolean (required); `is_test` boolean (required)
- **FinanceLinkAnswer**: `kind` FinanceLinkKindEnum (required); `id` integer (required); `order` string (required, null); `invoice` string (required, null); `amount` decimal (required, null); `state` FinanceLinkStateEnum (required); `url` string (required); `razorpay_link_id` string (required); `razorpay_payment_id` string (required, null); `sent_at` date-time (required); `last_sent_at` date-time (required, null); `expires_at` date-time (required); `paid_at` date-time (required, null); `created_by` string (required); `posted_at` date-time (required, null); `erp_name` string (required); `livemode` boolean (required); `is_test` boolean (required); `detail` string (required)
- **FinanceLinkAskRequest**: `order` string; `invoice` string; `action` OrderPaymentLinkActionEnum (required)
- **FinanceLinkKindEnum**: one of `order`, `invoice`
- **FinanceLinkPostedRequest**: `erp_name` string (required)
- **FinanceLinkStateEnum**: one of `sent`, `paid`, `cancelled`, `expired`
- **FinanceMatchRequest**: `line` integer (required); `payment` integer (null); `refund` integer (null); `accept` boolean; `note` string (required)
- **FinancePayment**: `id` integer (required, read-only); `order` string (required, read-only); `order_status` OrderStatusEnum (required, read-only); `method` PaymentMethodEnum (required, read-only); `status` OrderPaymentStatusEnum (required, read-only); `amount` decimal (required, read-only); `razorpay_order_id` string (required, null, read-only); `razorpay_payment_id` string (required, null, read-only); `razorpay_payment_link_id` string (required, null, read-only); `reference` string (required, read-only); `error` string (required, read-only); `livemode` boolean (required, read-only); `is_test` boolean (required, read-only); `stuck` boolean (required, read-only); `is_link` boolean (required, read-only); `fee` decimal (required, null, read-only); `tax` decimal (required, null, read-only); `settlement` FinanceSettlementRef (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **FinancePaymentDetail**: `id` integer (required, read-only); `order` string (required, read-only); `order_status` OrderStatusEnum (required, read-only); `method` PaymentMethodEnum (required, read-only); `status` OrderPaymentStatusEnum (required, read-only); `amount` decimal (required, read-only); `razorpay_order_id` string (required, null, read-only); `razorpay_payment_id` string (required, null, read-only); `razorpay_payment_link_id` string (required, null, read-only); `reference` string (required, read-only); `error` string (required, read-only); `livemode` boolean (required, read-only); `is_test` boolean (required, read-only); `stuck` boolean (required, read-only); `is_link` boolean (required, read-only); `fee` decimal (required, null, read-only); `tax` decimal (required, null, read-only); `settlement` FinanceSettlementRef (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `order_id` integer (required, read-only); `order_total` decimal (required, read-only); `order_placed_at` date-time (required, read-only); `payment_link_url` uri (required, read-only); `refunds` [FinancePaymentRefund] (required, read-only); `webhooks` [FinanceWebhook] (required, read-only); `last_webhook` any (required, read-only); `timeline` [OrderTimelineEntry] (required, read-only)
- **FinancePaymentRefund**: `id` integer (required, read-only); `amount` decimal (required, read-only); `status` RefundStatusEnum (required, read-only); `method` OrderRefundMethodEnum (required, read-only); `speed` RefundSpeedEnum (required, read-only); `razorpay_refund_id` string (required, null, read-only); `arn` string (required, read-only); `created` date-time (required, read-only); `processed_at` date-time (required, null, read-only)
- **FinanceReconciled**: `paid` boolean (required, null); `detail` string (required); `changes` object (required); `payment` FinancePaymentDetail (required)
- **FinanceRequestRow**: `kind` FinanceRowKindEnum (required); `id` integer (required); `order` string (required); `amount` decimal (required, null); `status` string (required); `reference` string (required); `method` string (required); `speed` string (required); `reason` string (required); `arn` string (required); `utr` string (required); `razorpay_refund_id` string (required); `credit_note` string (required, null); `payee_masked` string (required); `payment_method` string (required); `error` string (required); `change_request` integer (required, null); `change_request_status` string (required); `checker` string (required); `rule` string (required); `by` string (required); `created` date-time (required); `done_at` date-time (required, null); `livemode` boolean (required)
- **FinanceRowKindEnum**: one of `request`, `payment`, `refund`
- **FinanceSettlement**: `id` integer (required, read-only); `settlement_id` string (required, read-only); `date` date (required, read-only); `utr` string (required, read-only); `gross` decimal (required, read-only); `fees` decimal (required, read-only); `tax` decimal (required, read-only); `adjustments` decimal (required, read-only); `net` decimal (required, read-only); `state` FinanceSettlementStateEnum (required, read-only); `problem` string (required, read-only); `livemode` boolean (required, read-only); `is_test` boolean (required, read-only); `matched_at` date-time (required, null, read-only); `posted_at` date-time (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **FinanceSettlementDetail**: `id` integer (required, read-only); `settlement_id` string (required, read-only); `date` date (required, read-only); `utr` string (required, read-only); `gross` decimal (required, read-only); `fees` decimal (required, read-only); `tax` decimal (required, read-only); `adjustments` decimal (required, read-only); `net` decimal (required, read-only); `state` FinanceSettlementStateEnum (required, read-only); `problem` string (required, read-only); `livemode` boolean (required, read-only); `is_test` boolean (required, read-only); `matched_at` date-time (required, null, read-only); `posted_at` date-time (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `counts` object (required, read-only); `erp` FinanceSettlementErp (required, null, read-only)
- **FinanceSettlementErp**: `outbox` integer (required); `state` string (required); `attempts` integer (required); `last_error` string (required); `sent_at` date-time (required, null); `name` string (required, null)
- **FinanceSettlementLine**: `id` integer (required, read-only); `type` FinanceSettlementLineTypeEnum (required, read-only); `entity_id` string (required, read-only); `amount` decimal (required, read-only); `fee` decimal (required, read-only); `tax` decimal (required, read-only); `credit` decimal (required, read-only); `debit` decimal (required, read-only); `settled_at` date-time (required, null, read-only); `order_receipt` string (required, read-only); `order` string (required, null, read-only); `payment` FinanceLineRef (required, null, read-only); `refund` FinanceLineRef (required, null, read-only); `link` object (required, null, read-only); `matched` boolean (required, read-only); `matched_at` date-time (required, null, read-only); `matched_by` string (required, read-only); `note` string (required, read-only)
- **FinanceSettlementLineTypeEnum**: one of `payment`, `refund`, `adjustment`
- **FinanceSettlementRef**: `id` integer (required); `settlement_id` string (required); `date` date (required); `utr` string (required); `state` FinanceSettlementStateEnum (required)
- **FinanceSettlementStateEnum**: one of `fetched`, `matched`, `posted`, `mismatched`
- **FinanceToday**: `livemode` boolean (required); `as_of` date-time (required); `rows` [FinanceTodayRow] (required)
- **FinanceTodayKeyEnum**: one of `refunds_to_approve`, `bank_refunds`, `offline_to_approve`, `stuck_payments`, `b2b_to_post`, `settlement_lines`, `settlements_mismatched`, `cod_receivable`, `cod_overdue`, `cod_mismatched`, `credit_notes_refused`, `sync_differences`, `disputes`
- **FinanceTodayRow**: `key` FinanceTodayKeyEnum (required); `count` integer (required, null); `oldest` date (required, null); `amount` decimal (required, null); `configured` boolean (required)
- **FinanceWebhook**: `event_id` string (required); `name` string (required); `received_at` date-time (required)
- **Flag**: `key` string (required); `value` any (required); `effective_from` date-time (required, null); `changed_by` integer (required, null); `reason` string (required); `label` string (required); `group` string (required); `environment` any (required, null); `source` SettingSourceEnum (required)
- **Forecast**: `product` string (required, read-only); `title` string (required, read-only); `district` string (null); `week_start` date (required); `p10` double (required); `p50` double (required); `p90` double (required); `n` integer (required, read-only)
- **FraudSignal**: `id` integer (required, read-only); `kind` FraudSignalKindEnum (required); `label` string (required, read-only); `subject` string (required); `window_start` date-time (required); `window_end` date-time (required); `details` any; `created` date-time (required, read-only); `acknowledged_at` date-time (null); `n` integer (required, read-only)
- **FraudSignalKindEnum**: one of `codes_failed_account`, `codes_failed_ip`, `codes_failed_spike`, `codes_per_account`, `accounts_per_code`, `shared_phone`, `shared_address`, `codes_failed_device`, `codes_undispatched`
- **GoogleFigures**: `domain` string (required); `auto_staff` boolean (required)
- **GrantRequest**: `role` RoleEnum (required); `expires_at` date-time (null); `reason` string (required)
- **Gstr1Request**: `month` string (required); `months` MonthsEnum; `dry_run` boolean
- **HardeningRow**: `key` string (required); `label` string (required); `ok` boolean (required, null); `detail` string (required); `fix` string (required)
- **HeaderSuffixEnum**: one of `P`, `S`, `T`, `G`
- **HoldCreateRequest**: `user` integer (null); `target_type` any; `target_id` string; `reason` LegalHoldReasonEnum (required); `note` string; `until` date (null)
- **Home**: `as_of` date-time (required); `period` HomePeriod (required); `test_mode` boolean (required); `test_orders_left_out` integer (required); `cards` [HomeCard] (required)
- **HomeCard**: `key` string (required); `label` string (required); `group` string (required); `unit` string (required); `value` string (required, null); `definition` string (required); `as_of` date-time (required); `period` HomeSpan (required, null); `href` string (required); `test_mode` boolean (required); `comparison` HomeComparison (required, null); `error` string (required)
- **HomeComparison**: `previous` string (required); `difference` string (required); `percent` string (required, null); `period` HomeSpan (required)
- **HomePeriod**: `start` date (required); `end` date (required); `days` integer (required); `key` string (required); `label` string (required)
- **HomeSpan**: `start` date (required); `end` date (required); `days` integer (required)
- **HsnCode**: `code` string (required, read-only); `kind` HsnKindEnum (required, read-only); `description` string (required, read-only); `uqc` string (required, read-only); `today` HsnRateBrief (required, null, read-only); `next_change` HsnRateBrief (required, null, read-only); `products` integer (required, read-only); `created` date-time (required, read-only)
- **HsnCodeDetail**: `code` string (required, read-only); `kind` HsnKindEnum (required, read-only); `description` string (required, read-only); `uqc` string (required, read-only); `today` HsnRateBrief (required, null, read-only); `next_change` HsnRateBrief (required, null, read-only); `products` integer (required, read-only); `created` date-time (required, read-only); `rates` [HsnRate] (required, read-only); `linked` [HsnProduct] (required, read-only)
- **HsnKindEnum**: one of `hsn`, `sac`
- **HsnProduct**: `id` integer (required, read-only); `slug` string (required, read-only); `title` string (required, read-only); `kind` ProductKindEnum (required, read-only); `gst_rate` decimal (required, read-only); `is_active` boolean (required, read-only); `problem` string (required, read-only)
- **HsnRate**: `id` integer (required, read-only); `rate` decimal (required, read-only); `taxability` TaxabilityEnum (required, read-only); `effective_from` date (required, read-only); `effective_to` date (required, null, read-only); `until` date (required, null, read-only); `notification` string (required, read-only); `serial` string (required, read-only); `note` string (required, read-only); `created` date-time (required, read-only); `created_by` integer (required, null, read-only)
- **HsnRateBrief**: `rate` decimal (required); `taxability` TaxabilityEnum (required); `effective_from` date (required); `notification` string (required)
- **ImpersonateRequest**: `reason` string (required); `ticket` string (required)
- **Impersonation**: `token` string (required); `expires_at` date-time (required)
- **InboundEvent**: `id` integer (required, read-only); `account` integer (required, null, read-only); `state` InboundEventStateEnum (required, read-only); `event_id` string (required, read-only); `sha256` string (required, read-only); `headers` any (required, read-only); `received_at` date-time (required, read-only); `processed_at` date-time (required, null, read-only); `error` string (required, read-only); `body_excerpt` string (required, read-only)
- **InboundEventStateEnum**: one of `accepted`, `duplicate`, `rejected`, `failed`
- **InboxCount**: `open` integer (required); `overdue` integer (required)
- **InboxItem**: `id` integer (required, read-only); `kind` InboxKindEnum (required); `title` string (required); `target_type` string; `target_id` string; `permission` string (required); `assignee` integer (null); `due_at` date-time (null); `overdue` boolean (required, read-only); `snoozed_until` date-time (null); `done_at` date-time (null); `done_by` integer (null); `data` any; `created` date-time
- **InboxKindEnum**: one of `approval`, `teacher_request`, `deletion_request`, `data_request`, `incident`, `failed_job`, `failed_webhook`, `sync_failed`, `reconciliation`, `shipping_exception`, `dead_letter`, `failed_event`, `integration_down`, `tax_threshold`, `credit_note_missing`, `processor_task`, `compliance`, `order_hold`, `return_request`, `bank_refund`, `role_expired`, `offboarding`, `webhook_silent`, `template_idle`, `template_certify`, `backup_stale`, `dependencies_stale`, `scripts_changed`, `review`, `error_report`, `legal_deposit`, `ticket_due`, `ticket_breach`, `ticket_mention`, `settlement`, `b2b_payment`, `fraud_signal`
- **Incident**: `id` integer (required, read-only); `title` string (required); `kind` IncidentKindEnum (required); `detected_at` date-time; `noticed_by` integer (required, null, read-only); `description` string; `systems` string; `data_categories` string; `people_affected` integer (null); `children_affected` boolean; `cert_in_due` date-time (required, read-only); `cert_in_overdue` boolean (required, read-only); `cert_in_reported_at` date-time (null); `cert_in_reference` string; `board_due` date-time (required, read-only); `board_overdue` boolean (required, read-only); `board_notified_at` date-time (null); `board_report_at` date-time (null); `board_reference` string; `notice_text` string; `notices_sent` integer; `notices_sent_at` date-time (null); `actions` string; `root_cause` string; `closed_at` date-time (required, null, read-only); `closed_by` integer (required, null, read-only); `created` date-time (required, read-only)
- **IncidentKindEnum**: one of `data_breach`, `data_leak`, `unauthorised_access`, `malicious_code`, `application_attack`, `denial_of_service`, `loss_of_access`, `other`
- **IncidentRequest**: `title` string (required); `kind` IncidentKindEnum (required); `detected_at` date-time; `description` string; `systems` string; `data_categories` string; `people_affected` integer (null); `children_affected` boolean; `cert_in_reported_at` date-time (null); `cert_in_reference` string; `board_notified_at` date-time (null); `board_report_at` date-time (null); `board_reference` string; `notice_text` string; `notices_sent` integer; `notices_sent_at` date-time (null); `actions` string; `root_cause` string
- **IntegrationModeEnum**: one of `test`, `live`
- **InviteRequest**: `email` email (required); `role` RoleEnum (required); `reason` string (required)
- **ItemStat**: `item` integer (required); `chapter` integer (required, read-only); `kind` string (required, read-only); `text` string (required, read-only); `n` integer (required); `p` double (null); `discrimination` double (null); `flags` any
- **Job**: `id` integer (required, read-only); `kind` JobKindEnum (required, read-only); `state` JobStateEnum (required, read-only); `dry_run` boolean (required, read-only); `params` any (required, read-only); `done` integer (required, read-only); `total` integer (required, read-only); `errors` [JobError] (required, read-only); `result` any (required, read-only); `result_url` string (required, null, read-only); `change_request_id` integer (required, null, read-only); `cancel_requested` boolean (required, read-only); `started_by` integer (required, null, read-only); `created` date-time (required, read-only); `started_at` date-time (required, null, read-only); `finished_at` date-time (required, null, read-only)
- **JobError**: `id` any (required, null); `label` string (required); `message` string (required)
- **JobKindEnum**: one of `audit_export`, `bulk_action`, `erp_initial_load`, `gstr1_export`, `orders_pack`, `orders_print`, `orders_cancel`, `orders_export`, `content_import`, `grievance_export`, `settlement_fetch`, `report_export`, `coupon_codes`, `product_import`, `product_export`, `code_batch`
- **JobStartRequest**: `kind` JobKindEnum (required); `params` object; `dry_run` boolean
- **JobStateEnum**: one of `queued`, `running`, `done`, `failed`, `cancelled`
- **LanguageEnum**: one of `as`, `bn`, `en`
- **LastTest**: `at` date-time (required, null); `ok` boolean (required, null); `message` string (required)
- **LegalDeposit**: `id` integer (required, read-only); `book` integer (required); `book_title` string (required, read-only); `edition` string; `library` LegalDepositLibraryEnum (required); `sent_on` date (required); `proof` string (required); `has_file` boolean (required, read-only); `erp_delivery_note` string; `created_by` integer (required, null, read-only); `created` date-time (required, read-only)
- **LegalDepositLibraryEnum**: one of `national_library`, `connemara`, `asiatic_society`, `delhi_public_library`
- **LegalDepositRequest**: `book` integer (required); `edition` string; `library` LegalDepositLibraryEnum (required); `sent_on` date (required); `proof` string (required); `proof_file` binary; `erp_delivery_note` string
- **LegalHold**: `id` integer (required, read-only); `user` integer (required, null, read-only); `target_type` string (required, read-only); `target_id` string (required, read-only); `target_label` string (required, read-only); `reason` LegalHoldReasonEnum (required, read-only); `note` string (required, read-only); `until` date (required, null, read-only); `active` boolean (required, read-only); `created` date-time (required, read-only); `created_by` integer (required, null, read-only); `released_at` date-time (required, null, read-only); `released_by` integer (required, null, read-only); `release_reason` string (required, read-only)
- **LegalHoldReasonEnum**: one of `dispute`, `chargeback`, `claim`, `investigation`, `other`
- **LevelEnum**: one of `ok`, `watch`, `act`
- **LimitChange**: `name` string (required); `before` integer (required, null); `after` integer (required, null)
- **LogRow**: `key` string (required); `what` string (required); `where` string (required); `kept` string (required); `readers` string (required); `days` integer (required, null); `meets_retention` boolean (required, null)
- **Logs**: `retention_days` integer (required); `rule` string (required); `dpdp_from` date (required); `inventory` [LogRow] (required); `time` SystemClock (required); `cert_in` Contact (required)
- **Manifest**: `url` uri (required)
- **ManifestRequestRequest**: `shipments` [integer] (required)
- **Message**: `id` integer (required, read-only); `direction` TicketDirectionEnum (required, read-only); `channel` TicketChannelEnum (required, read-only); `author` integer (required, null, read-only); `author_name` string (required, read-only); `automatic` boolean (required, read-only); `body` string (required, read-only); `sent_at` date-time (required, read-only); `mentions` [integer] (required, read-only); `attachments` [Attachment] (required, read-only); `other_sender` boolean (required, read-only); `dropped` [string] (required, read-only)
- **MessageChannelEnum**: one of `email`, `sms`, `whatsapp`
- **MessageCreateChannelEnum**: one of `email`, `phone`, `whatsapp`, `nch`
- **MessageCreateDirectionEnum**: one of `out`, `note`
- **MessageCreateRequest**: `direction` MessageCreateDirectionEnum (required); `body` string (required); `channel` any; `mentions` [integer]
- **MissingDeposit**: `book` integer (required); `title` string (required); `edition` string (required); `subject` string (required); `published_on` date (required); `due_on` date (required); `overdue` boolean (required); `missing` [LegalDepositLibraryEnum] (required)
- **ModeRequest**: `reason` string (required); `mode` ConnectionModeEnum (required)
- **MonthsEnum**: one of `1`, `3`
- **NdrActionActionEnum**: one of `re-attempt`, `return`, `fake-attempt`
- **NdrActionRequest**: `action` NdrActionActionEnum (required); `comments` string (required); `deferred_date` date; `phone` string; `address1` string; `address2` string
- **NeedsChangesRequest**: `comment` string (required); `field` string
- **NewHsnCodeRequest**: `code` string (required); `kind` HsnKindEnum (required); `description` string (required); `uqc` string; `first_rate` NewHsnRateRequest (required)
- **NewHsnRateRequest**: `rate` decimal (required); `taxability` TaxabilityEnum (required); `effective_from` date (required); `effective_to` date (null); `notification` string (required); `serial` string; `note` string
- **Note**: `id` integer (required, read-only); `target_type` string (required); `target_id` string (required); `author` integer (required, read-only); `body` string (required); `pinned` boolean; `created` date-time (required, read-only)
- **NoteRequest**: `target_type` string (required); `target_id` string (required); `body` string (required); `pinned` boolean
- **NullEnum**: null
- **Offboarded**: `roles` [string] (required); `scopes` integer (required); `api_keys` integer (required); `change_requests` integer (required); `sessions` integer (required); `tokens` integer (required); `offboarding` integer (required)
- **Offboarding**: `id` integer (required, read-only); `user` integer (required); `started_by` integer (null); `reason` string (required); `started_at` date-time; `finished_at` date-time (null); `steps` [OffboardingStep] (required, read-only)
- **OffboardingStep**: `key` string (required); `label` string (required, read-only); `kind` OffboardingStepKindEnum (required); `state` OffboardingStepStateEnum; `detail` string; `done_at` date-time (null); `done_by` integer (null)
- **OffboardingStepKindEnum**: one of `auto`, `manual`
- **OffboardingStepStateEnum**: one of `done`, `todo`, `not_needed`
- **OffboardingTickRequest**: `step` string (required); `state` OffboardingStepStateEnum (required); `note` string
- **OfferScopeEnum**: one of `cart`, `products`, `categories`, `collections`
- **OfferStat**: `coupon` string (required, read-only); `offer` string (required, read-only); `period_start` date (required); `period_end` date (required); `orders` integer (required); `revenue` decimal (required); `discount_cost` decimal (required); `period_orders` integer (required); `baseline_orders` integer (required); `baseline_revenue` decimal (required); `interval_low` double (null); `interval_high` double (null); `note` string (required); `n` integer (required, read-only)
- **OrderAction**: `name` string (required); `permission` string (required); `primary` boolean (required)
- **OrderActionRequest**: `order` string
- **OrderAddress**: `name` string (required); `phone` string (required); `line1` string (required); `line2` string (required); `city` string (required); `district` string (required); `state` string (required); `pin` string (required)
- **OrderCancelRequest**: `reason` string (required); `customer_requested` boolean; `restock` boolean
- **OrderCourier**: `name` string (required); `tracking_number` string (required)
- **OrderCustomer**: `id` integer (required, null); `name` string (required); `email` string (required); `phone` string (required); `is_minor` boolean (required)
- **OrderDetail**: `id` integer (required, read-only); `number` string (required, null, read-only); `created` date-time (required, read-only); `placed_at` date-time (required, null, read-only); `status` OrderStatusEnum (required, read-only); `status_label` string (required, read-only); `payment_method` PaymentMethodEnum (required, read-only); `total` decimal (required, read-only); `items` [string] (required, read-only); `customer` OrderCustomer (required, read-only); `courier` OrderCourier (required, null, read-only); `parcel` string (required, null, read-only); `tags` [string] (required, read-only); `held` boolean (required, read-only); `hold_reason` string (required, read-only); `risk_bucket` any (required, read-only); `is_test` boolean (required, read-only); `is_cod` boolean (required, read-only); `has_returns` boolean (required, read-only); `staff_order` boolean (required, read-only); `livemode` boolean (required, read-only); `subtotal` decimal (required, read-only); `discount` decimal (required, read-only); `shipping_fee` decimal (required, read-only); `coupon_code` string (required, read-only); `savings` [OrderSaving] (required, read-only); `address` OrderAddress (required, read-only); `lines` [OrderLine] (required, read-only); `payments` [OrderPayment] (required, read-only); `refunds` [OrderRefund] (required, read-only); `documents` [OrderDocument] (required, read-only); `shipments` [OrderParcel] (required, read-only); `returns` [ReturnRow] (required, read-only); `hold` OrderHold (required, null, read-only); `risk_reasons` [string] (required, read-only); `is_digital` boolean (required, read-only); `quote` string (required, null, read-only); `created_by` string (required, null, read-only); `actions` [OrderAction] (required, read-only); `refund` OrderRefundOptions (required, read-only); `erp` [OrderErpLink] (required, read-only); `timeline` [OrderTimelineEntry] (required, read-only); `modified` date-time (required, read-only)
- **OrderDocument**: `kind` OrderDocumentKindEnum (required); `id` integer (required); `number` string (required); `created` date-time (required); `ready` boolean (required); `url` string (required); `amount` decimal (required, null)
- **OrderDocumentKindEnum**: one of `invoice`, `credit_note`
- **OrderDocumentsQueued**: `detail` string (required)
- **OrderErpLink**: `model` string (required); `object_id` string (required); `doctype` string (required); `name` string (required); `synced_at` date-time (required)
- **OrderHold**: `at` date-time (required); `by` string (required); `reason` string (required)
- **OrderHoldReasonRequest**: `reason` string (required)
- **OrderInvoiceSent**: `detail` string (required)
- **OrderLine**: `id` integer (required); `product` string (required); `title` string (required); `isbn` string (required); `hsn_code` string (required); `gst_rate` decimal (required); `mrp` decimal (required, read-only); `unit_price` decimal (required, read-only); `quantity` integer (required); `line_total` decimal (required, read-only); `discount` decimal (required, read-only); `invoiced` decimal (required, read-only); `refunded` integer (required); `returnable` integer (required); `digital` boolean (required)
- **OrderLineAskRequest**: `item` integer (required); `quantity` integer (required)
- **OrderNotified**: `detail` string (required)
- **OrderNotifyKindEnum**: one of `placed`, `paid`, `packed`, `shipped`, `delivered`, `cancelled`, `refunded`
- **OrderNotifyRequest**: `kind` OrderNotifyKindEnum (required)
- **OrderOfflinePaymentRequest**: `reference` string (required); `reason` string (required)
- **OrderParcel**: `id` integer (required, read-only); `order` string (required, read-only); `courier` CourierEnum (required, read-only); `tracking_number` string (required, read-only); `tracking_url` uri (required, read-only); `shipped_at` date-time (required, read-only); `delivered_at` date-time (required, null, read-only); `detail` ParcelDetail (required, null, read-only); `last_event` ShipmentEvent (required, null, read-only)
- **OrderPayment**: `id` integer (required, read-only); `method` PaymentMethodEnum (required, read-only); `amount` decimal (required, read-only); `status` OrderPaymentStatusEnum (required, read-only); `razorpay_order_id` string (required, null, read-only); `razorpay_payment_id` string (required, null, read-only); `payment_link_url` uri (required, read-only); `reference` string (required, read-only); `error` string (required, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `refundable` decimal (required, read-only); `older_than_6_months` boolean (required, read-only)
- **OrderPaymentLinkActionEnum**: one of `send`, `cancel`
- **OrderPaymentLinkRequest**: `action` OrderPaymentLinkActionEnum
- **OrderPaymentLinkSent**: `detail` string (required); `url` string (required)
- **OrderPaymentStatusEnum**: one of `created`, `authorized`, `captured`, `failed`, `refunded`
- **OrderRefund**: `id` integer (required, read-only); `amount` decimal (required, read-only); `status` RefundStatusEnum (required, read-only); `reason` string (required, read-only); `method` OrderRefundMethodEnum (required, read-only); `speed` RefundSpeedEnum (required, read-only); `lines` [OrderRefundLine] (required, read-only); `shipping_amount` decimal (required, read-only); `restock` boolean (required, read-only); `payee_masked` string (required, read-only); `utr` string (required, read-only); `arn` string (required, read-only); `razorpay_refund_id` string (required, null, read-only); `change_request` integer (required, null, read-only); `created` date-time (required, read-only); `processed_at` date-time (required, null, read-only); `error` string (required, read-only); `credit_note` string (required, null, read-only); `payment_method` string (required, read-only)
- **OrderRefundAskMethodEnum**: one of `source`, `bank`
- **OrderRefundAskRequest**: `lines` [OrderLineAskRequest]; `shipping` decimal; `restock` boolean; `method` OrderRefundAskMethodEnum; `speed` RefundSpeedEnum; `payee` RefundPayeeRequest; `customer_agreed` boolean; `reason` string (required); `return` integer
- **OrderRefundAsked**: `id` integer (required, read-only); `action` string (required); `label` string (required, read-only); `target_type` string; `target_id` string; `target_label` string; `payload` any; `payload_sha256` string (required); `amount` decimal (null); `maker` integer (required); `reason` string (required); `rule` string; `status` ChangeRequestStatusEnum; `expires_at` date-time (required); `overridden` boolean; `checker` string (required, read-only); `approvals` [Approval] (required, read-only); `result` any (null); `executed_by` integer (null); `executed_at` date-time (null); `created` date-time (required, read-only); `modified` date-time (required, read-only); `warnings` [string] (required, read-only)
- **OrderRefundLine**: `item` integer (required); `quantity` integer (required); `amount` decimal (required)
- **OrderRefundMethodEnum**: one of `source`, `bank`, `none`
- **OrderRefundOptions**: `payment` integer (required, null); `payment_method` string (required, null); `refundable` decimal (required); `shipping_left` decimal (required); `methods` [string] (required); `cancels` boolean (required); `payment_age_days` integer (required, null); `warnings` [string] (required)
- **OrderRiskEnum**: one of `low`, `medium`, `high`
- **OrderRow**: `id` integer (required, read-only); `number` string (required, null, read-only); `created` date-time (required, read-only); `placed_at` date-time (required, null, read-only); `status` OrderStatusEnum (required, read-only); `status_label` string (required, read-only); `payment_method` PaymentMethodEnum (required, read-only); `total` decimal (required, read-only); `items` [string] (required, read-only); `customer` OrderCustomer (required, read-only); `courier` OrderCourier (required, null, read-only); `parcel` string (required, null, read-only); `tags` [string] (required, read-only); `held` boolean (required, read-only); `hold_reason` string (required, read-only); `risk_bucket` any (required, read-only); `is_test` boolean (required, read-only); `is_cod` boolean (required, read-only); `has_returns` boolean (required, read-only); `staff_order` boolean (required, read-only); `livemode` boolean (required, read-only)
- **OrderSaving**: `label` string (required); `amount` decimal (required)
- **OrderShipRequest**: `courier` CourierEnum (required); `tracking_number` string (required); `tracking_url` any
- **OrderShipment**: `courier` string (required); `tracking_number` string (required); `tracking_url` string (required); `shipped_at` date-time (required); `delivered_at` date-time (required, null)
- **OrderStatusEnum**: one of `pending`, `paid`, `packed`, `shipped`, `delivered`, `cancelled`, `refunded`
- **OrderTagsRequest**: `add` [string]; `remove` [string]
- **OrderTimelineEntry**: `at` date-time (required); `kind` string (required); `label` string (required); `actor` string (required); `details` object (required)
- **OwnSession**: `id` integer (required); `browser` string (required); `system` string (required); `place` string (required); `created_at` date-time (required); `last_seen_at` date-time (required); `current` boolean (required)
- **OwnSessionsEnded**: `sessions` integer (required); `tokens` integer (required)
- **PackagingEnum**: one of `flyer`, `box`
- **PackingRow**: `number` string (required); `placed_at` date-time (required); `payment_method` string (required); `is_cod` boolean (required); `total` decimal (required); `risk_bucket` string (required); `tags` [string] (required); `destination` string (required); `weight_g` integer (required, null); `pick` [PickLine] (required)
- **PaginatedApiKeyList**: `next` uri (null); `previous` uri (null); `results` [ApiKey] (required)
- **PaginatedAuditEventList**: `next` uri (null); `previous` uri (null); `results` [AuditEvent] (required)
- **PaginatedBacktestList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [Backtest] (required)
- **PaginatedCallList**: `next` uri (null); `previous` uri (null); `results` [Call] (required)
- **PaginatedCatalogueAlertRowList**: `next` uri (null); `previous` uri (null); `results` [CatalogueAlertRow] (required)
- **PaginatedCatalogueCollectionList**: `next` uri (null); `previous` uri (null); `results` [CatalogueCollection] (required)
- **PaginatedCatalogueCouponList**: `next` uri (null); `previous` uri (null); `results` [CatalogueCoupon] (required)
- **PaginatedCatalogueOfferList**: `next` uri (null); `previous` uri (null); `results` [CatalogueOffer] (required)
- **PaginatedCatalogueProductRowList**: `next` uri (null); `previous` uri (null); `results` [CatalogueProductRow] (required)
- **PaginatedCatalogueShippingRateList**: `next` uri (null); `previous` uri (null); `results` [CatalogueShippingRate] (required)
- **PaginatedCatalogueStockRowList**: `next` uri (null); `previous` uri (null); `results` [CatalogueStockRow] (required)
- **PaginatedChangeRequestList**: `next` uri (null); `previous` uri (null); `results` [ChangeRequest] (required)
- **PaginatedChapterStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ChapterStat] (required)
- **PaginatedCodRemittanceList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [CodRemittance] (required)
- **PaginatedCodeActivationList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [CodeActivation] (required)
- **PaginatedCohortStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [CohortStat] (required)
- **PaginatedContentBookList**: `next` uri (null); `previous` uri (null); `results` [ContentBook] (required)
- **PaginatedContentErratumList**: `next` uri (null); `previous` uri (null); `results` [ContentErratum] (required)
- **PaginatedContentPaperList**: `next` uri (null); `previous` uri (null); `results` [ContentPaper] (required)
- **PaginatedContentQuestionList**: `next` uri (null); `previous` uri (null); `results` [ContentQuestion] (required)
- **PaginatedContentReportList**: `next` uri (null); `previous` uri (null); `results` [ContentReport] (required)
- **PaginatedContentReviewList**: `next` uri (null); `previous` uri (null); `results` [ContentReview] (required)
- **PaginatedContentSolutionList**: `next` uri (null); `previous` uri (null); `results` [ContentSolution] (required)
- **PaginatedCourseBatchList**: `next` uri (null); `previous` uri (null); `results` [CourseBatch] (required)
- **PaginatedCourseBinRowList**: `next` uri (null); `previous` uri (null); `results` [CourseBinRow] (required)
- **PaginatedCourseEntitlementList**: `next` uri (null); `previous` uri (null); `results` [CourseEntitlement] (required)
- **PaginatedCourseItemRowList**: `next` uri (null); `previous` uri (null); `results` [CourseItemRow] (required)
- **PaginatedCustomerConsentPendingList**: `next` uri (null); `previous` uri (null); `results` [CustomerConsentPending] (required)
- **PaginatedCustomerRowList**: `next` uri (null); `previous` uri (null); `results` [CustomerRow] (required)
- **PaginatedDarkPatternAuditList**: `next` uri (null); `previous` uri (null); `results` [DarkPatternAudit] (required)
- **PaginatedDataRequestListList**: `next` uri (null); `previous` uri (null); `results` [DataRequestList] (required)
- **PaginatedDeliveryStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [DeliveryStat] (required)
- **PaginatedErpCursorList**: `next` uri (null); `previous` uri (null); `results` [ErpCursor] (required)
- **PaginatedErpDifferenceList**: `next` uri (null); `previous` uri (null); `results` [ErpDifference] (required)
- **PaginatedErpOutboxList**: `next` uri (null); `previous` uri (null); `results` [ErpOutbox] (required)
- **PaginatedErpRunList**: `next` uri (null); `previous` uri (null); `results` [ErpRun] (required)
- **PaginatedFailureList**: `next` uri (null); `previous` uri (null); `results` [Failure] (required)
- **PaginatedFinanceLinkList**: `next` uri (null); `previous` uri (null); `results` [FinanceLink] (required)
- **PaginatedFinancePaymentList**: `next` uri (null); `previous` uri (null); `results` [FinancePayment] (required)
- **PaginatedFinanceRequestRowList**: `next` uri (null); `previous` uri (null); `results` [FinanceRequestRow] (required)
- **PaginatedFinanceSettlementLineList**: `next` uri (null); `previous` uri (null); `results` [FinanceSettlementLine] (required)
- **PaginatedFinanceSettlementList**: `next` uri (null); `previous` uri (null); `results` [FinanceSettlement] (required)
- **PaginatedForecastList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [Forecast] (required)
- **PaginatedFraudSignalList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [FraudSignal] (required)
- **PaginatedHsnCodeList**: `next` uri (null); `previous` uri (null); `results` [HsnCode] (required)
- **PaginatedInboundEventList**: `next` uri (null); `previous` uri (null); `results` [InboundEvent] (required)
- **PaginatedInboxItemList**: `next` uri (null); `previous` uri (null); `results` [InboxItem] (required)
- **PaginatedIncidentList**: `next` uri (null); `previous` uri (null); `results` [Incident] (required)
- **PaginatedItemStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ItemStat] (required)
- **PaginatedJobList**: `next` uri (null); `previous` uri (null); `results` [Job] (required)
- **PaginatedLegalDepositList**: `next` uri (null); `previous` uri (null); `results` [LegalDeposit] (required)
- **PaginatedLegalHoldList**: `next` uri (null); `previous` uri (null); `results` [LegalHold] (required)
- **PaginatedOfferStatList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [OfferStat] (required)
- **PaginatedOrderRowList**: `next` uri (null); `previous` uri (null); `results` [OrderRow] (required)
- **PaginatedPackingRowList**: `next` uri (null); `previous` uri (null); `results` [PackingRow] (required)
- **PaginatedParcelList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [Parcel] (required)
- **PaginatedPersonList**: `next` uri (null); `previous` uri (null); `results` [Person] (required)
- **PaginatedPickupLocationList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [PickupLocation] (required)
- **PaginatedPrintRunAdviceList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [PrintRunAdvice] (required)
- **PaginatedProcessorList**: `next` uri (null); `previous` uri (null); `results` [Processor] (required)
- **PaginatedQuoteRowList**: `next` uri (null); `previous` uri (null); `results` [QuoteRow] (required)
- **PaginatedReturnRowList**: `next` uri (null); `previous` uri (null); `results` [ReturnRow] (required)
- **PaginatedSavedReplyList**: `next` uri (null); `previous` uri (null); `results` [SavedReply] (required)
- **PaginatedSavedViewList**: `next` uri (null); `previous` uri (null); `results` [SavedView] (required)
- **PaginatedShipmentChargeList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ShipmentCharge] (required)
- **PaginatedShippingExceptionList**: `count` integer (required); `next` uri (null); `previous` uri (null); `results` [ShippingException] (required)
- **PaginatedStaffInviteList**: `next` uri (null); `previous` uri (null); `results` [StaffInvite] (required)
- **PaginatedTaxDocumentList**: `next` uri (null); `previous` uri (null); `results` [TaxDocument] (required)
- **PaginatedTicketList**: `next` uri (null); `previous` uri (null); `results` [Ticket] (required)
- **PaperPublishRequest**: `is_published` boolean; `is_sample` boolean
- **PaperQr**: `url` uri (required); `png` string (required)
- **Parcel**: `id` integer (required, read-only); `order` string (required, read-only); `courier` CourierEnum (required, read-only); `tracking_number` string (required, read-only); `tracking_url` uri (required, read-only); `shipped_at` date-time (required, read-only); `delivered_at` date-time (required, null, read-only); `detail` ParcelDetail (required, null, read-only)
- **ParcelDetail**: `carrier` CarrierEnum (required, read-only); `account` integer (required, null, read-only); `status` any (required, null, read-only); `reference` string (required, read-only); `external_order_id` string (required, read-only); `external_shipment_id` string (required, read-only); `courier_company_id` integer (required, null, read-only); `courier_name` string (required, read-only); `weight_g` integer (required, null, read-only); `length_cm` integer (required, null, read-only); `breadth_cm` integer (required, null, read-only); `height_cm` integer (required, null, read-only); `charged_weight_g` integer (required, null, read-only); `quoted_rate` decimal (required, null, read-only); `cod_amount` decimal (required, null, read-only); `declared_value` decimal (required, null, read-only); `last_event_at` date-time (required, null, read-only); `pickup_location` integer (required, null, read-only); `pickup_date` date (required, null, read-only); `manifested_at` date-time (required, null, read-only); `has_label` boolean (required, read-only); `has_photo` boolean (required, read-only)
- **ParcelHistory**: `id` integer (required, read-only); `order` string (required, read-only); `courier` CourierEnum (required, read-only); `tracking_number` string (required, read-only); `tracking_url` uri (required, read-only); `shipped_at` date-time (required, read-only); `delivered_at` date-time (required, null, read-only); `detail` ParcelDetail (required, null, read-only); `events` [ShipmentEvent] (required, read-only); `exceptions` [ShippingException] (required, read-only); `charges` [ShipmentCharge] (required, read-only); `cod_remittance` CodRemittance (required, null, read-only)
- **ParcelStatusEnum**: one of `booked`, `pickup_problem`, `in_transit`, `out_for_delivery`, `delivered`, `delivery_failed`, `returning`, `returned`, `lost_or_damaged`, `cancelled`, `partial`
- **ParentConfirmationRequest**: `evidence_ref` string (required)
- **PastTicket**: `number` string (required); `subject` string (required); `category` string (required); `status` string (required); `received_at` date-time (required)
- **PatchedCatalogueAttributeDefRequest**: `name` string; `code` string; `kind` AttributeKindEnum; `choices` string; `position` integer
- **PatchedCatalogueCategoryWriteRequest**: `name` string; `slug` string; `description` string; `parent` string (null)
- **PatchedCatalogueCollectionWriteRequest**: `slug` string; `name` string; `description` string; `is_active` boolean; `position` integer; `products` [string]
- **PatchedCatalogueCouponWriteRequest**: `code` string; `kind` DiscountKindEnum; `value` decimal; `min_order` decimal; `valid_from` date-time (null); `valid_until` date-time (null); `max_uses` integer (null); `max_uses_per_customer` integer (null); `is_active` boolean; `description` string; `note` string; `include_products` [string]; `include_categories` [string]; `exclude_products` [string]; `exclude_categories` [string]; `first_order_only` boolean; `stackable` boolean; `single_use` boolean; `reason` string
- **PatchedCatalogueOfferWriteRequest**: `name` string; `banner` string; `kind` DiscountKindEnum; `value` decimal; `scope` OfferScopeEnum; `products` [string]; `categories` [string]; `collections` [string]; `min_quantity` integer; `min_value` decimal; `valid_from` date-time (null); `valid_until` date-time (null); `max_uses` integer (null); `max_uses_per_customer` integer (null); `combinable` boolean; `is_active` boolean; `show_countdown` boolean; `reason` string
- **PatchedCataloguePictureChangeRequest**: `alt` string; `position` integer
- **PatchedCatalogueProductWriteRequest**: `title` string; `slug` string; `kind` ProductKindEnum; `is_active` boolean; `subject` integer (null); `book` string (null); `isbn` string; `pages` integer (null); `description` string; `product_type` integer (null); `attributes` object; `categories` [string]; `related` [string]; `weight_grams` integer; `length_cm` integer (null); `width_cm` integer (null); `height_cm` integer (null); `packaging` any; `seo_title` string; `seo_description` string; `hsn` string (null); `tax_treatment` TaxTreatmentEnum; `tax_note` string; `tax_note_date` date (null); `mrp` decimal; `price` decimal; `reason` string
- **PatchedCatalogueShippingRateWriteRequest**: `name` string; `states` [CatalogueStatesEnum]; `fee` decimal; `free_above` decimal (null); `is_active` boolean; `reason` string
- **PatchedCatalogueTypeRenameRequest**: `name` string
- **PatchedContentBookRequest**: `title` string; `subject` integer; `edition` string; `slug` string; `cover` string; `isbn` string; `format` BookFormatEnum; `published_on` date (null)
- **PatchedContentPaperDetailRequest**: `title` string; `tier` TierEnum; `number` integer; `full_marks` integer; `pass_marks` integer; `time_text` string; `header_json` ContentHeaderRequest
- **PatchedContentReportUpdateRequest**: `staff_note` string; `public` boolean; `printing` any; `step` integer (null)
- **PatchedCourseCardRequest**: `front` string; `back` string; `tags` [string]
- **PatchedCourseChapterRequest**: `must_do` string
- **PatchedCourseClipRequest**: `title` string; `kind` ClipKindEnum; `notes` string; `is_free_preview` boolean; `tags` [string]
- **PatchedCourseItemRequest**: `kind` QuizItemKindEnum; `text` string; `options` any; `answer` string; `explanation` string; `topic` string; `marks` integer; `difficulty` any; `bloom` any; `tags` [string]
- **PatchedCourseRevisionRequest**: `title` string; `target_minutes` integer
- **PatchedDarkPatternAuditRequest**: `year` integer; `rows` [AuditRowRequest]; `certificate_text` string; `effective_from` date (null)
- **PatchedDataRequestRequest**: `kind` DataRequestKindEnum; `channel` ChannelEnum; `user` integer (null); `requester` string; `summary` string; `received_at` date-time; `assignee` integer (null); `notes` string; `details` any
- **PatchedIncidentRequest**: `title` string; `kind` IncidentKindEnum; `detected_at` date-time; `description` string; `systems` string; `data_categories` string; `people_affected` integer (null); `children_affected` boolean; `cert_in_reported_at` date-time (null); `cert_in_reference` string; `board_notified_at` date-time (null); `board_report_at` date-time (null); `board_reference` string; `notice_text` string; `notices_sent` integer; `notices_sent_at` date-time (null); `actions` string; `root_cause` string
- **PatchedPickupLocationRequest**: `nickname` string; `address` string; `city` string; `state` string; `pin_code` string; `phone` string; `is_default` boolean; `active` boolean
- **PatchedProcessorRequest**: `name` string; `purpose` string; `data_categories` string; `country` string; `contract_signed_on` date (null); `contract_ends_on` date (null); `active` boolean; `notes` string; `holds_personal_data` boolean; `holds_marketing_data` boolean; `erasure_action` string
- **PatchedQuestionUpdateRequest**: `text_md` string; `table_md` string; `options_json` [string]; `marks_text` string; `group_label` string; `part_label` string; `is_alternative` boolean; `order` integer; `label` string; `tags` [string]
- **PatchedSavedReplyRequest**: `title` string; `language` LanguageEnum; `body` string
- **PatchedSavedViewRequest**: `role` string; `list_key` string; `name` string; `filters` any; `columns` any; `sort` any
- **PatchedSolutionUpdateRequest**: `body_md` string
- **PatchedTemplateRequest**: `event` string; `channel` MessageChannelEnum; `language` LanguageEnum; `text` string; `subject` string; `variables` [VariableRequest]; `dlt_template_id` string; `pe_id` string; `header` string; `header_suffix` any; `msg91_id` string; `whatsapp_name` string; `category` TemplateCategoryEnum; `approval_state` TemplateApprovalEnum; `self_certified_on` date (null); `notes` string
- **PatchedTicketChangeRequest**: `category` any; `priority` TicketPriorityEnum; `language` LanguageEnum; `source` TicketSourceEnum; `nch_docket` string; `subject` string; `name` string; `email` any; `phone` string; `order` string; `record` string
- **PatternEnum**: one of `false_urgency`, `basket_sneaking`, `confirm_shaming`, `forced_action`, `subscription_trap`, `interface_interference`, `bait_and_switch`, `drip_pricing`, `disguised_advertisement`, `nagging`, `trick_question`, `saas_billing`, `rogue_malware`
- **PaymentMethodEnum**: one of `razorpay`, `cod`, `offline`
- **Person**: `id` integer (required, read-only); `email` email (required); `full_name` string (required); `is_active` boolean; `is_superuser` boolean; `roles` [string] (required, read-only); `grants` [object] (required, read-only); `scopes` [Scope] (required, read-only); `mfa` boolean (required, read-only); `last_login` date-time (null); `created` date-time (required, read-only)
- **PhotoRequest**: `photo` binary (required)
- **PickLine**: `title` string (required); `isbn` string (required); `quantity` integer (required)
- **PickListRequest**: `orders` [string] (required)
- **PickupLocation**: `id` integer (required, read-only); `nickname` string (required); `address` string; `city` string; `state` string; `pin_code` string (required); `phone` string; `is_default` boolean; `active` boolean; `external_id` string (required, read-only)
- **PickupLocationRequest**: `nickname` string (required); `address` string; `city` string; `state` string; `pin_code` string (required); `phone` string; `is_default` boolean; `active` boolean
- **PickupRequestRequest**: `date` date
- **PickupResult**: `pickup_date` date (required, null)
- **Policy**: `id` integer (required); `slug` string (required); `title` string (required); `version` string (required); `number` integer (required); `effective_from` date (required); `summary` string (required); `updated` date-time (required); `placeholders` integer (required); `scheduled` PolicyVersion (required, null); `versions` integer (required)
- **PolicyAcknowledgement**: `id` integer (required, read-only); `user` integer (required, read-only); `policy` string (required); `version` string (required); `acknowledged_at` date-time (required, read-only)
- **PolicyAcknowledgementRequest**: `policy` string (required); `version` string (required)
- **PolicyDetail**: `id` integer (required); `slug` string (required); `title` string (required); `version` string (required); `number` integer (required); `effective_from` date (required); `summary` string (required); `updated` date-time (required); `placeholders` integer (required); `scheduled` PolicyVersion (required, null); `versions` [PolicyVersion] (required); `markdown` string (required)
- **PolicyDiff**: `number` integer (required); `version` string (required); `previous` integer (required, null); `effective_from` date (required); `summary` string (required); `title` string (required); `title_changed` boolean (required); `added` integer (required); `removed` integer (required); `lines` [PolicyDiffLine] (required)
- **PolicyDiffLine**: `kind` PolicyDiffLineKindEnum (required); `text` string (required)
- **PolicyDiffLineKindEnum**: one of `hunk`, `added`, `removed`, `context`
- **PolicyVersion**: `number` integer (required); `version` string (required); `title` string (required); `summary` string (required); `effective_from` date (required); `published_at` date-time (required, null); `published_by` integer (required, null); `in_force` boolean (required); `upcoming` boolean (required)
- **PostalPrice**: `service` string (required); `label` string (required); `price` decimal (required)
- **PrintRunAdvice**: `product` string (required, read-only); `title` string (required, read-only); `net_price` decimal (required); `unit_cost` decimal (required); `salvage` decimal (required); `critical_ratio` double (required); `target_quantity` integer (required); `supply` integer (required); `recommended_quantity` integer (required); `reprint_trigger_units` integer (required); `weeks_of_cover` double (null); `projected_leftover` integer (required); `level` LevelEnum; `alert` string; `n` integer (required, read-only)
- **PrivacyCalendarItem**: `date` date (required); `title` string (required); `detail` string (required); `state` PrivacyCalendarItemStateEnum (required)
- **PrivacyCalendarItemStateEnum**: one of `upcoming`, `in_force`, `done`, `overdue`
- **PrivacyCockpitSupport**: `installed` boolean (required); `error` string (required)
- **PrivacyConsentVersion**: `version` string (required); `number` integer (required, null); `in_force` boolean (required); `given` integer (required); `withdrawn` integer (required)
- **PrivacyDarkPatternState**: `year` integer (required); `due` date (required); `audit` integer (required, null); `state` PrivacyDarkPatternStateStateEnum (required); `completed_at` date-time (required, null); `effective_from` date (required, null); `certificate_year` integer (required, null)
- **PrivacyDarkPatternStateStateEnum**: one of `missing`, `draft`, `completed`
- **PrivacyDeletionConfirmed**: `deletion` integer (required); `parent_confirmed_at` date-time (required)
- **PrivacyNominee**: `name` string (required); `contact` string (required); `relation` string (required); `verified_at` date-time (required, null); `created` date-time (required); `updated` date-time (required)
- **PrivacyNomineeContact**: `contact` string (required)
- **Processor**: `id` integer (required, read-only); `name` string (required); `purpose` string (required); `data_categories` string (required); `country` string (required); `contract_signed_on` date (null); `contract_ends_on` date (null); `active` boolean; `notes` string; `holds_personal_data` boolean; `holds_marketing_data` boolean; `erasure_action` string
- **ProcessorRequest**: `name` string (required); `purpose` string (required); `data_categories` string (required); `country` string (required); `contract_signed_on` date (null); `contract_ends_on` date (null); `active` boolean; `notes` string; `holds_personal_data` boolean; `holds_marketing_data` boolean; `erasure_action` string
- **ProductKindEnum**: one of `sample-papers`, `solutions`, `bundle`, `digital`
- **ProductPick**: `slug` string (required, read-only); `title` string (required, read-only); `kind` ProductKindEnum (required, read-only); `isbn` string (required, read-only); `price` decimal (required, read-only); `mrp` decimal (required, read-only); `available` integer (required, read-only)
- **Proven**: `on` date (required); `engine` RestoreDrillEngineEnum (required)
- **PublishRequest**: `markdown` string (required); `title` string; `summary` string (required); `effective_from` date
- **QuizItemBloomEnum**: one of `remember`, `understand`, `apply`, `analyse`, `evaluate`, `create`
- **QuizItemDifficultyEnum**: one of `easy`, `medium`, `hard`
- **QuizItemKindEnum**: one of `mcq`, `true_false`, `fill_blank`
- **Quote**: `courier_company_id` integer (required); `courier_name` string (required); `rate` decimal (required); `etd_days` integer (required, null); `rating` double (required, null); `cod` boolean (required); `cod_charges` decimal (required); `rto_charges` decimal (required); `recommended` boolean (required)
- **QuoteConvertRequest**: `address` ShippingAddressRequest (required); `email` email; `send_link` boolean; `note` string; `reason` string
- **QuoteDetail**: `id` integer (required, read-only); `number` string (required, read-only); `school` string (required, read-only); `contact_name` string (required, read-only); `email` string (required, read-only); `phone` string (required, read-only); `gstin` string (required, read-only); `delivery_pin` string (required, read-only); `copies` integer (required, read-only); `status` QuoteStatusEnum (required, read-only); `discount_percent` decimal (required, read-only); `shipping_fee` decimal (required, read-only); `quoted_at` date-time (required, null, read-only); `valid_until` date (required, null, read-only); `has_quotation` boolean (required, read-only); `order` string (required, null, read-only); `created` date-time (required, read-only); `items` [object] (required, read-only); `note` string (required, read-only); `waiting` integer (required, null, read-only)
- **QuoteResult**: `couriers` [Quote] (required); `india_post` [PostalPrice] (required); `weight_g` integer (required); `stale` boolean (required); `error` string (required)
- **QuoteRow**: `id` integer (required, read-only); `number` string (required, read-only); `school` string (required, read-only); `contact_name` string (required, read-only); `email` string (required, read-only); `phone` string (required, read-only); `gstin` string (required, read-only); `delivery_pin` string (required, read-only); `copies` integer (required, read-only); `status` QuoteStatusEnum (required, read-only); `discount_percent` decimal (required, read-only); `shipping_fee` decimal (required, read-only); `quoted_at` date-time (required, null, read-only); `valid_until` date (required, null, read-only); `has_quotation` boolean (required, read-only); `order` string (required, null, read-only); `created` date-time (required, read-only)
- **QuoteStatusEnum**: one of `new`, `quoted`, `ordered`, `closed`
- **RazorpayHealth**: `last_event_at` date-time (required, null); `age_hours` double (required, null); `paid_in_window` integer (required); `window_hours` integer (required); `silent` boolean (required)
- **ReasonRequest**: `reason` string (required)
- **ReconcileRequest**: `order` string (required)
- **Reconciled**: `order` string (required); `paid` boolean (required, null)
- **ReconciliationLine**: `date` date (required); `state` string (required); `differences` integer (required)
- **RefundLineRequest**: `item` integer (required); `quantity` integer (required)
- **RefundMarkPaidRequest**: `utr` string (required)
- **RefundPayee**: `upi` string; `account` string; `ifsc` string; `name` string
- **RefundPayeeReasonRequest**: `reason` string (required)
- **RefundPayeeRequest**: `upi` string; `account` string; `ifsc` string; `name` string
- **RefundRequest**: `order` string; `amount` decimal (null); `lines` [RefundLineRequest]; `reason` string (required)
- **RefundSpeedEnum**: one of `normal`, `optimum`
- **RefundStatusEnum**: one of `pending`, `processed`, `failed`
- **ReleaseRequest**: `reason` string (required)
- **ReplayFailedRequest**: `since` date-time (required)
- **Replayed**: `replayed` integer (required); `more` boolean (required)
- **ReportBacktest**: `horizon_weeks` integer (required); `wape` double (required, null); `mase_vs_seasonal_naive` double (required, null); `shown` boolean (required); `n_weeks` integer (required); `data_as_of` date-time (required)
- **ReportCod**: `report` string (required); `definition` string (required); `columns` [ReportColumn] (required); `as_of` date-time (required); `test_mode` boolean (required); `period` ReportPeriod (required, null); `as_of_day` date (required); `remitted` ReportCodRemitted (required); `by_courier` [ReportCodCourier] (required); `rows` [ReportCodRow] (required)
- **ReportCodCourier**: `courier` string (required); `count` integer (required); `expected` decimal (required); `overdue` integer (required)
- **ReportCodRemitted**: `count` integer (required); `expected` decimal (required); `received` decimal (required); `difference` decimal (required)
- **ReportCodRow**: `key` string (required); `label` string (required); `count` integer (required); `expected` decimal (required); `oldest_expected_on` date (required, null)
- **ReportCodes**: `report` string (required); `definition` string (required); `columns` [ReportColumn] (required); `as_of` date-time (required); `test_mode` boolean (required); `period` ReportPeriod (required, null); `batch` string (required); `minimum` integer (required); `districts_computed_at` date-time (required, null); `districts` [ReportCodesDistrict] (required); `rows` [ReportCodesRow] (required)
- **ReportCodesDistrict**: `hidden` boolean (required); `under` integer (required, null); `district` string (required); `redeemed` integer (required, null); `redeemed_7d` integer (required, null)
- **ReportCodesRow**: `batch` string (required); `printed` integer (required); `sold` integer (required, null); `activated` integer (required); `activated_7d` integer (required); `revoked` integer (required, null); `activation_rate` decimal (required, null)
- **ReportColumn**: `key` string (required); `label` string (required); `definition` string (required)
- **ReportDemandRange**: `p10` integer (required); `p50` integer (required); `p90` integer (required); `weeks` integer (required)
- **ReportHealth**: `report` string (required); `definition` string (required); `columns` [ReportColumn] (required); `as_of` date-time (required); `test_mode` boolean (required); `period` ReportPeriod (required, null); `grain` string (required); `computed_at` date-time (required, null); `minimum` integer (required); `subject` integer (required, null); `chapter` integer (required, null); `subjects` [ReportHealthSubject] (required); `whole_course` boolean (required); `series` [ReportHealthPoint] (required); `codes_by_week` [ReportHealthWeek] (required); `rows` [ReportHealthChapter] (required)
- **ReportHealthChapter**: `hidden` boolean (required); `under` integer (required, null); `subject` integer (required); `chapter` integer (required); `number` integer (required); `title` string (required); `label` string (required); `active_7d` integer (required, null); `active_28d` integer (required, null); `clips_started` integer (required, null); `clips_completed` integer (required, null); `completion_rate` decimal (required, null); `quiz_answers` integer (required, null); `quiz_accuracy` decimal (required, null); `card_reviews` integer (required, null); `card_lapses` integer (required, null)
- **ReportHealthPoint**: `hidden` boolean (required); `under` integer (required, null); `period_start` date (required); `active_learners` integer (required, null); `clips_completed` integer (required, null); `quiz_answers` integer (required, null); `quiz_accuracy` decimal (required, null); `card_reviews` integer (required, null); `card_lapses` integer (required, null); `smoothed_7` decimal (required, null); `smoothed_28` decimal (required, null)
- **ReportHealthSubject**: `id` integer (required); `name` string (required)
- **ReportHealthWeek**: `hidden` boolean (required); `under` integer (required, null); `week_start` date (required); `redeemed` integer (required, null)
- **ReportIndex**: `test_mode` boolean (required); `reports` [ReportIndexItem] (required)
- **ReportIndexItem**: `key` string (required); `label` string (required); `summary` string (required); `page` string (required); `api` string (required); `needs` [string] (required); `available` boolean (required); `configured` boolean (required)
- **ReportPeriod**: `start` date (required); `end` date (required); `days` integer (required)
- **ReportPlace**: `report` string (required); `definition` string (required); `columns` [ReportColumn] (required); `as_of` date-time (required); `test_mode` boolean (required); `period` ReportPeriod (required, null); `level` string (required); `state` string (required); `minimum` integer (required); `hidden_rows` integer (required); `totals_shown` ReportPlaceTotals (required); `rows` [ReportPlaceRow] (required)
- **ReportPlaceRow**: `hidden` boolean (required); `under` integer (required, null); `level` string (required); `state` string (required, null); `state_name` string (required, null); `district` string (required, null); `pin` string (required, null); `label` string (required); `orders` integer (required, null); `units` integer (required, null); `net` decimal (required, null)
- **ReportPlaceTotals**: `orders` integer (required); `units` integer (required); `net` decimal (required)
- **ReportPrintRun**: `product` string (required); `title` string (required); `net_price` decimal (required); `unit_cost` decimal (required); `salvage` decimal (required); `critical_ratio` double (required); `percentile` integer (required); `target_quantity` integer (required, null); `supply` integer (required); `recommended_quantity` integer (required, null); `range` ReportDemandRange (required, null); `method` string (required); `data_as_of` date-time (required, null); `backtest` ReportBacktest (required, null); `shown` boolean (required); `note` string (required)
- **ReportPrintRunRequestRequest**: `product` string (required); `net_price` decimal (required); `unit_cost` decimal (required); `salvage` decimal
- **ReportSales**: `report` string (required); `definition` string (required); `columns` [ReportColumn] (required); `as_of` date-time (required); `test_mode` boolean (required); `period` ReportPeriod (required, null); `by` string (required); `grain` string (required); `totals` ReportSalesTotals (required); `rows` [ReportSalesRow] (required)
- **ReportSalesRow**: `key` string (required); `label` string (required); `period_start` date (required, null); `orders` integer (required); `units` integer (required); `gross` decimal (required); `discount` decimal (required); `net` decimal (required)
- **ReportSalesTotals**: `orders` integer (required); `units` integer (required); `gross` decimal (required); `discount` decimal (required); `net` decimal (required)
- **ReportSettlementRow**: `reference` string (required); `date` date (required, null); `gross` decimal (required, null); `fees` decimal (required, null); `tax` decimal (required, null); `refunds` decimal (required, null); `net` decimal (required, null); `utr` string (required); `state` string (required)
- **ReportSettlements**: `report` string (required); `definition` string (required); `columns` [ReportColumn] (required); `as_of` date-time (required); `test_mode` boolean (required); `period` ReportPeriod (required, null); `configured` boolean (required); `note` string (required); `rows` [ReportSettlementRow] (required)
- **ReportsOpen**: `total` integer (required); `by_category` object (required)
- **Requester**: `name` string (required); `email` string (required); `phone` string (required); `user` integer (required, null)
- **ResolveRequest**: `resolution` string (required); `dismiss` boolean
- **ResponseText**: `subject` string (required); `body` string (required)
- **RestoreDrill**: `id` integer (required, read-only); `performed_on` date (required); `engine` RestoreDrillEngineEnum (required); `backup` string (required); `result` RestoreDrillResultEnum (required); `duration_minutes` integer (required); `notes` string; `recorded_by` integer (required, null, read-only); `created` date-time (required, read-only)
- **RestoreDrillEngineEnum**: one of `platform`, `erpnext`, `both`
- **RestoreDrillRequest**: `performed_on` date (required); `engine` RestoreDrillEngineEnum (required); `backup` string (required); `result` RestoreDrillResultEnum (required); `duration_minutes` integer (required); `notes` string
- **RestoreDrillResultEnum**: one of `passed`, `partial`, `failed`
- **RetentionRule**: `key` string (required); `records` string (required); `minimum` string (required); `minimum_days` integer (required, null); `source` string (required); `changes_on` date (required, null); `next_minimum` string (required, null); `keep` string (required); `keep_days` integer (required, null); `trim_days` integer (required, null); `enforced_by` string (required)
- **ReturnAskRequest**: `lines` [OrderLineAskRequest] (required); `reason` ReturnReasonEnum (required); `note` string
- **ReturnDeclineRequest**: `note` string (required)
- **ReturnDetail**: `id` integer (required, read-only); `number` string (required, read-only); `order` string (required, read-only); `status` ReturnStatusEnum (required, read-only); `status_label` string (required, read-only); `reason` ReturnReasonEnum (required, read-only); `reason_label` string (required, read-only); `lines` [ReturnLine] (required, read-only); `by_customer` boolean (required, read-only); `decision_note` string (required, read-only); `return_courier` string (required, read-only); `return_awb` string (required, read-only); `photos` integer (required, read-only); `received_at` date-time (required, null, read-only); `inspected_at` date-time (required, null, read-only); `refund` integer (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `note` string (required, read-only); `next` [string] (required, read-only)
- **ReturnInspectOutcomeEnum**: one of `restocked`, `damaged`
- **ReturnInspectRequest**: `outcome` ReturnInspectOutcomeEnum (required)
- **ReturnLabelRequest**: `courier` string (required); `awb` string (required)
- **ReturnLine**: `item` integer (required); `title` string (required); `quantity` integer (required)
- **ReturnPhotoRequest**: `photo` binary (required)
- **ReturnReasonEnum**: one of `damaged`, `misprint`, `wrong_item`, `late`, `not_as_described`, `other`
- **ReturnRow**: `id` integer (required, read-only); `number` string (required, read-only); `order` string (required, read-only); `status` ReturnStatusEnum (required, read-only); `status_label` string (required, read-only); `reason` ReturnReasonEnum (required, read-only); `reason_label` string (required, read-only); `lines` [ReturnLine] (required, read-only); `by_customer` boolean (required, read-only); `decision_note` string (required, read-only); `return_courier` string (required, read-only); `return_awb` string (required, read-only); `photos` integer (required, read-only); `received_at` date-time (required, null, read-only); `inspected_at` date-time (required, null, read-only); `refund` integer (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **ReturnStatusEnum**: one of `requested`, `approved`, `declined`, `label_sent`, `received`, `restocked`, `damaged`, `refunded`
- **RevealReasonRequest**: `reason` string (required)
- **RevealRequest**: `show` [ShowEnum] (required); `reason` string (required)
- **Revealed**: `email` string (null); `phone` string (null); `login_phone` string (null); `parent_contact` string (null); `parent_name` string (null); `date_of_birth` string (null)
- **ReviewTaskStageEnum**: one of `check`, `publish`
- **ReviewTaskStateEnum**: one of `in_progress`, `approved`, `needs_changes`, `cancelled`
- **RiskEnum**: one of `low`, `medium`, `high`, `critical`
- **RoleCard**: `for` string (required); `cannot` string (required)
- **RoleCatalogue**: `name` RoleEnum (required); `card` RoleCard (required); `privileged` boolean (required); `admin_site` boolean (required); `passkey` boolean (required); `idle_timeout_s` integer (required); `limits` object (required); `scopes` object (required); `conflicts` [string] (required); `erp_profiles` [string] (required); `members` integer (required); `permissions` integer (required); `capabilities` [CapabilityArea] (required)
- **RoleChangeActionEnum**: one of `grant`, `revoke`
- **RoleEnum**: one of `ADMIN`, `AUDITOR`, `CONTENT_EDITOR`, `FINANCE`, `MARKETING`, `OWNER`, `PACKER`, `REVIEWER`, `SALES`, `SALES_REP`, `SUPPORT`
- **RolePreview**: `role` RoleEnum (required); `action` RoleChangeActionEnum (required); `holds_already` boolean (required); `gains` [CapabilityArea] (required); `losses` [CapabilityArea] (required); `limits` [LimitChange] (required); `scopes` [RoleScopeChange] (required); `idle_timeout_s` BeforeAfterSeconds (required); `conflicts` [Conflict] (required); `blocked` boolean (required); `needs_approval` boolean (required); `rule` string (required); `checker` string (required); `passkey_needed` boolean (required); `erp_profiles` BeforeAfterProfiles (required)
- **RolePreviewRequestRequest**: `role` RoleEnum (required); `action` RoleChangeActionEnum
- **RoleScopeChange**: `role` RoleEnum (required); `scopes` object (required); `added` boolean (required)
- **Rotated**: `token` string (required); `webhooks` WebhookInfo (required)
- **SavedReply**: `id` integer (required, read-only); `title` string (required); `language` LanguageEnum; `body` string (required); `variables` [string] (required, read-only); `created_by` integer (required, null, read-only); `created` date-time (required, read-only); `modified` date-time (required, read-only); `deleted_at` date-time (required, null, read-only)
- **SavedReplyRequest**: `title` string (required); `language` LanguageEnum; `body` string (required)
- **SavedReplyText**: `id` integer (required); `title` string (required); `language` string (required); `text` string (required)
- **SavedView**: `id` integer (required, read-only); `owner` integer (required, read-only); `role` string; `list_key` string (required); `name` string (required); `filters` any; `columns` any; `sort` any; `created` date-time (required, read-only); `modified` date-time (required, read-only)
- **SavedViewRequest**: `role` string; `list_key` string (required); `name` string (required); `filters` any; `columns` any; `sort` any
- **Scope**: `id` integer (required, read-only); `kind` ScopeKindEnum (required); `value` string (required); `granted_by` integer (required, null, read-only); `created` date-time (required, read-only); `expires_at` date-time (null)
- **ScopeAddRequest**: `kind` ScopeKindEnum (required); `value` string (required); `expires_at` date-time (null)
- **ScopeKindEnum**: one of `subject`, `board_class`, `order_status`, `warehouse`, `school`, `ticket_queue`, `ticket_category`
- **ScriptPageEnum**: one of `checkout`, `console`
- **ScriptRow**: `id` integer (required, read-only); `page` ScriptPageEnum (required); `src` any; `sha256` string (required); `first_seen` date-time; `last_seen` date-time; `current` boolean (required, read-only)
- **ScriptRun**: `page` ScriptPageEnum (required); `url` string (required); `at` date-time (required, null); `ok` boolean (required, null); `error` string (required); `added` integer (required); `removed` integer (required)
- **Scripts**: `runs` [ScriptRun] (required); `scripts` [ScriptRow] (required)
- **SecondFactors**: `authenticator_app` boolean (required); `passkey` boolean (required); `recovery_codes` boolean (required)
- **SeriesRegister**: `financial_year` string (required); `month` string (required, null); `series_from` string (required); `prefixes` object (required); `rows` [SeriesRow] (required)
- **SeriesRow**: `series` string (required); `nature` string (required); `document_type` SeriesTypeEnum (required); `financial_year` string (required); `first` string (required); `last` string (required); `total` integer (required); `cancelled` integer (required); `next_number` integer (required, null)
- **SeriesTypeEnum**: one of `invoice`, `tax_invoice`, `bill_of_supply`, `invoice_cum_bill_of_supply`, `credit_note`, `debit_note`, `receipt_voucher`, `refund_voucher`
- **SessionsEnded**: `sessions` integer (required); `tokens` integer (required)
- **Setting**: `key` string (required); `label` string (required); `kind` any (required); `permission` string (required); `value` any (required); `environment` any (required); `source` SettingSourceEnum (required); `effective_from` date-time (required, null); `changed_by` integer (required, null); `reason` string (required); `scheduled` [object] (required); `group` string (required)
- **SettingSourceEnum**: one of `environment`, `database`
- **SeverityEnum**: one of `critical`, `high`, `moderate`, `low`, `unknown`
- **ShipmentCharge**: `id` integer (required, read-only); `shipment` integer (required, null, read-only); `kind` ShipmentChargeKindEnum (required, read-only); `amount` decimal (required, read-only); `charged_weight_g` integer (required, null, read-only); `awb` string (required, read-only); `description` string (required, read-only); `statement_line_id` string (required, read-only); `charged_at` date-time (required, read-only)
- **ShipmentChargeKindEnum**: one of `freight`, `freight_reversal`, `cod`, `cod_reversal`, `rto_freight`, `rto_freight_reversal`, `excess_weight`, `excess_weight_reversal`, `other`
- **ShipmentEvent**: `source` ShipmentEventSourceEnum (required); `carrier_code` string; `carrier_label` string; `status` any (null); `occurred_at` date-time (required); `location` string; `activity` string
- **ShipmentEventSourceEnum**: one of `webhook`, `poll`, `manual`
- **ShippingAddressRequest**: `name` string (required); `phone` string (required); `line1` string (required); `line2` string; `city` string (required); `district` string (required); `state` StateEnum; `pin` string (required)
- **ShippingException**: `id` integer (required, read-only); `kind` ShippingExceptionKindEnum (required, read-only); `shipment` integer (required, read-only); `order` string (required, read-only); `due_at` date-time (required, read-only); `state` ShippingExceptionStateEnum (required, read-only); `reference` string (required, read-only); `data` any (required, read-only); `resolution` string (required, read-only); `resolved_at` date-time (required, null, read-only); `resolved_by` integer (required, null, read-only); `created` date-time (required, read-only)
- **ShippingExceptionKindEnum**: one of `pickup_problem`, `ndr`, `rto`, `lost`, `partial`, `weight_dispute`, `cod_overdue`, `no_movement`
- **ShippingExceptionStateEnum**: one of `open`, `resolved`, `dismissed`
- **ShowEnum**: one of `email`, `phone`, `login_phone`, `parent_contact`, `parent_name`, `date_of_birth`
- **Sidebar**: `account` Customer (required, null); `orders` [SidebarOrder] (required, null); `entitlements` [EntitlementRow] (required, null); `codes` [CodeRow] (required, null); `devices` [DeviceRow] (required, null); `tickets` [PastTicket] (required, null); `consents` [ConsentRow] (required, null)
- **SidebarLine**: `id` integer (required); `title` string (required); `quantity` integer (required); `unit_price` string (required); `discount` string (required, null)
- **SidebarOrder**: `number` string (required); `status` string (required); `status_label` string (required); `total` string (required); `payment_method` string (required); `created` date-time (required); `placed_at` date-time (required, null); `is_test` boolean (required); `refund_mode` string (required); `refund_warning` string (required); `linked` boolean (required); `payments` [SidebarPayment] (required); `refunds` [SidebarRefund] (required); `shipments` [OrderShipment] (required); `invoice` string (required, null); `credit_notes` [string] (required); `items` [SidebarLine] (required)
- **SidebarPayment**: `method` string (required); `paid_with` string (required); `status` string (required); `amount` string (required); `razorpay_order_id` string (required, null); `razorpay_payment_id` string (required, null); `created` date-time (required)
- **SidebarRefund**: `amount` string (required); `status` string (required); `razorpay_refund_id` string (required, null); `created` date-time (required)
- **SmsFigures**: `sent_today` integer (required); `capped_today` integer (required); `capped_7_days` integer (required); `delivery_7_days` object (required); `daily_cap` integer (required); `templates` integer (required)
- **SnoozeRequest**: `until` date-time (required)
- **StaffBreakGlass**: `reason_required` boolean (required); `reason` string (required, null); `ends_at` date-time (required)
- **StaffCatalogue**: `permissions` [object] (required); `roles` [object] (required)
- **StaffImpersonating**: `user_id` integer (required); `email` string (required); `until` date-time (required)
- **StaffInvite**: `id` integer (required, read-only); `email` string (required, read-only); `role` string (required); `invited_by` integer (null); `created` date-time; `expires_at` date-time (required); `accepted_at` date-time (null); `accepted_by` integer (null); `revoked_at` date-time (null)
- **StaffManifest**: `break_glass` StaffBreakGlass (required, null); `user` StaffUser (required); `roles` [object] (required); `permissions` [string] (required); `scopes` object (required); `role_scopes` object (required); `limits` object (required); `flags` object (required); `policies_due` [object] (required); `reauth_valid_until` date-time (required, null); `idle_timeout_s` integer (required); `absolute_expires_at` date-time (required); `impersonating` StaffImpersonating (required, null); `manifest_version` string (required); `steps` [StepsEnum] (required); `offer_end_sessions` boolean (required)
- **StaffOrderChannelEnum**: one of `phone`, `whatsapp`, `school`, `email`
- **StaffOrderLineRequest**: `product` string (required); `quantity` integer (required)
- **StaffOrderPreview**: `lines` [StaffOrderPreviewLine] (required); `subtotal` decimal (required); `offers` decimal (required); `discount` decimal (required); `percent` decimal (required); `shipping` decimal (required, null); `total` decimal (required); `limit` decimal (required, null); `approval` string (required, null); `problems` [string] (required)
- **StaffOrderPreviewAskRequest**: `lines` [StaffOrderLineRequest] (required); `state` string (required); `email` any; `discount` decimal; `shipping` decimal (null)
- **StaffOrderPreviewLine**: `product` string (required); `title` string (required); `unit_price` decimal (required); `quantity` integer (required); `line_total` decimal (required); `available` integer (required)
- **StaffOrderRequest**: `channel` StaffOrderChannelEnum (required); `lines` [StaffOrderLineRequest] (required); `email` email (required); `address` ShippingAddressRequest (required); `discount` decimal; `shipping` decimal (null); `send_link` boolean; `note` string; `reason` string (required)
- **StaffSystem**: `health` any (required); `celery` any (required); `webhooks` any (required); `email` any (required); `sms` any (required); `backups` any (required); `maintenance` any (required); `audit` any (required); `status` [SystemStatus] (required)
- **StaffUser**: `id` integer (required); `email` email (required); `full_name` string (required); `is_superuser` boolean (required)
- **StateEnum**: one of `KA`, `AP`, `KL`, `TN`, `MH`, `UP`, `GA`, `GJ`, `RJ`, `HP`, `TG`, `AR`, `AS`, `BR`, `CT`, `HR`, `JH`, `MP`, `MN`, `ML`, `MZ`, `NL`, `OR`, `PB`, `SK`, `TR`, `UT`, `WB`, `AN`, `CH`, `DH`, `DL`, `JK`, `LD`, `LA`, `PY`
- **StatusRequest**: `status` TicketStatusEnum (required); `resolution` string; `order` string; `record` string
- **StepsEnum**: one of `passkey_required`
- **StorageFigures**: `buckets` [Bucket] (required); `public_domain` string (required)
- **SupportSummary**: `since` date (required); `until` date (required); `received` integer (required); `by_category` object (required); `by_source` object (required); `first_response_hours` double (required, null); `resolution_hours` double (required, null); `backlog` object (required); `overdue` integer (required); `breaches` object (required)
- **SwitchChangeRequest**: `value` any (required, null); `reason` string (required); `effective_from` date-time
- **SwitchRow**: `key` string (required); `value` any (required); `effective_from` date-time (required); `changed_by` integer (required, null); `reason` string (required); `created` date-time (required)
- **Sync**: `status` any (required); `flows` [SyncFlow] (required); `dead_letters` [SyncDead] (required); `dead_count` integer (required); `inbound` SyncInbound (required); `reconciliations` [SyncRun] (required)
- **SyncDead**: `id` integer (required); `event` string (required); `examleaf_ref` string (required); `aggregate_type` string (required); `aggregate_id` string (required); `attempts` integer (required); `last_error` string (required); `created` date-time (required)
- **SyncFlow**: `flow` string (required); `switch` boolean (required); `states` object (required)
- **SyncInbound**: `states` object (required); `last_received_at` date-time (required, null)
- **SyncRun**: `id` integer (required); `date` date (required); `state` string (required); `differences_count` integer (required); `open_differences` integer (required); `finished_at` date-time (required, null); `error` string (required)
- **SystemClock**: `source` string (required); `documented` boolean (required); `app_now` date-time (required); `database_now` date-time (required, null); `offset_ms` integer (required, null); `ok` boolean (required)
- **SystemStatus**: `key` string (required); `state` SystemStatusStateEnum (required); `summary` string (required); `since` date-time (required, null)
- **SystemStatusStateEnum**: one of `ok`, `warn`, `bad`, `off`
- **TargetTypeEnum**: one of `shop.creditnote`, `shop.invoice`, `shop.order`, `shop.payment`, `shop.refund`, `staff.datarequest`
- **TaxCalendar**: `month` string (required); `qrmp` boolean (required); `items` [TaxCalendarItem] (required); `crossed` [ThresholdRow] (required)
- **TaxCalendarItem**: `key` string (required); `title` string (required); `covers` string (required); `due` date (required); `applies` boolean (required); `note` string (required); `past` boolean (required)
- **TaxCharge**: `label` string (required); `rate` decimal (required); `amount` decimal (required); `taxable` decimal (required); `tax` decimal (required)
- **TaxDocument**: `key` string (required); `kind` TaxDocumentKindEnum (required); `id` integer (required); `number` string (required); `series` string (required); `financial_year` string (required); `serial` integer (required); `document_type` any (required); `test` boolean (required); `date` date (required); `order` string (required); `against` string (required, null); `place_of_supply` string (required); `place_label` string (required); `total` decimal (required); `taxable_value` decimal (required, null); `exempt_value` decimal (required, null); `tax_amount` decimal (required, null); `cancelled_at` date-time (required, null); `cancel_reason` string (required); `cancelled_by` integer (required, null); `has_pdf` boolean (required)
- **TaxDocumentDetail**: `key` string (required); `kind` TaxDocumentKindEnum (required); `id` integer (required); `number` string (required); `series` string (required); `financial_year` string (required); `serial` integer (required); `document_type` any (required); `test` boolean (required); `date` date (required); `order` string (required); `against` string (required, null); `place_of_supply` string (required); `place_label` string (required); `total` decimal (required); `taxable_value` decimal (required, null); `exempt_value` decimal (required, null); `tax_amount` decimal (required, null); `cancelled_at` date-time (required, null); `cancel_reason` string (required); `cancelled_by` integer (required, null); `has_pdf` boolean (required); `title` string (required); `lines` [TaxLine] (required); `charges` [TaxCharge] (required); `round_off` decimal (required); `checks` [string] (required); `credit_notes` [string] (required)
- **TaxDocumentKindEnum**: one of `invoice`, `credit_note`
- **TaxDocumentTypeEnum**: one of `tax_invoice`, `bill_of_supply`, `invoice_cum_bill_of_supply`
- **TaxLine**: `title` string (required); `bundle` string (required); `hsn_code` string (required); `quantity` integer (required); `rate` decimal (required); `amount` decimal (required); `taxable` decimal (required); `tax` decimal (required)
- **TaxProblem**: `id` integer (required, read-only); `slug` string (required, read-only); `title` string (required, read-only); `kind` ProductKindEnum (required, read-only); `hsn_code` string (required, read-only); `gst_rate` decimal (required, read-only); `is_active` boolean (required, read-only); `tax_treatment` TaxTreatmentEnum (required, read-only); `problem` string (required, read-only)
- **TaxThresholdLineEnum**: one of `gstr9`, `warning`, `e_invoice`, `irp_30_days`, `b2c_large`, `eway_bill`
- **TaxTreatmentEnum**: one of `split`, `composite`, `mixed`
- **TaxabilityEnum**: one of `taxable`, `nil`, `exempt`, `non_gst`
- **Template**: `id` integer (required, read-only); `event` string (required); `channel` MessageChannelEnum (required); `language` LanguageEnum; `text` string; `subject` string; `variables` [Variable]; `dlt_template_id` string; `pe_id` string; `header` string; `header_suffix` any; `msg91_id` string; `whatsapp_name` string; `category` TemplateCategoryEnum (required); `approval_state` TemplateApprovalEnum; `last_used_at` date-time (required, null, read-only); `self_certified_on` date (null); `notes` string; `created` date-time (required, read-only); `modified` date-time (required, read-only); `days_unused` integer (required, read-only); `warnings` [string] (required, read-only)
- **TemplateApprovalEnum**: one of `draft`, `submitted`, `approved`, `rejected`, `paused`, `deactivated`
- **TemplateCategoryEnum**: one of `transactional`, `service`, `promotional`, `utility`, `authentication`
- **TemplateRequest**: `event` string (required); `channel` MessageChannelEnum (required); `language` LanguageEnum; `text` string; `subject` string; `variables` [VariableRequest]; `dlt_template_id` string; `pe_id` string; `header` string; `header_suffix` any; `msg91_id` string; `whatsapp_name` string; `category` TemplateCategoryEnum (required); `approval_state` TemplateApprovalEnum; `self_certified_on` date (null); `notes` string
- **TestResult**: `ok` boolean (required, null); `message` string (required); `card` ConnectionCard (required)
- **TestSendRequest**: `variables` object
- **TestSent**: `sent` boolean (required); `to` string (required); `detail` string (required)
- **ThresholdCard**: `as_of` date (required, null); `financial_year` string (required); `previous_year` string (required); `previous_turnover` decimal (required); `qrmp` boolean (required); `hsn_digits` integer (required); `basis` string (required); `rows` [ThresholdRow] (required)
- **ThresholdRow**: `line` TaxThresholdLineEnum (required, read-only); `label` string (required); `value` decimal (required, read-only); `limit` decimal (required, read-only); `crossed` boolean (required, read-only); `count` boolean (required, read-only); `detail` any (required, read-only); `date` date (required, read-only); `financial_year` string (required, read-only)
- **Ticket**: `id` integer (required, read-only); `number` string (required, read-only); `subject` string (required, read-only); `source` TicketSourceEnum (required, read-only); `nch_docket` string (required, read-only); `category` any (required, read-only); `priority` TicketPriorityEnum (required, read-only); `status` TicketStatusEnum (required, read-only); `language` LanguageEnum (required, read-only); `requester` Requester (required, read-only); `assignee` integer (required, null, read-only); `order` string (required, null, read-only); `received_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `first_response_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `closed_at` date-time (required, null, read-only); `ack_due_at` date-time (required, read-only); `due_at` date-time (required, read-only); `next_due_at` date-time (required, read-only); `ack_breached` boolean (required, read-only); `due_breached` boolean (required, read-only); `overdue` boolean (required, read-only); `clock` string (required, null, read-only); `is_test` boolean (required, read-only); `reopened_count` integer (required, read-only); `message_count` integer (required, read-only); `last_message_at` date-time (required, null, read-only)
- **TicketAssignRequest**: `assignee` integer (required, null)
- **TicketCancelRequest**: `order` string; `reason` string (required)
- **TicketCategoryEnum**: one of `order`, `payment`, `book_code`, `qr_solutions`, `content_error`, `school_order`, `privacy_request`, `grievance`
- **TicketChannelEnum**: one of `web`, `email`, `phone`, `whatsapp`, `sms`, `nch`, `panel`
- **TicketClock**: `name` string (required); `kind` string (required); `due` date-time (required); `rule` string (required); `stopped_at` date-time (required, null); `breached` boolean (required)
- **TicketContactEnum**: one of `phone`, `whatsapp`, `nch`, `email`
- **TicketCreateRequest**: `source` TicketContactEnum (required); `nch_docket` string; `name` string; `email` any; `phone` string; `category` any; `priority` TicketPriorityEnum; `subject` string (required); `message` string (required); `received_at` date-time; `order` string
- **TicketDetail**: `id` integer (required, read-only); `number` string (required, read-only); `subject` string (required, read-only); `source` TicketSourceEnum (required, read-only); `nch_docket` string (required, read-only); `category` any (required, read-only); `priority` TicketPriorityEnum (required, read-only); `status` TicketStatusEnum (required, read-only); `language` LanguageEnum (required, read-only); `requester` Requester (required, read-only); `assignee` integer (required, null, read-only); `order` string (required, null, read-only); `received_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `first_response_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `closed_at` date-time (required, null, read-only); `ack_due_at` date-time (required, read-only); `due_at` date-time (required, read-only); `next_due_at` date-time (required, read-only); `ack_breached` boolean (required, read-only); `due_breached` boolean (required, read-only); `overdue` boolean (required, read-only); `clock` string (required, null, read-only); `is_test` boolean (required, read-only); `reopened_count` integer (required, read-only); `message_count` integer (required, read-only); `last_message_at` date-time (required, null, read-only); `data_request` integer (required, null, read-only); `record` string (required, null, read-only); `resolution` string (required, read-only); `complaint_copy_sent_at` date-time (required, null, read-only); `ack_held` boolean (required, read-only); `redress_due_at` date-time (required, null, read-only); `nch_due_at` date-time (required, null, read-only); `dpdp_due_at` date-time (required, null, read-only); `it_due_at` date-time (required, null, read-only); `clocks` [TicketClock] (required, read-only); `closing_fields` [string] (required, read-only); `transitions` [string] (required, read-only); `messages` [Message] (required, read-only)
- **TicketDirectionEnum**: one of `in`, `out`, `note`
- **TicketOrderCancelled**: `order` string (required); `status` string (required)
- **TicketPriorityEnum**: one of `low`, `medium`, `high`, `urgent`
- **TicketRecord**: `id` integer (required, read-only); `number` string (required, read-only); `subject` string (required, read-only); `source` TicketSourceEnum (required, read-only); `nch_docket` string (required, read-only); `category` any (required, read-only); `priority` TicketPriorityEnum (required, read-only); `status` TicketStatusEnum (required, read-only); `language` LanguageEnum (required, read-only); `requester` Requester (required, read-only); `assignee` integer (required, null, read-only); `order` string (required, null, read-only); `received_at` date-time (required, read-only); `acknowledged_at` date-time (required, null, read-only); `first_response_at` date-time (required, null, read-only); `resolved_at` date-time (required, null, read-only); `closed_at` date-time (required, null, read-only); `ack_due_at` date-time (required, read-only); `due_at` date-time (required, read-only); `next_due_at` date-time (required, read-only); `ack_breached` boolean (required, read-only); `due_breached` boolean (required, read-only); `overdue` boolean (required, read-only); `clock` string (required, null, read-only); `is_test` boolean (required, read-only); `reopened_count` integer (required, read-only); `message_count` integer (required, read-only); `last_message_at` date-time (required, null, read-only); `data_request` integer (required, null, read-only); `record` string (required, null, read-only); `resolution` string (required, read-only); `complaint_copy_sent_at` date-time (required, null, read-only); `ack_held` boolean (required, read-only); `redress_due_at` date-time (required, null, read-only); `nch_due_at` date-time (required, null, read-only); `dpdp_due_at` date-time (required, null, read-only); `it_due_at` date-time (required, null, read-only); `clocks` [TicketClock] (required, read-only); `closing_fields` [string] (required, read-only); `transitions` [string] (required, read-only); `messages` [Message] (required, read-only); `sidebar` Sidebar (required, read-only); `saved_replies` [SavedReplyText] (required, read-only)
- **TicketRevealFieldEnum**: one of `email`, `phone`
- **TicketRevealRequest**: `show` [TicketRevealFieldEnum] (required); `reason` string (required)
- **TicketRevealed**: `email` string (required, null); `phone` string (required, null)
- **TicketSourceEnum**: one of `form`, `email`, `phone`, `whatsapp`, `nch`
- **TicketStatusEnum**: one of `new`, `open`, `waiting_customer`, `waiting_third_party`, `resolved`, `closed`, `spam`
- **TierEnum**: one of `E`, `M`, `H`
- **TokenRequest**: `token` string (required)
- **Unlocked**: `attempts_cleared` integer (required)
- **Variable**: `name` string (required); `type` VariableTypeEnum (required); `max_length` integer (required); `about` string
- **VariableRequest**: `name` string (required); `type` VariableTypeEnum (required); `max_length` integer (required); `about` string
- **VariableTypeEnum**: one of `numeric`, `alphanumeric`, `url`, `urlott`, `cbn`, `email`
- **VerifyIdentityRequest**: `note` string (required)
- **WebhookAuthEnum**: one of `token`, `signature`, `basic_and_sns`
- **WebhookInfo**: `provider` ConnectionProviderEnum (required); `url` string (required); `auth` WebhookAuthEnum (required); `header` string (required); `token` string (required); `rotated_at` date-time (required, null); `previous_valid_until` date-time (required, null); `rotatable` boolean (required); `events_kept` boolean (required); `states` object (required); `last_event_at` date-time (required, null); `silence_hours` integer (required); `silent` boolean (required)
<!-- /staff-api-reference -->

## Errors

DRF's standard format, always JSON:

| Status | Body |
|---|---|
| 400 | the fields' errors: `{"marks_obtained": ["Enter marks from 0 to 70."]}`; others (and the shop's rules) under `non_field_errors`; `{"detail": "Bad request."}` for a request Django refuses before the API sees it (a host name that is not served) |
| 401 | `{"detail": "Authentication credentials were not provided."}`; a bad or expired token: `{"detail": "Given token not valid for any token type", "code": "token_not_valid", "messages": [...]}` (refresh it); `"code": "password_changed"` or `"user_inactive"` (the password was changed, the account closed: log in again); a staff session ended: `"code": "session_idle"` or `"session_expired"` (log in again) |
| 403 | `{"detail": "Confirm your email address first."}` (or another reason; `"The shop opens soon."` while the shop is closed; `"Unlock this subject with the code printed in your book."` for a locked course; `"A parent or guardian has not confirmed this account yet."` for what the course saves while `consent_pending`); `"code": "reauthentication_required"` (re-authenticate, then send it again), `"mfa_setup_required"` (staff: set up a second factor), `"passkey_required"` (staff of OWNER, ADMIN or FINANCE: add a passkey on the website's `/account/security/` first), `"impersonating"` (a payment, password or account change while staff are logged in as the customer) |
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
| mistakes reported (`POST reports/`), per client address, the website's included | 5 an hour and 20 a day | fixed |
| the couriers' webhook (`POST /api/hooks/parcel-events/`), per client address | 300 a minute | `API_THROTTLE_PARCEL_EVENTS` |
| MSG91's delivery reports (`POST /api/hooks/sms-events/`), per client address | 300 a minute | `API_THROTTLE_SMS_EVENTS` |
| ERPNext's webhook (`POST /api/hooks/erp-events/`), per client address | 600 a minute | `API_THROTTLE_ERP_EVENTS` |
| the support mailbox's hook (`POST /api/hooks/support-mail/`), per client address | 120 a minute | `API_THROTTLE_SUPPORT_MAIL` |
| new requests from My requests (`POST me/tickets/`), per account | 10 an hour | `API_THROTTLE_SUPPORT_REQUEST` |
| a member of staff logged in as a customer, opened or ended (`account/impersonate/`), per client address | 20 an hour | `API_THROTTLE_IMPERSONATE` |
| the staff API (`staff/…`), per member of staff or API key | 600 a minute | `STAFF_THROTTLE` |
| searches that cost a query: customers (`GET staff/users/`), orders, Finance's payments, the support queue and a ticket's book-code lookup, a person searched for among the course's entitlements (`?q=`), a learner's page | 60 a minute | `STAFF_THROTTLE_SEARCH` |
| reveals of a customer's, a ticket's, a nominee's or a bank refund's payee details, and impersonation tokens (`staff/users/<id>/reveal/`, `…/impersonate/`, `staff/support/tickets/<number>/reveal/`, `staff/privacy/nominees/<user>/reveal/`, `staff/orders/refunds/<id>/payee/`) | 30 an hour | `STAFF_THROTTLE_REVEAL` |
| exports and the files made as jobs (`staff/audit/export/`, `staff/jobs/` of any kind but a bulk action, the GSTR-1 file, a day of settlements fetched) | 10 an hour | `STAFF_THROTTLE_EXPORT` |
| bulk actions started (`staff/jobs/` of kind `bulk_action`, and the catalogue's import) | 20 an hour | `STAFF_THROTTLE_BULK` |
| a template sent to oneself (`staff/templates/<id>/test/`) | 10 an hour | `STAFF_THROTTLE_TEST_SEND` |
| the staff reports (`staff/reports/…`), per member of staff or API key | 60 a minute | `STAFF_THROTTLE_REPORTS` |
| book codes looked up (`POST staff/course/codes/lookup/`) | 120 an hour | `STAFF_THROTTLE_CODE_LOOKUP` |
| money actions and approvals (`staff/change-requests/` asked, approved, run; role grants, invitations, offboarding; staff orders, refunds (a bank one marked paid too), offline payments and quotes made into orders; products, coupons and offers made or changed; a ticket's refund and cancel) | 120 an hour | `STAFF_THROTTLE_MONEY` |
| staff invitations accepted (`staff/invites/accept/`), per client address | 10 an hour | `STAFF_THROTTLE_INVITE` |

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
