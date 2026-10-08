"""Hand-written prose of coverage-matrix.md: journeys, gap register, proposals, the generic-feel section."""

JOURNEYS = """
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
| 10 | Revise | The revision course (clips, quiz, flash cards, pass plan, book codes) lives in the app: `/api/v1/learn/*`; the website has the staff preview and one account row | **G5** the account row names the app but gives no link, store badge or QR; the website has no student surface for the course (see section 4) |

### J2. Sign in and recover

| # | Step | Routes crossed | Gap |
|---|---|---|---|
| 1 | Register: name, email, password, class, board, district, date of birth, the parent's details under 18, consent | `/account/signup/` → `/account/confirm-email/` (six-box code) → `next` or `/` | `next` survives both steps (checked: QR landing → Register → code → the same paper) |
| 2 | Log in: SMS code, email code, Google (when keys are set), passkey, or password in a fold | `/account/login/` → `/account/login/code/confirm/` ; `/account/google/login/`; `/account/2fa/webauthn/login/` | **G24** the first field is a mobile number, usable only after one was confirmed on My account |
| 3 | Staff second step | `/account/2fa/authenticate/` (first time: `/account/2fa/totp/activate/`) → `/admin/` | |
| 4 | Forgot the password | `/account/password/reset/` → `/account/password/reset/done/` → email → `/account/password/reset/key/<uid>-<key>/` → `/account/password/reset/key/done/` | **G1b** the last page has no Log in button; **G18** after a reset the visitor is not signed in and the destination is gone; **G23** library copy ("Bad Token", "Change Password") |
| 5 | Add a way back in | My account → `/account/phone/change/` → `/account/phone/verify/`; `/account/2fa/webauthn/add/`; `/account/email/`; `/account/password/change/` | |
| 6 | An account is switched off | `/account/inactive/` | **G3** one line, no way to ask for help |

### J3. Account and data rights

| # | Step | Routes crossed | Gap |
|---|---|---|---|
| 1 | The hub | `/account/` (record, orders, details, addresses, mobile and passkeys, consent, data) | |
| 2 | A parent confirms a minor's account | link `/c/<token>/` (7 days); the student resends from `/account/` via POST `/account/parent-consent/` | **G4** an expired link tells the parent to ask the child; no contact link |
| 3 | Download my data | `/account/data/` → (password again) → JSON file | **G21** a raw JSON file, no readable summary |
| 4 | Delete my account | `/account/delete/` → (password again) → 7-day grace → `/account/delete/cancel/` | |
| 5 | Teacher access | `/account/teacher/` → status on `/account/` | **G14** a request only; no teacher features |

### J4. Staff operations

| # | Step | Routes crossed | Gap |
|---|---|---|---|
| 1 | Sign in with a second factor | `/admin/login/` → `/account/login/?next=/admin/` → `/account/2fa/authenticate/` | |
| 2 | The day's queue | `/admin/` (today and 30-day figures; orders to pack, on the way, reviews and quotations waiting) | **G2** two layouts: the admin, and the public layout for `/learn/preview/` and for the 403 page inside the admin |
| 3 | Orders | `/admin/shop/order/` → actions (pack, ship with courier and tracking, deliver, cancel, refund, payment link, offline payment); Add order for phone and school orders; customer page | |
| 4 | Catalogue and content | products, shelves, collections, offers, coupons, shipping rates; books, papers, questions, solutions; legal pages | |
| 5 | Revision course | chapters, revisions, clips (upload, ffmpeg, preview), flash cards, quiz items, entitlements, book codes | |
| 6 | Support and privacy | users, consent records, deletion requests, teacher verification, SMS log, email suppression | |
"""

