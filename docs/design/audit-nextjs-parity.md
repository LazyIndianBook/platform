# Parity check: every route of `parity-nextjs.md` answered once

![Component](../assets/badges/component-website.svg) ![Status](../assets/badges/status-archive.svg) ![For developers](../assets/badges/audience-developers.svg)

The review half of Phase 8D's parity check (8 October 2026): every route of [parity-nextjs.md](parity-nextjs.md)
requested once against the Next.js frontend's production build, signed out and signed in. It is kept as the record of
how the new frontend answered the Django site's routes.

Package 8D's parity sanity check (review half), made on 8 October 2026 (IST) against the production build of `examleaf-frontend/` on `http://localhost:3003` with the Django backend on 8103 (the proxy passes Django's prefixes through, as Caddy does). Every route of the tables in [parity-nextjs.md](parity-nextjs.md) was requested once with `curl`-style GETs (redirects not followed), **anonymous** and **signed in** (a temporary non-staff student, deleted afterwards), with real values filled in: the Physics Sample Papers slug, the open paper `PHY-E01`, an order of the student (`EL-2026-000003`, awaiting payment), the token of that order for the guest routes, one saved address, one marks attempt. The routes that the document marks **API** are POST-only pages of the old site: the API endpoint named in its notes was requested with GET and counts as answering when it exists (200, or 401/405 where the method or the sign-in is wrong). That is 123 routes and variants: every row of the document's tables, the variants its notes name (the lowercase code, a wrong order number, a missing attempt, a renamed product's old slug) and a few neighbours (`/account/verify-email/`, `/api/docs/`, the static Open Graph image, `/sitemap-django.xml`). The script is [audit-scripts/nextjs/parity.mjs](audit-scripts/nextjs/parity.mjs) (set-up in its [README](audit-scripts/nextjs/README.md)); the table below is generated from its output.

## Result

**114 of the 123 answer as documented; nine do not** (five groups):

