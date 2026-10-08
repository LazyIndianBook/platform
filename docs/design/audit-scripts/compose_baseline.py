"""Writes docs/design/baseline.md from the logs of baseline.sh and the weight measurements."""
import json, os, re, subprocess
SCR = os.path.dirname(os.path.abspath(__file__))
REPO = "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12"
DOCS = f"{REPO}/docs/design"
L = f"{SCR}/logs"
J = lambda n: json.load(open(f"{SCR}/{n}"))
snap = J("snapshot.json")
read = lambda n: open(f"{L}/{n}").read() if os.path.exists(f"{L}/{n}") else ""

RUN_A = {  # the first run, from the output kept in the session (its log files were overwritten by the second run)
    "started": "2026-10-08T06:14:02Z", "finished": "2026-10-08T06:16:06Z", "tree": "HEAD `4e30e59` with 53 uncommitted paths (the redesign stages 2a and 2b); another agent committed exactly that as `ba0b9dd` at 06:15Z, during the run",
    "rows": {
        "pytest": ("pass", "345 passed, 5 skipped, 33 warnings, 23 subtests passed in 116.05 s", "118.9 s"),
        "ruff-check": ("FAIL", "2 errors: E501 line too long (121 > 120) at `shop/services.py:464`; I001 unsorted imports at `shop/test_api.py:5` (fixable)", "0.1 s"),
        "ruff-format": ("FAIL", "2 files would be reformatted (`shop/services.py`, `shop/test_api.py`), 165 already formatted", "0.0 s"),
        "check-deploy": ("pass", "0 errors, 2 warnings: security.W005, security.W021 (HSTS includeSubDomains and preload, both off on purpose)", "1.8 s"),
        "makemigrations": ("pass", "No changes detected", "1.6 s"),
        "spectacular": ("pass", "valid, no warnings", "1.6 s"),
    },
}

def parse_run(folder):
    r = lambda n: open(f"{folder}/{n}").read() if os.path.exists(f"{folder}/{n}") else ""
    summary = {}
    for line in r("summary.tsv").splitlines():
        name, rc, secs = line.split("\t")
        summary[name] = (int(rc), float(secs))
    ok = lambda n: "pass" if n in summary and summary[n][0] == 0 else "FAIL"
    t = lambda n: f"{summary[n][1]:.1f} s" if n in summary else "-"
    pt = [l for l in r("pytest.out").splitlines() if re.search(r"\d+ passed", l)]
    pytest_line = pt[-1].strip(" =") if pt else "(no summary line)"
    failed = re.findall(r"^FAILED (\S+)", r("pytest.out"), flags=re.M)
    ruff = r("ruff-check.out")
    errs = re.findall(r"^(\w+\d+)\s+(?:\[\*\]\s+)?(.+)\n\s+-->\s+(\S+)", ruff, flags=re.M)
    found = (re.search(r"Found (\d+) errors?", ruff) or [None, "0"])[1]
    fmt = r("ruff-format.out")
    ffiles = list(dict.fromkeys(re.findall(r"^\s+-->\s+(\S+?):", fmt, flags=re.M)))
    fline = [l for l in fmt.splitlines() if "would be reformatted" in l and "file" in l]
    dw = list(dict.fromkeys(re.findall(r"\((security\.\w+)\)", r("check-deploy.err"))))
    spec_ok = summary.get("spectacular", (1, 0))[0] == 0
    return {
        "started": r("started.txt").strip(), "finished": r("finished.txt").strip(),
        "rows": {
            "pytest": (ok("pytest"), pytest_line + ("; failing: " + ", ".join(f"`{x}`" for x in failed) if failed else ""), t("pytest")),
            "ruff-check": (ok("ruff-check"), f"{found} errors: " + "; ".join(f"{c} {m} at `{p}`" for c, m, p in errs), t("ruff-check")),
            "ruff-format": (ok("ruff-format"), (fline[-1].strip() if fline else "all formatted") + (" (" + ", ".join(f"`{x}`" for x in ffiles) + ")" if ffiles else ""), t("ruff-format")),
            "check-deploy": (ok("check-deploy"), f"0 errors, {len(dw)} warnings: " + ", ".join(dw) + " (HSTS includeSubDomains and preload, both off on purpose)", t("check-deploy")),
            "makemigrations": (ok("makemigrations"), r("makemigrations.out").strip() or "(no output)", t("makemigrations")),
            "spectacular": (ok("spectacular"), "valid, no warnings" if spec_ok else "FAILED: " + r("spectacular.err").strip()[:200], t("spectacular")),
        },
        "dirty_start": r("uncommitted-at-start.txt").strip(),
    }

