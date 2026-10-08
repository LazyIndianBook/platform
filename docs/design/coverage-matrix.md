# ExamLeaf website: coverage matrix

Audit of every route of the Django site (`examleaf-web/`) against the journeys it serves, the screens' states and the redesign vocabulary of `direction.md` section 3. Written by the UX audit of 8 October 2026, 12:54 IST; the other deliverables are `baseline.md` and `screenshots/`.

**Django pages removed on 2026-10-08.** The Next.js frontend (`examleaf-frontend/`) now serves every page route below at the same address (`parity-nextjs.md`), and Caddy sends it every path but Django's own. Django's page views, templates, page-only forms, its CSS, scripts, KaTeX and web-app files are gone, allauth runs headless only, and Django keeps the API, allauth.headless, the admin and its staff player, the webhooks, media, the QR PNGs, health and Google's callback. This matrix describes the site as audited before that; its routes, templates and counts are history.

**Snapshot.** The audit began on commit `4e30e59` with 52 changed paths; at 11:45 IST another agent committed that work as `ba0b9dd`; the tree has 138 changed paths now. Other agents kept editing the templates, the API (a new headless-auth API, new endpoints for the app), the stylesheet (split into `site.css` and per-section files) and a migration throughout, so this is a snapshot, not a fixed point: routes that appeared during the audit are marked "in progress" and the numbers are from the tree as it stood when the audit ended. The scripts in section 6 re-measure everything; re-run them rather than trusting figures that are more than an hour old.

## 0. Summary

| What | Count |
|---|---|
| URL patterns in the resolver | 634 |
| Site routes (everything except the admin, the API and the debug toolbar) | 103: anonymous 53, signed-in student 39, machine 10, staff 1 |
| Django admin | 383 patterns for 58 models in 17 apps (section 3.2) |
| REST API v1 | 70 paths, 90 operations, plus the schema, Swagger and Redoc pages (section 3.3) |
| allauth headless API (for the app and for a browser client) | 67 patterns, 33 operations once the app and browser variants are merged (section 3.4) |
| Debug toolbar (development only) | 7 |
| HTML page routes (the site's pages, not files or JSON) | 68: done 34, done through allauth's element overrides 12, partial 3, layout only 13, not restyled 2, not rendered by the probe 4 |
| Templates | 87 `.html` files: 38 page templates, 15 partials, 12 allauth element overrides, 9 email and PDF templates, 7 error and offline pages. None still uses a pre-redesign class name except `coupon` in `shop/cart.html` |
| Journeys | 4 (J1 to J4) with 10 + 6 + 5 + 6 steps; 25 gaps in section 2 |

**Redesign column.** *done*: the page's own content uses the component vocabulary (three or more of `.btn .field .card .badge .alert .table-wrap .timeline ...`, or two on a short page) and no pre-redesign class. *done through allauth elements*: a library page whose controls come out as `.btn`, `.field`, `.card` through `templates/allauth/elements/`, with the library's copy. *partial*: one vocabulary class only, a pre-redesign class name left, or a form printed with a raw `{{ form }}` (the CSS styles bare controls, so it looks right but has no field error markup). *layout only*: the new header, footer and card around the library's plain content. *not restyled*: untouched by the vocabulary (the Django admin keeps its own theme; the health page is the library's). Judged on the HTML each route returns (a Django test client with a student, a guest and each staff role), not on the template source alone; the static scan of `templates/` agrees (section 6).

