# Changelog

What changed in the ExamLeaf web platform, newest first, by phase. Every phase below was built on 8 October 2026; the
commits are in `git log` (phase 4: abffe6f and e5abda5; phase 5 A and B with the redesign's stage 1: f8e4e5f; phase 6 D
and E: 4e30e59; the redesign's stage 2 so far: ba0b9dd). Details of each feature are in README.md; the numbers of the
tests are those of `pytest` at the end of the phase.

## Phase 8 backend, account part (8 October 2026)

What the account and revision pages (8C) asked of the API, docs/examleaf-phase8-nextjs-plan.md "Backend gaps found
by 8C". 467 tests pass (7 skipped); allauth's migration `usersessions.0001_initial`, none of ours.

- **Every chapter:** `learn/chapters/` lists the whole syllabus, not only chapters with a published revision:
  `has_revision`, `revision_status` (`published` or `none`; a revision in draft shows as none, without its clips,
  minutes or free cards) and `free_preview` (the id of the chapter's free clip, so a preview plays without fetching the
  chapter), with `weight`, `frequency` and the filters as before; `learn/chapters/<id>/` still answers published
  chapters only.
- **My record in figures:** `GET me/record/` (`?subject=&tier=` as `attempts/`): the average per tier as My record
  rounds it, per subject, and per paper the best and the latest attempt, with counts.
- **What Download my data holds:** `GET me/export/summary/`: each part's key, the website's words and its count,
  without the file or the password.
- **App store links:** `config/` `app_links` (`android`, `ios`) from the new settings `APP_LINK_ANDROID` and
  `APP_LINK_IOS` (empty: null).
- **Signed-in devices:** `allauth.usersessions` with its middleware and `USERSESSIONS_TRACK_ACTIVITY`;
  allauth.headless's `GET`/`DELETE /_allauth/<client>/v1/auth/sessions` list them (address, browser, first and last
  request, the current one marked) and sign out the others, so the API has no endpoint of its own for it. The rows are
  in Download my data (`sessions`, without the keys), deleted with the account, and dropped the night after their
  session ends (`ops.tasks.clear_sessions`); the admin shows them read-only (allauth's own admin searched
  `user__username`, which this User has not).
- **Export and deletion without a password:** `me/export/` and `me/deletion/` take the password or, without one, a
  browser session that logged in or re-authenticated through allauth (`auth/reauthenticate`, `auth/2fa/reauthenticate`,
  or Google again) in the last 5 minutes; otherwise `403 {"detail": ..., "code": "reauthentication_required"}`. A
  password sent is still checked and counted (L6). Not allauth's `did_recently_authenticate`, which lets an account
  with neither a password nor a second step through at any time.
- **Typed answers:** `learn/plan/` (`Plan`, the same JSON as before) and `me/record/` (`Record`) in the OpenAPI schema,
  for the generated TypeScript; `spectacular --validate --fail-on-warn` clean.
- Tests: `api/test_account.py` and the chapters test; two page query-count tests (`content`, `practice`) make one
  request first, as the first request after `force_login` records the device.

## Phase 8 backend, second part (8 October 2026)

The four API gaps the shop frontend (8B) found, docs/examleaf-phase8-nextjs-plan.md "Backend gaps found by 8B". 461
tests pass (7 skipped); no migration.

- **Picture sizes in the API:** `cover` and each of `images` on `products/` and `products/<slug>/` are now
  `{sources, src, width, height, alt}`: the AVIF and WebP sizes django-pictures makes (`sources["image/avif"]["400"]`,
  absolute URLs; a cover's 2/3 cut), the uploaded original as `src` with its size, and `alt` ("Cover of <title>" for a
  cover). This replaces `cover` as a URL and `images[]` as `{url, alt}`. Built from the field's `aspect_ratios`
  (`api.shop.picture`), not `pictures.contrib.rest_framework.PictureField`, which nests the sizes by ratio with
  relative URLs and lets `?cover_ratio=`/`?cover_container=` raise a server error on a wrong value.
- **Renamed products:** `GET products/<old slug>/` answers 301 to `products/<new slug>/` with
  `{"redirect_to": "<new slug>"}` for clients that do not follow redirects, as the website's page redirects by
  `SlugHistory`; 404 once the product is off sale.
- **Orders say what they ship:** `is_digital` (courses only, a bundle of courses included) and `has_shipping` (its
  opposite) on `orders/`, `orders/<number>/`, `orders/t/<token>/` and the checkout's answer, read from the order's
  lines (the list now fetches their products with them).
- **Product SEO fields:** `meta_title` and `meta_description` (the admin's "page title" and "meta description", `""`
  when not written) and `og_image` (the link preview's absolute URL, null until the worker has made it) on products;
  the OpenAPI schema has a product's response example.

## Phase 8 backend (8 October 2026)

What the Next.js frontend (docs/examleaf-phase8-nextjs-plan.md) needed from the API, with the website's rules. 459
tests pass (7 skipped).

- **Guest cart and checkout through the API:** `cart/`, `cart/items/…` and `cart/coupon/` serve visitors too: a browser
  on the site's origin by the session cookie (the CSRF token on every change; DRF checks it only for signed-in
  sessions, so `api.shop.GuestOrCustomer` does), a client without cookies by `X-Cart-Token`, issued once by
  `POST cart/` (`Cart.token`: its SHA-256, 30 days; migration `shop.0020_cart_token`; `CORS_ALLOW_HEADERS` lists it).
  Signed-in callers are unchanged (a confirmed email address). A visitor's coupons ask for Turnstile and count 10 an
  hour per client address with the website's cart page. `POST orders/` takes a visitor's `email`, `shipping_address`
  (the rules of `addresses/`, the PIN code's state included), `payment_method` and `turnstile`: cash on delivery
  refused (M8), a course needs an account, 10 checkouts per 10 minutes per address (shared); the answer is the order
  as its link shows it with the link's `token`, once. `POST orders/t/<token>/payment/` and `…/payment/confirm/` pay a
  guest's order (an account's: 404) and empty the visitor's cart; `can_pay` of `orders/t/<token>/` is true for a
  guest's pending order. The guest cart joins the account's at log-in: the session's by the existing signal
  (`shop.cart.merge_carts`, now shared), a token's on the first signed-in cart call carrying it. While the shop is
  closed visitors get 403 "The shop opens soon." like everyone.
