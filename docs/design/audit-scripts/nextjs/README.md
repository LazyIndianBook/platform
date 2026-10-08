# Scripts of the Next.js frontend review (Phase 8D, review half)

The scripts behind [audit-nextjs-lighthouse.md](../../audit-nextjs-lighthouse.md), [audit-nextjs-accessibility.md](../../audit-nextjs-accessibility.md), [audit-nextjs-security.md](../../audit-nextjs-security.md), [audit-nextjs-parity.md](../../audit-nextjs-parity.md) and the screenshots in `../../screenshots/nextjs/`. They were run on 8 October 2026 against `examleaf-frontend/` at `b10bde1` and are kept so that a number in a report can be reproduced. None of them changes `examleaf-frontend/` or `examleaf-web/` (the unit scripts transpile single frontend files to a scratch folder and run them there).

## Set-up

1. A scratch folder for the run, here called `$REVIEW_DIR` (nothing in it is committed): `npm i lighthouse@13 axe-core@4.14 puppeteer-core@25 sharp` in it, and copy these scripts into it (they read `node_modules/`, `cookies.json` and `django.log` from `$REVIEW_DIR`; the folder defaults to the current directory). Chrome is expected at `/Applications/Google Chrome.app` (`CHROME` in `lib.mjs`, `CHROME_PATH` in `lh.mjs`).
2. The backend, from `examleaf-web`, with its console log in `$REVIEW_DIR/django.log` (the log-in script reads the emailed code from it):
   `SITE_URL=http://localhost:3003 CSRF_TRUSTED_ORIGINS=http://localhost:3003 USE_X_FORWARDED_HOST=1 .venv/bin/python manage.py runserver 8103 --noreload > $REVIEW_DIR/django.log 2>&1`
   (`seed_shop --stock 100` if a book is out of stock; `SUPPORT_EMAIL` set to see the contact form.)
3. The frontend: `NEXT_PUBLIC_SITE_URL=http://localhost:3003 npm run build` in `examleaf-frontend`, copy `.next/standalone`, `.next/static` and `public` as the Dockerfile does, and start it: `NODE_ENV=production PORT=3003 API_INTERNAL_BASE=http://localhost:8103 node server.js`.
4. The temporary student: `.venv/bin/python manage.py shell < mkuser.py` (a non-staff account, verified email, no password), then `node login.mjs` (signs in through the email-code form, writes `cookies.json`). `order.mjs` places the unpaid order and `mkattempt.mjs` saves one marks attempt, for the order page and the record.

## What produced what

| Report | Scripts |
|---|---|
| Lighthouse | `lh.mjs <tag>` (all pages, mobile twice and desktop once; `lh2.mjs` takes `REPEAT` and `NODESKTOP` for the experiments), `digest.py <tag>` (reads the JSON reports, keeps the better run; `audits.py`, `lcp.py` print the failing audits and the LCP elements), `inp.mjs` (lab INP), `cls-account.mjs` and `cls-track.mjs` (the `/account/` shift), `noscript-proxy.mjs` and `framework-proxy.mjs` (the script-removal experiments of section 9: `node noscript-proxy.mjs <listen> <upstream>`) |
| Accessibility | `a11y-pages.mjs` (axe and the Tab walk on all 38 pages; `ONLY` and `EXTRA` select pages), `a11y-paper-walk.mjs` (the solutions pages' real stop counts), `a11y-menu`, `a11y-dialogs`, `a11y-stepper`, `a11y-toast`, `a11y-toast2`, `a11y-forms`, `a11y-forms2`, `a11y-otp`, `a11y-delete`, `a11y-devices`, `a11y-new`, `a11y-new2`, `a11y-zoom`, `a11y-motion`, `contrast.mjs`, `cart-remove-confirm.mjs`; `inpage.mjs` holds the probes that run in the page; `evidence.mjs` makes the evidence pictures |
| Security | `sec-headers.mjs` (CSP and Cache-Control per route), `sec-nonce.mjs`, `sec-rsc.mjs`, `sec-rsc2.mjs`, `sec-sw.mjs`, `sec-bfcache.mjs`, `sec-redirect.mjs` (the `?next=` vector end to end; the host is `attacker.invalid`), `sec-razorpay.mjs` (Razorpay stubbed; nothing leaves the machine), `sec-throttle.mjs` (320 lookups, then the recovery), `outage.sh` (stop Django first), `ts-run.cjs`, `sec-csp-unit.cjs`, `sec-next-unit.cjs` (run `safeNext`, `buildCsp` and `isPersonalPage` from the frontend's own files; `FRONTEND_DIR` points at the checkout) |
| Parity | `parity.mjs` (every route of `parity-nextjs.md`, anonymous and signed in; writes `parity.json`) |
| Fix pass (8F) | `jsload.mjs` (the JavaScript each page loads in Chrome, gzipped; `BASE`, `AUTH=1` for the signed-in cookies), `overflow.mjs <width> <paths>` (the page's width and what sticks out), `a11y-fix.mjs` (F1, F3, F4 and F6 again with real key presses); Lighthouse with `lh.mjs <tag> home,shop,product,paperopen,account` and `REPEAT=6 NODESKTOP=1 lh2.mjs` |
| Screenshots | `shots.mjs` (`SHOTS_OUT` is the target folder) |

## Taking it down

Stop both servers, then from `examleaf-web`, with `DATABASE_URL` pointing at the database used:

```
.venv/bin/python manage.py shell < cleanup-temp-user.py              # lists what would go
APPLY=1 .venv/bin/python manage.py shell < cleanup-temp-user.py      # deletes the student, its unpaid order, history rows and sessions
```

Then delete `$REVIEW_DIR` (it holds `cookies.json`, `django.log` with the emailed codes and the order token, and the Lighthouse reports).