GAPS = [
    # id, type, where, what, suggestion
    ("G1", "dead end", "`/s/<code>/` for a logged-out visitor; the home hero (`See a sample paper`, hard-coded to `PHY-M04`), the product page (`See a sample`), every paper link on `/books/<slug>/`", "Nothing can be read before registering (`SOLUTIONS_REQUIRE_LOGIN` defaults to 1), and the wall shows no preview of what is behind it.", "Open one sample paper per subject, or show a blurred first question and the marking table on the wall."),
    ("G1b", "dead end", "`/account/password/reset/key/done/`", "Heading reads Change Password, body one line, no Log in button.", "Own template with a Log in button that keeps `next`."),
    ("G2", "inconsistency", "`/learn/preview/<clip>/`, the 403 page inside the admin, `/health/`", "Staff meet three looks: the themed admin, the public layout, an unbranded library page.", "Pick one chrome for staff pages; give the admin a 403 of its own."),
    ("G3", "dead end", "`/account/inactive/`", "One line, no contact link.", "Say why and link Contact."),
    ("G4", "dead end", "`/c/<token>/` expired (HTTP 400)", "The parent is told to ask the child for a new link; no contact route, and the parent may not be able to reach the child.", "Add a Contact link and the student's first name."),
    ("G5", "dead end", "`/account/` row Revision course", "Names the app and says log in there, with no link, store badge or QR.", "Link to the app, show a QR on desktop."),
    ("G6", "dead end", "`/contact/` (and the 403, 404, 500 and consent pages that point to it)", "A static page with `[email]` and `[phone]` placeholders until staff fill them; no form.", "A contact form (or at least a mailto) and a launch check that fails while placeholders remain (the dashboard already counts them)."),
    ("G8", "missing state", "`/books/<slug>/`, `/s/<code>/`", "A book with no published paper, or a paper with no questions, renders a page with nothing to say.", "An `.empty` block with a way back."),
    ("G9", "missing state", "every form post (Register, Log in, Checkout, Add to cart, Save marks, coupons)", "Only the Pay button has a busy state; a slow post (signup sends an email) can be pressed twice.", "Set `aria-busy` and disable on submit in `site.js`."),
    ("G10", "missing state", "`/account/record/` with a filter", "A filter that matches nothing shows Nothing recorded yet, which is untrue.", "Tell No papers match these filters, with a Clear link."),
    ("G11", "context loss", "`/account/record/add/<code>/`", "A valid save sends the student to My record, away from the solutions they were reading; an invalid one to a separate page.", "Post back to the paper (`#record`), or save with fetch and keep the page."),
    ("G12", "missing state", "checkout and address forms", "The PIN autofill (`/shop/pin/<pin>/`) answers 404 when the directory is empty (it is, in the development database, until `import_pincodes` runs), and the form gives no sign.", "Hide the hint, or say when a PIN is not found; load the directory at deploy."),
    ("G13", "incomplete", "`/shop/?kind=`", "The parameter filters, but no control sets it.", "Add the kind tabs or drop the parameter."),
    ("G14", "incomplete", "`/account/teacher/`", "A request form only; `TeacherProfile` has no students (TODO in `api/views.py`).", "Define the link before building the screens."),
    ("G15", "context loss", "header Log in and Register (`base.html`)", "No `next`: logging in from `/books/...` or `/shop/...` lands on `/` (`LOGIN_REDIRECT_URL`). The QR wall, the cart and checkout do keep it.", "Add `?next={{ request.path }}` to both links."),
    ("G16", "context loss", "`/account/orders/` after a guest purchase", "Only orders placed while logged in are listed; a student who bought as a guest and registers later with the same email does not see it.", "Claim guest orders by verified email at first log-in."),
    ("G17", "context loss", "`/checkout/` for a minor with consent pending (`PARENTAL_CONSENT_MODE=verified`)", "Redirected to `/account/` with a toast; once the parent confirms, nothing brings the student back. The solutions page shows a save form that always fails for them.", "Disable the form with the reason; offer Back to checkout when consent arrives."),
    ("G18", "context loss", "password reset", "After a reset the visitor is not signed in and `next` is gone.", "Sign in after reset (allauth setting) or keep `next` in the key page."),
    ("G19", "dead end", "`/orders/t/<token>/` wrong or old", "The generic 404; only `/s/...` gets a hint on the 404 page.", "A 404 hint for `/orders/t/...`: Find your order."),
    ("G20", "journey break", "`/checkout/<n>/done/` and `/account/orders/<n>/`", "Nothing links the buyer to the papers or explains the QR code; the product, the book page and the order are three separate worlds.", "A Your papers block on the order: open Paper E-01, how the QR works."),
    ("G21", "incomplete", "`/account/data/`", "A raw JSON download with no readable summary or preview.", "A page that lists what is kept, then the download."),
    ("G22", "incomplete", "`/shop/category/<slug>/`, `/shop/collection/<slug>/`", "Built, but empty in the database and not linked from the home page.", "Seed one shelf or hide the entry points until used."),
    ("G23", "inconsistency", "{LIB_LAYOUT} allauth pages that are only the layout (`/account/inactive/`, `.../password/reset/done/`, `.../key/...`, `/account/3rdparty/...`) and {LIB_ELEMENTS} more drawn through the element overrides with the library's copy", "Library headings and copy: Bad Token, Account Inactive, Login Cancelled (says sign in), Third-Party Login Failure, Confirm Access, Email Address, Security Keys.", "Override the templates with the site's words and a next step."),
    ("G24", "journey friction", "`/account/login/` (SMS first)", "A first-time visitor sees Mobile number, Text me a code, and the help text The number you confirmed on My account; they have none.", "Lead with email unless the browser remembers a confirmed number."),
    ("G25", "robustness", "invoice PDF routes", "A missing PDF file (storage unreachable, file deleted) gives a 500, not a 404 (found while probing with another `MEDIA_ROOT`).", "Catch the file error in `pdf_response`."),
]

PROPOSED = """
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
"""