RUN_B = parse_run(f"{L}/run2")
CMDS = [
    ("pytest", "`.venv/bin/python -m pytest -q -p no:cacheprovider`"),
    ("ruff-check", "`.venv/bin/ruff check .`"),
    ("ruff-format", "`.venv/bin/ruff format --check .`"),
    ("check-deploy", "`manage.py check --deploy` with `DEBUG=0`, a random 50-character `SECRET_KEY`, `ALLOWED_HOSTS=examleaf.in`, `SITE_URL=https://examleaf.in`, `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`"),
    ("makemigrations", "`manage.py makemigrations --check --dry-run`"),
    ("spectacular", "`manage.py spectacular --validate --fail-on-warn --file /dev/null`"),
]
started = RUN_B["started"]

def kb(n):
    return f"{n / 1000:.1f} KB"

out = []
w = out.append
w(f"""# ExamLeaf website: baseline

What the site was, measured, before the craft pass. Taken {snap['date']}.

**Tree.** The audit began on commit `{snap['start_head']}` with {snap['dirty_start']} uncommitted paths; at 11:45 IST another agent committed that work as `{snap['head']}`; there are {snap['dirty_end']} uncommitted paths now (git HEAD `{snap['head']}`). Other agents were editing throughout (the redesign stages, the API's parity work, an SMS-limits migration, the stylesheet split), so the checks were run twice, and the page weights and screenshots were taken later on the live tree, with its drift: `site.css` was {', '.join(snap['css_sizes'])} bytes at the moments it was read.

## 1. Checks

Run from `examleaf-web/` with its virtualenv (Python 3.14, Django 6.1). **Run A** is the tree as found ({RUN_A['started']}, {RUN_A['tree']}); **Run B** is the same commands {RUN_B['started']} on the tree as the audit ended (HEAD `{snap['head']}` with {RUN_B['dirty_start']} uncommitted paths of work in progress). The machine was busy with other agents' test runs, so times are upper bounds.

| Check | Run A: result | Run A: detail | Run A: time | Run B: result | Run B: detail | Run B: time |
|---|---|---|---|---|---|---|
""")
for key, cmd in CMDS:
    ra, rb = RUN_A["rows"][key], RUN_B["rows"][key]
    w(f"| {cmd} | {ra[0]} | {ra[1]} | {ra[2]} | {rb[0]} | {rb[1]} | {rb[2]} |\n")
