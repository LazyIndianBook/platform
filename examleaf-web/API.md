# ExamLeaf API (v1)

The REST API behind the ExamLeaf app: the public catalogue (boards, subjects, books, papers), the solutions (for a
signed-in student with a confirmed email address, as on the website, or for everyone while the site's solutions are
open), the student's record of attempts, the account with its data rights (Download my data, Delete my account), and
the shop (books, cart, addresses, orders, payment with Razorpay's mobile SDK, invoices). Code: `api/` (`shop.py` for
the shop), settings: `examleaf/api_settings.py`, URLs: `api/urls.py` under `examleaf/api_urls.py`.

- Base URL: `https://<domain>/api/v1/`. Every path ends with `/`; a path without it answers 404 (no redirect).
- JSON only, both ways (`Content-Type: application/json`); anything else gets 415 (request) or 406 (`Accept`).
- Dates are ISO 8601, times with the Indian offset (`2026-10-15T10:00:00+05:30`); marks are decimal strings (`"52.5"`);
  money is a decimal string in rupees (`"299.00"`), except Razorpay's own `amount`, an integer in paise.
- OpenAPI 3 schema: `/api/schema/` (YAML; `?format=json` for JSON). Swagger UI: `/api/docs/`. Redoc: `/api/redoc/`.
  Both pages are served by the site itself (drf-spectacular-sidecar), so the Content-Security-Policy stays strict.
- `X-Request-ID`: send a UUID and it comes back in the response and in the server's log lines (otherwise the server
  makes one). Quote it when reporting a problem.

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

**Log in** with email and password. If the address is not confirmed yet, the answer is
`400 {"detail": "E-mail is not verified.", "verification_token": "..."}` and a new code is emailed (at most one every
three minutes): show the code screen and continue with verify-email.

```sh
curl -X POST https://examleaf.in/api/v1/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email": "rahul@example.com", "password": "Brahmaputra-2027"}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "user": {...}}
```

**Log in with a code by SMS** (no password), for a student who confirmed a mobile number on the website (My account:
the app cannot add or confirm one). `auth/phone/code/` takes the number as people type it ("98640 12345",
"+91 98640 12345", "098640 12345") and texts a 6-digit code if an account confirmed that number; every other Indian
mobile number gets the same answer and no SMS. `auth/phone/confirm/` takes the token and the code and answers as a
log-in. A wrong code is `400 {"code": [...]}`; three wrong codes, or 3 minutes, end the token:
`400 {"verification_token": ["Expired. Ask for a new code."]}`. At most 3 codes an hour per number (however it is
typed) and 5 a minute per client address: 429 above it. `404` while the server sends no SMS (`SMS_BACKEND` not set).

```sh
curl -X POST https://examleaf.in/api/v1/auth/phone/code/ -H 'Content-Type: application/json' -d '{"phone": "98640 12345"}'
# 200 {"detail": "Code sent by SMS.", "verification_token": "x8f2k1..."}
# 400 {"phone": ["Enter a 10-digit Indian mobile number."]}
curl -X POST https://examleaf.in/api/v1/auth/phone/confirm/ -H 'Content-Type: application/json' \
  -d '{"verification_token": "x8f2k1...", "code": "483920"}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "user": {...}}
```

**Refresh** when a request answers 401 with `"code": "token_not_valid"` (or a little before the access token runs
out). Every refresh returns a **new refresh token** and the old one stops working: always store the new one, and
send one refresh at a time.

```sh
curl -X POST https://examleaf.in/api/v1/auth/token/refresh/ -H 'Content-Type: application/json' -d '{"refresh": "eyJ..."}'
# 200 {"access": "eyJ...", "refresh": "eyJ..."}      401: log in again
```

**Log out** by sending the refresh token, which is then refused for good; forget both tokens in the app.

```sh
curl -X POST https://examleaf.in/api/v1/auth/logout/ -H 'Content-Type: application/json' -d '{"refresh": "eyJ..."}'
```

**Passwords.** `auth/password/change/` (signed in: `old_password`, `new_password1`, `new_password2`) and a password
reset ends every token of the account, on every device: log in again afterwards. The owner is told by email, as on the
website. `auth/password/reset/` (`email`) always answers 200 and emails a link to the website's "new password" page,
`<SITE_URL>/account/password/reset/key/<uid>-<token>/`; an app that opens such links itself can post `uid`, `token`,
`new_password1` and `new_password2` to `auth/password/reset/confirm/`. When an account deletion is carried out
(seven days after the request), every token of the account ends too.

Log-in, log-out, sign-up, verify-email, the SMS code endpoints and password reset ignore the `Authorization` header,
so an expired token left in it does no harm there.

