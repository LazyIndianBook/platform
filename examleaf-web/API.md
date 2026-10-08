# ExamLeaf API (v1)

The REST API behind the ExamLeaf app: the public catalogue (boards, subjects, books, papers), the solutions (for a
signed-in student with a confirmed email address, as on the website, or for everyone while the site's solutions are
open), the student's record of attempts, the account with its data rights (Download my data, Delete my account), the
shop (books, categories, collections, cart, addresses, orders, payment with Razorpay's mobile SDK, invoices) and the
revision course (chapters, clips, quiz, flash cards, a pass plan, book codes). Code: `api/` (`auth.py`, `views.py`,
`serializers.py`, `shop.py`, `learn.py`), settings: `examleaf/api_settings.py`, URLs: `api/urls.py` under
`examleaf/api_urls.py`.

## Contents

[Conventions](#conventions) · [Endpoints](#endpoints) · [Authentication](#authentication-from-the-app) ·
[Frontend integration guide](#frontend-integration-guide) · [Profile and data rights](#profile-and-data-rights) ·
[Catalogue and solutions](#catalogue-and-solutions) · [Attempts](#attempts) · [Store catalogue](#store-catalogue) ·
[Shop](#shop) · [Revision course](#revision-course) · [Site](#site-configuration-and-legal-pages) · [Lists](#lists) ·
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

Paths are under `/api/v1/` except those of the last two rows. Who: **anyone** needs no sign-in; **signed in** needs a
valid access token (or the website's session); **confirmed** also needs a confirmed email address. **Shop open**: while
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
| GET | `config/` | anyone | what the server has switched on: log-in methods, Turnstile, the shop, consent mode |
| GET | `pages/`, `pages/<slug>/` | anyone | the legal pages: Markdown, the website's HTML, version, last change |
| POST | `contact/` | anyone | the contact form: a message emailed to the support address |
| GET | `/api/schema/`, `/api/docs/`, `/api/redoc/` | anyone | the OpenAPI schema, Swagger UI, Redoc |
| any | `/_allauth/app/v1/…`, `/_allauth/browser/v1/…` | anyone; the account and authenticator endpoints need the signed-in session | allauth.headless: log-in, sign-up, codes, passkeys, Google, second step, email, phone, password, re-authentication, signed-in devices (`auth/sessions`); its OpenAPI file `/_allauth/openapi.json` (and `.yaml`) |

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

## Site configuration and legal pages

`config/` (anyone, `Cache-Control: public, max-age=300`) is what this server has switched on, for frontends to follow
rather than hard-code: `auth` (`login_methods`, `login_by_code`, `sms`, `google`, `passkeys`, `turnstile_site_key`,
null while the bot check is off), `shop` (`open`, `cod`, `cod_max_value`, `currency`), `shipping` (`fee_from`,
`free_above`: the lowest delivery fee and free-delivery value of `shipping/`, null without rates),
`solutions_require_login`,
`parental_consent` (`declared` or `verified`) and `support` (`email`: `SUPPORT_EMAIL`, else `SELLER_EMAIL`; `phone`:
`SELLER_PHONE`; each null while it still holds a `[placeholder]`) and `app_links` (`android`, `ios`: the app's pages on
Google Play and the App Store, `APP_LINK_ANDROID` and `APP_LINK_IOS`; null until set). allauth.headless's
`/_allauth/<client>/v1/config` adds allauth's own view (the providers, the authenticator types, `usersessions`).

`pages/` and `pages/<slug>/` (anyone; cached 15 minutes) are the legal and policy pages, `privacy`, `terms`, `refunds`,
`shipping` and `contact`: `slug`, `title`, `version` (consent records keep the privacy notice's), `updated` (the last
change, as in the page's history), `markdown`, `html` (the website's rendering; a `[placeholder]` still to fill in is
marked `<mark class="placeholder">`) and `web_url`.

`contact/` (anyone) is the website's contact form: `name` (80 characters at most), `email` (we reply to it), `message`
(2,000 at most) and `turnstile` while the bot check is on. The message is emailed to the support address with
`Reply-To` the sender; nothing is stored. `200 {"detail": "Thank you: your message is on its way to us. We reply by
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
#      "support": {"email": "help@examleaf.in", "phone": null}, "app_links": {"android": null, "ios": null}}
curl https://examleaf.in/api/v1/pages/privacy/
# 200 {"slug": "privacy", "title": "Privacy Policy", "version": "2026-10-08", "updated": "...", "markdown": "...",
#      "html": "<h2>...", "web_url": "https://examleaf.in/privacy/"}
```

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

## Errors

DRF's standard format, always JSON:

| Status | Body |
|---|---|
| 400 | the fields' errors: `{"marks_obtained": ["Enter marks from 0 to 70."]}`; others (and the shop's rules) under `non_field_errors`; `{"detail": "Bad request."}` for a request Django refuses before the API sees it (a host name that is not served) |
| 401 | `{"detail": "Authentication credentials were not provided."}`; a bad or expired token: `{"detail": "Given token not valid for any token type", "code": "token_not_valid", "messages": [...]}` (refresh it); `"code": "password_changed"` or `"user_inactive"` (the password was changed, the account closed: log in again) |
| 403 | `{"detail": "Confirm your email address first."}` (or another reason; `"The shop opens soon."` while the shop is closed; `"Unlock this subject with the code printed in your book."` for a locked course; `"A parent or guardian has not confirmed this account yet."` for what the course saves while `consent_pending`) |
| 404 | `{"detail": "No Paper matches the given query."}`, `{"detail": "Not found."}` |
| 405, 406, 415 | `{"detail": "..."}` |
| 413 | `{"detail": "The request body is too large."}` (over 1 MB, `DATA_UPLOAD_MAX_MEMORY_SIZE`) |
| 429 | `{"detail": "..."}`: DRF's limits say "Request was throttled. Expected available in 38 seconds." and carry a `Retry-After` header; allauth's (codes, password reset, wrong passwords) have their own text and no `Retry-After`; allauth.headless answers `{"status": 429}` |
| 500 | `{"detail": "Server error."}`; reported to Sentry, with the request ID in `X-Request-ID` (the site's own pages show an error page) |
| 503 | `{"detail": "The payment service could not be reached."}` (or "Online payment is not set up yet."), from `orders/<number>/payment/`: try again |

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
