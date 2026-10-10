# ExamLeaf website: baseline

![Component](../assets/badges/component-website.svg) ![Status](../assets/badges/status-archive.svg) ![For developers](../assets/badges/audience-developers.svg)

What the Django site was, measured, before the craft pass of 8 October 2026: the checks, the page weights before and
after the first redesign, and how they were measured. It is kept as a record; the site it measured was replaced by the
Next.js frontend in Phase 8.

What the site was, measured, before the craft pass. Taken 8 October 2026, 12:54 IST.

**Tree.** The audit began on commit `4e30e59` with 52 uncommitted paths; at 11:45 IST another agent committed that work as `ba0b9dd`; there are 138 uncommitted paths now (git HEAD `ba0b9dd`). Other agents were editing throughout (the redesign stages, the API's parity work, an SMS-limits migration, the stylesheet split), so the checks were run twice, and the page weights and screenshots were taken later on the live tree, with its drift: `site.css` was 78,312, 81,991, 81,909, 54,098, 54,116 bytes at the moments it was read.

## 1. Checks

Run from `examleaf-web/` with its virtualenv (Python 3.14, Django 6.1). **Run A** is the tree as found (2026-10-08T06:14:02Z, HEAD `4e30e59` with 53 uncommitted paths (the redesign stages 2a and 2b); another agent committed exactly that as `ba0b9dd` at 06:15Z, during the run); **Run B** is the same commands 2026-10-08T07:04:59Z on the tree as the audit ended (HEAD `ba0b9dd` with 112 uncommitted paths of work in progress). The machine was busy with other agents' test runs, so times are upper bounds.

| Check | Run A: result | Run A: detail | Run A: time | Run B: result | Run B: detail | Run B: time |
|---|---|---|---|---|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider` | pass | 345 passed, 5 skipped, 33 warnings, 23 subtests passed in 116.05 s | 118.9 s | FAIL | 1 failed, 413 passed, 7 skipped, 34 warnings, 23 subtests passed in 140.40s (0:02:20); failing: `accounts/test_parent_link.py::test_one_parent_address_gets_three_links_a_day_and_the_page_says_when_none_went` | 143.3 s |
| `.venv/bin/ruff check .` | FAIL | 2 errors: E501 line too long (121 > 120) at `shop/services.py:464`; I001 unsorted imports at `shop/test_api.py:5` (fixable) | 0.1 s | FAIL | 4 errors: E501 Line too long (121 > 120) at `accounts/views.py:338:121`; E501 Line too long (130 > 120) at `examleaf/settings.py:576:121`; E501 Line too long (121 > 120) at `learn/test_media.py:70:121`; DJ007 Do not use `__all__` with `ModelForm`, use `fields` instead at `learn/uploads.py:70:9` | 0.1 s |
| `.venv/bin/ruff format --check .` | FAIL | 2 files would be reformatted (`shop/services.py`, `shop/test_api.py`), 165 already formatted | 0.0 s | FAIL | 3 files would be reformatted, 177 files already formatted (`SECURITY_REVIEW_PHASE5_6.md`, `accounts/test_parent_link.py`, `examleaf/settings.py`) | 0.0 s |
| `manage.py check --deploy` with `DEBUG=0`, a random 50-character `SECRET_KEY`, `ALLOWED_HOSTS=examleaf.in`, `SITE_URL=https://examleaf.in`, `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` | pass | 0 errors, 2 warnings: security.W005, security.W021 (HSTS includeSubDomains and preload, both off on purpose) | 1.8 s | pass | 0 errors, 2 warnings: security.W005, security.W021 (HSTS includeSubDomains and preload, both off on purpose) | 1.6 s |
| `manage.py makemigrations --check --dry-run` | pass | No changes detected | 1.6 s | pass | No changes detected | 2.0 s |
| `manage.py spectacular --validate --fail-on-warn --file /dev/null` | pass | valid, no warnings | 1.6 s | pass | valid, no warnings | 2.3 s |

Reading them. Run A, the baseline proper: the tests are green; the two lint findings are one over-long line and one unsorted import block in files of the checkpoint that was being committed; `check --deploy` has no errors and two warnings that are decisions; migrations and the OpenAPI schema are in step. Run B is the same tree plus other agents' unfinished work: one new test fails (`accounts/test_parent_link.py`, a feature in progress: the parent's link limited to three a day), the lint findings grew to four (three over-long lines and one `DJ007` in `learn/uploads.py`, plus `ruff format` flags three files, one of them a Markdown file), and `ops/migrations/0005_sms_limits.py` (untracked; adds a column to `ops_smslog`) means a database copy made before it fails on the SMS log page of the admin until it is migrated. Neither run found anything wrong with what was in the last commit.

## 2. Page weights

Five pages: `/`, `/shop/`, the Physics Sample Papers product page, `/s/PHY-E01/` logged out (the register wall), and `/account/login/`. Sizes are bytes as served (no compression by the development server) with gzip level 9 beside HTML and CSS, which is what production's Caddy (`encode zstd gzip`) sends. 1 KB = 1000 bytes.

