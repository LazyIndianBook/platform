# ExamLeaf: Lighthouse audit (performance, accessibility, best practices, SEO)

Measured on 8 October 2026 (IST) on a copy of the working tree at commit `ba0b9dd` (redesign stages 2a and 2b; the only uncommitted file was `SECURITY_REVIEW_PHASE5_6.md`). Nothing under `examleaf-web/` was edited. The keyboard, zoom and screen-reader side is in [audit-accessibility.md](audit-accessibility.md).

## 1. In one minute

- The scores are already high. Mobile, simulated slow 4G: **accessibility 100 and best practices 100 on every real page**; SEO 100 on the public pages and 66 on cart, checkout, account and login, which say `noindex` on purpose. Performance is 90 to 99 on the dev server and 97 to 100 once the server behaves like production (compressed, hashed and cached static files).
- Lighthouse finds **no accessibility failure on any page**. Its automated rules do not reach what the manual pass found (cart table cut off at 375 px, header overflow at 320 px, toast covering focus, the Menu control): see [audit-accessibility.md](audit-accessibility.md).
- CLS 0 to 0.005, TBT 0 to 44 ms, lab INP 24 to 104 ms on every page. Nothing here is slow; what is left is the home page's weight, two late fonts, one blocking script set on login and the solutions page.
- Real performance findings, each tested by changing the page on the fly (section 5): **P2** the four cover files on the home page are 3 to 4 times too large for where they are shown (216 to 118 KiB, LCP 2.3 to 1.7 s); **P1** two of the four font files are found late on every page (preloading them: FCP 1.2 to 0.9 s); **P3** three parser-blocking passkey scripts on the login page (`defer`: FCP 1.5 to 1.2 s); **P4** the solutions page (KaTeX from jsDelivr, a 12,239-node DOM, a 118 ms render task; 97 to 99). Smaller: P5 lazy LCP image on `/shop/` (no lab gain), P6 product pictures cached for a day, P7 one 78 KiB stylesheet.
- Several audits only fire on the dev server (no compression, no cache headers). They disappear in the production-like pass and are listed apart (section 4.4).

## 2. How it was measured

| Item | Value |
|---|---|
| Tool | Lighthouse 13.5.0 (CLI), Chrome 154.0.8037.98 headless, Node 20.19.4, Apple M1 Pro, macOS 15.6 |
| Mobile preset | Lighthouse default: 412x823 at 1.75 DPR (Moto G Power user agent), simulated slow 4G (150 ms RTT, 1.6 Mbps down, 4x CPU slowdown) |
| Desktop preset | `--preset=desktop` (1350x940, 40 ms RTT, 10 Mbps, no CPU slowdown), home and product only |
| Categories | performance, accessibility, best-practices, seo |
| Runs | each page twice, the better run kept (higher performance score, then lower LCP). Accessibility, best practices and SEO were identical between the two runs of every page |
| Noise | other agents ran servers and tests on the same Mac (load average 5 to 7). The two runs of a page differ by 0 to 2 points (up to 0.7 s on the solutions page across all the runs made); the benchmark index was 2730 to 2890 on every run |
| Server | a **snapshot copy** of `examleaf-web` (code, `.env`, a copy of `db.sqlite3`) in the scratchpad, started with `manage.py runserver --noreload`: edits made meanwhile by other agents could not change a run, and the real database was not touched |
| Signed-in pages | a temporary non-staff student (no usable password, session made with `Client.force_login`) with one book in the cart, passed as `--extra-headers '{"Cookie":"sessionid=..."}'`. The user, its cart and the copy were deleted at the end; the session ids were scrubbed from the saved HTML |
| Pages | `/`, `/shop/`, `/shop/physics-sample-papers-2027/`, `/cart/`, `/checkout/`, `/s/PHY-E01/`, `/account/`, `/account/login/`, `/privacy/`, a 404 |

Two measurement passes, because the dev server hides some things and exaggerates others:

1. **Dev server** (port 8090), as asked: `DEBUG=1` from `.env`.
2. **Production-like** (port 8091), added: `DEBUG=0` with a throwaway secret key, `collectstatic` with WhiteNoise's hashed and pre-compressed files (brotli for text, `max-age=315360000, immutable`), a gzip middleware for text responses only (HTML, CSS, JS, JSON, SVG; fonts and images are left alone) standing in for Caddy's `encode zstd gzip`, the enforced CSP, `SMS_BACKEND=msg91` with a dummy key so the phone-login form is on the login page as in production, https redirect and HSTS off (plain http on localhost). It also serves the **real 404 page**: with `DEBUG=1` Django answers every 404 with its own technical page, so the dev "404" row is not the site's page.

Deviations from the brief, and why:

- **django-debug-toolbar is installed and cannot be switched off from the environment** (`DEBUG_TOOLBAR = DEBUG and not TESTING and find_spec("debug_toolbar")` in `examleaf/settings.py`). A settings wrapper outside the tree (`measure_settings.py`) removes it from `INSTALLED_APPS` and `MIDDLEWARE`; the toolbar markup is absent from the measured HTML.
- **`Cross-Origin-Opener-Policy` is off in both passes.** Lighthouse 13.5 on Chrome 154 stops with `NO_NAVSTART` ("something went wrong with recording the trace") on any page that sends `Cross-Origin-Opener-Policy: same-origin`, which is Django's default. The same page without the header traces normally. Production keeps the header; nothing else in the response changes. Anyone re-running against an unmodified server will see the error. Lighthouse's own informative audits `origin-isolation` and `has-hsts` ("no COOP header", "no HSTS header") are artefacts of this setup, not findings.
- Not reproduced locally: HTTP/2 or 3 from Caddy (local is HTTP/1.1), Postgres, Redis, the R2 bucket with one-year media caching, Turnstile and Google keys, a real network. TTFB here is 8 to 130 ms; expect more behind gunicorn and Postgres.
- Lighthouse navigation runs give TBT, not INP. INP was probed separately (section 3.5).

## 3. Scores and metrics

Columns: Perf, A11y, BP (best practices), SEO are the four Lighthouse category scores; FCP, LCP, TBT, CLS and Speed Index are lab metrics; Bytes is the transferred weight (`total-byte-weight`), Req the request count; the last column gives both runs as performance score / LCP in seconds. The saved HTML report of the kept run is linked in section 6.