| Route | Documented | Actual | Cause and fix |
|---|---|---|---|
| `/account/2fa/webauthn/reauthenticate/` | not built (404) | 307 to `/account/security/#passkeys` | the wildcard `["/account/2fa/webauthn/:path*", "/account/security/#passkeys"]` in `next.config.ts` catches it; a staff member sent there for a passkey re-authentication lands on the Security page. Document it as redirected, or list the path before the wildcard with a 404 |
| `/account/google/login/`, `/account/google/login/callback/` | Django (the `/account/google/` prefix) | 404 from Django's own page | the Google provider is not configured here (`config` says `google: false`), so allauth registers no such URL; cannot be checked without keys |
| `/checkout/<n>/pay/`, `/checkout/<n>/done/` (anonymous) | built (private) | 200 with the placeholder and a streamed `NEXT_REDIRECT;replace;/account/login/?next=…;307` instead of a 307 | the pages stream behind `loading.tsx`, so the status is already 200 when `requireUser()` redirects; the browser follows it, a visitor with scripts off sees "Loading" (the 8C notes record this for the account pages; the checkout's pay and done pages behave the same). Signed in: 200 |
| `/shop/category/<slug>/`, `/shop/collection/<slug>/`, a renamed product's old slug | built / 308 to the new slug | 404 for the unknown slugs tried | the development database has no shelf, collection or renamed product (`categories/` and `collections/` are empty), so only the not-found answer could be seen; the routes themselves could not be exercised |
| `/sitemap-django.xml` | Django (prefix list) | 404 | Django has no such sitemap; the commit `97ea4c6` (made while this review ran) dropped the prefix from Caddy and the frontend |

Everything else answered as documented, including: the 25 redirect rules (each a 307 to the documented destination, none looping, at most two hops), the "not built" and "Django" rows (404, 302 to the admin log-in, 405, an image or the API's own answer, as expected), the `API` rows (each endpoint exists: 200, 401 or 405), the guest routes by token, the real 404 of a wrong order number and a missing attempt for a signed-in visitor (and the redirect to log in for an anonymous one), `/s/phy-e01/` to `/s/PHY-E01/` (308), `/orders/<n>/` to `/account/orders/<n>/` (308), `/orders/` to the lookup or My orders (307), and the route handlers (`/robots.txt`, `/sitemap.xml`, `/manifest.webmanifest`, `/sw.js`, `/offline/`, `/api/health/`).

Two things the table shows that the document does not say:

- Anonymous requests to every private page answer **307 to `/account/login/?next=<the path>`** (the account pages, `/account/reauthenticate/`) but the cart and the checkout answer **200** for a visitor (the guest cart and guest checkout), which is documented.
- The fragment of a redirect is lost on the second hop for an anonymous visitor: `/account/data/` goes to `/account/privacy/#data`, then to log in with `next=/account/privacy/` (no `#data`), so after logging in the page opens at the top.

## Table

`§` is the section of `parity-nextjs.md` (A Discover, B Buy, C After the order, D Record, E Account and data rights, F Sign-in and recovery, G to I Staff, system, development; `x` = a neighbour). "Documented as" is the document's status; a path with `<token>` stands for the real token of the student's order.

| § | Documented route | Documented as | Path tried | Anonymous | Signed in | Answers as documented |
|---|---|---|---|---|---|---|
| A | `/` | built | `/` | 200 | 200 | yes |
| A | `/books/<slug>/` | built | `/books/physics-2027/` | 200 | 200 | yes |
| A | `/s/<code>/` | built | `/s/PHY-E01/` | 200 | 200 | yes |
| A | `/s/<code>/ (any case)` | built: any case -> the printed code | `/s/phy-e01/` | 308 → `/s/PHY-E01/` | 308 → `/s/PHY-E01/` | yes |
| A | `/qr/<code>.png` | Django | `/qr/PHY-E01.png` | 200 (image/png) | 200 (image/png) | yes |
| A | `/about/` | built | `/about/` | 200 | 200 | yes |
| A | `/privacy/` | built | `/privacy/` | 200 | 200 | yes |
| A | `/terms/` | built | `/terms/` | 200 | 200 | yes |
| A | `/refunds/` | built | `/refunds/` | 200 | 200 | yes |
| A | `/shipping/` | built | `/shipping/` | 200 | 200 | yes |
| A | `/contact/` | built | `/contact/` | 200 | 200 | yes |
| A | `/offline/` | built | `/offline/` | 200 | 200 | yes |
| A | `/revision/` | built | `/revision/` | 200 | 200 | yes |
| B | `/shop/` | built | `/shop/` | 200 | 200 | yes |
| B | `/shop/?kind=` | built (kind dropped) | `/shop/?kind=sample-papers` | 200 | 200 | yes |
| B | `/shop/category/<slug>/` | built | `/shop/category/no-such-shelf/` | 404 | 404 | **no**: no shelf exists in the development database: only the 404 for an unknown slug could be seen |
| B | `/shop/collection/<slug>/` | built | `/shop/collection/no-such-collection/` | 404 | 404 | **no**: no collection exists: only the 404 for an unknown slug could be seen |
| B | `/shop/<slug>/` | built | `/shop/physics-sample-papers-2027/` | 200 | 200 | yes |
| B | `/shop/<slug>/ (renamed product, old slug)` | built: 308 to the new slug (no renamed product here: 404 expected) | `/shop/old-slug-nothing/` | 404 | 404 | **no**: no renamed product exists: the 308 could not be seen (an unknown slug gives 404) |
| B | `/shop/<slug>/review/ (POST)` | API products/<slug>/reviews/ | `/api/v1/products/physics-sample-papers-2027/reviews/` | 200 (application/json) | 200 (application/json) | yes |
| B | `/shop/<slug>/stock-alert/ (POST)` | API products/<slug>/stock-alert/ | `/api/v1/products/physics-sample-papers-2027/stock-alert/` | 401 | 405 | yes |
| B | `/shop/school-orders/` | built | `/shop/school-orders/` | 200 | 200 | yes |
| B | `/shop/pin/<pin>/` | API shipping/quote/?pin= | `/api/v1/shipping/quote/?pin=781001&state=AS&amount=299` | 200 (application/json) | 200 (application/json) | yes |
| B | `/shop/media/<path>` | Django | `/shop/media/products/physics/2_3/400w.avif` | 200 (image/avif) | 200 (image/avif) | yes |
| B | `/cart/` | built | `/cart/` | 200 | 200 | yes |
| B | `/cart/add/<id>/ (POST)` | API cart/items/ | `/api/v1/cart/` | 200 (application/json) | 200 (application/json) | yes |
| B | `/checkout/` | built | `/checkout/` | 200 | 200 | yes |
| B | `/checkout/<n>/pay/` | built | `/checkout/EL-2026-000003/pay/` | 200 | 200 | **no**: anonymous: 200 with a client-side redirect to log in (streamed behind `loading.tsx`), not a 307 |
| B | `/checkout/t/<token>/pay/` | built (guest) | `/checkout/t/<token>/pay/` | 200 | 200 | yes |
| B | `/checkout/<n>/paid/ (POST)` | API orders/<n>/payment/confirm/ | `/api/v1/orders/EL-2026-000003/payment/confirm/` | 401 | 405 | yes |
| B | `/checkout/<n>/done/` | built | `/checkout/EL-2026-000003/done/` | 200 | 200 | **no**: anonymous: 200 with a client-side redirect to log in, not a 307 |
| B | `/checkout/t/<token>/done/` | built (guest) | `/checkout/t/<token>/done/` | 200 | 200 | yes |
| C | `/account/orders/` | built | `/account/orders/` | 307 → `/account/login/?next=%2Faccount%2Forders%2F` | 200 | yes |
| C | `/account/orders/<n>/` | built | `/account/orders/EL-2026-000003/` | 307 → `/account/login/?next=%2Faccount%2Forders%2FEL-2026-000003%2F` | 200 | yes |
| C | `/account/orders/<wrong>/` | built: a real 404 | `/account/orders/EL-2026-999999/` | 307 → `/account/login/?next=%2Faccount%2Forders%2FEL-2026-999999%2F` | 404 | yes |
| C | `/account/orders/<n>/cancel/ (POST)` | API orders/<n>/cancel/ | `/api/v1/orders/EL-2026-000003/cancel/` | 401 | 405 | yes |
| C | `/account/orders/<n>/invoice/` | redirected -> /api/v1/orders/<n>/invoice/ | `/account/orders/EL-2026-000003/invoice/` | 307 → `/api/v1/orders/EL-2026-000003/invoice/` | 307 → `/api/v1/orders/EL-2026-000003/invoice/` | yes |
| C | `/account/orders/<n>/credit-notes/<id>/` | redirected -> /api/v1/orders/<n>/credit-notes/<id>/ | `/account/orders/EL-2026-000003/credit-notes/1/` | 307 → `/api/v1/orders/EL-2026-000003/credit-notes/1/` | 307 → `/api/v1/orders/EL-2026-000003/credit-notes/1/` | yes |
| C | `/orders/lookup/` | built | `/orders/lookup/` | 200 | 200 | yes |
| C | `/orders/t/<token>/` | built | `/orders/t/<token>/` | 200 | 200 | yes |
| C | `/orders/t/<token>/cancel/ (POST)` | API orders/t/<token>/cancel/ | `/api/v1/orders/t/<token>/cancel/` | 405 | 405 | yes |
| C | `/orders/t/<token>/invoice/` | redirected -> /api/v1/orders/t/<token>/invoice/ | `/orders/t/<token>/invoice/` | 307 → `/api/v1/orders/t/<order-token>/invoice/` | 307 → `/api/v1/orders/t/<order-token>/invoice/` | yes |
| C | `/orders/t/<token>/credit-notes/<id>/` | redirected -> /api/v1/orders/t/<token>/credit-notes/<id>/ | `/orders/t/<token>/credit-notes/1/` | 307 → `/api/v1/orders/t/<order-token>/credit-notes/1/` | 307 → `/api/v1/orders/t/<order-token>/credit-notes/1/` | yes |
| C | `/account/addresses/add/` | redirected -> /account/addresses/ | `/account/addresses/add/` | 307 → `/account/addresses/` | 307 → `/account/addresses/` | yes |
| C | `/account/addresses/<id>/` | redirected -> /account/addresses/ | `/account/addresses/6/` | 307 → `/account/addresses/` | 307 → `/account/addresses/` | yes |
| C | `/account/addresses/<id>/delete/ (POST)` | API addresses/<id>/ | `/api/v1/addresses/6/` | 401 | 200 (application/json) | yes |
| C | `/orders/` | built (extra): redirect to My orders or the lookup | `/orders/` | 307 → `/orders/lookup/` | 307 → `/account/orders/` | yes |
| C | `/orders/<n>/` | built (extra): redirect | `/orders/EL-2026-000003/` | 308 → `/account/orders/EL-2026-000003/` | 308 → `/account/orders/EL-2026-000003/` | yes |
| D | `/account/record/` | built | `/account/record/` | 307 → `/account/login/?next=%2Faccount%2Frecord%2F` | 200 | yes |
| D | `/account/record/add/<code>/` | redirected -> /s/<code>/#record | `/account/record/add/PHY-E01/` | 307 → `/s/PHY-E01/#record` | 307 → `/s/PHY-E01/#record` | yes |
| D | `/account/record/<id>/edit/` | built | `/account/record/4/edit/` | 307 → `/account/login/?next=%2Faccount%2Frecord%2F4%2Fedit%2F` | 200 | yes |
| D | `/account/record/<missing>/edit/` | built: a real 404 | `/account/record/99999/edit/` | 307 → `/account/login/?next=%2Faccount%2Frecord%2F99999%2Fedit%2F` | 404 | yes |
| E | `/account/` | built | `/account/` | 307 → `/account/login/?next=%2Faccount%2F` | 200 | yes |
| E | `/account/teacher/` | built | `/account/teacher/` | 307 → `/account/login/?next=%2Faccount%2Fteacher%2F` | 200 | yes |
| E | `/account/data/` | redirected -> /account/privacy/#data | `/account/data/` | 307 → `/account/privacy/#data` | 307 → `/account/privacy/#data` | yes |
| E | `/account/delete/` | redirected -> /account/privacy/#delete | `/account/delete/` | 307 → `/account/privacy/#delete` | 307 → `/account/privacy/#delete` | yes |
| E | `/account/delete/cancel/ (POST)` | API DELETE me/deletion/ | `/api/v1/me/deletion/` | 401 | 405 | yes |
| E | `/account/parent-consent/ (POST)` | API me/parent-consent/ | `/api/v1/me/parent-consent/` | 401 | 405 | yes |
| E | `/account/sms-updates/ (POST)` | API PATCH me/ | `/api/v1/me/` | 401 | 200 (application/json) | yes |
| E | `/c/<token>/` | built | `/c/bogus-token/` | 200 | 200 | yes |
| E | `/account/details/` | built (extra) | `/account/details/` | 307 → `/account/login/?next=%2Faccount%2Fdetails%2F` | 200 | yes |
| E | `/account/addresses/` | built (extra) | `/account/addresses/` | 307 → `/account/login/?next=%2Faccount%2Faddresses%2F` | 200 | yes |
| E | `/account/security/` | built (extra) | `/account/security/` | 307 → `/account/login/?next=%2Faccount%2Fsecurity%2F` | 200 | yes |
| E | `/account/privacy/` | built (extra) | `/account/privacy/` | 307 → `/account/login/?next=%2Faccount%2Fprivacy%2F` | 200 | yes |
| F | `/account/login/` | built | `/account/login/` | 200 | 200 | yes |
| F | `/account/signup/` | built | `/account/signup/` | 200 | 200 | yes |
| F | `/account/logout/` | built | `/account/logout/` | 200 | 200 | yes |
| F | `/account/inactive/` | not built | `/account/inactive/` | 404 | 404 | yes |
| F | `/account/reauthenticate/` | built | `/account/reauthenticate/` | 307 → `/account/login/?next=%2Faccount%2Freauthenticate%2F` | 200 | yes |
| F | `/account/email/` | redirected -> /account/security/#change-email | `/account/email/` | 307 → `/account/security/#change-email` | 307 → `/account/security/#change-email` | yes |
| F | `/account/confirm-email/` | redirected -> /account/verify-email/ | `/account/confirm-email/` | 307 → `/account/verify-email/` | 307 → `/account/verify-email/` | yes |
| F | `/account/verify-email/` | built (headless page) | `/account/verify-email/` | 200 | 200 | yes |
| F | `/account/password/change/` | redirected -> /account/security/#change-password | `/account/password/change/` | 307 → `/account/security/#change-password` | 307 → `/account/security/#change-password` | yes |
| F | `/account/password/set/` | redirected -> /account/security/#change-password | `/account/password/set/` | 307 → `/account/security/#change-password` | 307 → `/account/security/#change-password` | yes |
| F | `/account/password/reset/` | built | `/account/password/reset/` | 200 | 200 | yes |
| F | `/account/password/reset/done/` | redirected -> /account/password/reset/ | `/account/password/reset/done/` | 307 → `/account/password/reset/` | 307 → `/account/password/reset/` | yes |
| F | `/account/password/reset/key/<uid>-<key>/` | built | `/account/password/reset/key/abc-def/` | 200 | 200 | yes |
| F | `/account/password/reset/key/done/` | redirected -> /account/login/ | `/account/password/reset/key/done/` | 307 → `/account/login/` | 307 → `/account/login/` | yes |
| F | `/account/login/code/` | redirected -> /account/login/ | `/account/login/code/` | 307 → `/account/login/` | 307 → `/account/login/` | yes |
| F | `/account/login/code/confirm/` | redirected -> /account/login/ | `/account/login/code/confirm/` | 307 → `/account/login/` | 307 → `/account/login/` | yes |
| F | `/account/phone/verify/` | redirected -> /account/security/#mobile-number | `/account/phone/verify/` | 307 → `/account/security/#mobile-number` | 307 → `/account/security/#mobile-number` | yes |
| F | `/account/phone/change/` | redirected -> /account/security/#mobile-number | `/account/phone/change/` | 307 → `/account/security/#mobile-number` | 307 → `/account/security/#mobile-number` | yes |
| F | `/account/2fa/` | built | `/account/2fa/` | 307 → `/account/login/?next=%2Faccount%2F2fa%2F` | 200 | yes |
| F | `/account/2fa/authenticate/` | built | `/account/2fa/authenticate/` | 200 | 200 | yes |
| F | `/account/2fa/reauthenticate/` | not built | `/account/2fa/reauthenticate/` | 404 | 404 | yes |
| F | `/account/2fa/webauthn/reauthenticate/` | not built | `/account/2fa/webauthn/reauthenticate/` | 307 → `/account/security/#passkeys` | 307 → `/account/security/#passkeys` | **no**: documented "not built" (404), but the wildcard `/account/2fa/webauthn/:path*` redirects it to `/account/security/#passkeys` |
| F | `/account/2fa/totp/activate/` | redirected -> /account/2fa/ | `/account/2fa/totp/activate/` | 307 → `/account/2fa/` | 307 → `/account/2fa/` | yes |
| F | `/account/2fa/totp/deactivate/` | redirected -> /account/2fa/ | `/account/2fa/totp/deactivate/` | 307 → `/account/2fa/` | 307 → `/account/2fa/` | yes |
| F | `/account/2fa/recovery-codes/` | redirected -> /account/2fa/ | `/account/2fa/recovery-codes/` | 307 → `/account/2fa/` | 307 → `/account/2fa/` | yes |
| F | `/account/2fa/recovery-codes/generate/` | redirected -> /account/2fa/ | `/account/2fa/recovery-codes/generate/` | 307 → `/account/2fa/` | 307 → `/account/2fa/` | yes |
| F | `/account/2fa/recovery-codes/download/` | redirected -> /account/2fa/ | `/account/2fa/recovery-codes/download/` | 307 → `/account/2fa/` | 307 → `/account/2fa/` | yes |
| F | `/account/2fa/webauthn/` | redirected -> /account/security/#passkeys | `/account/2fa/webauthn/` | 307 → `/account/security/#passkeys` | 307 → `/account/security/#passkeys` | yes |
| F | `/account/2fa/webauthn/add/` | redirected -> /account/security/#passkeys | `/account/2fa/webauthn/add/` | 307 → `/account/security/#passkeys` | 307 → `/account/security/#passkeys` | yes |
| F | `/account/2fa/webauthn/keys/<id>/remove/` | redirected -> /account/security/#passkeys | `/account/2fa/webauthn/keys/1/remove/` | 307 → `/account/security/#passkeys` | 307 → `/account/security/#passkeys` | yes |
| F | `/account/2fa/webauthn/keys/<id>/edit/` | redirected -> /account/security/#passkeys | `/account/2fa/webauthn/keys/1/edit/` | 307 → `/account/security/#passkeys` | 307 → `/account/security/#passkeys` | yes |
| F | `/account/2fa/webauthn/login/` | API headless auth/webauthn/login | `/_allauth/browser/v1/auth/webauthn/login` | 200 (application/json) | 200 (application/json) | yes |
| F | `/account/3rdparty/login/cancelled/` | redirected -> /account/login/ | `/account/3rdparty/login/cancelled/` | 307 → `/account/login/` | 307 → `/account/login/` | yes |
| F | `/account/3rdparty/login/error/` | redirected -> /account/login/ | `/account/3rdparty/login/error/` | 307 → `/account/login/` | 307 → `/account/login/` | yes |
| F | `/account/3rdparty/signup/` | redirected -> /account/signup/ | `/account/3rdparty/signup/` | 307 → `/account/signup/` | 307 → `/account/signup/` | yes |
| F | `/account/3rdparty/` | redirected -> /account/security/#google | `/account/3rdparty/` | 307 → `/account/security/#google` | 307 → `/account/security/#google` | yes |
| F | `/account/google/login/` | Django | `/account/google/login/` | 404 | 404 | **no**: Django answers 404 here: the Google provider is not configured (`config` says `google: false`); not testable without keys |
| F | `/account/google/login/callback/` | Django | `/account/google/login/callback/` | 404 | 404 | **no**: as above |
| F | `/account/register/` | redirected -> /account/signup/ | `/account/register/` | 307 → `/account/signup/` | 307 → `/account/signup/` | yes |
| F | `/account/social/signup/` | not built | `/account/social/signup/` | 404 | 404 | yes |
| F | `/account/social/login/cancelled/` | not built | `/account/social/login/cancelled/` | 404 | 404 | yes |
| F | `/account/social/login/error/` | not built | `/account/social/login/error/` | 404 | 404 | yes |
| F | `/account/social/connections/` | not built | `/account/social/connections/` | 404 | 404 | yes |
| G | `/learn/preview/<clip>/` | Django | `/learn/preview/1/` | 302 → `/admin/login/?next=/learn/preview/1/` | 302 → `/admin/login/?next=/learn/preview/1/` | yes |
| G | `/admin/` | Django | `/admin/` | 302 → `/admin/login/?next=/admin/` | 302 → `/admin/login/?next=/admin/` | yes |
| H | `/robots.txt` | built | `/robots.txt` | 200 (text/plain) | 200 (text/plain) | yes |
| H | `/sitemap.xml` | built | `/sitemap.xml` | 200 (application/xml) | 200 (application/xml) | yes |
| H | `/manifest.webmanifest` | built | `/manifest.webmanifest` | 200 (application/manifest+json) | 200 (application/manifest+json) | yes |
| H | `/sw.js` | built | `/sw.js` | 200 (application/javascript) | 200 (application/javascript) | yes |
| H | `/favicon.ico` | redirected -> /favicon-32.png | `/favicon.ico` | 307 → `/favicon-32.png` | 307 → `/favicon-32.png` | yes |
| H | `/health/` | Django | `/health/` | 200 | 200 | yes |
| H | `/health/web/` | Django | `/health/web/` | 200 | 200 | yes |
| H | `/api/health/` | frontend process check | `/api/health/` | 200 (application/json) | 200 (application/json) | yes |
| H | `/shop/webhooks/razorpay/` | Django | `/shop/webhooks/razorpay/` | 405 | 405 | yes |
| H | `/learn/hls/<token>/<file>` | Django | `/learn/hls/tok/index.m3u8` | 404 | 404 | yes |
| I | `/__debug__/` | Django (development only) | `/__debug__/` | 404 | 404 | yes |
| x | `/sitemap-django.xml` | Django (prefix list) | `/sitemap-django.xml` | 404 | 404 | **no**: Django has no such sitemap (the prefix was dropped from Caddy and the frontend by commit `97ea4c6` while this review ran) |
| x | `/api/docs/` | Django (prefix list) | `/api/docs/` | 200 | 200 | yes |
| x | `/static/img/og-default.jpg` | Django (static, used by the metadata) | `/static/img/og-default.jpg` | 200 (image/jpeg) | 200 (image/jpeg) | yes |

## After the fix pass (Phase 8F)

The three groups that could be fixed in the frontend answer as documented now: `/account/2fa/webauthn/reauthenticate/` is a 404 (the passkeys redirect excludes it), an anonymous visitor's `/checkout/<n>/pay/` and `/checkout/<n>/done/` get a real 307 to `/account/login/?next=…` (the checkout's loading placeholder covers the address step only), and `/sitemap-django.xml` is gone from `parity-nextjs.md` and from `parity.mjs`. The Google, shelf, collection and renamed-product rows still need keys or data to be seen. `e2e/smoke.spec.ts` checks the first two.
