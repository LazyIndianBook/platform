# ExamLeaf Next.js frontend: Lighthouse audit (performance, accessibility, best practices, SEO)

Measured on 8 October 2026 (IST) on the production build of `examleaf-frontend/` (Next.js 16.4.0, Turbopack) at commit `b10bde1` (the Phase 8D build half), against the Django backend at the same commit. Nothing under `examleaf-frontend/` or `examleaf-web/` was edited (the build wrote `examleaf-frontend/.next/`, which git ignores). The keyboard, zoom and axe side is in [audit-nextjs-accessibility.md](audit-nextjs-accessibility.md), the security review in [audit-nextjs-security.md](audit-nextjs-security.md). The Django site's numbers, for comparison, are in [audit-lighthouse.md](audit-lighthouse.md).

## 1. In one minute

- **Scores are high and the weak spot is one number.** Mobile, simulated slow 4G, best of two runs: accessibility **100** on all 12 pages; best practices 100 (96 on login and on the 404 page); SEO 100 on the public pages and 61 to 66 on the pages that say `noindex` on purpose; performance **93 to 98**. Desktop: 100 on all four categories, LCP 0.6 and 0.7 s.
- **Against the Django site the frontend is slower in the lab and 2 to 4 times heavier**: LCP +0.2 to +1.4 s (home 2.8 s against 2.3 s, product 3.1 against 1.8, privacy 2.9 against 1.5), 264 to 494 KiB against 78 to 219 KiB, 21 to 34 requests against 10 to 19. The difference is JavaScript: **173 to 205 KB gzipped per route against 2 KiB**.
- **That JavaScript is the whole LCP story (L1, L2).** The same pages with the `<script>` tags removed score 100 with LCP 1.4 to 1.5 s; with only React, react-dom and the Next router left (125 KB gzipped) LCP is 1.7 to 2.8 s. The architecture document's budget (LCP ≤ 2.5 s on `/`, `/shop/`, a product, `/s/<code>/`, `/account/login/`) is **missed on four of the five pages** (2.8, 2.8, 3.1 and 3.1 s; login 2.3 s passes). The framework alone nearly uses the budget.
- **One real defect, not a budget** (L3): `/account/` shifts its footer by about 1,000 px when the page replaces its placeholder: CLS **0.295 in 4 of 8 runs** (performance 82 to 84 instead of 97 to 98). The other pages are at 0 to 0.008.
- Other budget misses and fixes: the two solutions pages' HTML is 92 and 86 KB gzipped against 60 KB (the inline RSC payload repeats the markup, L4); the four home covers are 97 KiB heavier than their boxes need, as on the Django site (L5); login logs a 401 to the console (best practices 96, L6).
- Accessibility is 100 everywhere, but Lighthouse cannot see what the manual pass found; read the accessibility file (a page that scrolls sideways on every phone, keyboard focus lost after cart steps, the Menu's tab order, a toast that lives 300 ms).

## 2. How it was measured

| Item | Value |
|---|---|
| Tool | Lighthouse 13.5.0 (CLI), Chrome 154.0.8037.98 headless (`--headless=new`), Node 20.19.4, Apple M1 Pro, macOS 15.6 |
| Mobile preset | Lighthouse default: 412x823 at 1.75 DPR, simulated slow 4G (RTT 150 ms, 1,638 kbps, request latency 562 ms), 4x CPU slowdown |
| Desktop preset | `--preset=desktop`, home and product only |
| Categories | performance, accessibility, best-practices, seo |
| Runs | each page twice, the better run kept (higher performance, then lower LCP); the 404 page with `--ignore-status-code`. Accessibility, best practices and SEO were identical between the two runs of every page |
| Noise | other agents' servers and tests ran on the same Mac (load average 4.5). Benchmark index 2690 to 2937 on every run (the Django audit: 2730 to 2890). Two runs of a page differ by 0 to 3 points, except `/shop/` (95 and 89, LCP 2.8 and 3.7 s) and `/account/` (the CLS finding) |
| Frontend | `NEXT_PUBLIC_SITE_URL=http://localhost:3003 npm run build`, then the **standalone output** (`.next/standalone` + `.next/static` + `public`, copied to a scratch folder so that another builder's rebuild could not change a run) started with `node server.js` as the Dockerfile does: `NODE_ENV=production PORT=3003 API_INTERNAL_BASE=http://localhost:8103`. The headers, bundles and routes are those of `npm start` |
| Backend | `manage.py runserver 8103 --noreload` (development settings, `DEBUG=1`, the shared SQLite database with `transaction_mode=IMMEDIATE`), `SITE_URL` and `CSRF_TRUSTED_ORIGINS` set to the frontend's origin, `USE_X_FORWARDED_HOST=1`; 24 to 25 copies of each book in stock. TTFB therefore includes Django's development server |
| Signed-in pages | a temporary non-staff student logged in through the frontend's own email-code form (the code read from Django's console log), its `sessionid` and `csrftoken` passed with `--extra-headers`; one Physics Sample Papers in its cart. The student, its order, address, marks and sessions were deleted at the end |
| Pages | `/`, `/shop/`, `/shop/physics-sample-papers-2027/`, `/cart/` (1 item), `/checkout/`, `/s/PHY-E01/` (open sample, anonymous), `/s/PHY-E02/` (signed in), `/account/`, `/account/login/`, `/revision/`, `/privacy/`, a 404 |

Deviations from the brief, and why:

- **No Caddy.** Local runs are plain HTTP/1.1 with Next's own gzip standing in for Caddy's `encode zstd gzip`; HSTS, `upgrade-insecure-requests` and HTTP/2 are not exercised. Razorpay, Turnstile and Google have no keys here, so no page loaded a third-party host.
- **COOP was left on.** The Django audit had to switch `Cross-Origin-Opener-Policy` off because Lighthouse 13.5 on Chrome 154 stopped with `NO_NAVSTART` on it. The frontend sends `same-origin` on every page and Lighthouse traced all of them; three runs out of about 50 (two `NO_NAVSTART`, one that hung for 200 s) were repeated by the script, which allows three attempts.
- **INP is not in navigation runs.** The INP column is a lab probe: the Event Timing API on real clicks and key presses at 375 px with 4x CPU slowdown, the worst interaction per page (values are rounded to 8 ms and include the next paint; only interactions of 16 ms or more are reported).
- The Django comparison uses the Django audit's *production-like* pass (compressed, hashed static files); its development-server pass is slower still.

## 3. Scores and metrics

Columns: the four category scores; FCP, LCP, TBT, CLS (lab); INP is the probe above; TTFB is the document's server response time; Bytes is `total-byte-weight`, Req the number of requests in the trace (it includes the router's background prefetches, 2 to 16 per page, see L8); the last column gives both runs as performance score / LCP in seconds.