### 3.1 Dev server, mobile (as asked)

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Speed Index | TTFB | Bytes | Req | Runs (perf / LCP s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Home `/` | **95** | 100 | 100 | 100 | 1.5 s | 2.9 s | 0 ms | 0 | 1.5 s | 39 ms | 300 KiB | 14 | 95 / 2.9, 94 / 3.0 (kept #1) |
| Shop `/shop/` | **97** | 100 | 100 | 100 | 1.5 s | 2.6 s | 0 ms | 0 | 1.5 s | 41 ms | 279 KiB | 13 | 97 / 2.6, 97 / 2.6 (kept #2) |
| Product `/shop/physics-sample-papers-2027/` | **97** | 100 | 100 | 100 | 1.5 s | 2.4 s | 0 ms | 0 | 1.5 s | 35 ms | 198 KiB | 11 | 97 / 2.4, 97 / 2.4 (kept #2) |
| Cart `/cart/` (1 item, signed in) | **99** | 100 | 100 | 66 | 1.5 s | 2.1 s | 0 ms | 0.005 | 1.5 s | 38 ms | 159 KiB | 11 | 97 / 2.3, 99 / 2.1 (kept #2) |
| Checkout `/checkout/` (signed in) | **98** | 100 | 100 | 66 | 1.8 s | 2.1 s | 0 ms | 0 | 1.8 s | 32 ms | 162 KiB | 12 | 98 / 2.1, 98 / 2.2 (kept #1) |
| Solutions `/s/PHY-E01/` (signed in) | **90** | 100 | 100 | 100 | 2.3 s | 3.2 s | 39 ms | 0 | 2.3 s | 44 ms | 343 KiB | 19 | 90 / 3.2, 90 / 3.2 (kept #1) |
| My account `/account/` (signed in) | **99** | 100 | 100 | 66 | 1.5 s | 2.1 s | 0 ms | 0 | 1.5 s | 132 ms | 153 KiB | 10 | 99 / 2.1, 98 / 2.3 (kept #1) |
| Login `/account/login/` | **98** | 100 | 100 | 66 | 1.8 s | 2.1 s | 0 ms | 0 | 1.8 s | 27 ms | 165 KiB | 13 | 98 / 2.1, 97 / 2.3 (kept #1) |
| Legal `/privacy/` | **99** | 100 | 100 | 100 | 1.5 s | 2.1 s | 0 ms | 0 | 1.5 s | 8 ms | 154 KiB | 10 | 99 / 2.1, 99 / 2.1 (kept #2) |
| 404 `/no-such-page-xyz/` | **100** | 100 | 96 | 45 | 0.8 s | 1.1 s | 0 ms | 0 | 0.8 s | 9 ms | 19 KiB | 3 | 100 / 1.1, 100 / 1.1 (kept #1) |

Notes. The 404 row is Django's debug page (3 requests, 19 KiB), not the site's page. SEO 66 is `is-crawlable` failing on a page that says `noindex` (intended). The solutions page scores lowest (90) because of KaTeX and an uncompressed 76 KiB document.

### 3.2 Production-like, mobile

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Speed Index | TTFB | Bytes | Req | Runs (perf / LCP s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Home `/` | **98** | 100 | 100 | 100 | 1.2 s | 2.3 s | 0 ms | 0 | 1.2 s | 37 ms | 216 KiB | 14 | 98 / 2.3, 98 / 2.3 (kept #1) |
| Shop `/shop/` | **100** | 100 | 100 | 100 | 1.2 s | 1.7 s | 0 ms | 0 | 1.2 s | 63 ms | 199 KiB | 13 | 100 / 1.7, 100 / 1.7 (kept #1) |
| Product `/shop/physics-sample-papers-2027/` | **99** | 100 | 100 | 100 | 1.2 s | 1.8 s | 0 ms | 0 | 1.2 s | 51 ms | 122 KiB | 11 | 99 / 1.8, 99 / 1.8 (kept #1) |
| Cart `/cart/` (1 item, signed in) | **100** | 100 | 100 | 66 | 1.2 s | 1.5 s | 0 ms | 0 | 1.2 s | 42 ms | 84 KiB | 11 | 100 / 1.5, 100 / 1.5 (kept #2) |
| Checkout `/checkout/` (signed in) | **100** | 100 | 100 | 66 | 1.2 s | 1.4 s | 0 ms | 0 | 1.2 s | 43 ms | 85 KiB | 12 | 100 / 1.4, 100 / 1.4 (kept #1) |
| Solutions `/s/PHY-E01/` (signed in) | **97** | 100 | 100 | 100 | 1.6 s | 2.5 s | 44 ms | 0 | 1.6 s | 31 ms | 219 KiB | 19 | 97 / 2.5, 97 / 2.5 (kept #2) |
| My account `/account/` (signed in) | **100** | 100 | 100 | 66 | 1.2 s | 1.5 s | 0 ms | 0 | 1.2 s | 48 ms | 78 KiB | 10 | 100 / 1.5, 100 / 1.5 (kept #1) |
| Login `/account/login/` | **100** | 100 | 100 | 66 | 1.5 s | 1.5 s | 0 ms | 0 | 1.5 s | 26 ms | 83 KiB | 13 | 99 / 1.7, 100 / 1.5 (kept #2) |
| Legal `/privacy/` | **100** | 100 | 100 | 100 | 1.2 s | 1.5 s | 0 ms | 0 | 1.2 s | 21 ms | 79 KiB | 10 | 100 / 1.5, 100 / 1.5 (kept #2) |
| 404 `/no-such-page-xyz/` | **98** | 100 | 96 | 61 | 1.2 s | 2.3 s | 0 ms | 0 | 1.2 s | 24 ms | 213 KiB | 14 | 98 / 2.3, 98 / 2.3 (kept #1) |

Notes. Compression and cache headers alone move home 95 to 98, shop 97 to 100, solutions 90 to 97, account 99 to 100 and cut the transferred weight by 28 to 50 percent (home 300 to 216 KiB, solutions 343 to 219 KiB, account 153 to 78 KiB). The solutions page varies most from run to run (97 to 99, LCP 1.8 to 2.5 s over all the runs made, because KaTeX comes from a CDN). The 404 row is the real branded page: SEO 61 (HTTP 404 status and `noindex`) and best practices 96 (the 404 response itself is logged as a console error) are expected for an error page. It repeats the home page's four covers, hence 213 KiB and LCP 2.3 s (see P2).

### 3.3 Desktop preset

Dev server:

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Speed Index | TTFB | Bytes | Req | Runs (perf / LCP s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Home `/` | **100** | 100 | 100 | 100 | 0.4 s | 0.6 s | 0 ms | 0 | 0.4 s | 40 ms | 300 KiB | 14 | 100 / 0.6 (kept #1) |
| Product `/shop/physics-sample-papers-2027/` | **100** | 100 | 100 | 100 | 0.4 s | 0.5 s | 0 ms | 0 | 0.4 s | 58 ms | 198 KiB | 11 | 100 / 0.5 (kept #1) |

Production-like:

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Speed Index | TTFB | Bytes | Req | Runs (perf / LCP s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Home `/` | **100** | 100 | 100 | 100 | 0.3 s | 0.5 s | 0 ms | 0 | 0.3 s | 39 ms | 216 KiB | 14 | 100 / 0.5 (kept #1) |
| Product `/shop/physics-sample-papers-2027/` | **100** | 100 | 100 | 100 | 0.3 s | 0.4 s | 0 ms | 0.001 | 0.3 s | 36 ms | 122 KiB | 11 | 100 / 0.4 (kept #1) |

Desktop is not a concern: 100 on all four categories, LCP 0.4 to 0.6 s.

### 3.4 What the bytes are made of (production-like, mobile; KiB transferred)

| Page | Total | Images | Fonts | CSS | JS | HTML | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Home | 216 KiB (dev 300) | 136 | 47 | 15 | 2 | 7 | 9 |
| Shop | 199 KiB (dev 279) | 121 | 47 | 15 | 2 | 5 | 9 |
| Product | 122 KiB (dev 198) | 43 | 47 | 15 | 2 | 6 | 9 |
| Cart | 84 KiB (dev 159) | 6 | 47 | 15 | 2 | 5 | 9 |
| Checkout | 85 KiB (dev 162) | 6 | 47 | 15 | 2 | 6 | 9 |
| Solutions | 219 KiB (dev 343) | 0 | 96 | 19 | 79 | 16 | 9 |
| My account | 78 KiB (dev 153) | 0 | 47 | 15 | 2 | 6 | 9 |
| Login | 83 KiB (dev 165) | 0 | 47 | 15 | 7 | 5 | 9 |
| Privacy | 79 KiB (dev 154) | 0 | 47 | 15 | 2 | 6 | 9 |
| 404 | 213 KiB (dev 18: debug page) | 136 | 47 | 15 | 2 | 4 | 9 |


Images are 63 percent of the home page and 61 percent of the shop page; the 14 KiB of CSS (78 KiB raw) and 47 KiB of fonts (four woff2 files) are the same on every page; JavaScript is 2 KiB except on the login page (7 KiB, allauth's passkey scripts) and the solutions page (79 KiB, KaTeX and `math.js`).

### 3.5 Lab INP (interaction latency), 375 px, 4x CPU slowdown

| Page | Interactions reported | Worst interaction | What it was |
|---|---:|---:|---|
| Home | 3 | 56 ms | Menu label, FAQ summary |
| Product | 4 | 40 ms | copies - / + buttons, typing in the box |
| Cart | 1 | 56 ms | copies stepper, Remove dialog |
| Login | 3 | 24 ms | typing a mobile number, opening the password form |
| Checkout | 2 | 32 ms | typing a name and a PIN code (starts the PIN lookup) |
| Solutions | 4 | 104 ms | opening "Instructions", typing marks (12,239-node page) |


All below 110 ms ("good" is 200 ms or less). The probe clicked and typed through Puppeteer and read the Event Timing API: worst interaction per page, values rounded to 8 ms and including the next paint; the API only reports interactions that took 16 ms or more, so faster ones are not in the count. The slowest is the solutions page because of its 12,239-node DOM.

## 4. Findings, in priority order

### 4.1 Accessibility (Lighthouse's automated rules)

None failing, on any page, in either pass (score 100). axe-core 4.14 run separately on 19 states that Lighthouse does not reach (menu open, Remove dialog open, three error pages after an invalid submit, toast, desktop widths) found one violation, `scrollable-region-focusable` on the solutions page; see [audit-accessibility.md](audit-accessibility.md), which also holds everything the automated rules cannot see.

### 4.2 Performance (real defects, production-like numbers; "measured" means tested in section 5)

**P1. Two of the four font files are found late. Priority: medium, effort: one line. Every page.**
- Where: `templates/base.html` preloads `poppins-800.woff2` and `hind-siliguri-400.woff2` only. `poppins-700.woff2` and `hind-siliguri-600.woff2` are first requested once `site.css` has been parsed, so the page loads HTML, then CSS, then two more fonts (`network-dependency-tree-insight`, every page).
- Measured (the two preloads injected, four runs each): home FCP 1.22 to 0.93 s, performance 98 to 99. LCP stays 2.3 s on its own because the images hold it (P2); with P2 as well: performance 100, FCP 0.92 s, LCP 1.67 s.
- Fix: add `<link rel="preload" href="{% static 'fonts/poppins-700.woff2' %}" as="font" type="font/woff2" crossorigin>` and the same for `hind-siliguri-600.woff2` in `base.html`, or drop those two weights.

**P2. Home page: the four cover files are far larger than the boxes they fill. Priority: high, effort: small. `/` and the 404 page.**
- Where: `{% static_cover %}` in `templates/home.html` (the hero fan, `div.stage > span.stage-cover`, `sizes="(min-width: 900px) 172px, 104px"`) and `templates/_tile.html` (the subject tiles, `sizes="112px"`). A cover is shown 104 to 172 CSS px wide, but the `srcset` offers only 320w and 480w, so the browser takes the 320w AVIF: `biology-320` 38 KiB, `chemistry-320` 34, `mathematics-320` 31, `physics-320` 30. That is 136 of the page's 216 KiB (63 percent), requested in the same burst as the CSS and the fonts. `image-delivery-insight`: 97 KiB estimated saving on mobile, 105 KiB on desktop.
- Measured (the same four URLs answered with a 200 px wide AVIF at quality 50, 8 to 11 KiB each; four runs each): home 216 to 118 KiB, LCP 2.27 to 1.74 s, performance 98 to 99.5. Making the tile images `loading="lazy"` alone changed nothing (LCP 2.3 s either way): the hero fan needs the same four files.
- Fix: add a 200 px (and a 240 px) variant of each cover to the `srcset` (`200w, 320w, 480w`) with the same `sizes`, and re-encode the 320w and 480w AVIFs about 10 quality points lower (Lighthouse sees 10 to 15 KiB of headroom in each). The 404 page shows the same covers.

**P3. Login: three parser-blocking passkey scripts. Priority: medium, effort: small. `/account/login/` (and other pages that include allauth's passkey snippet).**
- Where: `/static/mfa/js/webauthn-json.js`, `webauthn.js` and `/static/account/js/onload.js`, plain `<script src>` placed before the deferred `site.js` (`mfa/webauthn/snippets/login_script.html`, included at the end of `templates/account/login.html`). Lighthouse lists them as render-blocking (about 300 ms). On the dev server `webauthn-json.js` is also flagged unminified (2.2 KiB).
- Measured (`defer` added to the three tags, four runs each): login FCP 1.51 to 1.22 s; LCP and the score unchanged (100).
- Fix: override the snippet under `templates/mfa/webauthn/snippets/` and add `defer`, keeping the order; check that `onload.js` still sets up the passkey button once the scripts run deferred (the speed test did not exercise the passkey flow).

**P4. Solutions page: a very large DOM and third-party KaTeX. Priority: medium, effort: medium. `/s/<CODE>/` (measured on `/s/PHY-E01/`: performance 97 to 99, LCP 1.8 to 2.5 s, TBT 44 ms; 90 on the dev server).**
- Where: `templates/solutions.html` loads `katex.min.css` from `cdn.jsdelivr.net` (render-blocking and third-party: 898 ms estimated), three KaTeX fonts with no `font-display` (`KaTeX_Main-Regular`, `KaTeX_Size2-Regular`, `KaTeX_Math-Italic`: 50 to 60 ms each, `font-display-insight`); `static/js/math.js` then renders the whole page: 12,239 DOM elements, depth 39, a 40 ms forced reflow, five long tasks (140, 118, 77, 57, 52 ms; `math.js` itself 118 ms), max potential FID 120 ms.
- Measured: serving KaTeX from the same origin with an immutable cache moved FCP 1.68 to 1.37 s but LCP 1.81 to 2.15 s and TBT 40 to 125 ms (the maths task now falls after first paint): neutral in the lab. The case for self-hosting is robustness (no third-party dependency), caching and a tighter CSP (`KATEX_CDN` leaves `script-src`), not lab speed. A `preconnect` to jsDelivr changed nothing measurable (two runs).
- Fix, in order of effect: render the maths of a question when it scrolls into view (IntersectionObserver) instead of all 12,239 nodes at load (not tested); self-host KaTeX CSS, JS and the three fonts under `/static/` and add `font-display: swap` to the copied CSS.

**P5. Shop: the LCP image is lazy-loaded. Priority: low, effort: one line. `/shop/`.**
- Where: `templates/shop/catalogue.html` line 40, `div.fan > span.cover > picture > img` (`/shop/media/products/physics/2_3/300w.avif`): `{% picture ... img_loading="lazy" ... %}`. Lighthouse `lcp-discovery-insight` fails on two checks: no `fetchpriority=high`, and `loading=lazy` on the LCP resource. LCP 1.7 s.
- Measured (`loading="eager" fetchpriority="high"` on the first cover, four runs each): LCP 1.66 to 1.74 s: no change. The fan is above the fold, so eager is still the right attribute, but do not expect the lab number to move. (`image-delivery-insight` adds 15 KiB of AVIF headroom on the 300w and 400w files.)

**P6. Product pictures are cached for one day. Priority: low, effort: one line. `/shop/`, product, cart and checkout.**
- Where: `/shop/media/products/<name>/2_3/{100w,300w,400w}.avif` are sent with `Cache-Control: public, max-age=86400` (`cache-insight`: shop 48 KiB, product 17 KiB, cart and checkout 3 KiB for the 100w thumbnail). In production the "public" storage is R2 behind `PUBLIC_MEDIA_DOMAIN` with a one-year immutable cache (comment in `settings.py`), so this matters only for single-server installs without buckets. File names are never reused, so `shop.views.product_media` can send `max-age=31536000, immutable`.

**P7. `site.css`: 78 KiB raw, one stylesheet for the whole site. Priority: low. All pages.**
- `render-blocking-insight` estimates 150 to 880 ms (home 560, shop 420, product 420, cart 150, checkout 420, solutions 810, account 590, login 880, privacy 580, 404 580; desktop 150 to 160 ms), `unused-css-rules` finds 11 to 13 KiB of the 14 KiB brotli unused on any one page (every page except home), `unminified-css` 3.3 KiB brotli (17 KiB raw, 22 percent).
- Measured: inlining the whole file in the HTML, which is the upper bound for "critical CSS", moved home FCP only from 1.22 to 1.10 s and shop not at all. The blocking estimate is mostly the download of the file itself, which cannot be avoided; do not inline. Worth doing when convenient: minify in the build (rcssmin, lightningcss or esbuild before `collectstatic`), and split off the per-section rules (shop, account, solutions) to cut the 11 to 13 KiB.

**P8. Minor.**
- CLS is 0 everywhere except cart (0.005): `aside.summary-card` moves a few pixels when `site.js` unhides the copies stepper (`button.hidden = false`). Reserve the space (`visibility:hidden` instead of `hidden`) if you want exactly 0.
- Nothing else: TBT is 0 ms except on the solutions page, font fallbacks are tuned (`size-adjust`), covers are AVIF and WebP with a PNG fallback and carry `width` and `height`, one 2 KiB script, the service worker starts after load.

### 4.3 Best practices and SEO

| Audit | Pages | Verdict |
|---|---|---|
| `is-crawlable` (page blocked from indexing) | cart, checkout, account, login (SEO 66); 404 | By design: these pages say `noindex`. No action. |
| `http-status-code`, `errors-in-console`, `bf-cache` ("only 2xx pages can be cached") | 404 only | Expected for an error page: the 404 response is logged as a console error. No action. |
| `meta-description`, `viewport-insight` | dev 404 only | Django's own debug page, not the site's. The real 404 has both. |
| `csp-xss`, `trusted-types-xss`, `has-hsts`, `origin-isolation` | informative, every page | Not scored. HSTS and COOP are switched off by the measurement setup. `csp-xss` notes that `script-src` uses a host allowlist (the KaTeX CDN); self-hosting KaTeX (P4) would let `script-src 'self'` stand alone. |

No console errors, CSP violations or mixed content on any real page in the production-like pass, which enforces the CSP.

### 4.4 Shown on the dev server only (not defects)

| Audit | Dev pages | Why it goes away |
|---|---|---|
| `document-latency-insight` "No compression applied" (10 to 50 KiB per page) | all | Caddy's `encode zstd gzip`; the prod-like pass compresses and the audit passes. |
| Larger `render-blocking-insight`, `unused-css-rules`, `unminified-css` numbers (79 KiB CSS instead of 15 KiB) | all | WhiteNoise pre-compresses with brotli and gzip after `collectstatic`. |
| `unminified-javascript` on `webauthn-json.js` | login | Not flagged in the prod-like pass (2.7 KiB transferred; see P3 for the blocking). |
| Unhashed static URLs without `Cache-Control` | all | `CompressedManifestStaticFilesStorage` (hashed names, `max-age=315360000, immutable`) when `DEBUG=0`. |

### 4.5 Audit index (every failing or warning audit in either pass)

| Audit | Pages (production-like) | See |
|---|---|---|
| `render-blocking-insight` | all ten | P7 (P4 for KaTeX, P3 for login) |
| `network-dependency-tree-insight` | all ten | P1 |
| `unminified-css` | all ten | P7 |
| `unused-css-rules` | all but home | P7 |
| `image-delivery-insight` | home, 404, shop | P2 (P5 for shop) |
| `lcp-discovery-insight` | shop | P5 |
| `font-display-insight`, `forced-reflow-insight`, `max-potential-fid` | solutions | P4 |
| `cache-insight` | shop, product, cart, checkout | P6 |
| `is-crawlable` | cart, checkout, account, login, 404 | 4.3 (by design) |
| `http-status-code`, `errors-in-console`, `bf-cache` | 404 | 4.3 (expected) |
| `document-latency-insight`, `unminified-javascript`, `viewport-insight`, `meta-description` | dev only | 4.4 |

## 5. Experiments (production-like server, mobile, Lighthouse performance only)

Each fix was tried without touching the site: a small rewriting proxy (Node, port 8095) sat in front of the production-like server and changed the HTML before Lighthouse saw it (or answered an image request with a re-encoded file). Four runs per condition, median shown; the simulation moves by up to 0.3 s between identical runs, so smaller differences mean nothing.

| Page | Condition | Performance | FCP | LCP | TBT | Bytes |
|---|---|---:|---:|---:|---:|---:|
| Home | as served | 98 | 1.22 s | 2.27 s | 0 ms | 217 KiB |
| Home | `poppins-700` and `hind-siliguri-600` preloaded (P1) | 99 | **0.93 s** | 2.27 s | 0 ms | 217 KiB |
| Home | the four covers served as 200 px AVIF q50 (P2) | 99.5 | 1.22 s | **1.74 s** | 0 ms | **118 KiB** |
| Home | both | **100** | 0.92 s | 1.67 s | 0 ms | 118 KiB |
| Login | as served | 100 | 1.51 s | 1.51 s | 0 ms | 84 KiB |
| Login | passkey scripts `defer`red (P3) | 100 | **1.22 s** | 1.59 s | 0 ms | 84 KiB |
| Shop | as served | 100 | 1.22 s | 1.66 s | 0 ms | 199 KiB |
| Shop | first cover `loading="eager" fetchpriority="high"` (P5) | 100 | 1.22 s | 1.74 s | 0 ms | 199 KiB |
| Solutions | as served | 99 | 1.68 s | 1.81 s | 40 ms | 219 KiB |
| Solutions | KaTeX served from the same origin, immutable (P4) | 97 | 1.37 s | 2.15 s | 125 ms | 217 KiB |

Two more tests, two runs each: all of `site.css` inlined in the HTML (P7): home FCP 1.10 s against 1.22 s, LCP 2.3 s both, shop no change. And upper bounds: blocking the four `*.avif` files gave home LCP 1.7 s and performance 100; blocking the four woff2 fonts gave LCP 2.1 s and performance 99 (baseline 2.3 s and 98).

## 6. Files

HTML reports of the kept run of each page, mobile unless the name says desktop. About 19 MB in total: delete the `prodlike-*` set if the repository should stay small.

| Page | Dev server | Production-like |
|---|---|---|
| Home | [mobile](lighthouse/dev-home-mobile.html), [desktop](lighthouse/dev-home-desktop.html) | [mobile](lighthouse/prodlike-home-mobile.html), [desktop](lighthouse/prodlike-home-desktop.html) |
| Shop | [mobile](lighthouse/dev-shop-mobile.html) | [mobile](lighthouse/prodlike-shop-mobile.html) |
| Product | [mobile](lighthouse/dev-product-mobile.html), [desktop](lighthouse/dev-product-desktop.html) | [mobile](lighthouse/prodlike-product-mobile.html), [desktop](lighthouse/prodlike-product-desktop.html) |
| Cart | [mobile](lighthouse/dev-cart-mobile.html) | [mobile](lighthouse/prodlike-cart-mobile.html) |
| Checkout | [mobile](lighthouse/dev-checkout-mobile.html) | [mobile](lighthouse/prodlike-checkout-mobile.html) |
| Solutions | [mobile](lighthouse/dev-paper-mobile.html) | [mobile](lighthouse/prodlike-paper-mobile.html) |
| My account | [mobile](lighthouse/dev-account-mobile.html) | [mobile](lighthouse/prodlike-account-mobile.html) |
| Login | [mobile](lighthouse/dev-login-mobile.html) | [mobile](lighthouse/prodlike-login-mobile.html) |
| Privacy | [mobile](lighthouse/dev-legal-mobile.html) | [mobile](lighthouse/prodlike-legal-mobile.html) |
| 404 | [mobile (Django debug page)](lighthouse/dev-notfound-mobile.html) | [mobile (the site's page)](lighthouse/prodlike-notfound-mobile.html) |

To re-run: copy the tree, add a settings wrapper that removes `debug_toolbar` and sets `SECURE_CROSS_ORIGIN_OPENER_POLICY = None`, start `runserver --noreload` (and a `DEBUG=0` instance after `collectstatic` for the production-like pass), then `lighthouse <url> --chrome-flags=--headless=new --only-categories=performance,accessibility,best-practices,seo`, with `--preset=desktop` for desktop and `--ignore-status-code` for the 404. Not covered: orders and order detail, invoices, the `/learn/` player, the admin, emails, a real device or network.
