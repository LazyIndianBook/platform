"""Writes docs/design/coverage-matrix.md from the live data (run build_tables.py first)."""
import collections, datetime, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prose

SCR = os.path.dirname(os.path.abspath(__file__))
REPO = "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12"
DOCS = f"{REPO}/docs/design"
J = lambda name: json.load(open(f"{SCR}/{name}"))
counts, tables = J("counts.json"), J("tables.json")
craft = J("craft-after-before.json")
tpl = J("tpl-scan.json")
snap = J("snapshot.json")

def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO).stdout.strip()

# renumber the gap ids: the hand-written ids skip G7 and carry a G1b
RENUMBER = {"G1b": "G2", "G2": "G3", "G3": "G4", "G4": "G5", "G5": "G6", "G6": "G7"}
def renum(text):
    return re.sub(r"\bG\d+b?\b", lambda m: RENUMBER.get(m.group(0), m.group(0)), text)

def cell(s):
    return s.replace("|", "\\|")

# --------------------------------------------------------------------------------------------------------------------
g = counts["groups"]
aud, aud_a = counts["aud"], counts["aud_allauth"]
anon_n, student_n = aud.get("anon", 0) + aud_a.get("anon", 0), aud.get("student", 0) + aud_a.get("student", 0)
machine_n, staff_site_n = aud.get("machine", 0), aud.get("staff", 0)
rd = counts["redesign"]
pages_n = sum(rd.values())
def rdn(k):
    return rd.get(k, 0)
html_templates = [k for k in tpl if k.endswith(".html")]
partials = [k for k in html_templates if os.path.basename(k).startswith("_")]
elements = [k for k in html_templates if k.startswith("allauth/elements/")]
emails_pdfs = [k for k in html_templates if k.startswith(("email/", "shop/email/", "shop/invoice", "shop/credit_note", "shop/quotation"))]
errors = [k for k in html_templates if os.path.basename(k).split(".")[0] in ("400", "403", "403_csrf", "404", "429", "500", "offline")]
page_templates = [k for k in html_templates if k not in partials + elements + emails_pdfs + errors and not k.startswith(("allauth/layouts", "admin/", "shop/admin/")) and k != "base.html"]
legacy_left = sorted({(k, c) for k, v in tpl.items() for c in v["legacy"] if not k.startswith(("shop/admin/", "admin/"))})
apps_n = len({m.split(".")[0] for m in json.load(open(f"{SCR}/admin-models.json"))}) if os.path.exists(f"{SCR}/admin-models.json") else 17

craft_after = {(r["page"], r["width"]): r for r in craft if r["variant"] == "after"}
craft_before = {(r["page"], r["width"]): r for r in craft if r["variant"] == "before"}

out = []
w = out.append