### 2.1 What the HTML refers to, fetched with plain HTTP (the tree, `[::1]:8060`)

Each file the page names is fetched once: the stylesheet, the scripts, the preloaded fonts, one icon, the manifest, and for images the smallest and the largest candidate of each picture (a phone at 2x takes the larger). Fonts: *preloaded* are the two the HTML preloads; *declared* are all six `@font-face` files of the stylesheet (four Latin, two Bengali-script), of which a page fetches only the faces its text uses.

| Page | HTML | HTML gzip | CSS | CSS gzip | JS | Fonts preloaded | Fonts declared | Images (smallest to largest) | Requests |
|---|---|---|---|---|---|---|---|---|---|
| home | 27,848 | 6,335 | 54,392 | 12,428 | 4,875 (1) | 22,172 (2) | 185,408 (6) | 135,666 to 252,667 (8 images) | 11 |
| shop | 22,010 | 4,416 | 59,854 | 14,049 | 4,875 (1) | 22,172 (2) | 185,408 (6) | 24,025 to 191,556 (5 images) | 12 |
| product | 17,739 | 4,882 | 59,854 | 14,049 | 4,875 (1) | 22,172 (2) | 185,408 (6) | 5,657 to 43,225 (1 image) | 9 |
| solutions (logged out) | 11,143 | 3,216 | 54,392 | 12,428 | 4,875 (1) | 22,172 (2) | 185,408 (6) | 0 to 0 (0 images) | 7 |
| login | 13,896 | 3,982 | 59,731 | 13,990 | 16,562 (4) | 22,172 (2) | 185,408 (6) | 0 to 0 (0 images) | 11 |

Requests = the HTML + stylesheet + scripts + preloaded fonts + one icon + the manifest + each distinct image once. No page loads anything from another host except `/s/<code>/` signed in (KaTeX from jsDelivr, not counted here: the logged-out page is the one measured).

### 2.2 What headless Chrome fetches (cold cache, load plus 1.5 s, then scrolled to the bottom)

The numbers a visitor's browser actually pays: the fonts it needs for the text on the page, the image it picks from each `srcset`, lazy images after the scroll. *Other* is the favicon, the manifest and the service worker script. Body bytes, as decoded; the site's service worker is bypassed, so every request really went to the server.

| Page | Viewport | Requests | HTML | CSS | JS | Fonts | Images | Other | Total |
|---|---|---|---|---|---|---|---|---|---|
| home | desktop 1280x900@1 | 18 | 27,848 (1) | 54,392 (1) | 4,875 (1) | 44,636 (4) | 271,332 (8) | 6,201 (3) | 409,284 |
| home | phone 375x812@2 | 13 | 27,848 (1) | 54,392 (1) | 4,875 (1) | 44,636 (4) | 135,666 (4) | 5,906 (2) | 273,323 |
| shop | desktop 1280x900@1 | 15 | 22,010 (1) | 59,854 (2) | 4,875 (1) | 44,636 (4) | 206,968 (5) | 5,906 (2) | 344,249 |
| shop | phone 375x812@2 | 14 | 22,010 (1) | 59,854 (2) | 4,875 (1) | 44,636 (4) | 191,556 (4) | 5,906 (2) | 328,837 |
| product | desktop 1280x900@1 | 11 | 17,739 (1) | 59,854 (2) | 4,875 (1) | 44,636 (4) | 43,225 (1) | 5,906 (2) | 176,235 |
| product | phone 375x812@2 | 11 | 17,739 (1) | 59,854 (2) | 4,875 (1) | 44,636 (4) | 43,225 (1) | 5,906 (2) | 176,235 |
| solutions (logged out) | desktop 1280x900@1 | 9 | 11,143 (1) | 54,392 (1) | 4,875 (1) | 44,636 (4) | 0 (0) | 5,906 (2) | 120,952 |
| solutions (logged out) | phone 375x812@2 | 9 | 11,143 (1) | 54,392 (1) | 4,875 (1) | 44,636 (4) | 0 (0) | 5,906 (2) | 120,952 |
| login | desktop 1280x900@1 | 13 | 13,896 (1) | 59,731 (2) | 16,562 (4) | 44,636 (4) | 0 (0) | 5,906 (2) | 140,731 |
| login | phone 375x812@2 | 13 | 13,896 (1) | 59,731 (2) | 16,562 (4) | 44,636 (4) | 0 (0) | 5,906 (2) | 140,731 |

On the phone the shop's lazy images arrive with the scroll: 11 requests and 180,506 bytes at load, 14 and 328,837 after scrolling.

### 2.3 The same pages before the redesign (commit `9b4c3f2`, `[::1]:8070`)

