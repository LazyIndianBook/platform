# Screenshots: before and after

Eight pages at two sizes, before the redesign and now. Taken 8 October 2026, 12:54 IST.

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