w(f"""# ExamLeaf website: coverage matrix

Audit of every route of the Django site (`examleaf-web/`) against the journeys it serves, the screens' states and the redesign vocabulary of `direction.md` section 3. Written by the UX audit of {snap['date']}; the other deliverables are `baseline.md` and `screenshots/`.

**Snapshot.** The audit began on commit `{snap['start_head']}` with {snap['dirty_start']} changed paths; at 11:45 IST another agent committed that work as `{snap['head']}`; the tree has {snap['dirty_end']} changed paths now. Other agents kept editing the templates, the API (a new headless-auth API, new endpoints for the app), the stylesheet (split into `site.css` and per-section files) and a migration throughout, so this is a snapshot, not a fixed point: routes that appeared during the audit are marked "in progress" and the numbers are from the tree as it stood when the audit ended. The scripts in section 6 re-measure everything; re-run them rather than trusting figures that are more than an hour old.

## 0. Summary

| What | Count |
|---|---|
| URL patterns in the resolver | {sum(g.values())} |
| Site routes (everything except the admin, the API and the debug toolbar) | {counts['site_patterns']}: anonymous {anon_n}, signed-in student {student_n}, machine {machine_n}, staff {staff_site_n} |
| Django admin | {counts['admin_patterns']} patterns for {counts['admin_models']} models in {apps_n} apps (section 3.2) |
| REST API v1 | {counts['api_paths']} paths, {counts['api_ops']} operations, plus the schema, Swagger and Redoc pages (section 3.3) |
| allauth headless API (for the app and for a browser client) | {g['headless']} patterns, {counts['headless_names']} operations once the app and browser variants are merged (section 3.4) |
| Debug toolbar (development only) | {g['dev']} |
| HTML page routes (the site's pages, not files or JSON) | {pages_n}: done {rdn('done')}, done through allauth's element overrides {rdn('done via allauth elements')}, partial {rdn('partial')}, layout only {rdn('layout')}, not restyled {rdn('none')}, not rendered by the probe {rdn('unverified')} |
| Templates | {len(html_templates)} `.html` files: {len(page_templates)} page templates, {len(partials)} partials, {len(elements)} allauth element overrides, {len(emails_pdfs)} email and PDF templates, {len(errors)} error and offline pages. None still uses a pre-redesign class name except {', '.join(f'`{c}` in `{k}`' for k, c in legacy_left) or 'none'} |
| Journeys | 4 (J1 to J4) with 10 + 6 + 5 + 6 steps; {len(prose.GAPS)} gaps in section 2 |

**Redesign column.** *done*: the page's own content uses the component vocabulary (three or more of `.btn .field .card .badge .alert .table-wrap .timeline ...`, or two on a short page) and no pre-redesign class. *done through allauth elements*: a library page whose controls come out as `.btn`, `.field`, `.card` through `templates/allauth/elements/`, with the library's copy. *partial*: one vocabulary class only, a pre-redesign class name left, or a form printed with a raw `{{{{ form }}}}` (the CSS styles bare controls, so it looks right but has no field error markup). *layout only*: the new header, footer and card around the library's plain content. *not restyled*: untouched by the vocabulary (the Django admin keeps its own theme; the health page is the library's). Judged on the HTML each route returns (a Django test client with a student, a guest and each staff role), not on the template source alone; the static scan of `templates/` agrees (section 6).

**States column.** D default · L loading (busy button, skeleton, spinner) · E empty (nothing yet, nothing found) · V validation or error feedback · P permission denied (redirect to log in, 403, or the 404 given for other people's objects) · S expired session, link or token · U unavailable (shop closed, out of stock, payment service down, rate limit, offline). `!X`: a state the page needs and does not have. For API rows: D 200 or 201, E an empty page of results, V 400, P 401 or 403, S an expired access token (15 minutes, then refresh), U 429 or 503.

**Journey column.** J1 discover, buy, access, revise · J2 sign-in and recovery · J3 account and data rights · J4 staff operations · system.

**Status column.** *existing* works as built; *incomplete* is built in part (what is missing is said); *in progress* is in the working tree and not in the last commit; *proposed* is in section 4 only.

## 1. Journeys

""")
w(renum(prose.JOURNEYS))
w("""
## 2. Gaps

Dead ends, missing states and journeys that lose their context, found by reading every template and view, by walking the flows with a test client (the QR landing → Register → emailed code → the same paper keeps its destination; so does a code log-in, a password log-in, and a page that asks for a log-in) and by probing every route as each kind of visitor.

| Id | Kind | Where | What | Suggested fix |
|---|---|---|---|---|
""")
alr = counts.get("allauth_redesign", {})
for gid, kind, where, what, fix in prose.GAPS:
    where = where.replace("{LIB_LAYOUT}", str(alr.get("layout", 0))).replace("{LIB_ELEMENTS}", str(alr.get("done via allauth elements", 0)))
    w(f"| {renum(gid)} | {kind} | {cell(where)} | {cell(what)} | {cell(fix)} |\n")