| Page | HTML | HTML gzip | CSS | CSS gzip | JS | Fonts preloaded | Fonts declared | Images (smallest to largest) | Requests |
|---|---|---|---|---|---|---|---|---|---|
| home | 2,146 | 841 | 14,657 | 3,879 | 0 (0) | 0 (0) | 0 (0) | 705,806 to 705,806 (4 images) | 7 |
| shop | 4,312 | 1,026 | 14,657 | 3,879 | 0 (0) | 0 (0) | 0 (0) | 705,806 to 705,806 (5 images) | 7 |
| product | 2,790 | 1,314 | 14,657 | 3,879 | 0 (0) | 0 (0) | 0 (0) | 178,932 to 178,932 (1 image) | 4 |
| solutions (logged out) | 1,511 | 701 | 14,657 | 3,879 | 0 (0) | 0 (0) | 0 (0) | 0 to 0 (0 images) | 3 |
| login | 2,336 | 1,001 | 14,657 | 3,879 | 0 (0) | 0 (0) | 0 (0) | 0 to 0 (0 images) | 3 |

| Page | Viewport | Requests | HTML | CSS | JS | Fonts | Images | Other | Total |
|---|---|---|---|---|---|---|---|---|---|
| home | desktop 1280x900@1 | 7 | 2,146 (1) | 14,657 (1) | 0 (0) | 0 (0) | 705,806 (4) | 179 (1) | 722,788 |
| home | phone 375x812@2 | 6 | 2,146 (1) | 14,657 (1) | 0 (0) | 0 (0) | 705,806 (4) | 0 (0) | 722,609 |
| shop | desktop 1280x900@1 | 6 | 4,312 (1) | 14,657 (1) | 0 (0) | 0 (0) | 705,806 (4) | 0 (0) | 724,775 |
| shop | phone 375x812@2 | 6 | 4,312 (1) | 14,657 (1) | 0 (0) | 0 (0) | 705,806 (4) | 0 (0) | 724,775 |
| product | desktop 1280x900@1 | 3 | 2,790 (1) | 14,657 (1) | 0 (0) | 0 (0) | 178,932 (1) | 0 (0) | 196,379 |
| product | phone 375x812@2 | 3 | 2,790 (1) | 14,657 (1) | 0 (0) | 0 (0) | 178,932 (1) | 0 (0) | 196,379 |
| solutions (logged out) | desktop 1280x900@1 | 2 | 1,511 (1) | 14,657 (1) | 0 (0) | 0 (0) | 0 (0) | 0 (0) | 16,168 |
| solutions (logged out) | phone 375x812@2 | 2 | 1,511 (1) | 14,657 (1) | 0 (0) | 0 (0) | 0 (0) | 0 (0) | 16,168 |
| login | desktop 1280x900@1 | 2 | 2,336 (1) | 14,657 (1) | 0 (0) | 0 (0) | 0 (0) | 0 (0) | 16,993 |
| login | phone 375x812@2 | 2 | 2,336 (1) | 14,657 (1) | 0 (0) | 0 (0) | 0 (0) | 0 (0) | 16,993 |

### 2.4 Before and after, browser-observed, desktop

| Page | Requests before | Bytes before | Requests after | Bytes after | Change in bytes |
|---|---|---|---|---|---|
| home | 7 | 722,788 | 18 | 409,284 | -313,504 |
| shop | 6 | 724,775 | 15 | 344,249 | -380,526 |
| product | 3 | 196,379 | 11 | 176,235 | -20,144 |
| solutions (logged out) | 2 | 16,168 | 9 | 120,952 | +104,784 |
| login | 2 | 16,993 | 13 | 140,731 | +123,738 |

What the numbers say. The stylesheet grew from 14,657 to 54,392 bytes (3,879 to 12,428 gzipped; the shop and account pages add another 5 to 6 KB of `shop.css` or `account.css`), and one 4.9 KB script and four Latin font files (44,636 bytes) arrived: a page with no pictures, such as the register wall, now weighs 121 KB against 16 KB, about 105 KB more of fixed weight on every page. In return the covers went from PNG (about 176 KB each, 706 KB for the four on the home page) to AVIF at 320 px (about 35 KB each): on a desktop, with the whole page scrolled, the home page carries 313,504 bytes less and the shop 380,526 bytes less than before. Every cover is a `<picture>` with AVIF and WebP sources and the original PNG (biology.png, chemistry.png, mathematics.png, physics.png) as the fallback, so only a browser without AVIF and WebP downloads the 176 KB file; the headless Chrome used here takes the AVIF.

## 3. How this was measured

- `weights.py`: `urllib` fetches of the HTML and of everything it names (links, scripts, `<img>`, `<picture>` and `srcset`), and of the fonts and images the stylesheet names; the same code against both servers.
- `weights_cdp.py`: headless Chrome 154 over the DevTools protocol, one fresh tab per page and viewport (1280×900 at 1x; 375×812 at 2x with touch), cache disabled, network events summed by type.
- Servers: the tree on `[::1]:8060` and commit `9b4c3f2` (a git worktree, run with the current virtualenv) on `[::1]:8070`; development settings with `DEBUG` switched off at run time (so error pages are the site's own and the debug toolbar, about 30 KB of markup and several more requests on every page, stays out of the numbers); a copy of the development database for both.
- The browser capture bypasses the site's service worker on purpose: it serves static files cache-first under a name that does not change while the file names are not hashed (development, or `DEBUG` off without `collectstatic`), which showed a stale stylesheet in an earlier capture. Production's hashed names avoid this.
- The checks in section 1 are `baseline.sh`; the git state was read before and after.