- **The order's link without Django's pages:** `POST orders/t/<token>/cancel/`, `GET orders/t/<token>/invoice/` and
  `…/credit-notes/<id>/`; the link's `invoice.url` and `credit_notes[].url` point there (the frontend serves
  `/orders/t/…` once Caddy switches).
- **Contact form:** `POST contact/` (name 80, message 2,000 characters, Turnstile, honeypot, 5 an hour per address with
  the website's form), emailed by `pages.views.send_contact` (now shared) with Reply-To the sender, nothing stored; 503
  while the support address is a `[placeholder]`. New setting `SUPPORT_EMAIL` (empty: `SELLER_EMAIL`), which
  `config/`'s `support.email` now follows.
- **Shipping:** `GET shipping/` (the rates and the lowest fee and free-delivery value), `GET shipping/quote/` (the fee
  to a PIN code or state for the caller's cart or an amount, with the PIN code's states and districts: the frontend's
  PIN autofill), and `shipping` in `config/` for "delivery from ₹40". `ShippingRate.rate_for` and `.summary`.
- **Frontend development:** README.md "The Next.js frontend in development" (Django on 8100 with
  `SITE_URL=http://localhost:3000`, `CSRF_TRUSTED_ORIGINS`, `USE_X_FORWARDED_HOST=1`; no CORS: one origin) and
  DEPLOYMENT.md section 20; `HEADLESS_FRONTEND_URLS`' fallback for a failed Google log-in is `/account/login/` (it shows
  `?error=`), the other entries and every email link are paths the frontend serves.