w("""
Checked and found sound, so nobody needs to look again: `?next=` survives the QR wall, sign-up with the emailed code, the code log-in, the password log-in, the cart's and the checkout's Log in links, and the re-entry of the password before data export or deletion; a guest's cart joins the account's at log-in; every order state (pending, placed on delivery, paid, delivered, cancelled) renders on `/account/orders/<n>/`, `/orders/t/<token>/` and `/checkout/<n>/done/`; other people's orders, addresses and attempts answer 404; the 400, 403, 404, 429 and 500 pages are the site's own.

## 3. Coverage matrix
""")
w("\n### 3.1 Site routes\n\nWho means who gets a useful answer; where an anonymous visitor is redirected to log in, the row says student. Methods are GET unless the route says POST.\n")
for letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I"]:
    if letter not in tables["SECTIONS"]:
        continue
    w(f"\n#### {tables['sec_title'][letter]}\n\n")
    w(tables["SECTIONS"][letter] + "\n")

w(f"""
### 3.2 Staff and the admin

**Door.** `/admin/login/` redirects to the allauth log-in; a member of staff without an authenticator app or a passkey is sent to `/account/2fa/totp/activate/` before anything else opens (`StaffMFAMiddleware`); staff sessions end after 8 hours. The admin is Django's, themed by `admin_interface` with the site's colours (`ops/migrations/0004_admin_theme_tokens.py`), so the component vocabulary does not apply to it. Roles are the groups in `accounts/roles.py`.

**Home.** `/admin/` shows "ExamLeaf at a glance" (today and the last 30 days: registrations, those with a confirmed email, attempts saved), what waits (teacher requests, account deletions, legal pages still holding placeholders) and, for those who may view orders, the shop block (orders to pack, on the way, reviews and quotations waiting, sales by day, most sold, running out). States: D, E ("No orders.", "None yet.", "Nothing is running out."), P (modules are listed by permission), S (8-hour session), U (the authenticator step). No loading state, no chart.

**Custom pages.** the customer page `/admin/shop/order/customer/<user>/` (account, orders, addresses, reviews, quotations, stock alerts, courses; `shop/admin/customer.html`), the Add order form for phone and school orders (`staff_order.html`), the action forms for shipping and offline payments (`action_form.html`, untouched since the pre-redesign commit), the quotation PDF (`/admin/shop/quoterequest/<pk>/quotation/`), and `/learn/preview/<clip>/` (section 3.1 G).

**Access by role** (probed with a user of each role: the change list for view, the add form for add; change and delete follow `roles.py`).

""")
w(tables["ADMIN"] + "\n")
w(f"""
Reading the table: ADMIN reaches everything except what only superusers may change (periodic tasks, groups, second factors, social apps: view only); CONTENT_EDITOR owns the books, papers, questions, legal pages, the catalogue structure and the revision course's content; SALES owns prices, stock, coupons, offers, shipping, orders, payments, refunds and reviews; SUPPORT can look up accounts, consent, deletions, orders, the SMS log and email suppression, verify teachers, and open a course by hand. A permission failure inside the admin renders the public site's 403 page.

### 3.3 REST API v1

`/api/v1/<path>` (URL-path versioned), JWT bearer or the website's session; JSON only; the OpenAPI schema is `/api/schema/` with Swagger at `/api/docs/` and Redoc at `/api/redoc/`. Anonymous callers get the catalogue; everything else needs a signed-in user whose email is confirmed. "Probe" lists the HTTP status the test client got as an anonymous caller and as a student (empty bodies for POST, so 400 means "reachable, the body was refused" and 401 means "sign in first"). Paths that appeared during the audit are marked in progress: the API is being brought to parity with the website for the app.

""")
w(tables["API"] + "\n")
w(f"""
### 3.4 allauth headless API

`/_allauth/app/v1/...` (token sessions, for the mobile app) and `/_allauth/browser/v1/...` (cookie sessions, for a browser client), plus `/_allauth/openapi.json` and `.yaml`. They are the library's JSON versions of the log-in, sign-up, code, password, second-factor, passkey and Google flows; the website's own pages do not call them, and their screens (and states) belong to whichever client is built on them. {g['headless']} patterns, {counts['headless_names']} operations. All of it is in progress (not in the last commit); `POST /api/v1/auth/exchange/` turns an app session into the REST API's JWT pair.

""")
w(tables["HEADLESS"] + "\n")

