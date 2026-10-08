# ExamLeaf Next.js frontend: Lighthouse audit (performance, accessibility, best practices, SEO)

Measured on 8 October 2026 (IST) on the production build of `examleaf-frontend/` (Next.js 16.4.0, Turbopack) at commit `b10bde1` (the Phase 8D build half; the build was made at 16:38 from the working tree as it stood), against the Django backend running from the same tree. Nothing under `examleaf-frontend/` or `examleaf-web/` was edited (the build wrote `examleaf-frontend/.next/`, which git ignores). The keyboard, zoom and axe side is in [audit-nextjs-accessibility.md](audit-nextjs-accessibility.md), the security review in [audit-nextjs-security.md](audit-nextjs-security.md). The Django site's numbers, for comparison, are in [audit-lighthouse.md](audit-lighthouse.md).

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
| Units | sizes are KiB (1,024 bytes) throughout; "KB" in the text means the same |
| Noise | other agents' servers and tests ran on the same Mac (load average 4.5). Benchmark index 2690 to 2937 on every run (the Django audit: 2730 to 2890). Two runs of a page differ by 0 to 3 points, except `/shop/` (95 and 89, LCP 2.8 and 3.7 s) and `/account/` (the CLS finding) |
| Frontend | `NEXT_PUBLIC_SITE_URL=http://localhost:3003 npm run build`, then the **standalone output** (`.next/standalone` + `.next/static` + `public`, copied to a scratch folder so that another builder's rebuild could not change a run) started with `node server.js` as the Dockerfile does: `NODE_ENV=production PORT=3003 API_INTERNAL_BASE=http://localhost:8103`. The headers, bundles and routes are those of `npm start` |
| Backend | one process, started at 16:38 from the clean tree at `b10bde1`, served the 26 main runs, the repeated account runs, the script-removal experiment, the INP probe and the screenshots (the framework-only experiment and the footer tracking of L3 ran about an hour later against a restart of the same API from a snapshot of `git HEAD`): `manage.py runserver 8103 --noreload` (development settings, `DEBUG=1`, the shared SQLite database with `transaction_mode=IMMEDIATE`), `SITE_URL` and `CSRF_TRUSTED_ORIGINS` set to the frontend's origin, `USE_X_FORWARDED_HOST=1`; 24 to 25 copies of each book in stock. TTFB therefore includes Django's development server |
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

"Other" is the web manifest, the icons and the router's `?_rsc=` prefetches. JavaScript is 67 to 69 percent of every page that has no images (51 percent of the open solutions page, whose HTML is large); the Django pages carried 2 KiB (7 on login, 79 on the solutions page with KaTeX). The uncompressed HTML of the two solutions pages is 1,409 KiB and 1,191 KiB.

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

## 4. The architecture document's budgets

From "Performance and accessibility budgets for the current frontend" in `docs/examleaf-frontend-architecture.md` (lab, mid-range Android profile, slow 4G).

| Budget | Measured | Verdict |
|---|---|---|
| LCP ≤ 2.5 s on `/`, `/shop/`, a product page, `/s/<code>/`, `/account/login/` | 2.8 s, 2.8 s, 3.1 s, 3.1 s (open sample; 2.7 s signed in), 2.3 s | **missed on four of the five** (L1). The other pages: cart 2.8, checkout 2.8, account 2.7, privacy 2.9, 404 2.8; only revision (2.3) and login pass |
| CLS ≤ 0.1 | 0 on ten of the twelve pages; shop 0.006, product 0.008; `/account/`: 0.295 in 4 of 8 runs | missed on `/account/` (L3) |
| INP ≤ 200 ms | 16 to 72 ms (lab probe) | pass |
| HTML ≤ 60 KB | 8 to 23 KB gzipped on ten pages; **92 KB** (`/s/PHY-E01/`) and **86 KB** (`/s/PHY-E02/`) | missed on the solutions pages (L4) |
| CSS ≤ 60 KB | 14.3 KB gzipped (62.7 KB raw), 20.5 KB (93 KB raw) with KaTeX's | pass as transferred; a little over if the budget means the uncompressed file |
| Fonts ≤ 60 KB Latin | 45.6 KB (four files); 88.3 KB on the signed-in solutions page, which adds two KaTeX files | pass (KaTeX's fonts are separate) |
| Hero images ≤ 150 KB in total | home 138 KB | pass, with 97 KiB of it avoidable (L5) |
| No third-party scripts except KaTeX (solutions) and Razorpay (payment page) | none on the twelve pages; KaTeX is self-hosted; Razorpay only on `/checkout/**` (security file S2, S3) | pass |
| A JavaScript budget | none is written; the note on the 8A status calls "about 170 KB of JavaScript (gzip) for React and the App Router" a known cost | the shared JavaScript is 173 KB; of it 134 KB is React and Next, 39 KB is ExamLeaf's own (L2) |

The 8A status figures reproduce: home 96/100/100/100, LCP 2.8 s; `/s/PHY-E01/` 93 (then 94), LCP 3.1 s (then 3.0). Accessibility on the solutions page is now 100 (then 96).

## 5. Against the Django site

The Django audit's production-like pass, mobile, same tool and Chrome, same machine class; the Next figures are the kept runs above. The Django pages those numbers describe were removed from the repository at 16:59 today (commit `b6b8d06`), so they cannot be re-measured: the numbers are the earlier audit's.

| Page | Next.js: Perf / LCP / bytes / requests | Django: Perf / LCP / bytes / requests |
|---|---|---|
| Home | 96 / 2.8 s / 414 KiB / 34 | 98 / 2.3 s / 216 KiB / 14 |
| Shop | 95 / 2.8 s / 494 KiB / 31 | 100 / 1.7 s / 199 KiB / 13 |
| Product | 94 / 3.1 s / 313 KiB / 26 | 99 / 1.8 s / 122 KiB / 11 |
| Cart (1 item, signed in) | 96 / 2.8 s / 293 KiB / 29 | 100 / 1.5 s / 84 KiB / 11 |
| Checkout (signed in) | 96 / 2.8 s / 273 KiB / 24 | 100 / 1.4 s / 85 KiB / 12 |
| Solutions (Next: `/s/PHY-E02/` signed in; open sample 93 / 3.1 s) | 95 / 2.7 s / 415 KiB / 31 | 97 / 2.5 s / 219 KiB / 19 (signed in) |
| My account | 97 / 2.7 s / 298 KiB / 34 | 100 / 1.5 s / 78 KiB / 10 |
| Login | 98 / 2.3 s / 270 KiB / 24 | 100 / 1.5 s / 83 KiB / 13 |
| Legal (`/privacy/`) | 95 / 2.9 s / 264 KiB / 21 | 100 / 1.5 s / 79 KiB / 10 |
| 404 | 96 / 2.8 s / 401 KiB / 32 (BP 96, SEO 61) | 98 / 2.3 s / 213 KiB / 14 (BP 96, SEO 61) |
| Desktop home | 100 / 0.6 s / 412 KiB / 38 | 100 / 0.5 s / 216 KiB / 14 |
| Desktop product | 100 / 0.7 s / 320 KiB / 34 | 100 / 0.4 s / 122 KiB / 11 |

Accessibility is 100 and best practices 100 (96 on the same two pages) on both. The Django site had no revision page to compare, and measured only the signed-in solutions page. Tail latency and server cost are not in the comparison: every Next page is rendered per request (the nonce needs it) and makes 2 to 4 calls to Django, which the Django pages did in-process.

## 6. JavaScript bytes per route

Transferred (gzip) and uncompressed, summed over the page's script requests (kept mobile runs); the same files are cached across routes in a real session, so only the first page of a visit pays the shared 173 KB.

| Route | Scripts | Transferred | Uncompressed | Shared by every route | Route-specific |
|---|---:|---:|---:|---:|---:|
| `/` | 9 | 173.2 KB | 548 KB | 173.2 KB | 0 |
| `/shop/` | 10 | 179.9 KB | 565 KB | 173.2 KB | 6.7 KB |
| product | 10 | 179.9 KB | 565 KB | 173.2 KB | 6.7 KB |
| `/cart/` | 11 | 197.2 KB | 615 KB | 173.2 KB | 24.0 KB |
| `/checkout/` | 10 | 184.3 KB | 579 KB | 173.2 KB | 11.1 KB |
| `/s/PHY-E01/` (anonymous) | 10 | 177.8 KB | 559 KB | 173.2 KB | 4.6 KB |
| `/s/PHY-E02/` (signed in) | 12 | 201.8 KB | 625 KB | 173.2 KB | 28.6 KB |
| `/account/` | 13 | 204.5 KB | 632 KB | 173.2 KB | 31.3 KB |
| `/account/login/` | 10 | 183.9 KB | 577 KB | 173.2 KB | 10.7 KB |
| `/revision/` | 10 | 179.5 KB | 563 KB | 173.2 KB | 6.3 KB |
| `/privacy/` | 10 | 178.5 KB | 561 KB | 173.2 KB | 5.3 KB |
| 404 | 10 | 178.5 KB | 561 KB | 173.2 KB | 5.3 KB |

What the files are (identified by their contents; the build has no source maps, so Lighthouse's treemap shows whole files only):

| File | Gzip | Raw | What it holds | Loaded on |
|---|---:|---:|---|---|
| `0qhaqciba1wvt.js` | 72.2 KB | 228 KB | react-dom (Lighthouse: 26 to 29 KiB of it unused on every page) | every route |
| `0lo5zoq19faan.js` | 48.2 KB | 172 KB | the App Router's client (router, prefetch, RSC reader) | every route |
| `1jsd8w5f7d-go.js` | 17.2 KB | 41 KB | the site's shell: Button, icons (lucide), Radix Slot, the header | every route |
| `3hd0of63c0up9.js` | **15.7 KB** | 50 KB | **sonner, the toast library with its CSS** | every route, though a toast only appears after an action |
| `2zusw0t-z8qoc.js` | 6.2 KB | 20 KB | the header's drawer and links | every route |
| `1r2slleuw7gs5.js`, `turbopack-3-….js`, `077bzkpwilha0.js`, `01_20ff8cuuv3.js` | 13.7 KB | 37 KB | Next's runtime helpers, the chunk loader, small bootstraps | every route |
| `03_9zyzabu8nz.js` | 12.9 KB | 37 KB | Radix Dialog (the cart's Remove, the order's Cancel) | cart, account, signed-in solutions |
| `14-d7_qxtliia.js` | 11.0 KB | 30 KB | the forms' parts (fields, error summary, the Turnstile loader) | cart, account, signed-in solutions |
| `37g8kk_1acwof.js` | 11.0 KB | 31 KB | the checkout form, the pay button | checkout |
| `3xi-c7_liw0l2.js` | 10.6 KB | 28 KB | the login form with the OTP input | login |
| `1rly-zgbfy994.js` | 6.7 KB | 17 KB | product cards and the add-to-cart island | shop, product |
| `3_ecn1vvny92g.js` | 6.3 KB | 15 KB | the revision page's islands (hls.js itself, 113 KB gzipped, loads only when a clip plays) | revision |

So of the 173 KB every page pays, about **134 KB is React and Next** and **39 KB is ExamLeaf's own** (the shell 17.2, the toaster 15.7, the drawer 6.2).

## 7. Findings, in priority order

Severity: High = misses a budget by a wide margin or is a real defect on a core page; Medium = real but small; Low = tidy-up or by design.

### L1. LCP is over the 2.5 s budget on four of the five budget pages (High)

- **Where.** `/` 2.8 s, `/shop/` 2.8 s, the product page 3.1 s, `/s/PHY-E01/` 3.1 s (login 2.3 s passes); the pages outside the budget list are the same (privacy 2.9 s, 404 2.8 s). The LCP element is the hero's lead paragraph (`section.relative > div.container-site > div.flex > p.text-lead`) on `/`, the first cover (`span.cover > picture > img`, `fetchpriority="high"`) on the shop and the product page, a paragraph elsewhere.
- **Why.** The trace without throttling paints at 60 to 220 ms and `observedLargestContentfulPaint` equals the FCP. Lighthouse's estimate is the simulated path to that paint, and the simulation counts every request that had started before it: the 9 to 13 script files (173 to 205 KB gzipped), the four fonts and the stylesheet, all replayed at 1.6 Mbps. Section 9 isolates it: the same pages without scripts score 100 with LCP 1.4 to 1.5 s (about 8 ms of LCP per KB of gzipped JavaScript), and with only react-dom, the router and the runtime (124.8 KB) LCP is 1.7 to 2.8 s.
- **How real it is.** The real critical path is two steps (HTML, then the stylesheet) and the scripts are `async`, so a phone paints before they arrive; they compete with the images and fonts for the radio. The lab number is still the budget's definition, and it shows how little room is left: React and the router alone put the home page at 2.5 s.
- **Fix, in order of effect.** (a) Take what is ExamLeaf's own out of the shared bundle: load the toaster only when a message exists (15.7 KB gzipped on every route, `src/components/ui/toaster.tsx` imports `sonner` in the root layout), load Radix Dialog only when a dialog opens (12.9 KB on cart, account and the signed-in paper), split the forms' common chunk (11 KB). The toaster alone is 15.7 KB on every route (about 0.13 s in the lab); the dialog and the forms chunk add 24 KB on the cart, the account and the signed-in paper. (b) Decide what the budget measures: on this profile an App Router page cannot get under 2.5 s on every listed page whatever the app code does (home 2.5 s with zero app code), so either re-base the number (for example LCP ≤ 3.0 s on the simulated profile, with field data from the Chrome UX Report as the judge, as the architecture note already says) or gate on a DevTools-throttled run. (c) Keep text-only pages (legal, 404) as light as possible: they pay the full framework for a menu button.

### L2. 173 to 205 KB of JavaScript on every route (High, the cause of L1)

- **Where.** The table in section 6: 173.2 KB shared plus 0 to 31 KB per route; the Django pages carried 2 KiB. The accounts and the signed-in paper pay most (204.5 and 201.8 KB): Radix Dialog, the forms' parts and the paper's marks form.
- **What to cut.** The three items of L1 (a); the forms' common chunk (`14-d7_qxtliia.js`, with the Turnstile loader inside) is loaded by `/account/` as well as by the cart: check that the dashboard needs it; `1jsd8w5f7d-go.js` (17 KB) holds the whole site shell and icons: check that nothing in it is only needed after a click.
- **Not worth fighting.** react-dom's 26 to 29 KiB "unused" (`unused-javascript`) is code paths the page does not take, not removable by the app.

### L3. `/account/` shifts its footer by about 1,000 px: CLS 0.295 in 4 of 8 runs (High)

- **Where and how often.** `/account/`, element `body > footer.band-night`. Lighthouse: CLS 0.295 and performance 82 to 84 in four runs, 0 and 97 to 98 in the other four. The kept run in the table is a 0 run because the better run is kept; the HTML report of a 0.295 run is saved as `lighthouse-nextjs/account-mobile-cls.html`.
- **Cause, measured.** The account pages stream behind a placeholder (`(account)/account/(streamed)/loading.tsx`). Tracked frame by frame under the mobile profile, the first frame has `main` 476 px tall (seven grey bars) and the footer at y = 541, inside the 823 px first screen; 15 to 20 ms later (once 4.3 s later) the content arrives, `main` is 1,492 px and the footer jumps to y = 1,557. Whether the browser paints the placeholder between the two decides if it counts, hence 50 percent of the runs; on a real slow-4G phone the second part of the stream arrives later, so expect it more often there. The same placeholder is used by orders, record, details, addresses, security, teacher, 2FA and privacy (not measured by Lighthouse, same cause); cart and checkout have placeholders too and showed 0 in both of their runs.
- **Fix.** Give the placeholder the page's height (a `min-height` on `main` of about 60 rem), or drop `loading.tsx` from the pages whose data answers in about 250 ms (the placeholder buys nothing and costs the shift), or keep the footer out of the first screen until the content is there (`main { min-height: 100svh }`).

### L4. The two solutions pages' HTML is 92 and 86 KB gzipped against a 60 KB budget (Medium)

- **Where.** `/s/PHY-E01/` and `/s/PHY-E02/`: the document is 1,409 KiB and 1,191 KiB uncompressed, 92.2 and 85.7 KiB gzipped, about 12,000 tags and 214 formulas on E-01. Decompressed, E-01 is 1.44 MB: 468 KB is markup (33 KB gzipped) and **972 KB is the inline `self.__next_f.push(…)` RSC payload (60 KB gzipped)**: each solution's HTML (KaTeX's HTML and MathML) is sent once as markup and once more inside the flight data that React reads to hydrate. FCP is 1.4 s anonymous and 2.0 s signed in (TTFB 268 ms plus the transfer), TBT 28 to 33 ms, INP 72 ms: the cost is bytes and parse time rather than blocking.
- **Fix (untested).** Pass each question's solution to the browser as one pre-rendered HTML string (`dangerouslySetInnerHTML` of the server-rendered KaTeX output, as the Django site's `markdown` filter does) so the flight data holds a string instead of an element tree; or split a paper into its four groups (`/s/<code>/` anchors stay) and load later groups on demand; or leave the payload but drop what the markup repeats. `content-visibility: auto` on `.question` is already there and right.

### L5. The home page's four covers are 97 KiB heavier than their boxes need (Medium)

- **Where.** `/` (97 KiB on mobile, 105 KiB on desktop) and the 404 page, which repeats the four tiles: `<img src="/static/img/biology-320.avif" sizes="(min-width: 900px) 172px, 104px" …>` (physics, chemistry, mathematics the same). The boxes are 133 × 172 CSS px (about 233 device px at 1.75 DPR) and the `srcset` offers 320w and 480w only, so the browser takes 320w: 31 to 39 KB each. This is the Django audit's P2, carried over because the files are Django's `static/img/`. `image-delivery-insight` also reports 34 KiB on `/shop/` (the 400w covers in 230 px cards) and 19 KiB on the product page.
- **Fix.** As P2 in the Django audit: add a 200w and a 240w AVIF per cover to the `srcset`, re-encode about ten quality points lower; for the shop add a 300w to the sources of the card covers. Backend asset work (django-pictures sizes), no frontend change beyond the `sizes`.

### L6. Login logs a 401 to the console: best practices 96 (Medium)

- **Where.** `/account/login/` (and `/account/signup/`, seen in the console in the page scan): `GET /_allauth/browser/v1/auth/session` answers 401, allauth's normal answer for a visitor with no session, and Chrome logs a failed response as a console error, so `errors-in-console` fails. The request is `auth.session()` in `LoginForm`'s `useEffect` (to resume a pending code or a return from Google).
- **Fix.** Only ask when there is something to resume: the server page can read the `sessionid` cookie (`hasSessionCookie()`) and pass `resume` to the form; a visitor without the cookie has no pending flow and needs no call. Best practices goes to 100 on login and signup.

### L7. One render-blocking stylesheet, 90 to 540 ms estimated (Low)

- **Where.** Every page: `/_next/static/chunks/0zfcsffje63id.css`, 14.3 KB gzipped (62.7 KB raw, the whole Tailwind build); `/s/**` adds `1yq582wkzw12r.css` (KaTeX, 6.2 KB gzipped, 31 KB raw), `/shop/` a 0.4 KB `shop.css`. `render-blocking-insight`: home 110 ms, shop 240, product 90, cart 300, checkout 130, account 280, login 270, privacy 140, solutions 240 and 540.
- **Fix.** None recommended on its own: the file's download is most of the estimate and the Django audit found that inlining the whole stylesheet changed home FCP by 0.1 s. `experimental.inlineCss` would add about 14 KB gzipped to every HTML response, uncacheable; try it only after L1 (a).

### L8. 2 to 16 background prefetch requests per page (Low)

- **Where.** `?_rsc=` fetches right after load for every `<Link>` in view: `/account/` prefetches `/`, `/cart/`, `/shop/`, `/account/record/`, `/account/orders/` and `/account/details/` (12 requests, 11 KB in the kept run; the run with 48 requests also prefetched the four book pages, `/revision/`, `/shipping/` and `/refunds/`); home 12 (11 KB), desktop home 16 (15 KB), privacy 2. Each is the route's shell (a render on the Next server), `private, no-store`, no personal data (checked in the security file, section 3).
- **Fix.** `prefetch={false}` on the footer's and the account navigation's links; keep it for the primary navigation. No measurable change in the lab (they follow the load), but each is a server render and a request on a slow connection.

### L9. `/shop/` is the heaviest page and the least stable run (Low)

- **Where.** 494 KiB (222 KiB of images: nine covers) against 313 KiB for the product; the two runs gave 95 and 89 (LCP 2.8 and 3.7 s), the widest spread of any page except the account page's shift. The LCP element is the first cover (`fetchpriority="high"`, 300w); the other eight are lazy.
- **Fix.** L5's smaller cover variants; nothing else is wrong with the page.

### L10. Two tiny layout shifts (Low)

- `/shop/` 0.006: the featured card's second cover (`div.-ml-12.w-[150px].translate-y-2.rotate-3`); the product page 0.008: the buy column (`div.flex-[1_1_420px]`, as the add-to-cart island hydrates). Both far under 0.1; reserve the island's height if you want exactly 0.

### L11. By design or informational (no action)

| Audit | Pages | Why it is fine |
|---|---|---|
| `is-crawlable` (SEO 61 to 66) | cart, checkout, account, login, 404 | these pages say `noindex` on purpose |
| `http-status-code`, `errors-in-console` | 404 | the 404 response itself |
| `bf-cache` | cart, checkout, account, login, 404, signed-in solutions | `Cache-Control: no-store` on personal pages; the public pages restore from the back/forward cache (a side effect: the security file's S6) |
| `valid-source-maps` | both solutions pages | the build ships no source maps for the browser (intended; security file, "Dockerfile and image") |
| `font-display-insight` | signed-in solutions | KaTeX_Math-Italic, 5 ms |
| `network-dependency-tree-insight` | every page | a two-step chain (HTML, then CSS), nothing to preconnect |
| `max-potential-fid`, `interactive`, `first-contentful-paint`, `speed-index` | most pages | metric scores of 0.85 to 0.99, no separate fault |

## 8. Index of every audit below 1

| Audit | Pages | See |
|---|---|---|
| `largest-contentful-paint` | all 14 runs (the two desktop ones at 0.99) | L1 |
| `unused-javascript` | all 14 runs | L2 (react-dom's 26 to 29 KiB) |
| `network-dependency-tree-insight` | all 14 | L11 |
| `render-blocking-insight` | 13 (not 404) | L7 |
| `max-potential-fid`, `interactive` | 12 mobile | L11 |
| `bf-cache` | 6 | L11 |
| `is-crawlable` | 5 | L11 |
| `image-delivery-insight` | home (both), 404, product, shop | L5 |
| `first-contentful-paint` / `speed-index` | FCP: shop and both solutions pages; speed index: signed-in solutions | L4, L9 |
| `errors-in-console` | login, 404 | L6, L11 |
| `valid-source-maps` | both solutions pages | L11 |
| `http-status-code` | 404 | L11 |
| `font-display-insight` | signed-in solutions | L11 |
| `layout-shifts` / CLS | `/account/` (4 of 8 runs), shop, product | L3, L10 |

Accessibility audits: none below 1 on any page.

## 9. Experiments

The same pages through a small rewriting proxy (Node, ports 3023 and 3033, in front of the production server); two runs per condition, the better kept, mobile profile. No page was changed in the repository.

| Page | As built | Framework scripts only (react-dom, router, runtime: 124.8 KB gzipped, inline scripts kept) | No scripts at all |
|---|---|---|---|
| Home | 96 / LCP 2.8 s | 98 / 2.5 s | 100 / 1.5 s |
| Product | 94 / 3.1 s | 98 / 2.3 s | 100 / 1.4 s |
| `/s/PHY-E01/` | 93 / 3.1 s | 96 / 2.6 s | 100 / 1.5 s |
| Login | 98 / 2.3 s | 99 / 2.1 s | 100 / 1.4 s |
| Privacy | 95 / 2.9 s | 100 / 1.7 s | 100 / 1.4 s |

The "framework only" column keeps every inline script, so the RSC payload (972 KB on `/s/PHY-E01/`) is still counted, which is why that page stays at 2.6 s. Best practices is 92 on home and product in the two experimental columns (those pages are no longer hydrated; not investigated).

The account page's shift (L3) was measured separately: eight loads of `/account/` under the mobile profile with a per-frame log of the footer's position and the placeholder's bars (all eight: placeholder first, `main` 476 px, footer 541; content next, `main` 1,492 px, footer 1,557).

## 10. Files

HTML reports of three runs, the cookie values scrubbed from the signed-in one:

| File | What it is |
|---|---|
| [lighthouse-nextjs/home-mobile.html](lighthouse-nextjs/home-mobile.html) | `/`, the kept mobile run (96, LCP 2.8 s): the budget miss and the cover finding |
| [lighthouse-nextjs/paper-open-mobile.html](lighthouse-nextjs/paper-open-mobile.html) | `/s/PHY-E01/`, the kept mobile run (93, LCP 3.1 s): the QR landing page every printed code opens, with the 92 KB document |
| [lighthouse-nextjs/account-mobile-cls.html](lighthouse-nextjs/account-mobile-cls.html) | `/account/`, a mobile run with CLS 0.295 (82): the footer shift |

The other HTML reports and all the JSON reports were deleted after their numbers were copied into the tables above. To re-run: build with `NEXT_PUBLIC_SITE_URL=http://localhost:3003`, start the standalone server (or `npm start`) on 3003 with `API_INTERNAL_BASE` at a running Django, sign in once through the email-code form, then `lighthouse <url> --chrome-flags=--headless=new --only-categories=performance,accessibility,best-practices,seo` (add `--extra-headers '{"Cookie":"sessionid=…; csrftoken=…"}'` for the signed-in pages, `--preset=desktop` for desktop, `--ignore-status-code` for the 404). The scripts that ran the pages, the experiments and the INP probe are in [audit-scripts/nextjs/](audit-scripts/nextjs/README.md). Not covered: orders and order pages, the pay page (Razorpay has no keys here), the contact form's send, a real device or network.

## After the fix pass

Phase 8F (the review's fixes, commits `9a749b1` to the CHANGELOG's "Phase 8F review fixes"), measured on 8 October 2026 with the same script (`lh.mjs`, Lighthouse 13.5.0, Chrome 154, mobile preset, two runs each; the account page eight times) on the same Mac. Both builds were served by `next start` on 3005 against one Django on 8105 (`runserver`, the shared development database): **before** is the tree the review read, rebuilt from `4e5c218`; **after** is the fixed tree. Lab LCP moves by up to 1.4 s between two runs of one build here (home before: 1.6 and 2.9 s), so the LCP columns show both runs.

| Page | Perf before (runs) | Perf after (runs) | LCP before | LCP after | CLS before | CLS after | JS before → after (KiB transferred) | Total bytes before → after (KiB) | HTML before → after (KiB) |
|---|---|---|---|---|---|---|---|---|---|
| Home `/` | 100, 96 | 97, 96 | 1.6, 2.9 s | 2.7, 2.8 s | 0 | 0 | 173.3 → **160.8** | 414 → **349** | 23.1 → 23.0 |
| Shop `/shop/` | 90, 94 | 94, 94 | 3.6, 3.0 s | 3.0, 3.0 s | 0, 0.006 | 0.006 | 179.9 → **171.4** | 489 → **480** | 16.7 → 16.1 |
| Product | 91, 94 | 94, 93 | 3.5, 3.2 s | 3.1, 3.3 s | 0.008 | 0, 0.008 | 179.9 → **171.4** | 313 → **305** | 15.6 → 15.7 |
| `/s/PHY-E01/` (open sample) | 93, 97 | 93, 98 | 3.1, 2.4 s | 3.1, 2.1 s | 0 | 0 | 177.8 → **170.4** | 349 → **330** | 92.2 → **81.1** |
| `/account/` (signed in, 8 runs) | 100, 96, 100, 92, 99, 97, 92, **83** | 97, 97, 93, 97, 93, 97, 93, 97 | 1.2 to 3.3 s | 2.7 to 3.2 s | **0.343 in 1 of 8** | **0 in 8 of 8** | 207.3 → **194.4** | 304 → **291** | 13.3 → 13.5 |
| Desktop home / product | 100 / 99 | 100 / 100 | 0.6 / 0.8 s | 0.6 / 0.7 s | 0 | 0 | 173.3 / 179.9 → 160.8 / 171.4 | 417 / 314 → 358 / 310 | |

Accessibility 100, best practices 100 and SEO as before on every run (SEO 66 on `/account/`: `noindex` on purpose).

**JavaScript per route** (`jsload.mjs` in the fix pass's scratch set-up: every script a page loads in Chrome until the network is idle, gzipped at level 6 as Next sends it; Next 16's `next build` no longer prints first-load sizes):

| Route | Before | After | Route | Before | After |
|---|---:|---:|---|---:|---:|
| `/` | 167.9 KB | 155.4 KB | `/cart/` (signed in) | 190.7 KB | 170.2 KB |
| `/shop/`, product | 174.0 KB | 165.4 KB | `/checkout/` | 178.3 KB | 169.3 KB |
| `/books/physics-2027/` | 167.9 KB | 155.4 KB | `/account/` | 199.5 KB | 186.1 KB |
| `/s/PHY-E01/` | 171.9 KB | 164.5 KB | `/account/record/` | 193.0 KB | 172.6 KB |
| `/account/login/` | 177.9 KB | 170.1 KB | `/s/PHY-E02/` (signed in) | 194.6 KB | 179.3 KB |
| `/privacy/`, 404 | 172.5 KB | 163.4 KB | `/revision/` | 173.7 KB | 167.3 KB |

What went: sonner (a toaster of a few lines in its place), Radix Dialog (the browser's own `<dialog>`), the sign-in client in the header (loaded on Log out), the clip player and the Turnstile widget (loaded when used). **The target of 120 KB on public routes is out of reach on this stack**: React 19's react-dom (73.2 KB) and the App Router's client (45.1 KB) with Turbopack's runtime and Next's own entry (12.7 KB) are 131 KB before a line of ExamLeaf's code; what ExamLeaf adds is now 24 to 39 KB on the public routes (55 KB on `/account/`). Getting under 120 KB means fewer framework bytes, not app bytes (no client router on the public pages, or another framework for them).

**What changed against the findings.** L1: LCP is unchanged within the noise (2.7 to 3.1 s on the budget pages, against 2.5 s); the 8 to 13 KB less JavaScript is worth about 0.1 s in the lab, as section 9 predicted. L2: 6 to 21 KB less per route (above). L3: fixed, the account pages keep at least a screen of height while their content streams in. L4: the solutions page's HTML 92.2 → 81.1 KiB (KaTeX's HTML output without its MathML copy, 72.8 KiB; each formula then gets spoken words for screen readers, `rehype-math-speech.ts`, 8 KiB of it), still over the 60 KB budget: the inline RSC payload still repeats the markup (the review's suggestion of one pre-rendered HTML string per solution remains). L5: the covers come at 240 px too, home 414 → 349 KiB. L6 to L11: not part of this pass.