- Tests: `shop/test_api_guest.py` (browse, cart, coupon, order, mocked payment, confirm, the status page, cancel and
  PDFs by the link; the token client and its merge; CSRF and the merge at a headless log-in; the website's checks),
  and in `api/test_contract.py` (contact) and `shop/test_api_contract.py` (shipping).

## Phase 7 journeys (8 October 2026)

The user-journey gaps of docs/design/coverage-matrix.md closed where they were contained; what needs a founder's
decision or a missing feature is under its new "Open journeys" heading. 453 tests pass (7 skipped).

- **A sample with no wall (G1):** `Paper.is_sample`, one per book (a constraint; the data migration ticks each book's
  E-01; the admin's change form edits it): its solutions open without an account even with `SOLUTIONS_REQUIRE_LOGIN`
  on, on the website and in the API (`is_sample` in the paper serializers), cached publicly for 5 minutes. The home
  page's "See a sample paper", the book page, the product page and the wall of every other paper link to it.
- **Log in where you were (G15):** the header's Log in and Register carry `?next=` for the page (on the log-in pages,
  the `next` they were given), paths of this site only (`url_has_allowed_host_and_scheme` with no host allowed).
- **Guest orders join the account (G16):** an address confirmed (allauth's `email_confirmed`) or a log-in with confirmed
  addresses attaches the orders placed without an account under that address, any case, through `save` (history kept);
  My orders lists them.
- **From the order to the papers (G20):** the order's page and the delivered email link each book to its page ("Scan
  the QR code on each paper for its solutions") and a course to `/revision/`.
- **`/revision/` (G6):** the revision course on the website: what it is, each subject's chapters with the Board's marks
  and past questions, the free clips, the app (store links still `[placeholders]`), the student's entitlements and a
  book code form with the app's rules and limits (the same throttle counts as `api/v1/learn/redeem/`). My account,
  the footer and the sitemap link it.
- **Dead ends:** password reset sent, link expired, password changed (with Log in), account switched off, Google log-in
  cancelled or failed, the password asked again, the email and passkey pages: the site's words and a next step (G2, G4,
  G23). An expired parent's link names the student (as its SMS does) and offers Contact (G5). `/contact/` has a form that
  emails `SUPPORT_EMAIL` (else `SELLER_EMAIL`; no form while it is a `[placeholder]`), with Turnstile, a honeypot and 5
  an hour per address, storing nothing (G7). The 404 helps with an old order link (G19); a book without papers says so
  (G8); a missing invoice file is a 404 (G25).
- **Forms:** every form shows its button busy and is sent once (`site.js`, G9); a PIN code the directory lacks is said
  in its help (G12); the marks form saves back to the paper's `#record` and shows its errors there (G11), and a student
  whose parent has not confirmed sees why instead of a form (G17); My record names an empty filter with Show all (G10);
  the shop and its shelves get kind links for `?kind=` (G13); Download my data first lists what the file holds (G21).
  The address, sign-up, marks, checkout, lookup and contact forms say what each box needs, and every error summary
  names its field and links to it (a radio group at its first button).
- **Courses alone** are never called books, copies, shipping or delivery in the cart, checkout, order page and summary,
  or on the product page (`totals.digital_only`, the new `totals.has_digital`, `order.is_digital`,
  `product.digital_only`).
- **Platform:** KaTeX 0.19.0 served from `static/katex/` with its fonts and licence (checked byte for byte against the
  npm release; MAT-M02 draws its 397 formulas with no error), and jsDelivr gone from the CSP; 240 px covers for the
  home page's phone stage (`build_covers` run again); the four Latin fonts preloaded; messages inline on phones under
  600 px; product pictures cached for a year (`immutable`) and the product admin says while their sizes are made; a
  failed clip on the admin dashboard; signed-out PUT, PATCH and DELETE on `/_allauth/*/v1/account/phone` get allauth's
  401 instead of a server error; the privacy draft names the mobile number, the SMS log (90 days), reviews, stock
  alerts, quotations, the course's data, reminder devices and the parent's link; the design tokens copied to
  `docs/design/tokens.css`. The fonts were not re-subset: their originals have no tabular figures (Open journeys, T1).

## Phase 7 security (8 October 2026)

SECURITY_REVIEW_PHASE5_6.md: the High and the five Medium findings fixed, the Low and informational ones fixed or
decided; each has its status under it. 53 tests more (`learn/test_uploads.py`, `accounts/test_codes.py`,
`ops/test_sms_limits.py`, `accounts/test_parent_link.py`, `shop/test_offer_limits.py` and `test_review_lows.py` in
accounts, shop and learn; `learn/test_media.py` grew).

- **Slow requests (H1):** gunicorn runs threads (`--worker-class gthread --threads 8 --timeout 60`; it was a 10-minute
  timeout on sync workers). Caddy reads a body (up to 10 MB) before gunicorn sees it, and gives a client 10 seconds for
  its headers and 5 minutes for its body. Clip videos go from the editor's browser straight to the private bucket on a
  PUT link signed for 15 minutes with their size and type (`learn/uploads.py`, `static/learn/upload.js`), and the form
  carries only their signed name; without a bucket (development) they still come with the form, Caddy's 500 MB on the
  clip pages stays for that, and only signed-in staff may send such a body there (`LargeBodyGuard`).
- **Codes (M1, I7):** three tries per code, now also counted in the cache under a lock (parallel requests read the same
  count in the session); 5 email confirmation codes an hour and 10 a day per address, as actions of their own: allauth
  keeps one history per action and kind of key, so the review's `1/10s/key,10/d/key` would have capped nothing. Log-in
  codes: 3 an hour per address or number and 30 per client address; no "send a new code" on the log-in code page
  (allauth answered it with a server error for an unknown number). The API answers a refused code with a JSON 429.
- **SMS (M2):** limits in the SMS log before the daily cap: 5 an hour and 10 a day per number, 20 a day per account, and
  each purpose its share of the day (codes 70 %, order updates 30 %, parents' links 10 %). A refused SMS is never
  reported as sent: 429 "Too many messages have gone to this number…" (website and API), and the parent's link says it
  was not sent. The SMS log keeps the account (for the limits, Download my data and the deletion).
- **Parents' links (M3):** sent once the student has confirmed their own address (or at once after Google), never from
  an anonymous sign-up; fixed text, with the student's name only when it is plain letters (otherwise "a student"); at
  most 3 links a day to one address or number.
- **Offers (M4):** their usage limits are checked again under a lock when an order is paid or placed, as coupons are
  (`OfferUsedUp`: cancelled and refunded at capture, refused for cash on delivery and offline payments).
- **ffmpeg (M5):** a clip must be mp4/mov/m4v/webm/mkv with H.264, HEVC, VP9 or AV1 and AAC, Opus or MP3, checked by
  name and size before it is fetched and by ffprobe before ffmpeg decodes it; ffprobe and ffmpeg open local files only,
  those two demuxers and the decoders of those codecs, with two threads. The media worker has an environment of its own
  (`x-media-env`: the database, the queue, the buckets and `SECRET_KEY`), drops every capability and cannot gain any.
- **Smaller:** attribute filters refuse huge numbers and take 5 at most (L2); back-in-stock alerts for signed-in accounts
  only, to their own address (L3); API log-ins with a password or a code alone refused for staff and accounts with a
  second step (L4); staff cannot log in with a passkey alone (L5); a mobile number added or moved is emailed to both
  accounts (L6); a server does not start without `LEARN_CODE_SECRET`, nor does `make_book_codes` run (L7); 5 devices and
  1,000 quiz answers or card reviews a day per account, reminders sent 500 at a time by id, tokens Firebase calls invalid
  deleted (L8); the API's code sessions last 15 minutes and the PIN lookup is no longer kept in the server's cache (L9);
  deletion takes the SMS log and failed phone log-ins, Download my data has the SMS log, the email suppression and staff
  notes (L10); no staff order for a student whose parent has not confirmed (L11); the public bucket's storage keeps its
  key out of the picture tasks (L12); Turnstile is checked first and sent the client's address (I1); email subjects lose
  line breaks (I2); category imports check each slug (I4); revise-again lists only what the student may still open
  (I5); hls.js's hashes next to its licence (I8); Dependabot watches the Docker base image and no `.json` file reaches
  the image (I9).
- **To do before the next deployment:** set `LEARN_CODE_SECRET` in `.env` (the web container stops at `migrate`
  without it); add PUT to the private bucket's CORS rule (DEPLOYMENT.md section 17); for the reminders, a Firebase
  service account with the "Firebase Cloud Messaging API Admin" role only; a key for the public bucket alone in
  `PUBLIC_S3_*`.
- Open (decided in the review): refunds of offline payments (L11), Turnstile's hostname check (I1), staff discount and
  grant controls (I6), headless code confirmations counted in the session only (I7), firebase-admin's size and a
  blocking pip-audit (I9), clip links as bearer links (I10).

## QA pass of phases 5 and 6: every new flow walked (8 October 2026)

Every flow that phases 5 and 6 added was walked with the Django test client, with `curl` and a script against a
development server (sign-up, mobile number and codes by SMS and by email, the app's log-in by SMS, passkey pages,
parental consent by SMS, SES bounces and a send that they block, pictures, JSON-LD, the web app files, PIN codes,
tracking links, reviews, quotations, stock alerts, GSTR-1, the course API with and without access, book codes, the
plan, digital products, offers, staff orders, payment links, offline payments, every admin page for each role) and on
PostgreSQL 17, besides the unreliable cases (no ffmpeg, a corrupt or empty video, buckets that cannot be reached, Redis
and the broker down, Turnstile and FCM unset or out of reach, two redemptions of a code at the same instant). The
failures below were reproduced first; each has a test that fails without its fix. 439 tests, all passing on
SQLite and on PostgreSQL (the thread tests and `test_a_real_ffmpeg_run` skip where they cannot run); `manage.py check
--deploy` shows only W005 and W021 (with `LEARN_CODE_SECRET` set).

### Fixed

- **Orders:** the app's checkout accepted the staff-only payment method `offline` and made an order whose payment page
  failed with a server error: checkout takes `razorpay` or `cod` (the service, the serializer and the OpenAPI schema).
  A part refund (a goodwill amount, or a refused parcel refunded less its shipping) closed the course of an order with
  a course in it: only a refund in full does (`services.refunded_in_full`). A bundle of courses only was "out of
  stock", would have been charged shipping and left to be packed: it is a course (`Product.digital_only`, also
  `Totals.digital_only` for the pages).
- **Server errors:** `?attr_<text attribute>=%00` crashed on PostgreSQL; Google's three addresses answered 500 on a
  server without its keys (now 404); a member of staff who may only view products (SUPPORT) got a 500 on a product's
  page; a product picture saved while the broker was down ended in a 500 (its AVIF and WebP sizes are now made in the
  request, as emails and SMS are sent); the reminder task's batches had no order (a failure on PostgreSQL).
- **Privacy:** "Delete my account" now deletes the "email me when it is back" requests kept under the address; a student
  under 18 whose parent has not confirmed (`PARENTAL_CONSENT_MODE=verified`) reads the course but saves nothing in it
  (progress, quiz answers, card reviews, codes, settings, devices answer 403; taking a device off is allowed).
- **Shop:** the school quotation form lists books only (a course opens in one account; pupils get book codes); a
  quotation follows a book renamed since the request; the sitemap lists the shop page, the school-orders page, the
  shelves and the collections.
- **Admin:** the dashboard counts the clips that failed to process (`clips_failed`, for `templates/admin/dashboard.html`).
  `import_chapter_insights` says what is wrong when `--root` is (an error message, not a traceback).

### Added

- Tests: `ops/test_no_server_errors.py` (every address of the site and of the API answers an empty request without a
  server error, signed in or not: it finds the Google 500), a book code redeemed by two students, or twice by one, at the
  same instant (PostgreSQL), and the regression tests of the list above, beside the tests they belong to.

## Phase 7: API contract (8 October 2026)

18 tests more (`api/test_headless.py`, `api/test_contract.py`, `shop/test_api_contract.py`). Any frontend (the app, or
a web frontend of its own) can now do through documented JSON what the website's pages do; the server keeps every rule.

- **allauth.headless** at `/_allauth/` (clients `app` and `browser`; the website's pages stay): codes by email or SMS,
  passwords, passkeys, Google, the second step, sign-up, email, phone and password changes; its OpenAPI file at
  `/_allauth/openapi.json`. `POST /api/v1/auth/exchange/` turns an app's session token (`X-Session-Token`) into the JWT
  pair, so API v1 keeps its Bearer tokens; dj-rest-auth's endpoints stay, legacy-compatible. Emails link to the
  website's pages whichever client asked (`HEADLESS_FRONTEND_URLS`).
- **The site's rules hold there too:** every sign-up form is built on `accounts.signup.StudentDetailsForm`
  (`ACCOUNT_SIGNUP_FORM_CLASS`: the student details, the consent record, the STUDENT role, the parent's link, no phone
  at sign-up, Turnstile; after Google too); headless's code request and phone change take the website's forms
  (Turnstile; "wait a minute" rather than a server error); staff without an authenticator app get a JSON 403 from
  `/api/` with a session (it was a redirect) and from the exchange, while `/_allauth/` stays open for the set-up; no
  `/_allauth/` answer is cached.
- **New in API v1:** `me/teacher/`, `me/parent-consent/`, `me/` fields `consent_pending`, `login_phone`,
  `login_phone_verified` and `sms_updates`; `products/<slug>/reviews/` and `products/<slug>/stock-alert/`, `quotes/`
  (Turnstile while it is on), `orders/t/<token>/` (the emails' link, read-only), `config/` (what is switched on) and
  `pages/` (the legal pages).
- **OpenAPI:** operations tagged by area (auth, account, catalogue, record, shop, learn, site; `api/schema.py`) and
  examples on the main requests; `spectacular --validate --fail-on-warn` clean. API.md has the new endpoints and a
  "Frontend integration guide"; DEPLOYMENT.md section 20 the settings. JSON clients send Turnstile's token as
  `turnstile` (the widget's own field still works).
- Open: guest checkout through the API (it keeps no session carts: guests buy on the website); the app's passkey
  association files (`/.well-known/`); a teacher's view of their students.

## Website redesign (8 October 2026): stage 1 done, stage 2 in progress

Work package C of `../docs/examleaf-phase5-plan.md`, from the design canvas (`../docs/design/direction.md`,
`components.md`, `tokens.css`).

- **Stage 1** (commit f8e4e5f): self-hosted subset fonts (Poppins and Hind Siliguri), one stylesheet
  (`static/css/site.css`), the base layout and the public pages.
- **Stage 2** restyles the shop, account and allauth templates, the emails and the staff player. In progress; its first
  part is in commit ba0b9dd.

## Phase 6 E: store flexibility (8 October 2026)

26 tests more, in `shop/`. Work package E of `../docs/examleaf-phase6-plan.md`; its Status section has a line per item.
Our shop grows the ideas of django-oscar and Saleor that matter for a publisher (neither is installed).

- **Catalogue:** a category tree (django-treebeard, drag and drop in the admin), products on several shelves, category
  pages `/shop/category/<slug>/` with their sub-shelves' products, collections in the staff's order
  (`/shop/collection/<slug>/`), the shop page listing both and filtering by `?kind=`; product types with attributes
  (text, number, list, yes/no; values checked by kind) shown under "Details"; related products ("You may also need");
  a renamed product's old address redirects (301, `SlugHistory`); `GET /api/v1/categories/`, `/collections/`, and
  product filters `?category=`, `?collection=`, `?attr_<code>=`.
- **Digital products:** kind "Digital (in the app)", alone or in a bundle with a book: no shipping, stock or cash on
  delivery, one per order, an account needed; paid, it opens the course (`learn.services.grant_for_order`) and an order
  of digital products only is delivered at once; cancelled or refunded in full, it closes it (`revoke_for_order`). No
  "Book" or shipping in its JSON-LD; the form refuses the books' HSN code for it.
- **Offers:** automatic discounts (per cent or rupees; on the cart, products, categories or collections; minimum copies
  or value; dates; limits in all and per customer; combinable or alone) applied after the coupon and shown as their own
  lines everywhere ("savings" in the API). Each order line keeps its share of the discounts (`OrderItem.discount`,
  `OrderDiscount` lines), which invoices and credit notes print; orders made before keep their old split.
- **Staff orders:** "Add order" in the admin for phone and school orders (offers, a staff discount, shipping set by
  hand, a note), Razorpay Payment Links emailed by us and completed once by the `payment_link.paid` webhook (and by the
  clean-up's check of the link), payments received offline recorded with their bank or UPI reference (printed on the
  invoice), internal order notes with history, the order's timeline, and a customer page (orders, addresses, reviews,
  quotations, stock alerts, courses).
- **Admin:** filters and search on every store model, stock alerts listed, bulk "Put on sale", "Take off sale" and
  "Set stock", product and category import and export for ADMIN only (logged), inline attribute values, and the
  dashboard's store section (sales by day, most sold, running out, reviews and quotations waiting).
  django-admin-sortable2 2.3.1 was left out (no Django 6.1 templates): pictures keep position numbers.
- **Roles:** CONTENT_EDITOR the catalogue and the course content; SALES offers, staff orders, offline payments, notes,
  reviews, quotations and stock alerts; SUPPORT course entitlements and book codes (migration 0019 and
  `bootstrap_roles`).
- **Download my data** adds reviews, quotation requests, stock alerts and the course's data.

## Phase 6 D: revision course (8 October 2026)

35 tests more, in `learn/`. Work package D of `../docs/examleaf-phase6-plan.md`; its Status section has a line per item.
A new app, `learn`, for the mobile app's short-video revision (the app itself is a separate project).

- **Content:** chapters (subject, number, Board marks, previous-year questions, must-do note), one revision per
  chapter (target 10 to 15 minutes, draft or published, order), clips (order, kind: concept, trick, shortcut, formula,
  pattern, mistake, previous-year question; the video; notes in Markdown; free preview; linked questions; tags), flash
  cards and one-mark quiz items (multiple choice, true or false, fill in the blank). Admin: clips inline on the
  revision with their processing status and a Preview link, Move up / Move down, publish and back to draft, "Process
  the video again". django-admin-sortable2 2.3.1 was left out: it has no Django 6.1 templates or actions script.
- **Video:** ffmpeg (Dockerfile) on a `media` queue (docker-compose.yml `media-worker`, one at a time) makes each
  upload into HLS for low-end phones: 480×854 at about 700 kbps and 720×1280 at about 1.5 Mbps, AAC 64 kbps, 4-second
  segments, a poster at 1 s; a bad file fails with the end of ffmpeg's messages, storage trouble is tried 3 times;
  `manage.py reprocess_clips`. Files in the private storage behind links signed for 10 minutes (`/learn/hls/…`,
  segments redirected to the bucket), or the public bucket with `LEARN_PUBLIC_VIDEO=1`; uploads up to
  `LEARN_MAX_UPLOAD_MB`.
- **Data:** `manage.py import_chapter_insights` (marks per chapter from `format.json`, question counts from `pyq/`;
  51 chapters, 70/70/80/70 marks) and `manage.py build_quiz_items` (664 quiz items from the one-mark questions whose
  options and answer parse unambiguously; the rest counted and skipped).
- **Access:** entitlements per subject or all (book code, purchase, staff grant; a code or a purchase lasts a year);
  book codes of 12 characters without 0/O/1/I, kept as a keyed hash (`LEARN_CODE_SECRET`), redeemed once, 5 tries an
  hour per user and per address, logged; `manage.py make_book_codes` writes the printer's CSV;
  `learn.services.grant_for_order` and `revoke_for_order` for the shop's digital products. Free: the first clip of every
  revision and the first chapter's flash cards (`LEARN_FREE_PREVIEW`).
- **Pass plan:** chapters by Board marks × past-paper questions × (1 + share of wrong quiz answers), unwatched clips
  packed into the student's minutes a day until the exam, the minimum to pass (most marks per minute up to 1.5 times
  the pass marks); revise-again with wrong answers back after 1, 3 and 7 days.
- **API** (`api/learn.py`, API.md "Revision course"): chapters, clips with signed links and progress, quiz checked on
  the server, flash cards, plan, revise-again, redeem, entitlements, settings, devices. Throttles `learn_redeem`,
  `learn_redeem_address` (5 an hour), `learn_quiz` (600 an hour).
- **Reminders:** a daily push (18:00) through Firebase Cloud Messaging with firebase-admin 7.7.0, to students who turn
  it on, only with `FCM_SERVICE_ACCOUNT_JSON`; addressed to the app's Firebase installation ID.
- **Privacy:** progress, quiz answers, card reviews, settings, entitlements and devices are deleted with the account
  (receiver on the deletion request); `learn.services.export_learning` for Download my data. No video analytics.
- **Staff player:** `/learn/preview/<clip>/` with hls.js 1.7.3 served by the site (`static/learn/`, its licence beside
  it); CSP `media-src 'self' blob:` and, with buckets, the bucket hosts.

## Phase 5 B: storage, media, shop and web platform (8 October 2026)

21 tests more. Work package B of `../docs/examleaf-phase5-plan.md`; its Status section has a line per item.

- **Two buckets** (Cloudflare R2; DEPLOYMENT.md sections 15 and 17): a private one for invoices, credit notes,
  quotations and answer sheets, reached by links signed for 5 minutes, and a public one for product pictures on
  `PUBLIC_MEDIA_DOMAIN`, cached a year as immutable; keys `S3_*` of their own (`PUBLIC_S3_*` for a private bucket on
  AWS S3 Mumbai); the boto3 checksum variables R2 needs; the CSP allows the media domain. Without buckets (development,
  tests, one server) both stay in `media/`, and `/shop/media/` serves only the public folders.
- **Pictures:** covers and product pictures get AVIF and WebP sizes on the worker (django-pictures 1.8.0, covers
  cropped 2:3) and pages use `<picture>`; their widths and heights are stored, so no page opens the files. The four
  static covers have committed AVIF and WebP copies at 320 and 480 px (`manage.py build_covers`).
- **Search engines and link previews:** canonical link and Open Graph tags on every page (`templates/_head_meta.html`,
  included by base.html), a default preview picture and one per product (cover and title, made on save by the worker),
  JSON-LD for products (Product and Book: price, stock, ISBN/GTIN, shipping, returns; the rating only from approved
  reviews), breadcrumbs and the publisher. No FAQ markup (retired by Google).
- **Web app:** manifest, maskable icons drawn with Pillow, a service worker that keeps only the static files and a
  standalone offline page (never a page, so nothing of an account outlives a log-out), registered from the new
  `static/js/site.js` (`templates/_body_end.html`); CSP `manifest-src` and `worker-src 'self'`.
- **PIN codes:** `manage.py import_pincodes <csv>` loads India Post's directory (data.gov.in); the address forms fill in
  the district and state, and the website, the checkout and the API refuse a state that does not match the PIN code.
- **Shipping:** a courier list on shipments; the tracking link is filled in when staff leave it empty (Delhivery, Blue
  Dart, Ekart, 17TRACK for India Post and the rest).
- **Reviews** from buyers whose order was delivered, one per book, approved in the admin, shown as "Verified buyer";
  honeypot and rate limit; deleted with the account.
- **School and bulk orders:** a public form (`/shop/school-orders/`, GSTIN checked with python-stdnum, Turnstile when
  on), staff emailed, a quotation PDF valid 15 days from the admin, kept in the private bucket. The coupon form takes
  Turnstile too.
- **Stock:** "Email me when it is back" on products out of stock (one email, hourly check), a daily email of the books
  running low to the SALES role (`SHOP_LOW_STOCK`).
- **GST:** `manage.py export_gstr1 --from --to` writes the B2C, HSN summary and credit-note CSVs for the accountant.
- **Order SMS** go out from the shop's notifications through `ops.sms.send_order_sms` (phase 5 A).
- **Supply chain:** Dependabot (pip and GitHub Actions, weekly); DEPLOYMENT.md notes Jazzband's wind-down.
- Upgrading: `MEDIA_ENDPOINT_URL` is gone (`S3_ENDPOINT_URL`), and `MEDIA_BUCKET` now needs `PUBLIC_MEDIA_BUCKET` and
  `PUBLIC_MEDIA_DOMAIN`; product picture URLs change with the buckets (API.md). The first migration records the size of
  every product picture and queues its AVIF and WebP sizes for the worker: until the worker has made them (seconds), a
  product page may show no cover. Beat gets two new schedules (stock alerts hourly, the low-stock email daily). SALES
  got its permissions for reviews, quotations and stock alerts in Phase 6 E (`accounts/roles.py`).

## Phase 5 A: sign-in and communications (8 October 2026)

32 tests more. Work package A of `../docs/examleaf-phase5-plan.md`; its Status section has a line per item.

- **Phone log-in.** A student adds a mobile number on My account (never at sign-up) and confirms it with an SMS code;
  then it logs in with the password or a code by SMS ("Log in with a code", email or number). Numbers are taken as
  people type them ("98640 12345") and kept as +91…; one account per number. Every code, emailed or texted, is now 6
  digits (was `ABCD-EFGH`). Failed password log-ins by phone are limited per number (allauth keyed them all on one
  empty key). An empty "send me a code" form and a second code to the same number within a minute no longer end in a
  server error. Phone log-in exists only where SMS are sent (`SMS_BACKEND=msg91`, or development).
- **Passkeys** for everyone (My account → Passkeys, "Use a passkey" on the log-in page; Passwordless ticked by
  default), one relying party for the host of `SITE_URL`; staff may use a passkey instead of the authenticator app.
- **Google sign-in** when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set: a new student fills in the student
  details after Google (one form mixin with the sign-up form); PKCE; `form-action` allows Google only then.
- **App API:** `POST auth/phone/code/` and `auth/phone/confirm/` (API.md): log-in by SMS code, the same JWT pair.
- **SMS gateway** (`ops/sms.py`): one Celery task, `console` or `msg91` (OTP and Flow APIs), retries on network
  errors, an SMS log without whole numbers (Admin → Ops), at most `SMS_DAILY_CAP` a day counted in the
  database. Order SMS (placed, shipped, delivered) for students who ask for them on My account, through
  `ops.sms.send_order_sms(order, kind)`.
- **Parental consent by SMS** (`verified` mode): a parent's Indian mobile number gets the link by SMS; links are now
  short (`/c/<token>/`, email too: links sent before this release stop working) and record how they were confirmed.
- **Email:** Amazon SES as the documented production backend, bounce and complaint webhooks (`/anymail/…`, only with
  `ANYMAIL_WEBHOOK_SECRET`), an email suppression list that stops sends to bad addresses (staff delete a row to send
  again).
- **Cloudflare Turnstile** on sign-up and code requests when its keys are set (fails open, logged).
- Data export and account deletion include the new data (log-in number, passkeys, Google accounts); Sentry filters SMS
  variables; DEPLOYMENT.md sections 13, 15 and 16, RUNBOOK.md "SMS", "Phone numbers and passkeys", "Email bounces and
  complaints".
- Upgrading: `migrate` adds the SMS log, the email suppression list and the Google tables; `bootstrap_roles` gives SUPPORT
  the right to view the SMS log and to delete suppressions (both run on every deploy).

## Phase 4 security, shop (8 October 2026)

16 tests more, in `shop/test_security.py`. The shop's findings of SECURITY_REVIEW.md; each finding there has its status line.

- **Order links (M2).** Each order has an unguessable token, and every email about it links to `/orders/t/<token>/`:
  the order read only, its invoice and credit notes, and a cancel button while it is pending or paid. "Find your
  order" (website and API) no longer opens the order: for a guest order it emails that link to the order's address,
  and it answers "If an order matches, we have emailed you a link." either way. 10 lookups an hour per client address,
  per email address and per order number; refused while they cannot be counted. API: `POST orders/lookup/` no longer
  returns the order.
- **Test and live mode (M3).** Payments and orders record the mode of their Razorpay keys. Payments, webhooks and
  refunds of the other mode change nothing; invoice and credit-note series follow the order's mode; once live, test
  orders are marked TEST and cannot be packed or shipped. One webhook secret per mode (`RAZORPAY_WEBHOOK_SECRET_TEST`,
  `RAZORPAY_WEBHOOK_SECRET`). `SHOP_OPEN=0` leaves buying to staff during Razorpay's review ("Shop opens soon").
- **Webhook data (M6).** Only the payment's id, order, status, method, amount, currency, error and time are kept (the
  stored payloads are stripped by a migration), not shown in the admin, and cleared after 180 days.
- **Cash on delivery (M8).** Only for accounts with a confirmed email address, orders up to `SHOP_COD_MAX_VALUE`
  (₹1,500) and two on their way per account. Checkout and place order: 10 per 10 minutes per client address.
- **Retention (M10).** Orders never paid or placed lose the customer's details 30 days after they were cancelled; the
  yearly purge of invoiced orders past eight years is in RUNBOOK.md.
- **Refunds (L1, L3).** A retried refund first looks for the one Razorpay already made; a second payment captured for
  a paid order is recorded and refunded by itself, and a cancellation still refunds the first one.
- **Coupons (L4).** One answer for every code that cannot be used; 10 tries an hour per client address (website) and
  per user (API, `API_THROTTLE_COUPON`).
- **Redis (L8).** The cache has a Redis of its own (`redis-cache`: 256 MB, least used keys evicted); the queue's never
  evicts. The shop's limits refuse while the cache cannot be read; Razorpay's webhooks go on.
- **Hardening (I4, I6, M5).** Products and addresses sort only by the fields named; invoice PDFs fetch only static files
  and data: URLs; the orders export needs `export_order` (ADMIN) and is logged.
- Migrations `shop` 0005 to 0008.

## Phase 4 security, accounts, API and operations (8 October 2026)

23 tests more, 227 in all. The security review's other findings (SECURITY_REVIEW.md, each with its status line), one
test or more each in `accounts/test_security.py`, `api/test_security.py` and `ops/test_security.py`.

### Staff and roles

- **Two-factor authentication for staff** (H2): `allauth.mfa`, an authenticator app with ten recovery codes; staff
  without one are sent to set it up before anything else opens; the admin's log-in is allauth's (its per-account limit,
  the code); staff sessions end 8 hours after the log-in. RUNBOOK.md "Staff accounts".
- **ADMIN can no longer** edit periodic tasks, task results, groups, permissions or second factors, nor make anyone
  superuser or change a superuser; only superusers give roles (I7).
- **Admin exports** need an `export_…` permission (ADMIN only), leave out dates of birth and parents' contacts, are
  written to the admin log, and escape a leading `=` (M5, L7).

### Log-ins, passwords and the API

- The API's log-in counts failures per account like the website (5 in 5 minutes); allauth now sees the client's address
  behind Caddy instead of Caddy's (M7).
- Password reset emails: 5 a minute per address, API and website together (L5); five wrong passwords in an hour on the
  API's password checks revoke the user's refresh tokens and answer 429 (L6).
- Passwords: 10 characters at least, none found in data breaches (Pwned Passwords); reset links last an hour (L11).
- At most 20 new attempts of a paper a day; notes 2,000 characters (L12). Boards and subjects sort by id and name only
  (I4); the public API's cache keys ignore unknown query parameters (L8).
- `JWT_SIGNING_KEY`: the app's tokens can have their own key (I5).

### Operations and privacy

- `/health/` and `/health/web/` answer only the uptime monitor (Caddy, `X-Health-Token`) and keep their results 20 s;
  `/api/v1/health/` is gone (H1).
- Sentry gets no stack-frame variables and no email text (M4).
- Verifiable parental consent behind `PARENTAL_CONSENT_MODE=verified`: a link emailed to the parent, the account
  read-only until they agree, how and when recorded (M9); to switch before May 2027 (DEPLOYMENT.md section 14).
- Expired sessions are deleted daily; uploaded backups can be encrypted with age, with a 30-day bucket rule; the
  privacy draft says how logs are really kept (M10).
- The site refuses to start with development settings on a server (I1); a Permissions-Policy header (I6); QR images
  only for published papers, cached a day (I3).
- CI: read-only permissions, a pip-audit job (not blocking yet); test and lint tools in `requirements-dev.txt`, not in
  the image (L10).

## Phase 4: QA pass (8 October 2026)

60 tests more, 188 in all. Every flow of the site was walked on a development server (visitor, cart, log-in, both
checkouts, cancellation, guest lookup, registration under 18, data export, deletion, teacher access, every admin page,
every API endpoint and error), the failures below were reproduced first, and each fix has a test that fails without it.

### Fixed: money and orders

- **Coupon limits** ("one per customer", "at most N uses") were checked only when an order was made, so several open
  orders could each take the last use. They are checked again, under a lock on the coupon, when an order is paid or
  placed (`services.claim_coupon`): the first wins; a cash-on-delivery order that loses goes back to the cart with a
  message, an online payment that loses is refunded and the customer told why. The payment page and the API stop
  before taking money for a coupon that is gone.
- **A payment Razorpay took but the site never heard about** (the customer never came back and the webhook was lost) was
  left charged without an order when the order expired after two days. Before cancelling, the daily clean-up now asks
  Razorpay (`payments.reconcile`); a Razorpay that cannot be asked leaves the order for the next run;
  `manage.py reconcile_payments` does the same by hand.
- The clean-up could cancel an order that was paid in the same moment: the order is checked again under its lock.
- After a payment that could not be used (books sold out, coupon gone) the thank-you page said "placed" and emptied the
  cart; it now says the order could not be completed and is being refunded, and the cart is kept (website and API).
- Refunds made in the Razorpay dashboard were ignored; they are recorded from their webhook (the order, the customer's
  email and the credit note follow).
- Cash-on-delivery review pages that nobody finished stayed pending for ever; they are cancelled after two days, like
  online orders.
- Invoices: no invoice of the real series is numbered while a `SELLER_*` setting still holds a `[placeholder]` (the numbers
  cannot be reissued); the "Amount" column is what is payable after the discount; "MRP-inclusive" became "prices include
  tax"; the Docker image carries Noto fonts, so a name or address in Assamese prints (it would have been empty boxes).
- The admin's revenue is net of refunds (a refused parcel refunded less the shipping brought in nothing).
- Admin: saving a product page that was opened before a sale put the old copy count back; pictures over 2 MB are
  refused with a reason.

### Fixed: availability

- **Redis down: nobody could log in, register or reset a password** (allauth's rate-limit lock treated django-redis's
  fail-soft `add` as "locked" and answered 429; the old test only opened pages). `examleaf.cache.SoftRedisCache`
  fixes it.
- A broker that accepts connections and never answers hung the request for ever; Celery now gives up after about 4
  seconds and the email is sent from the web process. If the email provider is down as well, the failure is logged and
  the page goes on (it was a 500). The old test of the broker fallback never reached the broker: fixed (`broker` fixture).
- `/health/` held a gunicorn worker for 3 seconds on every call (the Celery ping waited out its timeout): `limit=1`.
- A `%00` in an address gave a 500 on PostgreSQL (`/s/AB%00C/` among them): 404.
- Double clicks ended in a 500 for the second request: "Add to cart" (a unique row made twice), "Delete my account" and
  "Ask for teacher access" (one waiting request or profile per user).

### Fixed: privacy

- A sign-up with an address that already has an account answered faster than one with a new address (no password
  hashing): the same work is done, so the timing does not tell.
- Account deletion left the user's email in the admin history of their attempts and the name and PIN code in that of
  their addresses.
- Download my data now also holds the roles, the cart, each order's payments and status timeline.
- The delete page says that orders and invoices stay (tax law); the notes of an attempt are limited to 2000 characters.
- Pages seen by a signed-in user were kept by the browser: after Log out on a shared computer (a cyber café) the Back
  button showed the account, record and orders; they now carry `Cache-Control: no-store`.

### Fixed: front end and copy

- The header is one row at every width: on a phone the name, the cart and a Menu button (CSS only, a hidden checkbox:
  no JavaScript, the CSP is unchanged), instead of three lines; keyboard operable.
- Text colours that missed 4.5:1 (stock, saving, paid-status) darkened; the brand link has an accessible name.
- Every page has its own title and meta description; the private ones are `noindex`; `robots.txt`, a favicon and touch
  icon were added.
- Branded 400, 403, 403 for an expired form, 404, 429 and 500 pages (the 400 and 500 pages need no layout or database;
  the API answers JSON); the 429 of the guests' order lookup was plain text.
- "Log in" and "Register" everywhere (allauth said Sign In and Sign Up), emails greet from ExamLeaf instead of the
  host name, the words about registering follow `SOLUTIONS_REQUIRE_LOGIN`, the About page names the publisher and
  points to Contact, dispatch and delivery times are no longer promised outside the Shipping Policy (product page,
  emails), the empty home page no longer says `manage.py import_papers`.
- `[placeholders]` in the legal pages are marked yellow on the site, counted in the Pages list and on the admin index.

### Added

- Tests: error pages and metadata (`ops/test_errors.py`), the admin crawl (`ops/test_admin_pages.py`, every list, add,
  change, history and delete page), Redis half-open (`ops/test_resilience.py`), copy (`ops/test_copy.py`), orders and
  coupons at the same instant, stuck payments and the admin (`shop/test_robustness.py`: four of them run threads against
  PostgreSQL and are skipped on SQLite), export and sign-up (`accounts/test_export_and_signup.py`).
- Docs: environment variable reference in DEPLOYMENT.md, the shop in RUNBOOK.md (a stuck payment, refund disputes,
  reconciling settlements, a missing invoice, coupons and stock), API.md matched to the routes, this file.

## Phase 3b: shop on the API, credit notes, privacy of the shop (8 October 2026)

Shop REST endpoints (products, cart, addresses, orders, payment through Razorpay's mobile SDK, cancellation, invoice
and credit note PDFs, guests' lookup); credit notes (own number series, GST reversed per line); orders in Download my
data; Sentry scrubbing of secrets and personal data; the `SOLUTIONS_REQUIRE_LOGIN` switch (open or registered
solutions); webhook replay protection; a readiness check before gunicorn starts; the CI builds the Docker image; tests
isolated so that they pass in any order on SQLite and PostgreSQL. 128 tests.

## Phase 3: REST API v1 (8 October 2026)

DRF with dj-rest-auth and JWT (short access token, rotated and blacklisted refresh token, ended by a password change),
sign-up and the email code on the website's own form and rules, drf-spectacular schema with Swagger UI and Redoc served
by the site, CORS for listed origins on `/api/` only, throttles counted in the cache, API.md.

## Phase 2: the shop (8 October 2026)

Catalogue and product pages; the cart (a guest's joins the account's at log-in); checkout with Indian address checks
and saved addresses; Razorpay payments and signed webhooks; cash on delivery; the order and payment state machines
with a customer timeline; stock under row locks; coupons; shipping rates by state; shipments with tracking; refunds
(also partial); GST invoices as PDFs (bill of supply while every book is exempt); order management in the admin (pack,
ship, deliver, cancel, refund, export); Refund and Shipping policy pages; SALES and SUPPORT roles.

## Phase 1: production (8 October 2026)

PostgreSQL, Redis cache and Celery with beat; Sentry and JSON logs with request IDs; roles and permissions; teacher
access requests and their verification; DPDP self-service (Download my data, Delete my account with seven days to
change one's mind, consent records); legal pages with history; the branded admin with its dashboard; the Docker and
Caddy stack; backups; CI; DEPLOYMENT.md and RUNBOOK.md.

## Phase 0: the site (8 October 2026)

Books, papers, questions and solutions imported from the Markdown of the four subjects (30 papers each); the QR code
of every paper opening its solutions; registration with parental consent under 18 and an emailed code; My record of
attempts; a Markdown renderer that keeps the maths for KaTeX and escapes everything else; a strict Content-Security-
Policy; private caching of the gated pages; failed log-ins only in the lock-out records. A first QA pass fixed an XSS in
the renderer and the consent logic. 33 tests.