w(f"""
Reading them. Run A, the baseline proper: the tests are green; the two lint findings are one over-long line and one unsorted import block in files of the checkpoint that was being committed; `check --deploy` has no errors and two warnings that are decisions; migrations and the OpenAPI schema are in step. Run B is the same tree plus other agents' unfinished work: one new test fails (`accounts/test_parent_link.py`, a feature in progress: the parent's link limited to three a day), the lint findings grew to four (three over-long lines and one `DJ007` in `learn/uploads.py`, plus `ruff format` flags three files, one of them a Markdown file), and `ops/migrations/0005_sms_limits.py` (untracked; adds a column to `ops_smslog`) means a database copy made before it fails on the SMS log page of the admin until it is migrated. Neither run found anything wrong with what was in the last commit.

## 2. Page weights

Five pages: `/`, `/shop/`, the Physics Sample Papers product page, `/s/PHY-E01/` logged out (the register wall), and `/account/login/`. Sizes are bytes as served (no compression by the development server) with gzip level 9 beside HTML and CSS, which is what production's Caddy (`encode zstd gzip`) sends. 1 KB = 1000 bytes.

### 2.1 What the HTML refers to, fetched with plain HTTP (the tree, `[::1]:8060`)

Each file the page names is fetched once: the stylesheet, the scripts, the preloaded fonts, one icon, the manifest, and for images the smallest and the largest candidate of each picture (a phone at 2x takes the larger). Fonts: *preloaded* are the two the HTML preloads; *declared* are all six `@font-face` files of the stylesheet (four Latin, two Bengali-script), of which a page fetches only the faces its text uses.

""")
A, B = J("weights-after.json"), J("weights-before.json")
def inv_table(data):
    out = ["| Page | HTML | HTML gzip | CSS | CSS gzip | JS | Fonts preloaded | Fonts declared | Images (smallest to largest) | Requests |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in data:
        im = r["images"]
        out.append(f"| {r['name']} | {r['html']:,} | {r['html_gz']:,} | {r['css']['bytes']:,} | {r['css']['gz']:,} | {r['js']['bytes']:,} ({r['js']['files']}) | {r['fonts']['preloaded_bytes']:,} ({r['fonts']['preloaded_files']}) | {r['fonts']['declared_bytes']:,} ({r['fonts']['declared_files']}) | {im['bytes_modern_smallest']:,} to {im['bytes_modern_largest']:,} ({im['img_elements']} image{'s' if im['img_elements'] != 1 else ''}) | {r['requests_inventory']} |")
    return "\n".join(out)
w(inv_table(A) + "\n\n")
w("Requests = the HTML + stylesheet + scripts + preloaded fonts + one icon + the manifest + each distinct image once. No page loads anything from another host except `/s/<code>/` signed in (KaTeX from jsDelivr, not counted here: the logged-out page is the one measured).\n\n")
w("### 2.2 What headless Chrome fetches (cold cache, load plus 1.5 s, then scrolled to the bottom)\n\nThe numbers a visitor's browser actually pays: the fonts it needs for the text on the page, the image it picks from each `srcset`, lazy images after the scroll. *Other* is the favicon, the manifest and the service worker script. Body bytes, as decoded; the site's service worker is bypassed, so every request really went to the server.\n\n")
C = J("weights-cdp-after-before.json")
def cdp_table(variant):
    out = ["| Page | Viewport | Requests | HTML | CSS | JS | Fonts | Images | Other | Total |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in C:
        if r["variant"] != variant:
            continue
        s = r["scrolled"]
        fmt = lambda k: f"{s[k]['bytes']:,} ({s[k]['n']})"
        out.append(f"| {r['page']} | {r['view'].split(' ')[0]} {r['view'].split(' ')[1]} | {s['total']['n']} | {fmt('html')} | {fmt('css')} | {fmt('js')} | {fmt('font')} | {fmt('image')} | {fmt('other')} | {s['total']['bytes']:,} |")
    return "\n".join(out)
w(cdp_table("after") + "\n\n")
shop_phone = next((r for r in C if r["variant"] == "after" and r["page"] == "shop" and r["view"].startswith("phone")), None)
if shop_phone:
    w(f"On the phone the shop's lazy images arrive with the scroll: {shop_phone['initial']['total']['n']} requests and {shop_phone['initial']['total']['bytes']:,} bytes at load, {shop_phone['scrolled']['total']['n']} and {shop_phone['scrolled']['total']['bytes']:,} after scrolling.\n\n")
w("### 2.3 The same pages before the redesign (commit `9b4c3f2`, `[::1]:8070`)\n\n")
w(inv_table(B) + "\n\n")
w(cdp_table("before") + "\n\n")
# deltas
def tot(variant, page, view="desktop"):
    r = next((r for r in C if r["variant"] == variant and r["page"] == page and r["view"].startswith(view)), None)
    return r["scrolled"]["total"] if r else None
def delta_row(page):
    a, b = tot("after", page), tot("before", page)
    return f"| {page} | {b['n']} | {b['bytes']:,} | {a['n']} | {a['bytes']:,} | {a['bytes'] - b['bytes']:+,} |"
w("### 2.4 Before and after, browser-observed, desktop\n\n| Page | Requests before | Bytes before | Requests after | Bytes after | Change in bytes |\n|---|---|---|---|---|---|\n")
for p in ["home", "shop", "product", "solutions (logged out)", "login"]:
    w(delta_row(p) + "\n")
def less(page):
    diff = tot("before", page)["bytes"] - tot("after", page)["bytes"]
    return f"{abs(diff):,} bytes {'less' if diff > 0 else 'more'}"
png_a = A[1]["images"]["png_in_markup"]
png_note = ("Every cover is a `<picture>` with AVIF and WebP sources and the original PNG (" + ", ".join(png_a) + ") as the fallback, so only a browser without AVIF and WebP downloads the 176 KB file; the headless Chrome used here takes the AVIF.") if png_a else "The shop's covers are served as AVIF as well."
flat_after, flat_before = tot("after", "solutions (logged out)")["bytes"], tot("before", "solutions (logged out)")["bytes"]
fonts_a = next(r for r in C if r["variant"] == "after" and r["page"] == "home" and r["view"].startswith("desktop"))["scrolled"]["font"]
css_a = A[0]["css"]["bytes"]; css_b = B[0]["css"]["bytes"]
w(f"""
What the numbers say. The stylesheet grew from {css_b:,} to {css_a:,} bytes ({B[0]['css']['gz']:,} to {A[0]['css']['gz']:,} gzipped; the shop and account pages add another 5 to 6 KB of `shop.css` or `account.css`), and one {A[0]['js']['bytes'] / 1000:.1f} KB script and four Latin font files ({fonts_a['bytes']:,} bytes) arrived: a page with no pictures, such as the register wall, now weighs {flat_after / 1000:.0f} KB against {flat_before / 1000:.0f} KB, about {(flat_after - flat_before) / 1000:.0f} KB more of fixed weight on every page. In return the covers went from PNG (about 176 KB each, 706 KB for the four on the home page) to AVIF at 320 px (about 35 KB each): on a desktop, with the whole page scrolled, the home page carries {less('home')} and the shop {less('shop')} than before. {png_note}

## 3. How this was measured

- `weights.py`: `urllib` fetches of the HTML and of everything it names (links, scripts, `<img>`, `<picture>` and `srcset`), and of the fonts and images the stylesheet names; the same code against both servers.
- `weights_cdp.py`: headless Chrome 154 over the DevTools protocol, one fresh tab per page and viewport (1280×900 at 1x; 375×812 at 2x with touch), cache disabled, network events summed by type.
- Servers: the tree on `[::1]:8060` and commit `9b4c3f2` (a git worktree, run with the current virtualenv) on `[::1]:8070`; development settings with `DEBUG` switched off at run time (so error pages are the site's own and the debug toolbar, about 30 KB of markup and several more requests on every page, stays out of the numbers); a copy of the development database for both.
- The browser capture bypasses the site's service worker on purpose: it serves static files cache-first under a name that does not change while the file names are not hashed (development, or `DEBUG` off without `collectstatic`), which showed a stale stylesheet in an earlier capture. Production's hashed names avoid this.
- The checks in section 1 are `baseline.sh`; the git state was read before and after.
""")
open(f"{DOCS}/baseline.md", "w").write("".join(out))
print("baseline.md written", sum(len(x) for x in out), "bytes")
