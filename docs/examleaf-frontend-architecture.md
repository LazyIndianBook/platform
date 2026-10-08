# ExamLeaf web frontend — architecture assessment (2026-10-08)

The founder's brief asks for a distinctive, premium web experience with clear architectural boundaries, and prefers a decoupled Next.js/TypeScript frontend "where practical", while warning against migrating frameworks for fashion. This is the assessment and the decision taken, with the incremental path if the migration is chosen.

## What exists
- **Backend**: Django 6.1 with the REST API v1 (DRF, JWT and session auth, OpenAPI at `/api/docs/`) covering content, attempts, shop, learn and the email/phone code flows; allauth for every sign-in method (email + password, login by code, phone OTP, passkeys, Google, staff TOTP), the admin, Celery workers, Razorpay, GST invoices, the LMS pipeline. Business rules, payment verification, entitlements and permissions live here and are tested (342 tests at the time of writing).
- **Web frontend**: server-rendered Django templates, one stylesheet built from the token layer and component spec of the Design canvas, self-hosted subset fonts (about 45 KB of Latin fonts), no JavaScript framework (two small self-hosted scripts plus KaTeX on solutions pages), strict Content-Security-Policy without nonces, PWA manifest and service worker, structured data and Open Graph. The redesign (stages 1, 2a, 2b) is being applied to every template.
- **Audience**: Class 12 students in Assam on low-end Android phones and slow networks; parents who buy; school staff; the publisher's staff in the admin.

## Options
| | Keep Django-rendered web (current) | Decoupled Next.js app (App Router, TypeScript) + Django API |
|---|---|---|
| First paint on a low-end phone | HTML + 1 CSS file + fonts; no hydration; the fastest achievable | React runtime and hydration on every route unless kept to server components; Next's image and font pipelines help; needs discipline to stay under budget |
| Server-side gating of paid/personal content | By construction: the view decides | Must be re-done in route handlers/middleware against the API; the API already enforces it, the BFF must not cache user data |
| Sign-in flows | allauth pages (MFA, passkeys, phone, Google) ready | Needs allauth headless (JSON API for all flows) — now being added so both frontends can use it |
| Deployment | One image: web + worker + beat behind Caddy | A second runtime (Node) and container, its own build, health check and rollout; one more thing that can fail |
| Independent frontend team and releases | Templates live in the Django repo; releases ride with the backend | Fully independent develop/test/build/deploy; typed API client from OpenAPI |
| Rich interactions (revision player, dashboards, previews) | Possible with vanilla JS and CSS, but each one is hand-built | The natural home for them |
| Tests | 342 Django tests cover templates and flows | Vitest + Playwright to be written; backend tests stay |
| Work and risk now | Finishing stages 2a/2b and a craft pass | Porting about 45 routes, re-establishing CSP (nonces), auth, Razorpay checkout, PWA, SEO; weeks of work and a period with two frontends |

## Decision
1. **Ship the Django-rendered frontend as the production web experience now.** For this audience and team it is the faster, simpler and safer product: no hydration cost, authorisation by construction, one deployment unit, and the design quality asked for (typography, composition, motion, states) is CSS/HTML craft that does not need a client framework. Migrating now would delay launch and spend effort re-building what works.
2. **Make the backend contract complete so a decoupled frontend is possible without backend changes**: allauth headless for every sign-in flow, API v1 endpoints for every web capability, a `GET /api/v1/config/` of feature flags, OpenAPI tags and examples, and a frontend integration guide in API.md. This is the "documented API contracts → independent backend services" boundary the brief asks for, and the mobile app needs it anyway.
3. **Recommend the Next.js frontend as a later, incremental step when a reason exists** (a separate frontend team, or interaction-heavy student surfaces on the web such as a revision player and progress dashboard). Strangler path: Next.js app at `/app/*` for the student surfaces first (served by Caddy next to Django), sharing the token layer and components spec; then catalogue and checkout; the marketing pages last or never. Session handling through a BFF route using the headless `browser` client on the same origin; CSP with per-request nonces in Next middleware; `Cache-Control: private, no-store` for every personalised route; Playwright journeys against a seeded Django backend; a performance budget per route (LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at the 75th percentile on a mid-range Android profile in the lab, field data from the Chrome UX Report once live).
4. **This is a consequential decision and is recorded for the founder.** If the founder prefers the Next.js frontend now, the backend work in point 2 is the prerequisite and is being done; the design system (tokens, components, motion rules) carries over unchanged.

## Performance and accessibility budgets for the current frontend (lab, mid-range Android profile, slow 4G)
- LCP ≤ 2.5 s on `/`, `/shop/`, a product page, `/s/<code>/` and `/account/login/`; CLS ≤ 0.1 (fonts preloaded with metric-matched fallbacks, images with dimensions); INP ≤ 200 ms (no long tasks; KaTeX rendering deferred below the fold).
- Page weight: HTML ≤ 60 KB, CSS ≤ 60 KB, fonts ≤ 60 KB Latin, hero images ≤ 150 KB total, no third-party scripts except KaTeX (solutions) and Razorpay (payment page).
- WCAG 2.2 AA: target size minimum 24 px (44 px for primary controls), focus not obscured, visible focus, consistent help, redundant entry avoided in checkout, dragging not required; verified with automated checks and a manual keyboard and screen-reader pass.

## Status
(appended by the builders)
- **Backend contract, point 2 (2026-10-08): done.** allauth.headless at `/_allauth/` (`browser` client same-origin with the session cookie and CSRF; `app` client with `X-Session-Token`, exchanged for the JWT pair at `POST /api/v1/auth/exchange/`), with the site's rules on every flow (student details and consent at every sign-up through `ACCOUNT_SIGNUP_FORM_CLASS`, Turnstile, rate limits, SMS cap, staff authenticators). API v1 now covers teacher access, a parent's link, SMS updates, reviews, back-in-stock alerts, school quotations, the order's emailed link, `config/` feature flags and the legal pages; OpenAPI tagged by area with examples (`--fail-on-warn` clean); API.md "Frontend integration guide" has the boundaries, errors, pagination, limits, caching and the login-by-code, phone, passkey, Google and second-step sequences. Not covered yet: guest checkout through the API (guests buy on the website) and the app's passkey association files.