w("""
## 4. Proposed additions (not built)

Only what a journey above needs and the code does not do; each is tied to a gap or to evidence in the repository.

""")
w(prose.PROPOSED)

# --------------------------------------------------------------------------------------------------------------------
def c(page, width, key, variant="after"):
    r = (craft_after if variant == "after" else craft_before).get((page, width))
    return r.get(key) if r else None

def top_gaps():
    rows = []
    for page in ["cart (empty)", "privacy", "order lookup", "school orders", "shop", "home", "login", "signup", "book", "product", "solutions (logged out)", "404"]:
        rows.append((page, c(page, 1280, "headerToH1"), c(page, 1280, "h1ToNext"), c(page, 1280, "h1Font")))
    return rows

gaps_txt = "; ".join(f"{p} {a} px" for p, a, _, _ in top_gaps() if a is not None)
h1_fonts = collections.Counter(c(p, 1280, "h1Font") for p in ["shop", "cart (empty)", "privacy", "order lookup", "school orders", "book", "product", "404"])
shapes = {p: (c(p, 1280, "cards"), c(p, 1280, "cardShapes")) for p in ["book", "shop", "home", "product"]}
cart_footer = (c("cart (empty)", 1280, "footerHeight"), c("cart (empty)", 1280, "docHeight"))
import urllib.request
def main_text(path):
    html = urllib.request.urlopen("http://[::1]:8060" + path).read().decode()
    body = re.search(r"<main.*?</main>", html, flags=re.S).group(0)
    body = re.sub(r"<(script|style|svg)\b.*?</\1>", "", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
home_text = main_text("/")
n_deliv, n_qr = len(re.findall(r"(?i)deliver\w* (?:anywhere in|across) India", home_text)), len(re.findall("QR code", home_text))
h1_gaps = [c(p, 1280, "h1ToNext") for p in ["shop", "cart (empty)", "privacy", "order lookup", "school orders", "book", "product"] if c(p, 1280, "h1ToNext") is not None]
bengali_kb = round(sum(os.path.getsize(f"{REPO}/examleaf-web/static/fonts/{f}") for f in os.listdir(f"{REPO}/examleaf-web/static/fonts") if f.endswith("bengali.woff2")) / 1000)
bento_gap = c("home", 1280, "bentoGap")
sol375 = (c("solutions (logged out)", 375, "words"), c("solutions (logged out)", 375, "footerHeight"), c("solutions (logged out)", 375, "docHeight"))
lib_pages = counts.get('allauth_redesign', {}).get('layout', 0) + counts.get('allauth_redesign', {}).get('done via allauth elements', 0)
heights375 = {p: c(p, 375, "docHeight") for p in ["home", "shop", "signup", "login", "product"]}

w(f"""
## 5. What makes it feel generic

Observations from the screenshots in `screenshots/before/` (commit `9b4c3f2`, the pre-redesign site) and `screenshots/after/` (the tree at the snapshot), backed by measurements of the laid-out pages (headless Chrome, `craft.py`). The redesign has already fixed the plainest faults of the before: the system font (before: `system-ui`, and Times on the bare 404), one 48 rem column, two to four type sizes, no imagery but the covers, a 404 that was Django's default. What is left is mostly repetition and flatness, not default styling. Each row names the page, so the craft pass can act on it; file names are in `screenshots/`.

| # | Observation | Page (after screenshot) | Evidence | Move for the craft pass |
|---|---|---|---|---|
| 1 | **One card shape repeated.** The book page is a wall of 30 identical white cards; the shop's nine cards share two or three shapes; the home page's feature grid is four same-shaped icon-title-grey-paragraph cards, then three text-only offer cards | `/books/physics-2027/`, `/shop/` (`shop-1280-after`), `/` (`home-1280-after`, Q.1 and Q.4) | cards and distinct shapes at 1280: book {shapes['book'][0]} cards in {shapes['book'][1]} shape, shop {shapes['shop'][0]} in {shapes['shop'][1]}, home {shapes['home'][0]} in {shapes['home'][1]}, product {shapes['product'][0]} in {shapes['product'][1]} | Vary the anatomy by what the thing is: the book as a hero row, tiers as bands with their colour, papers as a compact index with done marks for a signed-in student; subject colour as a band on shop cards instead of a chip |
| 2 | **Missing or token imagery where the product is sold.** The three offer cards on the home page sell a printed book with no picture of it; the four Solutions books in the shop are a flat colour panel with the wordmark, which reads as an image that failed to load; the before shows the same flat panels, so the redesign restyled the placeholder without replacing it | `/` Q.4, `/shop/` | in the development data the four Solutions books have no cover image uploaded, so they get the placeholder every cover-less product gets; the Sample Papers covers exist as AVIF at 320 and 480 px | Real cover art for the Solutions books, or one deliberate typographic cover per subject (a big numeral and the subject colour) that looks designed, not missing; put a cover in each offer card |
| 3 | **Weak, uniform hierarchy.** Every page opens with the same H1 recipe ({', '.join(f'{k}' for k in h1_fonts)}) whether it is the shop, the cart, a legal page or a lookup form, and the H1 sits only {min(h1_gaps)} to {max(h1_gaps)} px above the first block | `/cart/`, `/orders/lookup/`, `/privacy/`, `/shop/school-orders/`, `/shop/` | H1 to first block: cart {c('cart (empty)', 1280, 'h1ToNext')} px, lookup {c('order lookup', 1280, 'h1ToNext')}, privacy {c('privacy', 1280, 'h1ToNext')}, shop {c('shop', 1280, 'h1ToNext')}. Before: 25.6 px at 375, 32 px at 1280, one weight | Two page-head patterns: transactional (compact H1, no lead) and editorial (breadcrumb, H1, lead); a larger step between H1 and the first block |
| 4 | **Inconsistent top spacing.** Header to H1 is {gaps_txt} at 1280 | `/cart/` (`cart-empty-1280-after`) against `/product`, `/s/PHY-E01/`, `/404` | the numbers in the row | One token for the space under the header, and let breadcrumbs and heroes add to it deliberately |
| 5 | **Empty and error screens are one dashed card.** Cart empty, 404, 403, 429 and offline share an icon, a centred title and one button. The cart prints its H1 *Your cart* left-aligned above a centred card that says *Your cart is empty.*, the same words twice, and the two do not align | `/cart/` (`cart-empty-1280-after`), `/this-page-does-not-exist/` (`404-1280-after`) | Before: the cart was one sentence, the 404 Django's default | Drop the duplicate heading; give the empty cart something to do (the two bestsellers, as the 404 shows books) |
| 6 | **The highest-intent page is the plainest.** A student holding the book scans the QR and lands on a navy header card and one white card with two buttons and one sentence | `/s/PHY-E01/` logged out (`solutions-logged-out-375-after`) | {sol375[0]} words in `main`; {sol375[2]} px tall at 375 of which the footer is {sol375[1]}; before: the same structure in plain text | Show the first question and the marking table behind the wall, the promise (free, once, every QR) in three short lines, and a Log in with a code shortcut; the `next` handling is already right |
| 7 | **Copy that fits any bookshop.** *Delivered anywhere in India* (or *across India*) appears {n_deliv} times in the home page's main content, *QR code* {n_qr} times; the final call to action reads *Start with one paper this week*; the 404 *We could not find that page*; the library pages *Bad Token* and *Account Inactive* | `/` (hero trust list, Q.1 trust strip, Q.3 step 1, final call to action), {lib_pages} allauth pages | phrase counts in the rendered `main` of `/` | One voice pass in the register of an Assam Class 12 student and parent: name the exam, quote what a marking step looks like, say it once; override the library pages |
| 8 | **One language.** No Assamese anywhere on the site, though two Bengali-script font subsets ({bengali_kb} KB) are declared and never fetched because no page has such text | whole site | `static/fonts/hind-siliguri-*-bengali.woff2`; browser-observed fonts: four Latin files only | A line of Assamese in the hero and the QR wall, or a language toggle for the wall and the FAQ; test the 1.7 line height on real text |
| 9 | **Dead space inside components.** The home page's big *30 full papers* card has {bento_gap} px of empty white between its text and the tier bars; the product page's Easy, Medium and Hard cards carry a title and nothing else; the FAQ and the Details table each stop at two thirds of the page width and leave the right third empty | `/` (`home-1280-after`, Q.1), `/shop/physics-sample-papers-2027/` (`product-physics-1280-after`, Q.1 and Q.2) | the gap is measured; the rest is visible in the full-page captures (`full/after/`) | Size cards to their content, or fill them: the tier's marks and an example question |
| 10 | **Chrome that never changes.** The same four-column footer and the same brand paragraph (the meta description word for word) on every page, even on the short transactional ones | `/cart/` (`cart-empty-1280-after`) | footer {cart_footer[0]} px of a {cart_footer[1]} px page | A slim footer on cart, checkout and payment; keep the full one on content pages |
| 11 | **Only the covers are pictures.** No photograph or drawing of a phone scanning the QR code, a printed solutions page, a marked answer sheet; *How it works* is a good CSS mock but static | `/` Q.3 | `static/img/` holds covers, icons and `og-default.jpg` only | One illustration set (scan, solve, check) in the same stroke style, or a device frame around the mock |
| 12 | **Long on phones.** Home is {heights375['home']} px tall at 375 (about {round((heights375['home'] or 0) / 812, 1)} screens), shop {heights375['shop']}, product {heights375['product']}, register {heights375['signup']} | `/` (`home-375-after`), `/shop/`, `/account/signup/` | document heights at 375 | Collapse Q.1 and the FAQ on phones; keep one trust line |

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

- **Routes.** `django.urls.get_resolver()` walked from `manage.py shell` (a dump of {sum(g.values())} patterns), joined to hand-written annotations (`matrix_data.py`); a route without an annotation fails the build (none did). The REST rows come from `manage.py spectacular` (the OpenAPI schema), the admin rows from `admin.site._registry`.
- **Who may use it.** Read from the views (`LoginRequiredMixin`, `login_required`, `staff_member_required`, `permission_classes`, `shop_open`, `visible_order`) and confirmed by a probe: a Django test client, on a copy of the dev database with the project's media folder pointed elsewhere, asked each route as an anonymous visitor, a student, a student with the parent's consent pending, a student just signed in, a member of staff of each of the four roles (with an authenticator app, so the middleware lets them in), and, for the API, as anonymous, student and admin (976 requests). The copy's orders, addresses and attempts were made with the project's factories; Razorpay was stubbed.
- **Redesign.** The HTML each route returned was searched for the classes of `direction.md` section 3, minus the classes the header and footer bring to every page, and for the {len(json.load(open(f"{SCR}/css-classes.json"))["legacy"])} class names that exist in the pre-redesign stylesheet and no longer in the new one. The static scan of `templates/` (own classes, included partials, parents except `base.html`) gives the same verdicts: no page template still uses a pre-redesign class except the one named in section 0.
- **States.** From reading each template and view; the flows (sign-up with a code, code log-in, password log-in, save marks) were walked with the test client.
- **Screenshots and measurements.** Headless Chrome 154 driven over the DevTools protocol against two servers on `[::1]:8060` (the tree) and `[::1]:8070` (commit `9b4c3f2` in a git worktree, run with the current virtualenv, the current database copy and a copy of `media/products`), settings as in development but with `DEBUG` switched off at run time so that the 404 is the site's own page and the debug toolbar stays out of the pictures. The Claude browser pane could not open a tab of its own (its tab limit was reached by other work), so the pane was left alone.
""")
text = "".join(out)
open(f"{DOCS}/coverage-matrix.md", "w").write(text)
print("coverage-matrix.md written:", len(text.splitlines()), "lines,", len(text), "bytes")
