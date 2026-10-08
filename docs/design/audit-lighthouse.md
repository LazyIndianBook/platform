# ExamLeaf: Lighthouse audit (performance, accessibility, best practices, SEO)

Measured on 8 October 2026 (IST) on a copy of the working tree at commit `ba0b9dd` (redesign stages 2a and 2b; the only uncommitted file was `SECURITY_REVIEW_PHASE5_6.md`). Nothing under `examleaf-web/` was edited. The keyboard, zoom and screen-reader side is in [audit-accessibility.md](audit-accessibility.md).

## 1. In one minute

- The scores are already high. Mobile, simulated slow 4G: **accessibility 100 and best practices 100 on every real page**; SEO 100 on the public pages and 66 on cart, checkout, account and login, which say `noindex` on purpose. Performance is 90 to 99 on the dev server and 97 to 100 once the server behaves like production.
- Lighthouse finds **no accessibility failure on any page**. Its automated rules do not reach what the manual pass found (cart table cut off at 375 px, header overflow at 320 px, toast covering focus, Menu control): see the other file.
- CLS 0 to 0.005, TBT 0 to 47 ms, lab INP 24 to 104 ms on every page. Nothing here is slow; what is left is page weight on the home page, one lazy-loaded LCP image, and the solutions page.
- Real performance findings, in order of payoff: (P1) render-blocking `site.css` plus a two-step font chain on every page; (P2) four eager 30 to 40 KB cover images on the home page (blocking them takes LCP from 2.3 s to 1.7 s); (P3) the `/shop/` LCP image is `loading="lazy"`; (P4) KaTeX from jsDelivr on the solutions page; (P5) three parser-blocking passkey scripts on the login page.
- Several findings only exist on the dev server (no compression, no cache headers); they disappear in the production-like pass and are listed apart (section 4.4).

## 2. How it was measured

| Item | Value |
|---|---|
| Tool | Lighthouse 13.5.0 (CLI), Chrome 154.0.8037.98 headless, Node 20.19.4, Apple M1 Pro, macOS 15.6 |
| Mobile preset | Lighthouse default: 412x823 at 1.75 DPR (Moto G Power user agent), simulated slow 4G (150 ms RTT, 1.6 Mbps down, 4x CPU slowdown) |
| Desktop preset | `--preset=desktop` (1350x940, 40 ms RTT, 10 Mbps, no CPU slowdown), home and product only |
| Categories | performance, accessibility, best-practices, seo |
| Runs | each page twice, the better run kept (higher performance score, then lower LCP). Accessibility, best practices and SEO were identical between the two runs of every page |
| Noise | other agents ran servers and tests on the same Mac (load average 5 to 7). The two runs of a page differ by 0 to 2 points (up to 0.6 s on the solutions page in the prod-like pass); the benchmark index was 2730 to 2890 on every run |
| Server | a **snapshot copy** of `examleaf-web` (code, `.env`, a copy of `db.sqlite3`) in the scratchpad, started with `manage.py runserver --noreload`: edits made meanwhile by other agents could not change a run, and the real database was not touched |
| Signed-in pages | a temporary non-staff student (no usable password, session made with `Client.force_login`) with one book in the cart, passed as `--extra-headers '{"Cookie":"sessionid=..."}'`. The user, its cart and the copy were deleted at the end; the session ids were scrubbed from the saved HTML |
| Pages | `/`, `/shop/`, `/shop/physics-sample-papers-2027/`, `/cart/`, `/checkout/`, `/s/PHY-E01/`, `/account/`, `/account/login/`, `/privacy/`, a 404 |

Two measurement passes, because the dev server hides some things and exaggerates others:

1. **Dev server** (port 8090), as asked: `DEBUG=1` from `.env`.
2. **Production-like** (port 8091), added: `DEBUG=0` with a throwaway secret key, `collectstatic` with WhiteNoise's hashed and pre-compressed files (brotli for text, `max-age=315360000, immutable`), `GZipMiddleware` standing in for Caddy's `encode zstd gzip`, the enforced CSP, `SMS_BACKEND=msg91` with a dummy key so the phone-login form is on the login page as in production, https redirect and HSTS off (plain http on localhost). It also serves the **real 404 page**: with `DEBUG=1` Django answers every 404 with its own technical page, so the dev "404" row is not the site's page.

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
| Home `/` | **98** | 100 | 100 | 100 | 1.2 s | 2.3 s | 0 ms | 0 | 1.2 s | 40 ms | 218 KiB | 14 | 98 / 2.4, 98 / 2.3 (kept #2) |
| Shop `/shop/` | **100** | 100 | 100 | 100 | 1.1 s | 1.7 s | 0 ms | 0 | 1.1 s | 42 ms | 200 KiB | 13 | 100 / 1.7, 100 / 1.7 (kept #2) |
| Product `/shop/physics-sample-papers-2027/` | **99** | 100 | 100 | 100 | 1.2 s | 1.8 s | 0 ms | 0 | 1.2 s | 57 ms | 123 KiB | 11 | 99 / 1.8, 99 / 1.8 (kept #2) |
| Cart `/cart/` (1 item, signed in) | **100** | 100 | 100 | 66 | 1.0 s | 1.3 s | 0 ms | 0 | 1.0 s | 121 ms | 85 KiB | 11 | 100 / 1.3, 100 / 1.5 (kept #1) |
| Checkout `/checkout/` (signed in) | **100** | 100 | 100 | 66 | 1.2 s | 1.5 s | 0 ms | 0 | 1.2 s | 29 ms | 86 KiB | 12 | 100 / 1.5, 100 / 1.5 (kept #1) |
| Solutions `/s/PHY-E01/` (signed in) | **99** | 100 | 100 | 100 | 1.7 s | 1.9 s | 47 ms | 0 | 1.7 s | 45 ms | 219 KiB | 19 | 97 / 2.4, 99 / 1.9 (kept #2) |
| My account `/account/` (signed in) | **100** | 100 | 100 | 66 | 1.2 s | 1.5 s | 0 ms | 0 | 1.2 s | 16 ms | 79 KiB | 10 | 100 / 1.5, 100 / 1.5 (kept #2) |
| Login `/account/login/` | **100** | 100 | 100 | 66 | 1.5 s | 1.5 s | 0 ms | 0 | 1.5 s | 24 ms | 84 KiB | 13 | 100 / 1.5, 100 / 1.5 (kept #2) |
| Legal `/privacy/` | **100** | 100 | 100 | 100 | 1.2 s | 1.5 s | 0 ms | 0 | 1.2 s | 17 ms | 80 KiB | 10 | 100 / 1.5, 100 / 1.5 (kept #2) |
| 404 `/no-such-page-xyz/` | **98** | 100 | 96 | 61 | 1.2 s | 2.4 s | 0 ms | 0 | 1.2 s | 17 ms | 215 KiB | 14 | 98 / 2.4, 98 / 2.4 (kept #2) |

Notes. Compression and cache headers alone move home 95 to 98, shop 97 to 100, solutions 90 to 99, account 99 to 100 and cut the transferred weight by 25 to 50 percent (home 300 to 218 KiB, solutions 343 to 219 KiB, account 153 to 79 KiB). The 404 row is the real branded page: SEO 61 (HTTP 404 status and `noindex`) and best practices 96 (the 404 response itself is logged as a console error) are expected for an error page. The 404 page repeats the home page's four cover tiles, hence 215 KiB and LCP 2.4 s (see P2).

### 3.3 Desktop preset

Dev server:

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Speed Index | TTFB | Bytes | Req | Runs (perf / LCP s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Home `/` | **100** | 100 | 100 | 100 | 0.4 s | 0.6 s | 0 ms | 0 | 0.4 s | 40 ms | 300 KiB | 14 | 100 / 0.6 (kept #1) |
| Product `/shop/physics-sample-papers-2027/` | **100** | 100 | 100 | 100 | 0.4 s | 0.5 s | 0 ms | 0 | 0.4 s | 58 ms | 198 KiB | 11 | 100 / 0.5 (kept #1) |

Production-like:

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | Speed Index | TTFB | Bytes | Req | Runs (perf / LCP s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Home `/` | **100** | 100 | 100 | 100 | 0.3 s | 0.5 s | 0 ms | 0 | 0.3 s | 17 ms | 217 KiB | 14 | 100 / 0.5 (kept #1) |
| Product `/shop/physics-sample-papers-2027/` | **100** | 100 | 100 | 100 | 0.3 s | 0.4 s | 0 ms | 0.001 | 0.3 s | 27 ms | 122 KiB | 11 | 100 / 0.4 (kept #1) |

Desktop is not a concern: 100 on all four categories, LCP 0.4 to 0.6 s.

### 3.4 What the bytes are made of (production-like, mobile; KiB transferred)

| Page | Total | Images | Fonts | CSS | JS | HTML | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Home | 218 KiB (dev 300) | 137 | 48 | 15 | 2 | 7 | 9 |
| Shop | 200 KiB (dev 279) | 121 | 48 | 15 | 2 | 5 | 9 |
| Product | 123 KiB (dev 198) | 43 | 48 | 15 | 2 | 6 | 9 |
| Cart | 85 KiB (dev 159) | 7 | 48 | 15 | 2 | 5 | 9 |
| Checkout | 86 KiB (dev 162) | 7 | 48 | 15 | 2 | 6 | 9 |
| Solutions | 219 KiB (dev 343) | 0 | 96 | 19 | 79 | 17 | 7 |
| My account | 79 KiB (dev 153) | 0 | 48 | 15 | 2 | 5 | 9 |
| Login | 84 KiB (dev 165) | 0 | 48 | 15 | 7 | 5 | 9 |
| Privacy | 80 KiB (dev 154) | 0 | 48 | 15 | 2 | 6 | 9 |
| 404 | 215 KiB (dev 18) | 137 | 48 | 15 | 2 | 4 | 9 |


Images are 63 percent of the home page and 60 percent of the shop page; the 14 KiB of CSS (78 KiB raw) and 48 KiB of fonts (four woff2 files) are the same on every page; JavaScript is 2 KiB except on the login page (7 KiB, allauth's passkey scripts) and the solutions page (79 KiB, KaTeX and `math.js`).

### 3.5 Lab INP (interaction latency), 375 px, 4x CPU slowdown

| Page | Interactions timed | Worst interaction | What it was |
|---|---:|---:|---|
| Home | 3 | 56 ms | Menu label, FAQ summary |
| Product | 4 | 40 ms | copies - / + buttons, typing in the box |
| Cart | 1 | 56 ms | copies stepper, Remove dialog |
| Login | 3 | 24 ms | typing a mobile number, opening the password form |
| Checkout | 2 | 32 ms | typing a name and a PIN code (starts the PIN lookup) |
| Solutions | 4 | 104 ms | opening "Instructions", typing marks (12,239-node page) |


All below 110 ms ("good" is 200 ms or less). The probe clicked and typed through Puppeteer and read the Event Timing API (worst interaction per page; values are rounded to 8 ms and include the next paint). The slowest is the solutions page because of its 12,239-node DOM.

## 4. Findings, in priority order

### 4.1 Accessibility (Lighthouse's automated rules)

None failing, on any page, in either pass (score 100). axe-core 4.14 run separately on 19 states that Lighthouse does not reach (menu open, Remove dialog open, three error pages after an invalid submit, toast, desktop widths) found one violation, `scrollable-region-focusable` on the solutions page; see [audit-accessibility.md](audit-accessibility.md), which also holds everything the automated rules cannot see.

### 4.2 Performance (real defects, production-like numbers)

**P1. Render-blocking `site.css` and a two-step font chain. Priority: high, effort: medium. All pages.**
- Where: `<link rel="stylesheet" href="{% static 'css/site.css' %}">` in `templates/base.html`. The file is 78 KiB raw, 14 KiB brotli, one request. Estimated saving by Lighthouse (`render-blocking-insight`): home 560 ms, shop 420, product 420, cart 150, checkout 420, solutions 810, account 590, login 880, privacy 580, 404 580 (mobile); 150 to 160 ms on desktop.
- The fonts `poppins-700.woff2` and `hind-siliguri-600.woff2` are found only after the CSS is parsed (HTML, then CSS, then fonts: `network-dependency-tree-insight`); only `poppins-800` and `hind-siliguri-400` are preloaded in `base.html`.
- About 80 percent of the file is unused on any one page (`unused-css-rules`: 11 to 13 KiB of the 14 KiB, every page except home) and 22 percent is whitespace and comments (`unminified-css`: 3.3 KiB compressed, 17 KiB raw).
- LCP is a text node on 8 of 10 pages (for example `section.band > div.container > div.hero-copy > p.lead` on home), so LCP waits for CSS and fonts. Blocking the font files alone moved home LCP from 2.3 s to 2.1 s (experiment, section 5).
- Fix, cheapest first: minify the CSS in the build (rcssmin, lightningcss or esbuild before `collectstatic`); preload the two other fonts used above the fold or drop those two weights; split the stylesheet into a small shared file (tokens, layout, buttons, header, footer) and per-section files (shop, account, solutions). The CSP rules out the `media="print" onload` trick (no inline event handlers), so every file stays blocking and the gain is size.

**P2. Home page: four eager cover images. Priority: high, effort: small. `/` and the 404 page.**
- Where: `div.grid.tiles > a.tile > picture > img` in `templates/home.html` ("Open a book, then any paper's solutions"): `biology-320.avif` 38 KiB, `chemistry-320` 34, `mathematics-320` 31, `physics-320` 30. That is 137 KiB of the 218 KiB page. They are displayed 196x277 CSS px, below the hero on a phone, yet fetched at High priority in the same burst as the CSS and the fonts (`image-delivery-insight`: 97 KiB estimated saving on mobile, 105 KiB on desktop: a 320x452 file for a 196x277 box, plus 10 to 15 KiB each of compression headroom).
- Evidence: blocking `*.avif` in Lighthouse took home from LCP 2.3 s and performance 98 to LCP 1.7 s and performance 100 (section 5). The images compete with the render-blocking CSS and fonts for the simulated 1.6 Mbps.
- Fix: `loading="lazy" decoding="async"` on the four tile images (not on the hero stage covers); add a 200 or 240 px width to their `srcset` with `sizes="(max-width: 767px) 80vw, 25vw"`; re-encode the AVIFs about 10 quality points lower.

**P3. Shop: the LCP image is lazy-loaded. Priority: medium, effort: one line. `/shop/` (and any listing that opens with a bundle card).**
- Where: `templates/shop/catalogue.html`, line 40, `div.fan > span.cover > picture > img` (`/shop/media/products/physics/2_3/300w.avif`): `{% picture ... img_loading="lazy" ... %}`. Lighthouse `lcp-discovery-insight` fails on two checks: `fetchpriority=high` missing, and `loading=lazy` on the LCP resource. LCP 1.7 s (2.6 s on the dev server).
- Fix: for the first cover of the first card use `img_loading="eager"` and `img_fetchpriority="high"`; keep the rest lazy. (`image-delivery-insight` adds 15 KiB of AVIF compression headroom on the 300w and 400w files.)

**P4. Solutions page: KaTeX from jsDelivr and a very large DOM. Priority: medium, effort: medium. `/s/<CODE>/` (measured on `/s/PHY-E01/`; performance 99 prod-like, 90 dev).**
- Where: `templates/solutions.html` loads `katex.min.css` from `cdn.jsdelivr.net` (render-blocking, third-party: 898 ms estimated), three KaTeX fonts with no `font-display` (`KaTeX_Main-Regular`, `KaTeX_Size2-Regular`, `KaTeX_Math-Italic`: 50 to 60 ms each, `font-display-insight`), then `static/js/math.js` renders the whole page: 12,239 DOM elements, depth 39, a 40 ms forced reflow, five long tasks (140, 118, 77, 57, 52 ms; `math.js` itself 118 ms), TBT 47 ms, max potential FID 120 ms.
- Fix: self-host the KaTeX CSS, JS and the three fonts under `/static/` (hashed and immutable like the rest, no second TLS connection, `KATEX_CDN` leaves the CSP) and preload the three fonts; if that is not wanted, add `<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>`. To shorten the long task, render maths per question when it scrolls into view (IntersectionObserver) instead of all at once.

**P5. Login page: three parser-blocking passkey scripts. Priority: medium, effort: small. `/account/login/` (and the other pages that include allauth's passkey snippet).**
- Where: `/static/mfa/js/webauthn-json.js`, `webauthn.js` and `/static/account/js/onload.js`, plain `<script src>` placed before the deferred `site.js` (`mfa/webauthn/snippets/login_script.html`, included from `templates/account/login.html`). Lighthouse lists them as render-blocking (about 300 ms); login FCP is 1.5 s against 1.2 s on the other pages. On the dev server `webauthn-json.js` is also flagged unminified (2.2 KiB).
- Fix: override the snippet in `templates/mfa/webauthn/snippets/` and add `defer` to the three tags, keeping their order; check that `onload.js` runs on DOMContentLoaded (it should, by design; not verified here).

**P6. Product pictures cache for one day. Priority: low, effort: one line. `/shop/`, product, cart and checkout.**
- Where: `/shop/media/products/<name>/2_3/{100w,300w,400w}.avif` are sent with `Cache-Control: public, max-age=86400` by `shop.views.product_media` (`cache-insight`: shop 48 KiB, product 17 KiB, cart and checkout 3 KiB for the 100w thumbnail).
- In production the "public" storage is R2 behind `PUBLIC_MEDIA_DOMAIN` with a one-year immutable cache (comment in `settings.py`), so this matters only for single-server installs without buckets. File names are never reused, so `product_media` can send `max-age=31536000, immutable`.

**P7. Minor, no action needed unless convenient.**
- CLS is 0 everywhere except cart (0.005): `aside.summary-card` moves a few pixels when `site.js` unhides the copies stepper (`button.hidden = false`). Reserve the space (`visibility:hidden` instead of `hidden`) if you want exactly 0.
- `identical-links-same-purpose` is informative only (two "Choose a subject" links on home); it is an accessibility point, see the other file.

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
| `unminified-javascript` on `webauthn-json.js` | login | Small enough after compression to pass in the prod-like pass (see P5 for the blocking). |
| Unhashed static URLs without `Cache-Control` | all | `CompressedManifestStaticFilesStorage` (hashed names, `max-age=315360000, immutable`) when `DEBUG=0`. |

### 4.5 Audit index (every failing or warning audit in either pass)

| Audit | Pages (production-like) | See |
|---|---|---|
| `render-blocking-insight` | all ten | P1 (P4 for KaTeX, P5 for login) |
| `network-dependency-tree-insight` | all ten | P1 |
| `unminified-css` | all ten | P1 |
| `unused-css-rules` | all but home | P1 |
| `image-delivery-insight` | home, 404, shop | P2, P3 |
| `lcp-discovery-insight` | shop | P3 |
| `font-display-insight`, `forced-reflow-insight`, `max-potential-fid` | solutions | P4 |
| `cache-insight` | shop, product, cart, checkout | P6 |
| `is-crawlable` | cart, checkout, account, login, 404 | 4.3 (by design) |
| `http-status-code`, `errors-in-console`, `bf-cache` | 404 | 4.3 (expected) |
| `document-latency-insight`, `unminified-javascript`, `viewport-insight`, `meta-description` | dev only | 4.4 |

## 5. Experiments (production-like home page, mobile, two runs each)

| Condition | Performance | FCP | LCP | Bytes |
|---|---:|---:|---:|---:|
| As served | 98 | 1.2 s | 2.3 to 2.4 s | 218 KiB |
| The four cover AVIFs blocked (`--blocked-url-patterns=*.avif`) | 100 | 1.2 s | 1.7 s | 81 KiB |
| The four woff2 fonts blocked | 99 | 1.2 s | 2.1 s | 170 KiB |

FCP does not move: it is set by the HTML and the CSS. Blocking the images is an upper bound for what lazy-loading them can give (the images would still load, later); blocking the fonts is an upper bound for what preloading the other two can give.

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
