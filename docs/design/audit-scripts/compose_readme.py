"""Writes docs/design/screenshots/README.md."""
import json, os
SCR = os.path.dirname(os.path.abspath(__file__))
DOCS = "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12/docs/design"
snap = json.load(open(f"{SCR}/snapshot.json"))
rep = json.load(open(f"{SCR}/shots/report-before-after.json"))
by = {(r["variant"], r["page"], r["view"].split("@")[0].split("x")[0]): r for r in rep}
PAGES = [
    ("home", "/", "The home page", "A title, one sentence, four covers", "Dark hero with the fanned covers, Q.1 to Q.5 sections, FAQ, call to action"),
    ("shop", "/shop/", "The catalogue", "Nine product cards (the bundle first), the Solutions books as flat panels", "Featured bundle, subject tabs, nine cards"),
    ("product-physics", "/shop/physics-sample-papers-2027/", "The Physics Sample Papers product page", "Cover, price, copies, a list", "Cover, price, buy form, what is inside, details, reviews"),
    ("cart-empty", "/cart/", "The cart with nothing in it (a new session)", "One sentence and a link", "Empty-state card"),
    ("login", "/account/login/", "Log in", "allauth's Sign In form", "Code by SMS first (development has SMS on), email code, passkey, password in a fold"),
    ("signup", "/account/signup/", "Register", "allauth's Sign Up form", "Numbered fieldsets and the privacy aside"),
    ("solutions-logged-out", "/s/PHY-E01/", "The QR landing page, logged out (the register wall)", "Heading, one sentence, two buttons", "QR card with its seal, then a card with two buttons"),
    ("404", "/this-page-does-not-exist/", "A page that does not exist", "Django's default Not Found (the branded 404 arrived after this commit)", "The site's own 404 with the four books"),
]
lines = [f"""# Screenshots: before and after

Eight pages at two sizes, before the redesign and now. Taken {snap['date']}.

- **before** is the site as of commit `9b4c3f2` (Phase 3b, the last commit before the redesign began), run from a git worktree with the current virtualenv, a copy of the current development database and a copy of `media/products` (the old code reads covers from there), on `[::1]:8070`.
- **after** is the working tree (HEAD `{snap['head']}` plus uncommitted work by other agents; `site.css` {snap['css_final']}), on `[::1]:8060`, with its own copy of the same database, migrated to the tree's schema. The tree was still being edited: a later capture may differ.
- Both servers use development settings with `DEBUG` switched off at run time, so that error pages are the site's own and the debug toolbar is not in the picture.
- Headless Chrome 154, one fresh tab per picture, cache off, fonts loaded and 1.5 s of waiting for the entry animations. Phone: **375×812** viewport at 2x with touch (the JPEGs are 750×1624). Desktop: **1280×900** at 1x. JPEG quality 80. Each picture is the first screen only (the viewport); the whole pages are in `full/before/` and `full/after/` (1x, quality 65) for reading below the fold.
- The "before" site predates several features, so some pairs differ by feature as well as by design: no phone log-in, no pictures field, no branded error pages, no school-order page.

File names: `<page>-<width>-<before|after>.jpg`.

| Page | URL | 375 before | 375 after | 1280 before | 1280 after | Before | After |
|---|---|---|---|---|---|---|---|
"""]
for slug, url, name, b, a in PAGES:
    cells = []
    for w in ("375", "1280"):
        for v in ("before", "after"):
            cells.append(f"[`{slug}-{w}-{v}.jpg`]({v}/{slug}-{w}-{v}.jpg)")
    lines.append(f"| {name} | `{url}` | " + " | ".join(cells) + f" | {b} | {a} |\n")
lines.append("""
Whole-page versions: `full/before/<name>.jpg` and `full/after/<name>.jpg`, same names. `after-craft/` beside them is the craft pass's own set (other pages, PNG), not part of this audit.

How they were made: `shots.py` in the audit's scratch folder (a small DevTools-protocol client, `cdp.py`); it can be re-run against any two servers.
""")
open(f"{DOCS}/screenshots/README.md", "w").write("".join(lines))
print("README written")