## Endpoints

| Method and path | Who | What |
|---|---|---|
| `POST auth/registration/` | anyone | sign up; emails a code |
| `POST auth/registration/verify-email/` | anyone | the code; returns the tokens |
| `POST auth/login/`, `auth/logout/` | anyone | tokens in, refresh token out |
| `POST auth/token/refresh/`, `auth/token/verify/` | anyone | new tokens; check a token |
| `POST auth/password/reset/`, `auth/password/reset/confirm/` | anyone | forgotten password |
| `POST auth/password/change/` | signed in | new password |
| `GET PUT PATCH me/` | signed in | profile; changeable: `full_name`, `phone`, `class_level`, `board`, `district` |
| `POST me/export/` | signed in | Download my data (`password`): everything kept about the user |
| `POST DELETE me/deletion/` | signed in | Delete my account (`password`), due in 7 days; DELETE cancels |
| `GET boards/`, `boards/<id>/`, `subjects/` (`?board=`), `subjects/<id>/` | anyone | the boards and subjects |
| `GET books/`, `books/<slug>/` | anyone | books with their papers (`code`, `tier`, `number`, `title`, `is_published`) |
| `GET papers/`, `papers/<code>/` | anyone | paper details: marks, time, instructions, `web_url`, `solutions_url` |
| `GET papers/<code>/solutions/` | signed in, email confirmed (anyone while solutions are open) | the questions in order, each with its solution |
| `GET qr/<code>/` | anyone | a scanned code (any case) to its paper and `solutions_url` |
| `GET POST attempts/`, `GET PUT PATCH DELETE attempts/<id>/` | signed in, email confirmed | the student's own record |
| `GET products/`, `products/<slug>/` | anyone | the books on sale: prices, pictures, a bundle's books, `in_stock` |
| `GET cart/`, `POST cart/items/`, `PUT PATCH DELETE cart/items/<slug>/`, `POST DELETE cart/coupon/` | signed in, email confirmed | the account's cart (`?state=` adds the shipping) |
| `GET POST addresses/`, `GET PUT PATCH DELETE addresses/<id>/` | signed in, email confirmed | saved delivery addresses |
| `GET POST orders/`, `GET orders/<number>/` | signed in, email confirmed | the customer's orders; POST is the checkout |
| `POST orders/<number>/cancel/` | signed in, email confirmed | cancel (an online payment is refunded) |
| `POST orders/<number>/payment/`, `orders/<number>/payment/confirm/` | signed in, email confirmed | options for Razorpay's SDK; its answer, checked |
| `GET orders/<number>/invoice/`, `orders/<number>/credit-notes/<id>/` | signed in, email confirmed | PDF files, not JSON |
| `POST orders/lookup/` | anyone | a guest's order by number and email |

Only published papers appear, as on the website. The email address, date of birth and parent details are read-only
here (the email changes on the website, after a code; the others decide the consent rules). The QR codes in the books
encode `<SITE_URL>/s/<CODE>/`: the app reads the code from the scanned address and asks `qr/<code>/`.

```sh
curl https://examleaf.in/api/v1/books/physics-2027/
curl 'https://examleaf.in/api/v1/papers/?subject=1&tier=H&ordering=number'
curl -H "Authorization: Bearer $ACCESS" https://examleaf.in/api/v1/papers/PHY-E01/solutions/
```

A question of `solutions/` (Markdown with `$…$` maths; `solution.html` is rendered by the site, with the maths left
for KaTeX; `is_alternative` marks the OR choice of the question before it; `number` is what the book prints):

```json
{"order": 17, "label": "2(b)", "number": "2(b)", "part_label": "",
 "group_label": "2. Answer any ten questions from the following as directed : `2×10=20`", "is_alternative": false,
 "text": "Give reason why the potential energy of a system of two positive point charges is always positive.",
 "table": "", "options": [], "marks": "2",
 "solution": {"markdown": "| Step | Marks |\n|---|---|\n| The charges repel each other, ... | 1 |\n...",
              "html": "<div class=\"table-scroll\"><table class=\"steps\">..."}}
```

