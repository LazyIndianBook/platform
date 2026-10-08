# (account) — package 8C, not built yet

TODO(8C): the account and revision pages go here, at the paths the Django site uses today (so emails, runbooks
and bookmarks keep working). Until they exist these URLs are served by Django (Caddy's default upstream is Django
until the switch in docs/examleaf-phase8-nextjs-plan.md, "Then").

- `account/page.tsx` — My account (`/account/`): record summary, orders, details and addresses, phone, passkeys and
  MFA management, parent's consent state and resend (`POST /api/v1/me/parent-consent/`), data export and deletion.
- `account/record/page.tsx` — My record (`/account/record/`, `GET /api/v1/attempts/`), plus saving marks from a
  solutions page (`POST /api/v1/attempts/`; the `#record` card of `/s/<code>/` links here for now).
- `account/teacher/`, `account/orders/` (with 8B), `revision/` (entitlements, chapters, clips with hls.js).

How to build a page here:

- `layout.tsx` already redirects anyone without a session to `/account/login/?next=<path>` and marks the pages
  `noindex`. Personal data comes from `serverApi` with `await personalFetch()` (cookies forwarded, never cached), or
  from the browser `api` client with `personal()` (a 401 sends the visitor to log in and back).
- Sensitive changes need a recent password: on a 401 with a pending `reauthenticate` flow, send the visitor to
  `/account/reauthenticate/?next=<path>` (`nextRoute()` in `src/lib/auth/headless.ts` does it).
- Use the components in `src/components/ui/` (Card, Field, Table, Pagination, Timeline, EmptyState …); no new
  colours or shadows outside `src/app/globals.css`.