**States column.** D default · L loading (busy button, skeleton, spinner) · E empty (nothing yet, nothing found) · V validation or error feedback · P permission denied (redirect to log in, 403, or the 404 given for other people's objects) · S expired session, link or token · U unavailable (shop closed, out of stock, payment service down, rate limit, offline). `!X`: a state the page needs and does not have. For API rows: D 200 or 201, E an empty page of results, V 400, P 401 or 403, S an expired access token (15 minutes, then refresh), U 429 or 503.

**Journey column.** J1 discover, buy, access, revise · J2 sign-in and recovery · J3 account and data rights · J4 staff operations · system.

**Status column.** *existing* works as built; *incomplete* is built in part (what is missing is said); *in progress* is in the working tree and not in the last commit; *proposed* is in section 4 only.

## 1. Journeys


### J1. Discover, buy, access, revise (a student, or a parent buying for one)

| # | Step | Routes crossed | Gap |
|---|---|---|---|
| 1 | Arrive from a search, a shared link, or by scanning the QR code in a printed paper | `/`, `/shop/<slug>/`, `/s/<code>/` | |
| 2 | Pick a subject and see what a book holds | `/` (tiles) → `/books/<slug>/` (30 papers in 3 tiers) | |
| 3 | Try a paper | `/s/<code>/` → logged out: wall (`landing.html`) with Register and Log in, both keeping `?next=` | **G1** every "see a sample" link ends on this wall; **G15** the header's Log in and Register links do not keep the page |
| 4 | Choose books | `/shop/` (tabs, featured bundle) → `/shop/<slug>/` | **G13** `?kind=` has no control; **G22** shelves and collections exist but no data and no door from the home page |
| 5 | Add to the cart | POST `/cart/add/<id>/` → `/cart/` (copies, remove dialog, coupon) | **G9** no busy state on the form posts |
| 6 | Check out (guest with an email, or logged in; a minor whose parent has not confirmed is sent to My account) | `/checkout/` → `/checkout/<n>/pay/` (Razorpay Checkout or Place order) → POST `/checkout/<n>/paid/` → `/checkout/<n>/done/` | **G12** PIN autofill is silent when the directory is empty; **G17** the consent redirect does not return the student to checkout |
| 7 | After the order: status, tracking, invoice, cancel | email link `/orders/t/<token>/`; or `/account/orders/<n>/`; lost link `/orders/lookup/` | **G16** a guest order is not attached to an account made later with the same email; **G19** a wrong or old token gets the generic 404; **G20** nothing on the done page or the order page leads to the papers or explains the QR code |
| 8 | Open the solutions and mark the paper | `/s/<code>/` (signed in) → POST `/account/record/add/<code>/` | **G11** a valid save leaves the paper for `/account/record/`; an invalid one for a separate page; **G17** a minor with consent pending sees a form that cannot save |
| 9 | Follow progress | `/account/record/` (tier averages, filters) → `/account/record/<id>/edit/` | **G10** a filter that matches nothing says "Nothing recorded yet" |
| 10 | Revise | The revision course (clips, quiz, flash cards, pass plan, book codes) lives in the app: `/api/v1/learn/*`; the website has the staff preview and one account row | **G6** the account row names the app but gives no link, store badge or QR; the website has no student surface for the course (see section 4) |

### J2. Sign in and recover

| # | Step | Routes crossed | Gap |
|---|---|---|---|
| 1 | Register: name, email, password, class, board, district, date of birth, the parent's details under 18, consent | `/account/signup/` → `/account/confirm-email/` (six-box code) → `next` or `/` | `next` survives both steps (checked: QR landing → Register → code → the same paper) |
| 2 | Log in: SMS code, email code, Google (when keys are set), passkey, or password in a fold | `/account/login/` → `/account/login/code/confirm/` ; `/account/google/login/`; `/account/2fa/webauthn/login/` | **G24** the first field is a mobile number, usable only after one was confirmed on My account |
| 3 | Staff second step | `/account/2fa/authenticate/` (first time: `/account/2fa/totp/activate/`) → `/admin/` | |
| 4 | Forgot the password | `/account/password/reset/` → `/account/password/reset/done/` → email → `/account/password/reset/key/<uid>-<key>/` → `/account/password/reset/key/done/` | **G2** the last page has no Log in button; **G18** after a reset the visitor is not signed in and the destination is gone; **G23** library copy ("Bad Token", "Change Password") |
| 5 | Add a way back in | My account → `/account/phone/change/` → `/account/phone/verify/`; `/account/2fa/webauthn/add/`; `/account/email/`; `/account/password/change/` | |
| 6 | An account is switched off | `/account/inactive/` | **G4** one line, no way to ask for help |

### J3. Account and data rights

| # | Step | Routes crossed | Gap |
|---|---|---|---|
| 1 | The hub | `/account/` (record, orders, details, addresses, mobile and passkeys, consent, data) | |
| 2 | A parent confirms a minor's account | link `/c/<token>/` (7 days); the student resends from `/account/` via POST `/account/parent-consent/` | **G5** an expired link tells the parent to ask the child; no contact link |
| 3 | Download my data | `/account/data/` → (password again) → JSON file | **G21** a raw JSON file, no readable summary |
| 4 | Delete my account | `/account/delete/` → (password again) → 7-day grace → `/account/delete/cancel/` | |
| 5 | Teacher access | `/account/teacher/` → status on `/account/` | **G14** a request only; no teacher features |

### J4. Staff operations

| # | Step | Routes crossed | Gap |
|---|---|---|---|
| 1 | Sign in with a second factor | `/admin/login/` → `/account/login/?next=/admin/` → `/account/2fa/authenticate/` | |
| 2 | The day's queue | `/admin/` (today and 30-day figures; orders to pack, on the way, reviews and quotations waiting) | **G3** two layouts: the admin, and the public layout for `/learn/preview/` and for the 403 page inside the admin |
| 3 | Orders | `/admin/shop/order/` → actions (pack, ship with courier and tracking, deliver, cancel, refund, payment link, offline payment); Add order for phone and school orders; customer page | |
| 4 | Catalogue and content | products, shelves, collections, offers, coupons, shipping rates; books, papers, questions, solutions; legal pages | |
| 5 | Revision course | chapters, revisions, clips (upload, ffmpeg, preview), flash cards, quiz items, entitlements, book codes | |
| 6 | Support and privacy | users, consent records, deletion requests, teacher verification, SMS log, email suppression | |

## 2. Gaps

Dead ends, missing states and journeys that lose their context, found by reading every template and view, by walking the flows with a test client (the QR landing → Register → emailed code → the same paper keeps its destination; so does a code log-in, a password log-in, and a page that asks for a log-in) and by probing every route as each kind of visitor.

| Id | Kind | Where | What | Suggested fix |
|---|---|---|---|---|
| G1 | dead end | `/s/<code>/` for a logged-out visitor; the home hero (`See a sample paper`, hard-coded to `PHY-M04`), the product page (`See a sample`), every paper link on `/books/<slug>/` | Nothing can be read before registering (`SOLUTIONS_REQUIRE_LOGIN` defaults to 1), and the wall shows no preview of what is behind it. | Open one sample paper per subject, or show a blurred first question and the marking table on the wall. |
| G2 | dead end | `/account/password/reset/key/done/` | Heading reads Change Password, body one line, no Log in button. | Own template with a Log in button that keeps `next`. |
| G3 | inconsistency | `/learn/preview/<clip>/`, the 403 page inside the admin, `/health/` | Staff meet three looks: the themed admin, the public layout, an unbranded library page. | Pick one chrome for staff pages; give the admin a 403 of its own. |
| G4 | dead end | `/account/inactive/` | One line, no contact link. | Say why and link Contact. |
| G5 | dead end | `/c/<token>/` expired (HTTP 400) | The parent is told to ask the child for a new link; no contact route, and the parent may not be able to reach the child. | Add a Contact link and the student's first name. |
| G6 | dead end | `/account/` row Revision course | Names the app and says log in there, with no link, store badge or QR. | Link to the app, show a QR on desktop. |
| G7 | dead end | `/contact/` (and the 403, 404, 500 and consent pages that point to it) | A static page with `[email]` and `[phone]` placeholders until staff fill them; no form. | A contact form (or at least a mailto) and a launch check that fails while placeholders remain (the dashboard already counts them). |
| G8 | missing state | `/books/<slug>/`, `/s/<code>/` | A book with no published paper, or a paper with no questions, renders a page with nothing to say. | An `.empty` block with a way back. |
| G9 | missing state | every form post (Register, Log in, Checkout, Add to cart, Save marks, coupons) | Only the Pay button has a busy state; a slow post (signup sends an email) can be pressed twice. | Set `aria-busy` and disable on submit in `site.js`. |
| G10 | missing state | `/account/record/` with a filter | A filter that matches nothing shows Nothing recorded yet, which is untrue. | Tell No papers match these filters, with a Clear link. |
| G11 | context loss | `/account/record/add/<code>/` | A valid save sends the student to My record, away from the solutions they were reading; an invalid one to a separate page. | Post back to the paper (`#record`), or save with fetch and keep the page. |
| G12 | missing state | checkout and address forms | The PIN autofill (`/shop/pin/<pin>/`) answers 404 when the directory is empty (it is, in the development database, until `import_pincodes` runs), and the form gives no sign. | Hide the hint, or say when a PIN is not found; load the directory at deploy. |
| G13 | incomplete | `/shop/?kind=` | The parameter filters, but no control sets it. | Add the kind tabs or drop the parameter. |
| G14 | incomplete | `/account/teacher/` | A request form only; `TeacherProfile` has no students (TODO in `api/views.py`). | Define the link before building the screens. |
| G15 | context loss | header Log in and Register (`base.html`) | No `next`: logging in from `/books/...` or `/shop/...` lands on `/` (`LOGIN_REDIRECT_URL`). The QR wall, the cart and checkout do keep it. | Add `?next={{ request.path }}` to both links. |
| G16 | context loss | `/account/orders/` after a guest purchase | Only orders placed while logged in are listed; a student who bought as a guest and registers later with the same email does not see it. | Claim guest orders by verified email at first log-in. |
| G17 | context loss | `/checkout/` for a minor with consent pending (`PARENTAL_CONSENT_MODE=verified`) | Redirected to `/account/` with a toast; once the parent confirms, nothing brings the student back. The solutions page shows a save form that always fails for them. | Disable the form with the reason; offer Back to checkout when consent arrives. |
| G18 | context loss | password reset | After a reset the visitor is not signed in and `next` is gone. | Sign in after reset (allauth setting) or keep `next` in the key page. |
| G19 | dead end | `/orders/t/<token>/` wrong or old | The generic 404; only `/s/...` gets a hint on the 404 page. | A 404 hint for `/orders/t/...`: Find your order. |
| G20 | journey break | `/checkout/<n>/done/` and `/account/orders/<n>/` | Nothing links the buyer to the papers or explains the QR code; the product, the book page and the order are three separate worlds. | A Your papers block on the order: open Paper E-01, how the QR works. |
| G21 | incomplete | `/account/data/` | A raw JSON download with no readable summary or preview. | A page that lists what is kept, then the download. |
| G22 | incomplete | `/shop/category/<slug>/`, `/shop/collection/<slug>/` | Built, but empty in the database and not linked from the home page. | Seed one shelf or hide the entry points until used. |
| G23 | inconsistency | 7 allauth pages that are only the layout (`/account/inactive/`, `.../password/reset/done/`, `.../key/...`, `/account/3rdparty/...`) and 12 more drawn through the element overrides with the library's copy | Library headings and copy: Bad Token, Account Inactive, Login Cancelled (says sign in), Third-Party Login Failure, Confirm Access, Email Address, Security Keys. | Override the templates with the site's words and a next step. |
| G24 | journey friction | `/account/login/` (SMS first) | A first-time visitor sees Mobile number, Text me a code, and the help text The number you confirmed on My account; they have none. | Lead with email unless the browser remembers a confirmed number. |
| G25 | robustness | invoice PDF routes | A missing PDF file (storage unreachable, file deleted) gives a 500, not a 404 (found while probing with another `MEDIA_ROOT`). | Catch the file error in `pdf_response`. |

Checked and found sound, so nobody needs to look again: `?next=` survives the QR wall, sign-up with the emailed code, the code log-in, the password log-in, the cart's and the checkout's Log in links, and the re-entry of the password before data export or deletion; a guest's cart joins the account's at log-in; every order state (pending, placed on delivery, paid, delivered, cancelled) renders on `/account/orders/<n>/`, `/orders/t/<token>/` and `/checkout/<n>/done/`; other people's orders, addresses and attempts answer 404; the 400, 403, 404, 429 and 500 pages are the site's own.

## 3. Coverage matrix

### 3.1 Site routes

Who means who gets a useful answer; where an anonymous visitor is redirected to log in, the row says student. Methods are GET unless the route says POST.

#### A. Discover: pages anyone can read

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/` | Brand landing: what the books are, subject tiles, how QR solutions work, prices from the database, FAQ, final call to action | anonymous, student (same page; the last button switches between Find your order and My orders) | `home.html`, `_tile.html` | D E | J1 discover | existing | done |
| `/books/<slug>/` | One subject: facts, buy buttons, the 30 papers in three tiers (each links to its solutions), register prompt | anonymous, student | `book.html` | D !E | J1 discover, access | existing | done |
| `/s/<code>/` | The address inside the QR code. Signed in: worked solutions, marking steps, the marks form. Logged out: a register or log-in wall that keeps the destination (`?next=`). Wrong case redirects (301) to the canonical code. V: a bad marks form leaves this page for `attempt_form.html` (the form is a raw `{{ form }}`). !L: maths draws after KaTeX loads, with no placeholder. !E: a paper with no questions renders an empty page | anonymous (wall), student (solutions). `SOLUTIONS_REQUIRE_LOGIN=0` opens the solutions to everyone | `landing.html` or `solutions.html`, `_qr_card.html`; KaTeX from jsDelivr | D V P U !L !E | J1 access | existing | done |
| `/qr/<code>.png` | The QR image printed on the paper, for the print side; published papers only, cached a day | anyone | PNG from `Paper.qr_image` | D U | J1 access (print) | existing | n/a |
| `/about/` | Publisher, what the books are, how to use a paper | anonymous, student | `about.html` | D | J1 discover | existing | layout only |
| `/privacy/` `/terms/` `/refunds/` `/shipping/` `/contact/` | Legal and policy pages from the database (`pages.Page`, Markdown, versioned; consent records keep the privacy version) | anonymous, student | `page.html` | D U | all | existing (copy unfinished: 40 `[placeholders]` across the five pages, 12 of them in Contact) | layout only |
| `/offline/` | Offline fallback the service worker shows when a page cannot be fetched | anyone with the worker installed | `offline.html` (self-contained) | U | system | existing | done |

#### B. Buy: shop, cart, checkout

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/shop/` (`?kind=`) | Catalogue: subject tabs (CSS only), featured bundle, product cards, shelves and collections links. U: the Shop opens soon alert while `SHOP_OPEN` is off; the Out of stock badge. `?kind=` has no control in the page | anonymous, student | `shop/catalogue.html`, `_product_card.html`, `_price.html`, `no_cover.html` | D E U | J1 buy | existing | done |
| `/shop/category/<slug>/` | A shelf of the category tree, with its sub-shelves | anonymous, student | `shop/catalogue.html` | D E U | J1 buy | incomplete (no shelves exist; nothing on the home page links to one) | done |
| `/shop/collection/<slug>/` | A hand-picked collection, in staff order | anonymous, student | `shop/catalogue.html` | D E U | J1 buy | incomplete (no collections exist yet) | done |
| `/shop/<slug>/` | Product: cover, price, buy form, bundle contents, what is inside, details, reviews. A renamed slug redirects (301). E: No reviews yet. U: shop closed, only N left, out of stock with Email me when it is back, digital product wording | anonymous, student | `shop/product.html`, `_price.html`, `_product_card.html` | D E V U | J1 buy | existing | done |
| `/shop/<slug>/review/` (POST) | A review from a buyer whose order was delivered; bots caught by a honeypot | student who bought it (rate limited) | none: toast and redirect to `#reviews` | V P U | J1 buy (after) | existing | n/a |
| `/shop/<slug>/stock-alert/` (POST) | Email me once when a product is back | anonymous, student (rate limited) | none: toast and redirect | V U | J1 buy | existing | n/a |
| `/shop/school-orders/` | Quotation request for schools, coaching centres and bookshops | anonymous, student (rate limited, honeypot, Turnstile when keys are set) | `shop/quote_request.html` | D V U !L | J1 buy (bulk) | existing | done |
| `/shop/pin/<pin>/` | JSON for the address form's autofill (district, state of a PIN code) | anonymous (called by `site.js`) | JSON | D U | J1 buy | incomplete (the PIN directory is empty until `manage.py import_pincodes` runs: autofill then does nothing, silently) | n/a |
| `/shop/media/<path>` | Public product pictures when no bucket is configured | anyone | file | D U | system | existing | n/a |
| `/cart/` | Cart: copies, remove with confirm dialog, coupon, summary. Guests keep a cart in the session; it joins the account's at log-in. The empty state is a dashed card under a repeated H1. The one pre-redesign class name left in any page template is `coupon` here (cosmetic), which is why this row reads partial | anonymous, student (staff only while `SHOP_OPEN` is off) | `shop/cart.html`, `_thumb.html` | D E V U !L | J1 buy | existing | partial |
| `/cart/add/<id>/` (POST) | Add copies, then show the cart | anonymous, student | none: redirect to `/cart/` with a toast | V U | J1 buy | existing | n/a |
| `/checkout/` | Address (saved or new), delivery charges, payment method; creates the pending order. Guests give an email; a student whose parent has not consented is sent to My account | anonymous (guest), student | `shop/checkout.html`, `_stepper.html`, `_thumb.html` | D E V P U !L | J1 buy | existing | done |
| `/checkout/<n>/pay/` | Review and pay: Razorpay Checkout in the page, or Place order for cash on delivery. L: the Pay button is busy until Razorpay's script loads and while the payment is checked. U: payment service unavailable, test mode banner, noscript | the order's owner, or the browser session that placed it | `shop/pay.html`, `order_summary.html`; `shop/static/shop/checkout.js` | D L V P S U | J1 buy | existing | done |
| `/checkout/<n>/paid/` (POST) | Razorpay's success handler posts here; the signature is checked | the order's owner or session | none: redirect to done or back to pay | V | J1 buy | existing | n/a |
| `/checkout/<n>/done/` | Thank you, confirming, or could not complete (sold out while paying) | the order's owner or session | `shop/order_detail.html` (thanks) | D P U | J1 buy | existing | done |

#### C. After the order

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/account/orders/` | My orders, newest first | student | `shop/order_list.html` | D E P S | J1 buy (after) | existing (orders placed as a guest are not listed, even with the same email) | done |
| `/account/orders/<n>/` | Status timeline, shipments with tracking, refunds, invoice and credit notes, cancel. L: a skeleton stands in for an invoice still being made | the order's owner, or the session that placed it | `shop/order_detail.html`, `order_summary.html` | D E L P U | J1 buy (after) | existing | done |
| `/account/orders/<n>/cancel/` (POST) | Cancel until it is packed; online payments are refunded | the order's owner or session | none: toast and redirect | V P | J1 buy (after) | existing | n/a |
| `/account/orders/<n>/invoice/` | The GST invoice (PDF download) | the order's owner; staff with `view_invoice` | PDF (WeasyPrint) from `shop/invoice.html` | D U P | J1 buy (after) | existing (404 until the file is made; a missing file gives a 500 instead) | n/a |
| `/account/orders/<n>/credit-notes/<id>/` | A credit note (PDF) for a refund | the order's owner; staff with `view_creditnote` | PDF from `shop/credit_note.html` | D U P | J1 buy (after) | existing | n/a |
| `/orders/lookup/` | Guests ask for the link to their order by its number and email; the answer is the same whether or not an order matched | anonymous, student (rate limited) | `shop/lookup.html` | D V U | J1 buy (after) | existing | done |
| `/orders/t/<token>/` | The order by the secret link in its emails, no account needed | whoever holds the link | `shop/order_detail.html` | D P U | J1 buy (after) | existing (a wrong or old token gets the generic 404, no hint to Find your order) | done |
| `/orders/t/<token>/cancel/` (POST) | Cancel from the emailed link | whoever holds the link | none: toast and redirect | V P | J1 buy (after) | existing | n/a |
| `/orders/t/<token>/invoice/` | Invoice PDF from the emailed link | whoever holds the link | PDF | D U P | J1 buy (after) | existing | n/a |
| `/orders/t/<token>/credit-notes/<id>/` | Credit note PDF from the emailed link | whoever holds the link | PDF | D U P | J1 buy (after) | existing | n/a |
| `/account/addresses/add/` | Add a saved delivery address | student | `shop/address_form.html` | D V P | J3 account, J1 buy | existing | done |
| `/account/addresses/<id>/` | Change a saved address (another user's: 404) | the address's owner | `shop/address_form.html` | D V P | J3 account, J1 buy | existing | done |
| `/account/addresses/<id>/delete/` (POST) | Delete an address (button on My account) | the address's owner | none: redirect to My account | P | J3 account | existing | n/a |

#### D. Record: marks and progress

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/account/record/` | My record: average for each tier, a table of saved papers, filters by subject and tier | student | `record.html` | D E P S !V | J1 access, revise | existing (a filter that matches nothing shows Nothing recorded yet) | done |
| `/account/record/add/<code>/` | Save a score for a paper (the form on the solutions page posts here; errors come back on this separate page) | student; with `PARENTAL_CONSENT_MODE=verified` a minor needs the parent's confirmation; 20 saves a paper a day | `attempt_form.html` (raw `{{ form }}`) | D V P U | J1 access | existing | partial |
| `/account/record/<id>/edit/` | Edit or correct a saved score (own only) | the attempt's owner | `attempt_form.html` | D V P | J1 revise | existing (no delete in the website; the API deletes) | partial |

#### E. Account and data rights

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/account/` | My account: record summary, orders, details and addresses, mobile number and passkeys, consent, data download and deletion. U: banners for a pending deletion and for the parent's consent still waiting | student | `my_account.html` | D E P S U | J3 account | existing | done |
| `/account/teacher/` | Ask for teacher access (school, district, subject); staff verify it | student, once per account | `teacher_request.html` | D V P | J3 account | incomplete (a request only: no teacher features, nothing links a teacher to students; see the TODO in `api/views.py`) | done |
| `/account/data/` | Download my data as one JSON file (DPDP right of access) | student, after re-entering the password | JSON download (`export_user_data`) | D S | J3 data rights | existing (a raw JSON file; no readable summary, no preview) | n/a |
| `/account/delete/` | Delete my account after a 7-day grace period (confirm box; the password again on submit) | student | `account_delete.html` | D V S U | J3 data rights | existing | done |
| `/account/delete/cancel/` (POST) | Keep my account (button on My account while a deletion waits) | student | none: toast and redirect | P | J3 data rights | existing | n/a |
| `/account/parent-consent/` (POST) | Send the parent's confirmation link again, to the same or a corrected contact | student under 18 whose consent is pending (one send per 10 minutes) | none: toast and redirect | V U | J3 data rights | existing | n/a |
| `/account/sms-updates/` (POST) | Order updates by SMS on or off (needs a confirmed mobile number) | student | none: toast and redirect | P | J3 account | existing | n/a |
| `/c/<token>/` | The parent's link (email or SMS): who registered, link to the privacy notice, I agree; valid 7 days | the parent or guardian who holds the link (no account) | `parent_consent.html` | D S | J3 data rights | existing (an expired link tells the parent to ask the child, who may not be reachable; no contact link) | done |

#### F. Sign-in and recovery (allauth, restyled in part)

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/account/login/` | Log in: a code by SMS, a code by email, Google (when its keys are set), a passkey, or email and password in a fold | anonymous (a signed-in user is sent home) | `account/login.html` | D V U | J2 sign-in | existing (SMS first, though a number works only after it was confirmed on My account) | done |
| `/account/signup/` | Register: name, email, password, class, board, district, date of birth, the parent's details under 18, consent; then an emailed code | anonymous | `account/signup.html` | D V U | J2 sign-in | existing | done |
| `/account/logout/` | Log out (the header posts straight to it; GET shows a confirm page) | student | `account/logout.html` | D P | J2 sign-in | existing | done |
| `/account/inactive/` | Shown when an account is switched off | anyone redirected there | allauth default | D | J2 sign-in | existing (one line, no contact link) | layout only |
| `/account/reauthenticate/` | Enter the password again before data export, deletion, email or passkey changes | student | allauth default | D V S | J3 account | existing | done via allauth elements |
| `/account/email/` | Change the email address (the new one takes over once its emailed code is confirmed) | student | allauth default (`account/email_change.html`) | D V P | J3 account | existing | done via allauth elements |
| `/account/confirm-email/` | Type the 6-digit code emailed at sign-up or after an email change | the visitor in the sign-up or email-change stage | `account/base_confirm_code.html` (the site's six-box code page) | D V S U | J2 sign-in | existing | done |
| `/account/password/change/` | Change the password | student | allauth default | D V P | J3 account | existing | done via allauth elements |
| `/account/password/set/` | Set a password for an account made without one (Google); a student with a password is sent to change it | student | allauth default | D V P | J3 account | existing | done via allauth elements |
| `/account/password/reset/` | Ask for a password reset email | anonymous | allauth default (`account/password_reset.html`) | D V U | J2 sign-in | existing | done via allauth elements |
| `/account/password/reset/done/` | We have sent you an email | anonymous | allauth default | D | J2 sign-in | existing (no link onward) | layout only |
| `/account/password/reset/key/<uid>-<key>/` | The emailed link: choose a new password; a used or old link says Bad Token | holder of the emailed link | allauth default | D V S | J2 sign-in | existing | layout only |
| `/account/password/reset/key/done/` | Your password is now changed | anonymous | allauth default (heading reads Change Password) | D | J2 sign-in | existing (no Log in button: a dead end) | layout only |
| `/account/login/code/` | Ask for a log-in code by email (or by SMS to a confirmed number) | anonymous | `account/request_login_code.html` | D V U | J2 sign-in | existing | done |
| `/account/login/code/confirm/` | Type the log-in code (six boxes), resend, change the address | the visitor who asked for a code | `account/confirm_login_code.html`, `base_confirm_code.html` | D V S U | J2 sign-in | existing | done |
| `/account/phone/verify/` | Type the code texted to confirm a mobile number | student adding a number | `account/confirm_phone_verification_code.html` | D V S U | J3 account | existing | done |
| `/account/phone/change/` | Add or change the mobile number used for SMS log-in and order updates | student | `account/phone_change.html` | D V P | J3 account | existing | done |
| `/account/2fa/` | Two-factor overview: authenticator app, security keys, recovery codes | student (staff are forced here until one is set up) | allauth default (`mfa/index.html`) | D P | J2 sign-in, J3 account | existing | done via allauth elements |
| `/account/2fa/authenticate/` | Second step at log-in: authenticator code, recovery code, or passkey | a visitor who passed the first step | `mfa/authenticate.html` | D V S | J2 sign-in | existing | done |
| `/account/2fa/reauthenticate/` | Second step before a sensitive change | student with a second factor | allauth default | D V | J2 sign-in, J3 account | existing | unverified (not rendered by the probe) |
| `/account/2fa/totp/activate/` | Set up an authenticator app (QR code and secret) | student; required of staff before anything else | allauth default | D V | J2 sign-in, J3 account | existing | done via allauth elements |
| `/account/2fa/totp/deactivate/` | Remove the authenticator app | student with one set | allauth default | D P | J2 sign-in, J3 account | existing | done via allauth elements |
| `/account/2fa/recovery-codes/` | See the recovery codes | student with a second factor | allauth default | D E P | J2 sign-in, J3 account | existing | done via allauth elements |
| `/account/2fa/recovery-codes/generate/` | Make new recovery codes | student with a second factor | allauth default | D | J2 sign-in, J3 account | existing | done via allauth elements |
| `/account/2fa/recovery-codes/download/` | Download the recovery codes as a text file | student with a second factor | text file | D | J2 sign-in, J3 account | existing | n/a |
| `/account/2fa/webauthn/` | My passkeys and security keys | student | allauth default | D E P | J2 sign-in, J3 account | existing | done via allauth elements |
| `/account/2fa/webauthn/add/` | Add a passkey (browser prompt) | student | allauth default + JS | D V L | J2 sign-in, J3 account | existing | done via allauth elements |
| `/account/2fa/webauthn/reauthenticate/` | Re-check with a passkey | student | allauth default + JS | D V | J2 sign-in, J3 account | existing | unverified (not rendered by the probe) |
| `/account/2fa/webauthn/keys/<id>/remove/` | Remove a passkey | student | allauth default | D P | J2 sign-in, J3 account | existing | unverified (not rendered by the probe) |
| `/account/2fa/webauthn/keys/<id>/edit/` | Rename a passkey | student | allauth default | D V P | J2 sign-in, J3 account | existing | unverified (not rendered by the probe) |
| `/account/2fa/webauthn/login/` | Log in with a passkey (the login page's button posts here) | anonymous | allauth view, no page | D V | J2 sign-in | existing | n/a |
| `/account/3rdparty/login/cancelled/` | You cancelled the Google log-in | anonymous | allauth default | D | J2 sign-in | existing (copy says sign in) | layout only |
| `/account/3rdparty/login/error/` | The Google log-in failed | anonymous | allauth default | D U | J2 sign-in | existing | layout only |
| `/account/3rdparty/signup/` | After Google, a new student fills the Register details (no password) | a visitor returning from Google | `socialaccount/signup.html` (extends `account/signup.html`) | D V | J2 sign-in | existing (only with Google keys) | done |
| `/account/3rdparty/` | Connect or disconnect Google | student | allauth default | D E P | J3 account | existing (only useful with Google keys) | layout only |
| `/account/google/login/` (+ `callback/`, `token/`) | Start Google sign-in, its callback, and token sign-in for the app | anonymous | allauth view | D U | J2 sign-in | existing (404 until `GOOGLE_CLIENT_ID` and `_SECRET` are set) | n/a |
| `/account/register/` and `/account/social/...` (5 routes) | Redirects to `/account/signup/` (query kept) and to the `/account/3rdparty/...` pages | anyone | `RedirectView` | n/a | J2 sign-in | existing | n/a |

#### G. Staff

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/learn/preview/<clip>/` | The staff player for a revision clip (hls.js) with processing status and notes | staff with `learn.view_clip` (CONTENT_EDITOR, ADMIN) | `learn/preview.html` (on the public layout, not the admin's) | D L E V P S U | J4 staff | existing | done |
| `/admin/...` | Django admin, themed (`admin_interface`): 58 models in 17 apps, 382 URL patterns; see section 3.2 | staff by role (ADMIN, CONTENT_EDITOR, SALES, SUPPORT); an authenticator app or passkey is required first (`StaffMFAMiddleware`) | admin templates; `admin/dashboard.html`, `shop/admin/*.html` | D E V P S U | J4 staff | existing | not restyled |

#### H. System and machine endpoints

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/robots.txt` | Keeps crawlers out of account, cart, checkout, admin and API | crawlers | `robots.txt` | D | system | existing | n/a |
| `/sitemap.xml` | Pages, books and products for search engines | crawlers | Django sitemaps | D | system | existing | n/a |
| `/manifest.webmanifest` | The web app manifest (name, colours, icons) so a phone can add the site to the home screen | browsers | JSON | D | system | existing | n/a |
| `/sw.js` | Service worker: the offline page and this release's static files; never a page | browsers | `sw.js` | D | system | existing | n/a |
| `/favicon.ico` | Redirect to the PNG favicon | browsers | redirect | D | system | existing | n/a |
| `/health/` `/health/web/` | Health checks (database, cache, storage, Celery); Caddy answers 404 unless the X-Health-Token header matches | the uptime monitor, the container health check | django-health-check page (`health_check/index.html`, unbranded) | D U | system | existing | not restyled |
| `/shop/webhooks/razorpay/` (POST) | Razorpay's payment and refund webhooks, signature checked, replay protected | Razorpay | none (`ok` or 400) | D V | J1 buy | existing | n/a |
| `/learn/hls/<token>/<file>` | A clip's HLS playlist, segments and poster behind a signed, expiring link (the app's player and the staff player) | holder of a signed link (the app, the staff player) | HLS files | D S U | J1 revise | existing | n/a |

#### I. Development only

| Route | Purpose | Who may use it | Template / serializer | States | Journey | Status | Redesign |
|---|---|---|---|---|---|---|---|
| `/__debug__/...` (7 routes) | django-debug-toolbar panels | developers on 127.0.0.1 with `DEBUG=1` | library | D | dev | not shipped | n/a |

### 3.2 Staff and the admin

**Door.** `/admin/login/` redirects to the allauth log-in; a member of staff without an authenticator app or a passkey is sent to `/account/2fa/totp/activate/` before anything else opens (`StaffMFAMiddleware`); staff sessions end after 8 hours. The admin is Django's, themed by `admin_interface` with the site's colours (`ops/migrations/0004_admin_theme_tokens.py`), so the component vocabulary does not apply to it. Roles are the groups in `accounts/roles.py`.

**Home.** `/admin/` shows "ExamLeaf at a glance" (today and the last 30 days: registrations, those with a confirmed email, attempts saved), what waits (teacher requests, account deletions, legal pages still holding placeholders) and, for those who may view orders, the shop block (orders to pack, on the way, reviews and quotations waiting, sales by day, most sold, running out). States: D, E ("No orders.", "None yet.", "Nothing is running out."), P (modules are listed by permission), S (8-hour session), U (the authenticator step). No loading state, no chart.

**Custom pages.** the customer page `/admin/shop/order/customer/<user>/` (account, orders, addresses, reviews, quotations, stock alerts, courses; `shop/admin/customer.html`), the Add order form for phone and school orders (`staff_order.html`), the action forms for shipping and offline payments (`action_form.html`, untouched since the pre-redesign commit), the quotation PDF (`/admin/shop/quoterequest/<pk>/quotation/`), and `/learn/preview/<clip>/` (section 3.1 G).

**Access by role** (probed with a user of each role: the change list for view, the add form for add; change and delete follow `roles.py`).

| Model (app.model) | ADMIN | CONTENT_EDITOR | SALES | SUPPORT | Staff actions beyond edit |
|---|---|---|---|---|---|
| `account.emailaddress` | view + add | no | no | view |  |
| `accounts.consentrecord` | view | no | no | view | CSV export (ADMIN) |
| `accounts.deletionrequest` | view | no | no | view |  |
| `accounts.teacherprofile` | view + add | no | no | view | Verify (gives TEACHER), Revoke |
| `accounts.user` | view + add | no | no | view | CSV export (ADMIN) |
| `admin_interface.theme` | view + add | no | no | no |  |
| `auth.group` | view + add | no | no | no |  |
| `axes.accessattempt` | view | no | no | no |  |
| `axes.accessfailurelog` | view | no | no | no |  |
| `axes.accesslog` | view | no | no | no |  |
| `content.board` | view + add | view | no | no |  |
| `content.book` | view + add | view + add | view | no |  |
| `content.classlevel` | view + add | view | no | no |  |
| `content.paper` | view + add | view + add | no | no |  |
| `content.question` | view + add | view + add | no | no |  |
| `content.solution` | view + add | view + add | no | no |  |
| `content.subject` | view + add | view | no | no |  |
| `django_celery_beat.clockedschedule` | view + add | no | no | no |  |
| `django_celery_beat.crontabschedule` | view + add | no | no | no |  |
| `django_celery_beat.intervalschedule` | view + add | no | no | no |  |
| `django_celery_beat.periodictask` | view + add | no | no | no |  |
| `django_celery_beat.solarschedule` | view + add | no | no | no |  |
| `django_celery_results.groupresult` | view + add | no | no | no |  |
| `django_celery_results.taskresult` | view + add | no | no | no |  |
| `learn.bookcode` | view | no | no | view |  |
| `learn.chapter` | view + add | view + add | no | no |  |
| `learn.clip` | view + add | view + add | no | no | Move up, Move down, Process the video again; Preview link |
| `learn.entitlement` | view + add | no | no | view + add |  |
| `learn.flashcard` | view + add | view + add | no | no |  |
| `learn.quizitem` | view + add | view + add | no | no |  |
| `learn.revision` | view + add | view + add | no | no | Publish, Back to draft |
| `mfa.authenticator` | view + add | no | no | no |  |
| `ops.emailsuppression` | view | no | no | view |  |
| `ops.smslog` | view | no | no | view |  |
| `pages.page` | view | view | no | no |  |
| `practice.answersheetupload` | view + add | no | no | no |  |
| `practice.attempt` | view + add | no | no | view | CSV export (ADMIN) |
| `shop.category` | view + add | view + add | view | no |  |
| `shop.collection` | view + add | view + add | view | no |  |
| `shop.coupon` | view + add | no | view + add | no |  |
| `shop.creditnote` | view | no | view | view |  |
| `shop.invoice` | view | no | view | view |  |
| `shop.offer` | view + add | no | view + add | no |  |
| `shop.order` | view + add | no | view + add | view | Mark packed, delivered, shipped (courier and tracking), Cancel, Refund in full, Email payment link, Record offline payment; Add order (phone or school order); customer page |
| `shop.payment` | view | no | view | view |  |
| `shop.product` | view + add | view + add | view + add | view | Put on sale, Take off sale, Set stock |
| `shop.producttype` | view + add | view + add | view | no |  |
| `shop.quoterequest` | view | no | view | view | Make the quotation PDF (download link) |
| `shop.refund` | view | no | view | view |  |
| `shop.review` | view | no | view | view | Approve, Reject |
| `shop.shippingrate` | view + add | no | view + add | no |  |
| `shop.stockalert` | view | no | view | view |  |
| `socialaccount.socialaccount` | view + add | no | no | no |  |
| `socialaccount.socialapp` | view + add | no | no | no |  |
| `socialaccount.socialtoken` | view + add | no | no | no |  |
| `taggit.tag` | view + add | no | no | no |  |
| `token_blacklist.blacklistedtoken` | view + add | no | no | no |  |
| `token_blacklist.outstandingtoken` | view | no | no | no |  |

Reading the table: ADMIN reaches everything except what only superusers may change (periodic tasks, groups, second factors, social apps: view only); CONTENT_EDITOR owns the books, papers, questions, legal pages, the catalogue structure and the revision course's content; SALES owns prices, stock, coupons, offers, shipping, orders, payments, refunds and reviews; SUPPORT can look up accounts, consent, deletions, orders, the SMS log and email suppression, verify teachers, and open a course by hand. A permission failure inside the admin renders the public site's 403 page.

### 3.3 REST API v1

`/api/v1/<path>` (URL-path versioned), JWT bearer or the website's session; JSON only; the OpenAPI schema is `/api/schema/` with Swagger at `/api/docs/` and Redoc at `/api/redoc/`. Anonymous callers get the catalogue; everything else needs a signed-in user whose email is confirmed. "Probe" lists the HTTP status the test client got as an anonymous caller and as a student (empty bodies for POST, so 400 means "reachable, the body was refused" and 401 means "sign in first"). Paths that appeared during the audit are marked in progress: the API is being brought to parity with the website for the app.

| Path (`/api/v1`) | Methods | Purpose | Who (probe: anonymous / student) | Request → response serializer | States | Journey | Status |
|---|---|---|---|---|---|---|---|
| `/addresses/` | GET, POST | The signed-in customer's own addresses (another customer's: 404). | signed in, email confirmed. Probe: GET 401, POST 401 / GET 200, POST 400 | Address → Address, PaginatedAddressList | D E V P S | J1 buy | existing |
| `/addresses/{id}/` | GET, PUT, PATCH, DELETE | The signed-in customer's own addresses (another customer's: 404). | signed in, email confirmed. Probe: GET 401 / GET 200 | Address → Address | D V P S | J1 buy | existing |
| `/attempts/` | GET, POST | The signed-in student's own attempts (My record), filterable by subject id and tier. | signed in, email confirmed. Probe: GET 401, POST 401 / GET 200, POST 400 | Attempt → Attempt, PaginatedAttemptList | D E V P S | J1 access, revise | existing |
| `/attempts/{id}/` | GET, PUT, PATCH, DELETE | The signed-in student's own attempts (My record), filterable by subject id and tier. | signed in, email confirmed. Probe: GET 401, PUT 401 / GET 200, PUT 400 | Attempt → Attempt | D V P S | J1 access, revise | existing |
| `/auth/exchange/` | POST | The JWT pair for an app signed in through allauth.headless (/_allauth/app/v1/: a code by email or SMS, a passkey, Google, a password with a second step): send the session token of its answers as X-Session-Token. | an app signed in through the headless API (its session is exchanged). Probe: POST 401 / POST 200 | none → JWT | D V P S U | J2 sign-in | in progress (not in the last commit) |
| `/auth/login/` | POST | Check the credentials and return the REST Token if the credentials are valid and authenticated. | anyone. Probe: POST 400 / POST 400 | Login → JWT | D V U | J2 sign-in | existing |
| `/auth/logout/` | POST | Calls Django logout method and delete the Token object assigned to the current User object. | holder of a refresh token (it is sent in the body). Probe: POST 401 / POST 401 | Logout → RestAuthDetail | D V P S U | J2 sign-in | existing |
| `/auth/password/change/` | POST | Calls Django Auth SetPasswordForm save method. | signed in; the password is asked again. Probe: POST 401 / POST 400 | PasswordChange → RestAuthDetail | D V P S U | J2 sign-in | existing |
| `/auth/password/reset/` | POST | Calls Django Auth PasswordResetForm save method. | anyone. Probe: POST 400 / POST 400 | PasswordReset → RestAuthDetail | D V U | J2 sign-in | existing |
| `/auth/password/reset/confirm/` | POST | Password reset e-mail link is confirmed, therefore this resets the user's password. | anyone. Probe: POST 400 / POST 400 | PasswordResetConfirm → RestAuthDetail | D V U | J2 sign-in | existing |
| `/auth/phone/code/` | POST | Log in with a code by SMS: a 6-digit code goes to the number if an account confirmed it on the website (My account); the answer is the same for any Indian mobile number. | anyone. Probe: POST 400 / POST 400 | PhoneCode → VerificationSent | D V U | J2 sign-in | existing |
| `/auth/phone/confirm/` | POST | The texted code with the verification_token from phone/code/: answers with the tokens, as a log-in. | anyone. Probe: POST 400 / POST 400 | PhoneConfirm → JWT | D V U | J2 sign-in | existing |
| `/auth/registration/` | POST | Sign up. Emails a code; send it with the verification_token to verify-email, which logs the student in. | anyone. Probe: POST 400 / POST 400 | Register → VerificationSent | D V U | J2 sign-in | existing |
| `/auth/registration/verify-email/` | POST | Confirm the email address with the emailed code; answers with the tokens, as a log-in. | anyone. Probe: POST 400 / POST 400 | VerifyEmail → JWT | D V U | J2 sign-in | existing |
| `/auth/token/refresh/` | POST | Takes a refresh type JSON web token and returns an access type JSON web token if the refresh token is valid. | holder of a refresh token. Probe: POST 401 / POST 401 | TokenRefresh → TokenRefresh | D V P S U | J2 sign-in | existing |
| `/auth/token/verify/` | POST | Takes a token and indicates if it is valid. | anyone with a token to check. Probe: POST 400 / POST 400 | TokenVerify → inline JSON (no serializer in the schema) | D V U | J2 sign-in | existing |
| `/boards/` | GET | The exam boards. | anyone. Probe: GET 200 / GET 200 | none → PaginatedBoardList | D E | J1 discover, access | existing |
| `/boards/{id}/` | GET | One board. | anyone. Probe: GET 200 / GET 200 | none → Board | D | J1 discover, access | existing |
| `/books/` | GET | Books with their published papers (only published papers are public, as on the website). | anyone. Probe: GET 200 / GET 200 | none → PaginatedBookList | D E | J1 discover, access | existing |
| `/books/{slug}/` | GET | Books with their published papers (only published papers are public, as on the website). | anyone. Probe: GET 200 / GET 200 | none → Book | D | J1 discover, access | existing |
| `/cart/` | GET | The signed-in customer's cart, the same as on the website. | signed in, email confirmed. Probe: GET 401 / GET 200 | none → Cart | D P S | J1 buy | existing |
| `/cart/coupon/` | POST, DELETE | Use a coupon code (any case). | signed in, email confirmed. Probe: POST 401, DELETE 401 / POST 400, DELETE 200 | Coupon → Cart | D V P S U | J1 buy | existing |
| `/cart/items/` | POST | Add copies of a book (to those already in the cart), at most 20 in all. | signed in, email confirmed. Probe: POST 401 / POST 400 | CartItem → Cart | D V P S | J1 buy | existing |
| `/cart/items/{product}/` | PUT, PATCH, DELETE | Set the number of copies of a book in the cart (0 removes it). | signed in, email confirmed. Probe: PUT 401, DELETE 401 / PUT 400, DELETE 200 | Quantity → Cart | D V P S | J1 buy | existing |
| `/categories/` | GET | The category tree, in tree order (each category followed by its sub-categories); products/?category=<slug> lists a category's products. | anyone. Probe: GET 200 / GET 200 | none → PaginatedCategoryList | D E | J1 buy | existing |
| `/categories/{slug}/` | GET | The category tree, in tree order (each category followed by its sub-categories); products/?category=<slug> lists a category's products. | anyone. Probe: GET 200 / GET 200 | none → Category | D | J1 buy | existing |
| `/collections/` | GET | Hand-picked lists of products ("Board 2027 essentials"); `products` are slugs, in the order staff gave them. | anyone. Probe: GET 200 / GET 200 | none → PaginatedCollectionList | D E | J1 buy | existing |
| `/collections/{slug}/` | GET | Hand-picked lists of products ("Board 2027 essentials"); `products` are slugs, in the order staff gave them. | anyone. Probe: GET 200 / GET 200 | none → Collection | D | J1 buy | existing |
| `/config/` | GET | What this server has switched on, so that a frontend never hard-codes a feature flag: the ways to log in (allauth.headless's /_allauth/<client>/v1/config has allauth's own view of them), the bot check, the shop, whether the soluti | anyone. Probe: GET 200 / GET 200 | none → Config | D | J1 discover | in progress (not in the last commit) |
| `/devices/` | POST, DELETE | The app's Firebase Cloud Messaging token, for the daily reminder: POST after log-in (and when Firebase gives a new one), DELETE at log-out. | signed in, email confirmed. Probe: POST 401, DELETE 401 / POST 400, DELETE 400 | Device → Device | D V P S | J3 account, data rights | existing |
| `/learn/chapters/` | GET | Chapters with a published revision, `?subject=<id>`; one chapter with its revision's clips. | anyone. Probe: GET 200 / GET 200 | none → PaginatedChapterList | D E | J1 revise | existing |
| `/learn/chapters/{id}/` | GET | Chapters with a published revision, `?subject=<id>`; one chapter with its revision's clips. | anyone. Probe: GET 200 / GET 200 | none → ChapterDetail | D | J1 revise | existing |
| `/learn/clips/{id}/` | GET | A processed clip of a published revision, with its links (403 while it is locked); its progress. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: GET 401 / GET 404 | none → Clip | D P S | J1 revise | existing |
| `/learn/clips/{id}/progress/` | POST | How far the student watched; `completed` once true stays true. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: POST 401 / POST 404 | Progress → Progress | D V P S | J1 revise | existing |
| `/learn/entitlements/` | GET | What the user may watch, newest first (expired ones included: `valid_until`). | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: GET 401 / GET 200 | none → PaginatedEntitlementList | D E P S | J1 revise | existing |
| `/learn/flash-cards/` | GET | A chapter's flash cards (the first chapter's are free); "I knew it" or not, for revise-again. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: GET 401 / GET 200 | none → PaginatedFlashCardList | D E P S | J1 revise | existing |
| `/learn/flash-cards/{id}/review/` | POST | A chapter's flash cards (the first chapter's are free); "I knew it" or not, for revise-again. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: POST 401 / POST 404 | Review → inline JSON (no serializer in the schema) | D V P S | J1 revise | existing |
| `/learn/plan/` | GET | The pass plan: clips day by day until the exam, chapters by Board marks x previous-year questions x weakness, and the minimum to pass. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: GET 401 / GET 400 | none → inline JSON (no serializer in the schema) | D P S | J1 revise | existing |
| `/learn/quiz/` | GET | A chapter's one-mark quiz (no answers in the list); an answer is checked on the server and recorded. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: GET 401 / GET 403 | none → PaginatedQuizItemList | D E P S | J1 revise | existing |
| `/learn/quiz/{id}/attempt/` | POST | A chapter's one-mark quiz (no answers in the list); an answer is checked on the server and recorded. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: POST 401 / POST 403 | Answer → Checked | D V P S U | J1 revise | existing |
| `/learn/redeem/` | POST | A book code: opens its subject (or all) for a year; a code works once. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: POST 401 / POST 400 | Code → Entitlement | D V P S U | J1 revise | existing |
| `/learn/revise-again/` | GET | Quiz items and flash cards answered wrong whose day has come (1, 3 and 7 days), the longest waiting first. | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: GET 401 / GET 200 | none → inline JSON (no serializer in the schema) | D P S | J1 revise | existing |
| `/learn/settings/` | GET, PUT, PATCH | The student's course settings: exam date, minutes a day, the daily reminder (off until turned on). | signed in; the subject must be unlocked with a book code (403 otherwise). Probe: GET 401, PUT 401 / GET 200, PUT 200 | Learner → Learner | D V P S | J1 revise | existing |
| `/me/` | GET, PUT, PATCH | Reads and updates UserModel fields Accepts GET, PUT, PATCH methods. | signed in, email confirmed. Probe: GET 401, PATCH 401 / GET 200, PATCH 200 | Profile → Profile | D V P S | J3 account, data rights | existing |
| `/me/deletion/` | POST, DELETE | Delete my account: POST (with the password) asks for it, due seven days later; DELETE cancels it. | signed in; the password is asked again. Probe: POST 401, DELETE 401 / POST 400, DELETE 404 | Password → Deletion | D V P S U | J3 account, data rights | existing |
| `/me/export/` | POST | Download my data: everything kept about the user, as the website's JSON file. | signed in; the password is asked again. Probe: POST 401 / POST 400 | Password → JSON, the website's export | D V P S U | J3 account, data rights | existing |
| `/me/parent-consent/` | POST | PARENTAL_CONSENT_MODE "verified", while a parent has not confirmed (`consent_pending` in me/): the link to confirm, again, to the contact on record or a corrected one, as on My account. | signed in, email confirmed. Probe: POST 401 / POST 400 | ParentContact → Detail | D V P S U | J3 account, data rights | in progress (not in the last commit) |
| `/me/teacher/` | GET, POST | Teacher access, as on My account: GET the request and whether staff have verified it (404 until there is one); POST asks for it, once per account. | signed in, email confirmed. Probe: GET 401, POST 401 / GET 404, POST 400 | Teacher → Teacher | D V P S | J3 account, data rights | in progress (not in the last commit) |
| `/orders/` | GET, POST | The signed-in customer's own orders (another customer's: 404), checkout, payment and cancellation. | signed in, email confirmed. Probe: GET 401, POST 401 / GET 200, POST 400 | Checkout → Order, PaginatedOrderBriefList | D E V P S | J1 buy | existing |
| `/orders/{number}/` | GET | The signed-in customer's own orders (another customer's: 404), checkout, payment and cancellation. | signed in, email confirmed. Probe: GET 401 / GET 200 | none → Order | D P S | J1 buy | existing |
| `/orders/{number}/cancel/` | POST | Cancel while pending or paid; an online payment is refunded in full (5–7 working days). | signed in, email confirmed. Probe: POST 401 / POST 200 | none → Order | D V P S | J1 buy | existing |
| `/orders/{number}/credit-notes/{note}/` | GET | A credit note PDF (for a refund of an invoiced order). | signed in, email confirmed. Probe: GET 401 / GET 404 | none → PDF file | D P S | J1 buy | existing |
| `/orders/{number}/invoice/` | GET | The invoice PDF (404 until it has been made, a few minutes after payment). | signed in, email confirmed. Probe: GET 401 / GET 404 | none → PDF file | D P S | J1 buy | existing |
| `/orders/{number}/payment/` | POST | Start paying online: the options for Razorpay's mobile SDK, with the Razorpay order for this order (made on the first call; the same one afterwards). | signed in, email confirmed. Probe: POST 401 / POST 400 | none → PaymentStart | D V P S U | J1 buy | existing |
| `/orders/{number}/payment/confirm/` | POST | The SDK's success callback, checked (signature) and confirmed with Razorpay: the order is paid and the cart emptied. | signed in, email confirmed. Probe: POST 401 / POST 400 | PaymentConfirm → Order | D V P S U | J1 buy | existing |
| `/orders/lookup/` | POST | Guests (who ordered on the website without an account): the link to an order is emailed to the address it was placed with, never answered here; the answer is the same whether an order matched or not. | anyone. Probe: POST 400 / POST 400 | Lookup → LinkSent | D V U | J1 buy | existing |
| `/orders/t/{token}/` | GET | An order by the secret of the link in its emails (`https://<domain>/orders/t/<token>/`), without signing in, as the website's page: status, books, address, tracking, refunds and the PDFs; read-only. | whoever holds the emailed link. Probe: GET 200 / GET 200 | none → OrderLink | D | J1 buy | in progress (not in the last commit) |
| `/pages/` | GET | The legal and policy pages (privacy, terms, refunds, shipping, contact) as the website shows them: Markdown and HTML, the version (consent records keep the privacy notice's) and when the text last changed. | anyone. Probe: GET 200 / GET 200 | none → PaginatedPageList | D E | J1 discover | in progress (not in the last commit) |
| `/pages/{slug}/` | GET | The legal and policy pages (privacy, terms, refunds, shipping, contact) as the website shows them: Markdown and HTML, the version (consent records keep the privacy notice's) and when the text last changed. | anyone. Probe: GET 200 / GET 200 | none → Page | D | J1 discover | in progress (not in the last commit) |
| `/papers/` | GET | Published papers; filter by book, subject, tier; search by code or title. | anyone. Probe: GET 200 / GET 200 | none → PaginatedPaperList | D E | J1 discover, access | existing |
| `/papers/{code}/` | GET | One published paper (its solutions are a separate path). | anyone. Probe: GET 200 / GET 200 | none → Paper | D | J1 discover, access | existing |
| `/papers/{code}/solutions/` | GET | The questions in paper order, each with its marking-scheme solution (Markdown and HTML). | signed in, email confirmed (anyone when `SOLUTIONS_REQUIRE_LOGIN=0`). Probe: GET 401 / GET 200 | none → Question | D P S | J1 discover, access | existing |
| `/products/` | GET | The products on sale, with their prices, pictures, what a bundle holds, whether they are in stock, their categories and attributes. | anyone. Probe: GET 200 / GET 200 | none → PaginatedProductList | D E | J1 buy | existing |
| `/products/{slug}/` | GET | The products on sale, with their prices, pictures, what a bundle holds, whether they are in stock, their categories and attributes. | anyone. Probe: GET 200 / GET 200 | none → Product | D | J1 buy | existing |
| `/products/{slug}/reviews/` | GET, POST | GET: the approved reviews, their average, and whether the signed-in user may write one. | anyone to read; a buyer, signed in, to write. Probe: GET 200, POST 401 / GET 200, POST 400 | ProductReview → ProductReview, ProductReviews | D V P S U | J1 buy | in progress (not in the last commit) |
| `/products/{slug}/stock-alert/` | POST | "Email me when it is back", for a product out of stock: one email, to the signed-in user's address or the one given. | anyone (rate limited). Probe: POST 401 / POST 200 | StockAlert → Detail | D V P S U | J1 buy | in progress (not in the last commit) |
| `/qr/{code}/` | GET | What a scanned code (PHY-E01, any case) points to: the paper, with its solutions_url. | anyone. Probe: GET 200 / GET 200 | none → Paper | D | J1 discover, access | existing |
| `/quotes/` | POST | School and bulk orders, the website's form: the buyer's details and the copies of each book; staff are emailed and send a quotation. | anyone (Turnstile token when keys are set). Probe: POST 400 / POST 400 | Quote → QuoteSent | D V U | J1 buy | in progress (not in the last commit) |
| `/subjects/` | GET | Subjects with their board and class; filter by board. | anyone. Probe: GET 200 / GET 200 | none → PaginatedSubjectList | D E | J1 discover, access | existing |
| `/subjects/{id}/` | GET | One subject. | anyone. Probe: GET 200 / GET 200 | none → Subject | D | J1 discover, access | existing |

### 3.4 allauth headless API

`/_allauth/app/v1/...` (token sessions, for the mobile app) and `/_allauth/browser/v1/...` (cookie sessions, for a browser client), plus `/_allauth/openapi.json` and `.yaml`. They are the library's JSON versions of the log-in, sign-up, code, password, second-factor, passkey and Google flows; the website's own pages do not call them, and their screens (and states) belong to whichever client is built on them. 67 patterns, 33 operations. All of it is in progress (not in the last commit); `POST /api/v1/auth/exchange/` turns an app session into the REST API's JWT pair.

| Name (`headless:<client>:...`) | Path under `/_allauth/<app or browser>/v1/` | Purpose | Clients |
|---|---|---|---|
| `config` | `/config` | What this server offers (flows, providers) | app, browser |
| `account:current_session` | `/auth/session` | Read the session (GET) or log out (DELETE) | app, browser |
| `account:reauthenticate` | `/auth/reauthenticate` | Enter the password again | app, browser |
| `account:confirm_login_code` | `/auth/code/confirm` | Confirm the log-in code | app, browser |
| `account:request_password_reset` | `/auth/password/request` | Ask for a password reset email | app, browser |
| `account:reset_password` | `/auth/password/reset` | Set a new password from the emailed key | app, browser |
| `account:login` | `/auth/login` | Log in with email or mobile number and password | app, browser |
| `account:signup` | `/auth/signup` | Register | app, browser |
| `account:verify_email` | `/auth/email/verify` | Confirm the email code (GET shows what is pending) | app, browser |
| `account:resend_email_verification_code` | `/auth/email/verify/resend` | Send the email code again | app, browser |
| `account:verify_phone` | `/auth/phone/verify` | Confirm the texted code | app, browser |
| `account:resend_phone_verification_code` | `/auth/phone/verify/resend` | Send the texted code again | app, browser |
| `account:request_login_code` | `/auth/code/request` | Ask for a log-in code (email or SMS) | app, browser |
| `account:resend_login_code` | `/auth/code/resend` | Send the log-in code again | app, browser |
| `account:change_password` | `/account/password/change` | Change the password | app, browser |
| `account:manage_email` | `/account/email` | List, add, change and remove email addresses | app, browser |
| `account:manage_phone` | `/account/phone` | Read and change the mobile number | app, browser |
| `socialaccount:manage_providers` | `/account/providers` | List and disconnect connected providers | app, browser |
| `socialaccount:provider_signup` | `/auth/provider/signup` | Finish the sign-up after Google | app, browser |
| `socialaccount:redirect_to_provider` | `/auth/provider/redirect` | Start Google sign-in | app, browser |
| `socialaccount:provider_token` | `/auth/provider/token` | Sign in with a Google token (the app) | app, browser |
| `mfa:authenticate` | `/auth/2fa/authenticate` | Second step at log-in | app, browser |
| `mfa:reauthenticate` | `/auth/2fa/reauthenticate` | Second step before a sensitive change | app, browser |
| `mfa:authenticate_webauthn` | `/auth/webauthn/authenticate` | Passkey as the second step | app, browser |
| `mfa:reauthenticate_webauthn` | `/auth/webauthn/reauthenticate` | Passkey to re-check | app, browser |
| `mfa:login_webauthn` | `/auth/webauthn/login` | Log in with a passkey | app, browser |
| `mfa:authenticators` | `/account/authenticators` | List the second factors | app, browser |
| `mfa:manage_totp` | `/account/authenticators/totp` | Set up or remove the authenticator app | app, browser |
| `mfa:manage_recovery_codes` | `/account/authenticators/recovery-codes` | See or regenerate recovery codes | app, browser |
| `mfa:manage_webauthn` | `/account/authenticators/webauthn` | List, add, rename and remove passkeys | app, browser |
| `tokens:refresh` | `/tokens/refresh` | Refresh the session token (app client) | app |
| `openapi_yaml` | `/_allauth/openapi.yaml` | The OpenAPI document (YAML) | both |
| `openapi_json` | `/_allauth/openapi.json` | The OpenAPI document | both |

## 4. Proposed additions (not built)

Only what a journey above needs and the code does not do; each is tied to a gap or to evidence in the repository.


| Proposal | Route sketch | Journey | Why (evidence) | Needs |
|---|---|---|---|---|
| Open sample solutions | `/s/<code>/` open for one flagged paper per subject; the home and product links point to it | J1 discover | G1: every "sample" link ends on a wall | a `Paper.is_sample` flag |
| Find a paper by code | a box on the home page and on the 404 page: `PHY-E01` → `/s/PHY-E01/` | J1 access | a torn or unscannable QR has no fallback; the 404 only says to scan again | one GET route |
| Your papers block on the order | on `/checkout/<n>/done/` and `/account/orders/<n>/` | J1 buy to access | G20 | no new route |
| Web revision course | `/learn/` (subjects unlocked), `/learn/<chapter>/` (clips, quiz, flash cards), `/learn/plan/`, `/learn/redeem/` | J1 revise | the API is complete (`/api/v1/learn/*`, 26 operations); the website has none of it | views and templates only |
| App hand-off | a card on My account and the order page: link and QR | J1 revise | G5 | the store URL |
| Contact form | `/contact/` form | all | G6 | an inbox |
| Teacher view | `/account/teacher/students/` | J3 | G14 | the teacher-student link model |
| Answer-sheet check | `/account/record/<id>/sheet/` | J1 revise | `AnswerSheetUpload` exists with no logic ("planned") | the checker (docs plan) |
| Readable data page | `/account/data/` shows what is kept before the download | J3 | G21 | none |

## 5. What makes it feel generic

Observations from the screenshots in `screenshots/before/` (commit `9b4c3f2`, the pre-redesign site) and `screenshots/after/` (the tree at the snapshot), backed by measurements of the laid-out pages (headless Chrome, `craft.py`). The redesign has already fixed the plainest faults of the before: the system font (before: `system-ui`, and Times on the bare 404), one 48 rem column, two to four type sizes, no imagery but the covers, a 404 that was Django's default. What is left is mostly repetition and flatness, not default styling. Each row names the page, so the craft pass can act on it; file names are in `screenshots/`.

| # | Observation | Page (after screenshot) | Evidence | Move for the craft pass |
|---|---|---|---|---|
| 1 | **One card shape repeated.** The book page is a wall of 30 identical white cards; the shop's nine cards share two or three shapes; the home page's feature grid is four same-shaped icon-title-grey-paragraph cards, then three text-only offer cards | `/books/physics-2027/`, `/shop/` (`shop-1280-after`), `/` (`home-1280-after`, Q.1 and Q.4) | cards and distinct shapes at 1280: book 30 cards in 1 shape, shop 9 in 2, home 10 in 6, product 5 in 1 | Vary the anatomy by what the thing is: the book as a hero row, tiers as bands with their colour, papers as a compact index with done marks for a signed-in student; subject colour as a band on shop cards instead of a chip |
| 2 | **Missing or token imagery where the product is sold.** The three offer cards on the home page sell a printed book with no picture of it; the four Solutions books in the shop are a flat colour panel with the wordmark, which reads as an image that failed to load; the before shows the same flat panels, so the redesign restyled the placeholder without replacing it | `/` Q.4, `/shop/` | in the development data the four Solutions books have no cover image uploaded, so they get the placeholder every cover-less product gets; the Sample Papers covers exist as AVIF at 320 and 480 px | Real cover art for the Solutions books, or one deliberate typographic cover per subject (a big numeral and the subject colour) that looks designed, not missing; put a cover in each offer card |
| 3 | **Weak, uniform hierarchy.** Every page opens with the same H1 recipe (Poppins 44px w800) whether it is the shop, the cart, a legal page or a lookup form, and the H1 sits only 12 to 17 px above the first block | `/cart/`, `/orders/lookup/`, `/privacy/`, `/shop/school-orders/`, `/shop/` | H1 to first block: cart 12 px, lookup 16, privacy 17, shop 16. Before: 25.6 px at 375, 32 px at 1280, one weight | Two page-head patterns: transactional (compact H1, no lead) and editorial (breadcrumb, H1, lead); a larger step between H1 and the first block |
| 4 | **Inconsistent top spacing.** Header to H1 is cart (empty) 28 px; privacy 28 px; order lookup 28 px; school orders 28 px; shop 67 px; home 91 px; login 93 px; signup 97 px; book 126 px; product 159 px; solutions (logged out) 184 px; 404 193 px at 1280 | `/cart/` (`cart-empty-1280-after`) against `/product`, `/s/PHY-E01/`, `/404` | the numbers in the row | One token for the space under the header, and let breadcrumbs and heroes add to it deliberately |
| 5 | **Empty and error screens are one dashed card.** Cart empty, 404, 403, 429 and offline share an icon, a centred title and one button. The cart prints its H1 *Your cart* left-aligned above a centred card that says *Your cart is empty.*, the same words twice, and the two do not align | `/cart/` (`cart-empty-1280-after`), `/this-page-does-not-exist/` (`404-1280-after`) | Before: the cart was one sentence, the 404 Django's default | Drop the duplicate heading; give the empty cart something to do (the two bestsellers, as the 404 shows books) |
| 6 | **The highest-intent page is the plainest.** A student holding the book scans the QR and lands on a navy header card and one white card with two buttons and one sentence | `/s/PHY-E01/` logged out (`solutions-logged-out-375-after`) | 61 words in `main`; 1556 px tall at 375 of which the footer is 812; before: the same structure in plain text | Show the first question and the marking table behind the wall, the promise (free, once, every QR) in three short lines, and a Log in with a code shortcut; the `next` handling is already right |
| 7 | **Copy that fits any bookshop.** *Delivered anywhere in India* (or *across India*) appears 4 times in the home page's main content, *QR code* 6 times; the final call to action reads *Start with one paper this week*; the 404 *We could not find that page*; the library pages *Bad Token* and *Account Inactive* | `/` (hero trust list, Q.1 trust strip, Q.3 step 1, final call to action), 19 allauth pages | phrase counts in the rendered `main` of `/` | One voice pass in the register of an Assam Class 12 student and parent: name the exam, quote what a marking step looks like, say it once; override the library pages |
| 8 | **One language.** No Assamese anywhere on the site, though two Bengali-script font subsets (141 KB) are declared and never fetched because no page has such text | whole site | `static/fonts/hind-siliguri-*-bengali.woff2`; browser-observed fonts: four Latin files only | A line of Assamese in the hero and the QR wall, or a language toggle for the wall and the FAQ; test the 1.7 line height on real text |
| 9 | **Dead space inside components.** The home page's big *30 full papers* card has 138 px of empty white between its text and the tier bars; the product page's Easy, Medium and Hard cards carry a title and nothing else; the FAQ and the Details table each stop at two thirds of the page width and leave the right third empty | `/` (`home-1280-after`, Q.1), `/shop/physics-sample-papers-2027/` (`product-physics-1280-after`, Q.1 and Q.2) | the gap is measured; the rest is visible in the full-page captures (`full/after/`) | Size cards to their content, or fill them: the tier's marks and an example question |
| 10 | **Chrome that never changes.** The same four-column footer and the same brand paragraph (the meta description word for word) on every page, even on the short transactional ones | `/cart/` (`cart-empty-1280-after`) | footer 376 px of a 988 px page | A slim footer on cart, checkout and payment; keep the full one on content pages |
| 11 | **Only the covers are pictures.** No photograph or drawing of a phone scanning the QR code, a printed solutions page, a marked answer sheet; *How it works* is a good CSS mock but static | `/` Q.3 | `static/img/` holds covers, icons and `og-default.jpg` only | One illustration set (scan, solve, check) in the same stroke style, or a device frame around the mock |
| 12 | **Long on phones.** Home is 8627 px tall at 375 (about 10.6 screens), shop 7302, product 4271, register 2887 | `/` (`home-375-after`), `/shop/`, `/account/signup/` | document heights at 375 | Collapse Q.1 and the FAQ on phones; keep one trust line |

What already reads as designed, and should be left alone: the dark hero with the fanned covers and the gold *30*; the Q.1 to Q.5 exam-paper dividers; the navy QR card with its seal; the tier chips and subject colours; the Register page's numbered fieldsets; the checkout stepper.

## 6. Method and reproducibility

The scripts are in `docs/design/audit-scripts/` (paths at the top of each; they only read the project, and work on a copy of the development database and of `media/products`). Order of a re-run, from `examleaf-web/` with its virtualenv:

```
DATABASE_URL=sqlite:///<copy>  python manage.py shell -c "exec(open('dump_urls.py').read())" > urls.json    # the routes
DATABASE_URL=sqlite:///<copy>  python manage.py spectacular --format openapi-json --file schema.json        # the API
python tpl_scan.py                                                                                           # the templates
UXA=<folder> DATABASE_URL=sqlite:///<copy>  python manage.py shell -c "exec(open('probe.py').read())"       # who may use what
PYTHONPATH=<folder> python manage.py runserver '[::1]:8060' --noreload --settings=ux_audit_settings         # the tree; the old commit from a git worktree on :8070
python3 shots.py <out> before,after "" <full>; python3 weights.py <base-url> <json>; python3 weights_cdp.py after,before; python3 craft.py after,before
python3 build_tables.py; python3 compose.py; python3 compose_baseline.py; python3 compose_readme.py          # the documents
```

`baseline.sh` runs the checks of `baseline.md`. The compose scripts also read two small files the steps above leave (`snapshot.json`, `counts.json`).

- **Routes.** `django.urls.get_resolver()` walked from `manage.py shell` (a dump of 634 patterns), joined to hand-written annotations (`matrix_data.py`); a route without an annotation fails the build (none did). The REST rows come from `manage.py spectacular` (the OpenAPI schema), the admin rows from `admin.site._registry`.
- **Who may use it.** Read from the views (`LoginRequiredMixin`, `login_required`, `staff_member_required`, `permission_classes`, `shop_open`, `visible_order`) and confirmed by a probe: a Django test client, on a copy of the dev database with the project's media folder pointed elsewhere, asked each route as an anonymous visitor, a student, a student with the parent's consent pending, a student just signed in, a member of staff of each of the four roles (with an authenticator app, so the middleware lets them in), and, for the API, as anonymous, student and admin (976 requests). The copy's orders, addresses and attempts were made with the project's factories; Razorpay was stubbed.
- **Redesign.** The HTML each route returned was searched for the classes of `direction.md` section 3, minus the classes the header and footer bring to every page, and for the 42 class names that exist in the pre-redesign stylesheet and no longer in the new one. The static scan of `templates/` (own classes, included partials, parents except `base.html`) gives the same verdicts: no page template still uses a pre-redesign class except the one named in section 0.
- **States.** From reading each template and view; the flows (sign-up with a code, code log-in, password log-in, save marks) were walked with the test client.
- **Screenshots and measurements.** Headless Chrome 154 driven over the DevTools protocol against two servers on `[::1]:8060` (the tree) and `[::1]:8070` (commit `9b4c3f2` in a git worktree, run with the current virtualenv, the current database copy and a copy of `media/products`), settings as in development but with `DEBUG` switched off at run time so that the 404 is the site's own page and the debug toolbar stays out of the pictures. The Claude browser pane could not open a tab of its own (its tab limit was reached by other work), so the pane was left alone.

## Open journeys

The journeys pass of 8 October 2026 (CHANGELOG.md, "Phase 7 journeys") closed G1, G2, G4, G5, G7 to G13, G15, G16, G19 to G21 and G25, and in part G6 (`/revision/` waits for the store links), G17 (the marks form now says why it cannot save) and G23 (the pages below keep the library's words). What is left needs a founder's decision or a feature the backend does not have; nothing below was guessed into the interface.

| Id | What is open | Why it waits | What it needs |
|---|---|---|---|
| G3 | Staff meet three looks: the themed admin, the public layout for `/learn/preview/<clip>/` and the admin's 403, and the library's `/health/` page | which chrome staff pages use is a design decision | a choice; then an admin 403 template and the preview on `admin/base_site.html`, or the reverse |
| G14 | Teacher access is a request only: `TeacherProfile` has no students | nothing links a teacher to students (the TODO in `api/views.py`) | the link model and its consent rules, then `/account/teacher/students/` |
| G17 | A student under 18 sent from checkout to My account is not told when the parent confirms | a new message to the student (email or SMS, and its words) is a product decision | the message, sent from `ConsentRecord.record` for parents, with a link back to the cart |
| G18 | After a password reset the visitor is not signed in, and a `next` does not survive the emailed link | signing in on reset is a security setting (`ACCOUNT_LOGIN_ON_PASSWORD_RESET`), and this pass changed no setting but the CSP | the decision; the reset's last page now has a Log in button |
| G22 | No shelves or collections exist, so `/shop/category/...` and `/shop/collection/...` are empty | which shelves and collections to make is a content decision | the rows, in the admin; their links appear on the shop page once they exist |
| G23 | `/account/3rdparty/` (Account Connections) and the authenticator-app pages keep allauth's words | reachable only with Google keys or by staff; the wording waits for the founder's voice pass | copy overrides like the ones made in this pass |
| G24 | The log-in page leads with the mobile number, usable only after one was confirmed on My account | leading with email contradicts the drawn Log in artboard (components.md section 3) | a design decision on the order of the ways to log in |
| T1 | `tabular-nums` does nothing: Poppins 4.004 and Hind Siliguri 1.001 have proportional digits and no `tnum` feature, so a re-subset changed no byte | aligned numbers need another family for `.num` cells (a design decision) | the family, subset with its `tnum` |
| T2 | `/revision/` shows `[Google Play link]` and `[App Store link]` | the app is not in the stores yet | the store addresses (and a QR on desktop, G6's second half) |
| T3 | The Contact form writes to `SUPPORT_EMAIL`, else `SELLER_EMAIL`; `settings.py` has no `SUPPORT_EMAIL` line, so production uses `SELLER_EMAIL`, and while that holds a `[placeholder]` the page shows a marked note instead of the form | the support inbox | the address in `.env` (and, if it differs from the seller's, a `SUPPORT_EMAIL` line in `settings.py`) |
| T4 | School quotation requests are kept with no end: the privacy draft says `[how long]` | a retention period is a legal decision | the period, then a line in `shop.tasks.clean_up` |
| T5 | The revision course itself (clips, quiz, flash cards, plan) is only in the app; `/revision/` describes it, lists the chapters and free clips, and takes book codes | playing clips on the website (signed HLS links on the site, the player) is a product decision | section 4's web course, if wanted |