Attempts: `paper` (code, published papers only), `marks_obtained` (0 to the paper's full marks, halves allowed),
`date` (default today), `time_taken_minutes`, `notes`; the answer adds `subject`, `tier`, `full_marks`, `percent`.
The paper of an attempt cannot change. Filters: `?subject=<id>&tier=E|M|H`.

```sh
curl -X POST https://examleaf.in/api/v1/attempts/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"paper": "PHY-E01", "marks_obtained": "52.5", "time_taken_minutes": 170, "notes": "revise optics"}'
curl -X POST https://examleaf.in/api/v1/me/deletion/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"password": "Brahmaputra-2027"}'
# 201 {"status": "pending", "requested_at": "...", "due_at": "..."}
```

Teachers cannot see their students' attempts yet: nothing links a student to a teacher (see the TODO in `api/views.py`).

When the site's solutions are open (`SOLUTIONS_REQUIRE_LOGIN=0`), `papers/<code>/solutions/` answers everyone, with
`Cache-Control: public, max-age=300`; saving attempts still needs an account.

## Shop

The website's shop, for the app: the same prices, stock, coupons, shipping rates, emails and order pages. Customer
data (cart, addresses, orders) needs a signed-in account with a confirmed email address; another customer's address
or order answers 404. Visitors without an account shop on the website: the API keeps no session carts. While the shop
is closed (`SHOP_OPEN=0`, before the launch) changing the cart, checkout and payment answer 403
`{"detail": "The shop opens soon."}` except for staff; products, the cart, addresses and orders can still be read.

**Products** (public): `slug`, `title`, `kind` (`sample-papers`, `solutions`, `bundle`), `subject` (code), `book` (its
slug in `books/`), `isbn`, `pages`, `description` (Markdown), `cover` and `images` (`url`, `alt`), `mrp`, `price`,
`saving_percent`, `gst_rate`, `hsn_code`, `in_stock` (whether copies can be ordered; a bundle needs each of its
books; the number of copies is not given), `bundle_items` (`product`, `title`, `quantity`), `web_url`. Filters:
`?kind=`, `?subject=<id>`, `?search=`. The picture URLs are the uploaded originals: on the media domain
(`https://media.examleaf.in/products/…`, cached a year, a new upload gets a new name) once the site uses its buckets,
under `https://examleaf.in/shop/media/products/…` before; the website shows AVIF and WebP sizes of them (phase 5 B).

**Cart**: every answer is the whole cart at today's prices: `items` (`product`, `title`, `price`, `quantity`,
`total`), `count`, `coupon`, `coupon_problem` (why the coupon does not apply now), `subtotal`, `discount`, `shipping`
(null unless `?state=AS`, a two-letter state code, is given), `total`, `problems` (books off sale or short of stock,
which stop the checkout).

```sh
curl -X POST https://examleaf.in/api/v1/cart/items/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"product": "physics-sample-papers", "quantity": 2}'    # adds 2 copies (at most 20 of a book)
curl -X PATCH https://examleaf.in/api/v1/cart/items/physics-sample-papers/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"quantity": 1}'   # sets the copies; 0, or DELETE, removes the book
curl -X POST 'https://examleaf.in/api/v1/cart/coupon/?state=AS' -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"code": "welcome10"}'
# 200 {"items": [...], "count": 1, "coupon": "WELCOME10", "coupon_problem": null, "subtotal": "299.00",
#      "discount": "29.90", "shipping": "40.00", "total": "309.10", "problems": []}
# 400 {"code": ["This code cannot be applied to this cart."]}   whatever the reason: unknown, expired, used up, too
#     small a cart; 10 codes an hour per user (429 after)
```

