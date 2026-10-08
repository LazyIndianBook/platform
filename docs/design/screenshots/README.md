# Screenshots: before and after

Eight pages at two sizes, before the redesign and now. Taken 8 October 2026, 12:54 IST.

The atlas, every page at both sizes (signed out, as a student, as staff, with the Django admin), as one PDF: [`../examleaf-pages-2026-10-09.pdf`](../examleaf-pages-2026-10-09.pdf) (not in git, like every PDF under `docs/`). Regenerate it with [`../atlas/capture.mjs`](../atlas/capture.mjs) (the pictures; [`../atlas/seed.py`](../atlas/seed.py) makes the temporary accounts and rows, [`../atlas/manifest.json`](../atlas/manifest.json) is what the last run took) and [`../atlas/build.py`](../atlas/build.py) (the PDF); the header of `capture.mjs` says how to run them.

- **before** is the site as of commit `9b4c3f2` (Phase 3b, the last commit before the redesign began), run from a git worktree with the current virtualenv, a copy of the current development database and a copy of `media/products` (the old code reads covers from there), on `[::1]:8070`.
- **after** is the working tree (HEAD `ba0b9dd` plus uncommitted work by other agents; `site.css` 54,392 bytes, with account.css, shop.css, staff.css and print.css beside it), on `[::1]:8060`, with its own copy of the same database, migrated to the tree's schema. The tree was still being edited: a later capture may differ.
- Both servers use development settings with `DEBUG` switched off at run time, so that error pages are the site's own and the debug toolbar is not in the picture.
- Headless Chrome 154, one fresh tab per picture, cache off, fonts loaded and 1.5 s of waiting for the entry animations. Phone: **375×812** viewport at 2x with touch (the JPEGs are 750×1624). Desktop: **1280×900** at 1x. JPEG quality 80. Each picture is the first screen only (the viewport); the whole pages are in `full/before/` and `full/after/` (1x, quality 65) for reading below the fold.
- The "before" site predates several features, so some pairs differ by feature as well as by design: no phone log-in, no pictures field, no branded error pages, no school-order page.

File names: `<page>-<width>-<before|after>.jpg`.

| Page | URL | 375 before | 375 after | 1280 before | 1280 after | Before | After |
|---|---|---|---|---|---|---|---|
| The home page | `/` | [`home-375-before.jpg`](before/home-375-before.jpg) | [`home-375-after.jpg`](after/home-375-after.jpg) | [`home-1280-before.jpg`](before/home-1280-before.jpg) | [`home-1280-after.jpg`](after/home-1280-after.jpg) | A title, one sentence, four covers | Dark hero with the fanned covers, Q.1 to Q.5 sections, FAQ, call to action |
| The catalogue | `/shop/` | [`shop-375-before.jpg`](before/shop-375-before.jpg) | [`shop-375-after.jpg`](after/shop-375-after.jpg) | [`shop-1280-before.jpg`](before/shop-1280-before.jpg) | [`shop-1280-after.jpg`](after/shop-1280-after.jpg) | Nine product cards (the bundle first), the Solutions books as flat panels | Featured bundle, subject tabs, nine cards |
| The Physics Sample Papers product page | `/shop/physics-sample-papers-2027/` | [`product-physics-375-before.jpg`](before/product-physics-375-before.jpg) | [`product-physics-375-after.jpg`](after/product-physics-375-after.jpg) | [`product-physics-1280-before.jpg`](before/product-physics-1280-before.jpg) | [`product-physics-1280-after.jpg`](after/product-physics-1280-after.jpg) | Cover, price, copies, a list | Cover, price, buy form, what is inside, details, reviews |
| The cart with nothing in it (a new session) | `/cart/` | [`cart-empty-375-before.jpg`](before/cart-empty-375-before.jpg) | [`cart-empty-375-after.jpg`](after/cart-empty-375-after.jpg) | [`cart-empty-1280-before.jpg`](before/cart-empty-1280-before.jpg) | [`cart-empty-1280-after.jpg`](after/cart-empty-1280-after.jpg) | One sentence and a link | Empty-state card |
| Log in | `/account/login/` | [`login-375-before.jpg`](before/login-375-before.jpg) | [`login-375-after.jpg`](after/login-375-after.jpg) | [`login-1280-before.jpg`](before/login-1280-before.jpg) | [`login-1280-after.jpg`](after/login-1280-after.jpg) | allauth's Sign In form | Code by SMS first (development has SMS on), email code, passkey, password in a fold |
| Register | `/account/signup/` | [`signup-375-before.jpg`](before/signup-375-before.jpg) | [`signup-375-after.jpg`](after/signup-375-after.jpg) | [`signup-1280-before.jpg`](before/signup-1280-before.jpg) | [`signup-1280-after.jpg`](after/signup-1280-after.jpg) | allauth's Sign Up form | Numbered fieldsets and the privacy aside |
| The QR landing page, logged out (the register wall) | `/s/PHY-E01/` | [`solutions-logged-out-375-before.jpg`](before/solutions-logged-out-375-before.jpg) | [`solutions-logged-out-375-after.jpg`](after/solutions-logged-out-375-after.jpg) | [`solutions-logged-out-1280-before.jpg`](before/solutions-logged-out-1280-before.jpg) | [`solutions-logged-out-1280-after.jpg`](after/solutions-logged-out-1280-after.jpg) | Heading, one sentence, two buttons | QR card with its seal, then a card with two buttons |
| A page that does not exist | `/this-page-does-not-exist/` | [`404-375-before.jpg`](before/404-375-before.jpg) | [`404-375-after.jpg`](after/404-375-after.jpg) | [`404-1280-before.jpg`](before/404-1280-before.jpg) | [`404-1280-after.jpg`](after/404-1280-after.jpg) | Django's default Not Found (the branded 404 arrived after this commit) | The site's own 404 with the four books |