### 3.1 Mobile (slow 4G, 4x CPU)

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | INP (lab) | TTFB | Bytes | Req | Runs (perf / LCP s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Home `/` | **96** | 100 | 100 | 100 | 0.9 s | 2.8 s | 14 ms | 0 | 40 ms | 77 ms | 414 KiB | 34 | 95 / 3.0, 96 / 2.8 (kept #2) |
| Shop `/shop/` | **95** | 100 | 100 | 100 | 1.1 s | 2.8 s | 36 ms | 0.006 | 24 ms | 34 ms | 494 KiB | 31 | 95 / 2.8, 89 / 3.7 (kept #1) |
| Product `/shop/physics-sample-papers-2027/` | **94** | 100 | 100 | 100 | 0.9 s | 3.1 s | 17 ms | 0.008 | 16 ms | 24 ms | 313 KiB | 26 | 94 / 3.1, 94 / 3.1 (kept #1) |
| Cart `/cart/` (1 item, signed in) | **96** | 100 | 100 | 66 | 0.9 s | 2.8 s | 22 ms | 0 | 40 ms | 125 ms | 293 KiB | 29 | 94 / 3.0, 96 / 2.8 (kept #2) |
| Checkout `/checkout/` (signed in) | **96** | 100 | 100 | 63 | 0.9 s | 2.8 s | 18 ms | 0 | 24 ms | 103 ms | 273 KiB | 24 | 93 / 3.3, 96 / 2.8 (kept #2) |
| Solutions `/s/PHY-E01/` (open sample, anonymous) | **93** | 100 | 100 | 100 | 1.4 s | 3.1 s | 28 ms | 0 | 72 ms | 119 ms | 349 KiB | 24 | 93 / 3.1, 93 / 3.1 (kept #2) |
| Solutions `/s/PHY-E02/` (signed in) | **95** | 100 | 100 | 100 | 2.0 s | 2.7 s | 33 ms | 0 | 72 ms | 268 ms | 415 KiB | 31 | 95 / 2.7, 95 / 2.9 (kept #1) |
| My account `/account/` (signed in) | **97** | 100 | 100 | 66 | 0.9 s | 2.7 s | 20 ms | **0** (4 of 8 runs: **0.295**) | 16 ms | 252 ms | 298 KiB | 34 | 97 / 2.7, 82 / 2.7 (kept #1); six more runs: 84, 82, 97, 98, 84, 97 |
| Login `/account/login/` | **98** | 100 | **96** | 66 | 0.9 s | 2.3 s | 19 ms | 0 | 16 ms | 31 ms | 270 KiB | 24 | 98 / 2.3, 97 / 2.5 (kept #1) |
| Revision `/revision/` | **98** | 100 | 100 | 100 | 0.9 s | 2.3 s | 33 ms | 0 | n/a | 53 ms | 267 KiB | 21 | 95 / 3.0, 98 / 2.3 (kept #2) |
| Legal `/privacy/` | **95** | 100 | 100 | 100 | 0.9 s | 2.9 s | 32 ms | 0 | n/a | 13 ms | 264 KiB | 21 | 95 / 2.9, 95 / 2.9 (kept #1) |
| 404 `/no-such-page-xyz/` | **96** | 100 | **96** | 61 | 0.9 s | 2.8 s | 51 ms | 0 | n/a | 64 ms | 401 KiB | 32 | 94 / 3.1, 96 / 2.8 (kept #2) |

Notes. SEO 61 to 66 is `is-crawlable` failing on pages that say `noindex` on purpose (cart, checkout, account, login, 404); the 404 also fails `http-status-code`; the 63 of the checkout against 66 of the cart is only the weighting of audits that do not apply (no image, no canonical). Best practices 96 is `errors-in-console`: the 404 response itself on the 404 page (expected), a 401 on login (L6). Accessibility is 100 on every page and in every run.

### 3.2 Desktop preset

| Page | Perf | A11y | BP | SEO | FCP | LCP | TBT | CLS | TTFB | Bytes | Req |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Home `/` | **100** | 100 | 100 | 100 | 0.2 s | 0.6 s | 0 ms | 0 | 20 ms | 412 KiB | 38 |
| Product | **100** | 100 | 100 | 100 | 0.3 s | 0.7 s | 0 ms | 0 | 18 ms | 320 KiB | 34 |

Desktop is not a concern (Django, production-like: 100, LCP 0.5 and 0.4 s).

### 3.3 What the bytes are made of (kept mobile runs, KiB transferred)

| Page | Total | Images | Fonts | CSS | JS | HTML | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Home | 414 | 138 | 46 | 14 | 173 | 23 | 20 |
| Shop | 494 | 222 | 46 | 15 | 180 | 17 | 14 |
| Product | 313 | 44 | 46 | 14 | 180 | 16 | 14 |
| Cart | 293 | 7 | 46 | 14 | 197 | 13 | 17 |
| Checkout | 273 | 0 | 46 | 14 | 184 | 14 | 15 |
| Solutions, open sample | 349 | 0 | 46 | 21 | 178 | **92** | 13 |
| Solutions, signed in | 415 | 0 | 88 | 21 | 202 | **86** | 18 |
| My account | 298 | 0 | 46 | 14 | 205 | 13 | 20 |
| Login | 270 | 0 | 46 | 14 | 184 | 12 | 14 |
| Revision | 267 | 0 | 46 | 14 | 180 | 17 | 11 |
| Privacy | 264 | 0 | 46 | 14 | 179 | 15 | 11 |
| 404 | 401 | 138 | 46 | 14 | 179 | 8 | 16 |

"Other" is the web manifest, the icons and the router's `?_rsc=` prefetches. JavaScript is 67 to 69 percent of every page that has no images (51 percent of the open solutions page, whose HTML is large); the Django pages carried 2 KiB (7 on login, 79 on the solutions page with KaTeX). The raw (uncompressed) HTML of the two solutions pages is 1.41 MB and 1.19 MB.

### 3.4 Lab INP (interaction latency), 375 px, 4x CPU slowdown

| Page | Interactions reported | Worst | What it was |
|---|---:|---:|---|
| Home | 2 | 40 ms | Menu button open and close |
| Shop | 1 | 24 ms | a subject tab |
| Product | 4 | 16 ms | copies buttons, typing the number |
| Cart | 4 | 40 ms | copies stepper, Remove dialog |
| Login | 1 | 16 ms | typing a mobile number |
| Checkout | 4 | 24 ms | typing a name and a PIN code |
| Solutions (signed in) | 4 | 72 ms | opening "Instructions", typing marks (12,000-tag page) |
| My account | 1 | 16 ms | Menu |

All well under 200 ms. TBT is 14 to 51 ms on every page.