**Addresses**: `name`, `phone` (a 10-digit Indian mobile number; answered as `+919864012345`), `line1`, `line2`,
`city`, `district`, `state` (two-letter code, `AS`), `pin` (6 digits), `is_default` (one address at most). Once the
India Post directory is loaded, the state must be the PIN code's (`400 {"state": ["PIN code 781001 is in Assam."]}`;
PIN codes missing from the directory are not checked; phase 5 B). To fill in the district and state from a PIN code,
the app may call the website's `GET https://examleaf.in/shop/pin/781001/` (no log-in; `200 {"pin": "781001", "states":
["AS"], "districts": ["Kamrup Metro"]}`, 404 when unknown; cached a day); a few PIN codes lie in two states.

**Checkout**: `POST orders/` with `address` (an id from `addresses/`) and `payment_method` (`razorpay`, or `cod` when
the site offers cash on delivery) makes an order from the cart; the address is copied into it. An online order is
`pending` until paid; a cash-on-delivery order is placed at once and the cart emptied. Cash on delivery is for orders
worth at most ₹1,500 (`SHOP_COD_MAX_VALUE`, shipping included), and at most two such orders on their way per account.
Refusals (empty cart, sold out, a coupon that no longer applies, cash on delivery not offered or over those limits) are
`400 {"non_field_errors": ["..."]}`. Checkouts are limited to 10 per 10 minutes per client address, the website's
included (429).

An order: `number`, `created`, `placed_at`, `status` (`pending`, `paid`, `packed`, `shipped`, `delivered`,
`cancelled`, `refunded`), `status_label` (as the website shows it: "awaiting payment", "placed (pay on delivery)",
...), `payment_method`, `email`, `shipping_address`, `items` (`product`, `title`, `hsn_code`, `gst_rate`, `mrp`,
`unit_price`, `quantity`, `line_total`), `subtotal`, `discount`, `shipping_fee`, `total`, `coupon_code`, `timeline`
(`status`, `at`), `shipments` (`courier`, `tracking_number`, `tracking_url`, `shipped_at`, `delivered_at`), `refunds`
(`amount`, `status`, `reason`, `created`, `processed_at`), `can_cancel`, `can_pay`, `invoice` (`number`, `created`,
`url`; null until the PDF exists), `credit_notes` (the same with `amount`), `web_url`. The list (`orders/`, newest
first, `?status=`) gives `number`, `created`, `placed_at`, `status`, `status_label`, `payment_method`, `total` and the
`items` as text.

**Paying** with Razorpay's mobile SDK (Android `com.razorpay:checkout`, iOS `razorpay-pod`):

1. `POST orders/<number>/payment/` returns the SDK's options: `key`, `order_id` (Razorpay's order, the same on every
   call), `amount` (paise), `currency`, `name`, `description`, `prefill`, `notes`, `theme`, and `test_mode`. 503:
   Razorpay cannot be reached, try again later; 400 when the order is not waiting for an online payment (`can_pay`
   is false).
2. Open the SDK with those options. On success it returns `razorpay_order_id`, `razorpay_payment_id` and
   `razorpay_signature`: `POST` them to `orders/<number>/payment/confirm/`. The answer is the order, `paid` (and the
   cart is emptied), or still `pending` for a few minutes when Razorpay could not be asked: Razorpay's webhook to the
   site completes it, so read `orders/<number>/` again. A wrong signature: `400 {"non_field_errors": ["We could not
   confirm this payment. ..."]}`.
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
```

**Cancel**: `POST orders/<number>/cancel/` while `can_cancel` (pending or paid); an online payment is refunded in full
(5–7 working days; the order lists the refund, then turns `refunded`). Later: 400, see the Refund Policy.

**Invoices and credit notes** are PDF files: `GET orders/<number>/invoice/` and `orders/<number>/credit-notes/<id>/`
(the `url`s in the order) answer `application/pdf` as a download whatever the `Accept` header; 404 (JSON) until the
file exists. Each refund of an invoiced order gets a credit note.

**Guests** (who ordered on the website without an account): `POST orders/lookup/` with `number` and `email` never
returns the order. If a guest order has that number and email address, the link to it is emailed to that address;
the answer is always `200 {"detail": "If an order matches, we have emailed you a link."}`. Orders of accounts are
left out (their owners sign in). Limited to 10 an hour per client address (`API_THROTTLE_ORDER_LOOKUP`), and to 10 an
hour per email address and per order number from any address; 429 also while the limits cannot be counted. (Changed
in phase 4: the lookup used to return the order, or 404.)

**The order's link** is on the website, not in the API: every email about an order carries
`https://examleaf.in/orders/t/<token>/`, a secret of 22 characters per order. It shows the order without signing in
(status, books, address, tracking, refunds; no payment), its PDFs (`/orders/t/<token>/invoice/`,
`/orders/t/<token>/credit-notes/<id>/`) and, while the order is pending or paid, a cancel button
(`POST /orders/t/<token>/cancel/`). The API does not give the token.

## Lists

Lists are paginated: `{"count": 120, "next": "<url>", "previous": null, "results": [...]}`, 50 a page,
`?page=2`, `?page_size=` up to 200. `?search=` searches books (title, subject) and papers (code, title);
`?ordering=` sorts (`-number` for descending): papers by `code`, `number`, `tier`; books by `id`, `title`; attempts by
`date`, `marks_obtained`, `created`. Filters: papers `?book=<slug>&subject=<id>&tier=`, books `?subject=<id>`,
subjects `?board=<id>`. The catalogue is cached on the server for 15 minutes.

## Errors

DRF's standard format, always JSON:

| Status | Body |
|---|---|
| 400 | the fields' errors: `{"marks_obtained": ["Enter marks from 0 to 70."]}`; others (and the shop's rules) under `non_field_errors`; `{"detail": "Bad request."}` for a request Django refuses before the API sees it (a host name that is not served) |
| 401 | `{"detail": "Authentication credentials were not provided."}`; a bad or expired token adds `"code": "token_not_valid"` |
| 403 | `{"detail": "Confirm your email address first."}` (or another reason; `"The shop opens soon."` while the shop is closed) |
| 404 | `{"detail": "No Paper matches the given query."}`, `{"detail": "Not found."}` |
| 405, 406, 415 | `{"detail": "..."}` |
| 413 | `{"detail": "The request body is too large."}` (over 1 MB, `DATA_UPLOAD_MAX_MEMORY_SIZE`) |
| 429 | `{"detail": "Request was throttled. Expected available in 38 seconds."}` with a `Retry-After` header |
| 500 | `{"detail": "Server error."}`; reported to Sentry, with the request ID in `X-Request-ID` (the site's own pages show an error page) |
| 503 | `{"detail": "The payment service could not be reached."}` (Razorpay, `orders/<number>/payment/`): try again |

## Rate limits

Counted in the cache (Redis in production), per client address for anonymous requests and per user once signed in:

| Scope | Default | Setting |
|---|---|---|
| anonymous | 200 a minute | `API_THROTTLE_ANON` |
| signed in | 600 a minute | `API_THROTTLE_USER` |
| log-in, log-out, sign-up, codes, passwords, data export, deletion | 30 a minute | `API_THROTTLE_AUTH` |
| guests' order lookup (`orders/lookup/`), per client address | 10 an hour | `API_THROTTLE_ORDER_LOOKUP` |
| starting and confirming payments (`orders/<number>/payment/…`) | 30 a minute | `API_THROTTLE_PAYMENT` |
| coupon codes tried (`POST cart/coupon/`), per user | 10 an hour | `API_THROTTLE_COUPON` |
| guests' order lookup, per email address and per order number (any address) | 10 an hour | fixed |
| checkout (`POST orders/`), per client address, the website's included | 10 in 10 minutes | fixed |

The last two are counted by the shop itself and refuse (429) while the cache cannot be read (Redis down); the others
let requests through meanwhile.

A whole classroom often shares one address: raise the limits rather than lower them. django-axes still locks an
account for 15 minutes after 10 failed log-ins from one address, through the API too.

Per account, whatever the address (the website's limits, counted together with it):
- **log-in:** after 5 failed log-ins in 5 minutes, even the right password gets 400 "Too many failed login attempts.
  Try again later." for the rest of those 5 minutes;
- **password reset:** 5 emails a minute per email address (`auth/password/reset/` answers 429 above it);
- **SMS codes** (`auth/phone/code/`): 3 an hour per number and 5 a minute per client address (429 above it), and the
  site sends at most `SMS_DAILY_CAP` SMS a day in all (counted in the database, so also while Redis is down);
- **passwords of a signed-in user** (`auth/password/change/`, `me/export/`, `me/deletion/`): after 5 wrong ones in an
  hour every refresh token of the user is revoked (the app must log in again once the access token expires) and these
  answer 429 until the hour is over;
- **attempts:** at most 20 new attempts of one paper a day (400 with the reason); notes at most 2,000 characters. While
  a parent's consent is awaited (`PARENTAL_CONSENT_MODE=verified`, a student under 18) no attempt can be saved (400).

## CORS

None is needed by the app or the website. A web client on another origin must be listed in `CORS_ALLOWED_ORIGINS`;
only `/api/` answers CORS requests, without cookies (send the access token).

## Versioning

The version is in the path (`/api/v1/`). Within v1, changes only add: new endpoints, new fields in answers, new
optional parameters; clients must ignore fields they do not know. Removing or renaming a field, changing a type or a
meaning, or a new required parameter makes a v2, served beside v1 until the app versions that use v1 are retired (at
least six months, announced in the app). `ALLOWED_VERSIONS` in `examleaf/api_settings.py` lists the versions served.

## Operations

- Refresh tokens and their blacklist are kept in the database; `api.tasks.flush_expired_tokens` (celery beat, 04:30,
  editable in the admin under Periodic tasks) deletes the expired ones.
- The tokens are signed with `JWT_SIGNING_KEY`, or `SECRET_KEY` while it is unset: rotating it logs every app out.
- There is no health endpoint under `/api/` (it was open to anyone); the uptime monitor uses `/health/`.
- Tests: `api/tests.py` (sign-up rules, codes, tokens, gated solutions, attempts, data rights, query counts,
  limits, body size, CORS, schema validity) and `shop/test_api.py` (products, cart, addresses, checkout, payment and
  a bad signature, cancellation, the PDFs, other customers' orders, cash on delivery, lookup and its limit) and
  `shop/test_security.py` (the security review's shop fixes: order links, test and live mode, limits, refunds). `manage.py spectacular --validate --fail-on-warn --file schema.yml` checks the schema.