Whole-page versions: `full/before/<name>.jpg` and `full/after/<name>.jpg`, same names. `after-craft/` beside them is the craft pass's own set (other pages, PNG), not part of this audit.

How they were made: `shots.py` in the audit's scratch folder (a small DevTools-protocol client, `cdp.py`); it can be re-run against any two servers.

## The Next.js frontend (Phase 8D review half)

Ten pages at two sizes, the same ten as the Django craft pass's `after-craft/` set (`<page>-375.png`, `<page>-1280.png`), for the before and after of the move to `examleaf-frontend/`. Taken 8 October 2026, 17:01 to 17:03 IST, in [`nextjs/`](nextjs/).

- **What was captured.** The production build of `examleaf-frontend/` (Next.js 16.4, the standalone output, made at 16:38 from the tree at commit `b10bde1`) on `localhost:3003`, with the Django backend on 8103 and its development database (the four books of 30 papers, nine products with 24 to 25 copies each). Headless Chrome 154 through the DevTools protocol, one fresh browser context per picture, fonts loaded and 1.5 s of waiting. Phone: **375 × 812 viewport at 2x** (the PNGs are 750 × 1624). Desktop: **1280 × 800 at 1x**. Each picture is the first screen only (the viewport), PNG, as `after-craft/`.
- **Who was signed in**, as in the Django set: the five public pages (home, shop, product, login, 404) anonymous; the others (account, cart, checkout, order, solutions) as a temporary non-staff student who had one Physics Sample Papers in the cart, one saved address (made by placing the unpaid order) and that order, awaiting payment. The student and everything it made were deleted afterwards.
- **What differs from the Django set because of the data, not the design.** The Django account picture is another account (a name in Assamese script, a shipped order); here the account is "Review Temp" with no marks and one order awaiting payment (`EL-2026-000003`: the timeline shows Ordered only, with "Cancel the order"). The Django checkout picture is a guest's form; here the signed-in student's saved address is selected (Razorpay is not configured in development, so the order page is the closest "order" state: "Your order is awaiting payment").

| Page | URL | 375 | 1280 | State |
|---|---|---|---|---|
| The home page | `/` | [`home-375.png`](nextjs/home-375.png) | [`home-1280.png`](nextjs/home-1280.png) | anonymous |
| The catalogue | `/shop/` | [`shop-375.png`](nextjs/shop-375.png) | [`shop-1280.png`](nextjs/shop-1280.png) | anonymous; at 375 px the subject tabs run past the screen's right edge and the page scrolls sideways (the layout is 583 px wide: accessibility audit F2) |
| The Physics Sample Papers product page | `/shop/physics-sample-papers-2027/` | [`product-375.png`](nextjs/product-375.png) | [`product-1280.png`](nextjs/product-1280.png) | anonymous |
| Log in | `/account/login/` | [`login-375.png`](nextjs/login-375.png) | [`login-1280.png`](nextjs/login-1280.png) | anonymous (SMS code first; development has SMS on) |
| A page that does not exist | `/this-page-does-not-exist/` | [`404-375.png`](nextjs/404-375.png) | [`404-1280.png`](nextjs/404-1280.png) | anonymous |
| My account | `/account/` | [`account-375.png`](nextjs/account-375.png) | [`account-1280.png`](nextjs/account-1280.png) | signed in; at 375 px the side navigation is a scrolling strip of chips |
| The cart | `/cart/` | [`cart-375.png`](nextjs/cart-375.png) | [`cart-1280.png`](nextjs/cart-1280.png) | signed in, one book |
| Checkout | `/checkout/` | [`checkout-375.png`](nextjs/checkout-375.png) | [`checkout-1280.png`](nextjs/checkout-1280.png) | signed in, the saved address selected |
| An order | `/account/orders/EL-2026-000003/` | [`order-375.png`](nextjs/order-375.png) | [`order-1280.png`](nextjs/order-1280.png) | signed in, awaiting payment |
| The solutions | `/s/PHY-E01/` | [`solutions-375.png`](nextjs/solutions-375.png) | [`solutions-1280.png`](nextjs/solutions-1280.png) | signed in |

Side by side with the Django craft pass: `after-craft/<page>-<width>.png` (Django) and `nextjs/<page>-<width>.png` (Next.js) have the same names. At 375 px the pairs are close to identical in layout, type and colour for home, shop (apart from the tabs), product, login, 404 and solutions; the cart differs in detail (copies change at once, so there is no "Update copies" button, and the lines are not boxed), and the rest differ by the data above and by the account's chip strip. The Lighthouse and accessibility files give the numbers behind the pictures: [audit-nextjs-lighthouse.md](../audit-nextjs-lighthouse.md), [audit-nextjs-accessibility.md](../audit-nextjs-accessibility.md).

How they were made: a small Puppeteer script ([`shots.mjs`](../audit-scripts/nextjs/shots.mjs), with the set-up in [its README](../audit-scripts/nextjs/README.md)) driving headless Chrome against the running servers; it can be re-run against any build.

The complete page atlas PDF (1,195 pages, 54 MB) is attached to the GitHub release `pages-atlas-2026-10-09` of this repository rather than committed; `docs/design/atlas/` regenerates it.
